"""Ingest helpers — Pydantic models, shared state, classification and save utilities."""

import asyncio
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from packages.core.config import BASE_PATH, COMFYUI_OUTPUT_DIR, MOVIES_DIR
from packages.core.comfyui import build_ipadapter_workflow
from packages.lora_training.dedup import is_duplicate, register_hash
from packages.lora_training.feedback import register_pending_image

# In-memory progress for active ingestion jobs
_ingest_progress: dict = {}

# Slug used for frames that don't match any known character
_UNCLASSIFIED_SLUG = "_unclassified"

# ComfyUI input directory for IPAdapter workflows
COMFYUI_INPUT_DIR = Path("/opt/ComfyUI/input")

# Local alias for existing call sites
_build_ipadapter_workflow = build_ipadapter_workflow


# ===================================================================
# Pydantic request models
# ===================================================================

class YouTubeIngestRequest(BaseModel):
    url: str
    character_slug: str
    max_frames: int = 50


class YouTubeProjectIngestRequest(BaseModel):
    url: str
    project_name: str
    max_frames: int = 50


class LocalVideoIngestRequest(BaseModel):
    path: str
    project_name: str
    max_frames: int = 200
    fps: float = 4


class MovieExtractRequest(BaseModel):
    path: str
    project_name: str
    max_frames: int = 500
    fps: float = 4


class ClipClassifyRequest(BaseModel):
    path: str
    project_name: str
    target_character: str | None = None
    max_frames: int = 200
    extract_clips: bool = True
    clip_duration: float = 2.0


class ClipClassifyLocalRequest(BaseModel):
    frames_dir: str
    project_name: str
    target_character: str | None = None
    source_video: str | None = None


# ===================================================================
# Helper functions
# ===================================================================

def _save_unclassified_frame(
    frame: Path,
    *,
    project_name: str,
    source: str,
    source_url: str | None,
    frame_number: int,
    description: str,
    matched: list[str],
    timestamp: str,
) -> str | None:
    """Copy an unmatched frame to _unclassified/images/ with metadata.

    Returns the destination filename, or None if the frame is a duplicate.
    """
    unc_dir = BASE_PATH / _UNCLASSIFIED_SLUG / "images"
    unc_dir.mkdir(parents=True, exist_ok=True)

    project_slug = re.sub(r'[^a-z0-9_-]', '', project_name.lower().replace(' ', '_'))
    dest_name = f"yt_unclassified_{project_slug}_{timestamp}_{frame_number:04d}.png"
    dest = unc_dir / dest_name

    # Dedup against existing unclassified images
    if is_duplicate(frame, _UNCLASSIFIED_SLUG):
        return None

    shutil.copy2(frame, dest)

    meta = {
        "seed": None,
        "full_prompt": None,
        "design_prompt": "",
        "checkpoint_model": None,
        "source": source,
        "source_url": source_url,
        "frame_number": frame_number,
        "project_name": project_name,
        "character_name": "Unclassified",
        "generated_at": datetime.now().isoformat(),
        "vision_description": description[:300] if description else "",
        "vision_matched": matched,
        "unclassified": True,
    }
    dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    dest.with_suffix(".txt").write_text("unclassified frame")
    register_pending_image(_UNCLASSIFIED_SLUG, dest_name)
    register_hash(dest, _UNCLASSIFIED_SLUG)
    return dest_name


def _classify_image_sync(image_path: Path, **kwargs) -> tuple[list[str], str]:
    """Classify an image (blocking). Called via asyncio.to_thread().

    Tries CLIP-based classification first (fast, content-agnostic, works with NSFW).
    Falls back to vision model if CLIP has no reference embeddings for the project.
    """
    use_clip = kwargs.pop("use_clip", True)
    project_name = kwargs.get("project_name")
    allowed_slugs = kwargs.get("allowed_slugs")

    if use_clip and project_name:
        try:
            from packages.visual_pipeline.clip_classifier import (
                build_reference_embeddings, _embed_image, classify_frame_clip,
            )
            refs = build_reference_embeddings(project_name, allowed_slugs)
            if refs:
                embedding = _embed_image(image_path)
                result = classify_frame_clip(embedding, refs)
                matched_slugs = result.get("matched_slugs", [])
                if not matched_slugs and result.get("matched_slug"):
                    matched_slugs = [result["matched_slug"]]
                desc = f"CLIP match (score={result['similarity']:.3f})"
                if matched_slugs:
                    return matched_slugs, desc
                # CLIP found nothing — fall through to vision model
        except Exception as e:
            logging.getLogger(__name__).warning(f"CLIP classification failed for {image_path.name}: {e}")

    from packages.visual_pipeline.classification import classify_image
    return classify_image(image_path, **kwargs)


async def _classify_image(image_path: Path, **kwargs) -> tuple[list[str], str]:
    """Classify an image without blocking the event loop."""
    return await asyncio.to_thread(_classify_image_sync, image_path, **kwargs)


async def _save_frame_to_characters(
    frame: Path,
    matched: list[str],
    *,
    char_map: dict,
    source: str,
    source_url: str | None,
    frame_number: int,
    timestamp: str,
    project_name: str,
    description: str,
    prefix: str = "yt",
) -> tuple[list[str], int]:
    """Save a frame to ALL matched character datasets (multi-character aware).

    Per-character dedup: the same frame can be new for yoshi but a dupe for mario.

    Returns (saved_slugs, duplicate_count).
    """
    saved_slugs: list[str] = []
    dup_count = 0

    for slug in matched:
        if await asyncio.to_thread(is_duplicate, frame, slug):
            dup_count += 1
            continue

        db_info = char_map.get(slug, {})
        dataset_images = BASE_PATH / slug / "images"
        dataset_images.mkdir(parents=True, exist_ok=True)

        dest_name = f"{prefix}_{slug}_{timestamp}_{frame_number:04d}.png"
        dest = dataset_images / dest_name
        shutil.copy2(frame, dest)

        meta = {
            "seed": None,
            "full_prompt": None,
            "design_prompt": db_info.get("design_prompt", ""),
            "checkpoint_model": None,
            "source": source,
            "source_url": source_url,
            "frame_number": frame_number,
            "project_name": project_name,
            "character_name": db_info.get("name", slug),
            "generated_at": datetime.now().isoformat(),
            "vision_description": description[:300] if description else "",
            "vision_matched": matched,
        }
        dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
        caption = db_info.get("design_prompt") or slug.replace("_", " ")
        dest.with_suffix(".txt").write_text(caption)
        register_pending_image(slug, dest_name)
        register_hash(dest, slug)
        saved_slugs.append(slug)

    return saved_slugs, dup_count
