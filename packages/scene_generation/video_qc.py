"""Video Quality Control Loop — multi-frame vision review with prompt refinement.

Replaces the old single-frame "rate 1-10" gate with:
  1. Extract 3 frames (start, middle, end) from generated video
  2. Vision-review each frame for quality, motion, character, composition
  3. Identify specific issues → map to prompt/negative modifications
  4. Regenerate with targeted fixes (not just new seed + more steps)

Primary engine: FramePack (HunyuanVideo I2V), also supports LTX and Wan.
"""

import asyncio
import base64
import json
import logging
import random
import time
from pathlib import Path

from packages.core.config import COMFYUI_OUTPUT_DIR, COMFYUI_URL, OLLAMA_URL, VISION_MODEL
from packages.core.audit import log_decision

logger = logging.getLogger(__name__)

# Known issue categories the vision model can identify
KNOWN_ISSUES = [
    "artifact_flicker", "blurry", "wrong_character", "bad_anatomy",
    "frozen_motion", "wrong_action", "poor_lighting", "text_watermark",
    "color_shift",
]

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


async def extract_review_frames(video_path: str, count: int = 3) -> list[str]:
    """Extract frames at start (0.1s), midpoint, and end (-0.1s) via ffmpeg.

    Returns list of PNG paths stored alongside the video as _qc_frame_N.png.
    """
    video = Path(video_path)
    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    # Get video duration
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    duration = float(stdout.decode().strip()) if stdout.decode().strip() else 3.0

    # Calculate timestamps: 0.1s, midpoint, duration-0.1s
    timestamps = [0.1]
    if count >= 2:
        timestamps.append(max(0.2, duration / 2))
    if count >= 3:
        timestamps.append(max(0.3, duration - 0.1))

    frame_paths = []
    base = video_path.rsplit(".", 1)[0]

    for i, ts in enumerate(timestamps[:count]):
        out_path = f"{base}_qc_frame_{i}.png"
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-ss", str(ts), "-i", video_path,
            "-vframes", "1", "-q:v", "2", out_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0 and Path(out_path).exists():
            frame_paths.append(out_path)
        else:
            logger.warning(f"Frame extraction failed at {ts}s: {stderr.decode()[-200:]}")

    return frame_paths


async def _vision_review_single_frame(
    frame_path: str,
    motion_prompt: str,
    character_slug: str | None = None,
) -> dict:
    """Send a single frame to the vision model for structured assessment.

    Returns dict with visual_quality, motion_coherence, character_consistency,
    composition (all 1-10), and issues list.
    """
    import urllib.request

    with open(frame_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    char_context = f" The character should be '{character_slug}'." if character_slug else ""
    issue_list = ", ".join(KNOWN_ISSUES)

    prompt = (
        f"You are reviewing an anime video frame. The intended motion/action is: \"{motion_prompt}\".{char_context}\n\n"
        f"Score each category 1-10:\n"
        f"- visual_quality: sharpness, no artifacts, no glitches\n"
        f"- motion_coherence: does the frame match the described motion/action\n"
        f"- character_consistency: character appears on-model and correct\n"
        f"- composition: framing, lighting, visual appeal\n\n"
        f"Also list any issues from this set: [{issue_list}]\n\n"
        f"Reply in EXACTLY this JSON format, nothing else:\n"
        f'{{"visual_quality": N, "motion_coherence": N, "character_consistency": N, '
        f'"composition": N, "issues": ["issue1", "issue2"]}}'
    )

    payload = json.dumps({
        "model": VISION_MODEL,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.1},
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read())
        text = result.get("response", "").strip()

        # Extract JSON from response (may have markdown fences)
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        parsed = json.loads(text)

        # Validate and clamp scores
        scores = {}
        for key in ("visual_quality", "motion_coherence", "character_consistency", "composition"):
            val = parsed.get(key, 5)
            scores[key] = max(1, min(10, int(val)))

        # Validate issues
        issues = [i for i in parsed.get("issues", []) if i in KNOWN_ISSUES]

        return {**scores, "issues": issues}

    except Exception as e:
        logger.warning(f"Vision review failed for {frame_path}: {e}")
        return {
            "visual_quality": 5,
            "motion_coherence": 5,
            "character_consistency": 5,
            "composition": 5,
            "issues": [],
        }


async def review_video_frames(
    frame_paths: list[str],
    motion_prompt: str,
    character_slug: str | None = None,
) -> dict:
    """Review multiple frames and aggregate scores.

    Returns:
        {
            overall_score: float (0-1),
            issues: list[str],
            per_frame: list[dict],
        }
    """
    if not frame_paths:
        return {"overall_score": 0.5, "issues": [], "per_frame": []}

    # Review frames sequentially (Ollama single-model queue)
    per_frame = []
    for fp in frame_paths:
        result = await _vision_review_single_frame(fp, motion_prompt, character_slug)
        per_frame.append(result)

    # Aggregate: weighted average across frames, then weighted category mix
    # Weights: visual 0.3, motion 0.3, character 0.2, composition 0.2
    weights = {
        "visual_quality": 0.3,
        "motion_coherence": 0.3,
        "character_consistency": 0.2,
        "composition": 0.2,
    }

    category_avgs = {}
    for key in weights:
        vals = [fr[key] for fr in per_frame]
        category_avgs[key] = sum(vals) / len(vals)

    # Weighted sum normalized to 0-1 (scores are 1-10)
    raw_score = sum(category_avgs[k] * w for k, w in weights.items())
    overall_score = round((raw_score - 1) / 9, 2)  # map 1-10 → 0-1
    overall_score = max(0.0, min(1.0, overall_score))

    # Union of all frame issues
    all_issues = set()
    for fr in per_frame:
        all_issues.update(fr.get("issues", []))

    return {
        "overall_score": overall_score,
        "issues": sorted(all_issues),
        "per_frame": per_frame,
        "category_averages": {k: round(v, 1) for k, v in category_avgs.items()},
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

            # Multi-frame QC review
            frame_paths = await extract_review_frames(video_path)
            if frame_paths:
                review = await review_video_frames(frame_paths, current_prompt, character_slug)
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
