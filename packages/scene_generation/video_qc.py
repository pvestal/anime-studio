"""Video Quality Control Loop — multi-frame vision review with prompt refinement.

Replaces the old single-frame "rate 1-10" gate with:
  1. Extract 3 frames (start, middle, end) from generated video
  2. Vision-review each frame for quality, motion, character, composition
  3. Identify specific issues → map to prompt/negative modifications
  4. Regenerate with targeted fixes (not just new seed + more steps)

Primary engine: FramePack (HunyuanVideo I2V), also supports LTX and Wan.

Vision model interaction lives in video_vision.py; re-exported here for external callers.
"""

import asyncio
import json
import logging
import random
import time
from pathlib import Path

from packages.core.config import COMFYUI_OUTPUT_DIR
from packages.core.audit import log_decision

# Re-export vision functions so external callers can still import from video_qc
from .video_vision import (  # noqa: F401
    KNOWN_ISSUES,
    extract_review_frames,
    _vision_review_single_frame,
    review_video_frames,
)

logger = logging.getLogger(__name__)

# Issue → prompt/negative fix mapping
_ISSUE_FIXES = {
    "blurry": {
        "negative_add": "blurry, out of focus, soft focus",
        "prompt_add": "sharp, high detail",
        "fixable": True,
    },
    "artifact_flicker": {
        "negative_add": "flickering, artifacts, glitch",
        "prompt_add": "smooth animation, consistent frames",
        "fixable": True,
    },
    "frozen_motion": {
        "negative_add": "static, frozen, still image",
        "prompt_add": "dynamic motion, fluid movement",
        "fixable": True,
    },
    "poor_lighting": {
        "negative_add": "dark, underexposed, overexposed",
        "prompt_add": "well-lit, balanced lighting",
        "fixable": True,
    },
    "bad_anatomy": {
        "negative_add": "bad anatomy, extra limbs, deformed hands, malformed fingers",
        "prompt_add": "",
        "fixable": True,
    },
    "text_watermark": {
        "negative_add": "text, watermark, logo, subtitle",
        "prompt_add": "",
        "fixable": True,
    },
    "color_shift": {
        "negative_add": "color banding, desaturated, wrong colors",
        "prompt_add": "vibrant colors, consistent color",
        "fixable": True,
    },
    # These require manual prompt rewrite — cannot be auto-fixed
    "wrong_action": {
        "negative_add": "",
        "prompt_add": "",
        "fixable": False,
    },
    "wrong_character": {
        "negative_add": "",
        "prompt_add": "",
        "fixable": False,
    },
}


def build_prompt_fixes(
    issues: list[str],
    current_prompt: str,
    current_negative: str,
) -> dict:
    """Map detected issues to prompt/negative modifications.

    Returns:
        {
            modified_prompt: str,
            modified_negative: str,
            fixable: bool,
            applied_fixes: list[str],
        }
    """
    prompt_additions = []
    negative_additions = []
    applied_fixes = []
    has_unfixable = False

    for issue in issues:
        fix = _ISSUE_FIXES.get(issue)
        if not fix:
            continue

        if not fix["fixable"]:
            has_unfixable = True
            continue

        if fix["prompt_add"] and fix["prompt_add"] not in current_prompt:
            prompt_additions.append(fix["prompt_add"])
        if fix["negative_add"] and fix["negative_add"] not in current_negative:
            negative_additions.append(fix["negative_add"])
        applied_fixes.append(issue)

    # Build modified strings — append additions, don't duplicate
    modified_prompt = current_prompt
    if prompt_additions:
        modified_prompt = current_prompt.rstrip(", ") + ", " + ", ".join(prompt_additions)

    modified_negative = current_negative
    if negative_additions:
        modified_negative = current_negative.rstrip(", ") + ", " + ", ".join(negative_additions)

    # fixable = True if we found at least one auto-fixable issue (or no issues at all)
    fixable = len(applied_fixes) > 0 or (not has_unfixable and len(issues) == 0)

    return {
        "modified_prompt": modified_prompt,
        "modified_negative": modified_negative,
        "fixable": fixable,
        "applied_fixes": applied_fixes,
        "unfixable_issues": [i for i in issues if not _ISSUE_FIXES.get(i, {}).get("fixable", True)],
    }


async def run_qc_loop(
    shot_data: dict,
    conn,
    max_attempts: int = 3,
    accept_threshold: float = 0.6,
    min_threshold: float = 0.3,
) -> dict:
    """Main QC loop — replaces the inline progressive gate from builder.py.

    For each attempt:
      1. Build workflow → submit to ComfyUI → poll completion
      2. Extract 3 review frames from output video
      3. Vision review → overall_score + issues
      4. If score >= threshold → ACCEPT
      5. If below and fixable → modify prompt/negative → loop
      6. After all attempts → use best-scoring attempt

    Args:
        shot_data: dict-like row from shots table
        conn: asyncpg connection
        max_attempts: max retry count
        accept_threshold: score for first attempt to pass
        min_threshold: score for last attempt to pass

    Returns:
        {accepted, video_path, last_frame_path, quality_score, attempts,
         status, issues, prompt_modifications, generation_time}
    """
    from .builder import (
        copy_to_comfyui_input, extract_last_frame, poll_comfyui_completion,
        COMFYUI_OUTPUT_DIR,
    )
    from .framepack import build_framepack_workflow, _submit_comfyui_workflow
    from .ltx_video import build_ltx_workflow, _submit_comfyui_workflow as _submit_ltx_workflow
    from .wan_video import build_wan_t2v_workflow, _submit_comfyui_workflow as _submit_wan_workflow

    shot_id = shot_data["id"]
    scene_id = shot_data["scene_id"]

    # Check engine blacklist before spending GPU time
    shot_engine_check = shot_data.get("video_engine") or "framepack"
    chars_check = shot_data.get("characters_present")
    char_slug_check = chars_check[0] if chars_check and isinstance(chars_check, list) and len(chars_check) > 0 else None
    if char_slug_check:
        # Get project_id from scene
        project_id = None
        try:
            scene_row = await conn.fetchrow("SELECT project_id FROM scenes WHERE id = $1", scene_id)
            if scene_row:
                project_id = scene_row["project_id"]
        except Exception:
            pass
        bl = await check_engine_blacklist(conn, char_slug_check, project_id, shot_engine_check)
        if bl:
            logger.warning(
                f"Shot {shot_id}: engine '{shot_engine_check}' blacklisted for "
                f"'{char_slug_check}' — reason: {bl.get('reason')}"
            )
            return {
                "accepted": False,
                "video_path": None,
                "last_frame_path": None,
                "quality_score": 0.0,
                "attempts": 0,
                "status": "engine_blacklisted",
                "issues": [f"Engine '{shot_engine_check}' is blacklisted for '{char_slug_check}'"],
                "prompt_modifications": [],
                "generation_time": 0.0,
            }

    # Build progressive thresholds (linear interpolation from accept to min)
    thresholds = []
    for i in range(max_attempts):
        if max_attempts == 1:
            thresholds.append(min_threshold)
        else:
            t = accept_threshold - (accept_threshold - min_threshold) * i / (max_attempts - 1)
            thresholds.append(round(t, 2))

    # Current prompt/negative — will be modified across attempts
    current_prompt = shot_data["motion_prompt"] or shot_data.get("generation_prompt") or ""
    current_negative = "low quality, blurry, distorted, watermark"
    shot_engine = shot_data.get("video_engine") or "framepack"
    shot_steps = shot_data.get("steps") or 25
    shot_seconds = float(shot_data.get("duration_seconds") or 3)
    shot_use_f1 = shot_data.get("use_f1") or False
    original_seed = shot_data.get("seed")
    character_slug = None

    # Try to extract character slug from characters_present
    chars = shot_data.get("characters_present")
    if chars and isinstance(chars, list) and len(chars) > 0:
        character_slug = chars[0]

    best_video = None
    best_quality = 0.0
    best_last_frame = None
    best_issues = []
    all_modifications = []
    final_gen_time = 0.0

    for attempt in range(max_attempts):
        threshold = thresholds[attempt]
        attempt_start = time.time()

        try:
            # Determine first frame source
            if shot_data.get("_prev_last_frame") and Path(shot_data["_prev_last_frame"]).exists():
                first_frame_path = shot_data["_prev_last_frame"]
                image_filename = await copy_to_comfyui_input(first_frame_path)
            else:
                source_path = shot_data["source_image_path"]
                image_filename = await copy_to_comfyui_input(source_path)
                from packages.core.config import BASE_PATH
                first_frame_path = str(BASE_PATH / source_path) if not Path(source_path).is_absolute() else source_path

            # Vary seed on retry
            shot_seed = original_seed if attempt == 0 else random.randint(0, 2**63 - 1)
            retry_steps = shot_steps + (attempt * 5)

            # Dispatch to the right video engine
            if shot_engine == "wan":
                fps = 16
                num_frames = max(9, int(shot_seconds * fps) + 1)
                workflow, prefix = build_wan_t2v_workflow(
                    prompt_text=current_prompt,
                    num_frames=num_frames,
                    fps=fps,
                    steps=retry_steps,
                    seed=shot_seed,
                    use_gguf=True,
                )
                comfyui_prompt_id = _submit_wan_workflow(workflow)
            elif shot_engine == "ltx":
                fps = 24
                num_frames = max(9, int(shot_seconds * fps) + 1)
                workflow, prefix = build_ltx_workflow(
                    prompt_text=current_prompt,
                    image_path=image_filename if image_filename else None,
                    num_frames=num_frames,
                    fps=fps,
                    steps=retry_steps,
                    seed=shot_seed,
                    lora_name=shot_data.get("lora_name"),
                    lora_strength=shot_data.get("lora_strength", 0.8),
                )
                comfyui_prompt_id = _submit_ltx_workflow(workflow)
            else:
                # framepack or framepack_f1
                use_f1 = shot_engine == "framepack_f1" or shot_use_f1
                workflow_data, sampler_node_id, prefix = build_framepack_workflow(
                    prompt_text=current_prompt,
                    image_path=image_filename,
                    total_seconds=shot_seconds,
                    steps=retry_steps,
                    use_f1=use_f1,
                    seed=shot_seed,
                    negative_text=current_negative,
                    gpu_memory_preservation=6.0,
                )
                comfyui_prompt_id = _submit_comfyui_workflow(workflow_data["prompt"])

            # Update shot with current ComfyUI prompt
            await conn.execute(
                "UPDATE shots SET comfyui_prompt_id = $2, first_frame_path = $3 WHERE id = $1",
                shot_id, comfyui_prompt_id, first_frame_path,
            )

            # Poll for completion
            result = await poll_comfyui_completion(comfyui_prompt_id)
            gen_time = time.time() - attempt_start

            if result["status"] != "completed" or not result["output_files"]:
                logger.warning(
                    f"Shot {shot_id} QC attempt {attempt+1}: ComfyUI {result['status']}"
                )
                continue

            video_filename = result["output_files"][0]
            video_path = str(COMFYUI_OUTPUT_DIR / video_filename)
            last_frame = await extract_last_frame(video_path)

            # Multi-frame QC review (comparative when source image available)
            source_img = shot_data.get("source_image_path")
            if source_img and not Path(source_img).is_absolute():
                from packages.core.config import BASE_PATH
                source_img = str(BASE_PATH / source_img) if (BASE_PATH / source_img).exists() else source_img

            frame_paths = await extract_review_frames(video_path)
            if frame_paths:
                review = await review_video_frames(
                    frame_paths, current_prompt, character_slug, source_img,
                )
                shot_quality = review["overall_score"]
                issues = review["issues"]
            else:
                # Fallback: no frames extracted, assume decent
                shot_quality = 0.5
                issues = []
                review = {"per_frame": [], "category_averages": {}}

            logger.info(
                f"Shot {shot_id} QC attempt {attempt+1}/{max_attempts}: "
                f"quality={shot_quality:.2f}, threshold={threshold}, issues={issues}"
            )

            # Track best attempt
            if shot_quality > best_quality:
                best_quality = shot_quality
                best_video = video_path
                best_last_frame = last_frame
                best_issues = issues
                final_gen_time = gen_time

            if shot_quality >= threshold:
                # PASSED — log and return
                gate_label = "high" if threshold >= 0.55 else ("medium" if threshold >= 0.4 else "low")
                await log_decision(
                    decision_type="video_qc_gate",
                    input_context={
                        "shot_id": str(shot_id),
                        "scene_id": str(scene_id),
                        "quality_score": shot_quality,
                        "attempt": attempt + 1,
                        "threshold": threshold,
                        "gate_label": gate_label,
                        "video": video_filename,
                        "issues": issues,
                        "prompt_modifications": all_modifications,
                        "category_averages": review.get("category_averages", {}),
                    },
                    decision_made="accepted",
                    confidence_score=shot_quality,
                    reasoning=(
                        f"Quality {shot_quality:.0%} passed {gate_label} gate "
                        f"({threshold:.0%}) on attempt {attempt+1}"
                    ),
                )

                # Store QC detail data + set review_status
                review_status = "approved" if shot_quality >= 0.75 else "pending_review"
                await _store_qc_review_data(
                    conn, shot_id, issues,
                    review.get("category_averages", {}),
                    review.get("per_frame", []),
                    review_status,
                )

                return {
                    "accepted": True,
                    "video_path": video_path,
                    "last_frame_path": last_frame,
                    "quality_score": shot_quality,
                    "attempts": attempt + 1,
                    "status": "accepted",
                    "issues": issues,
                    "prompt_modifications": all_modifications,
                    "generation_time": gen_time,
                }

            # Below threshold — try prompt refinement for next attempt
            if attempt < max_attempts - 1:
                fixes = build_prompt_fixes(issues, current_prompt, current_negative)
                if fixes["fixable"] and fixes["applied_fixes"]:
                    current_prompt = fixes["modified_prompt"]
                    current_negative = fixes["modified_negative"]
                    all_modifications.append({
                        "attempt": attempt + 1,
                        "fixes_applied": fixes["applied_fixes"],
                        "prompt_before": shot_data.get("motion_prompt") or "",
                        "prompt_after": current_prompt,
                    })
                    logger.info(
                        f"Shot {shot_id} QC: applying fixes {fixes['applied_fixes']}, "
                        f"prompt now: {current_prompt[:100]}..."
                    )

                await log_decision(
                    decision_type="video_qc_gate",
                    input_context={
                        "shot_id": str(shot_id),
                        "scene_id": str(scene_id),
                        "quality_score": shot_quality,
                        "attempt": attempt + 1,
                        "threshold": threshold,
                        "video": video_filename,
                        "issues": issues,
                        "fixes_applied": fixes.get("applied_fixes", []) if 'fixes' in dir() else [],
                    },
                    decision_made="retry_with_fixes",
                    confidence_score=round(1.0 - shot_quality, 2),
                    reasoning=(
                        f"Quality {shot_quality:.0%} below gate ({threshold:.0%}), "
                        f"attempt {attempt+1}/{max_attempts}, "
                        f"fixes: {fixes.get('applied_fixes', []) if 'fixes' in dir() else 'none'}"
                    ),
                )

        except Exception as e:
            logger.error(f"Shot {shot_id} QC attempt {attempt+1} failed: {e}")
            if attempt == max_attempts - 1 and not best_video:
                raise

    # All attempts exhausted — return best
    await log_decision(
        decision_type="video_qc_gate",
        input_context={
            "shot_id": str(shot_id),
            "scene_id": str(scene_id),
            "quality_score": best_quality,
            "attempts": max_attempts,
            "issues": best_issues,
            "prompt_modifications": all_modifications,
        },
        decision_made="accepted_best",
        confidence_score=best_quality,
        reasoning=f"All {max_attempts} attempts exhausted, using best (quality={best_quality:.0%})",
    )

    # Store QC detail data + set review_status for the best attempt
    if best_video:
        review_status = "approved" if best_quality >= 0.85 else "pending_review"
        await _store_qc_review_data(
            conn, shot_id, best_issues, {}, [], review_status,
        )

    return {
        "accepted": best_quality >= min_threshold,
        "video_path": best_video,
        "last_frame_path": best_last_frame,
        "quality_score": best_quality,
        "attempts": max_attempts,
        "status": "accepted_best" if best_video else "failed",
        "issues": best_issues,
        "prompt_modifications": all_modifications,
        "generation_time": final_gen_time,
    }


async def _store_qc_review_data(
    conn,
    shot_id,
    issues: list[str],
    category_averages: dict,
    per_frame: list[dict],
    review_status: str,
):
    """Persist QC review details and review_status to the shots table."""
    try:
        await conn.execute("""
            UPDATE shots
            SET qc_issues = $2,
                qc_category_averages = $3::jsonb,
                qc_per_frame = $4::jsonb,
                review_status = $5
            WHERE id = $1
        """, shot_id,
            issues if issues else None,
            json.dumps(category_averages) if category_averages else '{}',
            json.dumps(per_frame) if per_frame else '[]',
            review_status,
        )
    except Exception as e:
        logger.warning(f"Failed to store QC review data for shot {shot_id}: {e}")


async def check_engine_blacklist(
    conn,
    character_slug: str | None,
    project_id: int | None,
    video_engine: str,
) -> dict | None:
    """Check if a video engine is blacklisted for a character+project.

    Returns the blacklist row dict if blacklisted, None if allowed.
    """
    if not character_slug:
        return None
    try:
        row = await conn.fetchrow("""
            SELECT id, reason, created_at
            FROM engine_blacklist
            WHERE character_slug = $1
              AND video_engine = $2
              AND (project_id = $3 OR project_id IS NULL)
            LIMIT 1
        """, character_slug, video_engine, project_id)
        return dict(row) if row else None
    except Exception as e:
        logger.warning(f"Engine blacklist check failed (non-fatal): {e}")
        return None
