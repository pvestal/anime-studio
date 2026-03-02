"""Episode assembly — concatenate scene videos into full episodes.

Supports crossfade transitions between scenes using ffmpeg xfade filters.
Falls back to hard-cut concat if xfade fails (e.g. mismatched codecs).
"""

import asyncio
import logging
import os
import shutil
from pathlib import Path

from packages.core.config import BASE_PATH

logger = logging.getLogger(__name__)

EPISODE_OUTPUT_DIR = BASE_PATH.parent / "output" / "episodes"
EPISODE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Default episode-level transition (scene-to-scene)
_DEFAULT_EPISODE_TRANSITION = "fadeblack"
_DEFAULT_EPISODE_TRANSITION_DURATION = 0.5


async def _probe_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return float(stdout.decode().strip()) if stdout.decode().strip() else 5.0


async def _probe_has_audio(video_path: str) -> bool:
    """Check if a video file contains an audio stream via ffprobe."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-select_streams", "a",
        "-show_entries", "stream=index", "-of", "csv=p=0", video_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return bool(stdout.decode().strip())


async def _concat_hardcut(video_paths: list[str], output_path: str) -> str:
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
        raise RuntimeError(f"Episode hard-cut concat failed: {stderr.decode()[-300:]}")
    return output_path


async def assemble_episode(
    episode_id: str,
    scene_video_paths: list[str],
    transitions: list[str] | None = None,
) -> str:
    """Concatenate scene videos into an episode MP4 with crossfade transitions.

    Args:
        episode_id: UUID of the episode
        scene_video_paths: Ordered list of scene video file paths
        transitions: Per-scene transition type. Length = len(scene_video_paths).
                     Supported: "cut", "dissolve", "fade", "fadeblack",
                     "wipeleft", "slideup". Defaults to fadeblack between scenes.

    Returns:
        Path to assembled episode video
    """
    output_path = str(EPISODE_OUTPUT_DIR / f"episode_{episode_id}.mp4")

    if len(scene_video_paths) == 1:
        shutil.copy2(scene_video_paths[0], output_path)
        return output_path

    # Normalize transitions list (one per join point = len - 1)
    if not transitions:
        transitions = [_DEFAULT_EPISODE_TRANSITION] * (len(scene_video_paths) - 1)
    else:
        # transitions list aligns with scenes; we need join-point transitions
        # First scene's transition is irrelevant; use transitions[1:] for joins
        if len(transitions) >= len(scene_video_paths):
            transitions = transitions[1:len(scene_video_paths)]
        elif len(transitions) < len(scene_video_paths) - 1:
            transitions.extend(
                [_DEFAULT_EPISODE_TRANSITION] * (len(scene_video_paths) - 1 - len(transitions))
            )

    # Check if all transitions are "cut" — use fast concat demuxer
    if all(t == "cut" for t in transitions):
        logger.info(f"Episode {episode_id}: all cut transitions, using fast concat")
        return await _concat_hardcut(scene_video_paths, output_path)

    # Probe all video durations and audio presence upfront
    durations = []
    has_audio = []
    for vp in scene_video_paths:
        durations.append(await _probe_duration(vp))
        has_audio.append(await _probe_has_audio(vp))

    any_has_audio = any(has_audio)

    # Build ffmpeg xfade filter chain
    inputs = []
    for vp in scene_video_paths:
        inputs.extend(["-i", vp])

    n = len(scene_video_paths)
    video_filter_parts = []
    audio_filter_parts = []
    cumulative_duration = durations[0]

    # --- Video xfade chain (unchanged logic) ---
    for i in range(n - 1):
        xfade_type = transitions[i] if i < len(transitions) else _DEFAULT_EPISODE_TRANSITION
        if xfade_type == "cut":
            xfade_type = "fade"  # treat "cut" in mixed mode as quick fade
        xfade_dur = min(
            _DEFAULT_EPISODE_TRANSITION_DURATION,
            durations[i] * 0.4,
            durations[i + 1] * 0.4,
        )
        offset = cumulative_duration - xfade_dur

        src_label = "[0:v]" if i == 0 else f"[v{i}]"
        dst_label = f"[{i + 1}:v]"
        out_label = "[vout]" if i == n - 2 else f"[v{i + 1}]"

        video_filter_parts.append(
            f"{src_label}{dst_label}xfade=transition={xfade_type}:"
            f"duration={xfade_dur:.3f}:offset={offset:.3f}{out_label}"
        )

        cumulative_duration = offset + durations[i + 1]

    # --- Audio crossfade chain (new) ---
    if any_has_audio:
        # For each input: normalize existing audio or inject silence
        for i in range(n):
            if has_audio[i]:
                audio_filter_parts.append(
                    f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo[a{i}]"
                )
            else:
                audio_filter_parts.append(
                    f"anullsrc=r=48000:cl=stereo:d={durations[i]:.3f}[a{i}]"
                )

        # Build acrossfade chain matching xfade offsets
        cumulative_duration_a = durations[0]
        for i in range(n - 1):
            xfade_dur = min(
                _DEFAULT_EPISODE_TRANSITION_DURATION,
                durations[i] * 0.4,
                durations[i + 1] * 0.4,
            )

            a_src = f"[a{0}]" if i == 0 else f"[ac{i}]"
            a_dst = f"[a{i + 1}]"
            a_out = "[aout]" if i == n - 2 else f"[ac{i + 1}]"

            audio_filter_parts.append(
                f"{a_src}{a_dst}acrossfade=d={xfade_dur:.3f}:c1=tri:c2=tri{a_out}"
            )

            cumulative_duration_a = cumulative_duration_a - xfade_dur + durations[i + 1]

    filter_complex = ";".join(video_filter_parts + audio_filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
    ]
    if any_has_audio:
        cmd.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
    cmd.extend([
        "-c:v", "libx264", "-preset", "fast", "-crf", "19",
        "-pix_fmt", "yuv420p",
        output_path,
    ])

    logger.info(
        f"Episode {episode_id}: xfade assembly with {n} scenes "
        f"(audio={sum(has_audio)}/{n}), transitions={transitions[:5]}"
    )
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        if any_has_audio:
            # Fallback: try video-only xfade, then mux audio in second pass
            logger.warning(
                f"Episode xfade+audio failed, retrying video-only: {stderr.decode()[-200:]}"
            )
            video_only_path = output_path.rsplit(".", 1)[0] + "_vidonly.mp4"
            cmd_v = [
                "ffmpeg", "-y",
                *inputs,
                "-filter_complex", ";".join(video_filter_parts),
                "-map", "[vout]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "19",
                "-pix_fmt", "yuv420p",
                video_only_path,
            ]
            proc_v = await asyncio.create_subprocess_exec(
                *cmd_v,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr_v = await proc_v.communicate()
            if proc_v.returncode == 0:
                # Move video-only to final output
                os.replace(video_only_path, output_path)
                logger.warning(f"Episode {episode_id}: assembled video-only (audio chain failed)")
                return output_path

        logger.warning(
            f"Episode xfade failed, falling back to hard-cut: {stderr.decode()[-200:]}"
        )
        return await _concat_hardcut(scene_video_paths, output_path)

    logger.info(f"Episode {episode_id} assembled: {output_path} from {n} scenes (with audio)")
    return output_path


async def get_video_duration(video_path: str) -> float | None:
    """Get video duration in seconds using ffprobe."""
    probe = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await probe.communicate()
    try:
        return float(stdout.decode().strip())
    except (ValueError, AttributeError):
        return None


async def extract_thumbnail(video_path: str, output_path: str) -> str | None:
    """Extract first frame as thumbnail."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", video_path,
        "-vframes", "1", "-q:v", "2", output_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    if proc.returncode == 0 and Path(output_path).exists():
        return output_path
    return None
