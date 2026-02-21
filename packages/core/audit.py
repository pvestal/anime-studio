"""Autonomy decision audit logger — records every autonomous action with reasoning.

Follows Echo Brain's src/autonomous/audit.py pattern.
Writes to generation_history, rejections, approvals, autonomy_decisions tables.
All functions are fire-and-forget safe: errors are logged, never raised.
"""

import json
import logging
from typing import Any

from .db import get_pool

logger = logging.getLogger(__name__)


async def log_generation(
    character_slug: str,
    project_name: str = None,
    comfyui_prompt_id: str = None,
    generation_type: str = "image",
    checkpoint_model: str = None,
    prompt: str = None,
    negative_prompt: str = None,
    seed: int = None,
    cfg_scale: float = None,
    steps: int = None,
    sampler: str = None,
    scheduler: str = None,
    width: int = None,
    height: int = None,
) -> int | None:
    """Record a generation submission to generation_history. Returns row ID."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO generation_history
                    (character_slug, project_name, comfyui_prompt_id, generation_type,
                     checkpoint_model, prompt, negative_prompt, seed,
                     cfg_scale, steps, sampler, scheduler, width, height)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                RETURNING id
            """,
                character_slug, project_name, comfyui_prompt_id, generation_type,
                checkpoint_model, prompt, negative_prompt, seed,
                cfg_scale, steps, sampler, scheduler, width, height,
            )
        return row["id"] if row else None
    except Exception as e:
        logger.warning(f"Failed to log generation: {e}")
        return None


async def update_generation_quality(
    gen_id: int,
    quality_score: float,
    character_match: float = None,
    clarity: float = None,
    training_value: float = None,
    solo: bool = None,
    species_verified: bool = None,
    status: str = "pending",
    rejection_categories: list[str] = None,
    artifact_path: str = None,
):
    """Update a generation_history row with quality review results."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE generation_history SET
                    quality_score = $2, character_match = $3, clarity = $4,
                    training_value = $5, solo = $6, species_verified = $7,
                    status = $8, rejection_categories = $9, artifact_path = $10,
                    reviewed_at = NOW()
                WHERE id = $1
            """,
                gen_id, quality_score, character_match, clarity,
                training_value, solo, species_verified,
                status, rejection_categories, artifact_path,
            )
    except Exception as e:
        logger.warning(f"Failed to update generation quality: {e}")


async def log_rejection(
    character_slug: str,
    image_name: str,
    categories: list[str],
    feedback_text: str = None,
    negative_additions: list[str] = None,
    quality_score: float = None,
    project_name: str = None,
    source: str = "vision",
    generation_history_id: int = None,
    checkpoint_model: str = None,
):
    """Record a rejection to the rejections table."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO rejections
                    (character_slug, project_name, image_name, generation_history_id,
                     categories, feedback_text, negative_additions, source, quality_score,
                     checkpoint_model)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            """,
                character_slug, project_name, image_name, generation_history_id,
                categories, feedback_text, negative_additions, source, quality_score,
                checkpoint_model,
            )
    except Exception as e:
        logger.warning(f"Failed to log rejection: {e}")


async def log_approval(
    character_slug: str,
    image_name: str,
    quality_score: float,
    auto_approved: bool = False,
    vision_review: dict = None,
    project_name: str = None,
    generation_history_id: int = None,
    checkpoint_model: str = None,
):
    """Record an approval to the approvals table."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO approvals
                    (character_slug, project_name, image_name, generation_history_id,
                     quality_score, auto_approved, vision_review, checkpoint_model)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            """,
                character_slug, project_name, image_name, generation_history_id,
                quality_score, auto_approved,
                json.dumps(vision_review) if vision_review else None,
                checkpoint_model,
            )
    except Exception as e:
        logger.warning(f"Failed to log approval: {e}")


async def log_decision(
    decision_type: str,
    character_slug: str = None,
    project_name: str = None,
    input_context: dict[str, Any] = None,
    decision_made: str = "",
    confidence_score: float = None,
    reasoning: str = "",
    outcome: str = "success",
) -> int | None:
    """Record an autonomous decision to the audit trail. Returns row ID."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO autonomy_decisions
                    (decision_type, character_slug, project_name,
                     input_context, decision_made, confidence_score, reasoning, outcome)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            """,
                decision_type,
                character_slug,
                project_name,
                json.dumps(input_context or {}),
                decision_made,
                confidence_score,
                reasoning,
                outcome,
            )
        return row["id"] if row else None
    except Exception as e:
        logger.warning(f"Failed to log autonomy decision: {e}")
        return None
