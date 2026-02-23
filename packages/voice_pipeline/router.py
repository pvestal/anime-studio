"""Voice pipeline — diarization, training, synthesis.

Voice sample management routes (assignment, approval, streaming, stats)
are in voice_samples.py (included as sub-router).
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from packages.core.config import BASE_PATH
from packages.core.db import connect_direct, get_char_project_map
from packages.core.models import (
    VoiceDiarizeRequest, VoiceTrainRequest, VoiceSynthesizeRequest,
    VoiceSceneDialogueRequest,
)
from packages.voice_pipeline.diarization import diarize_project
from packages.voice_pipeline.cloning import (
    start_sovits_training, start_rvc_training, get_training_jobs,
    get_training_job, get_training_log, cancel_training_job,
)
from packages.voice_pipeline.synthesis import (
    synthesize_dialogue, get_voice_models,
    synthesize_scene_dialogue, generate_dialogue_from_story,
)

from .voice_samples import router as samples_router

logger = logging.getLogger(__name__)
router = APIRouter()
router.include_router(samples_router)

VOICE_BASE = BASE_PATH.parent
VOICE_DATASETS = VOICE_BASE / "voice_datasets"


# =============================================================================
# Phase A: Diarization
# =============================================================================

@router.post("/diarize")
async def run_diarization(body: VoiceDiarizeRequest):
    """Run pyannote speaker diarization on project audio."""
    result = await diarize_project(body.project_name)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/speakers/{project_name}")
async def list_speakers(project_name: str):
    """List speaker clusters for a project with segment counts."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch(
            "SELECT * FROM voice_speakers WHERE project_name = $1 ORDER BY speaker_label",
            project_name,
        )

        speakers = [dict(r) for r in rows]

        # Also check diarization_meta.json if DB is empty
        if not speakers:
            safe_project = project_name.lower().replace(" ", "_")[:50]
            meta_path = VOICE_BASE / "voice" / safe_project / "diarization_meta.json"
            if meta_path.exists():
                with open(meta_path) as f:
                    meta = json.load(f)

                # Seed DB from diarization metadata
                for spk in meta.get("speakers", []):
                    await conn.execute("""
                        INSERT INTO voice_speakers (speaker_label, project_name, segment_count,
                            total_duration_seconds, created_at)
                        VALUES ($1, $2, $3, $4, NOW())
                        ON CONFLICT DO NOTHING
                    """, spk["speaker_label"], project_name,
                        spk["segment_count"], spk["total_duration_seconds"])

                speakers = [dict(r) for r in await conn.fetch(
                    "SELECT * FROM voice_speakers WHERE project_name = $1 ORDER BY speaker_label",
                    project_name,
                )]

        return {"project_name": project_name, "speakers": speakers, "total": len(speakers)}
    finally:
        await conn.close()


# =============================================================================
# Phase C: Voice Clone Training
# =============================================================================

@router.post("/train/sovits")
async def train_sovits(body: VoiceTrainRequest):
    """Start GPT-SoVITS voice training for a character."""
    result = await start_sovits_training(
        character_slug=body.character_slug,
        character_name=body.character_name or "",
        project_name=body.project_name or "",
        epochs=body.epochs or 8,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/train/rvc")
async def train_rvc(body: VoiceTrainRequest):
    """Start RVC v2 voice training for a character."""
    result = await start_rvc_training(
        character_slug=body.character_slug,
        character_name=body.character_name or "",
        project_name=body.project_name or "",
        epochs=body.epochs or 40,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/train/jobs")
async def list_training_jobs(project_name: str = None, character_slug: str = None):
    """List all voice training jobs, optionally filtered."""
    jobs = await get_training_jobs(project_name=project_name, character_slug=character_slug)
    return {"jobs": jobs, "total": len(jobs)}


@router.get("/train/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get status of a specific training job."""
    job = await get_training_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")
    return job


@router.get("/train/jobs/{job_id}/log")
async def get_job_log(job_id: str, lines: int = 50):
    """Tail the log file of a training job."""
    log_text = get_training_log(job_id, lines=lines)
    return {"job_id": job_id, "log": log_text}


@router.post("/train/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running training job."""
    result = await cancel_training_job(job_id)
    return result


# =============================================================================
# Phase D: Voice Synthesis
# =============================================================================

@router.post("/synthesize")
async def synthesize(body: VoiceSynthesizeRequest):
    """Generate speech from text using character's voice model."""
    result = await synthesize_dialogue(
        character_slug=body.character_slug,
        text=body.text,
        engine=body.engine,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Record in DB
    conn = await connect_direct()
    try:
        import uuid
        job_id = f"synth_{uuid.uuid4().hex[:8]}"
        await conn.execute("""
            INSERT INTO voice_synthesis_jobs
                (job_id, character_slug, engine, text, output_path,
                 duration_seconds, status, created_at, completed_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'completed', NOW(), NOW())
        """, job_id, body.character_slug, result.get("engine_used", ""),
            body.text, result.get("output_path", ""),
            result.get("duration_seconds", 0))
        result["job_id"] = job_id
    finally:
        await conn.close()

    return result


@router.get("/synthesis/{job_id}")
async def get_synthesis_result(job_id: str):
    """Get synthesis job result."""
    conn = await connect_direct()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM voice_synthesis_jobs WHERE job_id = $1", job_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Synthesis job not found")
        return dict(row)
    finally:
        await conn.close()


@router.get("/synthesis/{job_id}/audio")
async def stream_synthesis_audio(job_id: str):
    """Stream synthesized audio WAV file."""
    conn = await connect_direct()
    try:
        output_path = await conn.fetchval(
            "SELECT output_path FROM voice_synthesis_jobs WHERE job_id = $1", job_id
        )
    finally:
        await conn.close()

    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(output_path, media_type="audio/wav")


@router.post("/scene/{scene_id}/dialogue")
async def generate_scene_dialogue(scene_id: str, body: VoiceSceneDialogueRequest):
    """Generate and synthesize dialogue for a scene.

    If dialogue_list is provided, synthesize those lines directly.
    If description + characters are provided, use LLM to generate dialogue first.
    """
    dialogue_list = body.dialogue_list

    if not dialogue_list and body.description and body.characters:
        dialogue_list = await generate_dialogue_from_story(
            scene_id=scene_id,
            description=body.description,
            characters=body.characters,
        )
        if not dialogue_list:
            raise HTTPException(status_code=400, detail="Failed to generate dialogue from description")

    if not dialogue_list:
        raise HTTPException(status_code=400, detail="Provide dialogue_list or description + characters")

    result = await synthesize_scene_dialogue(
        scene_id=scene_id,
        dialogue_list=dialogue_list,
        pause_seconds=body.pause_seconds or 0.5,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/models/{character_slug}")
async def available_voice_models(character_slug: str):
    """Get available voice models and engines for a character."""
    return await get_voice_models(character_slug)
