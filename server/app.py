#!/usr/bin/env python3
"""
Tower Anime Studio v3.3 — Modular FastAPI application.

Domain-based API routing:
  /api/story/*      — projects, characters, storylines, world settings
  /api/visual/*     — image generation, gallery, vision review
  /api/scenes/*     — scene builder, shots, assembly
  /api/episodes/*   — episode CRUD, assembly, Jellyfin publish
  /api/training/*   — datasets, approvals, ingestion, LoRA training
  /api/audio/*      — audio analysis, voice segment extraction
  /api/echo/*       — Echo Brain chat, prompt enhancement
  /api/voice/*      — voice diarization, cloning, synthesis
  /api/system/*     — health, GPU, learning, replenishment, quality gates

Database credentials loaded from Vault (secret/anime/database).
"""

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from packages.core.auth import AuthMiddleware
from packages.core.config import APP_ENV
from packages.core.db import init_pool, get_pool, run_migrations
from packages.core.logging_config import setup_logging
from packages.core.events import event_bus
from packages.core.gpu_router import get_system_status
import packages.core.learning as learning  # registers EventBus handlers on import
import packages.core.auto_correction as auto_correction  # registers EventBus handler on import
import packages.core.replenishment as replenishment  # registers EventBus handler on import
import packages.core.orchestrator as orchestrator
from packages.core.model_selector import (
    recommend_params, detect_drift, character_quality_summary,
    checkpoint_comparison, suggest_exploration, explore_checkpoints,
)
from packages.lora_training.feedback import reconcile_training_jobs

from packages.story.router import router as story_router
from packages.visual_pipeline.router import router as visual_router
from packages.scene_generation.router import router as scene_router
from packages.scene_generation.full_pipeline import router as pipeline_router
from packages.lora_training.router import router as training_router
from packages.audio_composition.router import router as audio_router
from packages.echo_integration.router import router as echo_router
from packages.voice_pipeline.router import router as voice_router
from packages.episode_assembly.router import router as episode_router
from packages.core.graph_router import router as graph_router
from packages.testing import testing_router
from packages.core.orchestrator_router import router as orchestrator_router
from packages.narrative_state import narrative_router
from packages.interactive import interactive_router

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Tower Anime Studio", version="3.5")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)

# ── Domain Router Mounts ─────────────────────────────────────────────────
# Routers whose decorator paths are generic (no domain prefix):
app.include_router(story_router,    prefix="/api/story",    tags=["story"])
app.include_router(visual_router,   prefix="/api/visual",   tags=["visual"])
app.include_router(training_router, prefix="/api/training", tags=["training"])
app.include_router(audio_router,    prefix="/api/audio",    tags=["audio"])

# Routers whose decorator paths already include their domain prefix:
app.include_router(scene_router,   prefix="/api", tags=["scenes"])      # /api/scenes/*
app.include_router(pipeline_router, prefix="/api", tags=["pipeline"])    # /api/scenes/produce-episode
app.include_router(echo_router,    prefix="/api", tags=["echo"])        # /api/echo/*
app.include_router(episode_router, prefix="/api", tags=["episodes"])    # /api/episodes/*

# voice_pipeline: prefix="/voice" removed from router, mounted here:
app.include_router(voice_router, prefix="/api/voice", tags=["voice"])   # /api/voice/*

# Graph analytics (Apache AGE):
app.include_router(graph_router, prefix="/api/graph", tags=["graph"])   # /api/graph/*

# Production orchestrator:
app.include_router(orchestrator_router, prefix="/api/system", tags=["orchestrator"])  # /api/system/orchestrator/*

# Narrative State Machine:
app.include_router(narrative_router, prefix="/api/narrative", tags=["narrative"])  # /api/narrative/*

# Interactive Visual Novel:
app.include_router(interactive_router, prefix="/api/interactive", tags=["interactive"])  # /api/interactive/*

# Prompt testing harness:
app.include_router(testing_router, prefix="/api/testing", tags=["testing"])  # /api/testing/*


@app.on_event("startup")
async def startup():
    await init_pool()
    await run_migrations()
    reconcile_training_jobs()

    # Register graph sync EventBus handlers
    from packages.core.events import register_graph_sync_handlers
    register_graph_sync_handlers()

    # Register orchestrator EventBus handlers + start tick loop
    orchestrator.register_orchestrator_handlers()
    await orchestrator.start_tick_loop()

    # Register NSM EventBus handlers
    from packages.narrative_state.hooks import register_nsm_handlers
    register_nsm_handlers()

    # Register voice pipeline event handlers (training completion → re-synthesis)
    from packages.voice_pipeline.event_handlers import register_voice_event_handlers
    register_voice_event_handlers()

    # Recover any shots stuck in 'generating' from before this restart
    from packages.scene_generation.builder import recover_interrupted_generations
    await recover_interrupted_generations()

    # Start interactive session cleanup loop
    from packages.interactive.session_store import store as interactive_store
    interactive_store.start_cleanup()

    logger.info("Tower Anime Studio v3.5 started — 10 packages + graph + orchestrator + NSM + interactive mounted")


# ── System Endpoints ─────────────────────────────────────────────────────


@app.get("/api/system/health")
async def health():
    return {"status": "healthy", "service": "tower-anime-studio", "version": "3.5", "env": APP_ENV}


@app.get("/api/system/db-health")
async def db_health():
    """Database connectivity check — returns healthy if SELECT 1 succeeds."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "healthy", "db_check": "ok"}
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Database unhealthy: {e}")


@app.get("/api/system/gpu/status")
async def gpu_status():
    """Full GPU dashboard — both GPUs + Ollama + ComfyUI."""
    return get_system_status()


@app.get("/api/system/events/stats")
async def events_stats():
    """EventBus statistics — registered handlers, emit count, errors."""
    return event_bus.stats()


# --- Learning System ---


@app.get("/api/system/learning/stats")
async def get_learning_stats():
    """Overall learning system statistics for last 30 days."""
    return await learning.learning_stats()


@app.get("/api/system/learning/suggest/{character_slug}")
async def get_suggestions(character_slug: str):
    """Suggest optimal generation parameters based on historical quality data."""
    params = await learning.suggest_params(character_slug)
    if not params:
        return {"character_slug": character_slug, "suggestions": None,
                "reason": f"Insufficient data (need {learning.MIN_SAMPLES}+ successful generations)"}
    return {"character_slug": character_slug, "suggestions": params}


@app.get("/api/system/learning/rejections/{character_slug}")
async def get_rejection_patterns(character_slug: str):
    """Top rejection categories for a character."""
    patterns = await learning.rejection_patterns(character_slug)
    return {"character_slug": character_slug, "patterns": patterns}


@app.get("/api/system/learning/checkpoints/{project_name}")
async def get_checkpoint_rankings(project_name: str):
    """Rank checkpoints by quality score for a project."""
    rankings = await learning.checkpoint_rankings(project_name)
    return {"project_name": project_name, "rankings": rankings}


@app.get("/api/system/learning/trend")
async def get_quality_trend(character_slug: str = None, project_name: str = None, days: int = 7):
    """Quality score trend over recent days."""
    if not character_slug and not project_name:
        return {"error": "Provide character_slug or project_name"}
    trend = await learning.quality_trend(character_slug=character_slug, project_name=project_name, days=days)
    return {"character_slug": character_slug, "project_name": project_name, "days": days, "trend": trend}


# --- Model Selector & Drift Detection ---


@app.get("/api/system/recommend/{character_slug}")
async def get_recommendations(character_slug: str):
    """Recommend optimal params for a character based on learned patterns."""
    rec = await recommend_params(character_slug)
    return {"character_slug": character_slug, "recommendation": rec}


@app.get("/api/system/drift")
async def get_drift(character_slug: str = None, project_name: str = None):
    """Detect quality drift — characters whose recent quality is declining."""
    if not character_slug and not project_name:
        pass
    alerts = await detect_drift(character_slug=character_slug, project_name=project_name)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/api/system/quality/summary/{project_name}")
async def get_quality_summary(project_name: str):
    """Per-character quality summary for a project."""
    summary = await character_quality_summary(project_name)
    return {"project_name": project_name, "characters": summary}


# --- Model Exploration ---


@app.get("/api/system/checkpoints/compare/{project_name}")
async def get_checkpoint_comparison(project_name: str):
    """Compare all checkpoints used in a project — ranked by quality and approval rate."""
    comparison = await checkpoint_comparison(project_name)
    return {"project_name": project_name, "checkpoints": comparison}


@app.get("/api/system/checkpoints/suggest/{character_slug}")
async def get_exploration_suggestions(character_slug: str, project_name: str = None):
    """Suggest untested or under-tested checkpoints to try for a character."""
    result = await suggest_exploration(character_slug, project_name or "")
    return result


from pydantic import BaseModel, Field


class ExploreRequest(BaseModel):
    checkpoints: list[str] | None = Field(None, description="Checkpoint filenames to test. Auto-suggests if empty.")
    images_per_checkpoint: int = Field(2, ge=1, le=5, description="Images to generate per checkpoint.")


@app.post("/api/system/checkpoints/explore/{character_slug}")
async def run_checkpoint_exploration(
    character_slug: str,
    body: ExploreRequest = ExploreRequest(),
):
    """Run multi-checkpoint A/B test — generates images with each checkpoint.

    Results flow through the normal vision review + approval pipeline.
    Query /api/system/checkpoints/compare/{project} afterward to see rankings.
    """
    results = await explore_checkpoints(
        character_slug=character_slug,
        checkpoints=body.checkpoints,
        images_per_checkpoint=body.images_per_checkpoint,
    )
    return {
        "character_slug": character_slug,
        "checkpoints_tested": len(results),
        "results": results,
    }


# --- Auto-Correction & Quality Gates ---


@app.get("/api/system/correction/stats")
async def get_correction_stats():
    """Auto-correction success rate and statistics."""
    return await auto_correction.get_correction_stats()


@app.post("/api/system/correction/toggle")
async def toggle_auto_correction(enabled: bool = True):
    """Enable or disable auto-correction on rejected images."""
    auto_correction.enable_auto_correction(enabled)
    return {"auto_correction_enabled": enabled}


@app.get("/api/system/quality/gates")
async def get_quality_gates():
    """Get all configured quality gates with thresholds."""
    gates = await auto_correction.get_quality_gates()
    return {"gates": gates}


@app.put("/api/system/quality/gates/{gate_name}")
async def update_gate(gate_name: str, threshold: float = None, is_active: bool = None):
    """Update a quality gate threshold or active status."""
    ok = await auto_correction.update_quality_gate(gate_name, threshold, is_active)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update quality gate")
    return {"gate_name": gate_name, "updated": True}


# --- Replenishment Loop ---


@app.get("/api/system/replenishment/status")
async def get_replenishment_status():
    """Get replenishment loop status — enabled, active tasks, daily counts."""
    return await replenishment.status()


@app.post("/api/system/replenishment/toggle")
async def toggle_replenishment(enabled: bool = True):
    """Enable or disable the autonomous replenishment loop."""
    replenishment.enable(enabled)
    return {"replenishment_enabled": enabled}


@app.post("/api/system/replenishment/target")
async def set_replenishment_target(target: int = 20, character_slug: str = None):
    """Set the target approved image count (global or per-character)."""
    replenishment.set_target(character_slug=character_slug, target=target)
    return {
        "target": target,
        "character_slug": character_slug,
        "scope": "character" if character_slug else "global",
    }


@app.get("/api/system/replenishment/readiness")
async def get_character_readiness(project_name: str = None):
    """Get readiness status for all characters — approved vs target counts."""
    chars = await replenishment.character_readiness(project_name=project_name)
    ready = sum(1 for c in chars if c["ready"])
    return {
        "project_name": project_name,
        "characters": chars,
        "total": len(chars),
        "ready": ready,
        "deficit": len(chars) - ready,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8401)
