"""Scene image generation via ComfyUI — translates image_prompt to workflow."""
import asyncio
import logging
from pathlib import Path

from packages.core.config import COMFYUI_OUTPUT_DIR
from packages.core.generation import _comfyui_slot
from packages.core.model_profiles import get_model_profile, translate_prompt
from packages.visual_pipeline.comfyui import (
    build_comfyui_workflow,
    submit_comfyui_workflow,
    get_comfyui_progress,
)

from .session_store import SessionState

logger = logging.getLogger(__name__)

# Where interactive images are saved within ComfyUI output
INTERACTIVE_SUBDIR = "interactive"


async def generate_scene_image(session: SessionState, scene_index: int, image_prompt: str):
    """Queue image generation for a scene. Updates session.images in-place."""
    session.images[scene_index] = {"status": "pending", "progress": 0.0}

    try:
        profile = get_model_profile(session.checkpoint_model)
        params = session.generation_params

        # Translate the AI-generated image prompt through the model profile
        translated = translate_prompt(
            design_prompt=image_prompt,
            appearance_data=None,
            profile=profile,
            pose="",
        )

        workflow = build_comfyui_workflow(
            design_prompt=translated,
            checkpoint_model=session.checkpoint_model,
            cfg_scale=params["cfg_scale"],
            steps=params["steps"],
            sampler=params["sampler"],
            scheduler=params["scheduler"],
            width=params["width"],
            height=params["height"],
            negative_prompt=params["negative_prompt"],
            generation_type="image",
            character_slug=INTERACTIVE_SUBDIR,
            project_name=f"play_{session.session_id}",
        )

        # Acquire shared ComfyUI slot
        async with _comfyui_slot:
            session.images[scene_index]["status"] = "generating"
            prompt_id = submit_comfyui_workflow(workflow)
            session.images[scene_index]["prompt_id"] = prompt_id

            # Poll until complete
            image_path = await _poll_image(prompt_id, session, scene_index)

        if image_path:
            session.images[scene_index].update({
                "status": "ready",
                "progress": 1.0,
                "path": str(image_path),
            })
        else:
            session.images[scene_index]["status"] = "failed"

    except Exception:
        logger.exception("Image generation failed for session %s scene %d", session.session_id, scene_index)
        session.images[scene_index]["status"] = "failed"


async def _poll_image(prompt_id: str, session: SessionState, scene_index: int, timeout: float = 120.0) -> Path | None:
    """Poll ComfyUI until image is done. Returns output path or None."""
    elapsed = 0.0
    interval = 2.0
    while elapsed < timeout:
        await asyncio.sleep(interval)
        elapsed += interval

        progress = get_comfyui_progress(prompt_id)
        status = progress.get("status", "unknown")

        if status == "completed":
            images = progress.get("images", [])
            if images:
                # ComfyUI returns relative paths under output dir
                return Path(images[0].get("abs_path") or _resolve_image_path(images[0]))
            return None
        elif status == "error":
            logger.error("ComfyUI error for prompt %s", prompt_id)
            return None

        # Update progress
        session.images[scene_index]["progress"] = progress.get("progress", 0.0)

    logger.warning("Image generation timed out for prompt %s", prompt_id)
    return None


def _resolve_image_path(image_info: dict) -> str:
    """Resolve ComfyUI image info to absolute path."""
    filename = image_info.get("filename", "")
    subfolder = image_info.get("subfolder", "")
    if subfolder:
        return str(COMFYUI_OUTPUT_DIR / subfolder / filename)
    return str(COMFYUI_OUTPUT_DIR / filename)


async def start_image_generation(session: SessionState, scene_index: int, image_prompt: str):
    """Fire-and-forget image generation as a background task."""
    asyncio.create_task(generate_scene_image(session, scene_index, image_prompt))


def get_image_status(session: SessionState, scene_index: int) -> dict:
    """Get current image generation status for a scene."""
    info = session.images.get(scene_index)
    if not info:
        return {"status": "pending", "progress": 0.0, "url": None}

    url = None
    if info.get("status") == "ready" and info.get("path"):
        url = f"/api/interactive/sessions/{session.session_id}/image/{scene_index}/file"

    return {
        "status": info.get("status", "pending"),
        "progress": info.get("progress", 0.0),
        "url": url,
    }
