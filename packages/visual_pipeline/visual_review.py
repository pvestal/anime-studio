"""Visual Pipeline — background vision quality review sub-router.

Extracted from visual_pipeline/router.py.  Manages background Ollama-based
quality review tasks: start, poll, cancel, list.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from packages.core.config import BASE_PATH, OLLAMA_URL
from packages.core.db import get_char_project_map
from packages.core.models import VisionReviewRequest
from packages.lora_training.feedback import record_rejection, queue_regeneration, REJECTION_NEGATIVE_MAP
from packages.core.audit import log_decision, log_rejection, log_approval
from packages.core.events import event_bus, IMAGE_REJECTED, IMAGE_APPROVED, REGENERATION_QUEUED

from packages.core.model_profiles import get_model_profile, adjust_thresholds

from .vision import vision_review_image, vision_issues_to_categories

logger = logging.getLogger(__name__)
router = APIRouter()

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
