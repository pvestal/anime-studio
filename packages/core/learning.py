"""Learning system — SQL-based pattern analysis from generation_history/rejections/approvals.

Adapted from /opt/anime-studio/quality/learning_system.py (800 LOC standalone)
into a streamlined module that uses our asyncpg pool and new Phase 1 tables.

No sklearn/numpy dependency — pattern analysis done via SQL aggregation.

Key functions:
    suggest_params(slug)   → dict of optimal params for a character
    rejection_patterns(slug) → top rejection categories + frequencies
    checkpoint_rankings(project) → best checkpoint per quality score
    record_pattern(slug, quality, params) → update learned_patterns table
"""

import logging
from typing import Any

from .db import get_pool
from .events import event_bus, IMAGE_REJECTED, IMAGE_APPROVED

logger = logging.getLogger(__name__)

# Minimum generations before we trust learned patterns
MIN_SAMPLES = 5

# Quality threshold for "successful" generation
SUCCESS_THRESHOLD = 0.7


async def suggest_params(character_slug: str) -> dict[str, Any]:
    """Suggest optimal generation parameters based on historical quality data.

    Queries generation_history for this character's successful generations
    and returns median values for cfg_scale, steps, plus best sampler.
    Returns empty dict if insufficient data.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Get median params from successful generations
            row = await conn.fetchrow("""
                SELECT
                    COUNT(*) as sample_count,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cfg_scale) as median_cfg,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY steps) as median_steps,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY width) as median_width,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY height) as median_height,
                    AVG(quality_score) as avg_quality
                FROM generation_history
                WHERE character_slug = $1
                  AND quality_score >= $2
                  AND quality_score IS NOT NULL
                  AND cfg_scale IS NOT NULL
            """, character_slug, SUCCESS_THRESHOLD)

            if not row or row["sample_count"] < MIN_SAMPLES:
                return {}

            # Best sampler (by avg quality)
            sampler_row = await conn.fetchrow("""
                SELECT sampler, AVG(quality_score) as avg_q, COUNT(*) as n
                FROM generation_history
                WHERE character_slug = $1
                  AND quality_score >= $2
                  AND quality_score IS NOT NULL
                  AND sampler IS NOT NULL
                GROUP BY sampler
                HAVING COUNT(*) >= 3
                ORDER BY avg_q DESC
                LIMIT 1
            """, character_slug, SUCCESS_THRESHOLD)

            suggestions = {
                "sample_count": row["sample_count"],
                "avg_quality": round(float(row["avg_quality"]), 3),
                "cfg_scale": round(float(row["median_cfg"]), 1) if row["median_cfg"] else None,
                "steps": int(row["median_steps"]) if row["median_steps"] else None,
                "width": int(row["median_width"]) if row["median_width"] else None,
                "height": int(row["median_height"]) if row["median_height"] else None,
            }

            if sampler_row:
                suggestions["sampler"] = sampler_row["sampler"]
                suggestions["sampler_avg_quality"] = round(float(sampler_row["avg_q"]), 3)

            return suggestions

    except Exception as e:
        logger.warning(f"Failed to suggest params for {character_slug}: {e}")
        return {}


async def rejection_patterns(character_slug: str, limit: int = 10) -> list[dict]:
    """Get top rejection categories for a character, ordered by frequency.

    Returns list of {category, count, latest_at}.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    unnest(categories) as category,
                    COUNT(*) as count,
                    MAX(created_at) as latest_at
                FROM rejections
                WHERE character_slug = $1
                GROUP BY category
                ORDER BY count DESC
                LIMIT $2
            """, character_slug, limit)

            return [
                {
                    "category": r["category"],
                    "count": r["count"],
                    "latest_at": r["latest_at"].isoformat() if r["latest_at"] else None,
                }
                for r in rows
            ]

    except Exception as e:
        logger.warning(f"Failed to get rejection patterns for {character_slug}: {e}")
        return []


async def checkpoint_rankings(project_name: str) -> list[dict]:
    """Rank checkpoints by average quality score for a project.

    Returns list of {checkpoint, avg_quality, count, approval_rate}.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    checkpoint_model,
                    AVG(quality_score) as avg_quality,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'approved') as approved,
                    COUNT(*) FILTER (WHERE status = 'rejected') as rejected
                FROM generation_history
                WHERE project_name = $1
                  AND quality_score IS NOT NULL
                  AND checkpoint_model IS NOT NULL
                GROUP BY checkpoint_model
                ORDER BY avg_quality DESC
            """, project_name)

            return [
                {
                    "checkpoint": r["checkpoint_model"],
                    "avg_quality": round(float(r["avg_quality"]), 3),
                    "total": r["total"],
                    "approved": r["approved"],
                    "rejected": r["rejected"],
                    "approval_rate": round(r["approved"] / r["total"], 2) if r["total"] > 0 else 0,
                }
                for r in rows
            ]

    except Exception as e:
        logger.warning(f"Failed to get checkpoint rankings for {project_name}: {e}")
        return []


async def quality_trend(character_slug: str = None, project_name: str = None, days: int = 7) -> list[dict]:
    """Get quality score trend over recent days.

    Returns list of {date, avg_quality, count, approved, rejected}.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if character_slug:
                rows = await conn.fetch("""
                    SELECT
                        DATE(generated_at) as gen_date,
                        AVG(quality_score) as avg_quality,
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE status = 'approved') as approved,
                        COUNT(*) FILTER (WHERE status = 'rejected') as rejected
                    FROM generation_history
                    WHERE character_slug = $1
                      AND quality_score IS NOT NULL
                      AND generated_at > NOW() - ($2 || ' days')::INTERVAL
                    GROUP BY gen_date
                    ORDER BY gen_date
                """, character_slug, str(days))
            elif project_name:
                rows = await conn.fetch("""
                    SELECT
                        DATE(generated_at) as gen_date,
                        AVG(quality_score) as avg_quality,
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE status = 'approved') as approved,
                        COUNT(*) FILTER (WHERE status = 'rejected') as rejected
                    FROM generation_history
                    WHERE project_name = $1
                      AND quality_score IS NOT NULL
                      AND generated_at > NOW() - ($2 || ' days')::INTERVAL
                    GROUP BY gen_date
                    ORDER BY gen_date
                """, project_name, str(days))
            else:
                return []

            return [
                {
                    "date": r["gen_date"].isoformat() if r["gen_date"] else None,
                    "avg_quality": round(float(r["avg_quality"]), 3),
                    "count": r["total"],
                    "approved": r["approved"],
                    "rejected": r["rejected"],
                }
                for r in rows
            ]

    except Exception as e:
        logger.warning(f"Failed to get quality trend: {e}")
        return []


async def learning_stats() -> dict:
    """Overall learning system statistics."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_generations,
                    COUNT(*) FILTER (WHERE quality_score IS NOT NULL) as reviewed,
                    AVG(quality_score) FILTER (WHERE quality_score IS NOT NULL) as avg_quality,
                    COUNT(*) FILTER (WHERE status = 'approved') as approved,
                    COUNT(*) FILTER (WHERE status = 'rejected') as rejected,
                    COUNT(DISTINCT character_slug) FILTER (WHERE character_slug IS NOT NULL) as characters_tracked,
                    COUNT(DISTINCT checkpoint_model) FILTER (WHERE checkpoint_model IS NOT NULL) as checkpoints_used
                FROM generation_history
                WHERE generated_at > NOW() - INTERVAL '30 days'
            """)

            rej_row = await conn.fetchrow("""
                SELECT COUNT(*) as total_rejections,
                       COUNT(DISTINCT character_slug) as characters_rejected
                FROM rejections
                WHERE created_at > NOW() - INTERVAL '30 days'
            """)

            patterns_row = await conn.fetchrow("""
                SELECT COUNT(*) as total_patterns
                FROM learned_patterns
            """)

            decisions_row = await conn.fetchrow("""
                SELECT COUNT(*) as total_decisions,
                       COUNT(*) FILTER (WHERE decision_type = 'auto_approve') as auto_approves,
                       COUNT(*) FILTER (WHERE decision_type = 'auto_reject') as auto_rejects,
                       COUNT(*) FILTER (WHERE decision_type = 'regeneration') as regenerations
                FROM autonomy_decisions
                WHERE created_at > NOW() - INTERVAL '30 days'
            """)

            return {
                "generation_history": {
                    "total": row["total_generations"],
                    "reviewed": row["reviewed"],
                    "avg_quality": round(float(row["avg_quality"]), 3) if row["avg_quality"] else None,
                    "approved": row["approved"],
                    "rejected": row["rejected"],
                    "characters_tracked": row["characters_tracked"],
                    "checkpoints_used": row["checkpoints_used"],
                },
                "rejections": {
                    "total": rej_row["total_rejections"],
                    "characters_affected": rej_row["characters_rejected"],
                },
                "learned_patterns": patterns_row["total_patterns"],
                "autonomy_decisions": {
                    "total": decisions_row["total_decisions"],
                    "auto_approves": decisions_row["auto_approves"],
                    "auto_rejects": decisions_row["auto_rejects"],
                    "regenerations": decisions_row["regenerations"],
                },
                "period": "last_30_days",
            }

    except Exception as e:
        logger.warning(f"Failed to get learning stats: {e}")
        return {}


async def record_learned_pattern(
    character_slug: str,
    pattern_type: str,  # "success" or "failure"
    project_name: str = None,
    checkpoint_model: str = None,
    quality_score: float = None,
    cfg_scale: float = None,
    steps: int = None,
):
    """Update learned_patterns table with a new data point.

    Upserts by character_slug + pattern_type + checkpoint_model:
    - Increments frequency
    - Updates running average quality score
    - Updates cfg/steps ranges
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Check existing pattern
            existing = await conn.fetchrow("""
                SELECT id, quality_score_avg, frequency, cfg_range_min, cfg_range_max,
                       steps_range_min, steps_range_max
                FROM learned_patterns
                WHERE character_slug = $1 AND pattern_type = $2
                  AND COALESCE(checkpoint_model, '') = COALESCE($3, '')
            """, character_slug, pattern_type, checkpoint_model)

            if existing:
                # Update running average and ranges
                old_avg = existing["quality_score_avg"] or 0
                old_freq = existing["frequency"] or 1
                new_avg = (old_avg * old_freq + (quality_score or 0)) / (old_freq + 1) if quality_score else old_avg

                new_cfg_min = min(existing["cfg_range_min"] or 999, cfg_scale) if cfg_scale else existing["cfg_range_min"]
                new_cfg_max = max(existing["cfg_range_max"] or 0, cfg_scale) if cfg_scale else existing["cfg_range_max"]
                new_steps_min = min(existing["steps_range_min"] or 999, steps) if steps else existing["steps_range_min"]
                new_steps_max = max(existing["steps_range_max"] or 0, steps) if steps else existing["steps_range_max"]

                await conn.execute("""
                    UPDATE learned_patterns SET
                        frequency = frequency + 1,
                        quality_score_avg = $2,
                        cfg_range_min = $3, cfg_range_max = $4,
                        steps_range_min = $5, steps_range_max = $6,
                        updated_at = NOW()
                    WHERE id = $1
                """,
                    existing["id"], round(new_avg, 3),
                    new_cfg_min, new_cfg_max,
                    new_steps_min, new_steps_max,
                )
            else:
                # Insert new pattern
                await conn.execute("""
                    INSERT INTO learned_patterns
                        (character_slug, project_name, pattern_type, checkpoint_model,
                         quality_score_avg, frequency,
                         cfg_range_min, cfg_range_max, steps_range_min, steps_range_max)
                    VALUES ($1, $2, $3, $4, $5, 1, $6, $6, $7, $7)
                """,
                    character_slug, project_name, pattern_type, checkpoint_model,
                    quality_score, cfg_scale, steps,
                )

    except Exception as e:
        logger.warning(f"Failed to record learned pattern: {e}")


# ---- EventBus Handlers ----
# Registered at import time; fire when events are emitted from router.py

@event_bus.on(IMAGE_REJECTED)
async def _handle_rejection(data: dict):
    """Learn from rejected images: update failure patterns."""
    slug = data.get("character_slug")
    if not slug:
        return

    await record_learned_pattern(
        character_slug=slug,
        pattern_type="failure",
        project_name=data.get("project_name"),
        checkpoint_model=data.get("checkpoint_model"),
        quality_score=data.get("quality_score"),
    )

    logger.debug(f"Learning: recorded failure pattern for {slug}")


@event_bus.on(IMAGE_APPROVED)
async def _handle_approval(data: dict):
    """Learn from approved images: update success patterns."""
    slug = data.get("character_slug")
    if not slug:
        return

    await record_learned_pattern(
        character_slug=slug,
        pattern_type="success",
        project_name=data.get("project_name"),
        checkpoint_model=data.get("checkpoint_model"),
        quality_score=data.get("quality_score"),
    )

    logger.debug(f"Learning: recorded success pattern for {slug}")
