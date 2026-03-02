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

Sub-modules:
  - orchestrator_gates.py: gate check functions
  - orchestrator_work.py: work dispatch functions
"""

import asyncio
import json
import logging
from datetime import datetime

from .config import BASE_PATH
from .db import get_pool, connect_direct
from .events import (
    event_bus,
    IMAGE_APPROVED,
    PIPELINE_PHASE_ADVANCED,
    TRAINING_STARTED,
    SCENE_PLANNING_COMPLETE,
    SCENE_READY,
    SHOT_GENERATED,
    EPISODE_ASSEMBLED,
    EPISODE_PUBLISHED,
)
from .audit import log_decision

# Import gate checks from sub-module
from .orchestrator_gates import (
    _count_approved_from_file,
    _gate_training_data,
    _gate_lora_training,
    _gate_scene_planning,
    _gate_shot_preparation,
    _gate_video_generation,
    _gate_video_qc,
    _gate_scene_assembly,
    _gate_episode_assembly,
    _gate_publishing,
    check_gate as _check_gate_impl,
)

# Import work functions from sub-module
from .orchestrator_work import (
    advance_phase as _advance_phase_impl,
    do_work as _do_work_impl,
    _next_phase,
    _auto_link_lora,
    _echo_narrate,
    _build_echo_prompt,
    work_training_data as _work_training_data,
    work_lora_training as _work_lora_training,
    work_scene_planning as _work_scene_planning,
    work_shot_preparation as _work_shot_preparation,
    work_video_generation as _work_video_generation,
    work_video_qc as _work_video_qc,
    work_scene_assembly as _work_scene_assembly,
    work_episode_assembly as _work_episode_assembly,
    work_publishing as _work_publishing,
)

logger = logging.getLogger(__name__)

# ── State (module-level, same pattern as replenishment.py) ──────────────

_enabled = False
_tick_interval = 60        # seconds between ticks
_graph_sync_interval = 1800  # 30 min between graph syncs
_tick_task = None           # asyncio.Task for the background loop
_graph_sync_task = None     # asyncio.Task for periodic graph sync
_training_target = 100     # approved images needed to advance past training_data
_active_work: dict[str, asyncio.Task] = {}  # tracks running work tasks

# Phase definitions
CHARACTER_PHASES = ["training_data", "lora_training", "ready"]
PROJECT_PHASES = [
    "scene_planning", "shot_preparation", "video_generation",
    "video_qc", "scene_assembly", "episode_assembly", "publishing",
]


# ── Enable / Disable ───────────────────────────────────────────────────

async def enable(on: bool = True):
    global _enabled
    _enabled = on
    logger.info(f"Orchestrator {'enabled' if on else 'disabled'}")
    # Persist to DB so state survives restarts
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO system_config (key, value, description, category, updated_at)
                VALUES ('orchestrator_enabled', $1, 'Orchestrator on/off state (persisted)', 'orchestrator', NOW())
                ON CONFLICT (key) DO UPDATE SET value = $1, updated_at = NOW()
            """, str(on).lower())
    except Exception as e:
        logger.warning(f"Failed to persist orchestrator state: {e}")


def is_enabled() -> bool:
    return _enabled


async def _load_enabled_state():
    """Load persisted orchestrator enabled state from DB on startup."""
    global _enabled
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT value FROM system_config WHERE key = 'orchestrator_enabled'"
            )
            if val is not None:
                _enabled = val.lower() == 'true'
                logger.info(f"Orchestrator state loaded from DB: enabled={_enabled}")
            else:
                logger.info("No persisted orchestrator state found, defaulting to disabled")
    except Exception as e:
        logger.warning(f"Failed to load orchestrator state from DB: {e}")


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

        char_count = 0
        for ch in chars:
            await conn.execute("""
                INSERT INTO production_pipeline
                    (entity_type, entity_id, project_id, phase, status)
                VALUES ('character', $1, $2, $3, 'pending')
                ON CONFLICT (entity_type, entity_id, phase) DO NOTHING
            """, ch["slug"], project_id, CHARACTER_PHASES[0])
            char_count += 1

        await conn.execute("""
            INSERT INTO production_pipeline
                (entity_type, entity_id, project_id, phase, status)
            VALUES ('project', $1, $2, $3, 'pending')
            ON CONFLICT (entity_type, entity_id, phase) DO NOTHING
        """, str(project_id), project_id, PROJECT_PHASES[0])

    entries_created = char_count + 1

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

        if status == "blocked":
            await conn.execute("""
                UPDATE production_pipeline
                SET status = 'pending', blocked_reason = NULL,
                    last_checked_at = $1, updated_at = $1
                WHERE id = $2
            """, now, entry["id"])
            status = "pending"

    # Run the gate check
    gate_result = await _check_gate_impl(
        conn, entity_type, entity_id, project_id, phase, _training_target,
    )

    await conn.execute("""
        UPDATE production_pipeline
        SET last_checked_at = $1, gate_check_result = $2, updated_at = $1
        WHERE id = $3
    """, now, json.dumps(gate_result), entry["id"])

    if gate_result["passed"]:
        await _advance_phase_impl(conn, entry, CHARACTER_PHASES, PROJECT_PHASES)
    elif gate_result.get("action_needed"):
        work_key = f"{entity_type}:{entity_id}:{phase}"
        task_running = work_key in _active_work and not _active_work[work_key].done()

        if status != "active":
            await conn.execute("""
                UPDATE production_pipeline
                SET status = 'active', started_at = COALESCE(started_at, $1), updated_at = $1
                WHERE id = $2
            """, now, entry["id"])

        if not task_running:
            task = asyncio.create_task(
                _do_work_impl(
                    entity_type, entity_id, project_id, phase,
                    gate_result, _enabled, _training_target,
                )
            )
            _active_work[work_key] = task


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


async def _graph_sync_loop():
    """Background loop that runs graph full_sync() every _graph_sync_interval seconds.

    Non-fatal — if graph sync fails, it logs and retries next interval.
    Runs regardless of orchestrator enabled state (graph data is useful even when paused).
    """
    # Initial delay to let the app finish starting
    await asyncio.sleep(30)
    while True:
        try:
            from .graph_sync import full_sync
            result = full_sync()
            if asyncio.iscoroutine(result):
                result = await result
            logger.info(f"Periodic graph sync complete: {result}")
        except Exception as e:
            logger.warning(f"Periodic graph sync failed (non-fatal): {e}")
        await asyncio.sleep(_graph_sync_interval)


async def start_tick_loop():
    """Start the background tick loop and graph sync loop. Called once at app startup."""
    global _tick_task, _graph_sync_task
    if _tick_task is not None and not _tick_task.done():
        return
    # Load persisted enabled state before starting the loop
    await _load_enabled_state()
    _tick_task = asyncio.create_task(_tick_loop())
    _graph_sync_task = asyncio.create_task(_graph_sync_loop())
    logger.info(
        f"Orchestrator tick loop started (interval={_tick_interval}s, enabled={_enabled}), "
        f"graph sync loop started (interval={_graph_sync_interval}s)"
    )


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
        for ts_field in ("started_at", "completed_at", "last_checked_at", "created_at", "updated_at"):
            if entry.get(ts_field):
                entry[ts_field] = entry[ts_field].isoformat()
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
            await _advance_phase_impl(conn, dict(entry), CHARACTER_PHASES, PROJECT_PHASES)
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


async def _handle_training_started(data: dict):
    """Audit log when LoRA training begins."""
    slug = data.get("character_slug", "unknown")
    logger.info(f"Orchestrator: training started for {slug}")
    await log_decision(
        decision_type="orchestrator_training_started",
        character_slug=slug,
        input_context=data,
        decision_made="training_started",
        confidence_score=1.0,
        reasoning=f"LoRA training initiated for {data.get('character_name', slug)}",
    )


async def _handle_scene_planning_complete(data: dict):
    """Auto-advance scene_planning phase and trigger shot preparation."""
    project_id = data.get("project_id")
    if not project_id:
        return

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            entry = await conn.fetchrow("""
                SELECT * FROM production_pipeline
                WHERE entity_type = 'project' AND project_id = $1
                  AND phase = 'scene_planning' AND status NOT IN ('completed', 'skipped')
            """, project_id)
            if entry:
                await _advance_phase_impl(conn, dict(entry), CHARACTER_PHASES, PROJECT_PHASES)
                logger.info(
                    f"Orchestrator: scene_planning → shot_preparation "
                    f"(auto-advanced for project {project_id}, {data.get('scene_count', '?')} scenes)"
                )
    except Exception as e:
        logger.error(f"Orchestrator: failed to auto-advance scene_planning for project {project_id}: {e}")


async def _handle_scene_ready(data: dict):
    """When a scene's videos finish, check if all shots are done and trigger assembly."""
    project_id = data.get("project_id")
    scene_id = data.get("scene_id")
    if not project_id or not scene_id:
        return

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Check if all shots in this scene have video
            counts = await conn.fetchrow("""
                SELECT COUNT(*) as total,
                       COUNT(*) FILTER (WHERE status IN ('completed', 'accepted_best')
                                        AND output_video_path IS NOT NULL) as done
                FROM shots WHERE scene_id = $1
            """, scene_id)

            if counts and counts["total"] > 0 and counts["done"] >= counts["total"]:
                logger.info(
                    f"Orchestrator: scene {scene_id} all {counts['done']} shots complete, "
                    f"eligible for assembly"
                )
                await log_decision(
                    decision_type="orchestrator_scene_ready",
                    project_name=str(project_id),
                    input_context={"scene_id": scene_id, "shots_done": counts["done"]},
                    decision_made="scene_ready_for_assembly",
                    confidence_score=1.0,
                    reasoning=f"All {counts['done']} shots generated for scene {scene_id}",
                )
    except Exception as e:
        logger.error(f"Orchestrator: scene_ready handler failed for scene {scene_id}: {e}")


async def _handle_shot_generated(data: dict):
    """Log shot completion and update pipeline progress."""
    shot_id = data.get("shot_id")
    project_id = data.get("project_id")
    engine = data.get("video_engine", "unknown")
    gen_time = data.get("generation_time", 0)

    logger.info(
        f"Orchestrator: shot {shot_id} generated via {engine} in {gen_time:.0f}s"
    )

    if not project_id:
        return

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Update video_generation phase progress
            progress = await conn.fetchrow("""
                SELECT
                    (SELECT COUNT(*) FROM shots sh
                     JOIN scenes sc ON sh.scene_id = sc.id
                     WHERE sc.project_id = $1
                       AND sh.status IN ('completed', 'accepted_best')
                       AND sh.output_video_path IS NOT NULL) as done,
                    (SELECT COUNT(*) FROM shots sh
                     JOIN scenes sc ON sh.scene_id = sc.id
                     WHERE sc.project_id = $1) as total
            """, project_id)

            if progress:
                await conn.execute("""
                    UPDATE production_pipeline
                    SET progress_current = $1, progress_target = $2, updated_at = NOW()
                    WHERE entity_type = 'project' AND project_id = $3
                      AND phase = 'video_generation'
                      AND status NOT IN ('completed', 'skipped')
                """, progress["done"], progress["total"], project_id)
    except Exception as e:
        logger.warning(f"Orchestrator: shot_generated progress update failed: {e}")


async def _handle_episode_assembled(data: dict):
    """Log episode assembly completion."""
    project_id = data.get("project_id")
    episode_id = data.get("episode_id")
    episode_num = data.get("episode_number", "?")

    logger.info(f"Orchestrator: episode {episode_num} assembled for project {project_id}")

    await log_decision(
        decision_type="orchestrator_episode_assembled",
        project_name=str(project_id),
        input_context=data,
        decision_made="episode_assembled",
        confidence_score=1.0,
        reasoning=f"Episode {episode_num} video assembled from scene videos",
    )

    # Auto-advance episode_assembly phase if all episodes are assembled
    if not project_id:
        return

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            unassembled = await conn.fetchval("""
                SELECT COUNT(*) FROM episodes
                WHERE project_id = $1 AND final_video_path IS NULL
            """, project_id)
            if unassembled == 0:
                entry = await conn.fetchrow("""
                    SELECT * FROM production_pipeline
                    WHERE entity_type = 'project' AND project_id = $1
                      AND phase = 'episode_assembly'
                      AND status NOT IN ('completed', 'skipped')
                """, project_id)
                if entry:
                    await _advance_phase_impl(conn, dict(entry), CHARACTER_PHASES, PROJECT_PHASES)
                    logger.info(
                        f"Orchestrator: episode_assembly → publishing "
                        f"(all episodes assembled for project {project_id})"
                    )
    except Exception as e:
        logger.error(f"Orchestrator: episode_assembled handler failed: {e}")


async def _handle_episode_published(data: dict):
    """Log publishing and send Telegram notification."""
    project_id = data.get("project_id")
    episode_num = data.get("episode_number", "?")
    published_path = data.get("published_path", "")

    logger.info(f"Orchestrator: episode {episode_num} published to Jellyfin")

    await log_decision(
        decision_type="orchestrator_episode_published",
        project_name=str(project_id),
        input_context=data,
        decision_made="episode_published",
        confidence_score=1.0,
        reasoning=f"Episode {episode_num} published to Jellyfin at {published_path}",
    )

    # Best-effort Telegram notification
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            project_name = await conn.fetchval(
                "SELECT name FROM projects WHERE id = $1", project_id
            )

        import urllib.request
        payload = json.dumps({
            "method": "tools/call",
            "params": {
                "name": "send_notification",
                "arguments": {
                    "message": f"Episode {episode_num} of {project_name or project_id} published to Jellyfin",
                    "title": "Episode Published",
                    "channels": ["telegram"],
                    "priority": "normal",
                },
            },
        }).encode()
        req = urllib.request.Request(
            "http://localhost:8309/mcp",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.debug(f"Telegram notification failed (non-fatal): {e}")


def register_orchestrator_handlers():
    """Register EventBus handlers. Called once at startup."""
    event_bus.subscribe(IMAGE_APPROVED, _handle_image_approved)
    event_bus.subscribe(PIPELINE_PHASE_ADVANCED, _handle_phase_advanced)
    event_bus.subscribe(TRAINING_STARTED, _handle_training_started)
    event_bus.subscribe(SCENE_PLANNING_COMPLETE, _handle_scene_planning_complete)
    event_bus.subscribe(SCENE_READY, _handle_scene_ready)
    event_bus.subscribe(SHOT_GENERATED, _handle_shot_generated)
    event_bus.subscribe(EPISODE_ASSEMBLED, _handle_episode_assembled)
    event_bus.subscribe(EPISODE_PUBLISHED, _handle_episode_published)
    logger.info("Orchestrator EventBus handlers registered (8 events)")
