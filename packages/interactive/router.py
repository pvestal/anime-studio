"""FastAPI endpoints for interactive visual novel."""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .engine import start_session, generate_scene
from .image_gen import start_image_generation, get_image_status
from .models import StartSessionRequest, ChoiceRequest
from .session_store import store

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/sessions")
async def create_session(req: StartSessionRequest):
    """Start a new interactive visual novel session."""
    try:
        session, opening_scene = await start_session(req.project_id, req.character_slugs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception("Failed to start session")
        raise HTTPException(status_code=500, detail="Failed to start session — is Ollama running?")

    # Fire off image generation for the opening scene
    await start_image_generation(session, 0, opening_scene.image_prompt)

    return {
        "session_id": session.session_id,
        "scene": opening_scene.model_dump(),
        "image": get_image_status(session, 0),
    }


@router.get("/sessions")
async def list_sessions():
    """List all active sessions."""
    return {"sessions": store.list_sessions()}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session state."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session.session_id,
        "project_id": session.project_id,
        "project_name": session.project_name,
        "scene_count": len(session.scenes),
        "current_scene_index": session.current_scene_index,
        "is_ended": session.is_ended,
        "relationships": session.relationships,
        "variables": session.variables,
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """End and remove a session."""
    if store.delete(session_id):
        return {"message": "Session ended"}
    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions/{session_id}/scene")
async def get_current_scene(session_id: str):
    """Get the current scene."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.scenes:
        raise HTTPException(status_code=404, detail="No scenes yet")

    idx = session.current_scene_index
    return {
        "scene": session.scenes[idx],
        "image": get_image_status(session, idx),
    }


@router.post("/sessions/{session_id}/choose")
async def submit_choice(session_id: str, req: ChoiceRequest):
    """Submit a player choice and get the next scene."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.is_ended:
        raise HTTPException(status_code=400, detail="Session has ended")

    current = session.scenes[-1] if session.scenes else None
    if not current:
        raise HTTPException(status_code=400, detail="No current scene")

    choices = current.get("choices", [])
    if req.choice_index < 0 or req.choice_index >= len(choices):
        raise HTTPException(status_code=400, detail=f"Invalid choice index (0-{len(choices)-1})")

    choice_text = choices[req.choice_index]["text"]

    try:
        next_scene = await generate_scene(session, choice_text)
    except Exception:
        logger.exception("Failed to generate next scene")
        raise HTTPException(status_code=500, detail="Failed to generate scene")

    scene_idx = session.current_scene_index
    await start_image_generation(session, scene_idx, next_scene.image_prompt)

    return {
        "scene": next_scene.model_dump(),
        "image": get_image_status(session, scene_idx),
        "session_ended": session.is_ended,
    }


@router.get("/sessions/{session_id}/image/{scene_idx}")
async def image_status(session_id: str, scene_idx: int):
    """Get image generation status for a scene."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return get_image_status(session, scene_idx)


@router.get("/sessions/{session_id}/image/{scene_idx}/file")
async def serve_image(session_id: str, scene_idx: int):
    """Serve the generated image file."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    info = session.images.get(scene_idx)
    if not info or info.get("status") != "ready":
        raise HTTPException(status_code=404, detail="Image not ready")

    path = Path(info["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")

    return FileResponse(path, media_type="image/png")


@router.get("/sessions/{session_id}/history")
async def get_history(session_id: str):
    """Get full scene history for a session."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "scenes": session.scenes,
        "relationships": session.relationships,
        "variables": session.variables,
        "is_ended": session.is_ended,
    }
