"""Visual Pipeline router — generation, gallery, and vision quality review endpoints."""

import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from packages.core.config import BASE_PATH, COMFYUI_OUTPUT_DIR, VISION_MODEL, normalize_sampler
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


@router.post("/approval/vision-review")
async def vision_review(body: VisionReviewRequest):
    """Run vision training quality review on pending images.

    Reviews each image, scores it, then auto-triages:
    - quality_score < auto_reject_threshold -> reject + record feedback + queue regen
    - quality_score >= auto_approve_threshold AND solo -> auto-approve
    - Everything else -> stays pending with scores for manual review

    Updates .meta.json with vision_review dict and quality_score.
    Optionally overwrites .txt captions with vision model captions.
    """
    char_map = await get_char_project_map()

    # Determine which characters to process
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

    results = []
    reviewed = 0
    auto_approved = 0
    auto_rejected = 0
    slugs_needing_regen: set[str] = set()

    for slug in target_slugs:
        db_info = char_map[slug]
        checkpoint = db_info.get("checkpoint_model", "unknown")

        # Get model profile for model-aware vision review
        profile = get_model_profile(
            checkpoint,
            db_architecture=db_info.get("model_architecture"),
            db_prompt_format=db_info.get("prompt_format"),
        )
        # Adjust thresholds based on model type
        effective_reject, effective_approve = adjust_thresholds(
            profile, body.auto_reject_threshold, body.auto_approve_threshold
        )

        char_dir = BASE_PATH / slug
        images_path = char_dir / "images"
        if not images_path.exists():
            continue

        # Load approval status to find pending-only images
        approval_file = char_dir / "approval_status.json"
        approval_status = {}
        if approval_file.exists():
            with open(approval_file) as f:
                approval_status = json.load(f)

        if body.include_approved:
            # Review both pending and approved images (score only for approved)
            target_statuses = ("pending", "approved")
        else:
            target_statuses = ("pending",)
        target_pngs = [
            img for img in sorted(images_path.glob("*.png"))
            if approval_status.get(img.name, "pending") in target_statuses
        ]

        status_changed = False

        char_species = (db_info.get("appearance_data") or {}).get("species", "")

        for img_path in target_pngs:
            if reviewed >= body.max_images:
                break

            logger.info(f"Vision reviewing {slug}/{img_path.name} ({reviewed + 1}/{body.max_images})")

            try:
                review = vision_review_image(
                    img_path,
                    character_name=db_info["name"],
                    design_prompt=db_info.get("design_prompt", ""),
                    model=body.model,
                    appearance_data=db_info.get("appearance_data"),
                    model_profile=profile,
                )
            except Exception as e:
                logger.warning(f"Vision review failed for {img_path.name}: {e}")
                results.append({
                    "image": img_path.name,
                    "character_slug": slug,
                    "quality_score": None,
                    "solo": None,
                    "action": "error",
                    "issues": [f"Review failed: {e}"],
                })
                reviewed += 1
                continue

            # Compute quality_score as normalized average of key dimensions
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

            # Update .txt caption if requested or if auto-approving (good caption for training)
            if review.get("caption"):
                caption_path = img_path.with_suffix(".txt")
                if body.update_captions or quality_score >= effective_approve:
                    caption_path.write_text(review["caption"])

            # --- Auto-triage decision ---
            is_already_approved = approval_status.get(img_path.name) == "approved"
            action = "approved" if is_already_approved else "pending"

            if is_already_approved:
                # Score-only mode: don't change approval status, just record vision data
                if not review.get("solo", False):
                    action = "flagged_multi"  # signal for bulk-reject later
                logger.info(f"Scored approved {slug}/{img_path.name} (Q:{quality_score:.0%}, solo={review.get('solo')})")

            elif quality_score < effective_reject:
                # AUTO-REJECT: bad image -> reject, record feedback, flag for regen
                action = "rejected"
                approval_status[img_path.name] = "rejected"
                status_changed = True
                auto_rejected += 1

                # Record structured feedback from vision findings
                categories = vision_issues_to_categories(review)
                feedback_str = "|".join(categories) if categories else "bad_quality"
                issues_text = "; ".join(review.get("issues", []))
                if issues_text:
                    feedback_str += f"|Vision:{issues_text[:200]}"
                record_rejection(slug, img_path.name, feedback_str)
                slugs_needing_regen.add(slug)

                # Audit: log rejection + autonomous decision
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

                logger.info(f"Auto-rejected {slug}/{img_path.name} (Q:{quality_score:.0%}, threshold:{effective_reject:.0%}, issues: {categories})")

            elif quality_score >= effective_approve and review.get("solo", False):
                # AUTO-APPROVE: high quality + solo character -> approve
                action = "approved"
                approval_status[img_path.name] = "approved"
                status_changed = True
                auto_approved += 1

                # Audit: log approval + autonomous decision
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

                logger.info(f"Auto-approved {slug}/{img_path.name} (Q:{quality_score:.0%})")

            results.append({
                "image": img_path.name,
                "character_slug": slug,
                "quality_score": quality_score,
                "solo": review.get("solo"),
                "action": action,
                "issues": review.get("issues", []),
            })
            reviewed += 1

        # Write back approval status if any changes
        if status_changed:
            with open(approval_file, "w") as f:
                json.dump(approval_status, f, indent=2)

        if reviewed >= body.max_images:
            break

    # Queue regeneration for characters that had rejections
    regen_queued = 0
    if body.regenerate:
        for slug in slugs_needing_regen:
            try:
                queue_regeneration(slug)
                regen_queued += 1

                await log_decision(
                    decision_type="regeneration", character_slug=slug,
                    project_name=char_map.get(slug, {}).get("project_name"),
                    input_context={"trigger": "auto_reject_batch", "rejected_count": auto_rejected},
                    decision_made="queued_regeneration",
                    reasoning="Character had auto-rejected images, queued feedback-aware regeneration",
                )
                await event_bus.emit(REGENERATION_QUEUED, {
                    "character_slug": slug,
                    "project_name": char_map.get(slug, {}).get("project_name"),
                })

                logger.info(f"Queued feedback-aware regeneration for {slug}")
            except Exception as e:
                logger.warning(f"Regeneration failed for {slug}: {e}")

    return {
        "model": body.model or VISION_MODEL,
        "reviewed": reviewed,
        "auto_approved": auto_approved,
        "auto_rejected": auto_rejected,
        "regen_queued": regen_queued,
        "character_slug": body.character_slug,
        "project": body.project_name,
        "results": results,
    }
