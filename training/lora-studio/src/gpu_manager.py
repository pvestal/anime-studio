#!/usr/bin/env python3
"""GPU coordination utility for LoRA training.

Checks VRAM availability and frees ComfyUI cached models before training.
"""

import json
import logging
import subprocess
import urllib.request

logger = logging.getLogger(__name__)

COMFYUI_URL = "http://127.0.0.1:8188"
# Minimum free VRAM in MB to allow training (need ~5GB for SD1.5 LoRA)
MIN_FREE_VRAM_MB = 4500


def get_gpu_info() -> dict:
    """Query nvidia-smi for GPU memory info.

    Returns dict with total_mb, used_mb, free_mb, gpu_name, or None on failure.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free,name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            logger.error(f"nvidia-smi failed: {result.stderr}")
            return None
        line = result.stdout.strip().split("\n")[0]
        total, used, free, name = [x.strip() for x in line.split(",")]
        return {
            "total_mb": int(total),
            "used_mb": int(used),
            "free_mb": int(free),
            "gpu_name": name,
        }
    except Exception as e:
        logger.error(f"Failed to query GPU: {e}")
        return None


def check_gpu_available(min_free_mb: int = MIN_FREE_VRAM_MB) -> tuple[bool, str]:
    """Check if GPU has enough free VRAM for training.

    Returns (available, message).
    """
    info = get_gpu_info()
    if info is None:
        return False, "Cannot query GPU — nvidia-smi failed"

    if info["free_mb"] >= min_free_mb:
        return True, f"GPU ready: {info['free_mb']}MB free on {info['gpu_name']}"

    return False, (
        f"Insufficient VRAM: {info['free_mb']}MB free, need {min_free_mb}MB. "
        f"GPU: {info['gpu_name']} ({info['total_mb']}MB total, {info['used_mb']}MB used)"
    )


def check_comfyui_busy() -> bool:
    """Check if ComfyUI has an active generation job."""
    try:
        req = urllib.request.Request(f"{COMFYUI_URL}/queue")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        running = data.get("queue_running", [])
        pending = data.get("queue_pending", [])
        return len(running) > 0 or len(pending) > 0
    except Exception:
        # ComfyUI not reachable — not busy (or not running)
        return False


def free_comfyui_vram() -> bool:
    """Ask ComfyUI to free cached models from VRAM.

    Calls the /free endpoint to unload models. Returns True on success.
    """
    try:
        payload = json.dumps({"unload_models": True, "free_memory": True}).encode()
        req = urllib.request.Request(
            f"{COMFYUI_URL}/free",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        logger.info("ComfyUI models freed from VRAM")
        return True
    except Exception as e:
        logger.warning(f"Failed to free ComfyUI VRAM (may not be running): {e}")
        return False


def ensure_gpu_ready(min_free_mb: int = MIN_FREE_VRAM_MB) -> tuple[bool, str]:
    """Full pre-training GPU check: free ComfyUI if needed, verify VRAM.

    Returns (ready, message).
    """
    if check_comfyui_busy():
        return False, "ComfyUI has an active generation job — wait for it to finish"

    available, msg = check_gpu_available(min_free_mb)
    if available:
        return True, msg

    # Try freeing ComfyUI models
    logger.info("Not enough VRAM, attempting to free ComfyUI models...")
    free_comfyui_vram()

    # Re-check after freeing
    import time
    time.sleep(2)  # Give GPU a moment to release memory
    available, msg = check_gpu_available(min_free_mb)
    if available:
        return True, f"GPU ready after freeing ComfyUI: {msg}"

    return False, msg
