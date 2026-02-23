"""Orchestrator work functions — execute pipeline actions for each phase.

Split from orchestrator.py for readability. Each _work_* function delegates
to existing modules — no new logic, just coordination.
"""

import asyncio
import functools
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from .config import BASE_PATH
from .db import get_pool
from .events import (
    event_bus,
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


# ── Echo Brain Integration ─────────────────────────────────────────────

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


# ── Phase Advancement ──────────────────────────────────────────────────

def _next_phase(entity_type: str, current_phase: str, character_phases: list, project_phases: list) -> str | None:
    """Get the next phase in the pipeline, or None if terminal."""
    phases = character_phases if entity_type == "character" else project_phases
    try:
        idx = phases.index(current_phase)
        if idx + 1 < len(phases):
            return phases[idx + 1]
    except ValueError:
        pass
    return None


async def _auto_link_lora(conn, slug: str):
    """Auto-link a freshly trained LoRA file to the character's DB record."""
    lora_dir = Path("/opt/ComfyUI/models/loras")
    sd15_path = lora_dir / f"{slug}_lora.safetensors"
    sdxl_path = lora_dir / f"{slug}_xl_lora.safetensors"

    lora_path = None
    if sdxl_path.exists():
        lora_path = sdxl_path.name
    elif sd15_path.exists():
        lora_path = sd15_path.name

    if not lora_path:
        logger.warning(f"Auto-link LoRA: no file found for {slug}, skipping DB update")
        return

    try:
        result = await conn.execute("""
            UPDATE characters SET lora_path = $1, updated_at = NOW()
            WHERE LOWER(REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g')) = $2
              AND (lora_path IS NULL OR lora_path = '')
        """, lora_path, slug)
        logger.info(f"Auto-link LoRA: set {slug}.lora_path = {lora_path} ({result})")
    except Exception as e:
        logger.error(f"Auto-link LoRA failed for {slug}: {e}")


async def advance_phase(conn, entry: dict, character_phases: list, project_phases: list):
    """Mark current phase completed and create next phase entry."""
    now = datetime.utcnow()

    await conn.execute("""
        UPDATE production_pipeline
        SET status = 'completed', completed_at = $1, updated_at = $1
        WHERE id = $2
    """, now, entry["id"])

    # Auto-link LoRA to character DB record when lora_training completes
    if entry["entity_type"] == "character" and entry["phase"] == "lora_training":
        await _auto_link_lora(conn, entry["entity_id"])

    next_ph = _next_phase(entry["entity_type"], entry["phase"], character_phases, project_phases)
    if next_ph:
        await conn.execute("""
            INSERT INTO production_pipeline
                (entity_type, entity_id, project_id, phase, status)
            VALUES ($1, $2, $3, $4, 'pending')
            ON CONFLICT (entity_type, entity_id, phase) DO NOTHING
        """, entry["entity_type"], entry["entity_id"], entry["project_id"], next_ph)

    await event_bus.emit(PIPELINE_PHASE_ADVANCED, {
        "entity_type": entry["entity_type"],
        "entity_id": entry["entity_id"],
        "project_id": entry["project_id"],
        "completed_phase": entry["phase"],
        "next_phase": next_ph,
    })

    logger.info(
        f"Orchestrator: {entry['entity_type']}:{entry['entity_id']} "
        f"advanced from {entry['phase']} → {next_ph or 'DONE'}"
    )


# ── Work Functions ─────────────────────────────────────────────────────

async def work_training_data(slug: str, project_id: int, gate_result: dict, training_target: int):
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


async def work_lora_training(slug: str, project_id: int, training_target: int):
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
        reasoning=f"Character has {training_target}+ approved images, starting LoRA training",
    )


async def work_scene_planning(project_id: int):
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


async def work_shot_preparation(conn, project_id: int):
    """Assign best approved image to each shot missing source_image_path."""
    from .db import get_approved_images_for_project

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

    approved_images = await get_approved_images_for_project(project_id)
    total_images = sum(len(v) for v in approved_images.values())

    if not approved_images:
        logger.warning(f"Orchestrator: no approved images for project {project_id}")
        return

    shot_dicts = []
    for s in shots:
        chars_present = s["characters_present"] or []
        if isinstance(chars_present, str):
            chars_present = [chars_present]
        shot_dicts.append({
            "id": str(s["shot_id"]),
            "shot_number": s["shot_number"],
            "shot_type": s["shot_type"] or "medium",
            "camera_angle": s["camera_angle"],
            "characters_present": chars_present,
            "source_image_path": None,
        })

    from packages.scene_generation.image_recommender import recommend_for_scene

    loop = asyncio.get_event_loop()
    recommendations = await loop.run_in_executor(
        None,
        functools.partial(recommend_for_scene, BASE_PATH, shot_dicts, approved_images, 3),
    )

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

    # --- Engine selection pass ---
    engine_details = []
    try:
        from packages.scene_generation.engine_selector import select_engine

        # Fetch blacklist for project
        blacklist_rows = await conn.fetch(
            "SELECT character_slug, video_engine FROM engine_blacklist WHERE project_id = $1",
            project_id,
        )
        # Build per-character blacklist sets
        char_blacklists: dict[str, list[str]] = {}
        for bl_row in blacklist_rows:
            char_blacklists.setdefault(bl_row["character_slug"], []).append(bl_row["video_engine"])

        # Re-fetch all shots (including ones that already had images) for engine selection
        all_shots = await conn.fetch("""
            SELECT s.id, s.shot_type, s.characters_present, s.source_image_path,
                   s.video_engine, s.lora_name
            FROM shots s
            JOIN scenes sc ON s.scene_id = sc.id
            WHERE sc.project_id = $1
              AND s.status IN ('pending', 'draft')
            ORDER BY sc.scene_number, s.shot_number
        """, project_id)

        for shot_row in all_shots:
            chars = shot_row["characters_present"] or []
            if isinstance(chars, str):
                chars = [chars]

            # Collect blacklisted engines for all characters in this shot
            blocked = set()
            for c in chars:
                blocked.update(char_blacklists.get(c, []))

            has_image = bool(shot_row["source_image_path"])
            shot_type = shot_row["shot_type"] or "medium"

            selection = select_engine(
                shot_type=shot_type,
                characters_present=chars,
                has_source_image=has_image,
                blacklisted_engines=list(blocked),
            )

            await conn.execute(
                "UPDATE shots SET video_engine = $1, lora_name = $2, lora_strength = $3 WHERE id = $4",
                selection.engine, selection.lora_name, selection.lora_strength, shot_row["id"],
            )
            engine_details.append({
                "shot_id": str(shot_row["id"]),
                "engine": selection.engine,
                "reason": selection.reason,
                "lora_name": selection.lora_name,
            })

        logger.info(
            f"Orchestrator: assigned engines to {len(engine_details)} shots "
            f"(blacklist entries: {len(blacklist_rows)})"
        )
    except Exception as e:
        logger.warning(f"Engine selection pass failed (non-fatal): {e}")

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
            "engine_assignments": engine_details,
        },
        decision_made="smart_assigned_source_images_and_engines",
        confidence_score=0.85,
        reasoning=(
            f"Smart assignment: {assigned}/{len(shots)} shots, "
            f"pose+quality+diversity scoring via image_recommender, "
            f"engine selection: {len(engine_details)} shots"
        ),
    )


async def work_video_generation(conn, project_id: int):
    """Generate video for one scene at a time (GPU constraint)."""
    from packages.scene_generation.builder import generate_scene, _scene_generation_tasks

    scene = await conn.fetchrow("""
        SELECT id FROM scenes
        WHERE project_id = $1 AND final_video_path IS NULL
        ORDER BY scene_number
        LIMIT 1
    """, project_id)

    if not scene:
        return

    scene_id = str(scene["id"])

    if scene_id in _scene_generation_tasks:
        existing = _scene_generation_tasks[scene_id]
        if not existing.done():
            logger.info(f"Orchestrator: scene {scene_id} already generating (via API), skipping")
            return

    logger.info(f"Orchestrator: starting video generation for scene {scene_id}")

    sentinel = asyncio.get_event_loop().create_future()
    _scene_generation_tasks[scene_id] = sentinel

    try:
        await generate_scene(scene_id)
        await event_bus.emit(SCENE_READY, {
            "project_id": project_id,
            "scene_id": scene_id,
        })
        logger.info(f"Orchestrator: scene {scene_id} generation complete")
    except Exception as e:
        logger.error(f"Orchestrator: video generation failed for scene {scene_id}: {e}")
    finally:
        _scene_generation_tasks.pop(scene_id, None)
        if not sentinel.done():
            sentinel.set_result(None)

    await log_decision(
        decision_type="orchestrator_video_gen",
        project_name=str(project_id),
        input_context={"scene_id": scene_id},
        decision_made="generated_scene_video",
        confidence_score=0.8,
        reasoning="Generated video for next incomplete scene",
    )


async def work_video_qc(conn, project_id: int):
    """Run QC refinement pass on shots below quality threshold."""
    from packages.scene_generation.video_qc import run_qc_loop

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
        prev = await conn.fetchrow(
            "SELECT last_frame_path FROM shots WHERE scene_id = $1 AND shot_number < $2 "
            "ORDER BY shot_number DESC LIMIT 1", shot["scene_id"], shot["shot_number"])
        if prev and prev["last_frame_path"]:
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


async def work_scene_assembly(conn, project_id: int):
    """Assemble scenes that have all shots completed but no final_video_path."""
    from packages.scene_generation.builder import (
        SCENE_OUTPUT_DIR, concat_videos, apply_scene_audio,
    )

    scenes = await conn.fetch("""
        SELECT s.id, s.scene_number, s.title
        FROM scenes s
        WHERE s.project_id = $1
          AND s.final_video_path IS NULL
          AND EXISTS (
              SELECT 1 FROM shots sh
              WHERE sh.scene_id = s.id
                AND sh.status IN ('completed', 'accepted_best')
                AND sh.output_video_path IS NOT NULL
          )
        ORDER BY s.scene_number
    """, project_id)

    if not scenes:
        return

    assembled = 0
    for scene in scenes:
        scene_id = scene["id"]
        scene_id_str = str(scene_id)

        shot_videos = await conn.fetch("""
            SELECT output_video_path FROM shots
            WHERE scene_id = $1
              AND status IN ('completed', 'accepted_best')
              AND output_video_path IS NOT NULL
            ORDER BY shot_number
        """, scene_id)

        video_paths = [r["output_video_path"] for r in shot_videos]
        if not video_paths:
            continue

        scene_video_path = str(SCENE_OUTPUT_DIR / f"scene_{scene_id_str}.mp4")

        try:
            await concat_videos(video_paths, scene_video_path)
            await apply_scene_audio(conn, scene_id, scene_video_path)

            probe = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                "-of", "csv=p=0", scene_video_path,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await probe.communicate()
            duration = float(stdout.decode().strip()) if stdout.decode().strip() else None

            total_shots = await conn.fetchval(
                "SELECT COUNT(*) FROM shots WHERE scene_id = $1", scene_id
            )
            gen_status = "completed" if len(video_paths) >= total_shots else "partial"

            await conn.execute("""
                UPDATE scenes SET final_video_path = $2, actual_duration_seconds = $3,
                       generation_status = $4, completed_shots = $5
                WHERE id = $1
            """, scene_id, scene_video_path, duration, gen_status, len(video_paths))

            assembled += 1
            logger.info(
                f"Orchestrator: assembled scene {scene['title'] or scene_id_str} "
                f"({len(video_paths)} shots, {gen_status})"
            )
        except Exception as e:
            logger.error(f"Orchestrator: scene assembly failed for {scene_id_str}: {e}")

    await log_decision(
        decision_type="orchestrator_scene_assembly",
        project_name=str(project_id),
        input_context={"scenes_found": len(scenes), "assembled": assembled},
        decision_made="assembled_scenes",
        confidence_score=0.85,
        reasoning=f"Assembled {assembled}/{len(scenes)} scenes with completed shots",
    )


async def work_episode_assembly(conn, project_id: int):
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


async def work_publishing(conn, project_id: int):
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


async def do_work(entity_type: str, entity_id: str, project_id: int, phase: str, gate_result: dict, enabled: bool, training_target: int):
    """Dispatch to the appropriate work function. Runs as a background task."""
    if not enabled:
        logger.info(f"Orchestrator disabled — skipping work for {entity_type}:{entity_id} phase={phase}")
        return
    try:
        if entity_type == "character":
            if phase == "training_data":
                await work_training_data(entity_id, project_id, gate_result, training_target)
            elif phase == "lora_training":
                await work_lora_training(entity_id, project_id, training_target)
        else:  # project
            pool = await get_pool()
            async with pool.acquire() as conn:
                if phase == "scene_planning":
                    await work_scene_planning(project_id)
                elif phase == "shot_preparation":
                    await work_shot_preparation(conn, project_id)
                elif phase == "video_generation":
                    await work_video_generation(conn, project_id)
                elif phase == "video_qc":
                    await work_video_qc(conn, project_id)
                elif phase == "scene_assembly":
                    await work_scene_assembly(conn, project_id)
                elif phase == "episode_assembly":
                    await work_episode_assembly(conn, project_id)
                elif phase == "publishing":
                    await work_publishing(conn, project_id)
    except Exception as e:
        logger.error(f"Orchestrator work failed: {entity_type}:{entity_id} phase={phase}: {e}")

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
