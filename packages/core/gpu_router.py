"""Dual-GPU task routing — NVIDIA RTX 3060 (generation) + AMD RX 9070 XT (inference)."""

import json
import logging
import subprocess
import urllib.request

logger = logging.getLogger(__name__)

COMFYUI_URL = "http://127.0.0.1:8188"
OLLAMA_URL = "http://localhost:11434"
MIN_FREE_VRAM_MB = 4500  # Minimum free VRAM for generation tasks

# Task → GPU routing table
GPU_ROUTES = {
    # NVIDIA RTX 3060 — generation workloads (ComfyUI, training)
    "comfyui_generate": "nvidia",
    "framepack_video": "nvidia",
    "lora_training": "nvidia",
    "wd14_tagging": "nvidia",

    # AMD RX 9070 XT — inference workloads (Ollama)
    "vision_review": "amd",
    "echo_embeddings": "amd",
    "echo_chat": "amd",
    "image_classification": "amd",
}


def get_nvidia_info() -> dict | None:
    """Query nvidia-smi for GPU memory info."""
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
        logger.error(f"Failed to query NVIDIA GPU: {e}")
        return None


def get_amd_info() -> dict | None:
    """Query rocm-smi for AMD GPU memory info."""
    try:
        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            # Try alternative: amdgpu_top or /sys/class/drm
            return _get_amd_info_sysfs()
        data = json.loads(result.stdout)
        # rocm-smi JSON format varies; parse common shapes
        for card_key, card_data in data.items():
            if "VRAM Total Memory" in card_data:
                total_bytes = int(card_data["VRAM Total Memory (B)"])
                used_bytes = int(card_data["VRAM Total Used Memory (B)"])
                return {
                    "total_mb": total_bytes // (1024 * 1024),
                    "used_mb": used_bytes // (1024 * 1024),
                    "free_mb": (total_bytes - used_bytes) // (1024 * 1024),
                    "gpu_name": "AMD RX 9070 XT",
                }
        return _get_amd_info_sysfs()
    except Exception as e:
        logger.warning(f"rocm-smi failed ({e}), trying sysfs")
        return _get_amd_info_sysfs()


def _get_amd_info_sysfs() -> dict | None:
    """Fallback: read AMD VRAM from /sys/class/drm/card*/device/mem_info_vram_*."""
    try:
        from pathlib import Path
        drm_dir = Path("/sys/class/drm")
        for card_dir in sorted(drm_dir.glob("card[0-9]")):
            device_dir = card_dir / "device"
            vram_total_file = device_dir / "mem_info_vram_total"
            vram_used_file = device_dir / "mem_info_vram_used"
            if vram_total_file.exists() and vram_used_file.exists():
                total = int(vram_total_file.read_text().strip())
                used = int(vram_used_file.read_text().strip())
                # Check if this is the AMD card (not NVIDIA)
                vendor_file = device_dir / "vendor"
                if vendor_file.exists():
                    vendor = vendor_file.read_text().strip()
                    if vendor != "0x1002":  # AMD vendor ID
                        continue
                return {
                    "total_mb": total // (1024 * 1024),
                    "used_mb": used // (1024 * 1024),
                    "free_mb": (total - used) // (1024 * 1024),
                    "gpu_name": "AMD RX 9070 XT",
                }
    except Exception as e:
        logger.error(f"Failed to query AMD GPU via sysfs: {e}")
    return None


def get_ollama_models() -> list[dict]:
    """Query Ollama for currently loaded models and VRAM usage."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/ps")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        models = []
        for m in data.get("models", []):
            models.append({
                "name": m.get("name", "unknown"),
                "size_mb": m.get("size", 0) // (1024 * 1024),
                "vram_mb": m.get("size_vram", 0) // (1024 * 1024),
            })
        return models
    except Exception as e:
        logger.warning(f"Failed to query Ollama models: {e}")
        return []


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
        return False


def get_comfyui_queue() -> dict:
    """Get ComfyUI queue status."""
    try:
        req = urllib.request.Request(f"{COMFYUI_URL}/queue")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        return {
            "queue_running": len(data.get("queue_running", [])),
            "queue_pending": len(data.get("queue_pending", [])),
        }
    except Exception:
        return {"queue_running": 0, "queue_pending": 0, "error": "ComfyUI not reachable"}


def free_comfyui_vram() -> bool:
    """Ask ComfyUI to free cached models from VRAM."""
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
        logger.warning(f"Failed to free ComfyUI VRAM: {e}")
        return False


def check_gpu_available(task: str, min_free_mb: int = MIN_FREE_VRAM_MB) -> tuple[bool, str]:
    """Route-aware GPU availability check."""
    gpu_target = GPU_ROUTES.get(task, "nvidia")

    if gpu_target == "nvidia":
        info = get_nvidia_info()
        if info is None:
            return False, "Cannot query NVIDIA GPU — nvidia-smi failed"
        if info["free_mb"] >= min_free_mb:
            return True, f"NVIDIA ready: {info['free_mb']}MB free on {info['gpu_name']}"
        return False, (
            f"Insufficient NVIDIA VRAM: {info['free_mb']}MB free, need {min_free_mb}MB. "
            f"{info['gpu_name']} ({info['total_mb']}MB total, {info['used_mb']}MB used)"
        )

    elif gpu_target == "amd":
        info = get_amd_info()
        if info is None:
            # AMD GPU info not available but Ollama may still work
            return True, "AMD GPU info unavailable, proceeding (Ollama manages its own VRAM)"
        if info["free_mb"] >= min_free_mb:
            return True, f"AMD ready: {info['free_mb']}MB free on {info['gpu_name']}"
        return False, (
            f"Insufficient AMD VRAM: {info['free_mb']}MB free, need {min_free_mb}MB. "
            f"{info['gpu_name']} ({info['total_mb']}MB total, {info['used_mb']}MB used)"
        )

    return False, f"Unknown GPU target for task '{task}'"


def ensure_gpu_ready(task: str, min_free_mb: int = MIN_FREE_VRAM_MB) -> tuple[bool, str]:
    """Full pre-task GPU check: free ComfyUI if needed (NVIDIA tasks), verify VRAM."""
    gpu_target = GPU_ROUTES.get(task, "nvidia")

    if gpu_target == "nvidia":
        if check_comfyui_busy():
            return False, "ComfyUI has an active generation job — wait for it to finish"

        available, msg = check_gpu_available(task, min_free_mb)
        if available:
            return True, msg

        # Try freeing ComfyUI models
        logger.info("Not enough NVIDIA VRAM, attempting to free ComfyUI models...")
        free_comfyui_vram()

        import time
        time.sleep(2)
        available, msg = check_gpu_available(task, min_free_mb)
        if available:
            return True, f"NVIDIA ready after freeing ComfyUI: {msg}"
        return False, msg

    elif gpu_target == "amd":
        # AMD tasks use Ollama which manages its own VRAM
        return True, "AMD GPU ready (Ollama manages VRAM allocation)"

    return False, f"Unknown GPU target for task '{task}'"


def get_host_stats() -> dict:
    """CPU usage + system RAM."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "cpu_count": psutil.cpu_count(),
            "ram_total_mb": round(mem.total / 1048576),
            "ram_used_mb": round(mem.used / 1048576),
            "ram_free_mb": round(mem.available / 1048576),
            "ram_percent": mem.percent,
        }
    except ImportError:
        return {"cpu_percent": 0, "cpu_count": 0, "ram_total_mb": 0, "ram_used_mb": 0, "ram_free_mb": 0, "ram_percent": 0}


def get_system_status() -> dict:
    """Full GPU dashboard — both GPUs + Ollama + ComfyUI + host CPU/RAM."""
    return {
        "nvidia": get_nvidia_info(),
        "amd": get_amd_info(),
        "ollama": {
            "loaded_models": get_ollama_models(),
            "total_vram_mb": sum(m["vram_mb"] for m in get_ollama_models()),
        },
        "comfyui": get_comfyui_queue(),
        "host": get_host_stats(),
    }
