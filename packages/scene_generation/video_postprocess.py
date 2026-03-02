"""Video post-processing pipeline: RIFE interpolation + ESRGAN upscale + deflicker.

GPU pipeline (preferred):
  1. RIFE 4.7 frame interpolation (16fps → 32fps) — interpolate BEFORE upscale
  2. RealESRGAN x4plus anime upscale → downscale to 2x target
  3. Pixel deflicker (temporal smoothing)
  4. Color grading (ffmpeg LUT, if .cube file exists for project)
  5. Encode final video

ffmpeg fallback (when GPU is busy or nodes unavailable):
  1. minterpolate (16fps → 30fps)
  2. lanczos 2x upscale
"""

import json
import logging
import subprocess
import shutil
import time
import urllib.request
from pathlib import Path

from packages.core.config import COMFYUI_URL, COMFYUI_OUTPUT_DIR, COMFYUI_INPUT_DIR

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ComfyUI GPU workflow: RIFE interpolation → ESRGAN upscale → video out
# ---------------------------------------------------------------------------

def build_postprocess_workflow(
    video_path: str,
    upscale_model: str = "RealESRGAN_x4plus_anime_6B.pth",
    rife_model: str = "rife47.pth",
    interpolation_multiplier: int = 2,
    target_width: int = 960,
    target_height: int = 1440,
    output_fps: int = 32,
    output_prefix: str = "pp",
) -> tuple[dict, str]:
    """Build a ComfyUI workflow: load video → RIFE interpolate → ESRGAN upscale → save.

    Order: interpolate first (fewer frames to process), then upscale.
    """
    workflow = {}

    # 1: Load video frames
    workflow["1"] = {
        "class_type": "VHS_LoadVideo",
        "inputs": {
            "video": video_path,
            "force_rate": 0,
            "custom_width": 0,
            "custom_height": 0,
            "frame_load_cap": 0,
            "skip_first_frames": 0,
            "select_every_nth": 1,
        },
    }

    # 2: RIFE frame interpolation (2x frames)
    workflow["2"] = {
        "class_type": "RIFE VFI",
        "inputs": {
            "ckpt_name": rife_model,
            "frames": ["1", 0],
            "multiplier": interpolation_multiplier,
            "clear_cache_after_n_frames": 10,
            "fast_mode": True,
            "ensemble": False,
            "scale_factor": 1.0,
        },
    }

    # 3: Load upscale model
    workflow["3"] = {
        "class_type": "UpscaleModelLoader",
        "inputs": {"model_name": upscale_model},
    }

    # 4: ESRGAN upscale (4x native, then we downscale)
    workflow["4"] = {
        "class_type": "ImageUpscaleWithModel",
        "inputs": {
            "upscale_model": ["3", 0],
            "image": ["2", 0],
        },
    }

    # 5: Downscale to 2x target (4x ESRGAN → 2x final)
    workflow["5"] = {
        "class_type": "ImageScale",
        "inputs": {
            "image": ["4", 0],
            "upscale_method": "lanczos",
            "width": target_width,
            "height": target_height,
            "crop": "disabled",
        },
    }

    # 6: Save as video
    workflow["6"] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "frame_rate": output_fps,
            "loop_count": 0,
            "filename_prefix": output_prefix,
            "format": "video/h264-mp4",
            "pingpong": False,
            "save_output": True,
            "images": ["5", 0],
        },
    }

    return workflow, output_prefix


def _submit_workflow(workflow: dict) -> str:
    """Submit workflow to ComfyUI, return prompt_id."""
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read()).get("prompt_id", "")


def _poll_completion(prompt_id: str, timeout: int = 600) -> dict | None:
    """Poll ComfyUI history for completion. Return output info or None."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            url = f"{COMFYUI_URL}/history/{prompt_id}"
            resp = urllib.request.urlopen(urllib.request.Request(url), timeout=10)
            history = json.loads(resp.read())
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                status = history[prompt_id].get("status", {})
                if status.get("status_str") == "error":
                    logger.error(f"ComfyUI post-processing failed: {status}")
                    return None
                # Look for video output from VHS_VideoCombine
                for nid, out in outputs.items():
                    gifs = out.get("gifs", [])
                    if gifs:
                        return {"filename": gifs[0].get("filename", ""), "subfolder": gifs[0].get("subfolder", "")}
                    images = out.get("images", [])
                    if images:
                        return {"filename": images[0].get("filename", ""), "subfolder": images[0].get("subfolder", "")}
                return None
        except Exception:
            pass
        time.sleep(5)
    logger.error(f"Post-processing timed out after {timeout}s")
    return None


def postprocess_gpu(
    input_video: str,
    output_prefix: str = "pp",
    timeout: int = 600,
) -> str | None:
    """Run GPU post-processing via ComfyUI: RIFE + ESRGAN.

    Returns path to processed video or None on failure.
    """
    # Copy video to ComfyUI input if needed
    input_p = Path(input_video)
    comfyui_input = Path(COMFYUI_INPUT_DIR)
    if not str(input_p).startswith(str(comfyui_input)):
        dest = comfyui_input / input_p.name
        shutil.copy2(input_p, dest)
        video_for_workflow = input_p.name
    else:
        video_for_workflow = input_p.name

    # Probe source video dimensions to determine target upscale size
    # (avoids hardcoded 960x1440 portrait default for landscape videos)
    pp_target_w, pp_target_h = 960, 1440  # default portrait (480x720 * 2)
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "stream=width,height",
             "-of", "csv=p=0:s=x", str(input_p)],
            capture_output=True, text=True, timeout=10,
        )
        parts = probe.stdout.strip().split("x")
        if len(parts) >= 2:
            src_w, src_h = int(parts[0]), int(parts[1].split("\n")[0])
            pp_target_w, pp_target_h = src_w * 2, src_h * 2
    except Exception:
        pass

    workflow, prefix = build_postprocess_workflow(
        video_path=video_for_workflow,
        target_width=pp_target_w,
        target_height=pp_target_h,
        output_prefix=output_prefix,
    )

    prompt_id = _submit_workflow(workflow)
    if not prompt_id:
        logger.error("Failed to submit post-processing workflow")
        return None

    logger.info(f"GPU post-processing submitted: {prompt_id}")
    result = _poll_completion(prompt_id, timeout)

    if result and result.get("filename"):
        subfolder = result.get("subfolder", "")
        if subfolder:
            path = Path(COMFYUI_OUTPUT_DIR) / subfolder / result["filename"]
        else:
            path = Path(COMFYUI_OUTPUT_DIR) / result["filename"]
        if path.exists():
            logger.info(f"GPU post-processing complete: {path}")
            return str(path)

    logger.warning("GPU post-processing produced no output")
    return None


# ---------------------------------------------------------------------------
# ffmpeg fallback pipeline
# ---------------------------------------------------------------------------

def upscale_video_ffmpeg(input_path: str, output_path: str, scale_factor: int = 2) -> bool:
    """Upscale video using ffmpeg lanczos (fallback when GPU busy)."""
    input_p = Path(input_path)
    if not input_p.exists():
        return False

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "stream=width,height",
         "-of", "csv=p=0:s=x", str(input_p)],
        capture_output=True, text=True,
    )
    parts = probe.stdout.strip().split("x")
    if len(parts) < 2:
        return False

    w, h = int(parts[0]), int(parts[1].split("\n")[0])
    new_w, new_h = w * scale_factor, h * scale_factor

    cmd = [
        "ffmpeg", "-y", "-i", str(input_p),
        "-vf", f"scale={new_w}:{new_h}:flags=lanczos",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy", str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        logger.error(f"ffmpeg upscale failed: {result.stderr[:300]}")
        return False
    logger.info(f"ffmpeg upscaled {w}x{h} → {new_w}x{new_h}")
    return True


def interpolate_video_ffmpeg(input_path: str, output_path: str, target_fps: int = 30) -> bool:
    """Interpolate frames using ffmpeg minterpolate (fallback)."""
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", f"minterpolate=fps={target_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        logger.error(f"ffmpeg interpolation failed: {result.stderr[:300]}")
        return False
    logger.info(f"ffmpeg interpolated to {target_fps}fps")
    return True


def apply_color_grade(input_path: str, output_path: str, lut_path: str | None = None) -> bool:
    """Apply color grading via ffmpeg. Uses .cube LUT if provided, else default anime enhance."""
    filters = []
    if lut_path and Path(lut_path).exists():
        filters.append(f"lut3d={lut_path}")
    else:
        # Default anime enhancement: slight contrast boost + saturation
        filters.append("curves=preset=increase_contrast")
        filters.append("eq=saturation=1.15:contrast=1.05")

    # Subtle vignette — skip for dark/night scenes (caller can pass lut_path=None)
    # Vignette darkens edges which hurts already-dark bedroom/night scenes
    # filters.append("vignette=PI/5")  # disabled: too aggressive for dark scenes

    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", ",".join(filters),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy", str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.error(f"Color grading failed: {result.stderr[:300]}")
        return False
    logger.info(f"Color graded: {output_path}")
    return True


# ---------------------------------------------------------------------------
# Main entry point — tries GPU, falls back to ffmpeg
# ---------------------------------------------------------------------------

async def postprocess_wan_video(
    input_video: str,
    output_dir: str | None = None,
    upscale: bool = True,
    interpolate: bool = True,
    color_grade: bool = True,
    scale_factor: int = 2,
    target_fps: int = 30,
    lut_path: str | None = None,
    use_gpu: bool = True,
) -> str | None:
    """Full post-processing pipeline for video output.

    Tries GPU pipeline (RIFE + ESRGAN via ComfyUI) first.
    Falls back to ffmpeg if GPU pipeline fails or is unavailable.

    Pipeline order: interpolate → upscale → color grade
    (interpolate at lower res = faster + better quality)
    """
    input_p = Path(input_video)
    if not input_p.exists():
        logger.error(f"Input video not found: {input_video}")
        return None

    if output_dir is None:
        output_dir = str(input_p.parent)

    stem = input_p.stem
    current = str(input_p)

    # Try GPU pipeline first (RIFE + ESRGAN in one ComfyUI workflow)
    if use_gpu and upscale and interpolate:
        try:
            ts = int(time.time())
            gpu_result = postprocess_gpu(
                current,
                output_prefix=f"pp_{stem}_{ts}",
                timeout=600,
            )
            if gpu_result:
                gpu_intermediate = gpu_result
                current = gpu_result
                # Apply color grading on top (always ffmpeg, fast)
                if color_grade:
                    graded = str(Path(output_dir) / f"{stem}_final.mp4")
                    if apply_color_grade(current, graded, lut_path):
                        current = graded
                # Clean up intermediate pp_ file
                try:
                    Path(gpu_intermediate).unlink(missing_ok=True)
                except OSError:
                    pass
                logger.info(f"GPU post-processing complete: {current}")
                return current
            else:
                logger.warning("GPU pipeline failed, falling back to ffmpeg")
        except Exception as e:
            logger.warning(f"GPU pipeline error: {e}, falling back to ffmpeg")

    # ffmpeg fallback
    intermediates = []
    if interpolate:
        interpolated = str(Path(output_dir) / f"{stem}_interp.mp4")
        if interpolate_video_ffmpeg(current, interpolated, target_fps):
            intermediates.append(current if current != str(input_p) else None)
            current = interpolated

    if upscale:
        upscaled = str(Path(output_dir) / f"{stem}_upscaled.mp4")
        if upscale_video_ffmpeg(current, upscaled, scale_factor):
            intermediates.append(current)
            current = upscaled

    if color_grade:
        graded = str(Path(output_dir) / f"{stem}_final.mp4")
        if apply_color_grade(current, graded, lut_path):
            intermediates.append(current)
            current = graded

    # Clean up intermediate files (_interp, _upscaled)
    for f in intermediates:
        if f:
            try:
                Path(f).unlink(missing_ok=True)
            except OSError:
                pass

    logger.info(f"Post-processing complete (ffmpeg): {current}")
    return current
