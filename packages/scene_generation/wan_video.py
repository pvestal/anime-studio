"""Wan 2.1/2.2 Text-to-Video workflow builder.

Wan 2.1 1.3B is ideal for environment/establishing shots where no source image
exists. Uses native ComfyUI Wan nodes + GGUF loader for low-VRAM operation.

Wan 2.2 5B adds LoRA support (e.g. furry LoRAs) and I2V mode via
Wan22FunControlToVideo. Uses 48-channel VAE (different from 2.1's 16-channel).

VRAM: ~8GB at FP16, ~4-6GB with GGUF Q4/Q8 quantization.
Speed: Faster than FramePack for short clips.

Model files needed in ComfyUI/models/:
  Wan 2.1:
    - unet/: Wan2.1-T2V-1.3B-Q8_0.gguf (GGUF, recommended)
             OR wan2.1_t2v_1.3B_fp16.safetensors (standard)
    - text_encoders/: umt5_xxl_fp8_e4m3fn_scaled.safetensors (UMT5-XXL, NOT T5-XXL)
    - vae/: wan_2.1_vae.safetensors
  Wan 2.2:
    - unet/: Wan2.2-TI2V-5B-Q4_K_S.gguf (GGUF Q4, ~3.1GB)
    - text_encoders/: umt5_xxl_fp8_e4m3fn_scaled.safetensors (shared with 2.1)
    - vae/: wan2.2_vae.safetensors (48-channel, NOT compatible with 2.1)
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

# Wan 2.2 models — 5B with 48-channel VAE (LoRA-compatible)
WAN22_MODELS = {
    "unet_gguf": "Wan2.2-TI2V-5B-Q4_K_S.gguf",
    "text_encoder": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",  # shared with 2.1
    "vae": "wan2.2_vae.safetensors",  # 48-channel, NOT compatible with 2.1
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
    output_prefix: str | None = None,
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
    prefix = output_prefix or f"wan_{ts}"
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


def build_wan22_workflow(
    prompt_text: str,
    width: int = 480,
    height: int = 720,
    num_frames: int = 81,
    fps: int = 16,
    steps: int = 30,
    cfg: float = 6.0,
    seed: int | None = None,
    negative_text: str = "low quality, blurry, distorted, watermark, text, ugly",
    output_prefix: str | None = None,
    lora_name: str | None = None,
    lora_strength: float = 0.8,
    ref_image: str | None = None,
) -> tuple[dict, str]:
    """Build a Wan 2.2 5B ComfyUI workflow with LoRA and optional I2V support.

    Uses Wan22FunControlToVideo for correct 48-channel latent generation.
    The node outputs (positive, negative, latent) so KSampler connects to its
    outputs rather than directly to CLIPTextEncode.

    Args:
        prompt_text: Scene description for video generation.
        width: Video width (multiple of 16). 480 default for 12GB VRAM.
        height: Video height (multiple of 16).
        num_frames: Number of frames (81 = ~5s at 16fps).
        fps: Output frame rate.
        steps: Sampling steps.
        cfg: CFG guidance scale.
        seed: Random seed, auto-generated if None.
        negative_text: Negative prompt.
        output_prefix: Filename prefix for output.
        lora_name: LoRA filename (in ComfyUI/models/loras/). None to skip.
        lora_strength: LoRA strength (0.0-1.0).
        ref_image: Reference image filename (in ComfyUI/input/) for I2V mode.
    """
    import random as _random
    if seed is None:
        seed = _random.randint(0, 2**63 - 1)

    workflow = {}
    nid = 1

    # --- Model loading chain ---

    # Node: UnetLoaderGGUF (Wan 2.2 5B Q4_K_S)
    unet_node = str(nid)
    workflow[unet_node] = {
        "class_type": "UnetLoaderGGUF",
        "inputs": {
            "unet_name": WAN22_MODELS["unet_gguf"],
        },
    }
    nid += 1

    # Current model output — may be overridden by LoRA
    model_out_node = unet_node
    model_out_slot = 0

    # Node: LoraLoaderModelOnly (optional — LoRA injection)
    if lora_name:
        lora_node = str(nid)
        workflow[lora_node] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [model_out_node, model_out_slot],
                "lora_name": lora_name,
                "strength_model": lora_strength,
            },
        }
        model_out_node = lora_node
        model_out_slot = 0
        nid += 1

    # Node: ModelSamplingSD3 — sigma scaling for Wan
    sampling_node = str(nid)
    workflow[sampling_node] = {
        "class_type": "ModelSamplingSD3",
        "inputs": {
            "model": [model_out_node, model_out_slot],
            "shift": 8,
        },
    }
    nid += 1

    # --- Text encoding ---

    # Node: CLIPLoader (UMT5-XXL, shared with Wan 2.1)
    clip_node = str(nid)
    workflow[clip_node] = {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": WAN22_MODELS["text_encoder"],
            "type": "wan",
        },
    }
    nid += 1

    # Node: Positive CLIP encode
    pos_node = str(nid)
    workflow[pos_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": prompt_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # Node: Negative CLIP encode
    neg_node = str(nid)
    workflow[neg_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # --- VAE ---

    vae_node = str(nid)
    workflow[vae_node] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": WAN22_MODELS["vae"]},
    }
    nid += 1

    # --- Latent generation via Wan22FunControlToVideo ---
    # This node reads vae.latent_channels dynamically (48 for Wan 2.2)
    # and outputs (positive, negative, latent) — wrapping the conditioning.

    fun_node = str(nid)
    fun_inputs = {
        "positive": [pos_node, 0],
        "negative": [neg_node, 0],
        "vae": [vae_node, 0],
        "width": width,
        "height": height,
        "length": num_frames,
        "batch_size": 1,
    }
    nid += 1

    # Optional: load reference image for I2V mode
    if ref_image:
        load_img_node = str(nid)
        workflow[load_img_node] = {
            "class_type": "LoadImage",
            "inputs": {"image": ref_image},
        }
        fun_inputs["ref_image"] = [load_img_node, 0]
        nid += 1

    workflow[fun_node] = {
        "class_type": "Wan22FunControlToVideo",
        "inputs": fun_inputs,
    }

    # --- Sampling ---
    # KSampler uses outputs from Wan22FunControlToVideo:
    #   slot 0 = positive conditioning, slot 1 = negative conditioning, slot 2 = latent

    sampler_node = str(nid)
    workflow[sampler_node] = {
        "class_type": "KSampler",
        "inputs": {
            "model": [sampling_node, 0],
            "positive": [fun_node, 0],
            "negative": [fun_node, 1],
            "latent_image": [fun_node, 2],
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": "uni_pc",
            "scheduler": "simple",
            "denoise": 1.0,
        },
    }
    nid += 1

    # --- Decode + output ---

    decode_node = str(nid)
    workflow[decode_node] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": [sampler_node, 0],
            "vae": [vae_node, 0],
        },
    }
    nid += 1

    ts = int(time.time())
    prefix = output_prefix or f"wan22_{ts}"
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

    # GGUF unet (Wan 2.1)
    gguf_found = any(
        (base / d / WAN_GGUF_MODELS["unet"]).exists()
        for d in ["diffusion_models", "unet"]
    )
    status["unet_gguf"] = {
        "filename": WAN_GGUF_MODELS["unet"],
        "available": gguf_found,
    }

    # Wan 2.2 models
    wan22_unet_found = any(
        (base / d / WAN22_MODELS["unet_gguf"]).exists()
        for d in ["diffusion_models", "unet"]
    )
    status["wan22_unet_gguf"] = {
        "filename": WAN22_MODELS["unet_gguf"],
        "available": wan22_unet_found,
    }
    wan22_vae_found = (base / "vae" / WAN22_MODELS["vae"]).exists()
    status["wan22_vae"] = {
        "filename": WAN22_MODELS["vae"],
        "available": wan22_vae_found,
    }
    return status


def check_wan22_ready() -> tuple[bool, str]:
    """Check if all Wan 2.2 models are available. Returns (ready, message)."""
    status = check_wan_models_available()
    missing = []
    if not status["wan22_unet_gguf"]["available"]:
        missing.append(f"unet: {WAN22_MODELS['unet_gguf']}")
    if not status["text_encoder"]["available"]:
        missing.append(f"text_encoder: {WAN22_MODELS['text_encoder']}")
    if not status["wan22_vae"]["available"]:
        missing.append(f"vae: {WAN22_MODELS['vae']}")
    if missing:
        return False, f"Missing Wan 2.2 models: {', '.join(missing)}"
    return True, "All Wan 2.2 models available"


@router.get("/generate/wan/models")
async def check_wan_models():
    """Check availability of Wan model files (2.1 and 2.2)."""
    status = check_wan_models_available()
    all_ready = all(v["available"] for k, v in status.items() if k not in ("unet_gguf", "wan22_unet_gguf", "wan22_vae"))
    gguf_ready = (
        status["unet_gguf"]["available"]
        and status["text_encoder"]["available"]
        and status["vae"]["available"]
    )
    wan22_ready, wan22_msg = check_wan22_ready()
    return {
        "models": status,
        "standard_ready": all_ready,
        "gguf_ready": gguf_ready,
        "wan22_ready": wan22_ready,
        "wan22_message": wan22_msg,
        "download_instructions": {
            "unet_gguf": "wget -O /opt/ComfyUI/models/unet/Wan2.1-T2V-1.3B-Q8_0.gguf https://huggingface.co/samuelchristlie/Wan2.1-T2V-1.3B-GGUF/resolve/main/Wan2.1-T2V-1.3B-Q8_0.gguf",
            "vae": "wget -O /opt/ComfyUI/models/vae/wan_2.1_vae.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors",
            "text_encoder": "wget -O /opt/ComfyUI/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
            "wan22_unet_gguf": "wget -O /opt/ComfyUI/models/unet/Wan2.2-TI2V-5B-Q4_K_S.gguf https://huggingface.co/QuantStack/Wan2.2-TI2V-5B-GGUF/resolve/main/Wan2.2-TI2V-5B-Q4_K_S.gguf",
            "wan22_vae": "wget -O /opt/ComfyUI/models/vae/wan2.2_vae.safetensors https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors",
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


@router.post("/generate/wan22")
async def generate_wan22_video(
    prompt: str,
    width: int = 480,
    height: int = 720,
    num_frames: int = 81,
    fps: int = 16,
    steps: int = 30,
    cfg: float = 6.0,
    seed: int | None = None,
    lora_name: str | None = None,
    lora_strength: float = 0.8,
    ref_image: str | None = None,
):
    """Generate a Wan 2.2 5B video with optional LoRA and I2V mode."""
    ready, msg = check_wan22_ready()
    if not ready:
        raise HTTPException(status_code=503, detail=msg + ". GET /generate/wan/models for instructions.")

    if lora_name:
        from pathlib import Path
        lora_path = Path("/opt/ComfyUI/models/loras") / lora_name
        if not lora_path.exists():
            raise HTTPException(status_code=404, detail=f"LoRA not found: {lora_name}")

    workflow, prefix = build_wan22_workflow(
        prompt_text=prompt,
        width=width,
        height=height,
        num_frames=num_frames,
        fps=fps,
        steps=steps,
        cfg=cfg,
        seed=seed,
        lora_name=lora_name,
        lora_strength=lora_strength,
        ref_image=ref_image,
    )

    try:
        prompt_id = _submit_comfyui_workflow(workflow)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ComfyUI submission failed: {e}")

    seconds = num_frames / fps
    mode = "i2v" if ref_image else "t2v"

    return {
        "prompt_id": prompt_id,
        "engine": "wan22-5b-gguf",
        "mode": mode,
        "lora": lora_name,
        "seconds": round(seconds, 1),
        "resolution": f"{width}x{height}",
        "prefix": prefix,
    }
