"""Audio composition — voice extraction, segment management, music generation."""

import json
import logging
import re
import shutil
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from packages.core.config import BASE_PATH
from packages.core.db import get_char_project_map
from packages.core.models import MusicGenerateRequest

logger = logging.getLogger(__name__)
router = APIRouter()

ACE_STEP_URL = "http://localhost:8440"
MUSIC_CACHE = BASE_PATH / "output" / "music_cache"
MUSIC_CACHE.mkdir(parents=True, exist_ok=True)

# Mood → music generation caption mapping
MOOD_PROMPTS = {
    "tense": "dark suspenseful orchestral, low strings, building tension, minor key",
    "romantic": "gentle piano melody, soft strings, warm intimate, slow tempo",
    "seductive": "sensual jazz, soft saxophone, intimate atmosphere, slow groove, breathy",
    "intimate": "gentle piano melody, soft strings, warm romantic atmosphere, slow tempo",
    "action": "intense percussion, fast electronic, dramatic hits, driving rhythm",
    "melancholy": "slow piano, minor key, ambient pads, emotional strings",
    "comedic": "playful pizzicato, bouncy rhythm, lighthearted woodwinds",
    "threatening": "deep bass drones, dark orchestral, heavy percussion, menacing",
    "powerful": "epic orchestral, brass fanfare, powerful drums, dramatic crescendo",
    "desperate": "dissonant strings, erratic piano, anxious tempo, building dread",
    "vulnerable": "solo piano, fragile melody, sparse arrangement, melancholy",
    "peaceful": "ambient pads, gentle harp, nature sounds, meditative, slow",
    "dominant": "heavy beat, dark electronic, bass-heavy, aggressive confidence",
    "provocative": "sultry bass, slow groove, jazz drums, smoky atmosphere",
    "ambient": "atmospheric pads, gentle textures, ethereal, floating",
}

VOICE_BASE = BASE_PATH.parent


def _extract_audio_segments(
    video_path: Path, output_dir: Path,
    min_duration: float = 0.5, max_duration: float = 30.0,
    silence_threshold: str = "-25dB", silence_duration: float = 0.3,
    keep_full_audio: bool = False,
) -> list[dict]:
    """Extract speech segments from a video using ffmpeg silence detection.

    Strategy: bandpass filter to voice frequencies (200-3000Hz), detect silence
    on filtered audio, then extract segments from original audio.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Extract full audio to WAV
    audio_path = output_dir / "full_audio.wav"
    subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
         "-ar", "22050", "-ac", "1", str(audio_path), "-y"],
        capture_output=True, timeout=120,
    )
    if not audio_path.exists():
        logger.warning("Failed to extract audio from video")
        return []

    # Step 2: Create voice-filtered version for silence detection
    filtered_path = output_dir / "voice_filtered.wav"
    subprocess.run(
        ["ffmpeg", "-i", str(audio_path),
         "-af", "highpass=f=200,lowpass=f=3000",
         str(filtered_path), "-y"],
        capture_output=True, timeout=60,
    )
    detect_input = filtered_path if filtered_path.exists() else audio_path

    # Step 3: Detect silence boundaries
    detect_result = subprocess.run(
        ["ffmpeg", "-i", str(detect_input),
         "-af", f"silencedetect=noise={silence_threshold}:d={silence_duration}",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )

    silence_starts = []
    silence_ends = []
    for line in detect_result.stderr.split("\n"):
        m_start = re.search(r"silence_start:\s*([\d.]+)", line)
        m_end = re.search(r"silence_end:\s*([\d.]+)", line)
        if m_start:
            silence_starts.append(float(m_start.group(1)))
        if m_end:
            silence_ends.append(float(m_end.group(1)))

    # Get total duration
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True, timeout=30,
    )
    total_duration = float(probe.stdout.strip()) if probe.stdout.strip() else 0

    logger.info(f"Audio: {total_duration:.1f}s, {len(silence_starts)} silence boundaries found")

    # Step 4: Build speech segments (gaps between silence)
    speech_segments = []
    if not silence_starts and total_duration > 0:
        speech_segments.append((0, total_duration))
    else:
        if silence_starts and silence_starts[0] > min_duration:
            speech_segments.append((0, silence_starts[0]))
        for i, end_time in enumerate(silence_ends):
            start = end_time
            next_silence = silence_starts[i + 1] if i < len(silence_starts) - 1 else total_duration
            if next_silence - start > min_duration:
                speech_segments.append((start, next_silence))

    # Step 5: Extract each segment from the ORIGINAL audio
    results = []
    for idx, (start, end) in enumerate(speech_segments):
        duration = end - start
        if duration < min_duration or duration > max_duration:
            continue
        segment_path = output_dir / f"segment_{idx+1:03d}.wav"
        subprocess.run(
            ["ffmpeg", "-i", str(audio_path), "-ss", str(start),
             "-t", str(duration), "-acodec", "pcm_s16le",
             str(segment_path), "-y"],
            capture_output=True, timeout=30,
        )
        if segment_path.exists():
            results.append({
                "path": str(segment_path),
                "filename": segment_path.name,
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(duration, 2),
            })

    # Clean up temp files (keep full_audio.wav if requested for diarization)
    if not keep_full_audio:
        audio_path.unlink(missing_ok=True)
    filtered_path.unlink(missing_ok=True)

    logger.info(f"Extracted {len(results)} speech segments from {len(speech_segments)} candidates")
    return results


@router.post("/ingest/voice")
async def ingest_voice(body: dict):
    """Extract voice/audio segments from a YouTube video."""
    url = body.get("url")
    project_name = body.get("project_name")
    min_duration = body.get("min_duration", 0.5)
    max_duration = body.get("max_duration", 30.0)

    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    if not project_name:
        raise HTTPException(status_code=400, detail="project_name is required")

    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="lora_voice_")

    try:
        tmp_video = Path(tmpdir) / "video.mp4"
        dl_result = subprocess.run(
            ["yt-dlp", "--js-runtimes", "node", "--remote-components", "ejs:github",
             "-f", "bestaudio[ext=m4a]/bestaudio/best",
             "-o", str(tmp_video), url],
            capture_output=True, text=True, timeout=300,
        )
        if dl_result.returncode != 0:
            raise HTTPException(status_code=400, detail=f"yt-dlp failed: {dl_result.stderr[:500]}")

        if not tmp_video.exists():
            downloads = list(Path(tmpdir).glob("video.*"))
            if downloads:
                tmp_video = downloads[0]
            else:
                raise HTTPException(status_code=500, detail="Download produced no output")

        safe_project = project_name.lower().replace(" ", "_")[:50]
        voice_dir = VOICE_BASE / "voice" / safe_project
        voice_dir.mkdir(parents=True, exist_ok=True)

        segments = _extract_audio_segments(
            tmp_video, voice_dir,
            min_duration=min_duration,
            max_duration=max_duration,
            keep_full_audio=body.get("keep_full_audio", True),
        )

        meta = {
            "source_url": url,
            "project": project_name,
            "extracted_at": datetime.now().isoformat(),
            "segments": segments,
        }
        with open(voice_dir / "extraction_meta.json", "w") as f:
            json.dump(meta, f, indent=2)

        return {
            "segments_extracted": len(segments),
            "project": project_name,
            "voice_dir": str(voice_dir),
            "segments": segments,
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@router.get("/voice/{project_name}")
async def list_voice_segments(project_name: str):
    """List extracted voice segments for a project."""
    safe_project = project_name.lower().replace(" ", "_")[:50]
    voice_dir = VOICE_BASE / "voice" / safe_project

    if not voice_dir.is_dir():
        return {"segments": [], "project": project_name}

    segments = []
    for wav in sorted(voice_dir.glob("segment_*.wav")):
        segments.append({
            "filename": wav.name,
            "size_kb": round(wav.stat().st_size / 1024, 1),
        })

    meta_path = voice_dir / "extraction_meta.json"
    meta = {}
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)

    return {
        "project": project_name,
        "total_segments": len(segments),
        "segments": meta.get("segments", segments),
        "source_url": meta.get("source_url"),
    }


@router.get("/voice/{project_name}/segment/{filename}")
async def get_voice_segment(project_name: str, filename: str):
    """Stream a voice segment audio file."""
    safe_project = project_name.lower().replace(" ", "_")[:50]
    segment_path = VOICE_BASE / "voice" / safe_project / filename

    if not segment_path.exists() or not segment_path.name.startswith("segment_"):
        raise HTTPException(status_code=404, detail="Segment not found")

    return FileResponse(segment_path, media_type="audio/wav", filename=filename)


@router.post("/voice/{project_name}/transcribe")
async def transcribe_voice_segments(project_name: str, body: dict = {}):
    """Transcribe voice segments using OpenAI Whisper."""
    safe_project = project_name.lower().replace(" ", "_")[:50]
    voice_dir = VOICE_BASE / "voice" / safe_project

    if not voice_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"No voice data for project '{project_name}'")

    model_size = body.get("model", "base")

    try:
        import whisper
    except ImportError:
        raise HTTPException(status_code=500, detail="Whisper not installed. Run: pip install openai-whisper")

    logger.info(f"Loading whisper model '{model_size}' for transcription...")
    model = whisper.load_model(model_size)

    segments = sorted(voice_dir.glob("segment_*.wav"))
    if not segments:
        return {"project": project_name, "transcriptions": [], "total": 0}

    char_map = await get_char_project_map()
    project_chars = {slug: info for slug, info in char_map.items()
                     if info.get("project_name") == project_name}
    char_names = {info.get("name", slug).lower(): slug for slug, info in project_chars.items()}

    results = []
    for seg_path in segments:
        try:
            result = model.transcribe(str(seg_path))
            text = result.get("text", "").strip()
            language = result.get("language", "unknown")

            matched_character = None
            text_lower = text.lower()
            for name, slug in char_names.items():
                if name in text_lower:
                    matched_character = slug
                    break

            results.append({
                "filename": seg_path.name,
                "text": text,
                "language": language,
                "matched_character": matched_character,
            })
        except Exception as e:
            logger.warning(f"Transcription failed for {seg_path.name}: {e}")
            results.append({
                "filename": seg_path.name, "text": "", "language": "unknown",
                "matched_character": None, "error": str(e),
            })

    meta_path = voice_dir / "extraction_meta.json"
    meta = {}
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
    meta["transcriptions"] = results
    meta["whisper_model"] = model_size
    meta["transcribed_at"] = datetime.now().isoformat()
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    transcribed = len([r for r in results if r.get("text")])
    matched = len([r for r in results if r.get("matched_character")])

    return {
        "project": project_name,
        "total": len(results),
        "transcribed": transcribed,
        "characters_matched": matched,
        "transcriptions": results,
    }


# --- Music Generation (ACE-Step) ---


def _ace_step_request(method: str, path: str, data: dict | None = None) -> dict:
    """Make a request to the ACE-Step API."""
    url = f"{ACE_STEP_URL}{path}"
    if data is not None:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        raise HTTPException(status_code=503, detail=f"ACE-Step unavailable: {e}")


def _build_music_caption(mood: str, genre: str, bpm: int | None = None, key: str | None = None) -> str:
    """Build a music generation caption from mood/genre parameters."""
    base = MOOD_PROMPTS.get(mood, MOOD_PROMPTS["ambient"])
    parts = [f"{genre} style", base]
    if bpm:
        parts.append(f"{bpm} bpm")
    if key:
        parts.append(f"key of {key}")
    return ", ".join(parts)


@router.post("/generate-music")
async def generate_music(req: MusicGenerateRequest):
    """Submit a music generation task to ACE-Step.

    Returns immediately with a task_id for polling.
    """
    # Build caption from mood/genre or use free-form override
    caption = req.caption or _build_music_caption(req.mood, req.genre, req.bpm, req.key)

    ace_payload = {
        "prompt": caption,
        "lyrics": "",
        "duration": req.duration,
        "format": "wav",
        "instrumental": req.instrumental,
        "infer_steps": 60,
        "guidance_scale": 15.0,
    }
    if req.seed is not None:
        ace_payload["seed"] = req.seed

    result = _ace_step_request("POST", "/generate", ace_payload)

    return {
        "task_id": result.get("task_id"),
        "status": result.get("status", "pending"),
        "caption": caption,
        "duration": req.duration,
        "scene_id": req.scene_id,
    }


@router.get("/generate-music/{task_id}/status")
async def music_generation_status(task_id: str):
    """Poll ACE-Step task status. When complete, copies audio to music cache."""
    result = _ace_step_request("GET", f"/status/{task_id}")

    if result.get("status") == "completed" and result.get("output_path"):
        # Copy to local music cache
        src = Path(result["output_path"])
        if src.exists():
            dest = MUSIC_CACHE / src.name
            if not dest.exists():
                shutil.copy2(src, dest)
            result["cached_path"] = str(dest)

    return result


@router.get("/music")
async def list_generated_music():
    """List all generated music tracks in the cache."""
    tracks = []
    for f in sorted(MUSIC_CACHE.glob("*.wav")):
        tracks.append({
            "filename": f.name,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "path": str(f),
        })
    return {"tracks": tracks, "total": len(tracks)}


@router.get("/music/{filename}")
async def serve_music(filename: str):
    """Stream a generated music file."""
    path = MUSIC_CACHE / filename
    if not path.exists():
        # Also check ACE-Step output dir
        path = Path(f"/opt/tower-ace-step/output/{filename}")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Track not found")
    return FileResponse(path, media_type="audio/wav", filename=filename)
