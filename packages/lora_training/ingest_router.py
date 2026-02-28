"""Ingest sub-router -- delegates to ingest_helpers + ingest_videos sub-modules.

Keeps image upload, ComfyUI scan, IPAdapter refine, clear-stuck, and progress routes.
Video ingestion routes live in ingest_videos.py.
"""

import asyncio
import json
import logging
import random
import shutil
import urllib.request as _ur
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from packages.core.config import BASE_PATH, COMFYUI_URL, COMFYUI_OUTPUT_DIR
from packages.core.db import get_char_project_map, connect_direct
from packages.lora_training.dedup import is_duplicate, register_hash
from .ingest_helpers import (
    _ingest_progress,
    _classify_image,
    _save_frame_to_characters,
    _save_unclassified_frame,
    COMFYUI_INPUT_DIR,
    _build_ipadapter_workflow,
    # Re-export Pydantic models for backward compatibility
    YouTubeIngestRequest,
    YouTubeProjectIngestRequest,
    LocalVideoIngestRequest,
    MovieExtractRequest,
    ClipClassifyRequest,
    ClipClassifyLocalRequest,
)
from .ingest_videos import router as video_router

logger = logging.getLogger(__name__)
ingest_router = APIRouter()
ingest_router.include_router(video_router)


@ingest_router.get("/ingest/progress")
async def get_ingest_progress():
    """Poll current ingestion progress. Returns empty dict if no active job.

    Background tasks (movie-extract) store progress under named keys.
    This endpoint merges active job data to the top level for the frontend.
    """
    # Check for background task progress stored under named keys
    for key in ("clip-classify", "movie", "youtube-project", "local-video", "youtube"):
        if key in _ingest_progress and isinstance(_ingest_progress[key], dict):
            return _ingest_progress[key]
    return _ingest_progress


@ingest_router.post("/ingest/image")
async def ingest_image(file: UploadFile = File(...), character_slug: str = ""):
    """Upload a single image to a character's dataset. Converts to PNG and registers for approval."""
    if not character_slug:
        raise HTTPException(status_code=400, detail="character_slug is required")

    dataset_path = BASE_PATH / character_slug
    dataset_images = dataset_path / "images"
    dataset_images.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_name = f"upload_{character_slug}_{timestamp}.png"
    dest = dataset_images / dest_name

    content = await file.read()
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(content))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        img.save(dest, "PNG")
    except Exception:
        dest.write_bytes(content)

    # Dedup check: reject perceptual duplicates of existing dataset images
    if await asyncio.to_thread(is_duplicate, dest, character_slug):
        dest.unlink(missing_ok=True)
        return {"image": dest_name, "character": character_slug, "status": "duplicate"}

    matched, description = await _classify_image(dest)

    char_map = await get_char_project_map()
    db_info = char_map.get(character_slug, {})
    meta = {
        "seed": None,
        "full_prompt": None,
        "design_prompt": db_info.get("design_prompt", ""),
        "checkpoint_model": None,
        "source": "upload",
        "original_filename": file.filename,
        "project_name": db_info.get("project_name", ""),
        "character_name": db_info.get("name", character_slug),
        "generated_at": datetime.now().isoformat(),
        "vision_description": description[:300],
        "vision_matched": matched,
    }
    dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    caption = db_info.get("design_prompt", f"a portrait of {character_slug.replace('_', ' ')}")
    dest.with_suffix(".txt").write_text(caption)

    approval_file = dataset_path / "approval_status.json"
    approval_status = {}
    if approval_file.exists():
        try:
            approval_status = json.loads(approval_file.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    approval_status[dest_name] = "pending"
    approval_file.write_text(json.dumps(approval_status, indent=2))
    register_hash(dest, character_slug)

    return {
        "image": dest_name,
        "character": character_slug,
        "status": "pending",
        "vision_matched": matched,
        "vision_description": description[:200] if description else None,
    }


@ingest_router.post("/ingest/scan-comfyui")
async def scan_comfyui():
    """Scan ComfyUI output directory for new untracked images and match to characters."""
    comfyui_output = COMFYUI_OUTPUT_DIR
    if not comfyui_output.exists():
        raise HTTPException(status_code=500, detail="ComfyUI output directory not found")

    char_map = await get_char_project_map()

    existing = set()
    if BASE_PATH.exists():
        for char_dir in BASE_PATH.iterdir():
            if char_dir.is_dir():
                images_dir = char_dir / "images"
                if images_dir.exists():
                    existing.update(p.name for p in images_dir.glob("*.png"))

    new_images = 0
    duplicates = 0
    matched_chars = {}
    unmatched = []

    skipped_small = 0
    for png in sorted(comfyui_output.glob("*.png")):
        if png.name in existing:
            continue

        # Skip tiny images (thumbnails, test stubs) -- real training images are 50KB+
        try:
            if png.stat().st_size < 50_000:
                skipped_small += 1
                continue
        except OSError:
            continue

        matched_slug = None
        fn_lower = png.name.lower()
        for slug in char_map:
            if slug in fn_lower or slug.replace("_", "") in fn_lower:
                matched_slug = slug
                break

        vision_matched = []
        vision_description = ""
        if not matched_slug:
            vision_matched, vision_description = await _classify_image(
                png, allowed_slugs=list(char_map.keys())
            )
            if vision_matched:
                matched_slug = vision_matched[0]

        if matched_slug:
            # Save to all vision-matched slugs (multi-character), or just the filename-matched slug
            all_slugs = vision_matched if vision_matched else [matched_slug]
            for save_slug in all_slugs:
                if save_slug not in char_map:
                    continue
                if await asyncio.to_thread(is_duplicate, png, save_slug):
                    duplicates += 1
                    continue

                db_info = char_map[save_slug]
                dest_dir = BASE_PATH / save_slug / "images"
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / png.name
                if not dest.exists():
                    shutil.copy2(png, dest)
                    meta = {
                        "seed": None,
                        "source": "comfyui_scan",
                        "design_prompt": db_info.get("design_prompt") or "",
                        "project_name": db_info.get("project_name") or "",
                        "character_name": db_info.get("name") or save_slug,
                        "generated_at": datetime.now().isoformat(),
                        "vision_description": vision_description[:300] if vision_description else None,
                        "vision_matched": vision_matched if vision_matched else None,
                    }
                    dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
                    caption = db_info.get("design_prompt") or save_slug.replace("_", " ")
                    dest.with_suffix(".txt").write_text(caption)
                    from packages.lora_training.feedback import register_pending_image
                    register_pending_image(save_slug, png.name)
                    register_hash(dest, save_slug)
                    new_images += 1
                    matched_chars[save_slug] = matched_chars.get(save_slug, 0) + 1
        else:
            unmatched.append(png.name)

    return {
        "new_images": new_images,
        "duplicates_skipped": duplicates,
        "skipped_small": skipped_small,
        "matched": matched_chars,
        "unmatched_count": len(unmatched),
        "unmatched_samples": unmatched[:20],
    }


@ingest_router.post("/refine")
async def refine_image(body: dict):
    """Use an approved image as a style reference via IPAdapter to generate variants."""
    character_slug = body.get("character_slug")
    reference_image = body.get("reference_image")
    prompt_override = body.get("prompt_override")
    count = body.get("count", 3)
    weight = body.get("weight", 0.95)
    denoise = body.get("denoise", 0.30)

    if not character_slug or not reference_image:
        raise HTTPException(status_code=400, detail="character_slug and reference_image are required")

    ref_path = BASE_PATH / character_slug / "images" / reference_image
    if not ref_path.exists():
        raise HTTPException(status_code=404, detail="Reference image not found")

    # Copy reference image to ComfyUI input dir (LoadImage only reads from there)
    comfyui_ref_name = f"ref_{character_slug}_{reference_image}"
    comfyui_ref_path = COMFYUI_INPUT_DIR / comfyui_ref_name
    COMFYUI_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ref_path, comfyui_ref_path)

    char_map = await get_char_project_map()
    db_info = char_map.get(character_slug, {})

    prompt_text = prompt_override or db_info.get("design_prompt", "")
    negative_text = "worst quality, low quality, blurry, watermark, deformed"
    checkpoint = db_info.get("checkpoint_model", "realcartoonPixar_v12.safetensors")
    steps = db_info.get("steps") or 25
    cfg = db_info.get("cfg_scale") or 7.0
    width = db_info.get("width") or 768
    height = db_info.get("height") or 768

    results = []

    for i in range(count):
        seed = random.randint(1, 2**31)
        workflow = _build_ipadapter_workflow(
            prompt_text=prompt_text,
            negative_text=negative_text,
            checkpoint=checkpoint,
            ref_image_name=comfyui_ref_name,
            seed=seed,
            steps=steps,
            cfg=cfg,
            denoise=denoise,
            weight=weight,
            width=width,
            height=height,
            filename_prefix=f"refine_{character_slug}",
        )

        try:
            payload = json.dumps({"prompt": workflow}).encode()
            req = _ur.Request(
                f"{COMFYUI_URL}/prompt", data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = _ur.urlopen(req)
            prompt_id = json.loads(resp.read()).get("prompt_id", "")
            results.append({"prompt_id": prompt_id, "seed": seed})
            logger.info(f"IPAdapter refine queued: {character_slug} seed={seed} prompt_id={prompt_id}")
        except Exception as e:
            logger.error(f"IPAdapter refine failed: {e}")
            results.append({"error": str(e)})

    return {
        "message": f"Queued {count} IPAdapter refinement(s) for {character_slug}",
        "reference_image": reference_image,
        "results": results,
    }


@ingest_router.post("/generate/clear-stuck")
async def clear_stuck_generations():
    """Clear stuck ComfyUI generation jobs."""
    try:
        req = _ur.Request(f"{COMFYUI_URL}/queue")
        resp = _ur.urlopen(req, timeout=10)
        queue_data = json.loads(resp.read())

        running = queue_data.get("queue_running", [])
        pending = queue_data.get("queue_pending", [])

        cancelled = 0
        for job in pending:
            try:
                cancel_payload = json.dumps({"delete": [job[1]]}).encode()
                cancel_req = _ur.Request(
                    f"{COMFYUI_URL}/queue",
                    data=cancel_payload,
                    headers={"Content-Type": "application/json"},
                )
                _ur.urlopen(cancel_req, timeout=5)
                cancelled += 1
            except Exception:
                pass

        return {
            "message": f"Cleared {cancelled} pending jobs",
            "running": len(running),
            "pending_before": len(pending),
            "cancelled": cancelled,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to communicate with ComfyUI: {e}")


@ingest_router.get("/ingest/clips/{character_slug}")
async def list_character_clips(character_slug: str, limit: int = 50):
    """List extracted video clips for a character from the character_clips table."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch(
            "SELECT id, character_slug, clip_path, source_video, timestamp_seconds, "
            "similarity, duration_seconds, frame_index, created_at "
            "FROM character_clips WHERE character_slug = $1 "
            "ORDER BY similarity DESC NULLS LAST LIMIT $2",
            character_slug, limit,
        )
        clips = []
        for r in rows:
            clip_path = r["clip_path"]
            clips.append({
                "id": r["id"],
                "character_slug": r["character_slug"],
                "clip_path": clip_path,
                "exists": Path(clip_path).exists() if clip_path else False,
                "source_video": r["source_video"],
                "timestamp_seconds": r["timestamp_seconds"],
                "similarity": r["similarity"],
                "duration_seconds": r["duration_seconds"],
                "frame_index": r["frame_index"],
                "created_at": str(r["created_at"]) if r["created_at"] else None,
            })
        return {"character_slug": character_slug, "clips": clips, "total": len(clips)}
    finally:
        await conn.close()


class ClipExtractRequest(BaseModel):
    video_path: str
    character_slug: str
    project_name: str
    max_frames: int = 100
    clip_duration: float = 2.0


@ingest_router.post("/ingest/clips/extract")
async def extract_clips_for_character(body: ClipExtractRequest):
    """Extract CLIP-classified video clips for a character and persist to DB.

    Combines frame extraction + CLIP classification + clip extraction + DB persistence.
    Runs as a background task — poll GET /ingest/progress for status.
    """
    video_path = Path(body.video_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video not found: {body.video_path}")

    existing = _ingest_progress.get("clip-classify")
    if isinstance(existing, dict) and existing.get("active"):
        raise HTTPException(status_code=409, detail="A CLIP classification is already running")

    char_map = await get_char_project_map()
    project_slugs = [
        slug for slug, info in char_map.items()
        if info.get("project_name") == body.project_name
    ]
    if not project_slugs:
        raise HTTPException(status_code=404, detail=f"No characters for project '{body.project_name}'")

    # Delegate to the existing CLIP classify pipeline with clip extraction enabled
    from .ingest_videos import _clip_classify_task
    req = ClipClassifyRequest(
        path=body.video_path,
        project_name=body.project_name,
        target_character=body.character_slug,
        max_frames=body.max_frames,
        extract_clips=True,
        clip_duration=body.clip_duration,
    )
    asyncio.create_task(_clip_classify_task(req, char_map, project_slugs, is_url=False))

    return {
        "status": "started",
        "character_slug": body.character_slug,
        "project_name": body.project_name,
        "video_path": body.video_path,
        "message": "Clip extraction started. Poll GET /api/training/ingest/progress for status.",
    }
