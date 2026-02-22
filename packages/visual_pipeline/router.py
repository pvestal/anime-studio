"""Visual Pipeline router — generation, gallery, and vision quality review endpoints."""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from packages.core.config import BASE_PATH, COMFYUI_OUTPUT_DIR, OLLAMA_URL, VISION_MODEL, normalize_sampler
from packages.core.db import get_char_project_map
from packages.core.models import GenerateRequest, VisionReviewRequest
from packages.lora_training.feedback import record_rejection, queue_regeneration, REJECTION_NEGATIVE_MAP
from packages.core.audit import log_generation, log_decision, log_rejection, log_approval
from packages.core.events import event_bus, GENERATION_SUBMITTED, IMAGE_REJECTED, IMAGE_APPROVED, REGENERATION_QUEUED
from packages.core.model_selector import recommend_params

from packages.core.model_profiles import get_model_profile, adjust_thresholds

from .comfyui import build_comfyui_workflow, submit_comfyui_workflow, get_comfyui_progress
from .vision import vision_review_image, vision_issues_to_categories

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/generate/{character_slug}")
async def generate_for_character(character_slug: str, body: GenerateRequest):
    """Generate an image or video for a character using SSOT profile."""
    char_map = await get_char_project_map()
    db_info = char_map.get(character_slug)
    if not db_info:
        raise HTTPException(status_code=404, detail=f"Character '{character_slug}' not found")

    # Use style_override if provided, otherwise use project default
    style_info = db_info
    if body.style_override:
        from packages.core.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT checkpoint_model, positive_prompt_template, negative_prompt_template, "
                "cfg_scale, sampler, steps, width, height, scheduler "
                "FROM generation_styles WHERE style_name = $1", body.style_override
            )
            if not row:
                raise HTTPException(status_code=400, detail=f"Style '{body.style_override}' not found")
            style_info = {**db_info, **dict(row)}
            logger.info(f"Using style override '{body.style_override}' for {character_slug}")

    checkpoint = style_info.get("checkpoint_model")
    if not checkpoint:
        raise HTTPException(status_code=400, detail="No checkpoint model configured for this character's project")

    prompt = body.prompt_override or db_info.get("design_prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="No design_prompt and no prompt_override provided")

    # Prepend positive_prompt_template from style (quality tags)
    style_preamble = style_info.get("positive_prompt_template") or db_info.get("style_preamble")
    if style_preamble and body.prompt_override:
        # For overrides, prepend the style's quality tags
        prompt = f"{style_preamble}, {prompt}"
    elif style_preamble and not body.prompt_override:
        prompt = f"{style_preamble}, {prompt}"

    norm_sampler, norm_scheduler = normalize_sampler(
        style_info.get("sampler"), style_info.get("scheduler")
    )

    # Use style's negative template if no explicit negative given
    style_negative = style_info.get("negative_prompt_template", "")
    base_negative = body.negative_prompt or style_negative or "worst quality, low quality, blurry, deformed"

    # Auto-enhance negative prompt with learned rejection patterns from DB
    try:
        rec = await recommend_params(
            character_slug, project_name=db_info.get("project_name"),
            checkpoint_model=checkpoint,
        )
        learned_neg = rec.get("learned_negatives", "")
        if learned_neg:
            base_negative = f"{base_negative}, {learned_neg}"
            logger.info(f"Enhanced negative prompt for {character_slug} with learned terms")
    except Exception:
        pass  # Never block generation on recommendation failure

    workflow = build_comfyui_workflow(
        design_prompt=prompt,
        checkpoint_model=checkpoint,
        cfg_scale=style_info.get("cfg_scale") or 7.0,
        steps=style_info.get("steps") or 25,
        sampler=norm_sampler,
        scheduler=norm_scheduler,
        width=style_info.get("width") or 512,
        height=style_info.get("height") or 768,
        negative_prompt=base_negative,
        generation_type=body.generation_type,
        seed=body.seed,
        character_slug=character_slug,
    )

    try:
        prompt_id = submit_comfyui_workflow(workflow)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ComfyUI submission failed: {e}")

    actual_seed = workflow["3"]["inputs"]["seed"]

    # Log to generation_history
    gen_id = await log_generation(
        character_slug=character_slug,
        project_name=db_info.get("project_name"),
        comfyui_prompt_id=prompt_id,
        generation_type=body.generation_type,
        checkpoint_model=checkpoint,
        prompt=prompt,
        negative_prompt=body.negative_prompt or "worst quality, low quality, blurry, deformed",
        seed=actual_seed,
        cfg_scale=db_info.get("cfg_scale"),
        steps=db_info.get("steps"),
        sampler=norm_sampler,
        scheduler=norm_scheduler,
        width=db_info.get("width"),
        height=db_info.get("height"),
    )

    await event_bus.emit(GENERATION_SUBMITTED, {
        "character_slug": character_slug,
        "prompt_id": prompt_id,
        "generation_history_id": gen_id,
        "project_name": db_info.get("project_name"),
    })

    return {
        "prompt_id": prompt_id,
        "generation_history_id": gen_id,
        "character": character_slug,
        "generation_type": body.generation_type,
        "prompt_used": prompt,
        "checkpoint": checkpoint,
        "seed": actual_seed,
    }


@router.get("/generate/{prompt_id}/status")
async def get_generation_status(prompt_id: str):
    """Check ComfyUI generation progress."""
    return get_comfyui_progress(prompt_id)


@router.get("/gallery")
async def get_gallery(limit: int = 50):
    """Get recent images from ComfyUI output directory."""
    if not COMFYUI_OUTPUT_DIR.exists():
        return {"images": []}

    image_files = []
    for ext in ("*.png", "*.jpg"):
        image_files.extend(COMFYUI_OUTPUT_DIR.glob(ext))

    image_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return {
        "images": [
            {
                "filename": img.name,
                "created_at": datetime.fromtimestamp(img.stat().st_mtime).isoformat(),
                "size_kb": round(img.stat().st_size / 1024, 1),
            }
            for img in image_files[:limit]
        ]
    }


@router.get("/gallery/image/{filename}")
async def get_gallery_image(filename: str):
    """Serve a gallery image from ComfyUI output."""
    image_path = COMFYUI_OUTPUT_DIR / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)


# --- Background Vision Review ---
# Tasks tracked in-memory. Only 1 can run at a time (Ollama is single-model).
_vision_tasks: dict[str, dict] = {}
_MAX_STORED_TASKS = 20
_CONSECUTIVE_ERROR_LIMIT = 5


@router.post("/approval/vision-review")
async def vision_review(body: VisionReviewRequest):
    """Start a background vision review. Returns immediately with a task_id for polling.

    The blocking Ollama calls run in a thread pool via asyncio.to_thread(),
    so the event loop stays free to serve other requests (pending images, etc.).

    Poll progress:  GET /api/visual/approval/vision-review/{task_id}
    Cancel:         POST /api/visual/approval/vision-review/{task_id}/cancel
    List all:       GET /api/visual/approval/vision-review/tasks
    """
    char_map = await get_char_project_map()

    # Validate inputs upfront
    target_slugs: list[str] = []
    if body.character_slug:
        if body.character_slug not in char_map:
            raise HTTPException(status_code=404, detail=f"Character '{body.character_slug}' not found")
        target_slugs = [body.character_slug]
    elif body.project_name:
        target_slugs = [slug for slug, info in char_map.items() if info.get("project_name") == body.project_name]
        if not target_slugs:
            raise HTTPException(status_code=404, detail=f"No characters found for project '{body.project_name}'")
    else:
        raise HTTPException(status_code=400, detail="Provide character_slug or project_name")

    # Only 1 review at a time
    for t in _vision_tasks.values():
        if t["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail=f"Vision review already running (task {t['task_id']}). "
                       f"Cancel it first: POST /api/visual/approval/vision-review/{t['task_id']}/cancel",
            )

    task_id = uuid.uuid4().hex[:8]
    _vision_tasks[task_id] = {
        "task_id": task_id,
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "character_slug": body.character_slug,
        "project_name": body.project_name,
        "max_images": body.max_images,
        "reviewed": 0,
        "auto_approved": 0,
        "auto_rejected": 0,
        "errors": 0,
        "regen_queued": 0,
        "current_image": None,
        "results": [],
        "cancelled": False,
    }

    # Prune old finished tasks
    if len(_vision_tasks) > _MAX_STORED_TASKS:
        finished = sorted(
            [t for t in _vision_tasks.values() if t["status"] != "running"],
            key=lambda t: t.get("started_at", ""),
        )
        for old in finished[: len(_vision_tasks) - _MAX_STORED_TASKS]:
            _vision_tasks.pop(old["task_id"], None)

    asyncio.create_task(_vision_review_worker(task_id, body, char_map, target_slugs))

    return {
        "task_id": task_id,
        "status": "running",
        "message": f"Vision review started for {len(target_slugs)} character(s), max {body.max_images} images",
        "poll_url": f"/api/visual/approval/vision-review/{task_id}",
    }


# Static route MUST come before the {task_id} dynamic route
@router.get("/approval/vision-review/tasks")
async def list_vision_tasks():
    """List all vision review tasks (running + recent finished)."""
    return {"tasks": list(_vision_tasks.values())}


@router.get("/approval/vision-review/{task_id}")
async def get_vision_task(task_id: str):
    """Poll vision review task progress."""
    task = _vision_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return task


@router.post("/approval/vision-review/{task_id}/cancel")
async def cancel_vision_task(task_id: str):
    """Cancel a running vision review task. Takes effect before next image."""
    task = _vision_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    if task["status"] != "running":
        return {"task_id": task_id, "status": task["status"], "message": "Task is not running"}
    task["cancelled"] = True
    return {"task_id": task_id, "message": "Cancellation requested — will stop before next image"}


async def _vision_review_worker(
    task_id: str,
    body: VisionReviewRequest,
    char_map: dict,
    target_slugs: list[str],
):
    """Background worker — processes vision review images without blocking the event loop.

    Each Ollama call runs in a thread via asyncio.to_thread(). Async DB/EventBus
    calls run normally on the event loop. The circuit breaker stops after 5
    consecutive Ollama errors (e.g. Ollama down).
    """
    task = _vision_tasks[task_id]
    slugs_needing_regen: set[str] = set()
    consecutive_errors = 0

    try:
        for slug in target_slugs:
            if task["cancelled"]:
                break

            db_info = char_map[slug]
            checkpoint = db_info.get("checkpoint_model", "unknown")

            profile = get_model_profile(
                checkpoint,
                db_architecture=db_info.get("model_architecture"),
                db_prompt_format=db_info.get("prompt_format"),
            )
            effective_reject, effective_approve = adjust_thresholds(
                profile, body.auto_reject_threshold, body.auto_approve_threshold
            )

            char_dir = BASE_PATH / slug
            images_path = char_dir / "images"
            if not images_path.exists():
                continue

            approval_file = char_dir / "approval_status.json"
            approval_status = {}
            if approval_file.exists():
                with open(approval_file) as f:
                    approval_status = json.load(f)

            target_statuses = ("pending", "approved") if body.include_approved else ("pending",)
            target_pngs = [
                img for img in sorted(images_path.glob("*.png"))
                if approval_status.get(img.name, "pending") in target_statuses
            ]

            status_changed = False

            for img_path in target_pngs:
                if task["reviewed"] >= body.max_images or task["cancelled"]:
                    break

                # Circuit breaker: stop if Ollama keeps failing
                if consecutive_errors >= _CONSECUTIVE_ERROR_LIMIT:
                    logger.error(
                        f"[{task_id}] Circuit breaker: {consecutive_errors} consecutive Ollama errors. "
                        f"Stopping review — Ollama may be down."
                    )
                    task["error_message"] = (
                        f"Stopped after {consecutive_errors} consecutive Ollama errors. "
                        f"Check Ollama status: curl {OLLAMA_URL}/api/tags"
                    )
                    break

                task["current_image"] = f"{slug}/{img_path.name}"
                logger.info(f"[{task_id}] Vision reviewing {slug}/{img_path.name} ({task['reviewed'] + 1}/{body.max_images})")

                try:
                    # Run blocking Ollama call in thread pool — event loop stays free
                    review = await asyncio.to_thread(
                        vision_review_image,
                        img_path,
                        character_name=db_info["name"],
                        design_prompt=db_info.get("design_prompt", ""),
                        model=body.model,
                        appearance_data=db_info.get("appearance_data"),
                        model_profile=profile,
                    )
                    consecutive_errors = 0  # Reset on success
                except Exception as e:
                    logger.warning(f"[{task_id}] Vision review failed for {img_path.name}: {e}")
                    consecutive_errors += 1
                    task["errors"] += 1
                    task["results"].append({
                        "image": img_path.name,
                        "character_slug": slug,
                        "quality_score": None,
                        "solo": None,
                        "action": "error",
                        "issues": [f"Review failed: {e}"],
                    })
                    task["reviewed"] += 1
                    continue

                quality_score = round(
                    (review["character_match"] + review["clarity"] + review["training_value"]) / 30, 2
                )

                # Update .meta.json
                meta_path = img_path.with_suffix(".meta.json")
                meta = {}
                if meta_path.exists():
                    try:
                        with open(meta_path) as f:
                            meta = json.load(f)
                    except (json.JSONDecodeError, IOError):
                        pass
                meta["vision_review"] = review
                meta["quality_score"] = quality_score
                with open(meta_path, "w") as f:
                    json.dump(meta, f, indent=2)

                if review.get("caption"):
                    caption_path = img_path.with_suffix(".txt")
                    if body.update_captions or quality_score >= effective_approve:
                        caption_path.write_text(review["caption"])

                # --- Auto-triage decision ---
                is_already_approved = approval_status.get(img_path.name) == "approved"
                action = "approved" if is_already_approved else "pending"

                if is_already_approved:
                    if not review.get("solo", False):
                        action = "flagged_multi"
                    logger.info(f"[{task_id}] Scored approved {slug}/{img_path.name} (Q:{quality_score:.0%})")

                elif quality_score < effective_reject:
                    action = "rejected"
                    approval_status[img_path.name] = "rejected"
                    status_changed = True
                    task["auto_rejected"] += 1

                    categories = vision_issues_to_categories(review)
                    feedback_str = "|".join(categories) if categories else "bad_quality"
                    issues_text = "; ".join(review.get("issues", []))
                    if issues_text:
                        feedback_str += f"|Vision:{issues_text[:200]}"
                    record_rejection(slug, img_path.name, feedback_str)
                    slugs_needing_regen.add(slug)

                    neg_terms = [REJECTION_NEGATIVE_MAP[c] for c in categories if c in REJECTION_NEGATIVE_MAP]
                    await log_rejection(
                        character_slug=slug, image_name=img_path.name,
                        categories=categories, feedback_text=feedback_str,
                        negative_additions=neg_terms, quality_score=quality_score,
                        project_name=db_info.get("project_name"), source="vision",
                        checkpoint_model=checkpoint,
                    )
                    await log_decision(
                        decision_type="auto_reject", character_slug=slug,
                        project_name=db_info.get("project_name"),
                        input_context={"quality_score": quality_score, "threshold": effective_reject,
                                       "model_profile": profile["style_label"],
                                       "issues": review.get("issues", [])[:5]},
                        decision_made="rejected", confidence_score=round(1.0 - quality_score, 2),
                        reasoning=f"Quality {quality_score:.0%} below {effective_reject:.0%}. Issues: {', '.join(categories)}",
                    )
                    await event_bus.emit(IMAGE_REJECTED, {
                        "character_slug": slug, "image_name": img_path.name,
                        "quality_score": quality_score, "categories": categories,
                        "project_name": db_info.get("project_name"),
                        "checkpoint_model": checkpoint,
                    })
                    logger.info(f"[{task_id}] Auto-rejected {slug}/{img_path.name} (Q:{quality_score:.0%})")

                elif quality_score >= effective_approve and review.get("solo", False):
                    action = "approved"
                    approval_status[img_path.name] = "approved"
                    status_changed = True
                    task["auto_approved"] += 1

                    await log_approval(
                        character_slug=slug, image_name=img_path.name,
                        quality_score=quality_score, auto_approved=True,
                        vision_review=review, project_name=db_info.get("project_name"),
                        checkpoint_model=checkpoint,
                    )
                    await log_decision(
                        decision_type="auto_approve", character_slug=slug,
                        project_name=db_info.get("project_name"),
                        input_context={"quality_score": quality_score, "solo": True,
                                       "threshold": effective_approve,
                                       "model_profile": profile["style_label"]},
                        decision_made="approved", confidence_score=quality_score,
                        reasoning=f"Quality {quality_score:.0%} above {effective_approve:.0%}, solo confirmed",
                    )
                    await event_bus.emit(IMAGE_APPROVED, {
                        "character_slug": slug, "image_name": img_path.name,
                        "quality_score": quality_score,
                        "project_name": db_info.get("project_name"),
                        "checkpoint_model": checkpoint,
                    })
                    logger.info(f"[{task_id}] Auto-approved {slug}/{img_path.name} (Q:{quality_score:.0%})")

                task["results"].append({
                    "image": img_path.name,
                    "character_slug": slug,
                    "quality_score": quality_score,
                    "solo": review.get("solo"),
                    "action": action,
                    "issues": review.get("issues", []),
                })
                task["reviewed"] += 1

            if status_changed:
                with open(approval_file, "w") as f:
                    json.dump(approval_status, f, indent=2)

            if task["reviewed"] >= body.max_images:
                break
            if consecutive_errors >= _CONSECUTIVE_ERROR_LIMIT:
                break

        # Queue regeneration for characters that had rejections
        if body.regenerate:
            for slug in slugs_needing_regen:
                try:
                    queue_regeneration(slug)
                    task["regen_queued"] += 1
                    await log_decision(
                        decision_type="regeneration", character_slug=slug,
                        project_name=char_map.get(slug, {}).get("project_name"),
                        input_context={"trigger": "auto_reject_batch", "rejected_count": task["auto_rejected"]},
                        decision_made="queued_regeneration",
                        reasoning="Character had auto-rejected images, queued feedback-aware regeneration",
                    )
                    await event_bus.emit(REGENERATION_QUEUED, {
                        "character_slug": slug,
                        "project_name": char_map.get(slug, {}).get("project_name"),
                    })
                    logger.info(f"[{task_id}] Queued regeneration for {slug}")
                except Exception as e:
                    logger.warning(f"[{task_id}] Regeneration failed for {slug}: {e}")

        task["status"] = "cancelled" if task["cancelled"] else "completed"

    except Exception as e:
        logger.error(f"[{task_id}] Vision review worker crashed: {e}", exc_info=True)
        task["status"] = "failed"
        task["error_message"] = str(e)

    finally:
        task["finished_at"] = datetime.now().isoformat()
        task["current_image"] = None
        logger.info(
            f"[{task_id}] Vision review {task['status']}: "
            f"reviewed={task['reviewed']}, approved={task['auto_approved']}, "
            f"rejected={task['auto_rejected']}, errors={task['errors']}"
        )
