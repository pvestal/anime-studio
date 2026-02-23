"""Video review & QC endpoints — pending videos, approve/reject, engine stats.

Split from router.py for readability.
"""

import json
import logging
import uuid
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException

from packages.core.db import connect_direct
from packages.core.models import VideoReviewRequest, BatchVideoReviewRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/scenes/pending-videos")
async def get_pending_videos(
    project_id: int | None = None,
    video_engine: str | None = None,
    character_slug: str | None = None,
):
    """List shots pending human video review, with scene/project context."""
    conn = await connect_direct()
    try:
        conditions = ["sh.review_status = 'pending_review'", "sh.output_video_path IS NOT NULL"]
        params = []
        idx = 1

        if project_id is not None:
            conditions.append(f"s.project_id = ${idx}")
            params.append(project_id)
            idx += 1
        if video_engine:
            conditions.append(f"sh.video_engine = ${idx}")
            params.append(video_engine)
            idx += 1
        if character_slug:
            conditions.append(f"${idx} = ANY(sh.characters_present)")
            params.append(character_slug)
            idx += 1

        where = " AND ".join(conditions)
        rows = await conn.fetch(f"""
            SELECT sh.id, sh.scene_id, sh.shot_number, sh.shot_type, sh.camera_angle,
                   sh.duration_seconds, sh.characters_present, sh.motion_prompt,
                   sh.source_image_path, sh.output_video_path, sh.quality_score,
                   sh.video_engine, sh.seed, sh.steps, sh.generation_time_seconds,
                   sh.review_status, sh.qc_issues, sh.qc_category_averages, sh.qc_per_frame,
                   sh.review_feedback, sh.reviewed_at,
                   s.title as scene_title, s.project_id,
                   p.name as project_name
            FROM shots sh
            JOIN scenes s ON sh.scene_id = s.id
            JOIN projects p ON s.project_id = p.id
            WHERE {where}
            ORDER BY sh.quality_score ASC NULLS FIRST
        """, *params)

        videos = []
        for r in rows:
            cat_avgs = r["qc_category_averages"]
            if isinstance(cat_avgs, str):
                cat_avgs = json.loads(cat_avgs)
            per_frame = r["qc_per_frame"]
            if isinstance(per_frame, str):
                per_frame = json.loads(per_frame)

            videos.append({
                "id": str(r["id"]),
                "scene_id": str(r["scene_id"]),
                "shot_number": r["shot_number"],
                "shot_type": r["shot_type"],
                "camera_angle": r["camera_angle"],
                "duration_seconds": float(r["duration_seconds"]) if r["duration_seconds"] else 3.0,
                "characters_present": r["characters_present"] or [],
                "motion_prompt": r["motion_prompt"],
                "source_image_path": r["source_image_path"],
                "output_video_path": r["output_video_path"],
                "quality_score": float(r["quality_score"]) if r["quality_score"] is not None else None,
                "video_engine": r["video_engine"] or "framepack",
                "seed": r["seed"],
                "steps": r["steps"],
                "generation_time_seconds": r["generation_time_seconds"],
                "review_status": r["review_status"],
                "qc_issues": r["qc_issues"] or [],
                "qc_category_averages": cat_avgs or {},
                "qc_per_frame": per_frame or [],
                "scene_title": r["scene_title"],
                "project_id": r["project_id"],
                "project_name": r["project_name"],
            })

        return {"pending_videos": videos, "total": len(videos)}
    finally:
        await conn.close()


@router.post("/scenes/review-video")
async def review_video(body: VideoReviewRequest):
    """Approve or reject a single shot video. Optionally blacklist the engine."""
    shot_id = uuid.UUID(body.shot_id)
    conn = await connect_direct()
    try:
        shot = await conn.fetchrow(
            "SELECT sh.*, s.project_id FROM shots sh JOIN scenes s ON sh.scene_id = s.id WHERE sh.id = $1",
            shot_id,
        )
        if not shot:
            raise HTTPException(status_code=404, detail="Shot not found")

        if body.approved:
            await conn.execute("""
                UPDATE shots SET review_status = 'approved', reviewed_at = NOW(),
                       review_feedback = $2
                WHERE id = $1
            """, shot_id, body.feedback)
        else:
            await conn.execute("""
                UPDATE shots SET review_status = 'rejected', reviewed_at = NOW(),
                       review_feedback = $2
                WHERE id = $1
            """, shot_id, body.feedback)

        if body.reject_engine and not body.approved:
            chars = shot["characters_present"]
            char_slug = chars[0] if chars and isinstance(chars, list) and len(chars) > 0 else None
            engine = shot["video_engine"] or "framepack"
            project_id = shot["project_id"]

            if char_slug:
                await conn.execute("""
                    INSERT INTO engine_blacklist (character_slug, project_id, video_engine, reason)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (character_slug, project_id, video_engine) DO UPDATE
                    SET reason = EXCLUDED.reason, created_at = NOW()
                """, char_slug, project_id, engine, body.feedback or "Rejected via video review")

        action = "approved" if body.approved else "rejected"
        return {
            "message": f"Shot {action}",
            "shot_id": body.shot_id,
            "review_status": "approved" if body.approved else "rejected",
            "engine_blacklisted": body.reject_engine and not body.approved,
        }
    finally:
        await conn.close()


@router.post("/scenes/batch-review-video")
async def batch_review_video(body: BatchVideoReviewRequest):
    """Batch approve or reject multiple shot videos."""
    conn = await connect_direct()
    try:
        shot_ids = [uuid.UUID(sid) for sid in body.shot_ids]
        status = "approved" if body.approved else "rejected"

        updated = 0
        for sid in shot_ids:
            result = await conn.execute("""
                UPDATE shots SET review_status = $2, reviewed_at = NOW(),
                       review_feedback = $3
                WHERE id = $1 AND review_status = 'pending_review'
            """, sid, status, body.feedback)
            if "UPDATE 1" in result:
                updated += 1

        return {
            "message": f"Batch {status}: {updated}/{len(shot_ids)} shots",
            "updated": updated,
            "total": len(shot_ids),
            "review_status": status,
        }
    finally:
        await conn.close()


@router.get("/scenes/engine-stats")
async def get_engine_stats(project_id: int | None = None, character_slug: str | None = None):
    """Per-engine quality statistics, filterable by project/character."""
    conn = await connect_direct()
    try:
        conditions = ["sh.quality_score IS NOT NULL"]
        params = []
        idx = 1

        if project_id is not None:
            conditions.append(f"s.project_id = ${idx}")
            params.append(project_id)
            idx += 1
        if character_slug:
            conditions.append(f"${idx} = ANY(sh.characters_present)")
            params.append(character_slug)
            idx += 1

        where = " AND ".join(conditions)
        rows = await conn.fetch(f"""
            SELECT COALESCE(sh.video_engine, 'framepack') as video_engine,
                   COUNT(*) as total,
                   ROUND(AVG(sh.quality_score)::numeric, 3) as avg_quality,
                   MIN(sh.quality_score) as min_quality,
                   MAX(sh.quality_score) as max_quality,
                   COUNT(*) FILTER (WHERE sh.review_status = 'approved') as approved,
                   COUNT(*) FILTER (WHERE sh.review_status = 'rejected') as rejected,
                   COUNT(*) FILTER (WHERE sh.review_status = 'pending_review') as pending,
                   ROUND(AVG(sh.generation_time_seconds)::numeric, 1) as avg_gen_time
            FROM shots sh
            JOIN scenes s ON sh.scene_id = s.id
            WHERE {where}
            GROUP BY COALESCE(sh.video_engine, 'framepack')
            ORDER BY avg_quality DESC NULLS LAST
        """, *params)

        bl_conditions = []
        bl_params = []
        bl_idx = 1
        if project_id is not None:
            bl_conditions.append(f"project_id = ${bl_idx}")
            bl_params.append(project_id)
            bl_idx += 1
        if character_slug:
            bl_conditions.append(f"character_slug = ${bl_idx}")
            bl_params.append(character_slug)
            bl_idx += 1

        bl_where = " AND ".join(bl_conditions) if bl_conditions else "TRUE"
        blacklist = await conn.fetch(f"""
            SELECT character_slug, video_engine, reason, created_at
            FROM engine_blacklist WHERE {bl_where}
            ORDER BY created_at DESC
        """, *bl_params)

        stats = []
        for r in rows:
            stats.append({
                "video_engine": r["video_engine"],
                "total": r["total"],
                "avg_quality": float(r["avg_quality"]) if r["avg_quality"] else None,
                "min_quality": float(r["min_quality"]) if r["min_quality"] else None,
                "max_quality": float(r["max_quality"]) if r["max_quality"] else None,
                "approved": r["approved"],
                "rejected": r["rejected"],
                "pending": r["pending"],
                "avg_gen_time": float(r["avg_gen_time"]) if r["avg_gen_time"] else None,
            })

        blacklist_list = [
            {
                "character_slug": bl["character_slug"],
                "video_engine": bl["video_engine"],
                "reason": bl["reason"],
                "created_at": bl["created_at"].isoformat() if bl["created_at"] else None,
            }
            for bl in blacklist
        ]

        return {"engine_stats": stats, "blacklist": blacklist_list}
    finally:
        await conn.close()


@router.post("/scenes/{scene_id}/shots/{shot_id}/qc-review")
async def qc_review_shot(scene_id: str, shot_id: str, auto_fix: bool = False):
    """Run multi-frame QC review on an existing shot video."""
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

        frame_paths = await extract_review_frames(shot["output_video_path"])
        if not frame_paths:
            raise HTTPException(status_code=500, detail="Failed to extract review frames")

        chars = shot["characters_present"]
        char_slug = chars[0] if chars and isinstance(chars, list) and len(chars) > 0 else None

        motion_prompt = shot["motion_prompt"] or shot.get("generation_prompt") or ""
        review = await review_video_frames(
            frame_paths, motion_prompt, char_slug,
            source_image_path=shot["source_image_path"],
        )

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

        await conn.execute(
            "UPDATE shots SET quality_score = $2 WHERE id = $1",
            shid, review["overall_score"],
        )

        return result
    finally:
        await conn.close()


@router.post("/scenes/{scene_id}/shots/{shot_id}/qc-regenerate")
async def qc_regenerate_shot(scene_id: str, shot_id: str):
    """Trigger a full QC loop on a specific shot (with prompt refinement)."""
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
