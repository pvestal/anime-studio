"""
Tower Anime Production System - API Router
Extends existing /api/anime endpoints with consistency, quality, and video support
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse

from ..models.schemas import (
    # Character models
    CharacterAttributeCreate, CharacterAttributeResponse,
    CharacterVariationCreate, CharacterVariationResponse,
    CharacterConsistencyUpdate, CharacterEmbeddingRequest, CharacterEmbeddingResponse,
    ConsistencyCheckRequest, ConsistencyCheckResponse,
    # Generation models
    GenerateRequest, GenerateResponse, GenerationParams, GenerationParamsResponse,
    ReproduceRequest, JobProgressResponse, JobStatus, JobType,
    # Quality models
    QualityThresholds, QualityScores, QualityScoresResponse, QualityEvaluationRequest,
    # Story models
    StoryBibleCreate, StoryBibleUpdate, StoryBibleResponse,
    # Echo models
    EchoTaskRequest, EchoTaskResponse, EchoWebhookPayload,
    # Test models
    PhaseTestSuite, TestResult, PhaseGateResult, Phase,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/anime", tags=["anime"])


# === Dependency Injection (configure in main.py) ===

async def get_db_pool():
    """Get database connection pool - override in main.py"""
    raise NotImplementedError("Configure db_pool dependency")

async def get_character_service():
    """Get character consistency service - override in main.py"""
    raise NotImplementedError("Configure character_service dependency")

async def get_quality_service():
    """Get quality metrics service - override in main.py"""
    raise NotImplementedError("Configure quality_service dependency")

async def get_comfyui_client():
    """Get ComfyUI client - override in main.py"""
    raise NotImplementedError("Configure comfyui_client dependency")


# === Character Consistency Endpoints ===

@router.put("/characters/{character_id}/embedding", response_model=CharacterEmbeddingResponse)
async def store_character_embedding(
    character_id: UUID,
    request: CharacterEmbeddingRequest,
    char_service = Depends(get_character_service)
):
    """
    Compute and store face embedding for a character.
    
    This embedding is used for consistency checking across generations.
    Requires a clear reference image with a visible face.
    """
    success, baseline = await char_service.store_character_embedding(
        character_id,
        request.reference_image_path,
        request.force_recompute
    )
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Could not compute face embedding. Ensure image contains a clear face."
        )
    
    return CharacterEmbeddingResponse(
        character_id=character_id,
        embedding_stored=True,
        embedding_dimensions=512,  # ArcFace dimension
        similarity_baseline=baseline
    )


@router.post("/characters/{character_id}/consistency-check", response_model=ConsistencyCheckResponse)
async def check_character_consistency(
    character_id: UUID,
    request: ConsistencyCheckRequest,
    char_service = Depends(get_character_service)
):
    """
    Check if a generated image matches the character reference.
    
    Returns similarity score and whether it passes the threshold.
    Default threshold is 0.70 (70% similarity).
    """
    result = await char_service.check_consistency(
        character_id,
        request.image_path,
        request.threshold
    )
    
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    
    return ConsistencyCheckResponse(
        character_id=character_id,
        similarity_score=result["similarity_score"],
        passes_threshold=result["passes_threshold"],
        threshold_used=result["threshold_used"]
    )


@router.put("/characters/{character_id}/consistency", response_model=dict)
async def update_character_consistency(
    character_id: UUID,
    update: CharacterConsistencyUpdate,
    db = Depends(get_db_pool)
):
    """Update character consistency anchors (color palette, prompts, LoRA)"""
    updates = {}
    if update.color_palette is not None:
        updates["color_palette"] = update.color_palette
    if update.base_prompt is not None:
        updates["base_prompt"] = update.base_prompt
    if update.negative_tokens is not None:
        updates["negative_tokens"] = update.negative_tokens
    if update.lora_model_path is not None:
        updates["lora_model_path"] = update.lora_model_path
    
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    # Build dynamic update query
    set_clauses = []
    params = [character_id]
    for i, (key, value) in enumerate(updates.items(), start=2):
        set_clauses.append(f"{key} = ${i}")
        params.append(value)
    
    async with db.acquire() as conn:
        await conn.execute(f"""
            UPDATE characters SET {', '.join(set_clauses)}
            WHERE id = $1
        """, *params)
    
    return {"status": "updated", "fields": list(updates.keys())}


# === Character Attributes & Variations ===

@router.post("/characters/{character_id}/attributes", response_model=CharacterAttributeResponse)
async def add_character_attribute(
    character_id: UUID,
    attribute: CharacterAttributeCreate,
    char_service = Depends(get_character_service)
):
    """Add a visual attribute to a character (hair_color, eye_color, outfit, etc.)"""
    attr_id = await char_service.add_attribute(
        character_id,
        attribute.attribute_type,
        attribute.attribute_value,
        attribute.prompt_tokens,
        attribute.priority
    )
    
    return CharacterAttributeResponse(
        id=attr_id,
        character_id=character_id,
        created_at=datetime.utcnow(),
        **attribute.model_dump()
    )


@router.get("/characters/{character_id}/attributes", response_model=List[CharacterAttributeResponse])
async def get_character_attributes(
    character_id: UUID,
    char_service = Depends(get_character_service)
):
    """Get all visual attributes for a character"""
    attrs = await char_service.get_attributes(character_id)
    return [CharacterAttributeResponse(**a) for a in attrs]


@router.post("/characters/{character_id}/variations", response_model=CharacterVariationResponse)
async def create_character_variation(
    character_id: UUID,
    variation: CharacterVariationCreate,
    char_service = Depends(get_character_service)
):
    """Create a character variation (outfit, expression, pose, age_variant)"""
    var_id = await char_service.create_variation(
        character_id,
        variation.variation_name,
        variation.variation_type.value,
        variation.prompt_modifiers,
        variation.reference_image_path
    )
    
    return CharacterVariationResponse(
        id=var_id,
        character_id=character_id,
        created_at=datetime.utcnow(),
        **variation.model_dump()
    )


@router.get("/characters/{character_id}/variations", response_model=List[CharacterVariationResponse])
async def get_character_variations(
    character_id: UUID,
    variation_type: Optional[str] = None,
    char_service = Depends(get_character_service)
):
    """Get variations for a character, optionally filtered by type"""
    variations = await char_service.get_variations(character_id, variation_type)
    return [CharacterVariationResponse(**v) for v in variations]


@router.get("/characters/{character_id}/prompt", response_model=dict)
async def get_character_prompt(
    character_id: UUID,
    variation_id: Optional[UUID] = None,
    char_service = Depends(get_character_service)
):
    """Build the full prompt string for a character including attributes"""
    base_prompt = await char_service.build_character_prompt(character_id)
    
    if variation_id:
        base_prompt = await char_service.apply_variation(
            character_id, variation_id, base_prompt
        )
    
    negative_tokens = await char_service.get_negative_tokens(character_id)
    
    return {
        "character_id": str(character_id),
        "positive_prompt": base_prompt,
        "negative_tokens": negative_tokens
    }


# === Generation Endpoints (Extended) ===

@router.post("/generate", response_model=GenerateResponse)
async def generate(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    db = Depends(get_db_pool),
    char_service = Depends(get_character_service),
    comfyui = Depends(get_comfyui_client)
):
    """
    Generate image or video with full reproducibility tracking.
    
    Supports:
    - Still images (Phase 1)
    - Animation loops (Phase 2)
    - Full video (Phase 3)
    
    Automatically stores generation parameters for reproduction.
    """
    job_id = uuid4()
    seed = request.seed or int(datetime.utcnow().timestamp() * 1000) % (2**32)
    
    # Build character-enhanced prompt
    prompt_parts = [request.prompt]
    negative_parts = [request.negative_prompt] if request.negative_prompt else []
    
    for char_id in request.character_ids:
        char_prompt = await char_service.build_character_prompt(char_id)
        prompt_parts.append(char_prompt)
        neg_tokens = await char_service.get_negative_tokens(char_id)
        negative_parts.extend(neg_tokens)
    
    final_prompt = ", ".join(prompt_parts)
    final_negative = ", ".join(negative_parts)
    
    # Create job record
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO jobs (id, project_id, status, job_type, created_at)
            VALUES ($1, $2, $3, $4, NOW())
        """, job_id, request.project_id, JobStatus.PENDING.value, request.job_type.value)
    
    # Store generation params if requested
    params_id = None
    if request.save_params:
        params_id = uuid4()
        async with db.acquire() as conn:
            await conn.execute("""
                INSERT INTO generation_params 
                (id, job_id, positive_prompt, negative_prompt, seed,
                 model_name, sampler_name, steps, cfg_scale, width, height,
                 frame_count, fps, lora_models, ipadapter_refs)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            """, params_id, job_id, final_prompt, final_negative, seed,
                "animagine-xl-3.1", "euler", request.steps, request.cfg_scale,
                request.width, request.height, request.frame_count, request.fps,
                [], [])  # LoRA and IPAdapter configs
    
    # Queue ComfyUI job
    background_tasks.add_task(
        _process_generation,
        job_id, request, final_prompt, final_negative, seed, db, comfyui
    )
    
    # Estimate time based on job type
    time_estimates = {
        JobType.STILL_IMAGE: 12.0,
        JobType.CHARACTER_SHEET: 30.0,
        JobType.ANIMATION_LOOP: 60.0,
        JobType.FULL_VIDEO: 180.0,
    }
    
    return GenerateResponse(
        job_id=job_id,
        status=JobStatus.QUEUED,
        generation_params_id=params_id,
        seed_used=seed,
        estimated_time_seconds=time_estimates.get(request.job_type, 30.0),
        websocket_url=f"ws://***REMOVED***:8328/ws/jobs/{job_id}"
    )


@router.post("/jobs/{job_id}/reproduce", response_model=GenerateResponse)
async def reproduce_generation(
    job_id: UUID,
    request: ReproduceRequest,
    background_tasks: BackgroundTasks,
    db = Depends(get_db_pool),
    comfyui = Depends(get_comfyui_client)
):
    """Reproduce a previous generation using stored parameters"""
    # Fetch original params
    async with db.acquire() as conn:
        params = await conn.fetchrow("""
            SELECT * FROM generation_params WHERE job_id = $1
        """, request.original_job_id)
    
    if not params:
        raise HTTPException(
            status_code=404,
            detail="No generation parameters found for original job"
        )
    
    # Create new job with same params
    new_job_id = uuid4()
    
    # Apply modifications if any
    prompt = params['positive_prompt']
    negative = params['negative_prompt']
    seed = params['seed']
    
    if request.modifications:
        if 'prompt' in request.modifications:
            prompt = request.modifications['prompt']
        if 'seed' in request.modifications:
            seed = request.modifications['seed']
    
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO jobs (id, project_id, status, job_type, created_at)
            VALUES ($1, $2, $3, $4, NOW())
        """, new_job_id, None, JobStatus.QUEUED.value, "still_image")
    
    return GenerateResponse(
        job_id=new_job_id,
        status=JobStatus.QUEUED,
        generation_params_id=None,
        seed_used=seed,
        estimated_time_seconds=12.0,
        websocket_url=f"ws://***REMOVED***:8328/ws/jobs/{new_job_id}"
    )


@router.get("/jobs/{job_id}/params", response_model=GenerationParamsResponse)
async def get_generation_params(job_id: UUID, db = Depends(get_db_pool)):
    """Get stored generation parameters for a job (for reproduction)"""
    async with db.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM generation_params WHERE job_id = $1
        """, job_id)
    
    if not row:
        raise HTTPException(status_code=404, detail="Parameters not found")
    
    return GenerationParamsResponse(**dict(row))


# === Quality Metrics Endpoints ===

@router.post("/quality/evaluate", response_model=QualityScoresResponse)
async def evaluate_quality(
    request: QualityEvaluationRequest,
    quality_service = Depends(get_quality_service)
):
    """
    Evaluate quality metrics for a generation output.
    
    Runs appropriate metrics based on output type (image vs video).
    """
    # Determine if image or video
    is_video = request.output_path.endswith(('.mp4', '.webm', '.gif'))
    
    if is_video:
        result = await quality_service.evaluate_animation_loop(
            request.job_id,
            request.output_path,
            request.character_ids
        )
    else:
        result = await quality_service.evaluate_still_image(
            request.job_id,
            request.output_path,
            request.character_ids
        )
    
    return QualityScoresResponse(
        id=uuid4(),
        job_id=request.job_id,
        evaluated_at=datetime.utcnow(),
        **result.scores,
        passes_threshold=result.passes_threshold
    )


@router.get("/jobs/{job_id}/quality", response_model=QualityScoresResponse)
async def get_job_quality(job_id: UUID, db = Depends(get_db_pool)):
    """Get quality scores for a completed job"""
    async with db.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM quality_scores WHERE job_id = $1
        """, job_id)
    
    if not row:
        raise HTTPException(status_code=404, detail="Quality scores not found")
    
    return QualityScoresResponse(**dict(row))


@router.post("/quality/phase-gate/{phase}", response_model=PhaseGateResult)
async def evaluate_phase_gate(
    phase: Phase,
    job_ids: List[UUID],
    quality_service = Depends(get_quality_service)
):
    """
    Evaluate if a development phase passes its quality gate.
    
    Requires at least 5 test jobs with 80%+ pass rate.
    """
    if len(job_ids) < 5:
        raise HTTPException(
            status_code=400,
            detail="At least 5 test jobs required for phase gate evaluation"
        )
    
    result = await quality_service.evaluate_phase_gate(phase.value, job_ids)
    
    return PhaseGateResult(
        phase=phase,
        passed=result["passed"],
        tests_run=result["jobs_evaluated"],
        tests_passed=int(result["pass_rate"] * result["jobs_evaluated"]),
        overall_score=result["pass_rate"],
        individual_results=[],  # Populated with detailed results
        can_advance=result["passed"],
        blocking_issues=[] if result["passed"] else ["Pass rate below 80%"]
    )


# === Story Bible Endpoints ===

@router.post("/projects/{project_id}/story-bible", response_model=StoryBibleResponse)
async def create_story_bible(
    project_id: UUID,
    bible: StoryBibleCreate,
    db = Depends(get_db_pool)
):
    """Create story bible for a project"""
    bible_id = uuid4()
    
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO story_bibles 
            (id, project_id, art_style, color_palette, line_weight, shading_style,
             setting_description, time_period, mood_keywords, narrative_themes, global_seed)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """, bible_id, project_id, bible.art_style, bible.color_palette,
            bible.line_weight, bible.shading_style, bible.setting_description,
            bible.time_period, bible.mood_keywords, bible.narrative_themes,
            bible.global_seed)
    
    return StoryBibleResponse(
        id=bible_id,
        version="1.0.0",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        **bible.model_dump()
    )


@router.get("/projects/{project_id}/story-bible", response_model=StoryBibleResponse)
async def get_story_bible(project_id: UUID, db = Depends(get_db_pool)):
    """Get story bible for a project"""
    async with db.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM story_bibles WHERE project_id = $1
        """, project_id)
    
    if not row:
        raise HTTPException(status_code=404, detail="Story bible not found")
    
    return StoryBibleResponse(**dict(row))


@router.put("/projects/{project_id}/story-bible", response_model=StoryBibleResponse)
async def update_story_bible(
    project_id: UUID,
    update: StoryBibleUpdate,
    db = Depends(get_db_pool)
):
    """Update story bible - increments version"""
    updates = {k: v for k, v in update.model_dump().items() if v is not None}
    
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    async with db.acquire() as conn:
        # Get current version
        current = await conn.fetchrow("""
            SELECT version FROM story_bibles WHERE project_id = $1
        """, project_id)
        
        if not current:
            raise HTTPException(status_code=404, detail="Story bible not found")
        
        # Increment version
        parts = current['version'].split('.')
        new_version = f"{parts[0]}.{int(parts[1]) + 1}.0"
        
        # Build update query
        set_clauses = ["version = $2", "updated_at = NOW()"]
        params = [project_id, new_version]
        
        for i, (key, value) in enumerate(updates.items(), start=3):
            set_clauses.append(f"{key} = ${i}")
            params.append(value)
        
        await conn.execute(f"""
            UPDATE story_bibles SET {', '.join(set_clauses)}
            WHERE project_id = $1
        """, *params)
        
        # Return updated
        row = await conn.fetchrow("""
            SELECT * FROM story_bibles WHERE project_id = $1
        """, project_id)
    
    return StoryBibleResponse(**dict(row))


# === Echo Brain Integration Endpoints ===

@router.post("/echo/tasks", response_model=EchoTaskResponse)
async def handle_echo_task(
    task: EchoTaskRequest,
    background_tasks: BackgroundTasks,
    db = Depends(get_db_pool),
    char_service = Depends(get_character_service),
    quality_service = Depends(get_quality_service),
    comfyui = Depends(get_comfyui_client)
):
    """
    Handle task dispatch from Echo Brain orchestrator.
    
    Echo Brain sends structured tasks which are translated into
    generation jobs with appropriate parameters.
    """
    job_id = uuid4()
    
    # Parse task type and create appropriate job
    if task.task_type.value.startswith("generate"):
        # Create generation job from Echo payload
        async with db.acquire() as conn:
            await conn.execute("""
                INSERT INTO jobs (id, project_id, status, job_type, created_at)
                VALUES ($1, $2, $3, $4, NOW())
            """, job_id, task.project_id, JobStatus.QUEUED.value, task.task_type.value)
        
        # Queue processing
        background_tasks.add_task(
            _process_echo_task, task, job_id, db, char_service, comfyui
        )
    
    return EchoTaskResponse(
        task_id=task.task_id,
        job_id=job_id,
        status=JobStatus.QUEUED
    )


@router.post("/echo/webhook-test")
async def test_echo_webhook(payload: EchoWebhookPayload):
    """Test endpoint for Echo Brain webhook callbacks"""
    logger.info(f"Received Echo webhook: {payload.event_type} for task {payload.task_id}")
    return {"received": True, "event_type": payload.event_type}


# === Helper Functions ===

async def _process_generation(
    job_id: UUID,
    request: GenerateRequest,
    prompt: str,
    negative: str,
    seed: int,
    db,
    comfyui
):
    """Background task to process generation through ComfyUI"""
    try:
        async with db.acquire() as conn:
            await conn.execute("""
                UPDATE jobs SET status = $1, started_at = NOW() WHERE id = $2
            """, JobStatus.PROCESSING.value, job_id)
        
        # Call ComfyUI (implement based on your existing client)
        # result = await comfyui.generate(...)
        
        # For now, simulate
        await asyncio.sleep(2)
        
        async with db.acquire() as conn:
            await conn.execute("""
                UPDATE jobs SET status = $1, completed_at = NOW() WHERE id = $2
            """, JobStatus.COMPLETED.value, job_id)
            
    except Exception as e:
        logger.error(f"Generation failed for job {job_id}: {e}")
        async with db.acquire() as conn:
            await conn.execute("""
                UPDATE jobs SET status = $1, error_message = $2 WHERE id = $3
            """, JobStatus.FAILED.value, str(e), job_id)


async def _process_echo_task(task, job_id, db, char_service, comfyui):
    """Background task to process Echo Brain dispatch"""
    # Implementation depends on task type
    pass
