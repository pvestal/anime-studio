"""Wan 2.1/2.2 Text-to-Video workflow builder.

Wan 2.1 1.3B is ideal for environment/establishing shots where no source image
exists. Uses native ComfyUI Wan nodes + GGUF loader for low-VRAM operation.

VRAM: ~8GB at FP16, ~4-6GB with GGUF Q4/Q8 quantization.
Speed: Faster than FramePack for short clips.

Model files needed in ComfyUI/models/:
  - unet/: Wan2.1-T2V-1.3B-Q8_0.gguf (GGUF, recommended)
           OR wan2.1_t2v_1.3B_fp16.safetensors (standard)
  - text_encoders/: umt5_xxl_fp8_e4m3fn_scaled.safetensors (UMT5-XXL, NOT T5-XXL)
  - vae/: wan_2.1_vae.safetensors
"""

import json
import logging
import time

from fastapi import APIRouter, HTTPException

from packages.core.config import COMFYUI_URL, COMFYUI_OUTPUT_DIR

logger = logging.getLogger(__name__)

router = APIRouter()

# Wan model filenames (GGUF preferred for 12GB VRAM)
WAN_MODELS = {
    # The T2V 1.3B model — standard safetensors
    "unet": "wan2.1_t2v_1.3B_fp16.safetensors",
    # Text encoder — UMT5-XXL (different from LTX's T5-XXL!)
    "text_encoder": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    # VAE
    "vae": "wan_2.1_vae.safetensors",
}

# GGUF model (recommended for 12GB VRAM)
WAN_GGUF_MODELS = {
    "unet": "Wan2.1-T2V-1.3B-Q8_0.gguf",
}


def _submit_comfyui_workflow(workflow: dict) -> str:
    """Submit a workflow to ComfyUI and return the prompt_id."""
    import urllib.request
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())
    return result.get("prompt_id", "")


def build_wan_t2v_workflow(
    prompt_text: str,
    width: int = 480,
    height: int = 720,
    num_frames: int = 81,
    fps: int = 16,
    steps: int = 30,
    cfg: float = 6.0,
    seed: int | None = None,
    negative_text: str = "low quality, blurry, distorted, watermark, text, ugly",
    use_gguf: bool = False,
) -> tuple[dict, str]:
    """Build a Wan 2.1 T2V ComfyUI workflow for environment/establishing shots.

    Returns (workflow_dict, output_prefix).

    Args:
        prompt_text: Scene description for video generation.
        width: Video width (multiple of 16). 480 is safe for 12GB.
        height: Video height (multiple of 16).
        num_frames: Number of frames (81 = ~5s at 16fps).
        fps: Output frame rate (Wan native is 16fps).
        steps: Sampling steps.
        cfg: CFG guidance scale.
        seed: Random seed, auto-generated if None.
        negative_text: Negative prompt.
        use_gguf: Use GGUF quantized model (lower VRAM, slightly lower quality).
    """
    import random as _random
    if seed is None:
        seed = _random.randint(0, 2**63 - 1)

    workflow = {}
    nid = 1

    # Node 1: Load model (GGUF or standard)
    if use_gguf:
        model_node = str(nid)
        workflow[model_node] = {
            "class_type": "UnetLoaderGGUF",
            "inputs": {
                "unet_name": WAN_GGUF_MODELS["unet"],
            },
        }
    else:
        model_node = str(nid)
        workflow[model_node] = {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": WAN_MODELS["unet"],
                "weight_dtype": "default",
            },
        }
    nid += 1

    # Node 2: ModelSamplingSD3 — required for Wan to set sigma scaling
    sampling_node = str(nid)
    workflow[sampling_node] = {
        "class_type": "ModelSamplingSD3",
        "inputs": {
            "model": [model_node, 0],
            "shift": 8,
        },
    }
    nid += 1

    # Node 3: Text encoder (UMT5-XXL — NOT the T5-XXL from LTX)
    clip_node = str(nid)
    workflow[clip_node] = {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": WAN_MODELS["text_encoder"],
            "type": "wan",
        },
    }
    nid += 1

    # Node 4: VAE
    vae_node = str(nid)
    workflow[vae_node] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": WAN_MODELS["vae"]},
    }
    nid += 1

    # Node 5: Positive CLIP encode
    pos_node = str(nid)
    workflow[pos_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": prompt_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # Node 6: Negative CLIP encode
    neg_node = str(nid)
    workflow[neg_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # Node 7: Empty video latent (EmptyHunyuanLatentVideo, NOT EmptyLatentImage)
    latent_node = str(nid)
    workflow[latent_node] = {
        "class_type": "EmptyHunyuanLatentVideo",
        "inputs": {
            "width": width,
            "height": height,
            "length": num_frames,
            "batch_size": 1,
        },
    }
    nid += 1

    # Node 8: KSampler (uni_pc/simple as per official Wan workflow)
    sampler_node = str(nid)
    workflow[sampler_node] = {
        "class_type": "KSampler",
        "inputs": {
            "model": [sampling_node, 0],
            "positive": [pos_node, 0],
            "negative": [neg_node, 0],
            "latent_image": [latent_node, 0],
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": "uni_pc",
            "scheduler": "simple",
            "denoise": 1.0,
        },
    }
    nid += 1

    # Node 9: VAE Decode
    decode_node = str(nid)
    workflow[decode_node] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": [sampler_node, 0],
            "vae": [vae_node, 0],
        },
    }
    nid += 1

    # Node 10: VHS_VideoCombine (output MP4)
    ts = int(time.time())
    prefix = f"wan_{ts}"
    output_node = str(nid)
    workflow[output_node] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": [decode_node, 0],
            "frame_rate": fps,
            "loop_count": 0,
            "filename_prefix": prefix,
            "format": "video/h264-mp4",
            "pix_fmt": "yuv420p",
            "crf": 19,
            "save_metadata": True,
            "trim_to_audio": False,
            "pingpong": False,
            "save_output": True,
        },
    }

    return workflow, prefix


def check_wan_models_available() -> dict:
    """Check which Wan model files are present in ComfyUI directories."""
    from pathlib import Path
    base = Path("/opt/ComfyUI/models")

    # Each model type → list of directories to check
    search_dirs = {
        "unet": ["diffusion_models", "unet"],
        "text_encoder": ["text_encoders", "clip"],
        "vae": ["vae"],
    }

    status = {}
    for key, filename in WAN_MODELS.items():
        dirs = search_dirs.get(key, ["diffusion_models", "unet", "text_encoders", "clip", "vae"])
        found = any((base / d / filename).exists() for d in dirs)
        status[key] = {"filename": filename, "available": found}

    # GGUF unet
    gguf_found = any(
        (base / d / WAN_GGUF_MODELS["unet"]).exists()
        for d in ["diffusion_models", "unet"]
    )
    status["unet_gguf"] = {
        "filename": WAN_GGUF_MODELS["unet"],
        "available": gguf_found,
    }
    return status


@router.get("/generate/wan/models")
async def check_wan_models():
    """Check availability of Wan model files."""
    status = check_wan_models_available()
    all_ready = all(v["available"] for k, v in status.items() if k != "unet_gguf")
    gguf_ready = (
        status["unet_gguf"]["available"]
        and status["text_encoder"]["available"]
        and status["vae"]["available"]
    )
    return {
        "models": status,
        "standard_ready": all_ready,
        "gguf_ready": gguf_ready,
        "download_instructions": {
            "unet_gguf": "wget -O /opt/ComfyUI/models/unet/Wan2.1-T2V-1.3B-Q8_0.gguf https://huggingface.co/samuelchristlie/Wan2.1-T2V-1.3B-GGUF/resolve/main/Wan2.1-T2V-1.3B-Q8_0.gguf",
            "vae": "wget -O /opt/ComfyUI/models/vae/wan_2.1_vae.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors",
            "text_encoder": "wget -O /opt/ComfyUI/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        },
    }


@router.post("/generate/wan")
async def generate_wan_video(
    prompt: str,
    width: int = 480,
    height: int = 720,
    num_frames: int = 81,
    fps: int = 16,
    steps: int = 30,
    cfg: float = 6.0,
    seed: int | None = None,
    use_gguf: bool = True,
):
    """Generate a Wan T2V environment video (no source image needed)."""
    status = check_wan_models_available()
    if use_gguf and not status["unet_gguf"]["available"]:
        raise HTTPException(status_code=503, detail="Wan GGUF model not downloaded. GET /generate/wan/models for instructions.")
    if not use_gguf and not status["unet"]["available"]:
        raise HTTPException(status_code=503, detail="Wan model not downloaded. GET /generate/wan/models for instructions.")
    if not status["text_encoder"]["available"]:
        raise HTTPException(status_code=503, detail="T5-XXL text encoder not found.")

    workflow, prefix = build_wan_t2v_workflow(
        prompt_text=prompt,
        width=width,
        height=height,
        num_frames=num_frames,
        fps=fps,
        steps=steps,
        cfg=cfg,
        seed=seed,
        use_gguf=use_gguf,
    )

    try:
        prompt_id = _submit_comfyui_workflow(workflow)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ComfyUI submission failed: {e}")

    seconds = num_frames / fps

    return {
        "prompt_id": prompt_id,
        "engine": "wan-t2v-1.3b" + ("-gguf" if use_gguf else ""),
        "mode": "t2v",
        "seconds": round(seconds, 1),
        "resolution": f"{width}x{height}",
        "prefix": prefix,
    }
