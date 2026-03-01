"""Speaker diarization — pyannote-based speaker identification and embedding extraction.

Runs pyannote-audio on extracted project audio to identify distinct speakers,
extract speaker embeddings, and map segments to speaker clusters.
"""

import json
import logging
import subprocess
from pathlib import Path

import numpy as np

from packages.core.config import BASE_PATH

logger = logging.getLogger(__name__)

VOICE_BASE = BASE_PATH.parent


def _get_hf_token() -> str | None:
    """Load HuggingFace token from Vault or env."""
    import os
    token = os.getenv("HF_TOKEN")
    if token:
        return token

    vault_addr = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
    vault_token = os.getenv("VAULT_TOKEN")
    if not vault_token:
        token_file = os.path.expanduser("~/.vault-token")
        if os.path.exists(token_file):
            with open(token_file) as f:
                vault_token = f.read().strip()

    if vault_token:
        try:
            import hvac
            client = hvac.Client(url=vault_addr, token=vault_token)
            if client.is_authenticated():
                response = client.secrets.kv.v2.read_secret_version(
                    path="anime/huggingface", mount_point="secret",
                    raise_on_deleted_version=True,
                )
                return response["data"]["data"].get("token")
        except Exception as e:
            logger.warning(f"Vault HuggingFace token unavailable: {e}")

    return None


def _ensure_full_audio(project_slug: str, voice_dir: Path) -> Path | None:
    """Ensure full_audio.wav exists. If missing, try to re-extract from source URL."""
    full_audio = voice_dir / "full_audio.wav"
    if full_audio.exists():
        return full_audio

    # Try to re-extract from source URL in extraction_meta.json
    meta_path = voice_dir / "extraction_meta.json"
    if not meta_path.exists():
        return None

    with open(meta_path) as f:
        meta = json.load(f)

    source_url = meta.get("source_url")
    if not source_url:
        return None

    logger.info(f"Re-extracting full audio from {source_url} for diarization")
    import tempfile
    import shutil

    tmpdir = tempfile.mkdtemp(prefix="diarize_")
    try:
        tmp_video = Path(tmpdir) / "video.mp4"
        dl_result = subprocess.run(
            ["yt-dlp", "--js-runtimes", "node", "--remote-components", "ejs:github",
             "-f", "bestaudio[ext=m4a]/bestaudio/best",
             "-o", str(tmp_video), source_url],
            capture_output=True, text=True, timeout=300,
        )
        if dl_result.returncode != 0:
            logger.error(f"yt-dlp failed: {dl_result.stderr[:500]}")
            return None

        # Find downloaded file (extension may vary)
        downloads = list(Path(tmpdir).glob("video.*"))
        if not downloads:
            return None
        tmp_video = downloads[0]

        subprocess.run(
            ["ffmpeg", "-i", str(tmp_video), "-vn", "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", str(full_audio), "-y"],
            capture_output=True, timeout=120,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return full_audio if full_audio.exists() else None


async def diarize_project(project_slug: str) -> dict:
    """Run pyannote speaker diarization on project audio.

    Returns dict with speaker clusters, segment assignments, and metadata.
    """
    safe_project = project_slug.lower().replace(" ", "_")[:50]
    voice_dir = VOICE_BASE / "voice" / safe_project

    if not voice_dir.is_dir():
        return {"error": f"No voice directory for project '{project_slug}'"}

    full_audio = _ensure_full_audio(project_slug, voice_dir)
    if not full_audio:
        return {"error": "No full_audio.wav available — run voice extraction first"}

    hf_token = _get_hf_token()
    if not hf_token:
        return {"error": "HuggingFace token required for pyannote. Set HF_TOKEN env var or store in Vault at secret/anime/huggingface"}

    try:
        from pyannote.audio import Pipeline
        import torch
    except ImportError:
        return {"error": "pyannote-audio not installed. Run: pip install pyannote-audio"}

    logger.info(f"Running speaker diarization on {full_audio}")

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )

    # Use GPU if available (prefer AMD ROCm, fallback NVIDIA CUDA)
    import torch
    if hasattr(torch, 'hip') and torch.hip.is_available():
        pipeline.to(torch.device("cuda"))  # PyTorch ROCm uses "cuda" device string
    elif torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))

    raw_output = pipeline(str(full_audio))

    # pyannote 4.x returns DiarizeOutput; extract the Annotation
    if hasattr(raw_output, 'speaker_diarization'):
        diarization = raw_output.speaker_diarization
    else:
        diarization = raw_output  # pyannote 3.x returns Annotation directly

    # Build speaker segments
    speakers: dict[str, list[dict]] = {}
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        if speaker not in speakers:
            speakers[speaker] = []
        speakers[speaker].append({
            "start": round(turn.start, 2),
            "end": round(turn.end, 2),
            "duration": round(turn.end - turn.start, 2),
        })

    # Match diarized segments to existing extracted segments
    existing_segments = sorted(voice_dir.glob("segment_*.wav"))
    meta_path = voice_dir / "extraction_meta.json"
    extraction_meta = {}
    if meta_path.exists():
        with open(meta_path) as f:
            extraction_meta = json.load(f)

    segment_assignments = []
    for seg_info in extraction_meta.get("segments", []):
        seg_start = seg_info.get("start", 0)
        seg_end = seg_info.get("end", 0)
        seg_mid = (seg_start + seg_end) / 2

        # Find which speaker owns the midpoint of this segment
        best_speaker = None
        best_overlap = 0
        for speaker, turns in speakers.items():
            for turn in turns:
                overlap_start = max(seg_start, turn["start"])
                overlap_end = min(seg_end, turn["end"])
                overlap = max(0, overlap_end - overlap_start)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = speaker

        segment_assignments.append({
            **seg_info,
            "speaker": best_speaker,
            "speaker_confidence": round(best_overlap / max(seg_end - seg_start, 0.01), 2),
        })

    # Build speaker summaries
    speaker_summaries = []
    for speaker, turns in speakers.items():
        total_duration = sum(t["duration"] for t in turns)
        speaker_summaries.append({
            "speaker_label": speaker,
            "segment_count": len(turns),
            "total_duration_seconds": round(total_duration, 2),
            "turns": turns,
        })

    # Write diarization metadata
    diarization_meta = {
        "project": project_slug,
        "audio_file": str(full_audio),
        "speakers": speaker_summaries,
        "segment_assignments": segment_assignments,
        "total_speakers": len(speakers),
    }
    with open(voice_dir / "diarization_meta.json", "w") as f:
        json.dump(diarization_meta, f, indent=2)

    logger.info(f"Diarization complete: {len(speakers)} speakers, {len(segment_assignments)} segments assigned")

    return diarization_meta


def extract_speaker_embedding(audio_path: str, start: float, end: float) -> list[float] | None:
    """Extract a 192-dim speaker embedding for an audio segment using pyannote."""
    try:
        from pyannote.audio import Inference
        import torch

        hf_token = _get_hf_token()
        if not hf_token:
            return None

        inference = Inference(
            "pyannote/embedding",
            token=hf_token,
            window="whole",
        )

        # Extract segment to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        subprocess.run(
            ["ffmpeg", "-i", audio_path, "-ss", str(start),
             "-t", str(end - start), "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", tmp_path, "-y"],
            capture_output=True, timeout=30,
        )

        embedding = inference(tmp_path)
        Path(tmp_path).unlink(missing_ok=True)

        return embedding.flatten().tolist()

    except Exception as e:
        logger.warning(f"Embedding extraction failed: {e}")
        return None
