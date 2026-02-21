"""Model selector — checkpoint and parameter recommendation from learned data.

Uses generation_history and learned_patterns to:
- Recommend the best checkpoint for a character/project
- Suggest parameter overrides based on historical success
- Detect quality drift and flag characters needing attention
- Provide learned negative prompt additions from DB rejection patterns

All functions are async, use the shared connection pool, and never raise.
"""

import logging
from typing import Any

from .db import get_pool

logger = logging.getLogger(__name__)

# Minimum data points before we trust recommendations
MIN_CONFIDENCE_SAMPLES = 5

# Quality threshold: only learn from images that scored well
QUALITY_FLOOR = 0.65

# Drift detection: alert if rolling avg drops below this
DRIFT_ALERT_THRESHOLD = 0.55


async def recommend_params(character_slug: str, project_name: str = None,
                          checkpoint_model: str = None) -> dict[str, Any]:
    """Recommend optimal generation parameters for a character.

    Combines project-level SSOT with learned patterns. Returns a dict with:
    - recommended params (cfg_scale, steps, sampler)
    - confidence level (low/medium/high based on sample count)
    - learned_negatives (additional negative prompt terms from rejection history)

    When checkpoint_model is provided, filters history to that checkpoint only
    to prevent cross-model contamination when switching checkpoints.

    The caller decides whether to apply these — SSOT stays authoritative.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # 1. Get successful generation stats for this character
            # Filter by checkpoint_model when provided to prevent cross-model contamination
            if checkpoint_model:
                param_row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as sample_count,
                        AVG(quality_score) as avg_quality,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cfg_scale) as median_cfg,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY steps) as median_steps,
                        MODE() WITHIN GROUP (ORDER BY sampler) as best_sampler,
                        MODE() WITHIN GROUP (ORDER BY scheduler) as best_scheduler
                    FROM generation_history
                    WHERE character_slug = $1
                      AND quality_score >= $2
                      AND quality_score IS NOT NULL
                      AND cfg_scale IS NOT NULL
                      AND checkpoint_model = $3
                """, character_slug, QUALITY_FLOOR, checkpoint_model)
            else:
                param_row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as sample_count,
                        AVG(quality_score) as avg_quality,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cfg_scale) as median_cfg,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY steps) as median_steps,
                        MODE() WITHIN GROUP (ORDER BY sampler) as best_sampler,
                        MODE() WITHIN GROUP (ORDER BY scheduler) as best_scheduler
                    FROM generation_history
                    WHERE character_slug = $1
                      AND quality_score >= $2
                      AND quality_score IS NOT NULL
                      AND cfg_scale IS NOT NULL
                """, character_slug, QUALITY_FLOOR)

            if not param_row or param_row["sample_count"] < MIN_CONFIDENCE_SAMPLES:
                # Not enough data — return learned negatives only
                negatives = await _get_learned_negatives(conn, character_slug)
                return {
                    "confidence": "none",
                    "sample_count": param_row["sample_count"] if param_row else 0,
                    "learned_negatives": negatives,
                }

            sample_count = param_row["sample_count"]
            confidence = "low" if sample_count < 10 else ("medium" if sample_count < 25 else "high")

            # 2. Best checkpoint for this project (unfiltered — compare all models)
            checkpoint_rec = None
            if project_name:
                ckpt_row = await conn.fetchrow("""
                    SELECT checkpoint_model, AVG(quality_score) as avg_q, COUNT(*) as n
                    FROM generation_history
                    WHERE project_name = $1
                      AND quality_score >= $2
                      AND quality_score IS NOT NULL
                      AND checkpoint_model IS NOT NULL
                    GROUP BY checkpoint_model
                    HAVING COUNT(*) >= 3
                    ORDER BY avg_q DESC
                    LIMIT 1
                """, project_name, QUALITY_FLOOR)
                if ckpt_row:
                    checkpoint_rec = {
                        "model": ckpt_row["checkpoint_model"],
                        "avg_quality": round(float(ckpt_row["avg_q"]), 3),
                        "sample_count": ckpt_row["n"],
                    }
                    if checkpoint_model and ckpt_row["checkpoint_model"] != checkpoint_model:
                        checkpoint_rec["note"] = f"Current model ({checkpoint_model}) differs from best ({ckpt_row['checkpoint_model']})"

            # 3. Learned negative prompt additions from rejection patterns
            negatives = await _get_learned_negatives(conn, character_slug)

            return {
                "confidence": confidence,
                "sample_count": sample_count,
                "avg_quality": round(float(param_row["avg_quality"]), 3),
                "cfg_scale": round(float(param_row["median_cfg"]), 1) if param_row["median_cfg"] else None,
                "steps": int(param_row["median_steps"]) if param_row["median_steps"] else None,
                "sampler": param_row["best_sampler"],
                "scheduler": param_row["best_scheduler"],
                "checkpoint": checkpoint_rec,
                "learned_negatives": negatives,
            }

    except Exception as e:
        logger.warning(f"recommend_params failed for {character_slug}: {e}")
        return {"confidence": "error", "learned_negatives": ""}


async def _get_learned_negatives(conn, character_slug: str) -> str:
    """Build negative prompt additions from DB rejection categories.

    Queries the rejections table for this character's top rejection categories
    and maps them to negative prompt terms via REJECTION_NEGATIVE_MAP.
    """
    from packages.lora_training.feedback import REJECTION_NEGATIVE_MAP

    rows = await conn.fetch("""
        SELECT unnest(categories) as category, COUNT(*) as freq
        FROM rejections
        WHERE character_slug = $1
        GROUP BY category
        ORDER BY freq DESC
        LIMIT 10
    """, character_slug)

    if not rows:
        return ""

    neg_terms = []
    for row in rows:
        cat = row["category"]
        if cat in REJECTION_NEGATIVE_MAP and row["freq"] >= 2:
            neg_terms.append(REJECTION_NEGATIVE_MAP[cat])

    return ", ".join(neg_terms)


async def detect_drift(character_slug: str = None, project_name: str = None,
                       window: int = 20) -> list[dict]:
    """Detect quality drift — characters whose recent quality is declining.

    Compares last `window` generations against the historical average.
    Returns list of characters with significant drops.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if character_slug:
                where_clause = "WHERE gh.character_slug = $1 AND gh.quality_score IS NOT NULL"
                args = [character_slug]
            elif project_name:
                where_clause = "WHERE gh.project_name = $1 AND gh.quality_score IS NOT NULL"
                args = [project_name]
            else:
                where_clause = "WHERE gh.quality_score IS NOT NULL"
                args = []

            # Get per-character rolling averages
            query = f"""
                WITH recent AS (
                    SELECT character_slug,
                           quality_score,
                           ROW_NUMBER() OVER (PARTITION BY character_slug ORDER BY generated_at DESC) as rn
                    FROM generation_history gh
                    {where_clause}
                ),
                stats AS (
                    SELECT
                        character_slug,
                        AVG(quality_score) FILTER (WHERE rn <= {window}) as recent_avg,
                        AVG(quality_score) as overall_avg,
                        COUNT(*) FILTER (WHERE rn <= {window}) as recent_count,
                        COUNT(*) as total_count
                    FROM recent
                    GROUP BY character_slug
                    HAVING COUNT(*) >= {MIN_CONFIDENCE_SAMPLES}
                )
                SELECT * FROM stats
                WHERE recent_avg < overall_avg - 0.1
                   OR recent_avg < {DRIFT_ALERT_THRESHOLD}
                ORDER BY (recent_avg - overall_avg) ASC
            """

            rows = await conn.fetch(query, *args)

            return [
                {
                    "character_slug": r["character_slug"],
                    "recent_avg": round(float(r["recent_avg"]), 3),
                    "overall_avg": round(float(r["overall_avg"]), 3),
                    "drift": round(float(r["recent_avg"] - r["overall_avg"]), 3),
                    "recent_count": r["recent_count"],
                    "total_count": r["total_count"],
                    "alert": r["recent_avg"] < DRIFT_ALERT_THRESHOLD,
                }
                for r in rows
            ]

    except Exception as e:
        logger.warning(f"Drift detection failed: {e}")
        return []


async def character_quality_summary(project_name: str) -> list[dict]:
    """Per-character quality summary for a project — used by dashboards and quality gates."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    character_slug,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'approved') as approved,
                    COUNT(*) FILTER (WHERE status = 'rejected') as rejected,
                    AVG(quality_score) FILTER (WHERE quality_score IS NOT NULL) as avg_quality,
                    MAX(quality_score) as best_quality,
                    MIN(quality_score) FILTER (WHERE quality_score IS NOT NULL) as worst_quality,
                    MAX(generated_at) as last_generated
                FROM generation_history
                WHERE project_name = $1
                  AND character_slug IS NOT NULL
                GROUP BY character_slug
                ORDER BY avg_quality DESC NULLS LAST
            """, project_name)

            return [
                {
                    "character_slug": r["character_slug"],
                    "total": r["total"],
                    "approved": r["approved"],
                    "rejected": r["rejected"],
                    "avg_quality": round(float(r["avg_quality"]), 3) if r["avg_quality"] else None,
                    "best_quality": round(float(r["best_quality"]), 3) if r["best_quality"] else None,
                    "worst_quality": round(float(r["worst_quality"]), 3) if r["worst_quality"] else None,
                    "approval_rate": round(r["approved"] / r["total"], 2) if r["total"] > 0 else 0,
                    "last_generated": r["last_generated"].isoformat() if r["last_generated"] else None,
                }
                for r in rows
            ]

    except Exception as e:
        logger.warning(f"Character quality summary failed: {e}")
        return []
