"""Orchestrator gate checks — each returns {passed, action_needed, ...metrics}.

Split from orchestrator.py for readability. All gates are imported and
re-exported by orchestrator.py so external callers are unaffected.
"""

import json
import logging
from pathlib import Path

from .config import BASE_PATH

logger = logging.getLogger(__name__)


def _count_approved_from_file(slug: str) -> int:
    """Count approved images from approval_status.json."""
    approval_file = BASE_PATH / slug / "approval_status.json"
    if not approval_file.exists():
        return 0
    try:
        statuses = json.loads(approval_file.read_text())
        return sum(1 for v in statuses.values() if v == "approved")
    except (json.JSONDecodeError, IOError):
        return 0


def _gate_training_data(slug: str, training_target: int) -> dict:
    """Check if character has enough approved images."""
    approved = _count_approved_from_file(slug)
    return {
        "passed": approved >= training_target,
        "action_needed": approved < training_target,
        "approved": approved,
        "target": training_target,
        "deficit": max(0, training_target - approved),
    }


def _gate_lora_training(slug: str) -> dict:
    """Check if LoRA safetensors file exists on disk."""
    lora_dir = Path("/opt/ComfyUI/models/loras")
    sd15_path = lora_dir / f"{slug}_lora.safetensors"
    sdxl_path = lora_dir / f"{slug}_xl_lora.safetensors"
    exists = sd15_path.exists() or sdxl_path.exists()

    if exists:
        return {
            "passed": True,
            "action_needed": False,
            "lora_exists": True,
            "checked_paths": [str(sd15_path), str(sdxl_path)],
        }

    # Check if a training job is already running/queued for this slug
    try:
        from packages.lora_training.feedback import load_training_jobs
        jobs = load_training_jobs()
        for job in jobs:
            if job.get("character_slug") == slug and job.get("status") in ("running", "queued"):
                return {
                    "passed": False,
                    "action_needed": False,
                    "lora_exists": False,
                    "reason": "training in progress",
                    "job_id": job.get("job_id"),
                    "job_status": job["status"],
                    "checked_paths": [str(sd15_path), str(sdxl_path)],
                }
    except Exception as e:
        logger.warning(f"Failed to check training jobs for {slug}: {e}")

    return {
        "passed": False,
        "action_needed": True,
        "lora_exists": False,
        "checked_paths": [str(sd15_path), str(sdxl_path)],
    }


async def _gate_scene_planning(conn, project_id: int) -> dict:
    """Check if scenes exist in DB for this project."""
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM scenes WHERE project_id = $1", project_id
    )
    return {
        "passed": count > 0,
        "action_needed": count == 0,
        "scene_count": count,
    }


async def _gate_shot_preparation(conn, project_id: int) -> dict:
    """Check if all shots have source_image_path assigned."""
    total = await conn.fetchval("""
        SELECT COUNT(*) FROM shots s
        JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = $1
    """, project_id)
    missing = await conn.fetchval("""
        SELECT COUNT(*) FROM shots s
        JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = $1 AND s.source_image_path IS NULL
    """, project_id)
    return {
        "passed": total > 0 and missing == 0,
        "action_needed": missing > 0,
        "total_shots": total,
        "missing_source_image": missing,
    }


async def _gate_video_generation(conn, project_id: int) -> dict:
    """Check if all shots have completed video generation."""
    total = await conn.fetchval("""
        SELECT COUNT(*) FROM shots s
        JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = $1
    """, project_id)
    completed = await conn.fetchval("""
        SELECT COUNT(*) FROM shots s
        JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = $1
          AND s.status IN ('completed', 'accepted_best')
    """, project_id)
    return {
        "passed": total > 0 and completed >= total,
        "action_needed": completed < total,
        "total_shots": total,
        "completed_shots": completed,
    }


async def _gate_video_qc(conn, project_id: int) -> dict:
    """Check if all completed shots meet minimum quality threshold."""
    total = await conn.fetchval("""
        SELECT COUNT(*) FROM shots s
        JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = $1
          AND s.status IN ('completed', 'accepted_best')
    """, project_id)
    below_threshold = await conn.fetchval("""
        SELECT COUNT(*) FROM shots s
        JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = $1
          AND s.status IN ('completed', 'accepted_best')
          AND (s.quality_score IS NULL OR s.quality_score < 0.3)
    """, project_id)
    return {
        "passed": total > 0 and below_threshold == 0,
        "action_needed": below_threshold > 0,
        "total_completed_shots": total,
        "below_threshold": below_threshold,
    }


async def _gate_scene_assembly(conn, project_id: int) -> dict:
    """Check if all scenes have final_video_path."""
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM scenes WHERE project_id = $1", project_id
    )
    assembled = await conn.fetchval("""
        SELECT COUNT(*) FROM scenes
        WHERE project_id = $1 AND final_video_path IS NOT NULL
    """, project_id)
    return {
        "passed": total > 0 and assembled >= total,
        "action_needed": assembled < total,
        "total_scenes": total,
        "assembled_scenes": assembled,
    }


async def _gate_episode_assembly(conn, project_id: int) -> dict:
    """Check if all episodes are assembled."""
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM episodes WHERE project_id = $1", project_id
    )
    assembled = await conn.fetchval("""
        SELECT COUNT(*) FROM episodes
        WHERE project_id = $1 AND final_video_path IS NOT NULL
    """, project_id)
    return {
        "passed": total > 0 and assembled >= total,
        "action_needed": total > 0 and assembled < total,
        "total_episodes": total,
        "assembled_episodes": assembled,
    }


async def _gate_publishing(conn, project_id: int) -> dict:
    """Check if all episodes are published."""
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM episodes WHERE project_id = $1", project_id
    )
    published = await conn.fetchval("""
        SELECT COUNT(*) FROM episodes
        WHERE project_id = $1 AND status = 'published'
    """, project_id)
    return {
        "passed": total > 0 and published >= total,
        "action_needed": total > 0 and published < total,
        "total_episodes": total,
        "published_episodes": published,
    }


async def check_gate(conn, entity_type: str, entity_id: str, project_id: int, phase: str, training_target: int) -> dict:
    """Dispatch to the appropriate gate check function."""
    if entity_type == "character":
        if phase == "training_data":
            return _gate_training_data(entity_id, training_target)
        elif phase == "lora_training":
            return _gate_lora_training(entity_id)
        elif phase == "ready":
            return {"passed": True, "action_needed": False}
    else:  # project
        if phase == "scene_planning":
            return await _gate_scene_planning(conn, project_id)
        elif phase == "shot_preparation":
            return await _gate_shot_preparation(conn, project_id)
        elif phase == "video_generation":
            return await _gate_video_generation(conn, project_id)
        elif phase == "video_qc":
            return await _gate_video_qc(conn, project_id)
        elif phase == "scene_assembly":
            return await _gate_scene_assembly(conn, project_id)
        elif phase == "episode_assembly":
            return await _gate_episode_assembly(conn, project_id)
        elif phase == "publishing":
            return await _gate_publishing(conn, project_id)

    return {"passed": False, "action_needed": False}
