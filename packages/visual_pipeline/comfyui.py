"""ComfyUI interaction helpers — workflow building, submission, progress tracking."""

import json
import logging
from pathlib import Path

from packages.core.config import COMFYUI_URL, COMFYUI_OUTPUT_DIR, BASE_PATH
from packages.core.model_profiles import get_model_profile

logger = logging.getLogger(__name__)


def _find_lora(character_slug: str, checkpoint_model: str) -> Path | None:
    """Find the architecture-matched LoRA for a character.

    SDXL checkpoints use *_xl_lora.safetensors, SD1.5 uses *_lora.safetensors.
    Returns None if no matching LoRA exists (never cross-architecture).
    """
    lora_dir = Path("/opt/ComfyUI/models/loras")
    profile = get_model_profile(checkpoint_model)
    if profile["architecture"] == "sdxl":
        xl_path = lora_dir / f"{character_slug}_xl_lora.safetensors"
        return xl_path if xl_path.exists() else None
    else:
        sd_path = lora_dir / f"{character_slug}_lora.safetensors"
        return sd_path if sd_path.exists() else None


def build_comfyui_workflow(
    design_prompt: str,
    checkpoint_model: str,
    cfg_scale: float = 7.0,
    steps: int = 25,
    sampler: str = "dpmpp_2m",
    scheduler: str = "karras",
    width: int = 512,
    height: int = 768,
    negative_prompt: str = "worst quality, low quality, blurry, deformed",
    generation_type: str = "image",
    seed: int | None = None,
    character_slug: str = "output",
    project_name: str | None = None,
    pose: str | None = None,
    multi_character: bool = False,
) -> dict:
    """Build a ComfyUI workflow dict for image or video generation.

    Args:
        multi_character: If True, skips IP-Adapter injection. IP-Adapter anchors
            to a single character's reference and actively kills the second person
            in multi-character scenes (tested 2026-02-28 across weights 0.2-0.7).
    """
    import random as _random
    if seed is None:
        seed = _random.randint(1, 2**31)

    batch_size = 1
    if generation_type == "video":
        batch_size = 16
        # Cap video resolution to 768 per dimension (was 512 — too blurry).
        # Scene engines (FramePack, Wan, LTX) handle their own resolution;
        # this only affects the legacy comfyui.py video path.
        width = min(width, 768)
        height = min(height, 768)

    workflow = {
        "3": {
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg_scale,
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
            "class_type": "KSampler",
        },
        "4": {
            "inputs": {"ckpt_name": checkpoint_model},
            "class_type": "CheckpointLoaderSimple",
        },
        "5": {
            "inputs": {"width": width, "height": height, "batch_size": batch_size},
            "class_type": "EmptyLatentImage",
        },
        "6": {
            "inputs": {"text": design_prompt, "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "7": {
            "inputs": {"text": negative_prompt, "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "8": {
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            "class_type": "VAEDecode",
        },
    }

    import re as _re
    import time as _time
    ts = int(_time.time())
    # Structured prefix: project_character_action_timestamp
    proj = _re.sub(r'[^a-z0-9]', '', (project_name or 'gen').lower())[:20]
    action = _re.sub(r'[^a-z0-9]', '', (pose or 'img').split(',')[0].lower())[:15]
    prefix = f"{proj}_{character_slug}_{action}_{ts}"

    # Inject LoraLoader if an architecture-matched LoRA exists for this character
    lora_path = _find_lora(character_slug, checkpoint_model)
    if lora_path is not None:
        workflow["10"] = {
            "inputs": {
                "lora_name": lora_path.name,
                "strength_model": 0.8,
                "strength_clip": 0.8,
                "model": ["4", 0],
                "clip": ["4", 1],
            },
            "class_type": "LoraLoader",
            "_meta": {"title": "LoRA Loader"},
        }
        # Rewire: KSampler model -> LoraLoader
        workflow["3"]["inputs"]["model"] = ["10", 0]
        # Rewire: CLIP text encoders -> LoraLoader CLIP
        workflow["6"]["inputs"]["clip"] = ["10", 1]
        workflow["7"]["inputs"]["clip"] = ["10", 1]
        logger.info(f"LoRA injected: {lora_path.name} for {character_slug}")

    # Inject IP-Adapter if reference images exist and the model profile has an adapter.
    # SKIP for multi-character shots — IPA anchors to one character and kills the second
    # person entirely (tested 2026-02-28: even weight 0.2 produces solo output).
    profile = get_model_profile(checkpoint_model)
    ref_dir = BASE_PATH / character_slug / "reference_images"
    ip_adapter_name = profile.get("ip_adapter_model")
    ipadapter_model = Path(f"/opt/ComfyUI/models/ipadapter/{ip_adapter_name}") if ip_adapter_name else None
    clip_vision_model = Path("/opt/ComfyUI/models/clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors")
    if multi_character:
        logger.info(f"Multi-character shot: skipping IP-Adapter (would kill second character)")
    elif ipadapter_model and ipadapter_model.exists() and ref_dir.exists() and clip_vision_model.exists():
        ref_images = sorted(ref_dir.glob("*.png")) + sorted(ref_dir.glob("*.jpg"))
        if ref_images:
            import random as _rand
            ref_img = _rand.choice(ref_images)
            # Copy reference to ComfyUI input if not already there
            comfyui_input = Path("/opt/ComfyUI/input")
            ref_dest = comfyui_input / f"ref_{character_slug}.png"
            if not ref_dest.exists() or ref_dest.stat().st_mtime < ref_img.stat().st_mtime:
                import shutil
                shutil.copy2(ref_img, ref_dest)

            # Determine which node provides the model (LoRA or checkpoint)
            model_source = ["10", 0] if lora_path is not None else ["4", 0]

            # Load CLIP Vision
            workflow["20"] = {
                "inputs": {"clip_name": clip_vision_model.name},
                "class_type": "CLIPVisionLoader",
            }
            # Load reference image
            workflow["21"] = {
                "inputs": {"image": ref_dest.name, "upload": "image"},
                "class_type": "LoadImage",
            }
            # IP-Adapter Unified Loader
            workflow["22"] = {
                "inputs": {
                    "preset": "PLUS (high strength)",
                    "model": model_source,
                },
                "class_type": "IPAdapterUnifiedLoader",
            }
            # IP-Adapter Apply
            workflow["23"] = {
                "inputs": {
                    "weight": 0.7,
                    "weight_type": "linear",
                    "combine_embeds": "concat",
                    "start_at": 0.0,
                    "end_at": 0.85,
                    "embeds_scaling": "K+V",
                    "model": ["22", 0],
                    "ipadapter": ["22", 1],
                    "image": ["21", 0],
                },
                "class_type": "IPAdapterAdvanced",
            }
            # Rewire KSampler to use IP-Adapter output model
            workflow["3"]["inputs"]["model"] = ["23", 0]
            logger.info(f"IP-Adapter injected: ref={ref_img.name} for {character_slug}")

    # Inject RescaleCFG node for v-prediction models (prevents oversaturation)
    rescale_cfg = profile.get("rescale_cfg")
    if rescale_cfg:
        # Current model source for KSampler
        current_model = workflow["3"]["inputs"]["model"]
        workflow["30"] = {
            "inputs": {
                "multiplier": rescale_cfg,
                "model": current_model,
            },
            "class_type": "RescaleCFG",
        }
        # Rewire KSampler to use RescaleCFG output
        workflow["3"]["inputs"]["model"] = ["30", 0]
        logger.info(f"RescaleCFG injected: multiplier={rescale_cfg}")

    if generation_type == "video":
        workflow["9"] = {
            "inputs": {
                "frame_rate": 8,
                "loop_count": 0,
                "filename_prefix": prefix,
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
                "images": ["8", 0],
            },
            "class_type": "VHS_VideoCombine",
        }
    else:
        workflow["9"] = {
            "inputs": {"filename_prefix": prefix, "images": ["8", 0]},
            "class_type": "SaveImage",
        }

    return workflow


def submit_comfyui_workflow(workflow: dict) -> str:
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


def get_comfyui_progress(prompt_id: str) -> dict:
    """Check ComfyUI generation progress for a given prompt_id."""
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

        # Check history for completion
        req = urllib.request.Request(f"{COMFYUI_URL}/history/{prompt_id}")
        resp = urllib.request.urlopen(req, timeout=10)
        history = json.loads(resp.read())

        if prompt_id in history:
            outputs = history[prompt_id].get("outputs", {})
            images = []
            for node_output in outputs.values():
                images.extend(node_output.get("images", []))
            return {
                "status": "completed",
                "progress": 1.0,
                "images": [img.get("filename") for img in images],
            }

        return {"status": "unknown", "progress": 0.0}
    except Exception as e:
        logger.warning(f"ComfyUI progress check failed: {e}")
        return {"status": "error", "progress": 0.0, "error": str(e)}
