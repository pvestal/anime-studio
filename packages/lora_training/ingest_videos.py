"""Ingest video sub-router — video upload, YouTube download, movie extraction, CLIP classification."""

import asyncio
import json
import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

from packages.core.config import BASE_PATH, MOVIES_DIR
from packages.core.db import get_char_project_map
from packages.lora_training.dedup import is_duplicate
from packages.lora_training.frame_extraction import extract_smart_frames, extract_frames_with_timestamps, download_video
from .ingest_helpers import (
    _ingest_progress,
    _UNCLASSIFIED_SLUG,
    _save_unclassified_frame,
    _classify_image,
    _save_frame_to_characters,
    YouTubeIngestRequest,
    YouTubeProjectIngestRequest,
    LocalVideoIngestRequest,
    MovieExtractRequest,
    ClipClassifyRequest,
    ClipClassifyLocalRequest,
)

from packages.core.db import connect_direct

logger = logging.getLogger(__name__)
router = APIRouter()

import re


async def _persist_clips_to_db(clips: list[dict], source_video: str | None = None):
    """Persist extracted video clips to the character_clips table.

    Each clip dict has: path, timestamp, similarity, character, frame_index.
    Uses ON CONFLICT to update similarity if a clip at the same path already exists.
    """
    if not clips:
        return 0
    conn = await connect_direct()
    try:
        inserted = 0
        for clip in clips:
            try:
                await conn.execute("""
                    INSERT INTO character_clips
                        (character_slug, clip_path, source_video, timestamp_seconds,
                         similarity, frame_index)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (clip_path) DO UPDATE SET
                        similarity = EXCLUDED.similarity,
                        source_video = EXCLUDED.source_video
                """,
                    clip["character"],
                    clip["path"],
                    source_video or clip.get("source_video"),
                    clip.get("timestamp"),
                    clip.get("similarity"),
                    clip.get("frame_index"),
                )
                inserted += 1
            except Exception as e:
                logger.debug(f"Failed to persist clip {clip.get('path')}: {e}")
        logger.info(f"Persisted {inserted}/{len(clips)} clips to character_clips table")
        return inserted
    finally:
        await conn.close()


@router.post("/ingest/video")
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


@router.post("/ingest/youtube")
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


@router.post("/ingest/youtube-project")
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


@router.post("/ingest/local-video")
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


@router.post("/ingest/movie-upload")
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


@router.get("/ingest/movies")
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


@router.post("/ingest/movie-extract")
async def extract_movie(req: MovieExtractRequest):
    """Extract frames from an uploaded movie and classify against all project characters.

    Runs as a background task -- poll GET /ingest/progress for status.
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
            f"Movie extraction complete: {video_path.name} -> "
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


@router.post("/ingest/clip-classify")
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

        # Persist extracted clips to DB for V2V pipeline
        clips_persisted = 0
        extracted_clips = result.get("clips", [])
        if extracted_clips:
            clips_persisted = await _persist_clips_to_db(extracted_clips, source_video=req.path)

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
            "clips_extracted": len(extracted_clips),
            "clips_persisted": clips_persisted,
            "reference_characters": result["reference_characters"],
            "message": (
                f"Done. {result['total_matched']} matched, "
                f"{sum(per_char_saved.values())} saved, {duplicates} dupes, "
                f"{clips_persisted} clips persisted."
            ),
        }
        logger.info(
            f"CLIP classify complete: {result['total_matched']} matched, "
            f"{sum(per_char_saved.values())} saved, {clips_persisted} clips persisted"
        )

    except Exception as e:
        logger.error(f"CLIP classification failed: {e}", exc_info=True)
        _ingest_progress["clip-classify"] = {
            "active": False, "stage": "error",
            "message": f"Failed: {e}",
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@router.post("/ingest/clip-classify-local")
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

        # Persist extracted clips to DB for V2V pipeline
        clips_persisted = 0
        extracted_clips = result.get("clips", [])
        if extracted_clips:
            clips_persisted = await _persist_clips_to_db(
                extracted_clips, source_video=req.source_video,
            )

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
            "clips_extracted": len(extracted_clips),
            "clips_persisted": clips_persisted,
            "reference_characters": result["reference_characters"],
            "message": (
                f"Done. {result['total_matched']} matched, "
                f"{sum(per_char_saved.values())} saved, {duplicates} dupes, "
                f"{clips_persisted} clips persisted."
            ),
        }

    except Exception as e:
        logger.error(f"CLIP local classification failed: {e}", exc_info=True)
        _ingest_progress["clip-classify"] = {
            "active": False, "stage": "error",
            "message": f"Failed: {e}",
        }


@router.post("/ingest/rebuild-references")
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
