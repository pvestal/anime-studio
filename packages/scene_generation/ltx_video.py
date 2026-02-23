"""LTX-Video workflow building and generation endpoints.

Uses the minimal LTX-Video 2B pipeline on NVIDIA RTX 3060:
  - Text encoder: t5xxl_fp8_e4m3fn (1.4G VRAM)
  - Model: ltxv-2b-fp8 (4.2G VRAM)
  - VAE: ltx2_vae (1.6G VRAM)
  - Total: ~7G — fits comfortably in 12GB

Supports both text-to-video and image-to-video modes.
Unlike FramePack, LTX-Video supports native LoRA injection.
"""

import json
import logging
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from packages.core.config import BASE_PATH, COMFYUI_URL, COMFYUI_INPUT_DIR, COMFYUI_OUTPUT_DIR
from packages.core.db import get_char_project_map

logger = logging.getLogger(__name__)

router = APIRouter()

# LTX-Video model files (as ComfyUI sees them)
LTX_MODELS = {
    "checkpoint": "ltxv-2b-fp8.safetensors",
    "text_encoder": "t5xxl_fp8_e4m3fn.safetensors",
    "vae": "ltx2_vae_fixed.safetensors",
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


def build_ltx_workflow(
    prompt_text: str,
    width: int = 512,
    height: int = 320,
    num_frames: int = 65,
    fps: int = 24,
    steps: int = 20,
    cfg: float = 3.5,
    seed: int | None = None,
    negative_text: str = "low quality, blurry, distorted, watermark, text",
    image_path: str | None = None,
    lora_name: str | None = None,
    lora_strength: float = 0.8,
) -> tuple[dict, str]:
    """Build an LTX-Video ComfyUI workflow.

    Returns (workflow_dict, output_prefix).

    Args:
        prompt_text: Main generation prompt.
        width: Video width (multiple of 32, max ~768 for 12GB VRAM).
        height: Video height (multiple of 32).
        num_frames: Number of frames (65 = ~2.7s at 24fps, 97 = ~4s).
        fps: Output frame rate.
        steps: Sampling steps.
        cfg: CFG guidance scale.
        seed: Random seed, auto-generated if None.
        negative_text: Negative prompt.
        image_path: If provided, use image-to-video mode (filename in ComfyUI/input/).
        lora_name: Optional LoRA filename to inject (LTX LoRAs work natively).
        lora_strength: LoRA injection strength.
    """
    import random as _random
    if seed is None:
        seed = _random.randint(0, 2**63 - 1)

    workflow = {}
    nid = 1

    # Node 1: UNETLoader — loads MODEL (detects as LTX correctly).
    # CheckpointLoaderSimple misdetects ltxv-2b as FLUX, breaking LTXVBaseSampler.
    unet_node = str(nid)
    workflow[unet_node] = {
        "class_type": "UNETLoader",
        "inputs": {
            "unet_name": LTX_MODELS["checkpoint"],
            "weight_dtype": "default",
        },
    }
    nid += 1

    # Node 2: CheckpointLoaderSimple — used ONLY for the embedded LTX-2 VAE.
    # The standalone ltx2_vae.safetensors is a mismatched LTX-1 format that
    # VAELoader can't load. The checkpoint embeds the correct LTX-2 VAE.
    ckpt_node = str(nid)
    workflow[ckpt_node] = {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": LTX_MODELS["checkpoint"]},
    }
    nid += 1

    # Node 3: CLIPLoader — T5-XXL FP8 text encoder (~1.4GB VRAM)
    clip_loader_node = str(nid)
    workflow[clip_loader_node] = {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": LTX_MODELS["text_encoder"],
            "type": "ltxv",
        },
    }
    nid += 1

    # Track which node provides the model (may be rewired by LoRA)
    model_source = [unet_node, 0]
    clip_source = [clip_loader_node, 0]
    vae_source = [ckpt_node, 2]

    # Optional: LoRA injection (LTX-Video supports this natively)
    if lora_name:
        lora_node = str(nid)
        workflow[lora_node] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": model_source,
                "lora_name": lora_name,
                "strength_model": lora_strength,
            },
        }
        model_source = [lora_node, 0]
        nid += 1

    # Node: Positive CLIP encode
    pos_node = str(nid)
    workflow[pos_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": prompt_text, "clip": clip_source},
    }
    nid += 1

    # Node: Negative CLIP encode
    neg_node = str(nid)
    workflow[neg_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_text, "clip": clip_source},
    }
    nid += 1

    # Node: LTXVConditioning (adds frame_rate info)
    cond_node = str(nid)
    workflow[cond_node] = {
        "class_type": "LTXVConditioning",
        "inputs": {
            "positive": [pos_node, 0],
            "negative": [neg_node, 0],
            "frame_rate": fps,
        },
    }
    nid += 1

    # Node: Latent (either empty for t2v, or from image for i2v)
    if image_path:
        # Image-to-video mode
        load_img_node = str(nid)
        workflow[load_img_node] = {
            "class_type": "LoadImage",
            "inputs": {"image": image_path},
        }
        nid += 1

        i2v_node = str(nid)
        workflow[i2v_node] = {
            "class_type": "LTXVImgToVideo",
            "inputs": {
                "positive": [cond_node, 0],
                "negative": [cond_node, 1],
                "vae": vae_source,
                "image": [load_img_node, 0],
                "width": width,
                "height": height,
                "length": num_frames,
                "batch_size": 1,
                "strength": 1.0,
            },
        }
        # LTXVImgToVideo outputs: 0=positive(CONDITIONING), 1=negative(CONDITIONING), 2=latent(LATENT)
        pos_source = [i2v_node, 0]
        neg_source = [i2v_node, 1]
        latent_source = [i2v_node, 2]
        nid += 1
    else:
        # Text-to-video mode
        latent_node = str(nid)
        workflow[latent_node] = {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": width,
                "height": height,
                "length": num_frames,
                "batch_size": 1,
            },
        }
        latent_source = [latent_node, 0]
        pos_source = [cond_node, 0]
        neg_source = [cond_node, 1]
        nid += 1

    # Node: LTXVScheduler
    scheduler_node = str(nid)
    workflow[scheduler_node] = {
        "class_type": "LTXVScheduler",
        "inputs": {
            "steps": steps,
            "max_shift": 2.05,
            "base_shift": 0.95,
            "stretch": True,
            "terminal": 0.1,
        },
    }
    nid += 1

    # Node: RandomNoise (outputs NOISE type)
    noise_node = str(nid)
    workflow[noise_node] = {
        "class_type": "RandomNoise",
        "inputs": {"noise_seed": seed},
    }
    nid += 1

    # Node: KSamplerSelect (outputs SAMPLER type)
    sampler_select_node = str(nid)
    workflow[sampler_select_node] = {
        "class_type": "KSamplerSelect",
        "inputs": {"sampler_name": "euler"},
    }
    nid += 1

    # Node: CFGGuider
    guider_node = str(nid)
    workflow[guider_node] = {
        "class_type": "CFGGuider",
        "inputs": {
            "model": model_source,
            "positive": pos_source,
            "negative": neg_source,
            "cfg": cfg,
        },
    }
    nid += 1

    # Node: LTXVBaseSampler
    sampler_node = str(nid)
    workflow[sampler_node] = {
        "class_type": "LTXVBaseSampler",
        "inputs": {
            "model": model_source,
            "vae": vae_source,
            "width": width,
            "height": height,
            "num_frames": num_frames,
            "guider": [guider_node, 0],
            "sampler": [sampler_select_node, 0],
            "sigmas": [scheduler_node, 0],
            "noise": [noise_node, 0],
        },
    }
    nid += 1

    # Node: LTXVSpatioTemporalTiledVAEDecode
    decode_node = str(nid)
    workflow[decode_node] = {
        "class_type": "LTXVSpatioTemporalTiledVAEDecode",
        "inputs": {
            "vae": vae_source,
            "latents": [sampler_node, 0],
            "spatial_tiles": 2,
            "spatial_overlap": 1,
            "temporal_tile_length": 16,
            "temporal_overlap": 1,
            "last_frame_fix": False,
            "working_device": "auto",
            "working_dtype": "auto",
        },
    }
    nid += 1

    # Node: VHS_VideoCombine (output)
    ts = int(time.time())
    prefix = f"ltx_{ts}"
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


@router.post("/generate/ltx")
async def generate_ltx_video(
    character_slug: str,
    prompt_override: str | None = None,
    negative_prompt: str | None = None,
    image_path: str | None = None,
    width: int = 512,
    height: int = 320,
    num_frames: int = 65,
    fps: int = 24,
    steps: int = 20,
    cfg: float = 3.5,
    seed: int | None = None,
    use_lora: bool = True,
    mode: str = "t2v",
):
    """Generate an LTX-Video clip for a character.

    Args:
        mode: "t2v" for text-to-video, "i2v" for image-to-video.
    """
    char_map = await get_char_project_map()
    db_info = char_map.get(character_slug)
    if not db_info:
        raise HTTPException(status_code=404, detail=f"Character '{character_slug}' not found")

    prompt = prompt_override or db_info.get("design_prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="No design_prompt and no prompt_override provided")

    # Resolve LoRA
    lora_name = None
    if use_lora:
        lora_path = Path("/opt/ComfyUI/models/loras") / f"{character_slug}_lora.safetensors"
        if lora_path.exists():
            lora_name = lora_path.name

    # Resolve image for i2v mode
    image_filename = None
    if mode == "i2v":
        image_filename = image_path
        if not image_filename:
            char_images_dir = BASE_PATH / character_slug / "images"
            approval_file = BASE_PATH / character_slug / "approval_status.json"
            approved_images = []
            if approval_file.exists():
                with open(approval_file) as f:
                    approvals = json.load(f)
                approved_images = [
                    name for name, st in approvals.items()
                    if st == "approved" or (isinstance(st, dict) and st.get("status") == "approved")
                ]
            if not approved_images and char_images_dir.exists():
                approved_images = [p.name for p in sorted(char_images_dir.glob("*.png"))[:1]]
            if not approved_images:
                raise HTTPException(status_code=400, detail="No images available for I2V. Use mode=t2v or upload images.")

            source_image = approved_images[0]
            source_path = char_images_dir / source_image
            dest_path = COMFYUI_INPUT_DIR / source_image
            if not dest_path.exists():
                shutil.copy2(source_path, dest_path)
            image_filename = source_image

    negative = negative_prompt or "low quality, blurry, distorted, watermark, text"

    workflow, prefix = build_ltx_workflow(
        prompt_text=prompt,
        width=width,
        height=height,
        num_frames=num_frames,
        fps=fps,
        steps=steps,
        cfg=cfg,
        seed=seed,
        negative_text=negative,
        image_path=image_filename,
        lora_name=lora_name,
        lora_strength=0.8,
    )

    try:
        prompt_id = _submit_comfyui_workflow(workflow)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ComfyUI submission failed: {e}")

    seconds = num_frames / fps

    return {
        "prompt_id": prompt_id,
        "character": character_slug,
        "engine": "ltx-video-2b",
        "mode": mode,
        "seconds": round(seconds, 1),
        "resolution": f"{width}x{height}",
        "source_image": image_filename,
        "lora": lora_name,
        "prefix": prefix,
    }


@router.get("/generate/ltx/{prompt_id}/status")
async def get_ltx_status(prompt_id: str):
    """Check LTX-Video generation progress."""
    import urllib.request
    try:
        req = urllib.request.Request(f"{COMFYUI_URL}/queue")
        resp = urllib.request.urlopen(req, timeout=10)
        queue_data = json.loads(resp.read())

        for job in queue_data.get("queue_running", []):
            if prompt_id in str(job):
                return {"status": "running", "progress": 0.5}

        for job in queue_data.get("queue_pending", []):
            if prompt_id in str(job):
                return {"status": "pending", "progress": 0.1}

        req = urllib.request.Request(f"{COMFYUI_URL}/history/{prompt_id}")
        resp = urllib.request.urlopen(req, timeout=10)
        history = json.loads(resp.read())

        if prompt_id in history:
            outputs = history[prompt_id].get("outputs", {})
            videos = []
            for node_output in outputs.values():
                for key in ("videos", "gifs", "images"):
                    for item in node_output.get(key, []):
                        videos.append(item.get("filename"))
            return {
                "status": "completed",
                "progress": 1.0,
                "output_files": videos,
            }

        return {"status": "unknown", "progress": 0.0}
    except Exception as e:
        logger.warning(f"LTX progress check failed: {e}")
        return {"status": "error", "progress": 0.0, "error": str(e)}
