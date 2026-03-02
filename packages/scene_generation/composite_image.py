"""Composite image generator for multi-character shots.

Generates a single still image containing two characters using SD1.5 + IP-Adapter
regional conditioning. Each character gets their own IP-Adapter reference image
applied to their region of the canvas, producing a composite source frame that
FramePack I2V can then animate.

Pipeline:
  1. Pick best approved reference image per character
  2. Build ComfyUI workflow with regional IP-Adapter (left/right masks)
  3. Submit and poll until complete
  4. Return path to generated composite image

Mask files (pre-generated, stored in ComfyUI/input/):
  - mask_left_half.png: left half white, right half black (544x704)
  - mask_right_half.png: right half white, left half black (544x704)
"""

import json
import logging
import random
import shutil
import time
import urllib.request
from pathlib import Path

from packages.core.config import BASE_PATH, COMFYUI_URL, COMFYUI_INPUT_DIR, COMFYUI_OUTPUT_DIR

logger = logging.getLogger(__name__)


def _ensure_masks_exist(width: int = 544, height: int = 704):
    """Create left/right half mask PNGs in ComfyUI input if they don't exist."""
    left_path = Path(COMFYUI_INPUT_DIR) / "mask_left_half.png"
    right_path = Path(COMFYUI_INPUT_DIR) / "mask_right_half.png"
    if left_path.exists() and right_path.exists():
        return
    try:
        from PIL import Image
        import numpy as np
        left = np.zeros((height, width), dtype=np.uint8)
        left[:, :width // 2] = 255
        Image.fromarray(left).save(left_path)
        right = np.zeros((height, width), dtype=np.uint8)
        right[:, width // 2:] = 255
        Image.fromarray(right).save(right_path)
        logger.info(f"Created composite masks: {width}x{height}")
    except Exception as e:
        logger.error(f"Failed to create masks: {e}")


async def pick_best_reference(conn, character_slug: str, project_id: int) -> Path | None:
    """Pick the best approved image for a character as IP-Adapter reference.

    Prefers images with higher quality_score from character_approvals,
    falls back to random approved image from approval_status.json.
    """
    # Try DB approvals with quality score first
    try:
        row = await conn.fetchrow(
            """SELECT image_path FROM character_approvals
               WHERE character_slug = $1 AND project_id = $2 AND status = 'approved'
               ORDER BY quality_score DESC NULLS LAST, created_at DESC
               LIMIT 1""",
            character_slug, project_id,
        )
        if row and row["image_path"]:
            p = Path(row["image_path"])
            if not p.is_absolute():
                p = BASE_PATH / p
            if p.exists():
                return p
    except Exception:
        pass

    # Fallback: pick from approval_status.json
    status_file = BASE_PATH / character_slug / "approval_status.json"
    if not status_file.exists():
        for d in BASE_PATH.iterdir():
            if d.is_dir() and d.name.replace("_", "") == character_slug.replace("_", ""):
                status_file = d / "approval_status.json"
                break
    if not status_file.exists():
        logger.warning(f"No approval_status.json for {character_slug}")
        return None

    with open(status_file) as f:
        statuses = json.load(f)

    approved = [k for k, v in statuses.items() if v == "approved"]
    if not approved:
        logger.warning(f"No approved images for {character_slug}")
        return None

    chosen = random.choice(approved)
    img_dir = BASE_PATH / character_slug / "images"
    if not img_dir.exists():
        img_dir = status_file.parent / "images"
    img_path = img_dir / chosen
    if img_path.exists():
        return img_path

    logger.warning(f"Approved image {chosen} not found on disk for {character_slug}")
    return None


def _copy_to_comfyui_input(src: Path, name: str) -> str:
    """Copy an image to ComfyUI input directory, return the filename."""
    dest = Path(COMFYUI_INPUT_DIR) / name
    shutil.copy2(src, dest)
    return name


def build_composite_workflow(
    prompt: str,
    negative_prompt: str,
    checkpoint_model: str,
    char_a_image: str,
    char_b_image: str,
    width: int = 544,
    height: int = 704,
    steps: int = 30,
    cfg: float = 7.0,
    sampler: str = "dpmpp_2m",
    scheduler: str = "karras",
    seed: int | None = None,
    output_prefix: str = "composite",
) -> tuple[dict, str]:
    """Build a ComfyUI workflow for two-character composite image generation.

    Uses IP-Adapter regional conditioning with pre-generated left/right mask PNGs
    loaded via LoadImageMask. Each character's reference image is applied to their
    half of the canvas.

    Returns (workflow_dict, output_prefix).
    """
    _ensure_masks_exist(width, height)

    if seed is None:
        seed = random.randint(1, 2**31)

    workflow = {}

    # 1: Checkpoint loader
    workflow["1"] = {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": checkpoint_model},
    }

    # 2: IP-Adapter Unified Loader (loads both model and ipadapter)
    workflow["2"] = {
        "class_type": "IPAdapterUnifiedLoader",
        "inputs": {
            "preset": "PLUS (high strength)",
            "model": ["1", 0],
        },
    }

    # 3: Load character A reference image
    workflow["3"] = {
        "class_type": "LoadImage",
        "inputs": {"image": char_a_image, "upload": "image"},
    }

    # 4: Load character B reference image
    workflow["4"] = {
        "class_type": "LoadImage",
        "inputs": {"image": char_b_image, "upload": "image"},
    }

    # 5: Positive prompt
    workflow["5"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": prompt, "clip": ["1", 1]},
    }

    # 6: Negative prompt
    workflow["6"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_prompt, "clip": ["1", 1]},
    }

    # 7: Load left-half mask (for character A)
    workflow["7"] = {
        "class_type": "LoadImageMask",
        "inputs": {"image": "mask_left_half.png", "channel": "red"},
    }

    # 8: Load right-half mask (for character B)
    workflow["8"] = {
        "class_type": "LoadImageMask",
        "inputs": {"image": "mask_right_half.png", "channel": "red"},
    }

    # 9: Regional conditioning for character A (left side)
    workflow["9"] = {
        "class_type": "IPAdapterRegionalConditioning",
        "inputs": {
            "image": ["3", 0],
            "image_weight": 0.8,
            "prompt_weight": 1.0,
            "weight_type": "linear",
            "start_at": 0.0,
            "end_at": 0.85,
            "mask": ["7", 0],
            "positive": ["5", 0],
            "negative": ["6", 0],
        },
    }

    # 10: Regional conditioning for character B (right side)
    workflow["10"] = {
        "class_type": "IPAdapterRegionalConditioning",
        "inputs": {
            "image": ["4", 0],
            "image_weight": 0.8,
            "prompt_weight": 1.0,
            "weight_type": "linear",
            "start_at": 0.0,
            "end_at": 0.85,
            "mask": ["8", 0],
            "positive": ["9", 1],  # Chain from region A
            "negative": ["9", 2],
        },
    }

    # 11: Combine regional IP-Adapter params
    workflow["11"] = {
        "class_type": "IPAdapterCombineParams",
        "inputs": {
            "params_1": ["9", 0],
            "params_2": ["10", 0],
        },
    }

    # 12: Apply combined IP-Adapter
    workflow["12"] = {
        "class_type": "IPAdapterFromParams",
        "inputs": {
            "model": ["2", 0],
            "ipadapter": ["2", 1],
            "ipadapter_params": ["11", 0],
            "combine_embeds": "concat",
            "embeds_scaling": "K+V",
        },
    }

    # 13: Empty latent
    workflow["13"] = {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": width, "height": height, "batch_size": 1},
    }

    # 14: KSampler
    workflow["14"] = {
        "class_type": "KSampler",
        "inputs": {
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": sampler,
            "scheduler": scheduler,
            "denoise": 1.0,
            "model": ["12", 0],
            "positive": ["10", 1],  # Final chained positive
            "negative": ["10", 2],  # Final chained negative
            "latent_image": ["13", 0],
        },
    }

    # 15: VAE Decode
    workflow["15"] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["14", 0],
            "vae": ["1", 2],
        },
    }

    # 16: Save Image
    workflow["16"] = {
        "class_type": "SaveImage",
        "inputs": {
            "filename_prefix": output_prefix,
            "images": ["15", 0],
        },
    }

    return workflow, output_prefix


def submit_workflow(workflow: dict) -> str:
    """Submit a workflow to ComfyUI and return the prompt_id."""
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())
    return result.get("prompt_id", "")


def poll_completion(prompt_id: str, timeout: int = 300) -> Path | None:
    """Poll ComfyUI until the prompt completes. Return the output image path."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            url = f"{COMFYUI_URL}/history/{prompt_id}"
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=10)
            history = json.loads(resp.read())

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_id, node_out in outputs.items():
                    images = node_out.get("images", [])
                    if images:
                        img = images[0]
                        subfolder = img.get("subfolder", "")
                        filename = img["filename"]
                        if subfolder:
                            return Path(COMFYUI_OUTPUT_DIR) / subfolder / filename
                        return Path(COMFYUI_OUTPUT_DIR) / filename
                logger.warning(f"Prompt {prompt_id} completed but no images in output")
                return None
        except Exception:
            pass
        time.sleep(3)

    logger.error(f"Prompt {prompt_id} timed out after {timeout}s")
    return None


async def generate_composite_source(
    conn,
    project_id: int,
    characters: list[str],
    scene_prompt: str,
    checkpoint_model: str = "realistic_vision_v51.safetensors",
) -> Path | None:
    """Generate a composite image with multiple characters for use as FramePack source.

    Args:
        conn: DB connection
        project_id: Project ID for character lookups
        characters: List of character slugs (first 2 used)
        scene_prompt: Text describing the scene/interaction
        checkpoint_model: SD1.5 checkpoint to use

    Returns:
        Path to the generated composite image, or None on failure.
    """
    if len(characters) < 2:
        logger.warning("generate_composite_source needs at least 2 characters")
        return None

    char_a, char_b = characters[0], characters[1]

    # Get reference images
    ref_a = await pick_best_reference(conn, char_a, project_id)
    ref_b = await pick_best_reference(conn, char_b, project_id)

    if not ref_a or not ref_b:
        logger.error(f"Missing reference images: {char_a}={ref_a}, {char_b}={ref_b}")
        return None

    # Get character design prompts
    design_a = ""
    design_b = ""
    for slug, attr in [(char_a, "a"), (char_b, "b")]:
        row = await conn.fetchrow(
            "SELECT name, design_prompt FROM characters "
            "WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1",
            slug,
        )
        if row:
            name = row["name"]
            design = (row["design_prompt"] or "").strip().rstrip(",. ")
            if attr == "a":
                design_a = f"{name} on the left, {design}"
            else:
                design_b = f"{name} on the right, {design}"

    full_prompt = f"two people, {design_a}, {design_b}, {scene_prompt}, masterpiece, best quality, detailed"
    negative = "worst quality, low quality, blurry, deformed, extra limbs, bad anatomy, three people, crowd, watermark, text"

    ref_a_name = _copy_to_comfyui_input(ref_a, f"composite_ref_{char_a}.png")
    ref_b_name = _copy_to_comfyui_input(ref_b, f"composite_ref_{char_b}.png")

    ts = int(time.time())
    prefix = f"composite_{char_a}_{char_b}_{ts}"

    workflow, _ = build_composite_workflow(
        prompt=full_prompt,
        negative_prompt=negative,
        checkpoint_model=checkpoint_model,
        char_a_image=ref_a_name,
        char_b_image=ref_b_name,
        output_prefix=prefix,
    )

    logger.info(f"Submitting composite workflow: {char_a} + {char_b}")
    prompt_id = submit_workflow(workflow)
    if not prompt_id:
        logger.error("Failed to submit composite workflow")
        return None

    logger.info(f"Composite workflow submitted: {prompt_id}, polling...")
    result = poll_completion(prompt_id, timeout=120)

    if result and result.exists():
        logger.info(f"Composite image generated: {result}")
        return result
    else:
        logger.error(f"Composite generation failed for {char_a} + {char_b}")
        return None
