"""Production Orchestrator — end-to-end pipeline coordinator.

Wires together all anime production stages so work flows autonomously:
  training_data → lora_training → ready (per character)
  scene_planning → shot_preparation → video_generation → scene_assembly
    → episode_assembly → publishing (per project, blocks until all chars ready)

Safety:
  - OFF by default (must be explicitly toggled on)
  - Respects ComfyUI semaphore (generation serialization)
  - Respects replenishment safety layers (daily limits, consecutive reject pause)
  - FramePack: one scene at a time (GPU memory constraint)
  - All autonomous actions logged to autonomy_decisions via log_decision()
"""

import asyncio
import functools
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from .config import BASE_PATH
from .db import get_pool, connect_direct
from .events import (
    event_bus,
    IMAGE_APPROVED,
    TRAINING_STARTED,
    TRAINING_COMPLETE,
    SCENE_PLANNING_COMPLETE,
    SCENE_READY,
    EPISODE_ASSEMBLED,
    EPISODE_PUBLISHED,
    PIPELINE_PHASE_ADVANCED,
)
from .audit import log_decision

logger = logging.getLogger(__name__)

# ── State (module-level, same pattern as replenishment.py) ──────────────

_enabled = False
_tick_interval = 60        # seconds between ticks
_tick_task = None           # asyncio.Task for the background loop
_training_target = 30      # approved images needed to advance past training_data
_active_work: dict[str, asyncio.Task] = {}  # tracks running _do_work tasks by "entity_type:entity_id:phase"

# Phase definitions
CHARACTER_PHASES = ["training_data", "lora_training", "ready"]
PROJECT_PHASES = [
    "scene_planning", "shot_preparation", "video_generation",
    "video_qc", "scene_assembly", "episode_assembly", "publishing",
]


# ── Enable / Disable ───────────────────────────────────────────────────

def enable(on: bool = True):
    global _enabled
    _enabled = on
    logger.info(f"Orchestrator {'enabled' if on else 'disabled'}")


def is_enabled() -> bool:
    return _enabled


def set_training_target(target: int):
    global _training_target
    _training_target = max(1, target)
    logger.info(f"Orchestrator training target set to {_training_target}")


# ── Initialize Project ─────────────────────────────────────────────────

async def initialize_project(project_id: int, training_target: int | None = None):
    """Bootstrap pipeline entries for all characters in a project + project phases.

    Idempotent — skips entries that already exist (ON CONFLICT DO NOTHING).
    """
    if training_target is not None:
        set_training_target(training_target)

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Get characters for this project
        chars = await conn.fetch("""
            SELECT
                REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') as slug,
                name
            FROM characters
            WHERE project_id = $1
              AND design_prompt IS NOT NULL AND design_prompt != ''
        """, project_id)

        if not chars:
            raise ValueError(f"No characters found for project_id={project_id}")

        # Insert only the FIRST phase for each character — subsequent phases
        # are created by _advance_phase() when the previous one completes.
        # This enforces sequential execution.
        char_count = 0
        for ch in chars:
            await conn.execute("""
                INSERT INTO production_pipeline
                    (entity_type, entity_id, project_id, phase, status)
                VALUES ('character', $1, $2, $3, 'pending')
                ON CONFLICT (entity_type, entity_id, phase) DO NOTHING
            """, ch["slug"], project_id, CHARACTER_PHASES[0])
            char_count += 1

        # Insert only the FIRST project phase
        await conn.execute("""
            INSERT INTO production_pipeline
                (entity_type, entity_id, project_id, phase, status)
            VALUES ('project', $1, $2, $3, 'pending')
            ON CONFLICT (entity_type, entity_id, phase) DO NOTHING
        """, str(project_id), project_id, PROJECT_PHASES[0])

    entries_created = char_count + 1  # 1 per character + 1 project phase

    await log_decision(
        decision_type="orchestrator_init",
        project_name=str(project_id),
        input_context={
            "project_id": project_id,
            "characters": char_count,
            "entries_created": entries_created,
            "training_target": _training_target,
        },
        decision_made="initialized_pipeline",
        confidence_score=1.0,
        reasoning=f"Bootstrapped pipeline: {char_count} characters (first phase) + 1 project phase",
    )

    return {
        "project_id": project_id,
        "characters": char_count,
        "entries_created": entries_created,
        "training_target": _training_target,
    }


# ── Gate Checks ────────────────────────────────────────────────────────
# Each returns {passed: bool, action_needed: bool, ...metrics}

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


def _gate_training_data(slug: str) -> dict:
    """Check if character has enough approved images."""
    approved = _count_approved_from_file(slug)
    return {
        "passed": approved >= _training_target,
        "action_needed": approved < _training_target,
        "approved": approved,
        "target": _training_target,
        "deficit": max(0, _training_target - approved),
    }


def _gate_lora_training(slug: str) -> dict:
    """Check if LoRA safetensors file exists on disk."""
    lora_dir = Path("/opt/ComfyUI/models/loras")
    # Check both SD1.5 and SDXL naming patterns
    sd15_path = lora_dir / f"{slug}_lora.safetensors"
    sdxl_path = lora_dir / f"{slug}_xl_lora.safetensors"
    exists = sd15_path.exists() or sdxl_path.exists()
    return {
        "passed": exists,
        "action_needed": not exists,
        "lora_exists": exists,
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


# ── Work Functions ─────────────────────────────────────────────────────
# Each delegates to existing modules — no new logic, just coordination.

async def _work_training_data(slug: str, project_id: int, gate_result: dict):
    """Generate images + trigger vision review for a character."""
    from .generation import generate_batch
    from .replenishment import _trigger_vision_review

    pool = await get_pool()
    async with pool.acquire() as conn:
        project_name = await conn.fetchval(
            "SELECT name FROM projects WHERE id = $1", project_id
        )

    try:
        await generate_batch(character_slug=slug, count=3)
        logger.info(f"Orchestrator: generated 3 images for {slug}")
    except Exception as e:
        logger.error(f"Orchestrator: generation failed for {slug}: {e}")
        return

    await _trigger_vision_review(slug, project_name)

    await log_decision(
        decision_type="orchestrator_training_data",
        character_slug=slug,
        project_name=project_name,
        input_context=gate_result,
        decision_made="generated_and_reviewed",
        confidence_score=0.9,
        reasoning=f"Character needs {gate_result.get('deficit', '?')} more approved images",
    )


async def _work_lora_training(slug: str, project_id: int):
    """Start LoRA training for a character."""
    from packages.lora_training.training_router import start_training
    from packages.core.models import TrainingRequest

    pool = await get_pool()
    async with pool.acquire() as conn:
        char_name = await conn.fetchval("""
            SELECT name FROM characters
            WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1
              AND project_id = $2
        """, slug, project_id)

    if not char_name:
        logger.error(f"Orchestrator: cannot find character name for slug={slug}")
        return

    try:
        req = TrainingRequest(character_name=char_name)
        await event_bus.emit(TRAINING_STARTED, {
            "character_slug": slug,
            "character_name": char_name,
        })
        result = await start_training(req)
        logger.info(f"Orchestrator: started LoRA training for {char_name}: {result}")
    except Exception as e:
        logger.error(f"Orchestrator: LoRA training failed for {char_name}: {e}")

    await log_decision(
        decision_type="orchestrator_lora_training",
        character_slug=slug,
        input_context={"character_name": char_name},
        decision_made="started_training",
        confidence_score=0.9,
        reasoning=f"Character has {_training_target}+ approved images, starting LoRA training",
    )


async def _echo_narrate(context_type: str, **kwargs) -> str | None:
    """Call Echo Brain narrate endpoint for contextual suggestions.

    Returns the suggestion text on success, None on any failure.
    Non-blocking: failures are logged and swallowed so the orchestrator
    keeps working even if Echo Brain is down.
    """
    import urllib.request as _ur

    ECHO_BRAIN_URL = "http://localhost:8309"
    payload = json.dumps({
        "question": _build_echo_prompt(context_type, kwargs),
    }).encode()

    try:
        req = _ur.Request(
            f"{ECHO_BRAIN_URL}/api/echo/ask",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = _ur.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        answer = data.get("answer", data.get("response", ""))
        return answer.strip() if answer else None
    except Exception as e:
        logger.debug(f"Echo narrate ({context_type}) unavailable: {e}")
        return None


def _build_echo_prompt(context_type: str, ctx: dict) -> str:
    """Build Echo Brain prompt for orchestrator enrichment."""
    project = ctx.get("project_name", "unnamed")
    genre = ctx.get("project_genre", "anime")

    if context_type == "scene_location":
        return (
            f"Suggest a specific, vivid scene location for '{project}' ({genre}). "
            f"Scene description: {ctx.get('scene_description', 'none')}. "
            "Return ONLY a brief location (e.g. 'abandoned rooftop overlooking neon district')."
        )
    elif context_type == "scene_mood":
        return (
            f"Suggest 1-3 mood words for a scene in '{project}' ({genre}). "
            f"Scene description: {ctx.get('scene_description', 'none')}. "
            "Return ONLY mood words (e.g. 'tense, foreboding')."
        )
    elif context_type == "motion_prompt":
        return (
            f"Suggest motion/animation for a {ctx.get('shot_type', 'medium')} shot. "
            f"Scene: {ctx.get('scene_description', 'no description')}. "
            "Return ONLY a brief motion description for video generation."
        )
    return f"Provide a suggestion for: {context_type}"


async def _work_scene_planning(project_id: int):
    """Generate scenes from story using AI, then optionally enrich via Echo Brain."""
    from packages.scene_generation.story_to_scenes import generate_scenes_from_story

    try:
        scenes = await generate_scenes_from_story(project_id)
        logger.info(f"Orchestrator: generated {len(scenes)} scenes for project {project_id}")

        # Fetch project context for Echo enrichment
        pool = await get_pool()
        async with pool.acquire() as conn:
            project_row = await conn.fetchrow(
                "SELECT name, genre FROM projects WHERE id = $1", project_id
            )
            project_name = project_row["name"] if project_row else str(project_id)
            project_genre = project_row["genre"] if project_row else "anime"

        # Enrich scenes with Echo Brain narration (best-effort, non-blocking)
        enriched = 0
        for scene_data in scenes:
            desc = scene_data.get("description", "")

            # Fill empty locations via Echo Brain
            if not scene_data.get("location") and desc:
                suggested = await _echo_narrate(
                    "scene_location",
                    project_name=project_name,
                    project_genre=project_genre,
                    scene_description=desc,
                )
                if suggested:
                    scene_data["location"] = suggested
                    enriched += 1

            # Fill empty moods via Echo Brain
            if not scene_data.get("mood") and desc:
                suggested = await _echo_narrate(
                    "scene_mood",
                    project_name=project_name,
                    project_genre=project_genre,
                    scene_description=desc,
                )
                if suggested:
                    scene_data["mood"] = suggested
                    enriched += 1

        if enriched:
            logger.info(f"Orchestrator: Echo Brain enriched {enriched} scene fields")

        # Insert scenes and shots into DB
        pool = await get_pool()
        async with pool.acquire() as conn:
            for i, scene_data in enumerate(scenes):
                scene_id = await conn.fetchval("""
                    INSERT INTO scenes (project_id, title, description, location,
                                        time_of_day, mood, scene_number)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                """,
                    project_id,
                    scene_data.get("title", f"Scene {i+1}"),
                    scene_data.get("description", ""),
                    scene_data.get("location"),
                    scene_data.get("time_of_day"),
                    scene_data.get("mood"),
                    i + 1,
                )

                for j, shot in enumerate(scene_data.get("suggested_shots", [])):
                    await conn.execute("""
                        INSERT INTO shots (scene_id, shot_number, shot_type,
                                           generation_prompt, motion_prompt, duration_seconds)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (scene_id, shot_number) DO NOTHING
                    """,
                        scene_id,
                        j + 1,
                        shot.get("shot_type", "medium"),
                        shot.get("description", ""),
                        shot.get("motion_prompt"),
                        shot.get("duration_seconds", 3),
                    )

        await event_bus.emit(SCENE_PLANNING_COMPLETE, {
            "project_id": project_id,
            "scene_count": len(scenes),
        })

    except Exception as e:
        logger.error(f"Orchestrator: scene planning failed for project {project_id}: {e}")

    await log_decision(
        decision_type="orchestrator_scene_planning",
        project_name=str(project_id),
        input_context={"project_id": project_id, "echo_enriched": enriched if 'enriched' in dir() else 0},
        decision_made="generated_scenes",
        confidence_score=0.8,
        reasoning="Generated scenes from storyline via AI" + (f", Echo Brain enriched {enriched} fields" if 'enriched' in dir() and enriched else ""),
    )


async def _work_shot_preparation(conn, project_id: int):
    """Assign best approved image to each shot that's missing source_image_path.

    Uses the image recommender's pose+quality+diversity scoring algorithm
    instead of assigning the same top-quality image to every shot.
    Optionally cross-validates against the graph DB for audit logging.
    """
    from .db import get_approved_images_for_project

    # Expanded query: include shot_type, camera_angle, characters_present
    shots = await conn.fetch("""
        SELECT s.id as shot_id, s.shot_number, s.shot_type, s.camera_angle,
               s.characters_present, s.generation_prompt,
               sc.id as scene_id
        FROM shots s
        JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = $1 AND s.source_image_path IS NULL
        ORDER BY sc.scene_number, s.shot_number
    """, project_id)

    if not shots:
        return

    # Query approved images from DB (replaces JSON file reading)
    approved_images = await get_approved_images_for_project(project_id)
    total_images = sum(len(v) for v in approved_images.values())

    if not approved_images:
        logger.warning(f"Orchestrator: no approved images for project {project_id}")
        return

    # Build shot dicts in the format recommend_for_scene() expects
    shot_dicts = []
    for s in shots:
        chars_present = s["characters_present"] or []
        # Ensure characters_present is a list of strings
        if isinstance(chars_present, str):
            chars_present = [chars_present]
        shot_dicts.append({
            "id": str(s["shot_id"]),
            "shot_number": s["shot_number"],
            "shot_type": s["shot_type"] or "medium",
            "camera_angle": s["camera_angle"],
            "characters_present": chars_present,
            "source_image_path": None,  # These are all unassigned
        })

    # Call image recommender (synchronous) via executor
    from packages.scene_generation.image_recommender import recommend_for_scene

    loop = asyncio.get_event_loop()
    recommendations = await loop.run_in_executor(
        None,
        functools.partial(recommend_for_scene, BASE_PATH, shot_dicts, approved_images, 3),
    )

    # Assign best recommendation per shot
    assigned = 0
    assignment_details = []
    for rec in recommendations:
        if not rec["recommendations"]:
            continue
        best = rec["recommendations"][0]
        full_path = str(BASE_PATH / best["slug"] / "images" / best["image_name"])
        await conn.execute(
            "UPDATE shots SET source_image_path = $1 WHERE id = $2",
            full_path, uuid.UUID(rec["shot_id"]),
        )
        assigned += 1
        assignment_details.append({
            "shot_id": rec["shot_id"],
            "shot_number": rec["shot_number"],
            "shot_type": rec["shot_type"],
            "image": best["image_name"],
            "slug": best["slug"],
            "score": best["score"],
            "reason": best["reason"],
        })

    logger.info(
        f"Orchestrator: smart-assigned source images to {assigned}/{len(shots)} shots "
        f"(pool: {total_images} images across {len(approved_images)} characters)"
    )

    # Optional graph enrichment (non-fatal)
    graph_count = 0
    try:
        from .graph_queries import approved_images_for_project
        project_name = await conn.fetchval(
            "SELECT name FROM projects WHERE id = $1", project_id
        )
        if project_name:
            graph_images = await approved_images_for_project(project_name)
            graph_count = sum(len(v) for v in graph_images.values())
    except Exception as e:
        logger.warning(f"Graph enrichment skipped (non-fatal): {e}")

    await log_decision(
        decision_type="orchestrator_shot_prep",
        project_name=str(project_id),
        input_context={
            "shots_needing_images": len(shots),
            "db_images": total_images,
            "graph_images": graph_count,
            "characters": len(approved_images),
            "assignments": assignment_details,
        },
        decision_made="smart_assigned_source_images",
        confidence_score=0.85,
        reasoning=(
            f"Smart assignment: {assigned}/{len(shots)} shots, "
            f"pose+quality+diversity scoring via image_recommender"
        ),
    )


async def _work_video_generation(conn, project_id: int):
    """Generate video for one scene at a time (GPU constraint)."""
    from packages.scene_generation.builder import generate_scene

    # Find the first scene that still needs generation
    scene = await conn.fetchrow("""
        SELECT id FROM scenes
        WHERE project_id = $1 AND final_video_path IS NULL
        ORDER BY scene_number
        LIMIT 1
    """, project_id)

    if not scene:
        return

    scene_id = str(scene["id"])
    logger.info(f"Orchestrator: starting video generation for scene {scene_id}")

    try:
        # generate_scene handles everything: shot rendering, crossfade, audio
        await generate_scene(scene_id)
        await event_bus.emit(SCENE_READY, {
            "project_id": project_id,
            "scene_id": scene_id,
        })
        logger.info(f"Orchestrator: scene {scene_id} generation complete")
    except Exception as e:
        logger.error(f"Orchestrator: video generation failed for scene {scene_id}: {e}")

    await log_decision(
        decision_type="orchestrator_video_gen",
        project_name=str(project_id),
        input_context={"scene_id": scene_id},
        decision_made="generated_scene_video",
        confidence_score=0.8,
        reasoning="Generated video for next incomplete scene",
    )


async def _work_video_qc(conn, project_id: int):
    """Run QC refinement pass on shots that are below quality threshold."""
    from packages.scene_generation.video_qc import run_qc_loop

    # Find shots that need QC refinement
    shots = await conn.fetch("""
        SELECT s.* FROM shots s
        JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = $1
          AND s.status IN ('completed', 'accepted_best')
          AND (s.quality_score IS NULL OR s.quality_score < 0.3)
        ORDER BY s.quality_score ASC NULLS FIRST
        LIMIT 1
    """, project_id)

    if not shots:
        return

    shot = dict(shots[0])
    shot_id = shot["id"]
    logger.info(f"Orchestrator: running QC refinement on shot {shot_id} (quality={shot.get('quality_score')})")

    try:
        shot["_prev_last_frame"] = None
        # Get previous shot's last frame for continuity
        prev = await conn.fetchrow(
            "SELECT last_frame_path FROM shots WHERE scene_id = $1 AND shot_number < $2 "
            "ORDER BY shot_number DESC LIMIT 1", shot["scene_id"], shot["shot_number"])
        if prev and prev["last_frame_path"]:
            from pathlib import Path
            if Path(prev["last_frame_path"]).exists():
                shot["_prev_last_frame"] = prev["last_frame_path"]

        qc_result = await run_qc_loop(
            shot_data=shot,
            conn=conn,
            max_attempts=3,
            accept_threshold=0.6,
            min_threshold=0.3,
        )

        if qc_result.get("video_path"):
            status = "completed" if qc_result["accepted"] else "accepted_best"
            await conn.execute("""
                UPDATE shots SET status = $2, output_video_path = $3,
                       last_frame_path = $4, generation_time_seconds = $5,
                       quality_score = $6
                WHERE id = $1
            """, shot_id, status, qc_result["video_path"],
                qc_result["last_frame_path"], qc_result["generation_time"],
                qc_result["quality_score"])
            logger.info(f"Orchestrator: QC refinement complete for shot {shot_id}, quality={qc_result['quality_score']:.2f}")
    except Exception as e:
        logger.error(f"Orchestrator: QC refinement failed for shot {shot_id}: {e}")

    await log_decision(
        decision_type="orchestrator_video_qc",
        project_name=str(project_id),
        input_context={"shot_id": str(shot_id), "original_quality": shot.get("quality_score")},
        decision_made="qc_refinement_pass",
        confidence_score=qc_result.get("quality_score", 0) if 'qc_result' in dir() else 0,
        reasoning=f"QC refinement pass on shot with quality below threshold",
    )


async def _work_episode_assembly(conn, project_id: int):
    """Assemble the next unassembled episode."""
    from packages.episode_assembly.builder import assemble_episode

    episode = await conn.fetchrow("""
        SELECT id, episode_number, title FROM episodes
        WHERE project_id = $1 AND final_video_path IS NULL
        ORDER BY episode_number
        LIMIT 1
    """, project_id)

    if not episode:
        return

    episode_id = str(episode["id"])

    # Get scene videos in order
    scene_videos = await conn.fetch("""
        SELECT s.final_video_path, es.transition
        FROM episode_scenes es
        JOIN scenes s ON es.scene_id = s.id
        WHERE es.episode_id = $1
        ORDER BY es.position
    """, episode["id"])

    video_paths = [r["final_video_path"] for r in scene_videos if r["final_video_path"]]
    transitions = [r["transition"] for r in scene_videos]

    if not video_paths:
        logger.warning(f"Orchestrator: no scene videos for episode {episode_id}")
        return

    try:
        result_path = await assemble_episode(episode_id, video_paths, transitions)
        await event_bus.emit(EPISODE_ASSEMBLED, {
            "project_id": project_id,
            "episode_id": episode_id,
            "episode_number": episode["episode_number"],
            "path": result_path,
        })
        logger.info(f"Orchestrator: assembled episode {episode['episode_number']}")
    except Exception as e:
        logger.error(f"Orchestrator: episode assembly failed for {episode_id}: {e}")

    await log_decision(
        decision_type="orchestrator_episode_assembly",
        project_name=str(project_id),
        input_context={"episode_id": episode_id, "scene_count": len(video_paths)},
        decision_made="assembled_episode",
        confidence_score=0.9,
        reasoning=f"Assembled episode {episode['episode_number']} from {len(video_paths)} scenes",
    )


async def _work_publishing(conn, project_id: int):
    """Publish the next assembled but unpublished episode."""
    from packages.episode_assembly.publish import publish_episode

    project_name = await conn.fetchval(
        "SELECT name FROM projects WHERE id = $1", project_id
    )

    episode = await conn.fetchrow("""
        SELECT id, episode_number, title, final_video_path, thumbnail_path
        FROM episodes
        WHERE project_id = $1
          AND final_video_path IS NOT NULL
          AND status != 'published'
        ORDER BY episode_number
        LIMIT 1
    """, project_id)

    if not episode:
        return

    try:
        result = await publish_episode(
            project_name=project_name,
            episode_number=episode["episode_number"],
            episode_title=episode["title"],
            video_path=episode["final_video_path"],
            thumbnail_path=episode["thumbnail_path"],
        )

        await conn.execute("""
            UPDATE episodes SET status = 'published', updated_at = NOW()
            WHERE id = $1
        """, episode["id"])

        await event_bus.emit(EPISODE_PUBLISHED, {
            "project_id": project_id,
            "episode_id": str(episode["id"]),
            "episode_number": episode["episode_number"],
            "published_path": result.get("published_path"),
        })
        logger.info(f"Orchestrator: published episode {episode['episode_number']}")
    except Exception as e:
        logger.error(f"Orchestrator: publishing failed for episode {episode['episode_number']}: {e}")

    await log_decision(
        decision_type="orchestrator_publish",
        project_name=project_name,
        input_context={"episode_number": episode["episode_number"]},
        decision_made="published_episode",
        confidence_score=0.9,
        reasoning=f"Published episode {episode['episode_number']} to Jellyfin",
    )


# ── Phase Advancement ──────────────────────────────────────────────────

def _next_phase(entity_type: str, current_phase: str) -> str | None:
    """Get the next phase in the pipeline, or None if terminal."""
    phases = CHARACTER_PHASES if entity_type == "character" else PROJECT_PHASES
    try:
        idx = phases.index(current_phase)
        if idx + 1 < len(phases):
            return phases[idx + 1]
    except ValueError:
        pass
    return None


async def _advance_phase(conn, entry: dict):
    """Mark current phase completed and create next phase entry."""
    now = datetime.utcnow()

    await conn.execute("""
        UPDATE production_pipeline
        SET status = 'completed', completed_at = $1, updated_at = $1
        WHERE id = $2
    """, now, entry["id"])

    next_phase = _next_phase(entry["entity_type"], entry["phase"])
    if next_phase:
        await conn.execute("""
            INSERT INTO production_pipeline
                (entity_type, entity_id, project_id, phase, status)
            VALUES ($1, $2, $3, $4, 'pending')
            ON CONFLICT (entity_type, entity_id, phase) DO NOTHING
        """, entry["entity_type"], entry["entity_id"], entry["project_id"], next_phase)

    await event_bus.emit(PIPELINE_PHASE_ADVANCED, {
        "entity_type": entry["entity_type"],
        "entity_id": entry["entity_id"],
        "project_id": entry["project_id"],
        "completed_phase": entry["phase"],
        "next_phase": next_phase,
    })

    logger.info(
        f"Orchestrator: {entry['entity_type']}:{entry['entity_id']} "
        f"advanced from {entry['phase']} → {next_phase or 'DONE'}"
    )


# ── Tick Logic ─────────────────────────────────────────────────────────

async def _all_characters_ready(conn, project_id: int) -> bool:
    """Check if all characters in the project have reached 'ready' phase."""
    not_ready = await conn.fetchval("""
        SELECT COUNT(*) FROM production_pipeline
        WHERE project_id = $1
          AND entity_type = 'character'
          AND phase != 'ready'
          AND status != 'completed'
    """, project_id)
    # Also check that at least some character entries exist
    total = await conn.fetchval("""
        SELECT COUNT(*) FROM production_pipeline
        WHERE project_id = $1 AND entity_type = 'character'
    """, project_id)
    return total > 0 and not_ready == 0


async def _evaluate_entry(conn, entry: dict):
    """Evaluate a single pipeline entry: check gate, advance or initiate work."""
    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]
    project_id = entry["project_id"]
    phase = entry["phase"]
    status = entry["status"]
    now = datetime.utcnow()

    # Project phases block until all characters are ready
    if entity_type == "project":
        chars_ready = await _all_characters_ready(conn, project_id)
        if not chars_ready:
            if status != "blocked":
                await conn.execute("""
                    UPDATE production_pipeline
                    SET status = 'blocked',
                        blocked_reason = 'Waiting for all character LoRAs',
                        last_checked_at = $1, updated_at = $1
                    WHERE id = $2
                """, now, entry["id"])
            return

        # Characters are ready — clear block if needed
        if status == "blocked":
            await conn.execute("""
                UPDATE production_pipeline
                SET status = 'pending', blocked_reason = NULL,
                    last_checked_at = $1, updated_at = $1
                WHERE id = $2
            """, now, entry["id"])
            status = "pending"

    # Run the gate check
    gate_result = await _check_gate(conn, entity_type, entity_id, project_id, phase)

    # Update last_checked_at and gate_check_result
    await conn.execute("""
        UPDATE production_pipeline
        SET last_checked_at = $1, gate_check_result = $2, updated_at = $1
        WHERE id = $3
    """, now, json.dumps(gate_result), entry["id"])

    if gate_result["passed"]:
        await _advance_phase(conn, entry)
    elif gate_result.get("action_needed"):
        work_key = f"{entity_type}:{entity_id}:{phase}"
        task_running = work_key in _active_work and not _active_work[work_key].done()

        if status != "active":
            # Mark active and initiate work
            await conn.execute("""
                UPDATE production_pipeline
                SET status = 'active', started_at = COALESCE(started_at, $1), updated_at = $1
                WHERE id = $2
            """, now, entry["id"])

        if not task_running:
            # (Re-)dispatch work — previous task finished or was never started
            task = asyncio.create_task(
                _do_work(entity_type, entity_id, project_id, phase, gate_result)
            )
            _active_work[work_key] = task


async def _check_gate(conn, entity_type: str, entity_id: str, project_id: int, phase: str) -> dict:
    """Dispatch to the appropriate gate check function."""
    if entity_type == "character":
        if phase == "training_data":
            return _gate_training_data(entity_id)
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


async def _do_work(entity_type: str, entity_id: str, project_id: int, phase: str, gate_result: dict):
    """Dispatch to the appropriate work function. Runs as a background task."""
    if not _enabled:
        logger.info(f"Orchestrator disabled — skipping work for {entity_type}:{entity_id} phase={phase}")
        return
    try:
        if entity_type == "character":
            if phase == "training_data":
                await _work_training_data(entity_id, project_id, gate_result)
            elif phase == "lora_training":
                await _work_lora_training(entity_id, project_id)
        else:  # project
            pool = await get_pool()
            async with pool.acquire() as conn:
                if phase == "scene_planning":
                    await _work_scene_planning(project_id)
                elif phase == "shot_preparation":
                    await _work_shot_preparation(conn, project_id)
                elif phase == "video_generation":
                    await _work_video_generation(conn, project_id)
                elif phase == "video_qc":
                    await _work_video_qc(conn, project_id)
                elif phase == "episode_assembly":
                    await _work_episode_assembly(conn, project_id)
                elif phase == "publishing":
                    await _work_publishing(conn, project_id)
    except Exception as e:
        logger.error(f"Orchestrator work failed: {entity_type}:{entity_id} phase={phase}: {e}")

        # Mark as failed
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE production_pipeline
                    SET status = 'failed', blocked_reason = $1, updated_at = NOW()
                    WHERE entity_type = $2 AND entity_id = $3 AND phase = $4
                """, str(e)[:500], entity_type, entity_id, phase)
        except Exception:
            pass


async def tick():
    """Single evaluation pass — check all non-completed pipeline entries."""
    if not _enabled:
        return {"skipped": True, "reason": "orchestrator disabled"}

    pool = await get_pool()
    async with pool.acquire() as conn:
        entries = await conn.fetch("""
            SELECT * FROM production_pipeline
            WHERE status NOT IN ('completed', 'skipped')
            ORDER BY project_id, entity_type DESC, phase
        """)

        evaluated = 0
        for entry in entries:
            await _evaluate_entry(conn, dict(entry))
            evaluated += 1

    return {"evaluated": evaluated, "timestamp": datetime.utcnow().isoformat()}


# ── Background Tick Loop ───────────────────────────────────────────────

async def _tick_loop():
    """Background loop that runs tick() every _tick_interval seconds."""
    while True:
        try:
            if _enabled:
                await tick()
        except Exception as e:
            logger.error(f"Orchestrator tick error: {e}")
        await asyncio.sleep(_tick_interval)


async def start_tick_loop():
    """Start the background tick loop. Called once at app startup."""
    global _tick_task
    if _tick_task is not None and not _tick_task.done():
        return
    _tick_task = asyncio.create_task(_tick_loop())
    logger.info(f"Orchestrator tick loop started (interval={_tick_interval}s, enabled={_enabled})")


# ── Status / Summary ──────────────────────────────────────────────────

async def get_pipeline_status(project_id: int) -> dict:
    """Structured pipeline status for dashboard display."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        entries = await conn.fetch("""
            SELECT * FROM production_pipeline
            WHERE project_id = $1
            ORDER BY entity_type DESC, entity_id, phase
        """, project_id)

        project_name = await conn.fetchval(
            "SELECT name FROM projects WHERE id = $1", project_id
        )

    characters = {}
    project_phases = {}

    for e in entries:
        entry = dict(e)
        # Convert timestamps to ISO strings
        for ts_field in ("started_at", "completed_at", "last_checked_at", "created_at", "updated_at"):
            if entry.get(ts_field):
                entry[ts_field] = entry[ts_field].isoformat()
        # Parse JSONB fields
        for json_field in ("progress_detail", "gate_check_result"):
            if isinstance(entry.get(json_field), str):
                try:
                    entry[json_field] = json.loads(entry[json_field])
                except (json.JSONDecodeError, TypeError):
                    pass

        if entry["entity_type"] == "character":
            characters.setdefault(entry["entity_id"], []).append(entry)
        else:
            project_phases[entry["phase"]] = entry

    # Calculate overall progress
    total = len(entries)
    completed = sum(1 for e in entries if e["status"] == "completed")
    active = sum(1 for e in entries if e["status"] == "active")
    failed = sum(1 for e in entries if e["status"] == "failed")

    return {
        "project_id": project_id,
        "project_name": project_name,
        "enabled": _enabled,
        "training_target": _training_target,
        "progress": {
            "total_phases": total,
            "completed": completed,
            "active": active,
            "failed": failed,
            "percent": round(completed / total * 100, 1) if total > 0 else 0,
        },
        "characters": characters,
        "project_phases": project_phases,
    }


async def get_pipeline_summary(project_id: int) -> str:
    """Human-readable summary for Echo Brain context injection."""
    status = await get_pipeline_status(project_id)
    lines = []
    lines.append(f"Production Pipeline: {status['project_name'] or f'Project {project_id}'}")
    lines.append(f"Overall: {status['progress']['completed']}/{status['progress']['total_phases']} phases complete ({status['progress']['percent']}%)")

    if status["progress"]["failed"] > 0:
        lines.append(f"ALERT: {status['progress']['failed']} phase(s) FAILED")

    lines.append("")

    # Character summary
    lines.append("Characters:")
    for slug, phases in status["characters"].items():
        current = next(
            (p for p in phases if p["status"] in ("pending", "active", "blocked")),
            phases[-1] if phases else None,
        )
        if current:
            lines.append(f"  {slug}: {current['phase']} ({current['status']})")
        else:
            lines.append(f"  {slug}: all complete")

    lines.append("")

    # Project phases
    lines.append("Project Phases:")
    for phase_name in PROJECT_PHASES:
        entry = status["project_phases"].get(phase_name)
        if entry:
            detail = f"{entry['status']}"
            if entry.get("blocked_reason"):
                detail += f" — {entry['blocked_reason']}"
            lines.append(f"  {phase_name}: {detail}")
        else:
            lines.append(f"  {phase_name}: not started")

    return "\n".join(lines)


# ── Manual Override ────────────────────────────────────────────────────

async def override_phase(
    entity_type: str,
    entity_id: str,
    phase: str,
    action: str,  # "skip", "reset", "complete"
) -> dict:
    """Force a phase to a specific status."""
    pool = await get_pool()
    now = datetime.utcnow()

    async with pool.acquire() as conn:
        entry = await conn.fetchrow("""
            SELECT * FROM production_pipeline
            WHERE entity_type = $1 AND entity_id = $2 AND phase = $3
        """, entity_type, entity_id, phase)

        if not entry:
            raise ValueError(f"No pipeline entry found: {entity_type}:{entity_id}:{phase}")

        if action == "skip":
            await conn.execute("""
                UPDATE production_pipeline
                SET status = 'skipped', updated_at = $1
                WHERE id = $2
            """, now, entry["id"])
        elif action == "reset":
            await conn.execute("""
                UPDATE production_pipeline
                SET status = 'pending', started_at = NULL, completed_at = NULL,
                    blocked_reason = NULL, gate_check_result = NULL, updated_at = $1
                WHERE id = $2
            """, now, entry["id"])
        elif action == "complete":
            await _advance_phase(conn, dict(entry))
        else:
            raise ValueError(f"Unknown override action: {action}")

    await log_decision(
        decision_type="orchestrator_override",
        input_context={
            "entity_type": entity_type,
            "entity_id": entity_id,
            "phase": phase,
            "action": action,
        },
        decision_made=f"manual_{action}",
        confidence_score=1.0,
        reasoning=f"Manual override: {action} on {entity_type}:{entity_id}:{phase}",
    )

    return {"entity_type": entity_type, "entity_id": entity_id, "phase": phase, "action": action}


# ── EventBus Handlers ──────────────────────────────────────────────────

async def _handle_image_approved(data: dict):
    """Update progress_current on the character's training_data entry."""
    slug = data.get("character_slug")
    if not slug:
        return

    approved = _count_approved_from_file(slug)

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE production_pipeline
                SET progress_current = $1, progress_target = $2, updated_at = NOW()
                WHERE entity_type = 'character' AND entity_id = $3 AND phase = 'training_data'
                  AND status NOT IN ('completed', 'skipped')
            """, approved, _training_target, slug)
    except Exception as e:
        logger.warning(f"Orchestrator: failed to update training_data progress for {slug}: {e}")


async def _handle_phase_advanced(data: dict):
    """Audit log when a phase advances."""
    await log_decision(
        decision_type="orchestrator_phase_advanced",
        project_name=str(data.get("project_id")),
        input_context=data,
        decision_made="phase_advanced",
        confidence_score=1.0,
        reasoning=(
            f"{data.get('entity_type')}:{data.get('entity_id')} "
            f"completed {data.get('completed_phase')} → {data.get('next_phase', 'DONE')}"
        ),
    )


def register_orchestrator_handlers():
    """Register EventBus handlers. Called once at startup."""
    event_bus.subscribe(IMAGE_APPROVED, _handle_image_approved)
    event_bus.subscribe(PIPELINE_PHASE_ADVANCED, _handle_phase_advanced)
    logger.info("Orchestrator EventBus handlers registered")
