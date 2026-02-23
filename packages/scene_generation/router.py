"""Scene generation CRUD and generation endpoints."""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from packages.core.config import BASE_PATH, COMFYUI_OUTPUT_DIR
from packages.core.db import connect_direct, get_char_project_map, log_model_change
from packages.core.audit import log_decision, log_generation, update_generation_quality
from packages.core.models import (
    SceneCreateRequest, ShotCreateRequest, ShotUpdateRequest, SceneUpdateRequest,
    SceneAudioRequest, VideoCompareRequest,
)
from .builder import (
    SCENE_OUTPUT_DIR, _scene_generation_tasks,
    extract_last_frame, concat_videos, copy_to_comfyui_input,
    poll_comfyui_completion, generate_scene,
    download_preview, overlay_audio, apply_scene_audio,
    _quality_gate_check,
)
from .framepack import (
    build_framepack_workflow, _submit_comfyui_workflow,
    router as framepack_router,
    MOTION_PRESETS,
)
from .ltx_video import (
    build_ltx_workflow,
    _submit_comfyui_workflow as _submit_ltx_workflow,
    router as ltx_router,
)
from .wan_video import (
    build_wan_t2v_workflow,
    router as wan_router,
)

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(framepack_router)
router.include_router(ltx_router)
router.include_router(wan_router)

# --- Scene Builder: CRUD Endpoints ---

@router.get("/scenes")
async def list_scenes(project_id: int):
    """List scenes for a project."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT id, project_id, title, description, location, time_of_day,
                   weather, mood, generation_status, target_duration_seconds,
                   actual_duration_seconds, total_shots, completed_shots,
                   final_video_path, created_at,
                   audio_track_id, audio_track_name, audio_track_artist,
                   audio_preview_url, audio_fade_in, audio_fade_out, audio_start_offset
            FROM scenes WHERE project_id = $1
            ORDER BY scene_number NULLS LAST, created_at
        """, project_id)
        scenes = []
        for r in rows:
            shot_count = await conn.fetchval(
                "SELECT COUNT(*) FROM shots WHERE scene_id = $1", r["id"])
            scene_data = {
                "id": str(r["id"]), "project_id": r["project_id"],
                "title": r["title"], "description": r["description"],
                "location": r["location"], "time_of_day": r["time_of_day"],
                "weather": r["weather"], "mood": r["mood"],
                "generation_status": r["generation_status"] or "draft",
                "target_duration_seconds": r["target_duration_seconds"],
                "actual_duration_seconds": r["actual_duration_seconds"],
                "total_shots": shot_count,
                "completed_shots": r["completed_shots"] or 0,
                "final_video_path": r["final_video_path"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            if r["audio_track_id"]:
                scene_data["audio"] = {
                    "track_id": r["audio_track_id"],
                    "track_name": r["audio_track_name"],
                    "track_artist": r["audio_track_artist"],
                    "preview_url": r["audio_preview_url"],
                    "fade_in": r["audio_fade_in"],
                    "fade_out": r["audio_fade_out"],
                    "start_offset": r["audio_start_offset"],
                }
            scenes.append(scene_data)
        return {"scenes": scenes}
    finally:
        await conn.close()

@router.post("/scenes")
async def create_scene(body: SceneCreateRequest):
    """Create a new scene."""
    conn = await connect_direct()
    try:
        max_num = await conn.fetchval(
            "SELECT COALESCE(MAX(scene_number), 0) FROM scenes WHERE project_id = $1",
            body.project_id)
        row = await conn.fetchrow("""
            INSERT INTO scenes (project_id, title, description, location, time_of_day,
                                weather, mood, target_duration_seconds, scene_number, generation_status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'draft')
            RETURNING id, created_at
        """, body.project_id, body.title, body.description, body.location,
            body.time_of_day, body.weather, body.mood, body.target_duration_seconds,
            (max_num or 0) + 1)
        return {
            "id": str(row["id"]), "scene_number": (max_num or 0) + 1,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
    finally:
        await conn.close()

@router.post("/scenes/generate-from-story")
async def generate_scenes_from_story_endpoint(project_id: int):
    """Auto-generate scene breakdowns from project storyline using AI."""
    from .story_to_scenes import generate_scenes_from_story
    try:
        scenes = await generate_scenes_from_story(project_id)
        return {"project_id": project_id, "scenes": scenes, "count": len(scenes)}
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"AI returned invalid JSON: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Story-to-scenes generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenes/motion-presets")
async def get_motion_presets(shot_type: str | None = None):
    """Get motion prompt presets, optionally filtered by shot type."""
    if shot_type:
        presets = MOTION_PRESETS.get(shot_type, [])
        return {"shot_type": shot_type, "presets": presets}
    return {"presets": MOTION_PRESETS}


# --- Video A/B Comparison ---

_video_compare_task: dict = {}  # single comparison at a time

_ENGINE_LABELS = {
    "framepack": "FramePack (standard)",
    "framepack_f1": "FramePack F1",
    "ltx": "LTX-Video 2B",
    "wan": "Wan 2.1 T2V 1.3B",
}


async def _run_video_compare(request: VideoCompareRequest, image_filename: str):
    """Background coroutine: run each engine sequentially, score results."""
    results = []
    _video_compare_task["status"] = "running"
    _video_compare_task["total"] = len(request.engines)
    _video_compare_task["completed"] = 0
    _video_compare_task["results"] = results

    for i, eng in enumerate(request.engines):
        engine_name = eng.engine
        label = _ENGINE_LABELS.get(engine_name, engine_name)
        _video_compare_task["current_engine"] = label
        entry = {
            "engine": engine_name, "label": label,
            "status": "running", "video_path": None,
            "quality_score": None, "generation_time": None,
            "file_size_mb": None, "error": None,
        }
        results.append(entry)

        try:
            t0 = time.time()

            if engine_name in ("framepack", "framepack_f1"):
                use_f1 = engine_name == "framepack_f1"
                workflow_data, _, prefix = build_framepack_workflow(
                    prompt_text=request.prompt,
                    image_path=image_filename,
                    total_seconds=request.total_seconds,
                    steps=eng.steps,
                    use_f1=use_f1,
                    seed=eng.seed,
                    negative_text=request.negative_prompt,
                    gpu_memory_preservation=eng.gpu_memory_preservation,
                )
                prompt_id = _submit_comfyui_workflow(workflow_data["prompt"])

            elif engine_name == "ltx":
                fps = 24
                num_frames = max(9, int(request.total_seconds * fps) + 1)
                workflow, prefix = build_ltx_workflow(
                    prompt_text=request.prompt,
                    steps=eng.steps,
                    seed=eng.seed,
                    negative_text=request.negative_prompt,
                    image_path=image_filename,
                    num_frames=num_frames,
                    fps=fps,
                    lora_name=eng.lora_name,
                    lora_strength=eng.lora_strength,
                )
                prompt_id = _submit_ltx_workflow(workflow)

            else:
                entry["status"] = "error"
                entry["error"] = f"Unknown engine: {engine_name}"
                _video_compare_task["completed"] = i + 1
                continue

            # Log generation to generation_history BEFORE polling
            gen_id = await log_generation(
                character_slug=request.character_slug,
                project_name=request.project_name,
                comfyui_prompt_id=prompt_id,
                generation_type="video",
                checkpoint_model=engine_name,
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                seed=eng.seed,
                steps=eng.steps,
            )
            entry["generation_history_id"] = gen_id

            # Poll for completion (reuse existing 30min timeout)
            poll_result = await poll_comfyui_completion(prompt_id)
            gen_time = round(time.time() - t0, 1)
            entry["generation_time"] = gen_time

            if poll_result["status"] == "completed" and poll_result.get("output_files"):
                video_path = str(COMFYUI_OUTPUT_DIR / poll_result["output_files"][0])
                entry["video_path"] = video_path
                entry["status"] = "completed"

                # File size
                if os.path.exists(video_path):
                    entry["file_size_mb"] = round(os.path.getsize(video_path) / (1024 * 1024), 2)

                # Extract last frame and score it
                try:
                    last_frame = await extract_last_frame(video_path)
                    if last_frame:
                        score = await _quality_gate_check(last_frame)
                        entry["quality_score"] = score
                except Exception as e:
                    logger.warning(f"Quality scoring failed for {engine_name}: {e}")

                # Update generation_history with quality + video_engine
                if gen_id:
                    await update_generation_quality(
                        gen_id=gen_id,
                        quality_score=entry["quality_score"] or 0,
                        status="completed",
                        artifact_path=video_path,
                    )
                    # Set video_engine column directly (not in update_generation_quality)
                    try:
                        from packages.core.db import get_pool
                        pool = await get_pool()
                        async with pool.acquire() as conn:
                            await conn.execute(
                                "UPDATE generation_history SET video_engine = $2, "
                                "generation_time_ms = $3 WHERE id = $1",
                                gen_id, engine_name, int(gen_time * 1000),
                            )
                    except Exception as e:
                        logger.warning(f"Failed to set video_engine on gen {gen_id}: {e}")

            else:
                entry["status"] = "failed"
                entry["error"] = f"ComfyUI returned: {poll_result['status']}"
                if gen_id:
                    await update_generation_quality(
                        gen_id=gen_id, quality_score=0, status="failed",
                    )

        except Exception as e:
            entry["status"] = "error"
            entry["error"] = str(e)
            logger.error(f"Video compare engine {engine_name} failed: {e}")

        _video_compare_task["completed"] = i + 1

    # Rank results by quality_score (highest first), then by generation_time (fastest)
    scored = [r for r in results if r["quality_score"] is not None]
    scored.sort(key=lambda r: (-r["quality_score"], r["generation_time"] or 9999))
    for rank, r in enumerate(scored, 1):
        r["rank"] = rank

    _video_compare_task["status"] = "completed"
    _video_compare_task["current_engine"] = None
    _video_compare_task["finished_at"] = datetime.now().isoformat()

    # Log summary to model_audit_log and autonomy_decisions
    try:
        summary = {
            "engines": [r["engine"] for r in results],
            "scores": {r["engine"]: r["quality_score"] for r in results},
            "times": {r["engine"]: r["generation_time"] for r in results},
            "winner": scored[0]["engine"] if scored else None,
        }
        await log_model_change(
            action="video_compare",
            checkpoint_model=scored[0]["engine"] if scored else "none",
            project_name=request.project_name,
            reason=json.dumps(summary),
        )
        await log_decision(
            decision_type="video_compare",
            character_slug=request.character_slug,
            project_name=request.project_name,
            input_context={"prompt": request.prompt, "engines": [e.engine for e in request.engines]},
            decision_made=f"Winner: {scored[0]['engine']}" if scored else "No valid results",
            confidence_score=scored[0]["quality_score"] if scored else 0,
            reasoning=f"Compared {len(request.engines)} engines, ranked by quality then speed",
        )
    except Exception as e:
        logger.warning(f"Failed to log video compare results: {e}")


@router.post("/scenes/video-compare")
async def start_video_compare(body: VideoCompareRequest):
    """Start a video engine A/B comparison (background task).

    Runs each engine sequentially against the same source image + prompt,
    scores quality via vision model, and ranks results.
    """
    # Only one comparison at a time
    if _video_compare_task.get("status") == "running":
        raise HTTPException(status_code=409, detail="A video comparison is already running")

    if not body.engines or len(body.engines) > 5:
        raise HTTPException(status_code=400, detail="Provide 1-5 engine configs")

    valid_engines = set(_ENGINE_LABELS.keys())
    for eng in body.engines:
        if eng.engine not in valid_engines:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown engine '{eng.engine}'. Valid: {sorted(valid_engines)}",
            )

    # Verify source image exists
    src = Path(body.source_image_path)
    if not src.exists():
        raise HTTPException(status_code=400, detail=f"Source image not found: {body.source_image_path}")

    # Copy source image to ComfyUI input dir once
    image_filename = await copy_to_comfyui_input(body.source_image_path)

    # Reset state
    _video_compare_task.clear()
    _video_compare_task["status"] = "starting"
    _video_compare_task["started_at"] = datetime.now().isoformat()
    _video_compare_task["request"] = {
        "prompt": body.prompt,
        "source_image": body.source_image_path,
        "total_seconds": body.total_seconds,
        "engines": [e.engine for e in body.engines],
    }

    # Launch background task
    asyncio.create_task(_run_video_compare(body, image_filename))

    return {
        "message": "Video comparison started",
        "engines": [{"engine": e.engine, "label": _ENGINE_LABELS.get(e.engine, e.engine)} for e in body.engines],
        "total_engines": len(body.engines),
        "poll_url": "/api/scenes/video-compare/status",
    }


@router.get("/scenes/video-compare/status")
async def get_video_compare_status():
    """Poll video comparison progress."""
    if not _video_compare_task:
        return {"status": "idle", "message": "No comparison running or completed"}

    return {
        "status": _video_compare_task.get("status", "unknown"),
        "total": _video_compare_task.get("total", 0),
        "completed": _video_compare_task.get("completed", 0),
        "current_engine": _video_compare_task.get("current_engine"),
        "started_at": _video_compare_task.get("started_at"),
        "finished_at": _video_compare_task.get("finished_at"),
        "results": [
            {k: v for k, v in r.items()}
            for r in _video_compare_task.get("results", [])
        ],
    }


@router.get("/scenes/video-compare/results")
async def get_video_compare_results():
    """Get ranked video comparison results (only available after completion)."""
    if not _video_compare_task:
        raise HTTPException(status_code=404, detail="No comparison data available")

    if _video_compare_task.get("status") != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Comparison is {_video_compare_task.get('status', 'unknown')}, not yet completed",
        )

    results = _video_compare_task.get("results", [])
    ranked = sorted(
        [r for r in results if r.get("quality_score") is not None],
        key=lambda r: (-r["quality_score"], r.get("generation_time") or 9999),
    )
    failed = [r for r in results if r.get("quality_score") is None]

    return {
        "status": "completed",
        "started_at": _video_compare_task.get("started_at"),
        "finished_at": _video_compare_task.get("finished_at"),
        "request": _video_compare_task.get("request"),
        "ranked": ranked,
        "failed": failed,
        "winner": ranked[0] if ranked else None,
    }


@router.get("/scenes/{scene_id}/shot-recommendations")
async def get_shot_recommendations(scene_id: str, top_n: int = 5):
    """Get smart image recommendations for each shot in a scene."""
    from .image_recommender import recommend_for_scene

    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow(
            "SELECT project_id FROM scenes WHERE id = $1", sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        shots = await conn.fetch(
            "SELECT id, shot_number, shot_type, camera_angle, "
            "characters_present, source_image_path "
            "FROM shots WHERE scene_id = $1 ORDER BY shot_number", sid)
        shot_list = [{
            "id": str(sh["id"]),
            "shot_number": sh["shot_number"],
            "shot_type": sh["shot_type"],
            "camera_angle": sh["camera_angle"],
            "characters_present": sh["characters_present"] or [],
            "source_image_path": sh["source_image_path"],
        } for sh in shots]

        # Gather approved images
        char_map = await get_char_project_map()
        approved: dict[str, list[str]] = {}
        for slug, info in char_map.items():
            approval_file = BASE_PATH / slug / "approval_status.json"
            images_dir = BASE_PATH / slug / "images"
            if not images_dir.exists():
                continue
            if approval_file.exists():
                with open(approval_file) as f:
                    statuses = json.load(f)
                imgs = [
                    name for name, st in statuses.items()
                    if (st == "approved" or (isinstance(st, dict) and st.get("status") == "approved"))
                    and (images_dir / name).exists()
                ]
                if imgs:
                    approved[slug] = sorted(imgs)

        recommendations = recommend_for_scene(BASE_PATH, shot_list, approved, top_n)
        return {"scene_id": scene_id, "shots": recommendations}
    finally:
        await conn.close()


@router.get("/scenes/{scene_id}")
async def get_scene(scene_id: str):
    """Get scene detail with all shots."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow("""
            SELECT s.*, p.name as project_name
            FROM scenes s LEFT JOIN projects p ON s.project_id = p.id
            WHERE s.id = $1
        """, sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        shots = await conn.fetch(
            "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number", sid)
        shot_list = []
        for sh in shots:
            shot_list.append({
                "id": str(sh["id"]), "shot_number": sh["shot_number"],
                "shot_type": sh["shot_type"], "camera_angle": sh["camera_angle"],
                "duration_seconds": float(sh["duration_seconds"]) if sh["duration_seconds"] else 3.0,
                "characters_present": sh["characters_present"] or [],
                "motion_prompt": sh["motion_prompt"] or sh["generation_prompt"],
                "source_image_path": sh["source_image_path"],
                "first_frame_path": sh["first_frame_path"],
                "last_frame_path": sh["last_frame_path"],
                "output_video_path": sh["output_video_path"],
                "comfyui_prompt_id": sh["comfyui_prompt_id"],
                "status": sh["status"] or "pending",
                "seed": sh["seed"], "steps": sh["steps"],
                "use_f1": sh["use_f1"] or False,
                "quality_score": sh["quality_score"],
                "error_message": sh["error_message"],
                "generation_time_seconds": sh["generation_time_seconds"],
                "dialogue_text": sh.get("dialogue_text"),
                "dialogue_character_slug": sh.get("dialogue_character_slug"),
                "video_engine": sh.get("video_engine") or "framepack",
                "transition_type": sh.get("transition_type") or "dissolve",
                "transition_duration": float(sh.get("transition_duration") or 0.3),
            })
        return {
            "id": str(scene["id"]), "project_id": scene["project_id"],
            "project_name": scene["project_name"],
            "title": scene["title"], "description": scene["description"],
            "location": scene["location"], "time_of_day": scene["time_of_day"],
            "weather": scene["weather"], "mood": scene["mood"],
            "generation_status": scene["generation_status"] or "draft",
            "target_duration_seconds": scene["target_duration_seconds"],
            "actual_duration_seconds": scene["actual_duration_seconds"],
            "total_shots": len(shot_list),
            "completed_shots": scene["completed_shots"] or 0,
            "final_video_path": scene["final_video_path"],
            "current_generating_shot_id": str(scene["current_generating_shot_id"]) if scene["current_generating_shot_id"] else None,
            "narrative_text": scene["narrative_text"],
            "emotional_tone": scene["emotional_tone"],
            "camera_directions": scene["camera_directions"],
            "audio": {
                "track_id": scene["audio_track_id"],
                "track_name": scene["audio_track_name"],
                "track_artist": scene["audio_track_artist"],
                "preview_url": scene["audio_preview_url"],
                "fade_in": scene["audio_fade_in"],
                "fade_out": scene["audio_fade_out"],
                "start_offset": scene["audio_start_offset"],
            } if scene["audio_track_id"] else None,
            "shots": shot_list,
        }
    finally:
        await conn.close()

@router.patch("/scenes/{scene_id}")
async def update_scene(scene_id: str, body: SceneUpdateRequest):
    """Update scene metadata."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        updates, params, idx = [], [], 2  # $1 is scene_id
        for field in ["title", "description", "location", "time_of_day", "weather", "mood", "target_duration_seconds", "post_interpolate_fps", "post_upscale_factor"]:
            val = getattr(body, field, None)
            if val is not None:
                updates.append(f"{field} = ${idx}")
                params.append(val)
                idx += 1
        if not updates:
            return {"message": "No fields to update"}
        updates.append("updated_at = NOW()")
        await conn.execute(f"UPDATE scenes SET {', '.join(updates)} WHERE id = $1", sid, *params)
        return {"message": "Scene updated"}
    finally:
        await conn.close()

@router.delete("/scenes/{scene_id}")
async def delete_scene(scene_id: str):
    """Delete a scene and its shots."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        await conn.execute("DELETE FROM shots WHERE scene_id = $1", sid)
        await conn.execute("DELETE FROM scenes WHERE id = $1", sid)
        return {"message": "Scene deleted"}
    finally:
        await conn.close()

@router.post("/scenes/{scene_id}/shots")
async def create_shot(scene_id: str, body: ShotCreateRequest):
    """Add a shot to a scene."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        row = await conn.fetchrow("""
            INSERT INTO shots (scene_id, shot_number, source_image_path, shot_type,
                               camera_angle, duration_seconds, motion_prompt,
                               characters_present, seed, steps, use_f1, status,
                               dialogue_text, dialogue_character_slug,
                               transition_type, transition_duration, video_engine)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'pending', $12, $13, $14, $15, $16)
            RETURNING id
        """, sid, body.shot_number, body.source_image_path, body.shot_type,
            body.camera_angle, body.duration_seconds, body.motion_prompt,
            body.characters_present if body.characters_present else None,
            body.seed, body.steps, body.use_f1,
            body.dialogue_text, body.dialogue_character_slug,
            body.transition_type, body.transition_duration, body.video_engine)
        return {"id": str(row["id"]), "shot_number": body.shot_number}
    finally:
        await conn.close()

@router.patch("/scenes/{scene_id}/shots/{shot_id}")
async def update_shot(scene_id: str, shot_id: str, body: ShotUpdateRequest):
    """Update a shot."""
    shid = uuid.UUID(shot_id)
    conn = await connect_direct()
    try:
        updates, params, idx = [], [], 2
        for field, col in [
            ("shot_number", "shot_number"), ("source_image_path", "source_image_path"),
            ("shot_type", "shot_type"), ("camera_angle", "camera_angle"),
            ("duration_seconds", "duration_seconds"), ("motion_prompt", "motion_prompt"),
            ("characters_present", "characters_present"),
            ("seed", "seed"), ("steps", "steps"), ("use_f1", "use_f1"),
            ("dialogue_text", "dialogue_text"), ("dialogue_character_slug", "dialogue_character_slug"),
            ("transition_type", "transition_type"), ("transition_duration", "transition_duration"),
            ("video_engine", "video_engine"),
        ]:
            val = getattr(body, field, None)
            if val is not None:
                updates.append(f"{col} = ${idx}")
                params.append(val)
                idx += 1
        if not updates:
            return {"message": "No fields to update"}
        await conn.execute(f"UPDATE shots SET {', '.join(updates)} WHERE id = $1", shid, *params)
        return {"message": "Shot updated"}
    finally:
        await conn.close()

@router.delete("/scenes/{scene_id}/shots/{shot_id}")
async def delete_shot(scene_id: str, shot_id: str):
    """Delete a shot."""
    shid = uuid.UUID(shot_id)
    conn = await connect_direct()
    try:
        await conn.execute("DELETE FROM shots WHERE id = $1", shid)
        return {"message": "Shot deleted"}
    finally:
        await conn.close()


# --- Video QC Review Endpoints ---

@router.post("/scenes/{scene_id}/shots/{shot_id}/qc-review")
async def qc_review_shot(scene_id: str, shot_id: str, auto_fix: bool = False):
    """Run multi-frame QC review on an existing shot video.

    Returns structured assessment: score, per-frame results, issues, suggested fixes.
    Set auto_fix=true to also return modified prompt/negative from build_prompt_fixes().
    """
    from .video_qc import extract_review_frames, review_video_frames, build_prompt_fixes

    shid = uuid.UUID(shot_id)
    conn = await connect_direct()
    try:
        shot = await conn.fetchrow(
            "SELECT * FROM shots WHERE id = $1 AND scene_id = $2",
            shid, uuid.UUID(scene_id),
        )
        if not shot:
            raise HTTPException(status_code=404, detail="Shot not found")
        if not shot["output_video_path"] or not Path(shot["output_video_path"]).exists():
            raise HTTPException(status_code=400, detail="Shot has no generated video")

        # Extract review frames
        frame_paths = await extract_review_frames(shot["output_video_path"])
        if not frame_paths:
            raise HTTPException(status_code=500, detail="Failed to extract review frames")

        # Get character slug from characters_present
        chars = shot["characters_present"]
        char_slug = chars[0] if chars and isinstance(chars, list) and len(chars) > 0 else None

        # Vision review
        motion_prompt = shot["motion_prompt"] or shot.get("generation_prompt") or ""
        review = await review_video_frames(frame_paths, motion_prompt, char_slug)

        result = {
            "shot_id": shot_id,
            "scene_id": scene_id,
            "video_path": shot["output_video_path"],
            "overall_score": review["overall_score"],
            "issues": review["issues"],
            "category_averages": review.get("category_averages", {}),
            "per_frame": review["per_frame"],
            "frame_paths": frame_paths,
            "current_quality_score": float(shot["quality_score"]) if shot["quality_score"] else None,
        }

        if auto_fix and review["issues"]:
            current_negative = "low quality, blurry, distorted, watermark"
            fixes = build_prompt_fixes(review["issues"], motion_prompt, current_negative)
            result["suggested_fixes"] = fixes

        # Update shot quality_score in DB with new assessment
        await conn.execute(
            "UPDATE shots SET quality_score = $2 WHERE id = $1",
            shid, review["overall_score"],
        )

        return result
    finally:
        await conn.close()


@router.post("/scenes/{scene_id}/shots/{shot_id}/qc-regenerate")
async def qc_regenerate_shot(scene_id: str, shot_id: str):
    """Trigger a full QC loop on a specific shot (with prompt refinement).

    Runs run_qc_loop() as a background task with vision-informed fixes.
    Returns immediately with tracking info.
    """
    from .video_qc import run_qc_loop
    from .builder import _QUALITY_GATES, _MAX_RETRIES, _scene_generation_tasks

    shid = uuid.UUID(shot_id)
    sid = uuid.UUID(scene_id)

    if scene_id in _scene_generation_tasks:
        task = _scene_generation_tasks[scene_id]
        if not task.done():
            raise HTTPException(status_code=409, detail="Scene is currently generating")

    conn = await connect_direct()
    try:
        shot = await conn.fetchrow(
            "SELECT * FROM shots WHERE id = $1 AND scene_id = $2", shid, sid)
        if not shot:
            raise HTTPException(status_code=404, detail="Shot not found")

        # Get previous shot's last frame for continuity
        prev = await conn.fetchrow(
            "SELECT last_frame_path FROM shots WHERE scene_id = $1 AND shot_number < $2 "
            "ORDER BY shot_number DESC LIMIT 1", sid, shot["shot_number"])

        await conn.execute(
            "UPDATE shots SET status = 'generating', error_message = NULL WHERE id = $1", shid)
    finally:
        await conn.close()

    async def _run_qc():
        c = await connect_direct()
        try:
            shot_dict = dict(shot)
            shot_dict["_prev_last_frame"] = (
                prev["last_frame_path"] if prev and prev["last_frame_path"]
                and Path(prev["last_frame_path"]).exists() else None
            )

            qc_result = await run_qc_loop(
                shot_data=shot_dict,
                conn=c,
                max_attempts=_MAX_RETRIES,
                accept_threshold=_QUALITY_GATES[0]["threshold"],
                min_threshold=_QUALITY_GATES[-1]["threshold"],
            )

            if qc_result.get("video_path"):
                status = "completed" if qc_result["accepted"] else "accepted_best"
                await c.execute("""
                    UPDATE shots SET status = $2, output_video_path = $3,
                           last_frame_path = $4, generation_time_seconds = $5,
                           quality_score = $6
                    WHERE id = $1
                """, shid, status, qc_result["video_path"],
                    qc_result["last_frame_path"], qc_result["generation_time"],
                    qc_result["quality_score"])
            else:
                await c.execute(
                    "UPDATE shots SET status = 'failed', error_message = 'QC loop failed' WHERE id = $1",
                    shid)
        except Exception as e:
            logger.error(f"QC regenerate failed for shot {shot_id}: {e}")
            await c.execute(
                "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                shid, str(e)[:500])
        finally:
            await c.close()

    asyncio.create_task(_run_qc())
    return {
        "message": "QC regeneration started",
        "shot_id": shot_id,
        "scene_id": scene_id,
        "max_attempts": _MAX_RETRIES,
        "poll_url": f"/api/scenes/{scene_id}/status",
    }


# --- Scene Builder: Audio Assignment Endpoints ---

@router.post("/scenes/{scene_id}/audio")
async def set_scene_audio(scene_id: str, body: SceneAudioRequest):
    """Assign an Apple Music track to a scene for audio overlay during assembly."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        exists = await conn.fetchval("SELECT 1 FROM scenes WHERE id = $1", sid)
        if not exists:
            raise HTTPException(status_code=404, detail="Scene not found")
        await conn.execute("""
            UPDATE scenes SET audio_track_id = $2, audio_track_name = $3,
                   audio_track_artist = $4, audio_preview_url = $5,
                   audio_fade_in = $6, audio_fade_out = $7, audio_start_offset = $8
            WHERE id = $1
        """, sid, body.track_id, body.track_name, body.track_artist,
            body.preview_url, body.fade_in, body.fade_out, body.start_offset)
        return {
            "message": "Audio track assigned to scene",
            "scene_id": scene_id,
            "track": {"name": body.track_name, "artist": body.track_artist},
        }
    finally:
        await conn.close()


@router.delete("/scenes/{scene_id}/audio")
async def remove_scene_audio(scene_id: str):
    """Remove audio track assignment from a scene."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        exists = await conn.fetchval("SELECT 1 FROM scenes WHERE id = $1", sid)
        if not exists:
            raise HTTPException(status_code=404, detail="Scene not found")
        await conn.execute("""
            UPDATE scenes SET audio_track_id = NULL, audio_track_name = NULL,
                   audio_track_artist = NULL, audio_preview_url = NULL,
                   audio_preview_path = NULL, audio_fade_in = 1.0,
                   audio_fade_out = 2.0, audio_start_offset = 0
            WHERE id = $1
        """, sid)
        return {"message": "Audio track removed from scene", "scene_id": scene_id}
    finally:
        await conn.close()


@router.post("/scenes/{scene_id}/generate-music")
async def generate_scene_music(scene_id: str):
    """Generate AI music for a scene based on its mood via ACE-Step.

    Reads the scene's mood and target_duration from DB, builds a music
    generation caption, submits to ACE-Step, and returns a task_id for polling.
    """
    import urllib.request as _req
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow(
            "SELECT mood, target_duration_seconds, title FROM scenes WHERE id = $1", sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")

        mood = (scene["mood"] or "ambient").split(",")[0].strip().lower()
        duration = scene["target_duration_seconds"] or 30

        # Import mood mapping from audio router
        from packages.audio_composition.router import MOOD_PROMPTS, _build_music_caption
        caption = _build_music_caption(mood, "orchestral anime soundtrack")

        payload = json.dumps({
            "prompt": caption,
            "lyrics": "",
            "duration": float(duration),
            "format": "wav",
            "instrumental": True,
            "infer_steps": 60,
            "guidance_scale": 15.0,
        }).encode()
        req = _req.Request(
            "http://localhost:8440/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = _req.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        task_id = result.get("task_id")

        # Store task_id for later path resolution
        await conn.execute(
            "UPDATE scenes SET generated_music_task_id = $2 WHERE id = $1",
            sid, task_id,
        )

        return {
            "task_id": task_id,
            "scene_id": scene_id,
            "scene_title": scene["title"],
            "mood": mood,
            "caption": caption,
            "duration": duration,
            "status": "pending",
            "poll_url": f"/api/audio/generate-music/{task_id}/status",
        }
    except urllib.error.URLError as e:
        raise HTTPException(status_code=503, detail=f"ACE-Step unavailable: {e}")
    finally:
        await conn.close()


@router.post("/scenes/{scene_id}/attach-music")
async def attach_scene_music(scene_id: str, body: dict):
    """Attach a generated or uploaded music file to a scene.

    Accepts task_id (resolves from ACE-Step) or path (direct file path).
    """
    import urllib.request as _req
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        music_path = body.get("path")

        if not music_path and body.get("task_id"):
            # Resolve from ACE-Step
            try:
                poll_req = _req.Request(f"http://localhost:8440/status/{body['task_id']}")
                poll_resp = _req.urlopen(poll_req, timeout=10)
                status = json.loads(poll_resp.read())
                if status.get("status") == "completed" and status.get("output_path"):
                    music_path = status["output_path"]
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Cannot resolve ACE-Step task: {e}")

        if not music_path or not Path(music_path).exists():
            raise HTTPException(status_code=400, detail="No valid music path provided")

        # Copy to music cache for durability
        from .builder import MUSIC_CACHE
        dest = MUSIC_CACHE / f"scene_{scene_id}_{Path(music_path).name}"
        if not dest.exists():
            import shutil
            shutil.copy2(music_path, str(dest))

        await conn.execute(
            "UPDATE scenes SET generated_music_path = $2 WHERE id = $1",
            sid, str(dest),
        )

        return {"scene_id": scene_id, "music_path": str(dest), "status": "attached"}
    finally:
        await conn.close()


# --- Scene Builder: Generation Endpoints ---

@router.post("/scenes/{scene_id}/generate")
async def generate_scene_endpoint(scene_id: str):
    """Start scene generation (background task)."""
    sid = uuid.UUID(scene_id)
    if scene_id in _scene_generation_tasks:
        task = _scene_generation_tasks[scene_id]
        if not task.done():
            raise HTTPException(status_code=409, detail="Scene is already generating")
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow("SELECT * FROM scenes WHERE id = $1", sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        shot_count = await conn.fetchval(
            "SELECT COUNT(*) FROM shots WHERE scene_id = $1", sid)
        if shot_count == 0:
            raise HTTPException(status_code=400, detail="Scene has no shots")
        # Reset shots to pending
        await conn.execute(
            "UPDATE shots SET status = 'pending', error_message = NULL WHERE scene_id = $1", sid)
        await conn.execute(
            "UPDATE scenes SET completed_shots = 0, current_generating_shot_id = NULL WHERE id = $1", sid)
        # Estimate time (minutes per shot based on duration)
        shots = await conn.fetch(
            "SELECT duration_seconds FROM shots WHERE scene_id = $1 ORDER BY shot_number", sid)
        est_minutes = 0
        for sh in shots:
            dur = float(sh["duration_seconds"] or 3)
            if dur <= 2: est_minutes += 20
            elif dur <= 3: est_minutes += 13
            elif dur <= 5: est_minutes += 25
            else: est_minutes += 30
    finally:
        await conn.close()
    # Spawn background task
    task = asyncio.create_task(generate_scene(sid))
    _scene_generation_tasks[scene_id] = task
    return {"message": "Scene generation started", "total_shots": shot_count, "estimated_minutes": est_minutes}

@router.get("/scenes/{scene_id}/status")
async def get_scene_status(scene_id: str):
    """Poll generation progress for a scene."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow("""
            SELECT generation_status, total_shots, completed_shots,
                   current_generating_shot_id, final_video_path, actual_duration_seconds
            FROM scenes WHERE id = $1
        """, sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        shots = await conn.fetch(
            "SELECT id, shot_number, status, output_video_path, error_message, "
            "comfyui_prompt_id, generation_time_seconds, quality_score, motion_prompt "
            "FROM shots WHERE scene_id = $1 ORDER BY shot_number", sid)
        shot_statuses = [{
            "id": str(sh["id"]), "shot_number": sh["shot_number"],
            "status": sh["status"] or "pending",
            "output_video_path": sh["output_video_path"],
            "error_message": sh["error_message"],
            "comfyui_prompt_id": sh["comfyui_prompt_id"],
            "generation_time_seconds": sh["generation_time_seconds"],
            "quality_score": sh["quality_score"],
            "motion_prompt": sh["motion_prompt"],
        } for sh in shots]
        return {
            "generation_status": scene["generation_status"] or "draft",
            "total_shots": scene["total_shots"] or len(shots),
            "completed_shots": scene["completed_shots"] or 0,
            "current_generating_shot_id": str(scene["current_generating_shot_id"]) if scene["current_generating_shot_id"] else None,
            "final_video_path": scene["final_video_path"],
            "actual_duration_seconds": scene["actual_duration_seconds"],
            "shots": shot_statuses,
        }
    finally:
        await conn.close()

@router.post("/scenes/{scene_id}/shots/{shot_id}/regenerate")
async def regenerate_shot(scene_id: str, shot_id: str):
    """Regenerate a single failed shot."""
    shid = uuid.UUID(shot_id)
    sid = uuid.UUID(scene_id)
    if scene_id in _scene_generation_tasks:
        task = _scene_generation_tasks[scene_id]
        if not task.done():
            raise HTTPException(status_code=409, detail="Scene is currently generating")
    conn = await connect_direct()
    try:
        shot = await conn.fetchrow("SELECT * FROM shots WHERE id = $1 AND scene_id = $2", shid, sid)
        if not shot:
            raise HTTPException(status_code=404, detail="Shot not found")
        await conn.execute(
            "UPDATE shots SET status = 'pending', error_message = NULL WHERE id = $1", shid)
        prev = await conn.fetchrow(
            "SELECT last_frame_path FROM shots WHERE scene_id = $1 AND shot_number < $2 "
            "ORDER BY shot_number DESC LIMIT 1", sid, shot["shot_number"])
        # Determine source
        if prev and prev["last_frame_path"] and Path(prev["last_frame_path"]).exists():
            image_filename = await copy_to_comfyui_input(prev["last_frame_path"])
            first_frame = prev["last_frame_path"]
        else:
            image_filename = await copy_to_comfyui_input(shot["source_image_path"])
            src_p = shot["source_image_path"]
            first_frame = str(BASE_PATH / src_p) if not Path(src_p).is_absolute() else src_p
        prompt_text = shot["motion_prompt"] or shot["generation_prompt"] or ""
        workflow_data, _, _ = build_framepack_workflow(
            prompt_text=prompt_text, image_path=image_filename,
            total_seconds=float(shot["duration_seconds"] or 3),
            steps=shot["steps"] or 25, use_f1=shot["use_f1"] or False,
            seed=shot["seed"], gpu_memory_preservation=6.0)
        comfyui_prompt_id = _submit_comfyui_workflow(workflow_data["prompt"])
        await conn.execute(
            "UPDATE shots SET status = 'generating', comfyui_prompt_id = $2, first_frame_path = $3 WHERE id = $1",
            shid, comfyui_prompt_id, first_frame)
    finally:
        await conn.close()

    async def _regen_single():
        import time as _time
        start = _time.time()
        result = await poll_comfyui_completion(comfyui_prompt_id)
        c = await connect_direct()
        try:
            if result["status"] == "completed" and result["output_files"]:
                vpath = str(COMFYUI_OUTPUT_DIR / result["output_files"][0])
                last_frame = await extract_last_frame(vpath)
                await c.execute("""
                    UPDATE shots SET status = 'completed', output_video_path = $2,
                           last_frame_path = $3, generation_time_seconds = $4
                    WHERE id = $1
                """, shid, vpath, last_frame, _time.time() - start)
            else:
                await c.execute(
                    "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                    shid, f"ComfyUI {result['status']}")
        finally:
            await c.close()
    asyncio.create_task(_regen_single())
    return {"message": "Shot regeneration started", "comfyui_prompt_id": comfyui_prompt_id}

@router.post("/scenes/{scene_id}/assemble")
async def assemble_scene(scene_id: str):
    """Re-concatenate completed shots into scene video."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        shots = await conn.fetch(
            "SELECT output_video_path FROM shots WHERE scene_id = $1 AND status = 'completed' "
            "ORDER BY shot_number", sid)
        if not shots:
            raise HTTPException(status_code=400, detail="No completed shots to assemble")
        video_paths = [sh["output_video_path"] for sh in shots if sh["output_video_path"]]
        if not video_paths:
            raise HTTPException(status_code=400, detail="No video files found")
        scene_video_path = str(SCENE_OUTPUT_DIR / f"scene_{scene_id}.mp4")
        await concat_videos(video_paths, scene_video_path)

        # Apply audio (dialogue + music) — non-fatal wrapper
        await apply_scene_audio(conn, sid, scene_video_path)

        probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", scene_video_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await probe.communicate()
        duration = float(stdout.decode().strip()) if stdout.decode().strip() else None
        await conn.execute("""
            UPDATE scenes SET final_video_path = $2, actual_duration_seconds = $3,
                   generation_status = CASE WHEN completed_shots = total_shots THEN 'completed' ELSE 'partial' END
            WHERE id = $1
        """, sid, scene_video_path, duration)
        return {"message": "Scene assembled", "video_path": scene_video_path,
                "duration_seconds": duration, "shots_included": len(video_paths)}
    finally:
        await conn.close()

@router.get("/scenes/{scene_id}/video")
async def serve_scene_video(scene_id: str):
    """Serve assembled scene video."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        path = await conn.fetchval("SELECT final_video_path FROM scenes WHERE id = $1", sid)
    finally:
        await conn.close()
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Scene video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"scene_{scene_id}.mp4")

@router.get("/scenes/{scene_id}/shots/{shot_id}/video")
async def serve_shot_video(scene_id: str, shot_id: str):
    """Serve individual shot video."""
    shid = uuid.UUID(shot_id)
    conn = await connect_direct()
    try:
        path = await conn.fetchval("SELECT output_video_path FROM shots WHERE id = $1", shid)
    finally:
        await conn.close()
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Shot video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"shot_{shot_id}.mp4")

@router.get("/scenes/{scene_id}/approved-images")
async def get_approved_images_for_scene(
    scene_id: str, project_id: int = 0, include_metadata: bool = False,
):
    """Get approved images for characters in a project (for shot source image picker).

    When include_metadata=true, each image entry includes pose, quality_score,
    and vision_summary from the .meta.json sidecar file.
    """
    char_map = await get_char_project_map()
    results = {}
    for slug, info in char_map.items():
        if project_id and info.get("project_name"):
            pass  # We include all for now, frontend can filter
        approval_file = BASE_PATH / slug / "approval_status.json"
        images_dir = BASE_PATH / slug / "images"
        if not images_dir.exists():
            continue
        approved = []
        if approval_file.exists():
            with open(approval_file) as f:
                statuses = json.load(f)
            for name, st in statuses.items():
                if st == "approved" or (isinstance(st, dict) and st.get("status") == "approved"):
                    if (images_dir / name).exists():
                        approved.append(name)
        if not approved:
            continue
        approved.sort()

        if include_metadata:
            from .image_recommender import batch_read_metadata
            meta_map = batch_read_metadata(BASE_PATH, slug, approved)
            enriched = []
            for name in approved:
                meta = meta_map.get(name, {})
                vr = meta.get("vision_review", {})
                vision_parts = []
                if isinstance(vr, dict):
                    if vr.get("solo") is not None:
                        vision_parts.append("solo" if vr["solo"] else "multi")
                    if vr.get("completeness"):
                        vision_parts.append(vr["completeness"])
                enriched.append({
                    "name": name,
                    "pose": meta.get("pose"),
                    "quality_score": meta.get("quality_score"),
                    "vision_summary": ", ".join(vision_parts) if vision_parts else None,
                })
            results[slug] = {
                "character_name": info.get("name", slug),
                "images": enriched,
            }
        else:
            results[slug] = {
                "character_name": info.get("name", slug),
                "images": approved,
            }
    return {"characters": results}
