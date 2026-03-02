"""Production Orchestrator — FastAPI endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import orchestrator

router = APIRouter()


class ToggleRequest(BaseModel):
    enabled: bool = True


class InitializeRequest(BaseModel):
    project_id: int
    training_target: int | None = None


class OverrideRequest(BaseModel):
    entity_type: str  # "character" or "project"
    entity_id: str
    phase: str
    action: str  # "skip", "reset", "complete"


class TrainingTargetRequest(BaseModel):
    target: int


@router.get("/orchestrator/status")
async def get_status():
    """Global orchestrator on/off + config."""
    return {
        "enabled": orchestrator.is_enabled(),
        "training_target": orchestrator._training_target,
        "tick_interval": orchestrator._tick_interval,
    }


@router.post("/orchestrator/toggle")
async def toggle(req: ToggleRequest):
    """Enable or disable the orchestrator."""
    await orchestrator.enable(req.enabled)
    return {"enabled": orchestrator.is_enabled()}


@router.post("/orchestrator/initialize")
async def initialize(req: InitializeRequest):
    """Bootstrap pipeline entries for a project."""
    try:
        result = await orchestrator.initialize_project(
            req.project_id, req.training_target
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/orchestrator/pipeline/{project_id}")
async def pipeline_status(project_id: int):
    """Full structured pipeline status for dashboard."""
    return await orchestrator.get_pipeline_status(project_id)


@router.get("/orchestrator/summary/{project_id}")
async def pipeline_summary(project_id: int):
    """Human-readable summary for Echo Brain context."""
    text = await orchestrator.get_pipeline_summary(project_id)
    return {"project_id": project_id, "summary": text}


@router.post("/orchestrator/tick")
async def manual_tick():
    """Trigger a single evaluation pass."""
    result = await orchestrator.tick()
    return result


@router.post("/orchestrator/override")
async def override(req: OverrideRequest):
    """Force a phase status (skip, reset, complete)."""
    try:
        result = await orchestrator.override_phase(
            req.entity_type, req.entity_id, req.phase, req.action
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orchestrator/training-target")
async def set_training_target(req: TrainingTargetRequest):
    """Set the approved image threshold for training_data phase."""
    orchestrator.set_training_target(req.target)
    return {"training_target": orchestrator._training_target}
