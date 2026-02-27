"""Narrative State Machine API endpoints."""

import logging
import uuid

from fastapi import APIRouter, HTTPException

from packages.core.db import connect_direct
from packages.core.events import event_bus, STATE_INITIALIZED, STATE_UPDATED, STATE_PROPAGATED
from .engine import narrative_engine
from .models import CharacterStateUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/state/{scene_id}")
async def get_scene_states(scene_id: str):
    """Get all character states for a scene."""
    sid = uuid.UUID(scene_id)
    states = await narrative_engine.get_scene_states(str(sid))
    return {"scene_id": scene_id, "states": states}


@router.get("/state/{scene_id}/{character_slug}")
async def get_character_state(scene_id: str, character_slug: str):
    """Get a single character's state for a scene."""
    sid = uuid.UUID(scene_id)
    state = await narrative_engine.get_state(str(sid), character_slug)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    return state


@router.put("/state/{scene_id}/{character_slug}")
async def set_character_state(
    scene_id: str, character_slug: str, body: CharacterStateUpdate,
):
    """Manual override for a character's state in a scene."""
    sid = uuid.UUID(scene_id)
    state_dict = body.model_dump(exclude_none=True)
    if not state_dict:
        raise HTTPException(status_code=400, detail="No fields provided")

    result = await narrative_engine.set_state(
        str(sid), character_slug, state_dict, source="manual"
    )
    await event_bus.emit(STATE_UPDATED, {
        "scene_id": scene_id,
        "character_slug": character_slug,
        "source": "manual",
    })
    return result


@router.delete("/state/{scene_id}/{character_slug}")
async def delete_character_state(scene_id: str, character_slug: str):
    """Remove manual override, allowing re-propagation."""
    sid = uuid.UUID(scene_id)
    deleted = await narrative_engine.delete_state(str(sid), character_slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="State not found")
    return {"message": "State removed", "scene_id": scene_id, "character_slug": character_slug}


@router.post("/state/{scene_id}/initialize")
async def initialize_states(scene_id: str):
    """AI-seed character states from scene description via Ollama."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow("SELECT project_id FROM scenes WHERE id = $1", sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        project_id = scene["project_id"]
    finally:
        await conn.close()

    results = await narrative_engine.initialize_from_description(str(sid), project_id)
    if results:
        await event_bus.emit(STATE_INITIALIZED, {
            "scene_id": scene_id,
            "project_id": project_id,
            "characters": [r["character_slug"] for r in results],
        })
    return {
        "scene_id": scene_id,
        "initialized": len(results),
        "states": results,
    }


@router.post("/state/{scene_id}/propagate")
async def propagate_states(scene_id: str):
    """Forward-propagate states to downstream scenes."""
    sid = uuid.UUID(scene_id)
    conn = await connect_direct()
    try:
        scene = await conn.fetchrow("SELECT project_id FROM scenes WHERE id = $1", sid)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        project_id = scene["project_id"]
    finally:
        await conn.close()

    propagated = await narrative_engine.propagate_forward(str(sid), project_id)
    if propagated:
        await event_bus.emit(STATE_PROPAGATED, {
            "source_scene_id": scene_id,
            "project_id": project_id,
            "propagated_count": len(propagated),
        })
    return {
        "source_scene_id": scene_id,
        "propagated": len(propagated),
        "states": propagated,
    }


@router.get("/timeline/{project_id}/{character_slug}")
async def get_timeline(project_id: int, character_slug: str):
    """Full state evolution for a character across all scenes in a project."""
    timeline = await narrative_engine.get_timeline(project_id, character_slug)
    return {
        "project_id": project_id,
        "character_slug": character_slug,
        "scenes": timeline,
    }


@router.get("/regeneration-queue/{project_id}")
async def get_regeneration_queue(project_id: int):
    """View pending regeneration items (Phase 2)."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT rq.*, s.title as scene_title
            FROM regeneration_queue rq
            JOIN scenes s ON rq.scene_id = s.id
            WHERE s.project_id = $1 AND rq.status = 'pending'
            ORDER BY rq.priority DESC, rq.created_at
        """, project_id)
        return {
            "project_id": project_id,
            "items": [
                {
                    "id": r["id"],
                    "scene_id": str(r["scene_id"]),
                    "scene_title": r["scene_title"],
                    "shot_id": str(r["shot_id"]) if r["shot_id"] else None,
                    "reason": r["reason"],
                    "priority": r["priority"],
                    "source_scene_id": str(r["source_scene_id"]) if r["source_scene_id"] else None,
                    "source_field": r["source_field"],
                    "status": r["status"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in rows
            ],
        }
    finally:
        await conn.close()


@router.post("/regeneration-queue/process")
async def process_regeneration_queue():
    """Process pending regeneration queue items (Phase 2)."""
    conn = await connect_direct()
    try:
        pending = await conn.fetch(
            "SELECT * FROM regeneration_queue WHERE status = 'pending' "
            "ORDER BY priority DESC, created_at LIMIT 10"
        )
        processed = 0
        for item in pending:
            await conn.execute(
                "UPDATE regeneration_queue SET status = 'processed', "
                "processed_at = now() WHERE id = $1",
                item["id"],
            )
            processed += 1

        return {"processed": processed, "remaining": len(pending) - processed}
    finally:
        await conn.close()


@router.post("/tag-images/{character_slug}")
async def tag_character_images(character_slug: str, project_name: str = None, limit: int = 50):
    """Batch auto-tag approved images for a character (Phase 1b)."""
    from .image_tagger import batch_tag_character_images
    result = await batch_tag_character_images(character_slug, project_name, limit)
    return result


@router.post("/fill-gaps/{project_id}")
async def fill_state_gaps(project_id: int, dry_run: bool = True):
    """Find and fill missing state images (Phase 3)."""
    from .state_generation import fill_state_gaps as _fill_gaps
    result = await _fill_gaps(project_id, dry_run=dry_run)
    return result
