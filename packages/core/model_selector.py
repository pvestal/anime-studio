"""Model selector — checkpoint and parameter recommendation from learned data.

Uses generation_history and learned_patterns to:
- Recommend the best checkpoint for a character/project
- Suggest parameter overrides based on historical success
- Detect quality drift and flag characters needing attention
- Provide learned negative prompt additions from DB rejection patterns
- Explore alternative checkpoints and rank them by quality/approval rate

All functions are async, use the shared connection pool, and never raise.
"""

import logging
import random
from pathlib import Path
from typing import Any

from .db import get_pool
from .model_profiles import MODEL_PROFILES, get_model_profile

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


# ── Model Exploration ────────────────────────────────────────────────────
# Compares checkpoint performance, identifies untested models, and runs
# multi-checkpoint A/B tests using the existing generate_batch + review loop.

# Checkpoints directory — scan once, cache
_CHECKPOINTS_DIR = Path("/opt/ComfyUI/models/checkpoints")


def _discover_available_checkpoints() -> list[dict]:
    """Scan disk for available checkpoint files and match to profiles."""
    if not _CHECKPOINTS_DIR.exists():
        return []
    results = []
    for f in sorted(_CHECKPOINTS_DIR.glob("*.safetensors")):
        profile = get_model_profile(f.name)
        results.append({
            "filename": f.name,
            "architecture": profile["architecture"],
            "style_label": profile["style_label"],
            "prompt_format": profile["prompt_format"],
        })
    return results


async def checkpoint_comparison(project_name: str) -> list[dict]:
    """Compare all checkpoints ever used in a project — ranked by quality and approval rate.

    Returns per-checkpoint stats: avg quality, approval rate, sample count, and
    whether the checkpoint is the project's current default.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Get the project's current default checkpoint
            default_row = await conn.fetchrow("""
                SELECT gs.checkpoint_model
                FROM projects p
                JOIN generation_styles gs ON gs.style_name = p.default_style
                WHERE p.name = $1
            """, project_name)
            current_checkpoint = default_row["checkpoint_model"] if default_row else None

            rows = await conn.fetch("""
                SELECT
                    checkpoint_model,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE quality_score IS NOT NULL) as scored,
                    AVG(quality_score) FILTER (WHERE quality_score IS NOT NULL) as avg_quality,
                    MAX(quality_score) as best_quality,
                    COUNT(*) FILTER (WHERE status = 'approved') as approved,
                    COUNT(*) FILTER (WHERE status = 'rejected') as rejected,
                    MAX(generated_at) as last_used
                FROM generation_history
                WHERE project_name = $1
                  AND checkpoint_model IS NOT NULL
                GROUP BY checkpoint_model
                ORDER BY AVG(quality_score) FILTER (WHERE quality_score IS NOT NULL) DESC NULLS LAST
            """, project_name)

            return [
                {
                    "checkpoint": r["checkpoint_model"],
                    "is_current_default": r["checkpoint_model"] == current_checkpoint,
                    "total_generations": r["total"],
                    "scored": r["scored"],
                    "avg_quality": round(float(r["avg_quality"]), 3) if r["avg_quality"] else None,
                    "best_quality": round(float(r["best_quality"]), 3) if r["best_quality"] else None,
                    "approved": r["approved"],
                    "rejected": r["rejected"],
                    "approval_rate": round(r["approved"] / r["total"], 2) if r["total"] > 0 else 0,
                    "last_used": r["last_used"].isoformat() if r["last_used"] else None,
                }
                for r in rows
            ]

    except Exception as e:
        logger.warning(f"checkpoint_comparison failed for {project_name}: {e}")
        return []


async def suggest_exploration(
    character_slug: str,
    project_name: str,
    max_suggestions: int = 3,
) -> dict:
    """Suggest untested or under-tested checkpoints for a character.

    Returns:
    - current: the character's current checkpoint + its stats
    - suggestions: list of checkpoints to try, with reasoning
    - available: all checkpoints on disk
    """
    try:
        available = _discover_available_checkpoints()
        available_filenames = {c["filename"] for c in available}

        pool = await get_pool()
        async with pool.acquire() as conn:
            # Current checkpoint
            current_row = await conn.fetchrow("""
                SELECT gs.checkpoint_model
                FROM characters c
                JOIN projects p ON c.project_id = p.id
                JOIN generation_styles gs ON gs.style_name = p.default_style
                WHERE REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1
            """, character_slug)
            current_checkpoint = current_row["checkpoint_model"] if current_row else None
            current_profile = get_model_profile(current_checkpoint) if current_checkpoint else None

            # What checkpoints have been tried for this character?
            tried_rows = await conn.fetch("""
                SELECT
                    checkpoint_model,
                    COUNT(*) as n,
                    AVG(quality_score) FILTER (WHERE quality_score IS NOT NULL) as avg_q,
                    COUNT(*) FILTER (WHERE status = 'approved') as approved,
                    COUNT(*) FILTER (WHERE status = 'rejected') as rejected
                FROM generation_history
                WHERE character_slug = $1
                  AND checkpoint_model IS NOT NULL
                GROUP BY checkpoint_model
            """, character_slug)

            tried = {r["checkpoint_model"]: {
                "count": r["n"],
                "avg_quality": round(float(r["avg_q"]), 3) if r["avg_q"] else None,
                "approved": r["approved"],
                "rejected": r["rejected"],
            } for r in tried_rows}

        # Build suggestions
        suggestions = []

        # 1. Untested checkpoints (same architecture preferred)
        for ckpt in available:
            if ckpt["filename"] not in tried:
                reason = "never tested"
                # Prefer same architecture as current
                if current_profile and ckpt["architecture"] == current_profile["architecture"]:
                    reason += f" (same arch: {ckpt['architecture']})"
                    priority = 1
                else:
                    reason += f" (different arch: {ckpt['architecture']})"
                    priority = 2
                suggestions.append({
                    "checkpoint": ckpt["filename"],
                    "style_label": ckpt["style_label"],
                    "architecture": ckpt["architecture"],
                    "reason": reason,
                    "priority": priority,
                    "history": None,
                })

        # 2. Under-tested checkpoints (< 5 generations)
        for ckpt in available:
            stats = tried.get(ckpt["filename"])
            if stats and stats["count"] < MIN_CONFIDENCE_SAMPLES:
                suggestions.append({
                    "checkpoint": ckpt["filename"],
                    "style_label": ckpt["style_label"],
                    "architecture": ckpt["architecture"],
                    "reason": f"under-tested ({stats['count']} generations, need {MIN_CONFIDENCE_SAMPLES}+)",
                    "priority": 3,
                    "history": stats,
                })

        # Sort by priority, then limit
        suggestions.sort(key=lambda s: s["priority"])
        suggestions = suggestions[:max_suggestions]

        # Clean up priority field (internal only)
        for s in suggestions:
            del s["priority"]

        return {
            "character_slug": character_slug,
            "current_checkpoint": current_checkpoint,
            "current_stats": tried.get(current_checkpoint) if current_checkpoint else None,
            "total_checkpoints_on_disk": len(available),
            "total_tested": len(tried),
            "suggestions": suggestions,
            "available_checkpoints": available,
        }

    except Exception as e:
        logger.warning(f"suggest_exploration failed for {character_slug}: {e}")
        return {"error": str(e)}


async def explore_checkpoints(
    character_slug: str,
    checkpoints: list[str] | None = None,
    images_per_checkpoint: int = 2,
) -> list[dict]:
    """Run a multi-checkpoint comparison for a character.

    Generates `images_per_checkpoint` images with each checkpoint using
    generate_batch(checkpoint_override=...). The existing vision review
    and approval/rejection flow scores results automatically.

    Args:
        character_slug: Character to test.
        checkpoints: List of checkpoint filenames to test. If None,
                     auto-selects from suggest_exploration().
        images_per_checkpoint: Images to generate per checkpoint (default 2).

    Returns:
        List of per-checkpoint generation results.
    """
    from packages.core.generation import generate_batch
    from packages.core.db import get_char_project_map

    char_map = await get_char_project_map()
    db_info = char_map.get(character_slug)
    if not db_info:
        return [{"error": f"Character '{character_slug}' not found"}]

    project_name = db_info.get("project_name")

    # Auto-select checkpoints if not provided
    if not checkpoints:
        exploration = await suggest_exploration(character_slug, project_name)
        checkpoints = [s["checkpoint"] for s in exploration.get("suggestions", [])]
        if not checkpoints:
            return [{"error": "No untested checkpoints available"}]

    # Validate checkpoints exist on disk
    valid = []
    for ckpt in checkpoints:
        if (_CHECKPOINTS_DIR / ckpt).exists():
            valid.append(ckpt)
        else:
            logger.warning(f"explore_checkpoints: {ckpt} not found on disk, skipping")
    if not valid:
        return [{"error": "None of the specified checkpoints exist on disk"}]

    results = []
    for ckpt in valid:
        profile = get_model_profile(ckpt)
        logger.info(
            f"explore_checkpoints: testing {ckpt} ({profile['style_label']}) "
            f"for {character_slug} — {images_per_checkpoint} images"
        )
        try:
            batch_results = await generate_batch(
                character_slug=character_slug,
                count=images_per_checkpoint,
                checkpoint_override=ckpt,
                include_learned_negatives=True,
                include_feedback_negatives=True,
                fire_events=True,
            )
            results.append({
                "checkpoint": ckpt,
                "style_label": profile["style_label"],
                "architecture": profile["architecture"],
                "status": "completed",
                "images_generated": sum(len(r.get("images", [])) for r in batch_results),
                "details": batch_results,
            })
        except Exception as e:
            logger.error(f"explore_checkpoints: {ckpt} failed for {character_slug}: {e}")
            results.append({
                "checkpoint": ckpt,
                "style_label": profile["style_label"],
                "status": "error",
                "error": str(e),
            })

    return results
