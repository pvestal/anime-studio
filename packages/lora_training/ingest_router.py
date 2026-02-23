"""Ingest sub-router — image upload, video upload, ComfyUI scan, YouTube, IPAdapter refine, progress."""

import asyncio
import json
import logging
import re
import shutil
import subprocess
import tempfile
import urllib.request as _ur
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from packages.core.config import BASE_PATH, COMFYUI_URL, COMFYUI_OUTPUT_DIR, MOVIES_DIR
from packages.core.comfyui import build_ipadapter_workflow
from packages.core.db import get_char_project_map
from packages.lora_training.dedup import is_duplicate, register_hash
from packages.lora_training.feedback import register_pending_image
from packages.lora_training.frame_extraction import extract_smart_frames, extract_frames_with_timestamps, download_video

logger = logging.getLogger(__name__)
ingest_router = APIRouter()

# In-memory progress for active ingestion jobs
_ingest_progress: dict = {}

# Slug used for frames that don't match any known character
_UNCLASSIFIED_SLUG = "_unclassified"


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
    """Classify an image (blocking). Called via asyncio.to_thread()."""
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


@ingest_router.post("/ingest/video")
async def ingest_video(file: UploadFile = File(...), character_slug: str = "",
                       max_frames: int = 50):
    """Upload a video, extract smart frames, classify, dedup, and add to a character's dataset."""
    if not character_slug:
        raise HTTPException(status_code=400, detail="character_slug is required")

    dataset_images = BASE_PATH / character_slug / "images"
    dataset_images.mkdir(parents=True, exist_ok=True)

    tmpdir = tempfile.mkdtemp(prefix="lora_video_")
    tmp_video = Path(tmpdir) / (file.filename or "upload.mp4")

    try:
        with open(tmp_video, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)

        staged_frames = await asyncio.to_thread(extract_smart_frames, tmp_video, max_frames, tmpdir)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        char_map = await get_char_project_map()
        db_info = char_map.get(character_slug, {})

        copied = 0
        unclassified = 0
        duplicates = 0
        per_char: dict[str, int] = {}
        for i, frame in enumerate(staged_frames):
            frame_num = i + 1
            matched, description = await _classify_image(frame)
            # Ensure target character is included if vision matched it
            if not matched or character_slug not in matched:
                # If target wasn't matched at all, save as unclassified
                if character_slug not in matched:
                    saved = await asyncio.to_thread(
                        _save_unclassified_frame, frame,
                        project_name=db_info.get("project_name", ""),
                        source="video_upload",
                        source_url=None,
                        frame_number=frame_num,
                        description=description,
                        matched=matched,
                        timestamp=timestamp,
                    )
                    if saved:
                        unclassified += 1
                    else:
                        duplicates += 1
                    continue

            saved_slugs, dup_count = await _save_frame_to_characters(
                frame, matched,
                char_map=char_map,
                source="video_upload",
                source_url=None,
                frame_number=frame_num,
                timestamp=timestamp,
                project_name=db_info.get("project_name", ""),
                description=description,
                prefix="vid",
            )
            duplicates += dup_count
            for slug in saved_slugs:
                per_char[slug] = per_char.get(slug, 0) + 1
            if character_slug in saved_slugs:
                copied += 1

        return {
            "frames_extracted": len(staged_frames),
            "frames_matched": copied,
            "frames_unclassified": unclassified,
            "frames_duplicate": duplicates,
            "character": character_slug,
            "per_character": per_char,
            "status": "pending_approval",
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


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

        # Skip tiny images (thumbnails, test stubs) — real training images are 50KB+
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


class YouTubeIngestRequest(BaseModel):
    url: str
    character_slug: str
    max_frames: int = 50


class YouTubeProjectIngestRequest(BaseModel):
    url: str
    project_name: str
    max_frames: int = 50


@ingest_router.post("/ingest/youtube")
async def ingest_youtube(req: YouTubeIngestRequest):
    """Download a YouTube video, extract smart frames, classify, dedup, and add to a character's dataset."""
    dataset_images = BASE_PATH / req.character_slug / "images"
    dataset_images.mkdir(parents=True, exist_ok=True)

    tmpdir = tempfile.mkdtemp(prefix="lora_yt_")
    try:
        _ingest_progress["youtube"] = {"status": "downloading", "character": req.character_slug}
        tmp_video = await asyncio.to_thread(download_video, req.url, tmpdir)

        _ingest_progress["youtube"] = {"status": "extracting", "character": req.character_slug}
        staged_frames = await asyncio.to_thread(extract_smart_frames, tmp_video, req.max_frames, tmpdir)

        char_map = await get_char_project_map()
        db_info = char_map.get(req.character_slug, {})
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        copied = 0
        unclassified = 0
        duplicates = 0
        per_char: dict[str, int] = {}
        for i, frame in enumerate(staged_frames):
            _ingest_progress["youtube"] = {
                "status": "classifying",
                "character": req.character_slug,
                "frame": i + 1,
                "total": len(staged_frames),
            }
            matched, description = await _classify_image(frame)
            if req.character_slug not in matched:
                saved = await asyncio.to_thread(
                    _save_unclassified_frame, frame,
                    project_name=db_info.get("project_name", ""),
                    source="youtube",
                    source_url=req.url,
                    frame_number=i + 1,
                    description=description,
                    matched=matched,
                    timestamp=timestamp,
                )
                if saved:
                    unclassified += 1
                else:
                    duplicates += 1
                continue

            saved_slugs, dup_count = await _save_frame_to_characters(
                frame, matched,
                char_map=char_map,
                source="youtube",
                source_url=req.url,
                frame_number=i + 1,
                timestamp=timestamp,
                project_name=db_info.get("project_name", ""),
                description=description,
                prefix="yt",
            )
            duplicates += dup_count
            for slug in saved_slugs:
                per_char[slug] = per_char.get(slug, 0) + 1
            if req.character_slug in saved_slugs:
                copied += 1

        return {
            "frames_extracted": len(staged_frames),
            "frames_matched": copied,
            "frames_unclassified": unclassified,
            "frames_duplicate": duplicates,
            "character": req.character_slug,
            "per_character": per_char,
            "status": "pending_approval",
        }
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        _ingest_progress.pop("youtube", None)
        shutil.rmtree(tmpdir, ignore_errors=True)


@ingest_router.post("/ingest/youtube-project")
async def ingest_youtube_project(req: YouTubeProjectIngestRequest):
    """Download a YouTube video once, classify each frame against all project characters."""
    char_map = await get_char_project_map()
    project_slugs = [
        slug for slug, info in char_map.items()
        if info.get("project_name") == req.project_name
    ]
    if not project_slugs:
        raise HTTPException(status_code=404, detail=f"No characters found for project '{req.project_name}'")

    tmpdir = tempfile.mkdtemp(prefix="lora_yt_proj_")
    try:
        _ingest_progress["youtube-project"] = {"status": "downloading", "project": req.project_name}
        tmp_video = await asyncio.to_thread(download_video, req.url, tmpdir)

        _ingest_progress["youtube-project"] = {"status": "extracting", "project": req.project_name}
        staged_frames = await asyncio.to_thread(extract_smart_frames, tmp_video, req.max_frames, tmpdir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        per_char: dict[str, int] = {}
        skipped = 0
        unclassified = 0
        duplicates = 0

        for i, frame in enumerate(staged_frames):
            _ingest_progress["youtube-project"] = {
                "status": "classifying",
                "project": req.project_name,
                "frame": i + 1,
                "total": len(staged_frames),
                "matched_so_far": dict(per_char),
            }
            matched, description = await _classify_image(
                frame, allowed_slugs=project_slugs
            )
            if not matched:
                saved = await asyncio.to_thread(
                    _save_unclassified_frame, frame,
                    project_name=req.project_name,
                    source="youtube_project",
                    source_url=req.url,
                    frame_number=i + 1,
                    description=description,
                    matched=matched,
                    timestamp=timestamp,
                )
                if saved:
                    unclassified += 1
                else:
                    duplicates += 1
                continue

            saved_slugs, dup_count = await _save_frame_to_characters(
                frame, matched,
                char_map=char_map,
                source="youtube_project",
                source_url=req.url,
                frame_number=i + 1,
                timestamp=timestamp,
                project_name=req.project_name,
                description=description,
                prefix="yt",
            )
            duplicates += dup_count
            for slug in saved_slugs:
                per_char[slug] = per_char.get(slug, 0) + 1

        return {
            "frames_extracted": len(staged_frames),
            "frames_matched": sum(per_char.values()),
            "frames_unclassified": unclassified,
            "frames_duplicate": duplicates,
            "per_character": per_char,
            "project": req.project_name,
            "status": "pending_approval",
        }
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        _ingest_progress.pop("youtube-project", None)
        shutil.rmtree(tmpdir, ignore_errors=True)


class LocalVideoIngestRequest(BaseModel):
    path: str
    project_name: str
    max_frames: int = 200
    fps: float = 4


@ingest_router.post("/ingest/local-video")
async def ingest_local_video(req: LocalVideoIngestRequest):
    """Extract frames from a video file already on the server and classify against project characters."""
    video_path = Path(req.path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video file not found: {req.path}")

    char_map = await get_char_project_map()
    project_slugs = [
        slug for slug, info in char_map.items()
        if info.get("project_name") == req.project_name
    ]
    if not project_slugs:
        raise HTTPException(status_code=404, detail=f"No characters found for project '{req.project_name}'")

    file_size_mb = round(video_path.stat().st_size / (1024 * 1024), 1)

    tmpdir = tempfile.mkdtemp(prefix="lora_local_vid_")
    try:
        _ingest_progress["local-video"] = {"status": "extracting", "project": req.project_name, "file_size_mb": file_size_mb}
        staged_frames = await asyncio.to_thread(extract_smart_frames, video_path, req.max_frames, tmpdir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        per_char: dict[str, int] = {}
        unclassified = 0
        duplicates = 0

        for i, frame in enumerate(staged_frames):
            _ingest_progress["local-video"] = {
                "status": "classifying",
                "project": req.project_name,
                "frame": i + 1,
                "total": len(staged_frames),
                "matched_so_far": dict(per_char),
            }
            matched, description = await _classify_image(
                frame, allowed_slugs=project_slugs
            )
            if not matched:
                saved = await asyncio.to_thread(
                    _save_unclassified_frame, frame,
                    project_name=req.project_name,
                    source="local_video",
                    source_url=req.path,
                    frame_number=i + 1,
                    description=description,
                    matched=matched,
                    timestamp=timestamp,
                )
                if saved:
                    unclassified += 1
                else:
                    duplicates += 1
                continue

            saved_slugs, dup_count = await _save_frame_to_characters(
                frame, matched,
                char_map=char_map,
                source="local_video",
                source_url=req.path,
                frame_number=i + 1,
                timestamp=timestamp,
                project_name=req.project_name,
                description=description,
                prefix="vid",
            )
            duplicates += dup_count
            for slug in saved_slugs:
                per_char[slug] = per_char.get(slug, 0) + 1

        return {
            "frames_extracted": len(staged_frames),
            "frames_matched": sum(per_char.values()),
            "frames_unclassified": unclassified,
            "frames_duplicate": duplicates,
            "per_character": per_char,
            "project": req.project_name,
            "file_size_mb": file_size_mb,
            "status": "pending_approval",
        }
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        _ingest_progress.pop("local-video", None)
        shutil.rmtree(tmpdir, ignore_errors=True)


class MovieExtractRequest(BaseModel):
    path: str
    project_name: str
    max_frames: int = 500
    fps: float = 4


@ingest_router.post("/ingest/movie-upload")
async def upload_movie(file: UploadFile = File(...), project_name: str = ""):
    """Upload a movie file (chunked) to persistent storage for later frame extraction."""
    if not project_name:
        raise HTTPException(status_code=400, detail="project_name is required")

    # Sanitize filename
    original = file.filename or "movie.mp4"
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', original)
    dest = MOVIES_DIR / safe_name

    # Chunked write (1MB chunks) to persistent storage
    size = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
            size += len(chunk)

    size_mb = round(size / (1024 * 1024), 1)
    logger.info(f"Movie uploaded: {safe_name} ({size_mb} MB) for project '{project_name}'")

    return {
        "path": str(dest),
        "filename": safe_name,
        "size_mb": size_mb,
        "project_name": project_name,
        "status": "uploaded",
    }


@ingest_router.get("/ingest/movies")
async def list_movies():
    """List all uploaded movies in the _movies directory."""
    movies = []
    if MOVIES_DIR.exists():
        for f in sorted(MOVIES_DIR.iterdir()):
            if f.is_file() and f.suffix.lower() in (".mp4", ".mkv", ".avi", ".mov", ".webm"):
                movies.append({
                    "filename": f.name,
                    "path": str(f),
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                })
    return {"movies": movies}


@ingest_router.post("/ingest/movie-extract")
async def extract_movie(req: MovieExtractRequest):
    """Extract frames from an uploaded movie and classify against all project characters.

    Runs as a background task — poll GET /ingest/progress for status.
    """
    # Check if an extraction is already running
    existing = _ingest_progress.get("movie")
    if isinstance(existing, dict) and existing.get("active"):
        raise HTTPException(status_code=409, detail="A movie extraction is already running")

    video_path = Path(req.path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Movie file not found: {req.path}")

    char_map = await get_char_project_map()
    project_slugs = [
        slug for slug, info in char_map.items()
        if info.get("project_name") == req.project_name
    ]
    if not project_slugs:
        raise HTTPException(status_code=404, detail=f"No characters found for project '{req.project_name}'")

    file_size_mb = round(video_path.stat().st_size / (1024 * 1024), 1)

    # Launch as background task so the HTTP response returns immediately
    asyncio.create_task(_extract_movie_task(video_path, req, char_map, project_slugs, file_size_mb))

    return {
        "status": "started",
        "file": video_path.name,
        "file_size_mb": file_size_mb,
        "project": req.project_name,
        "characters": len(project_slugs),
        "message": "Extraction started. Poll GET /api/training/ingest/progress for status.",
    }


async def _extract_movie_task(
    video_path: Path,
    req: MovieExtractRequest,
    char_map: dict,
    project_slugs: list[str],
    file_size_mb: float,
):
    """Background task: extract frames from movie, classify, register."""
    tmpdir = tempfile.mkdtemp(prefix="lora_movie_")
    try:
        _ingest_progress["movie"] = {
            "active": True,
            "stage": "extracting",
            "project": req.project_name,
            "file": video_path.name,
            "file_size_mb": file_size_mb,
            "message": f"Extracting frames from {video_path.name} ({file_size_mb} MB)...",
        }

        staged_frames = await asyncio.to_thread(
            extract_smart_frames, video_path, req.max_frames, tmpdir
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        per_char: dict[str, int] = {}
        unclassified = 0
        duplicates = 0

        for i, frame in enumerate(staged_frames):
            _ingest_progress["movie"] = {
                "active": True,
                "stage": "classifying",
                "project": req.project_name,
                "file": video_path.name,
                "frame": i + 1,
                "total": len(staged_frames),
                "frame_current": i + 1,
                "frame_total": len(staged_frames),
                "matched_so_far": dict(per_char),
                "per_character": dict(per_char),
                "duplicates": duplicates,
                "message": f"Classifying frame {i + 1}/{len(staged_frames)}...",
            }

            matched, description = await _classify_image(
                frame, allowed_slugs=project_slugs
            )
            if not matched:
                saved = await asyncio.to_thread(
                    _save_unclassified_frame, frame,
                    project_name=req.project_name,
                    source="movie_upload",
                    source_url=str(video_path),
                    frame_number=i + 1,
                    description=description,
                    matched=matched,
                    timestamp=timestamp,
                )
                if saved:
                    unclassified += 1
                else:
                    duplicates += 1
                continue

            saved_slugs, dup_count = await _save_frame_to_characters(
                frame, matched,
                char_map=char_map,
                source="movie_upload",
                source_url=str(video_path),
                frame_number=i + 1,
                timestamp=timestamp,
                project_name=req.project_name,
                description=description,
                prefix="movie",
            )
            duplicates += dup_count
            for slug in saved_slugs:
                per_char[slug] = per_char.get(slug, 0) + 1

        _ingest_progress["movie"] = {
            "active": False,
            "stage": "complete",
            "project": req.project_name,
            "file": video_path.name,
            "frame_total": len(staged_frames),
            "frame_current": len(staged_frames),
            "per_character": per_char,
            "duplicates": duplicates,
            "skipped": unclassified,
            "message": f"Done. {sum(per_char.values())} frames matched, {unclassified} unclassified, {duplicates} duplicates.",
        }
        logger.info(
            f"Movie extraction complete: {video_path.name} → "
            f"{sum(per_char.values())} matched, {unclassified} unclassified, {duplicates} dupes"
        )
    except Exception as e:
        logger.error(f"Movie extraction failed: {e}", exc_info=True)
        _ingest_progress["movie"] = {
            "active": False,
            "stage": "error",
            "message": f"Extraction failed: {e}",
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


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


@ingest_router.post("/ingest/clip-classify")
async def clip_classify_video(req: ClipClassifyRequest):
    """Classify characters in a video using CLIP visual similarity.

    Runs as background task. Supports local paths and YouTube URLs.
    Poll GET /ingest/progress for status (key: clip-classify).
    """
    existing = _ingest_progress.get("clip-classify")
    if isinstance(existing, dict) and existing.get("active"):
        raise HTTPException(status_code=409, detail="A CLIP classification is already running")

    # Determine video path
    is_url = req.path.startswith("http://") or req.path.startswith("https://")
    if not is_url:
        video_path = Path(req.path)
        if not video_path.exists():
            raise HTTPException(status_code=404, detail=f"Video not found: {req.path}")

    char_map = await get_char_project_map()
    project_slugs = [
        slug for slug, info in char_map.items()
        if info.get("project_name") == req.project_name
    ]
    if not project_slugs:
        raise HTTPException(status_code=404, detail=f"No characters for project '{req.project_name}'")

    asyncio.create_task(_clip_classify_task(req, char_map, project_slugs, is_url))

    return {
        "status": "started",
        "project": req.project_name,
        "target_character": req.target_character,
        "characters": len(project_slugs),
        "message": "CLIP classification started. Poll GET /api/training/ingest/progress for status.",
    }


async def _clip_classify_task(
    req: ClipClassifyRequest,
    char_map: dict,
    project_slugs: list[str],
    is_url: bool,
):
    """Background task: CLIP-based video frame classification."""
    tmpdir = tempfile.mkdtemp(prefix="clip_classify_")
    try:
        def _update_progress(phase, detail=""):
            _ingest_progress["clip-classify"] = {
                "active": True,
                "stage": phase,
                "project": req.project_name,
                "target": req.target_character,
                "detail": detail,
            }

        # Phase 1: Download if URL
        video_path = None
        if is_url:
            _update_progress("downloading", req.path)
            video_path = await asyncio.to_thread(download_video, req.path, tmpdir)
        else:
            video_path = Path(req.path)

        # Phase 2: Extract frames with timestamps
        _update_progress("extracting", f"max_frames={req.max_frames}")
        frame_data = await asyncio.to_thread(
            extract_frames_with_timestamps, video_path, req.max_frames, tmpdir
        )

        if not frame_data:
            _ingest_progress["clip-classify"] = {
                "active": False, "stage": "error",
                "message": "No frames extracted",
            }
            return

        frame_paths = [d["path"] for d in frame_data]
        frame_timestamps = [d["timestamp"] for d in frame_data]

        # Phase 3-5: Run CLIP pipeline
        _update_progress("classifying", f"{len(frame_paths)} frames")
        from packages.visual_pipeline.clip_classifier import run_clip_pipeline

        result = await asyncio.to_thread(
            run_clip_pipeline,
            frame_paths=frame_paths,
            project_name=req.project_name,
            character_slugs=project_slugs,
            target_slug=req.target_character,
            video_path=video_path if req.extract_clips else None,
            clip_duration=req.clip_duration,
            extract_clips=req.extract_clips,
            frame_timestamps=frame_timestamps,
            progress_callback=lambda phase, detail: _update_progress(phase, detail),
        )

        if "error" in result:
            _ingest_progress["clip-classify"] = {
                "active": False, "stage": "error",
                "message": result["error"],
            }
            return

        # Phase 6: Save matched frames to character datasets
        _update_progress("saving", f"{result['total_matched']} matched frames")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        per_char_saved: dict[str, int] = {}
        duplicates = 0

        for cls in result["classifications"]:
            slug = cls.get("matched_slug")
            if not slug:
                continue

            frame_path = Path(cls["frame_path"])
            if not frame_path.exists():
                continue

            saved_slugs, dup_count = await _save_frame_to_characters(
                frame_path, [slug],
                char_map=char_map,
                source="clip_classify",
                source_url=req.path,
                frame_number=cls.get("frame_index", 0) + 1,
                timestamp=timestamp,
                project_name=req.project_name,
                description=json.dumps({
                    "similarity": cls.get("similarity", 0),
                    "verified": cls.get("verified", False),
                }),
                prefix="clip",
            )
            duplicates += dup_count
            for s in saved_slugs:
                per_char_saved[s] = per_char_saved.get(s, 0) + 1

        _ingest_progress["clip-classify"] = {
            "active": False,
            "stage": "complete",
            "project": req.project_name,
            "target": req.target_character,
            "total_frames": result["total_frames"],
            "total_matched": result["total_matched"],
            "per_character": result["per_character"],
            "per_character_saved": per_char_saved,
            "duplicates": duplicates,
            "clips_extracted": len(result.get("clips", [])),
            "reference_characters": result["reference_characters"],
            "message": (
                f"Done. {result['total_matched']} matched, "
                f"{sum(per_char_saved.values())} saved, {duplicates} dupes."
            ),
        }
        logger.info(
            f"CLIP classify complete: {result['total_matched']} matched, "
            f"{sum(per_char_saved.values())} saved"
        )

    except Exception as e:
        logger.error(f"CLIP classification failed: {e}", exc_info=True)
        _ingest_progress["clip-classify"] = {
            "active": False, "stage": "error",
            "message": f"Failed: {e}",
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@ingest_router.post("/ingest/clip-classify-local")
async def clip_classify_local(req: ClipClassifyLocalRequest):
    """Classify pre-extracted frames using CLIP visual similarity.

    For directories of frames already on disk (e.g. /tmp/yoshi_frames/).
    Runs as background task.
    """
    frames_dir = Path(req.frames_dir)
    if not frames_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory not found: {req.frames_dir}")

    char_map = await get_char_project_map()
    project_slugs = [
        slug for slug, info in char_map.items()
        if info.get("project_name") == req.project_name
    ]
    if not project_slugs:
        raise HTTPException(status_code=404, detail=f"No characters for project '{req.project_name}'")

    # Gather frame files
    frame_paths = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        frame_paths.extend(sorted(frames_dir.glob(ext)))
    if not frame_paths:
        raise HTTPException(status_code=400, detail=f"No image files in {req.frames_dir}")

    asyncio.create_task(
        _clip_classify_local_task(req, frame_paths, char_map, project_slugs)
    )

    return {
        "status": "started",
        "frames": len(frame_paths),
        "project": req.project_name,
        "target_character": req.target_character,
        "message": "CLIP local classification started. Poll GET /api/training/ingest/progress for status.",
    }


async def _clip_classify_local_task(
    req: ClipClassifyLocalRequest,
    frame_paths: list[Path],
    char_map: dict,
    project_slugs: list[str],
):
    """Background: classify local frames with CLIP."""
    try:
        def _update_progress(phase, detail=""):
            _ingest_progress["clip-classify"] = {
                "active": True,
                "stage": phase,
                "project": req.project_name,
                "target": req.target_character,
                "detail": detail,
                "frames_total": len(frame_paths),
            }

        _update_progress("classifying", f"{len(frame_paths)} frames")
        from packages.visual_pipeline.clip_classifier import run_clip_pipeline

        result = await asyncio.to_thread(
            run_clip_pipeline,
            frame_paths=frame_paths,
            project_name=req.project_name,
            character_slugs=project_slugs,
            target_slug=req.target_character,
            video_path=Path(req.source_video) if req.source_video else None,
            extract_clips=bool(req.source_video),
            progress_callback=lambda phase, detail: _update_progress(phase, detail),
        )

        if "error" in result:
            _ingest_progress["clip-classify"] = {
                "active": False, "stage": "error",
                "message": result["error"],
            }
            return

        # Save matched frames
        _update_progress("saving", f"{result['total_matched']} matched frames")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        per_char_saved: dict[str, int] = {}
        duplicates = 0

        for cls in result["classifications"]:
            slug = cls.get("matched_slug")
            if not slug:
                continue
            frame_path = Path(cls["frame_path"])
            if not frame_path.exists():
                continue

            saved_slugs, dup_count = await _save_frame_to_characters(
                frame_path, [slug],
                char_map=char_map,
                source="clip_classify_local",
                source_url=req.frames_dir,
                frame_number=cls.get("frame_index", 0) + 1,
                timestamp=timestamp,
                project_name=req.project_name,
                description=json.dumps({
                    "similarity": cls.get("similarity", 0),
                    "verified": cls.get("verified", False),
                }),
                prefix="clip",
            )
            duplicates += dup_count
            for s in saved_slugs:
                per_char_saved[s] = per_char_saved.get(s, 0) + 1

        _ingest_progress["clip-classify"] = {
            "active": False,
            "stage": "complete",
            "project": req.project_name,
            "target": req.target_character,
            "total_frames": result["total_frames"],
            "total_matched": result["total_matched"],
            "per_character": result["per_character"],
            "per_character_saved": per_char_saved,
            "duplicates": duplicates,
            "reference_characters": result["reference_characters"],
            "message": (
                f"Done. {result['total_matched']} matched, "
                f"{sum(per_char_saved.values())} saved, {duplicates} dupes."
            ),
        }

    except Exception as e:
        logger.error(f"CLIP local classification failed: {e}", exc_info=True)
        _ingest_progress["clip-classify"] = {
            "active": False, "stage": "error",
            "message": f"Failed: {e}",
        }


@ingest_router.post("/ingest/rebuild-references")
async def rebuild_references(project_name: str):
    """Force-rebuild CLIP reference embeddings for a project.

    Call this after adding new reference images to character datasets.
    """
    from packages.visual_pipeline.clip_classifier import build_reference_embeddings

    # Get project slugs from DB (async) so we don't rely on sync cache
    char_map = await get_char_project_map()
    project_slugs = [
        slug for slug, info in char_map.items()
        if info.get("project_name") == project_name
    ]
    if not project_slugs:
        raise HTTPException(status_code=404, detail=f"No characters for project '{project_name}'")

    try:
        refs = await asyncio.to_thread(
            build_reference_embeddings, project_name, project_slugs, True,
        )
        return {
            "status": "rebuilt",
            "project": project_name,
            "characters": {slug: emb.shape[0] for slug, emb in refs.items()},
            "total_references": sum(emb.shape[0] for emb in refs.values()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebuild failed: {e}")


COMFYUI_INPUT_DIR = Path("/opt/ComfyUI/input")


_build_ipadapter_workflow = build_ipadapter_workflow  # local alias for existing call sites


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

    import random
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
