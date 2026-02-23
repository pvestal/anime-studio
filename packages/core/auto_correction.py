"""Auto-correction system — 7 fix strategies for failed generations.

Adapted from /opt/anime-studio/quality/auto_correction_system.py (700 LOC)
into an async module using our asyncpg pool and workflow builder patterns.

Fix strategies map rejection categories to targeted workflow modifications:
1. fix_quality     — increase steps, adjust CFG, upgrade sampler
2. fix_resolution  — upscale dimensions (multiples of 8)
3. fix_blur        — sharpen via higher steps + prompt enhancement
4. fix_brightness  — add lighting terms to prompt
5. fix_contrast    — add contrast/sharpness terms to prompt
6. fix_appearance  — enhance negative prompt with rejection-derived terms
7. fix_solo        — add "solo, single character" emphasis + negative "multiple"

Integrated via EventBus: on IMAGE_REJECTED, optionally auto-corrects and resubmits.
"""

import copy
import json
import logging
from typing import Any

from .db import get_pool
from .audit import log_decision
from .events import event_bus, IMAGE_REJECTED

logger = logging.getLogger(__name__)

# Max auto-correction attempts per character per day
MAX_CORRECTIONS_PER_DAY = 5

# Map rejection categories to fix strategy names
CATEGORY_TO_FIX = {
    "bad_quality": ["fix_quality"],
    "wrong_appearance": ["fix_appearance"],
    "not_solo": ["fix_solo"],
    "wrong_style": ["fix_quality", "fix_contrast"],
    "wrong_pose": ["fix_appearance"],
    "wrong_expression": ["fix_appearance"],
}


def fix_quality(workflow: dict, _categories: list[str]) -> bool:
    """Increase steps and adjust CFG for better quality."""
    changed = False
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "KSampler":
            inputs = node["inputs"]
            # Increase steps (cap at 50)
            old_steps = inputs.get("steps", 25)
            if old_steps < 50:
                inputs["steps"] = min(old_steps + 10, 50)
                changed = True
            # Nudge CFG up if below 9
            old_cfg = inputs.get("cfg", 7.0)
            if old_cfg < 9.0:
                inputs["cfg"] = min(old_cfg + 1.0, 10.0)
                changed = True
            # Upgrade sampler if using basic euler
            if inputs.get("sampler_name") in ("euler", "euler_ancestral"):
                inputs["sampler_name"] = "dpmpp_2m"
                inputs["scheduler"] = "karras"
                changed = True
    return changed


def fix_resolution(workflow: dict, _categories: list[str]) -> bool:
    """Increase resolution for higher detail."""
    changed = False
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "EmptyLatentImage":
            inputs = node["inputs"]
            w, h = inputs.get("width", 512), inputs.get("height", 768)
            if w < 768 or h < 768:
                factor = 1.5
            else:
                factor = 1.2
            inputs["width"] = int(w * factor) // 8 * 8
            inputs["height"] = int(h * factor) // 8 * 8
            changed = True
    return changed


def fix_blur(workflow: dict, _categories: list[str]) -> bool:
    """Fix blurry output: higher steps + sharpness prompt."""
    changed = False
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "KSampler":
            inputs = node["inputs"]
            old_steps = inputs.get("steps", 25)
            if old_steps < 40:
                inputs["steps"] = max(old_steps + 15, 40)
                changed = True
            inputs["cfg"] = 9.0
            changed = True
        elif node.get("class_type") == "CLIPTextEncode":
            text = node["inputs"].get("text", "")
            # Only modify positive prompt (longer ones)
            if len(text) > 50 and "sharp focus" not in text:
                node["inputs"]["text"] = f"{text}, sharp focus, high detail, crisp image"
                changed = True
    return changed


def fix_brightness(workflow: dict, _categories: list[str]) -> bool:
    """Add lighting terms when output is too dark."""
    changed = False
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "CLIPTextEncode":
            text = node["inputs"].get("text", "")
            if len(text) > 50 and "well-lit" not in text:
                node["inputs"]["text"] = f"{text}, well-lit, bright lighting, proper exposure"
                changed = True
                break  # Only modify positive prompt
    return changed


def fix_contrast(workflow: dict, _categories: list[str]) -> bool:
    """Enhance contrast and vibrancy."""
    changed = False
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "CLIPTextEncode":
            text = node["inputs"].get("text", "")
            if len(text) > 50 and "high contrast" not in text:
                node["inputs"]["text"] = f"{text}, high contrast, sharp details, vivid colors"
                changed = True
                break
    return changed


def fix_appearance(workflow: dict, categories: list[str]) -> bool:
    """Enhance negative prompt based on rejection categories."""
    from packages.lora_training.feedback import REJECTION_NEGATIVE_MAP

    neg_additions = []
    for cat in categories:
        if cat in REJECTION_NEGATIVE_MAP:
            neg_additions.append(REJECTION_NEGATIVE_MAP[cat])

    if not neg_additions:
        return False

    additions_str = ", ".join(neg_additions)
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "CLIPTextEncode":
            text = node["inputs"].get("text", "")
            # Target the negative prompt (shorter one or containing "worst quality")
            if "worst quality" in text.lower() or "low quality" in text.lower():
                if additions_str not in text:
                    node["inputs"]["text"] = f"{text}, {additions_str}"
                    return True
    return False


def fix_solo(workflow: dict, _categories: list[str]) -> bool:
    """Force solo character generation."""
    changed = False
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "CLIPTextEncode":
            text = node["inputs"].get("text", "")
            if len(text) > 50 and "solo" not in text.lower():
                # Positive prompt: add solo emphasis
                node["inputs"]["text"] = f"solo, single character, {text}"
                changed = True
                break

    # Also add to negative prompt
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "CLIPTextEncode":
            text = node["inputs"].get("text", "")
            if "worst quality" in text.lower() and "multiple characters" not in text:
                node["inputs"]["text"] = f"{text}, multiple characters, group shot, crowd"
                changed = True
    return changed


# Strategy registry
FIX_STRATEGIES = {
    "fix_quality": fix_quality,
    "fix_resolution": fix_resolution,
    "fix_blur": fix_blur,
    "fix_brightness": fix_brightness,
    "fix_contrast": fix_contrast,
    "fix_appearance": fix_appearance,
    "fix_solo": fix_solo,
}


async def apply_corrections(
    workflow: dict,
    categories: list[str],
    character_slug: str,
    quality_score: float = 0.0,
) -> dict | None:
    """Apply targeted corrections to a workflow based on rejection categories.

    Returns a corrected workflow copy, or None if no fixes were applicable
    or correction limit reached.
    """
    # Check daily correction limit
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval("""
                SELECT COUNT(*) FROM autonomy_decisions
                WHERE decision_type = 'auto_correction'
                  AND character_slug = $1
                  AND created_at > NOW() - INTERVAL '1 day'
            """, character_slug)
            if count >= MAX_CORRECTIONS_PER_DAY:
                logger.info(f"Correction limit reached for {character_slug} ({count}/{MAX_CORRECTIONS_PER_DAY})")
                return None
    except Exception:
        pass

    corrected = copy.deepcopy(workflow)
    applied = []

    # Determine which strategies to apply
    strategies_to_try = set()
    for cat in categories:
        for fix_name in CATEGORY_TO_FIX.get(cat, []):
            strategies_to_try.add(fix_name)

    # Always try fix_quality for low scores
    if quality_score < 0.4:
        strategies_to_try.add("fix_quality")

    if not strategies_to_try:
        return None

    for strategy_name in strategies_to_try:
        fix_fn = FIX_STRATEGIES.get(strategy_name)
        if fix_fn and fix_fn(corrected, categories):
            applied.append(strategy_name)

    if not applied:
        return None

    logger.info(f"Auto-correction for {character_slug}: applied {applied}")

    # Audit the correction
    await log_decision(
        decision_type="auto_correction",
        character_slug=character_slug,
        input_context={
            "categories": categories,
            "quality_score": quality_score,
            "strategies_applied": applied,
        },
        decision_made="corrected_workflow",
        confidence_score=round(1.0 - quality_score, 2),
        reasoning=f"Applied {len(applied)} fixes: {', '.join(applied)}",
    )

    return corrected


async def get_correction_stats() -> dict:
    """Get auto-correction statistics."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_corrections,
                    COUNT(DISTINCT character_slug) as characters_corrected,
                    COUNT(*) FILTER (WHERE outcome = 'success') as successful,
                    COUNT(*) FILTER (WHERE outcome = 'pending') as pending
                FROM autonomy_decisions
                WHERE decision_type = 'auto_correction'
                  AND created_at > NOW() - INTERVAL '30 days'
            """)
            return {
                "total": row["total_corrections"],
                "characters_corrected": row["characters_corrected"],
                "successful": row["successful"],
                "pending": row["pending"],
                "success_rate": round(row["successful"] / max(row["total_corrections"], 1), 2),
            }
    except Exception as e:
        logger.warning(f"Failed to get correction stats: {e}")
        return {}


# --- Quality Gates ---

async def get_quality_gates() -> list[dict]:
    """Get all quality gates (both legacy per-project and new autonomy gates)."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id,
                       COALESCE(gate_name, metric) as gate_name,
                       COALESCE(gate_type, stage) as gate_type,
                       COALESCE(threshold_value, threshold::float) as threshold_value,
                       COALESCE(is_active, is_blocking) as is_active,
                       description,
                       project_name
                FROM quality_gates
                ORDER BY id
            """)
            return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"Failed to get quality gates: {e}")
        return []


async def update_quality_gate(gate_name: str, threshold: float = None, is_active: bool = None) -> bool:
    """Update a quality gate threshold or active status."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if threshold is not None:
                await conn.execute(
                    "UPDATE quality_gates SET threshold_value = $2, threshold = $2 WHERE gate_name = $1",
                    gate_name, threshold,
                )
            if is_active is not None:
                await conn.execute(
                    "UPDATE quality_gates SET is_active = $2 WHERE gate_name = $1",
                    gate_name, is_active,
                )
            return True
    except Exception as e:
        logger.warning(f"Failed to update quality gate: {e}")
        return False


async def check_quality_gates(quality_score: float, solo: bool = True) -> dict:
    """Check if a generation passes all active autonomy quality gates.

    Returns {passed: bool, gates: [{name, threshold, value, passed}]}
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT gate_name, gate_type, threshold_value
                FROM quality_gates
                WHERE gate_name IS NOT NULL AND COALESCE(is_active, TRUE) = TRUE
            """)

            results = []
            all_passed = True
            for r in rows:
                gate_type = r["gate_type"]
                threshold = float(r["threshold_value"])

                if gate_type == "auto_reject":
                    value = quality_score
                    passed = value >= threshold
                elif gate_type == "auto_approve":
                    value = quality_score
                    passed = value >= threshold and solo
                elif gate_type == "overall_consistency":
                    value = quality_score
                    passed = value >= threshold
                else:
                    value = quality_score
                    passed = value >= threshold

                results.append({
                    "name": r["gate_name"],
                    "type": gate_type,
                    "threshold": threshold,
                    "value": round(value, 3),
                    "passed": passed,
                })
                if not passed:
                    all_passed = False

            return {"passed": all_passed, "gates": results}
    except Exception as e:
        logger.warning(f"Quality gate check failed: {e}")
        return {"passed": True, "gates": []}  # Fail open


# --- EventBus Handler ---

# Auto-correction is OFF by default — enable via quality_gates or API
_auto_correction_enabled = False


def enable_auto_correction(enabled: bool = True):
    """Toggle auto-correction on rejection events."""
    global _auto_correction_enabled
    _auto_correction_enabled = enabled
    logger.info(f"Auto-correction {'enabled' if enabled else 'disabled'}")


@event_bus.on(IMAGE_REJECTED)
async def _handle_rejection_correction(data: dict):
    """Optionally auto-correct rejected images by resubmitting with fixes."""
    if not _auto_correction_enabled:
        return

    slug = data.get("character_slug")
    categories = data.get("categories", [])
    quality_score = data.get("quality_score", 0.0)

    if not slug or not categories:
        return

    # We need the original workflow to correct it — check generation_history
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT prompt, checkpoint_model, cfg_scale, steps, sampler, scheduler,
                       width, height, comfyui_prompt_id
                FROM generation_history
                WHERE character_slug = $1
                ORDER BY generated_at DESC
                LIMIT 1
            """, slug)

            if not row or not row["prompt"]:
                return

            # Rebuild the workflow from stored params
            from packages.visual_pipeline.comfyui import build_comfyui_workflow
            from packages.core.config import normalize_sampler

            norm_sampler, norm_scheduler = normalize_sampler(
                row["sampler"], row["scheduler"]
            )

            workflow = build_comfyui_workflow(
                design_prompt=row["prompt"],
                checkpoint_model=row["checkpoint_model"],
                cfg_scale=row["cfg_scale"] or 7.0,
                steps=row["steps"] or 25,
                sampler=norm_sampler,
                scheduler=norm_scheduler,
                width=row["width"] or 512,
                height=row["height"] or 768,
                character_slug=slug,
            )

            corrected = await apply_corrections(workflow, categories, slug, quality_score)
            if corrected:
                from packages.visual_pipeline.comfyui import submit_comfyui_workflow
                prompt_id = submit_comfyui_workflow(corrected)
                logger.info(f"Auto-correction submitted for {slug}: prompt_id={prompt_id}")

    except Exception as e:
        logger.warning(f"Auto-correction handler failed for {slug}: {e}")
