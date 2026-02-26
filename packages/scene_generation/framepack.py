"""FramePack I2V workflow building and generation endpoints."""

import json
import logging
import shutil
from math import ceil
from pathlib import Path

from fastapi import APIRouter, HTTPException

from packages.core.config import BASE_PATH, COMFYUI_URL, COMFYUI_INPUT_DIR, COMFYUI_OUTPUT_DIR
from packages.core.db import get_char_project_map
from packages.core.models import FramePackRequest

logger = logging.getLogger(__name__)

router = APIRouter()

# Motion prompt presets keyed by shot type
MOTION_PRESETS: dict[str, list[str]] = {
    "establishing": [
        "slow pan across the scene, establishing the environment",
        "camera slowly zooms in on the location",
        "wide dolly shot revealing the setting",
        "gentle aerial view drifting over the scene",
    ],
    "wide": [
        "characters walk into frame from the side",
        "slow zoom out revealing the full scene",
        "camera pans left to right across the wide shot",
        "gentle wind blowing through the environment",
    ],
    "medium": [
        "character walks forward confidently",
        "character gestures while talking, slight body movement",
        "subtle idle sway, character shifts weight",
        "character turns to face the camera",
        "two characters face each other in conversation",
    ],
    "close-up": [
        "subtle breathing motion, gentle chest rise and fall",
        "character blinks and smiles softly",
        "gentle head turn from left to right",
        "character's eyes widen with surprise",
        "wind blows hair across the character's face",
    ],
    "extreme_close-up": [
        "eyes slowly narrow with determination",
        "a single tear rolls down the cheek",
        "lips move as if speaking quietly",
        "subtle eye movement, looking from side to side",
    ],
    "action": [
        "character leaps into frame with dynamic pose",
        "fast punch or kick with motion blur",
        "character sprints forward, running sequence",
        "dramatic dodge or evasive roll",
        "character powers up with energy radiating outward",
    ],
}

# FramePack model filenames (as ComfyUI sees them)
FRAMEPACK_MODELS = {
    "i2v": "FramePackI2V_HY_fp8_e4m3fn.safetensors",
    "f1": "FramePack_F1_I2V_HY_20250503_fp8_e4m3fn.safetensors",
    "clip_l": "clip_l.safetensors",
    "llava_text": "llava_llama3_fp16.safetensors",
    "clip_vision": "sigclip_vision_patch14_384.safetensors",
    "vae": "hunyuan_video_vae_bf16.safetensors",
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


def build_framepack_workflow(
    prompt_text: str,
    image_path: str,
    total_seconds: float = 3.0,
    steps: int = 30,
    use_f1: bool = False,
    seed: int | None = None,
    negative_text: str = "low quality, blurry, distorted, watermark",
    gpu_memory_preservation: float = 6.0,
    guidance_scale: float = 6.0,
) -> tuple[dict, str, str]:
    """Build FramePack I2V ComfyUI workflow.

    Returns (workflow_payload, sampler_node_id, prefix).

    NOTE: Character LoRAs trained on SD checkpoints (e.g. realcartoonPixar)
    are NOT compatible with FramePack's HunyuanVideo architecture.
    FramePack uses LoadFramePackModel + FramePackSampler, which is a
    fundamentally different model architecture from CheckpointLoaderSimple +
    KSampler used in image generation. SD-based LoraLoader nodes cannot be
    injected here. Character likeness in video comes from the source image
    (which was generated WITH the LoRA) and the CLIP vision encoder embedding.
    """
    import random as _random
    import time as _time
    if seed is None:
        seed = _random.randint(0, 2**63 - 1)

    model_file = FRAMEPACK_MODELS["f1"] if use_f1 else FRAMEPACK_MODELS["i2v"]

    workflow = {}
    nid = 1

    # Node 1: LoadFramePackModel
    model_node = str(nid)
    workflow[model_node] = {
        "class_type": "LoadFramePackModel",
        "inputs": {
            "model": model_file,
            "base_precision": "bf16",
            "quantization": "fp8_e4m3fn",
            "load_device": "offload_device",
            "attention_mode": "sdpa",
        },
    }
    nid += 1

    # Node 2: DualCLIPLoader
    clip_node = str(nid)
    workflow[clip_node] = {
        "class_type": "DualCLIPLoader",
        "inputs": {
            "clip_name1": FRAMEPACK_MODELS["clip_l"],
            "clip_name2": FRAMEPACK_MODELS["llava_text"],
            "type": "hunyuan_video",
            "device": "default",
        },
    }
    nid += 1

    # Node 3: Positive CLIP encode
    pos_node = str(nid)
    workflow[pos_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": prompt_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # Node 4: Negative CLIP encode
    neg_node = str(nid)
    workflow[neg_node] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_text, "clip": [clip_node, 0]},
    }
    nid += 1

    # Node 5: VAELoader
    vae_node = str(nid)
    workflow[vae_node] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": FRAMEPACK_MODELS["vae"]},
    }
    nid += 1

    # Node 6: LoadImage (reference image for I2V)
    load_img_node = str(nid)
    workflow[load_img_node] = {
        "class_type": "LoadImage",
        "inputs": {"image": image_path},
    }
    nid += 1

    # Node 6b: Downscale to safe resolution for RTX 3060 (max 544x704)
    # Pony XL images are 832x1216 which OOMs at sampling — must resize first
    max_w, max_h = 544, 704
    resize_node = str(nid)
    workflow[resize_node] = {
        "class_type": "ImageScale",
        "inputs": {
            "image": [load_img_node, 0],
            "width": max_w,
            "height": max_h,
            "upscale_method": "lanczos",
            "crop": "center",
        },
    }
    nid += 1
    # Downstream nodes use the resized image instead of the raw load
    img_source_node = resize_node

    # Node 7: VAEEncode source image -> start_latent
    vae_enc_node = str(nid)
    workflow[vae_enc_node] = {
        "class_type": "VAEEncode",
        "inputs": {
            "pixels": [img_source_node, 0],
            "vae": [vae_node, 0],
        },
    }
    nid += 1

    # Node 8: CLIPVisionLoader
    clip_vis_load_node = str(nid)
    workflow[clip_vis_load_node] = {
        "class_type": "CLIPVisionLoader",
        "inputs": {"clip_name": FRAMEPACK_MODELS["clip_vision"]},
    }
    nid += 1

    # Node 9: CLIPVisionEncode
    clip_vis_enc_node = str(nid)
    workflow[clip_vis_enc_node] = {
        "class_type": "CLIPVisionEncode",
        "inputs": {
            "clip_vision": [clip_vis_load_node, 0],
            "image": [img_source_node, 0],
            "crop": "center",
        },
    }
    nid += 1

    # Node 10: FramePackSampler
    sampler_node = str(nid)
    latent_window_size = 9
    sampler_inputs = {
        "model": [model_node, 0],
        "positive": [pos_node, 0],
        "negative": [neg_node, 0],
        "start_latent": [vae_enc_node, 0],
        "image_embeds": [clip_vis_enc_node, 0],
        "steps": steps,
        "use_teacache": True,
        "teacache_rel_l1_thresh": 0.15,
        "cfg": 1.0,
        "guidance_scale": guidance_scale,
        "shift": 0.0,
        "seed": seed,
        "latent_window_size": latent_window_size,
        "total_second_length": total_seconds,
        "gpu_memory_preservation": gpu_memory_preservation,
        "sampler": "unipc_bh1",
    }
    workflow[sampler_node] = {
        "class_type": "FramePackSampler",
        "inputs": sampler_inputs,
    }
    nid += 1

    # Node 11: VAEDecodeTiled
    decode_node = str(nid)
    workflow[decode_node] = {
        "class_type": "VAEDecodeTiled",
        "inputs": {
            "samples": [sampler_node, 0],
            "vae": [vae_node, 0],
            "tile_size": 256,
            "overlap": 64,
            "temporal_size": 64,
            "temporal_overlap": 8,
        },
    }
    nid += 1

    # Node 12: VHS_VideoCombine
    ts = int(_time.time())
    prefix = f"framepack_{ts}"
    output_node = str(nid)
    workflow[output_node] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": [decode_node, 0],
            "frame_rate": 30,
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

    return {"prompt": workflow}, sampler_node, prefix


def calc_framepack_sections(seconds: float, latent_window_size: int, use_f1: bool) -> int:
    """Calculate number of sampling sections for progress tracking."""
    if use_f1:
        section_duration = (latent_window_size * 4 - 3) / 30.0
        return max(ceil(seconds / section_duration), 1)
    else:
        return max(round((seconds * 30) / (latent_window_size * 4)), 1)


@router.post("/generate/framepack")
async def generate_framepack(body: FramePackRequest):
    """Generate a FramePack I2V video for a character."""
    char_map = await get_char_project_map()
    db_info = char_map.get(body.character_slug)
    if not db_info:
        raise HTTPException(status_code=404, detail=f"Character '{body.character_slug}' not found")

    prompt = body.prompt_override or db_info.get("design_prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="No design_prompt and no prompt_override provided")

    # Resolve reference image
    image_filename = body.image_path
    if not image_filename:
        # Pick the first approved image for this character
        char_images_dir = BASE_PATH / body.character_slug / "images"
        approval_file = BASE_PATH / body.character_slug / "approval_status.json"
        approved_images = []
        if approval_file.exists():
            with open(approval_file) as f:
                approvals = json.load(f)
            approved_images = [
                name for name, st in approvals.items()
                if st == "approved" or (isinstance(st, dict) and st.get("status") == "approved")
            ]
        if not approved_images and char_images_dir.exists():
            # Fall back to any image in the dataset
            approved_images = [p.name for p in sorted(char_images_dir.glob("*.png"))[:1]]
        if not approved_images:
            raise HTTPException(status_code=400, detail="No images available as I2V source. Upload or approve images first.")

        source_image = approved_images[0]
        source_path = char_images_dir / source_image
        dest_path = COMFYUI_INPUT_DIR / source_image
        if not dest_path.exists():
            shutil.copy2(source_path, dest_path)
        image_filename = source_image

    negative = body.negative_prompt or "low quality, blurry, distorted, watermark"
    latent_window_size = 9
    total_sections = calc_framepack_sections(body.seconds, latent_window_size, body.use_f1)
    total_steps = total_sections * body.steps

    workflow_data, sampler_node_id, prefix = build_framepack_workflow(
        prompt_text=prompt,
        image_path=image_filename,
        total_seconds=body.seconds,
        steps=body.steps,
        use_f1=body.use_f1,
        seed=body.seed,
        negative_text=negative,
        gpu_memory_preservation=body.gpu_memory_preservation,
        guidance_scale=body.guidance_scale,
    )

    try:
        prompt_id = _submit_comfyui_workflow(workflow_data["prompt"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ComfyUI submission failed: {e}")

    return {
        "prompt_id": prompt_id,
        "character": body.character_slug,
        "model": "f1" if body.use_f1 else "i2v",
        "seconds": body.seconds,
        "source_image": image_filename,
        "total_sections": total_sections,
        "total_steps": total_steps,
        "sampler_node_id": sampler_node_id,
    }


@router.get("/generate/framepack/{prompt_id}/status")
async def get_framepack_status(prompt_id: str):
    """Check FramePack generation progress (poll-based fallback)."""
    import urllib.request
    try:
        # Check queue
        req = urllib.request.Request(f"{COMFYUI_URL}/queue")
        resp = urllib.request.urlopen(req, timeout=10)
        queue_data = json.loads(resp.read())

        for job in queue_data.get("queue_running", []):
            if prompt_id in str(job):
                return {"status": "running", "progress": 0.5}

        for job in queue_data.get("queue_pending", []):
            if prompt_id in str(job):
                return {"status": "pending", "progress": 0.1}

        # Check history
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
        logger.warning(f"FramePack progress check failed: {e}")
        return {"status": "error", "progress": 0.0, "error": str(e)}
