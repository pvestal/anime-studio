"""Video clip extraction around character timestamps — ffmpeg stream copy.

Used after CLIP classification to extract short video clips of specific characters
from source video. Stream-copies (no re-encode) for instant extraction.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_clip(
    video_path: Path,
    timestamp: float,
    output_path: Path,
    duration: float = 2.0,
    padding_before: float = 0.5,
) -> Path | None:
    """Extract a short clip around a timestamp using ffmpeg stream copy.

    Args:
        video_path: Source video file
        timestamp: Center timestamp in seconds
        output_path: Where to save the clip
        duration: Total clip duration in seconds
        padding_before: Seconds before the timestamp to include

    Returns output path on success, None on failure.
    """
    start = max(0, timestamp - padding_before)
    end = start + duration

    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}",
            "-to", f"{end:.3f}",
            "-i", str(video_path),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            str(output_path),
        ],
        capture_output=True, text=True, timeout=30,
    )

    if result.returncode != 0:
        logger.warning(f"Clip extraction failed at {timestamp:.1f}s: {result.stderr[:200]}")
        return None

    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path

    return None


def extract_character_clips(
    video_path: Path,
    classifications: list[dict],
    target_slug: str,
    output_dir: Path,
    max_clips: int = 50,
    clip_duration: float = 2.0,
    min_gap: float = 1.5,
) -> list[dict]:
    """Extract video clips for frames classified as target character.

    Filters, deduplicates temporally, and extracts clips.

    Args:
        video_path: Source video
        classifications: Output from classify_frames_batch / verify_assignments
        target_slug: Character to extract clips for
        output_dir: Where to save clips
        max_clips: Maximum number of clips to extract
        clip_duration: Duration of each clip in seconds
        min_gap: Minimum gap between clips to avoid overlap

    Returns list of {path, timestamp, similarity, character} dicts.
    """
    # Filter to target character with timestamps
    target_frames = [
        c for c in classifications
        if c.get("matched_slug") == target_slug and "timestamp" in c
    ]

    if not target_frames:
        logger.info(f"No {target_slug} frames with timestamps for clip extraction")
        return []

    # Sort by timestamp
    target_frames.sort(key=lambda c: c["timestamp"])

    # Temporal dedup — skip clips within min_gap of each other
    deduped = []
    last_ts = -999
    for frame in target_frames:
        ts = frame["timestamp"]
        if ts - last_ts >= min_gap:
            deduped.append(frame)
            last_ts = ts

    # Limit
    deduped = deduped[:max_clips]

    output_dir.mkdir(parents=True, exist_ok=True)
    clips = []

    for i, frame in enumerate(deduped):
        ts = frame["timestamp"]
        clip_name = f"{target_slug}_{ts:.1f}s_{i:03d}.mp4"
        clip_path = output_dir / clip_name

        result = extract_clip(
            video_path, ts, clip_path,
            duration=clip_duration,
        )

        if result:
            clips.append({
                "path": str(result),
                "timestamp": ts,
                "similarity": frame.get("similarity", 0),
                "character": target_slug,
                "frame_index": frame.get("frame_index"),
            })

    logger.info(f"Extracted {len(clips)}/{len(deduped)} clips for {target_slug}")
    return clips
