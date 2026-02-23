"""Visual Pipeline router — generation, gallery endpoints.

Vision quality review endpoints are in visual_review.py (included as sub-router).
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from packages.core.config import BASE_PATH, COMFYUI_OUTPUT_DIR, normalize_sampler
from packages.core.db import get_char_project_map
from packages.core.models import GenerateRequest
from packages.core.audit import log_generation
from packages.core.events import event_bus, GENERATION_SUBMITTED
from packages.core.model_selector import recommend_params

from .comfyui import build_comfyui_workflow, submit_comfyui_workflow, get_comfyui_progress
from .visual_review import router as review_router

logger = logging.getLogger(__name__)
router = APIRouter()
router.include_router(review_router)


@router.post("/generate/{character_slug}")
async def generate_for_character(character_slug: str, body: GenerateRequest):
    """Generate an image or video for a character using SSOT profile."""
    char_map = await get_char_project_map()
    db_info = char_map.get(character_slug)
    if not db_info:
        raise HTTPException(status_code=404, detail=f"Character '{character_slug}' not found")

    # Use style_override if provided, otherwise use project default
    style_info = db_info
    if body.style_override:
        from packages.core.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT checkpoint_model, positive_prompt_template, negative_prompt_template, "
                "cfg_scale, sampler, steps, width, height, scheduler "
                "FROM generation_styles WHERE style_name = $1", body.style_override
            )
            if not row:
                raise HTTPException(status_code=400, detail=f"Style '{body.style_override}' not found")
            style_info = {**db_info, **dict(row)}
            logger.info(f"Using style override '{body.style_override}' for {character_slug}")

    checkpoint = style_info.get("checkpoint_model")
    if not checkpoint:
        raise HTTPException(status_code=400, detail="No checkpoint model configured for this character's project")

    prompt = body.prompt_override or db_info.get("design_prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="No design_prompt and no prompt_override provided")

    # Prepend positive_prompt_template from style (quality tags)
    style_preamble = style_info.get("positive_prompt_template") or db_info.get("style_preamble")
    if style_preamble and body.prompt_override:
        # For overrides, prepend the style's quality tags
        prompt = f"{style_preamble}, {prompt}"
    elif style_preamble and not body.prompt_override:
        prompt = f"{style_preamble}, {prompt}"

    norm_sampler, norm_scheduler = normalize_sampler(
        style_info.get("sampler"), style_info.get("scheduler")
    )

    # Use style's negative template if no explicit negative given
    style_negative = style_info.get("negative_prompt_template", "")
    base_negative = body.negative_prompt or style_negative or "worst quality, low quality, blurry, deformed"

    # Auto-enhance negative prompt with learned rejection patterns from DB
    try:
        rec = await recommend_params(
            character_slug, project_name=db_info.get("project_name"),
            checkpoint_model=checkpoint,
        )
        learned_neg = rec.get("learned_negatives", "")
        if learned_neg:
            base_negative = f"{base_negative}, {learned_neg}"
            logger.info(f"Enhanced negative prompt for {character_slug} with learned terms")
    except Exception:
        pass  # Never block generation on recommendation failure

    workflow = build_comfyui_workflow(
        design_prompt=prompt,
        checkpoint_model=checkpoint,
        cfg_scale=style_info.get("cfg_scale") or 7.0,
        steps=style_info.get("steps") or 25,
        sampler=norm_sampler,
        scheduler=norm_scheduler,
        width=style_info.get("width") or 512,
        height=style_info.get("height") or 768,
        negative_prompt=base_negative,
        generation_type=body.generation_type,
        seed=body.seed,
        character_slug=character_slug,
    )

    try:
        prompt_id = submit_comfyui_workflow(workflow)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ComfyUI submission failed: {e}")

    actual_seed = workflow["3"]["inputs"]["seed"]

    # Log to generation_history
    gen_id = await log_generation(
        character_slug=character_slug,
        project_name=db_info.get("project_name"),
        comfyui_prompt_id=prompt_id,
        generation_type=body.generation_type,
        checkpoint_model=checkpoint,
        prompt=prompt,
        negative_prompt=body.negative_prompt or "worst quality, low quality, blurry, deformed",
        seed=actual_seed,
        cfg_scale=db_info.get("cfg_scale"),
        steps=db_info.get("steps"),
        sampler=norm_sampler,
        scheduler=norm_scheduler,
        width=db_info.get("width"),
        height=db_info.get("height"),
    )

    await event_bus.emit(GENERATION_SUBMITTED, {
        "character_slug": character_slug,
        "prompt_id": prompt_id,
        "generation_history_id": gen_id,
        "project_name": db_info.get("project_name"),
    })

    return {
        "prompt_id": prompt_id,
        "generation_history_id": gen_id,
        "character": character_slug,
        "generation_type": body.generation_type,
        "prompt_used": prompt,
        "checkpoint": checkpoint,
        "seed": actual_seed,
    }


@router.get("/generate/{prompt_id}/status")
async def get_generation_status(prompt_id: str):
    """Check ComfyUI generation progress."""
    return get_comfyui_progress(prompt_id)


@router.get("/gallery")
async def get_gallery(limit: int = 50):
    """Get recent images from ComfyUI output directory."""
    if not COMFYUI_OUTPUT_DIR.exists():
        return {"images": []}

    image_files = []
    for ext in ("*.png", "*.jpg"):
        image_files.extend(COMFYUI_OUTPUT_DIR.glob(ext))

    image_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return {
        "images": [
            {
                "filename": img.name,
                "created_at": datetime.fromtimestamp(img.stat().st_mtime).isoformat(),
                "size_kb": round(img.stat().st_size / 1024, 1),
            }
            for img in image_files[:limit]
        ]
    }


@router.get("/gallery/image/{filename}")
async def get_gallery_image(filename: str):
    """Serve a gallery image from ComfyUI output."""
    image_path = COMFYUI_OUTPUT_DIR / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)
