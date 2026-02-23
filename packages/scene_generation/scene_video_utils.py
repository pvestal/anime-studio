"""Scene video utility functions — concat, interpolate, upscale, extract frames, probe duration."""

import asyncio
import logging
import os
import shutil

logger = logging.getLogger(__name__)


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
        target_fps: Target frame rate (e.g. 60 for 30->60fps doubling).
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

    logger.info(f"Frame interpolation: {input_path} -> {target_fps}fps ({method})")
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

    logger.info(f"Video upscale: {w}x{h} -> {new_w}x{new_h} ({scale_factor}x)")
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
