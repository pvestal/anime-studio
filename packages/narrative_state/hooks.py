"""NSM EventBus hooks — react to scene/shot/episode edits and propagate state changes.

Registered at startup via register_nsm_handlers().
"""

import logging

from packages.core.db import connect_direct
from packages.core.events import (
    event_bus,
    SCENE_UPDATED, SHOT_UPDATED, EPISODE_UPDATED,
    REGENERATION_NEEDED, STATE_UPDATED,
)
from .engine import narrative_engine

logger = logging.getLogger(__name__)


async def on_scene_updated(data: dict):
    """When a scene's description/mood/location changes, re-propagate states
    and detect impacted downstream shots.
    """
    scene_id = data.get("scene_id")
    if not scene_id:
        return

    conn = await connect_direct()
    try:
        scene = await conn.fetchrow(
            "SELECT project_id, scene_number FROM scenes WHERE id = $1", scene_id
        )
        if not scene:
            return

        project_id = scene["project_id"]

        # Check if this scene has states — if so, re-propagate forward
        states = await conn.fetch(
            "SELECT character_slug FROM character_scene_state WHERE scene_id = $1",
            scene_id,
        )
        if states:
            propagated = await narrative_engine.propagate_forward(scene_id, project_id)
            if propagated:
                logger.info(
                    f"NSM: Scene {scene_id} updated → propagated {len(propagated)} "
                    f"states to downstream scenes"
                )

        # Find downstream shots that may need regeneration
        downstream_scenes = await conn.fetch("""
            SELECT s.id, sh.id as shot_id, sh.status, sh.output_video_path
            FROM scenes s
            JOIN shots sh ON sh.scene_id = s.id
            WHERE s.project_id = $1
              AND s.scene_number > COALESCE($2, 0)
              AND sh.status IN ('completed', 'accepted_best')
              AND sh.output_video_path IS NOT NULL
        """, project_id, scene["scene_number"])

        for ds in downstream_scenes:
            # Queue regeneration for completed downstream shots
            await conn.execute("""
                INSERT INTO regeneration_queue
                    (scene_id, shot_id, reason, priority, source_scene_id, source_field, status)
                VALUES ($1, $2, $3, $4, $5, $6, 'pending')
                ON CONFLICT DO NOTHING
            """,
                ds["id"], ds["shot_id"],
                f"Upstream scene {scene_id} was edited",
                3,  # medium priority
                scene_id, "scene_description",
            )

        if downstream_scenes:
            await event_bus.emit(REGENERATION_NEEDED, {
                "source_scene_id": scene_id,
                "project_id": project_id,
                "queued_shots": len(downstream_scenes),
            })
            logger.info(
                f"NSM: Queued {len(downstream_scenes)} downstream shots for "
                f"regeneration after scene {scene_id} edit"
            )
    except Exception as e:
        logger.error(f"NSM on_scene_updated failed: {e}")
    finally:
        await conn.close()


async def on_shot_updated(data: dict):
    """When a shot's motion_prompt or characters change, mark it stale."""
    shot_id = data.get("shot_id")
    scene_id = data.get("scene_id")
    changed_fields = data.get("changed_fields", [])

    if not shot_id:
        return

    # Only care about content-changing fields
    content_fields = {"motion_prompt", "characters_present", "shot_type", "camera_angle"}
    if not (set(changed_fields) & content_fields):
        return

    conn = await connect_direct()
    try:
        shot = await conn.fetchrow(
            "SELECT status, output_video_path FROM shots WHERE id = $1", shot_id
        )
        if shot and shot["output_video_path"]:
            await conn.execute("""
                INSERT INTO regeneration_queue
                    (scene_id, shot_id, reason, priority, status)
                VALUES ($1, $2, $3, $4, 'pending')
            """, scene_id, shot_id, f"Shot content changed: {', '.join(changed_fields)}", 5)
            logger.info(f"NSM: Shot {shot_id} content changed, queued for regeneration")
    except Exception as e:
        logger.error(f"NSM on_shot_updated failed: {e}")
    finally:
        await conn.close()


async def on_episode_updated(data: dict):
    """When an episode is restructured, mark all its scenes as content-stale."""
    episode_id = data.get("episode_id")
    if not episode_id:
        return

    conn = await connect_direct()
    try:
        scenes = await conn.fetch("""
            SELECT es.scene_id, s.generation_status
            FROM episode_scenes es
            JOIN scenes s ON es.scene_id = s.id
            WHERE es.episode_id = $1
        """, episode_id)

        queued = 0
        for scene in scenes:
            if scene["generation_status"] == "completed":
                await conn.execute("""
                    INSERT INTO regeneration_queue
                        (scene_id, reason, priority, status)
                    VALUES ($1, $2, $3, 'pending')
                """, scene["scene_id"], f"Episode {episode_id} restructured", 2)
                queued += 1

        if queued:
            logger.info(
                f"NSM: Episode {episode_id} updated → {queued} scenes queued for review"
            )
    except Exception as e:
        logger.error(f"NSM on_episode_updated failed: {e}")
    finally:
        await conn.close()


async def on_state_updated(data: dict):
    """When a character state is manually overridden, propagate forward."""
    scene_id = data.get("scene_id")
    source = data.get("source")
    if not scene_id or source != "manual":
        return

    conn = await connect_direct()
    try:
        scene = await conn.fetchrow(
            "SELECT project_id FROM scenes WHERE id = $1", scene_id
        )
        if scene:
            propagated = await narrative_engine.propagate_forward(
                scene_id, scene["project_id"]
            )
            if propagated:
                logger.info(
                    f"NSM: Manual state override in scene {scene_id} → "
                    f"propagated {len(propagated)} downstream states"
                )
    except Exception as e:
        logger.error(f"NSM on_state_updated failed: {e}")
    finally:
        await conn.close()


def register_nsm_handlers():
    """Register all NSM handlers on the EventBus. Called once at startup."""
    event_bus.subscribe(SCENE_UPDATED, on_scene_updated)
    event_bus.subscribe(SHOT_UPDATED, on_shot_updated)
    event_bus.subscribe(EPISODE_UPDATED, on_episode_updated)
    event_bus.subscribe(STATE_UPDATED, on_state_updated)
    logger.info("EventBus: NSM handlers registered (scene/shot/episode/state)")
