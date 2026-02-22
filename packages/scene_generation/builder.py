"""Scene builder helper functions — ffmpeg utilities, ComfyUI polling, generation orchestrator."""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

import httpx

from packages.core.config import BASE_PATH, COMFYUI_URL, COMFYUI_OUTPUT_DIR, COMFYUI_INPUT_DIR
from packages.core.db import connect_direct
from packages.core.audit import log_decision

from .framepack import build_framepack_workflow, _submit_comfyui_workflow
from .ltx_video import build_ltx_workflow, _submit_comfyui_workflow as _submit_ltx_workflow
from .wan_video import build_wan_t2v_workflow, _submit_comfyui_workflow as _submit_wan_workflow

logger = logging.getLogger(__name__)

# ACE-Step music generation server
ACE_STEP_URL = "http://localhost:8440"
MUSIC_CACHE = BASE_PATH / "output" / "music_cache"
MUSIC_CACHE.mkdir(parents=True, exist_ok=True)

# Scene output directory
SCENE_OUTPUT_DIR = BASE_PATH.parent / "output" / "scenes"
SCENE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Audio cache directory
AUDIO_CACHE_DIR = SCENE_OUTPUT_DIR / "audio_cache"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Track active scene generation tasks
_scene_generation_tasks: dict[str, asyncio.Task] = {}

# Progressive quality gate thresholds
# Each retry loosens the gate so we don't loop forever
_QUALITY_GATES = [
    {"threshold": 0.6, "label": "high"},     # Attempt 1: aim high
    {"threshold": 0.45, "label": "medium"},   # Attempt 2: acceptable
    {"threshold": 0.3, "label": "low"},       # Attempt 3: minimum viable
]
_MAX_RETRIES = len(_QUALITY_GATES)
_SHOT_QUALITY_THRESHOLD = _QUALITY_GATES[-1]["threshold"]  # absolute floor


async def _quality_gate_check(frame_path: str) -> float | None:
    """Quick quality check on a video frame using the vision model.

    Returns quality score (0-1) or None if check fails/unavailable.
    Uses a lightweight prompt to avoid long Ollama inference.
    """
    import urllib.request
    import base64
    from packages.core.config import OLLAMA_URL, VISION_MODEL

    try:
        with open(frame_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        payload = json.dumps({
            "model": VISION_MODEL,
            "prompt": (
                "Rate this anime frame 1-10 on visual quality (sharpness, "
                "no artifacts, coherent anatomy). Reply with ONLY a number."
            ),
            "images": [img_b64],
            "stream": False,
            "options": {"temperature": 0.1},
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        text = result.get("response", "").strip()

        # Extract numeric score
        for token in text.split():
            try:
                score = float(token.replace("/10", "").replace("/", ""))
                if 1 <= score <= 10:
                    return round(score / 10, 2)
            except ValueError:
                continue

        return None  # Couldn't parse score

    except Exception as e:
        logger.debug(f"Quality gate check failed for {frame_path}: {e}")
        return None  # Non-blocking: if check fails, pass the gate


async def extract_last_frame(video_path: str) -> str:
    """Extract the last frame from a video using ffmpeg."""
    output_path = video_path.rsplit(".", 1)[0] + "_lastframe.png"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-sseof", "-0.1", "-i", video_path,
        "-vframes", "1", "-q:v", "2", output_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg last-frame extraction failed: {stderr.decode()[-200:]}")
    return output_path


async def _probe_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return float(stdout.decode().strip()) if stdout.decode().strip() else 3.0


async def concat_videos(
    video_paths: list,
    output_path: str,
    transitions: list[dict] | None = None,
) -> str:
    """Concatenate videos with crossfade transitions between shots.

    transitions: list of {"type": "dissolve", "duration": 0.3} per join point.
                 Length should be len(video_paths) - 1. Falls back to dissolve 0.3s.
    """
    if len(video_paths) < 2:
        # Single video — just copy it
        if video_paths:
            shutil.copy2(video_paths[0], output_path)
        return output_path

    # Default transitions: dissolve 0.3s between every pair
    if not transitions:
        transitions = [{"type": "dissolve", "duration": 0.3}] * (len(video_paths) - 1)

    # Probe all video durations upfront
    durations = []
    for vp in video_paths:
        durations.append(await _probe_duration(vp))

    # Build ffmpeg xfade filter chain
    # Each xfade: [prev][next]xfade=transition=TYPE:duration=D:offset=OFFSET
    # offset = cumulative duration of previous outputs minus cumulative crossfade overlap
    inputs = []
    for vp in video_paths:
        inputs.extend(["-i", vp])

    filter_parts = []
    cumulative_duration = durations[0]

    for i in range(len(video_paths) - 1):
        t = transitions[i] if i < len(transitions) else {"type": "dissolve", "duration": 0.3}
        xfade_type = t.get("type", "dissolve")
        xfade_dur = min(t.get("duration", 0.3), durations[i] * 0.4, durations[i + 1] * 0.4)
        offset = cumulative_duration - xfade_dur

        if i == 0:
            src_label = "[0:v]"
        else:
            src_label = f"[v{i}]"

        dst_label = f"[{i + 1}:v]"

        if i == len(video_paths) - 2:
            out_label = "[vout]"
        else:
            out_label = f"[v{i + 1}]"

        filter_parts.append(
            f"{src_label}{dst_label}xfade=transition={xfade_type}:"
            f"duration={xfade_dur:.3f}:offset={offset:.3f}{out_label}"
        )

        # Next segment's cumulative = previous total + next duration - overlap
        cumulative_duration = offset + xfade_dur + durations[i + 1] - xfade_dur
        # Simplifies to: cumulative_duration = offset + durations[i + 1]
        cumulative_duration = offset + durations[i + 1]

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "19",
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    logger.info(f"Crossfade concat: {len(video_paths)} clips, filter={filter_complex[:200]}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        # Fallback to hard-cut concat if xfade fails
        logger.warning(f"xfade concat failed, falling back to hard-cut: {stderr.decode()[-200:]}")
        return await _concat_videos_hardcut(video_paths, output_path)

    return output_path


async def _concat_videos_hardcut(video_paths: list, output_path: str) -> str:
    """Fallback: concatenate videos with hard cuts (no transitions)."""
    list_path = output_path.rsplit(".", 1)[0] + "_concat.txt"
    with open(list_path, "w") as f:
        for vp in video_paths:
            f.write(f"file '{vp}'\n")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_path, "-c", "copy", output_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    os.unlink(list_path)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {stderr.decode()[-200:]}")
    return output_path


async def interpolate_video(
    input_path: str,
    output_path: str,
    target_fps: int = 60,
    method: str = "mci",
) -> str:
    """Frame-interpolate a video to a higher framerate using ffmpeg minterpolate.

    Args:
        input_path: Source video path.
        output_path: Destination video path.
        target_fps: Target frame rate (e.g. 60 for 30→60fps doubling).
        method: Interpolation method — "mci" (motion compensated, best quality),
                "dup" (duplicate frames), "blend" (frame blending).

    Returns:
        Path to interpolated video.
    """
    # minterpolate with ME method: epzs (fast) or esa (slower, better)
    filter_str = (
        f"minterpolate=fps={target_fps}:mi_mode={method}:"
        f"mc_mode=aobmc:me_mode=bidir:vsbmc=1"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "fast", "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    ]

    logger.info(f"Frame interpolation: {input_path} → {target_fps}fps ({method})")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.warning(f"Frame interpolation failed (non-fatal): {stderr.decode()[-200:]}")
        return input_path  # Return original if interpolation fails

    logger.info(f"Frame interpolation complete: {output_path}")
    return output_path


async def upscale_video(
    input_path: str,
    output_path: str,
    scale_factor: int = 2,
    model: str = "RealESRGAN_x4plus_anime_6B.pth",
) -> str:
    """Upscale a video frame-by-frame using ffmpeg + RealESRGAN via ComfyUI.

    Since ComfyUI-based upscaling would require a complex workflow per frame,
    this uses ffmpeg to extract frames, submits a batch upscale workflow,
    then reassembles. For simplicity, uses ffmpeg's built-in scale filter
    with lanczos interpolation as a reliable baseline. For production quality,
    consider installing ComfyUI-SeedVR2_VideoUpscaler for temporal-aware upscaling.

    Args:
        input_path: Source video path.
        output_path: Destination video path.
        scale_factor: Upscale multiplier (2 = double resolution).
        model: Upscale model name (unused in current ffmpeg implementation;
               reserved for future ComfyUI-based upscaling).

    Returns:
        Path to upscaled video.
    """
    # Get current resolution
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0", input_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        w, h = stdout.decode().strip().split(",")
        new_w = int(w) * scale_factor
        new_h = int(h) * scale_factor
    except (ValueError, AttributeError):
        logger.warning(f"Could not probe video dimensions, skipping upscale")
        return input_path

    # Cap at 1920x1080 to avoid unreasonable file sizes
    if new_w > 1920:
        ratio = 1920 / new_w
        new_w = 1920
        new_h = int(int(h) * scale_factor * ratio)
    if new_h > 1080:
        ratio = 1080 / new_h
        new_h = 1080
        new_w = int(new_w * ratio)

    # Ensure even dimensions
    new_w = new_w - (new_w % 2)
    new_h = new_h - (new_h % 2)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"scale={new_w}:{new_h}:flags=lanczos",
        "-c:v", "libx264", "-preset", "fast", "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    ]

    logger.info(f"Video upscale: {w}x{h} → {new_w}x{new_h} ({scale_factor}x)")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.warning(f"Video upscale failed (non-fatal): {stderr.decode()[-200:]}")
        return input_path

    logger.info(f"Video upscale complete: {output_path}")
    return output_path


async def download_preview(url: str, scene_id: str) -> str:
    """Download a 30-sec Apple Music preview to the audio cache. Returns local path."""
    cache_path = AUDIO_CACHE_DIR / f"preview_{scene_id}.m4a"
    if cache_path.exists():
        return str(cache_path)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            cache_path.write_bytes(resp.content)
        logger.info(f"Downloaded audio preview to {cache_path} ({len(resp.content)} bytes)")
        return str(cache_path)
    except Exception as e:
        logger.error(f"Failed to download audio preview: {e}")
        raise


async def overlay_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    fade_in: float = 1.0,
    fade_out: float = 2.0,
    start_offset: float = 0,
) -> str:
    """Overlay audio onto video using ffmpeg. Copies video stream, encodes audio as AAC.

    - fade_in / fade_out: seconds for audio fade
    - start_offset: skip N seconds into the audio before overlaying
    - Uses -shortest so output matches shorter of video/audio
    """
    # Build afade filter chain
    filters = []
    if start_offset > 0:
        filters.append(f"atrim=start={start_offset}")
        filters.append("asetpts=PTS-STARTPTS")
    if fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in}")
    # We need video duration for fade-out positioning — probe it
    probe = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await probe.communicate()
    video_duration = float(stdout.decode().strip()) if stdout.decode().strip() else 30.0
    if fade_out > 0:
        fade_out_start = max(0, video_duration - fade_out)
        filters.append(f"afade=t=out:st={fade_out_start}:d={fade_out}")

    filter_str = ",".join(filters) if filters else "anull"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex", f"[1:a]{filter_str}[a]",
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg audio overlay failed: {stderr.decode()[-300:]}")

    logger.info(f"Audio overlay complete: {output_path}")
    return output_path


async def mix_scene_audio(
    video_path: str,
    output_path: str,
    dialogue_path: str | None = None,
    music_path: str | None = None,
    music_fade_in: float = 1.0,
    music_fade_out: float = 2.0,
    music_start_offset: float = 0,
    music_volume: float = 0.3,
) -> str:
    """Mix dialogue and/or music into a video. Single-pass ffmpeg when both exist."""
    if not dialogue_path and not music_path:
        return video_path

    if dialogue_path and music_path:
        # Both: 3-input ffmpeg with sidechaincompress for audio ducking.
        # Music automatically dips when dialogue is present and returns after.
        probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", video_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await probe.communicate()
        video_duration = float(stdout.decode().strip()) if stdout.decode().strip() else 30.0

        music_filters = []
        if music_start_offset > 0:
            music_filters.append(f"atrim=start={music_start_offset}")
            music_filters.append("asetpts=PTS-STARTPTS")
        music_filters.append(f"volume={music_volume}")
        if music_fade_in > 0:
            music_filters.append(f"afade=t=in:st=0:d={music_fade_in}")
        if music_fade_out > 0:
            fade_out_start = max(0, video_duration - music_fade_out)
            music_filters.append(f"afade=t=out:st={fade_out_start}:d={music_fade_out}")

        music_chain = ",".join(music_filters)

        # sidechaincompress: dialogue (sidechain input) controls music compression.
        # level_in=1: no input gain on music
        # threshold=0.02: trigger ducking at low dialogue levels (catches quiet speech)
        # ratio=6: compress music 6:1 when dialogue present (strong ducking)
        # attack=200: 200ms ramp-down (smooth entry)
        # release=1000: 1s recovery after dialogue stops
        # makeup=1: no makeup gain after compression
        filter_complex = (
            f"[2:a]{music_chain}[music];"
            f"[music][1:a]sidechaincompress="
            f"level_in=1:threshold=0.02:ratio=6:attack=200:release=1000:makeup=1[ducked];"
            f"[1:a][ducked]amix=inputs=2:duration=shortest:normalize=0[a]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", dialogue_path,
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_path,
        ]
    elif dialogue_path:
        # Dialogue only
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path, "-i", dialogue_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_path,
        ]
    else:
        # Music only — delegate to existing overlay_audio
        return await overlay_audio(
            video_path=video_path, audio_path=music_path,
            output_path=output_path, fade_in=music_fade_in,
            fade_out=music_fade_out, start_offset=music_start_offset,
        )

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg audio mix failed: {stderr.decode()[-300:]}")
    logger.info(f"Audio mix complete: {output_path}")
    return output_path


async def build_scene_dialogue(conn, scene_id) -> str | None:
    """Build combined dialogue WAV for a scene from per-shot dialogue fields."""
    shots = await conn.fetch(
        "SELECT dialogue_text, dialogue_character_slug, shot_number "
        "FROM shots WHERE scene_id = $1 AND dialogue_text IS NOT NULL "
        "AND dialogue_text != '' ORDER BY shot_number",
        scene_id,
    )
    if not shots:
        return None

    dialogue_list = [
        {"character_slug": sh["dialogue_character_slug"] or "", "text": sh["dialogue_text"]}
        for sh in shots
    ]

    try:
        from packages.voice_pipeline.synthesis import synthesize_scene_dialogue
        result = await synthesize_scene_dialogue(
            scene_id=str(scene_id),
            dialogue_list=dialogue_list,
            pause_seconds=0.5,
        )
        combined_path = result.get("combined_path")
        if combined_path:
            await conn.execute(
                "UPDATE scenes SET dialogue_audio_path = $2 WHERE id = $1",
                scene_id, combined_path,
            )
        return combined_path
    except Exception as e:
        logger.warning(f"Scene dialogue synthesis failed (non-fatal): {e}")
        return None


async def _auto_generate_scene_music(scene_id: str, mood: str, duration: float = 30.0) -> str | None:
    """Auto-generate music for a scene using ACE-Step. Returns path or None."""
    import urllib.request

    # Mood→caption mapping (matches audio_composition router)
    mood_prompts = {
        "tense": "dark suspenseful orchestral, low strings, building tension, minor key",
        "romantic": "gentle piano melody, soft strings, warm intimate, slow tempo",
        "seductive": "sensual jazz, soft saxophone, intimate atmosphere, slow groove",
        "intimate": "gentle piano melody, soft strings, warm romantic atmosphere, slow tempo",
        "action": "intense percussion, fast electronic, dramatic hits, driving rhythm",
        "melancholy": "slow piano, minor key, ambient pads, emotional strings",
        "comedic": "playful pizzicato, bouncy rhythm, lighthearted woodwinds",
        "threatening": "deep bass drones, dark orchestral, heavy percussion, menacing",
        "powerful": "epic orchestral, brass fanfare, powerful drums, dramatic crescendo",
        "desperate": "dissonant strings, erratic piano, anxious tempo, building dread",
        "vulnerable": "solo piano, fragile melody, sparse arrangement, melancholy",
        "peaceful": "ambient pads, gentle harp, nature sounds, meditative, slow",
        "ambient": "atmospheric pads, gentle textures, ethereal, floating",
    }
    caption = mood_prompts.get(mood, mood_prompts["ambient"])

    payload = json.dumps({
        "prompt": caption,
        "lyrics": "",
        "duration": duration,
        "format": "wav",
        "instrumental": True,
        "infer_steps": 60,
        "guidance_scale": 15.0,
    }).encode()

    req = urllib.request.Request(
        f"{ACE_STEP_URL}/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        task_id = result.get("task_id")
        if not task_id:
            return None
    except Exception:
        return None  # ACE-Step unavailable — non-fatal

    # Poll for completion (music gen takes ~20-70s)
    import time as _time
    start = _time.time()
    while (_time.time() - start) < 120:
        try:
            poll_req = urllib.request.Request(f"{ACE_STEP_URL}/status/{task_id}")
            poll_resp = urllib.request.urlopen(poll_req, timeout=10)
            status = json.loads(poll_resp.read())
            if status.get("status") == "completed" and status.get("output_path"):
                src = Path(status["output_path"])
                if src.exists():
                    dest = MUSIC_CACHE / f"scene_{scene_id}_{src.name}"
                    shutil.copy2(str(src), str(dest))
                    logger.info(f"Auto-generated music for scene {scene_id}: {dest.name}")
                    return str(dest)
            elif status.get("status") == "failed":
                logger.warning(f"ACE-Step generation failed for scene {scene_id}: {status.get('error')}")
                return None
        except Exception:
            pass
        await asyncio.sleep(5)

    logger.warning(f"ACE-Step generation timed out for scene {scene_id}")
    return None


async def apply_scene_audio(conn, scene_id, scene_video_path: str) -> str:
    """Build dialogue + download music + mix all audio into the scene video.

    Non-fatal: logs warnings on failure, never blocks generation.
    Returns the (possibly updated) video path.
    """
    try:
        # Build dialogue audio from shot fields
        dialogue_path = await build_scene_dialogue(conn, scene_id)

        # Get music: prefer ACE-Step generated, then Apple Music preview
        music_path = None
        scene_row = await conn.fetchrow(
            "SELECT audio_preview_url, audio_fade_in, audio_fade_out, "
            "audio_start_offset, generated_music_path "
            "FROM scenes WHERE id = $1", scene_id,
        )
        if scene_row and scene_row.get("generated_music_path"):
            gmp = Path(scene_row["generated_music_path"])
            if gmp.exists():
                music_path = str(gmp)
                logger.info(f"Scene {scene_id}: using ACE-Step generated music: {gmp.name}")
        if not music_path and scene_row and scene_row["audio_preview_url"]:
            try:
                music_path = await download_preview(scene_row["audio_preview_url"], str(scene_id))
            except Exception as dl_err:
                logger.warning(f"Music download failed (non-fatal): {dl_err}")
        if not music_path and scene_row:
            # Auto-generate music from scene mood if ACE-Step is available
            mood = scene_row.get("mood") or scene_row.get("audio_mood") or "ambient"
            try:
                music_path = await _auto_generate_scene_music(scene_id, mood)
            except Exception as gen_err:
                logger.warning(f"Auto music generation failed (non-fatal): {gen_err}")

        if not dialogue_path and not music_path:
            return scene_video_path

        output = str(SCENE_OUTPUT_DIR / f"scene_{scene_id}_audio.mp4")
        await mix_scene_audio(
            video_path=scene_video_path,
            output_path=output,
            dialogue_path=dialogue_path,
            music_path=music_path,
            music_fade_in=scene_row["audio_fade_in"] or 1.0 if scene_row else 1.0,
            music_fade_out=scene_row["audio_fade_out"] or 2.0 if scene_row else 2.0,
            music_start_offset=scene_row["audio_start_offset"] or 0 if scene_row else 0,
        )
        os.replace(output, scene_video_path)

        if music_path:
            await conn.execute(
                "UPDATE scenes SET audio_preview_path = $2 WHERE id = $1",
                scene_id, music_path,
            )
        logger.info(f"Scene {scene_id}: audio applied (dialogue={'yes' if dialogue_path else 'no'}, music={'yes' if music_path else 'no'})")
    except Exception as e:
        logger.warning(f"apply_scene_audio failed (non-fatal): {e}")

    return scene_video_path


async def copy_to_comfyui_input(image_path: str) -> str:
    """Copy source image to ComfyUI input dir, return the filename."""
    src = Path(image_path)
    if not src.is_absolute():
        src = BASE_PATH / image_path
    dest = COMFYUI_INPUT_DIR / src.name
    if not dest.exists():
        shutil.copy2(str(src), str(dest))
    return src.name


async def poll_comfyui_completion(prompt_id: str, timeout_seconds: int = 1800) -> dict:
    """Poll ComfyUI /history until the prompt completes or times out."""
    import urllib.request
    import time as _time
    start = _time.time()
    while (_time.time() - start) < timeout_seconds:
        try:
            req = urllib.request.Request(f"{COMFYUI_URL}/history/{prompt_id}")
            resp = urllib.request.urlopen(req, timeout=10)
            history = json.loads(resp.read())
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                videos = []
                for node_output in outputs.values():
                    for key in ("videos", "gifs", "images"):
                        for item in node_output.get(key, []):
                            fn = item.get("filename")
                            if fn:
                                videos.append(fn)
                return {"status": "completed", "output_files": videos}
        except Exception:
            pass
        await asyncio.sleep(5)
    return {"status": "timeout", "output_files": []}


async def generate_scene(scene_id: str):
    """Background task: generate all shots sequentially with continuity chaining."""
    import time as _time
    conn = None
    try:
        conn = await connect_direct()

        shots = await conn.fetch(
            "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number",
            scene_id,
        )
        if not shots:
            await conn.execute(
                "UPDATE scenes SET generation_status = 'failed' WHERE id = $1", scene_id
            )
            return

        await conn.execute(
            "UPDATE scenes SET generation_status = 'generating', total_shots = $2 WHERE id = $1",
            scene_id, len(shots),
        )

        completed_videos = []
        completed_count = 0
        prev_last_frame = None

        for shot in shots:
            shot_id = shot["id"]
            shot_accepted = False
            best_video = None
            best_quality = 0.0
            best_last_frame = None

            await conn.execute(
                "UPDATE shots SET status = 'generating' WHERE id = $1", shot_id
            )
            await conn.execute(
                "UPDATE scenes SET current_generating_shot_id = $2 WHERE id = $1",
                scene_id, shot_id,
            )

            # Progressive gate: retry with loosening thresholds
            for attempt in range(_MAX_RETRIES):
                gate = _QUALITY_GATES[attempt]
                shot_start = _time.time()

                try:
                    # Determine first frame: previous shot's last frame or source image
                    if prev_last_frame and Path(prev_last_frame).exists():
                        first_frame_path = prev_last_frame
                        image_filename = await copy_to_comfyui_input(first_frame_path)
                    else:
                        source_path = shot["source_image_path"]
                        image_filename = await copy_to_comfyui_input(source_path)
                        first_frame_path = str(BASE_PATH / source_path) if not Path(source_path).is_absolute() else source_path

                    prompt_text = shot["motion_prompt"] or shot["generation_prompt"] or ""
                    shot_steps = shot["steps"] or 25
                    shot_seconds = float(shot["duration_seconds"] or 3)
                    shot_use_f1 = shot["use_f1"] if shot["use_f1"] is not None else False
                    shot_engine = shot.get("video_engine") or "framepack"

                    # Vary seed on retry to get different results
                    import random
                    shot_seed = shot["seed"] if attempt == 0 else random.randint(0, 2**63 - 1)

                    # Bump steps on later attempts for higher quality
                    retry_steps = shot_steps + (attempt * 5)

                    # Dispatch to the right video engine
                    if shot_engine == "wan":
                        fps = 16
                        num_frames = max(9, int(shot_seconds * fps) + 1)
                        workflow, prefix = build_wan_t2v_workflow(
                            prompt_text=prompt_text,
                            num_frames=num_frames,
                            fps=fps,
                            steps=retry_steps,
                            seed=shot_seed,
                            use_gguf=True,
                        )
                        comfyui_prompt_id = _submit_wan_workflow(workflow)
                    elif shot_engine == "ltx":
                        fps = 24
                        num_frames = max(9, int(shot_seconds * fps) + 1)
                        workflow, prefix = build_ltx_workflow(
                            prompt_text=prompt_text,
                            image_path=image_filename if image_filename else None,
                            num_frames=num_frames,
                            fps=fps,
                            steps=retry_steps,
                            seed=shot_seed,
                        )
                        comfyui_prompt_id = _submit_ltx_workflow(workflow)
                    else:
                        # framepack or framepack_f1
                        use_f1 = shot_engine == "framepack_f1" or shot_use_f1
                        workflow_data, sampler_node_id, prefix = build_framepack_workflow(
                            prompt_text=prompt_text,
                            image_path=image_filename,
                            total_seconds=shot_seconds,
                            steps=retry_steps,
                            use_f1=use_f1,
                            seed=shot_seed,
                            gpu_memory_preservation=6.0,
                        )
                        comfyui_prompt_id = _submit_comfyui_workflow(workflow_data["prompt"])

                    await conn.execute(
                        "UPDATE shots SET comfyui_prompt_id = $2, first_frame_path = $3 WHERE id = $1",
                        shot_id, comfyui_prompt_id, first_frame_path,
                    )

                    # Poll for completion — one at a time
                    result = await poll_comfyui_completion(comfyui_prompt_id)
                    gen_time = _time.time() - shot_start

                    if result["status"] != "completed" or not result["output_files"]:
                        logger.warning(
                            f"Shot {shot_id} attempt {attempt+1}: ComfyUI {result['status']}"
                        )
                        continue  # retry

                    video_filename = result["output_files"][0]
                    video_path = str(COMFYUI_OUTPUT_DIR / video_filename)
                    last_frame = await extract_last_frame(video_path)

                    # Quality gate check
                    shot_quality = await _quality_gate_check(last_frame)

                    # None means vision check unavailable — auto-pass
                    if shot_quality is None:
                        shot_quality = 0.7  # assume decent

                    logger.info(
                        f"Shot {shot_id} attempt {attempt+1}/{_MAX_RETRIES}: "
                        f"quality={shot_quality:.2f}, gate={gate['threshold']} ({gate['label']})"
                    )

                    # Track best attempt even if below threshold
                    if shot_quality > best_quality:
                        best_quality = shot_quality
                        best_video = video_path
                        best_last_frame = last_frame

                    if shot_quality >= gate["threshold"]:
                        # Passed this gate level
                        shot_accepted = True
                        await log_decision(
                            decision_type="shot_quality_gate",
                            input_context={
                                "shot_id": str(shot_id),
                                "scene_id": scene_id,
                                "quality_score": shot_quality,
                                "attempt": attempt + 1,
                                "gate": gate["label"],
                                "video": video_filename,
                            },
                            decision_made="accepted",
                            confidence_score=shot_quality,
                            reasoning=f"Quality {shot_quality:.0%} passed {gate['label']} gate ({gate['threshold']:.0%}) on attempt {attempt+1}",
                        )
                        break
                    else:
                        # Below threshold — log and retry with looser gate
                        await log_decision(
                            decision_type="shot_quality_gate",
                            input_context={
                                "shot_id": str(shot_id),
                                "scene_id": scene_id,
                                "quality_score": shot_quality,
                                "attempt": attempt + 1,
                                "gate": gate["label"],
                                "video": video_filename,
                            },
                            decision_made="retry" if attempt < _MAX_RETRIES - 1 else "accepted_best",
                            confidence_score=round(1.0 - shot_quality, 2),
                            reasoning=f"Quality {shot_quality:.0%} below {gate['label']} gate ({gate['threshold']:.0%}), attempt {attempt+1}/{_MAX_RETRIES}",
                        )

                except Exception as e:
                    logger.error(f"Shot {shot_id} attempt {attempt+1} failed: {e}")
                    if attempt == _MAX_RETRIES - 1:
                        await conn.execute(
                            "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                            shot_id, str(e)[:500],
                        )

            # Use best result even if no attempt fully passed
            if best_video:
                completed_count += 1
                completed_videos.append(best_video)
                prev_last_frame = best_last_frame
                shot_status = "completed" if shot_accepted else "accepted_best"
                await conn.execute("""
                    UPDATE shots SET status = $2, output_video_path = $3,
                           last_frame_path = $4, generation_time_seconds = $5,
                           quality_score = $6
                    WHERE id = $1
                """, shot_id, shot_status, best_video, best_last_frame,
                    gen_time, best_quality)
            else:
                await conn.execute(
                    "UPDATE shots SET status = 'failed', error_message = 'All attempts failed' WHERE id = $1",
                    shot_id,
                )

            await conn.execute(
                "UPDATE scenes SET completed_shots = $2 WHERE id = $1",
                scene_id, completed_count,
            )

        # Assemble final video with crossfade transitions
        if completed_videos:
            scene_video_path = str(SCENE_OUTPUT_DIR / f"scene_{scene_id}.mp4")
            try:
                # Read transition settings from completed shots
                transitions = []
                for shot in shots[1:]:  # transitions between pairs, so skip first
                    transitions.append({
                        "type": shot.get("transition_type", "dissolve") or "dissolve",
                        "duration": float(shot.get("transition_duration", 0.3) or 0.3),
                    })
                await concat_videos(completed_videos, scene_video_path, transitions=transitions)

                # Optional post-processing: frame interpolation then upscaling
                scene_meta = await conn.fetchrow(
                    "SELECT post_interpolate_fps, post_upscale_factor FROM scenes WHERE id = $1",
                    scene_id,
                )
                if scene_meta:
                    interp_fps = scene_meta["post_interpolate_fps"]
                    if interp_fps and interp_fps > 30:
                        interp_path = scene_video_path.rsplit(".", 1)[0] + f"_{interp_fps}fps.mp4"
                        result_path = await interpolate_video(
                            scene_video_path, interp_path, target_fps=interp_fps
                        )
                        if result_path != scene_video_path:
                            os.replace(result_path, scene_video_path)

                    upscale_factor = scene_meta["post_upscale_factor"]
                    if upscale_factor and upscale_factor > 1:
                        upscale_path = scene_video_path.rsplit(".", 1)[0] + f"_{upscale_factor}x.mp4"
                        result_path = await upscale_video(
                            scene_video_path, upscale_path, scale_factor=upscale_factor
                        )
                        if result_path != scene_video_path:
                            os.replace(result_path, scene_video_path)

                # Apply audio (dialogue + music) — non-fatal wrapper
                await apply_scene_audio(conn, scene_id, scene_video_path)

                # Get duration
                probe = await asyncio.create_subprocess_exec(
                    "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                    "-of", "csv=p=0", scene_video_path,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await probe.communicate()
                duration = float(stdout.decode().strip()) if stdout.decode().strip() else None

                final_status = "completed" if completed_count == len(shots) else "partial"
                await conn.execute("""
                    UPDATE scenes SET generation_status = $2, final_video_path = $3,
                           actual_duration_seconds = $4, current_generating_shot_id = NULL
                    WHERE id = $1
                """, scene_id, final_status, scene_video_path, duration)
            except Exception as e:
                logger.error(f"Scene assembly failed: {e}")
                await conn.execute(
                    "UPDATE scenes SET generation_status = 'partial', current_generating_shot_id = NULL WHERE id = $1",
                    scene_id,
                )
        else:
            await conn.execute(
                "UPDATE scenes SET generation_status = 'failed', current_generating_shot_id = NULL WHERE id = $1",
                scene_id,
            )

    except Exception as e:
        logger.error(f"Scene generation task failed: {e}")
        if conn:
            await conn.execute(
                "UPDATE scenes SET generation_status = 'failed', current_generating_shot_id = NULL WHERE id = $1",
                scene_id,
            )
    finally:
        if conn:
            await conn.close()
        _scene_generation_tasks.pop(scene_id, None)
