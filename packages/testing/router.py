"""Prompt test grid — A/B test actions across engines, LoRAs, and seeds.

Endpoints:
  POST /testing/generate-prompt-grid  — create + run a test batch
  GET  /testing/batches                — list test batches
  GET  /testing/batches/{batch_id}     — get batch results
  POST /testing/civitai-templates      — store a Civitai config template
  GET  /testing/civitai-templates      — list stored templates
  GET  /testing/character-sheet/{slug} — get character identity + config
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from packages.core.db import connect_direct

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request/Response Models ────────────────────────────────────────────────

class PromptGridRequest(BaseModel):
    project_id: int
    character_slugs: list[str]
    actions: list[dict]  # [{"label": "cowgirl", "prompt": "cowgirl position, ..."}]
    engine_override: Optional[str] = None
    seeds: list[int] = [42, 1337]
    camera_setups: list[str] = ["medium"]
    steps_override: Optional[int] = None
    guidance_override: Optional[float] = None
    resolution_override: Optional[str] = None


class CivitaiTemplateCreate(BaseModel):
    source_url: Optional[str] = None
    source_filename: Optional[str] = None
    engine_type: str
    content_tags: list[str] = []
    base_model: Optional[str] = None
    lora_stack: list[dict] = []
    positive_prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    sampler: Optional[str] = None
    steps: Optional[int] = None
    guidance_scale: Optional[float] = None
    resolution: Optional[str] = None
    motion_strength: Optional[float] = None
    temporal_settings: dict = {}
    notes: Optional[str] = None
    quality_rating: Optional[float] = None


# ── Background task registry ───────────────────────────────────────────────

_grid_tasks: dict[str, asyncio.Task] = {}


# ── POST /testing/generate-prompt-grid ─────────────────────────────────────

@router.post("/generate-prompt-grid")
async def generate_prompt_grid(req: PromptGridRequest):
    """Create a prompt test grid and start generation.

    For each (action × seed × camera_setup), creates a row in prompt_tests
    and a temporary shot. Runs generation via the existing scene pipeline.
    """
    conn = await connect_direct()
    try:
        # Validate project
        project = await conn.fetchrow(
            "SELECT id, name, video_lora, style_preset FROM projects WHERE id = $1",
            req.project_id,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get identity blocks for requested characters
        char_rows = await conn.fetch(
            "SELECT name, identity_block, design_prompt, lora_path, lora_trigger "
            "FROM characters WHERE project_id = $1 AND LOWER(REGEXP_REPLACE(name, '\\s+', '_', 'g')) = ANY($2::text[])",
            req.project_id, req.character_slugs,
        )
        if not char_rows:
            raise HTTPException(status_code=404, detail="No matching characters found")

        # Build composite identity prompt from identity_block or fallback to design_prompt
        identity_parts = []
        for c in char_rows:
            block = c["identity_block"] or c["design_prompt"] or c["name"]
            identity_parts.append(block)
        identity_prompt = ", ".join(identity_parts)

        # Determine engine
        engine = req.engine_override or "framepack"

        # Determine LoRA stack from project + character
        lora_stack = []
        if project["video_lora"]:
            lora_stack.append({"name": project["video_lora"], "strength": 0.8, "scope": "project"})
        for c in char_rows:
            if c["lora_path"]:
                lora_stack.append({"name": c["lora_path"], "strength": 0.7, "scope": "character"})

        # Create batch
        batch_id = f"grid_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # Create a test scene for this batch
        scene_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO scenes (id, project_id, title, description, scene_number, generation_status) "
            "VALUES ($1, $2, $3, $4, (SELECT COALESCE(MAX(scene_number), 0) + 1 FROM scenes WHERE project_id = $2), 'draft')",
            scene_id, req.project_id,
            f"[TEST] {batch_id}",
            f"Prompt test grid: {len(req.actions)} actions × {len(req.seeds)} seeds × {len(req.camera_setups)} cameras",
        )

        # Create test rows + shots for each combination
        test_rows = []
        shot_number = 0
        for action in req.actions:
            for seed in req.seeds:
                for camera in req.camera_setups:
                    shot_number += 1
                    action_label = action.get("label", f"action_{shot_number}")
                    action_prompt = action.get("prompt", action_label)

                    # Full generation prompt = identity + action
                    full_prompt = f"{identity_prompt}, {action_prompt}"

                    shot_id = uuid.uuid4()
                    resolution = req.resolution_override or "544x704"

                    # Insert shot
                    await conn.execute(
                        "INSERT INTO shots (id, scene_id, shot_number, shot_type, "
                        "characters_present, generation_prompt, seed, steps, guidance_scale, "
                        "status, video_engine, duration_seconds) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending', $10, 3)",
                        shot_id, scene_id, shot_number, camera,
                        req.character_slugs, full_prompt,
                        seed, req.steps_override or 25, req.guidance_override or 6.0,
                        engine,
                    )

                    # Insert prompt_test record with shot_id for result tracking
                    await conn.execute(
                        "INSERT INTO prompt_tests (project_id, character_slugs, action_label, "
                        "action_prompt, identity_prompt, engine, lora_stack, seed, steps, "
                        "guidance_scale, resolution, camera_setup, status, batch_id, shot_id, scene_id) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11, $12, 'pending', $13, $14, $15)",
                        req.project_id, req.character_slugs, action_label,
                        action_prompt, identity_prompt, engine,
                        json.dumps(lora_stack), seed,
                        req.steps_override or 25, req.guidance_override or 6.0,
                        resolution, camera, batch_id, shot_id, scene_id,
                    )

                    test_rows.append({
                        "shot_id": str(shot_id),
                        "action": action_label,
                        "seed": seed,
                        "camera": camera,
                        "prompt": full_prompt[:120] + "...",
                    })

        # Update scene shot count
        await conn.execute(
            "UPDATE scenes SET total_shots = $2 WHERE id = $1",
            scene_id, shot_number,
        )

    finally:
        await conn.close()

    # Start generation in background
    async def _run_grid():
        try:
            from packages.scene_generation.builder import generate_scene
            await generate_scene(str(scene_id))

            # After generation, update prompt_test rows with results via shot_id
            conn2 = await connect_direct()
            try:
                shots = await conn2.fetch(
                    "SELECT id, status, output_video_path, "
                    "generation_time_seconds, quality_score, error_message "
                    "FROM shots WHERE scene_id = $1",
                    scene_id,
                )
                for shot in shots:
                    status = "completed" if shot["status"] in ("completed", "accepted_best") else "failed"
                    await conn2.execute(
                        "UPDATE prompt_tests SET status = $1, output_path = $2, "
                        "generation_time_seconds = $3, completed_at = NOW(), "
                        "error_message = $4 "
                        "WHERE shot_id = $5",
                        status, shot["output_video_path"],
                        shot["generation_time_seconds"],
                        shot["error_message"],
                        shot["id"],
                    )
            finally:
                await conn2.close()
            logger.info(f"Grid {batch_id}: completed, {len(shots)} shots processed")
        except Exception as e:
            logger.error(f"Grid generation {batch_id} failed: {e}")
            # Mark all pending tests as failed
            try:
                conn3 = await connect_direct()
                await conn3.execute(
                    "UPDATE prompt_tests SET status = 'failed', error_message = $1, completed_at = NOW() "
                    "WHERE batch_id = $2 AND status = 'pending'",
                    str(e), batch_id,
                )
                await conn3.close()
            except Exception:
                pass

    task = asyncio.create_task(_run_grid())
    _grid_tasks[batch_id] = task

    return {
        "batch_id": batch_id,
        "scene_id": str(scene_id),
        "total_tests": len(test_rows),
        "engine": engine,
        "identity_prompt": identity_prompt[:200],
        "lora_stack": lora_stack,
        "tests": test_rows,
        "message": f"Grid generation started — {len(test_rows)} shots queued",
    }


# ── GET /testing/batches ───────────────────────────────────────────────────

@router.get("/batches")
async def list_batches(project_id: Optional[int] = None):
    """List all prompt test batches with summary stats."""
    conn = await connect_direct()
    try:
        where = "WHERE project_id = $1" if project_id else ""
        params = [project_id] if project_id else []
        rows = await conn.fetch(f"""
            SELECT batch_id,
                   project_id,
                   engine,
                   COUNT(*) as total,
                   COUNT(*) FILTER (WHERE status = 'completed') as completed,
                   COUNT(*) FILTER (WHERE status = 'failed') as failed,
                   COUNT(*) FILTER (WHERE status = 'pending') as pending,
                   AVG(qualitative_score) FILTER (WHERE qualitative_score IS NOT NULL) as avg_score,
                   MIN(created_at) as started_at,
                   MAX(completed_at) as finished_at
            FROM prompt_tests
            {where}
            GROUP BY batch_id, project_id, engine
            ORDER BY MIN(created_at) DESC
        """, *params)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


# ── GET /testing/batches/{batch_id} ────────────────────────────────────────

@router.get("/batches/{batch_id}")
async def get_batch(batch_id: str):
    """Get all prompt test results for a batch."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch(
            "SELECT * FROM prompt_tests WHERE batch_id = $1 ORDER BY id",
            batch_id,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Batch not found")
        return {
            "batch_id": batch_id,
            "tests": [dict(r) for r in rows],
        }
    finally:
        await conn.close()


# ── POST /testing/batches/{batch_id}/score ──────────────────────────────────

@router.post("/batches/{batch_id}/score")
async def score_test(batch_id: str, test_id: int, score: float, notes: Optional[str] = None):
    """Score a prompt test result (0-10 scale)."""
    conn = await connect_direct()
    try:
        result = await conn.execute(
            "UPDATE prompt_tests SET qualitative_score = $1, score_notes = $2 "
            "WHERE id = $3 AND batch_id = $4",
            score, notes, test_id, batch_id,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Test not found")
        return {"ok": True, "test_id": test_id, "score": score}
    finally:
        await conn.close()


# ── POST /testing/civitai-templates ────────────────────────────────────────

@router.post("/civitai-templates")
async def create_civitai_template(tmpl: CivitaiTemplateCreate):
    """Store a Civitai video config as a reusable template."""
    conn = await connect_direct()
    try:
        row = await conn.fetchrow(
            "INSERT INTO civitai_templates "
            "(source_url, source_filename, engine_type, content_tags, base_model, "
            " lora_stack, positive_prompt, negative_prompt, sampler, steps, "
            " guidance_scale, resolution, motion_strength, temporal_settings, "
            " notes, quality_rating) "
            "VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,$15,$16) "
            "RETURNING id",
            tmpl.source_url, tmpl.source_filename, tmpl.engine_type,
            tmpl.content_tags, tmpl.base_model,
            json.dumps(tmpl.lora_stack), tmpl.positive_prompt, tmpl.negative_prompt,
            tmpl.sampler, tmpl.steps, tmpl.guidance_scale, tmpl.resolution,
            tmpl.motion_strength, json.dumps(tmpl.temporal_settings),
            tmpl.notes, tmpl.quality_rating,
        )
        return {"id": row["id"], "message": "Template stored"}
    finally:
        await conn.close()


# ── GET /testing/civitai-templates ─────────────────────────────────────────

@router.get("/civitai-templates")
async def list_civitai_templates(engine_type: Optional[str] = None):
    """List stored Civitai templates, optionally filtered by engine."""
    conn = await connect_direct()
    try:
        if engine_type:
            rows = await conn.fetch(
                "SELECT * FROM civitai_templates WHERE engine_type = $1 ORDER BY id DESC",
                engine_type,
            )
        else:
            rows = await conn.fetch("SELECT * FROM civitai_templates ORDER BY id DESC")
        return [dict(r) for r in rows]
    finally:
        await conn.close()


# ── GET /testing/character-sheet/{slug} ────────────────────────────────────

@router.get("/character-sheet/{slug}")
async def get_character_sheet(slug: str):
    """Get full character identity config for testing.

    Returns identity_block, design_prompt, LoRA config, reference stills,
    and the project's engine/LoRA defaults.
    """
    conn = await connect_direct()
    try:
        row = await conn.fetchrow("""
            SELECT c.name, c.identity_block, c.design_prompt,
                   c.lora_path, c.lora_trigger, c.reference_stills,
                   c.visual_prompt_template,
                   p.id as project_id, p.name as project_name,
                   p.video_lora as project_video_lora, p.style_preset
            FROM characters c
            JOIN projects p ON c.project_id = p.id
            WHERE LOWER(REGEXP_REPLACE(c.name, '\\s+', '_', 'g')) = $1
        """, slug)
        if not row:
            raise HTTPException(status_code=404, detail=f"Character '{slug}' not found")

        return {
            "name": row["name"],
            "identity_block": row["identity_block"],
            "design_prompt": row["design_prompt"],
            "lora": {
                "character_lora": row["lora_path"],
                "character_trigger": row["lora_trigger"],
                "project_video_lora": row["project_video_lora"],
            },
            "reference_stills": row["reference_stills"] or [],
            "visual_prompt_template": row["visual_prompt_template"],
            "project": {
                "id": row["project_id"],
                "name": row["project_name"],
                "style_preset": row["style_preset"],
            },
        }
    finally:
        await conn.close()
