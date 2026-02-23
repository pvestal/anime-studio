"""
Story Engine API Routes
Provides REST endpoints for story bible management, generation triggers,
queue status, and semantic search.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import logging

# Import from existing story engine modules
import sys
import os
sys.path.insert(0, '/opt/anime-studio')

from services.story_engine.story_manager import StoryManager
from services.story_engine.change_propagation import ChangePropagator
from services.story_engine.vector_store import StoryVectorStore
from services.story_engine.orchestrator import SceneOrchestrator
from services.story_engine.models import (
    CharacterCreate, EpisodeCreate, SceneCreate, StoryArcCreate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/story", tags=["Story Engine"])

# Initialize singletons
story_manager = StoryManager()
propagator = ChangePropagator()
vector_store = StoryVectorStore()
orchestrator = SceneOrchestrator()


# ── Health ────────────────────────────────────────────────────

@router.get("/health")
async def story_health():
    """Story engine health check with queue and vector stats."""
    queue_status = propagator.get_queue_status()
    vector_stats = vector_store.get_collection_stats()
    return {"status": "ok", "queue": queue_status, "vectors": vector_stats}


# ── Characters ────────────────────────────────────────────────

@router.post("/characters")
async def create_character(data: CharacterCreate):
    try:
        return story_manager.create_character(data)
    except Exception as e:
        logger.error(f"Failed to create character: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/characters/{project_id}")
async def list_characters(project_id: int):
    return story_manager.get_characters_for_project(project_id)

@router.patch("/characters/{character_id}")
async def update_character(character_id: int, updates: dict):
    try:
        return story_manager.update_character(character_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update character: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Episodes ──────────────────────────────────────────────────

@router.post("/episodes")
async def create_episode(data: EpisodeCreate):
    try:
        return story_manager.create_episode(data)
    except Exception as e:
        logger.error(f"Failed to create episode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Scenes ────────────────────────────────────────────────────

@router.post("/scenes")
async def create_scene(data: SceneCreate):
    try:
        return story_manager.create_scene(data)
    except Exception as e:
        logger.error(f"Failed to create scene: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/scenes/{scene_id}/context")
async def get_scene_context(scene_id: str):
    """Get full generation context for a scene: characters, profiles, rules, arcs."""
    # scene_id is UUID string
    context = story_manager.get_scene_with_context(scene_id)
    if not context:
        raise HTTPException(status_code=404, detail="Scene not found")
    return context


# ── Story Arcs ────────────────────────────────────────────────

@router.post("/arcs")
async def create_arc(data: StoryArcCreate):
    try:
        return story_manager.create_story_arc(data)
    except Exception as e:
        logger.error(f"Failed to create story arc: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ArcLinkRequest(BaseModel):
    arc_id: int
    scene_id: Optional[str] = None  # UUID string
    episode_id: Optional[str] = None  # UUID string
    relevance: float = 1.0
    arc_phase: str = "rising"
    tension: float = 0.5

@router.post("/arcs/link")
async def link_arc(data: ArcLinkRequest):
    try:
        if data.scene_id:
            story_manager.link_arc_to_scene(data.arc_id, data.scene_id, data.relevance)
        if data.episode_id:
            story_manager.link_arc_to_episode(data.arc_id, data.episode_id, data.arc_phase, data.tension)
        return {"status": "linked"}
    except Exception as e:
        logger.error(f"Failed to link arc: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Production Profiles ───────────────────────────────────────

class ProfileRequest(BaseModel):
    project_id: int
    profile_type: str
    settings: dict

@router.post("/profiles")
async def set_profile(data: ProfileRequest):
    try:
        story_manager.set_production_profile(data.project_id, data.profile_type, data.settings)
        return {"status": "saved"}
    except Exception as e:
        logger.error(f"Failed to set profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── World Rules ───────────────────────────────────────────────

class WorldRuleRequest(BaseModel):
    project_id: int
    category: str
    key: str
    value: str
    priority: int = 50

@router.post("/rules")
async def set_rule(data: WorldRuleRequest):
    try:
        story_manager.set_world_rule(data.project_id, data.category, data.key, data.value, data.priority)
        return {"status": "saved"}
    except Exception as e:
        logger.error(f"Failed to set world rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Generation Triggers ───────────────────────────────────────

class GenerateRequest(BaseModel):
    scene_id: str  # UUID string
    scopes: Optional[list[str]] = None  # None = all. Options: writing, visual, audio, composition

@router.post("/generate/scene")
async def generate_scene(data: GenerateRequest):
    """Trigger the full generation pipeline for a scene."""
    # Import here to avoid circular imports — orchestrator imports agents
    try:
        from services.story_engine.orchestrator import SceneOrchestrator
        orchestrator = SceneOrchestrator()
        result = orchestrator.generate_scene(data.scene_id, scopes=data.scopes)
        return result
    except ImportError:
        # Orchestrator not yet implemented
        return {"status": "not_implemented", "message": "Scene orchestrator not yet available"}
    except Exception as e:
        logger.error(f"Failed to generate scene: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate/episode/{episode_id}")
async def generate_episode(episode_id: str):
    """Generate all scenes in an episode."""
    try:
        from services.story_engine.orchestrator import SceneOrchestrator
        orchestrator = SceneOrchestrator()
        return orchestrator.generate_episode(episode_id)
    except ImportError:
        return {"status": "not_implemented", "message": "Scene orchestrator not yet available"}
    except Exception as e:
        logger.error(f"Failed to generate episode: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate/process-queue")
async def process_queue(limit: int = 10):
    """Process pending items from the generation queue."""
    try:
        from services.story_engine.orchestrator import SceneOrchestrator
        orchestrator = SceneOrchestrator()
        results = orchestrator.process_queue(limit=limit)
        return {"processed": len(results), "results": results}
    except ImportError:
        return {"status": "not_implemented", "message": "Scene orchestrator not yet available"}
    except Exception as e:
        logger.error(f"Failed to process queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Queue Management ──────────────────────────────────────────

@router.get("/queue/status")
async def queue_status():
    return propagator.get_queue_status()

@router.get("/queue/stale/{project_id}")
async def stale_scenes(project_id: int):
    return propagator.get_stale_scenes(project_id)

@router.post("/queue/propagate")
async def trigger_propagation():
    """Manually trigger change propagation."""
    results = propagator.process_pending_changes()
    return {"processed": len(results), "jobs": results}


# ── Semantic Search ───────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    project_id: Optional[int] = None
    content_type: Optional[str] = None  # character, scene, episode, arc, dialogue
    limit: int = 10

@router.post("/search")
async def semantic_search(data: SearchRequest):
    try:
        results = vector_store.search(
            query=data.query,
            project_id=data.project_id,
            content_type=data.content_type,
            limit=data.limit,
        )
        return {"results": results, "count": len(results)}
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Reality Feed ──────────────────────────────────────────────

class RealityEventRequest(BaseModel):
    source: str         # echo_brain_log, git_commit, comfyui_error, manual
    event_type: str     # bug_fix, architecture_change, generation_failure, eureka_moment
    content: str
    project_id: Optional[int] = None
    tags: Optional[list[str]] = None

@router.post("/reality-feed")
async def log_reality_event(data: RealityEventRequest):
    try:
        return story_manager.log_reality_event(
            source=data.source, event_type=data.event_type,
            content=data.content, project_id=data.project_id, tags=data.tags,
        )
    except Exception as e:
        logger.error(f"Failed to log reality event: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/reality-feed/unrated")
async def get_unrated_events(limit: int = 20):
    try:
        return story_manager.get_unrated_reality_events(limit=limit)
    except Exception as e:
        logger.error(f"Failed to get unrated events: {e}")
        raise HTTPException(status_code=500, detail=str(e))