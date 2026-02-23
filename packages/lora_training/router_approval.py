"""Approval sub-router -- pending images, approve/reject, reassign, bulk operations."""

import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from packages.core.config import BASE_PATH
from packages.core.db import get_char_project_map, invalidate_char_cache, connect_direct
from packages.core.models import (
    ApprovalRequest,
    ReassignRequest,
    BulkReassignRequest,
    BulkRejectRequest,
)
from .feedback import (
    record_rejection,
    queue_regeneration,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ===================================================================
# Approval endpoints
# ===================================================================

@router.get("/approval/pending")
async def get_pending_approvals():
    """Get all pending images across all characters, with project info."""
    pending = []
    if not BASE_PATH.exists():
        return {"pending_images": pending}

    char_map = await get_char_project_map()

    for char_dir in sorted(BASE_PATH.iterdir()):
        if not char_dir.is_dir():
            continue
        images_path = char_dir / "images"
        if not images_path.exists():
            continue

        slug = char_dir.name
        if slug == "_unclassified":
            db_info = {
                "name": "Unclassified",
                "project_name": "",
                "design_prompt": "",
                "checkpoint_model": "",
                "default_style": "",
            }
        else:
            db_info = char_map.get(slug)
            if not db_info:
                continue

        approval_file = char_dir / "approval_status.json"
        approval_status = {}
        if approval_file.exists():
            with open(approval_file) as f:
                approval_status = json.load(f)

        # Build set of pending filenames first, then only stat those
        pending_names = {name for name, st in approval_status.items() if st == "pending"}
        # Also include files not in approval_status at all (default pending)
        all_pngs = [img.name for img in images_path.glob("*.png")]
        for name in all_pngs:
            if name not in approval_status:
                pending_names.add(name)

        if not pending_names:
            continue

        # Single stat call batch via scandir (much faster than per-file stat)
        file_ctimes = {}
        with os.scandir(images_path) as entries:
            for e in entries:
                if e.name in pending_names and e.name.endswith(".png"):
                    try:
                        file_ctimes[e.name] = e.stat().st_ctime
                    except OSError:
                        file_ctimes[e.name] = 0

        proj_name = db_info.get("project_name", "")
        char_name = db_info["name"]
        design_prompt = db_info.get("design_prompt", "")
        checkpoint = db_info.get("checkpoint_model", "")
        style = db_info.get("default_style", "")

        for name, ctime in file_ctimes.items():
            source = "generated"
            if name.startswith("yt_unclassified"):
                source = "unclassified"
            elif name.startswith("yt_ref"):
                source = "youtube"
            elif name.startswith("upload_"):
                source = "upload"
            elif name.startswith("ref_"):
                source = "reference"

            # For unclassified images, read project_name from per-image metadata
            img_proj_name = proj_name
            entry = {
                "id": f"{slug}/{name}",
                "character_name": char_name,
                "character_slug": slug,
                "name": name,
                "project_name": img_proj_name,
                "checkpoint_model": checkpoint,
                "default_style": style,
                "status": "pending",
                "source": source,
                "created_at": datetime.fromtimestamp(ctime).isoformat(),
                "_sort_ts": ctime,
            }

            # Read metadata (skip only old yt_ref YouTube frames that have no .meta.json)
            img_path = images_path / name
            meta_path = img_path.with_suffix(".meta.json")
            if meta_path.exists():
                try:
                    with open(meta_path) as f:
                        meta = json.load(f)
                    entry["metadata"] = meta
                    # For unclassified images, use per-image project_name
                    if slug == "_unclassified" and meta.get("project_name"):
                        entry["project_name"] = meta["project_name"]
                except (json.JSONDecodeError, IOError):
                    pass
            caption_path = img_path.with_suffix(".txt")
            if caption_path.exists():
                try:
                    entry["prompt"] = caption_path.read_text().strip()
                except IOError:
                    pass

            pending.append(entry)

    pending.sort(key=lambda x: x.pop("_sort_ts", 0), reverse=True)
    # Send design prompts once per character (not per image)
    character_designs = {
        slug: info.get("design_prompt", "")
        for slug, info in char_map.items()
    }
    return {"pending_images": pending, "character_designs": character_designs}

@router.post("/approval/approve")
async def approve_image(approval: ApprovalRequest):
    """Approve or reject an image."""
    if approval.character_slug:
        safe_name = approval.character_slug
    else:
        safe_name = re.sub(r'[^a-z0-9_-]', '', approval.character_name.lower().replace(' ', '_'))

    dataset_path = BASE_PATH / safe_name
    approval_file = dataset_path / "approval_status.json"

    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail=f"Character dataset not found: {safe_name}")

    approval_status = {}
    if approval_file.exists():
        with open(approval_file) as f:
            approval_status = json.load(f)

    approval_status[approval.image_name] = "approved" if approval.approved else "rejected"

    with open(approval_file, "w") as f:
        json.dump(approval_status, f, indent=2)

    # If user provided an edited prompt, update BOTH the .txt sidecar AND the DB design_prompt (SSOT)
    prompt_updated = False
    if approval.edited_prompt:
        image_path = dataset_path / "images" / approval.image_name
        caption_path = image_path.with_suffix(".txt")
        caption_path.write_text(approval.edited_prompt)

        try:
            conn = await connect_direct()
            row = await conn.fetchrow("""
                SELECT c.id, c.name, c.design_prompt
                FROM characters c
                WHERE REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1
                  AND c.project_id IS NOT NULL
                ORDER BY LENGTH(COALESCE(c.design_prompt, '')) DESC
                LIMIT 1
            """, safe_name)
            if row:
                old_prompt = row["design_prompt"] or ""
                new_prompt = approval.edited_prompt.strip()
                if new_prompt != old_prompt:
                    await conn.execute(
                        "UPDATE characters SET design_prompt = $1 WHERE id = $2",
                        new_prompt, row["id"],
                    )
                    prompt_updated = True
                    logger.info(f"SSOT updated: {row['name']} design_prompt changed ({len(old_prompt)} -> {len(new_prompt)} chars)")
                    invalidate_char_cache()
            await conn.close()
        except Exception as e:
            logger.warning(f"Failed to update DB design_prompt for {safe_name}: {e}")

    if approval.feedback:
        feedback_file = dataset_path / "feedback.log"
        with open(feedback_file, "a") as f:
            f.write(f"{datetime.now().isoformat()} - {approval.image_name}: {approval.feedback}\n")

    if not approval.approved:
        record_rejection(safe_name, approval.image_name, approval.feedback or "Rejected", approval.edited_prompt)

    regenerated = False
    if not approval.approved:
        import packages.core.replenishment as replenishment
        if replenishment._enabled:
            try:
                queue_regeneration(safe_name)
                regenerated = True
            except Exception as e:
                logger.warning(f"Regeneration queue failed for {safe_name}: {e}")

    return {
        "message": f"Image {approval.image_name} {'approved' if approval.approved else 'rejected'}",
        "regeneration_queued": regenerated,
        "design_prompt_updated": prompt_updated,
    }


@router.post("/approval/reassign")
async def reassign_image(req: ReassignRequest):
    """Move an image from one character's dataset to another."""
    source_dir = BASE_PATH / req.character_slug
    target_dir = BASE_PATH / req.target_character_slug

    if not source_dir.exists():
        raise HTTPException(status_code=404, detail=f"Source character not found: {req.character_slug}")
    if not target_dir.exists():
        (target_dir / "images").mkdir(parents=True, exist_ok=True)

    source_img = source_dir / "images" / req.image_name
    if not source_img.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {req.image_name}")

    old_name = req.image_name
    new_name = re.sub(
        rf'^(yt_ref_|gen_){re.escape(req.character_slug)}_',
        rf'\g<1>{req.target_character_slug}_',
        old_name,
    )
    if new_name == old_name:
        logger.warning(f"Reassign: filename '{old_name}' doesn't match expected pattern, keeping as-is")

    target_img = target_dir / "images" / new_name

    shutil.move(str(source_img), str(target_img))
    for ext in (".txt", ".meta.json"):
        source_sidecar = source_img.with_suffix(ext)
        target_sidecar = target_img.with_suffix(ext)
        if source_sidecar.exists():
            shutil.move(str(source_sidecar), str(target_sidecar))

    meta_path = target_img.with_suffix(".meta.json")
    if meta_path.exists():
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            meta["reassigned_from"] = req.character_slug
            meta["classified_character"] = req.target_character_slug
            meta["character_name"] = req.target_character_slug.replace("_", " ").title()
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to update meta.json for {new_name}: {e}")

    source_approval_file = source_dir / "approval_status.json"
    if source_approval_file.exists():
        with open(source_approval_file) as f:
            source_status = json.load(f)
        source_status.pop(old_name, None)
        with open(source_approval_file, "w") as f:
            json.dump(source_status, f, indent=2)

    target_approval_file = target_dir / "approval_status.json"
    target_status = {}
    if target_approval_file.exists():
        with open(target_approval_file) as f:
            target_status = json.load(f)
    target_status[new_name] = "pending"
    with open(target_approval_file, "w") as f:
        json.dump(target_status, f, indent=2)

    logger.info(f"Reassigned {old_name} -> {new_name}: {req.character_slug} -> {req.target_character_slug}")

    return {
        "message": f"Image reassigned to {req.target_character_slug}",
        "source": req.character_slug,
        "target": req.target_character_slug,
        "old_name": old_name,
        "new_name": new_name,
    }


@router.post("/approval/bulk-reassign")
async def bulk_reassign(req: BulkReassignRequest):
    """Batch-reassign multiple images to a target character."""
    target_dir = BASE_PATH / req.target_character_slug
    if not target_dir.exists():
        (target_dir / "images").mkdir(parents=True, exist_ok=True)

    results = []
    errors = []
    for item in req.images:
        slug = item.get("character_slug", "")
        image_name = item.get("image_name", "")
        if not slug or not image_name:
            errors.append({"image_name": image_name, "error": "missing character_slug or image_name"})
            continue
        try:
            single = ReassignRequest(
                character_slug=slug,
                image_name=image_name,
                target_character_slug=req.target_character_slug,
            )
            result = await reassign_image(single)
            results.append(result)
        except Exception as e:
            errors.append({"image_name": image_name, "error": str(e)})

    return {
        "message": f"Reassigned {len(results)} image(s) to {req.target_character_slug}",
        "reassigned_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }


@router.post("/approval/bulk-reject")
async def bulk_reject(req: BulkRejectRequest):
    """Bulk reject images by criteria (solo_false, no_vision_review, low_quality)."""
    if not req.character_slug and not req.project_name:
        raise HTTPException(status_code=400, detail="Provide character_slug or project_name")

    if req.project_name:
        conn = await connect_direct()
        rows = await conn.fetch(
            """SELECT REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') AS slug
               FROM characters c JOIN projects p ON c.project_id = p.id
               WHERE p.name = $1""",
            req.project_name,
        )
        await conn.close()
        slugs = [r["slug"] for r in rows]
        if not slugs:
            raise HTTPException(status_code=404, detail=f"No characters found for project: {req.project_name}")
    else:
        slugs = [req.character_slug]

    all_results = {}
    total_matched = 0

    for slug in slugs:
        dataset_path = BASE_PATH / slug
        images_dir = dataset_path / "images"
        approval_file = dataset_path / "approval_status.json"

        if not images_dir.exists():
            continue

        statuses = {}
        if approval_file.exists():
            with open(approval_file) as f:
                statuses = json.load(f)

        matches = []
        for img_file in sorted(images_dir.glob("*.png")):
            img_name = img_file.name
            if statuses.get(img_name) != "approved":
                continue

            meta_file = images_dir / f"{img_file.stem}.meta.json"
            meta = {}
            if meta_file.exists():
                with open(meta_file) as f:
                    meta = json.load(f)

            # Legacy compat: old meta files used "llava_review" key
            review = meta.get("vision_review") or meta.get("llava_review")

            if req.criteria == "solo_false":
                if review and review.get("solo") is False:
                    matches.append(img_name)
            elif req.criteria == "no_vision_review":
                if not review:
                    matches.append(img_name)
            elif req.criteria == "low_quality":
                qs = meta.get("quality_score")
                if qs is not None and qs < req.quality_threshold:
                    matches.append(img_name)
            else:
                raise HTTPException(status_code=400, detail=f"Unknown criteria: {req.criteria}. Use: solo_false, no_vision_review, low_quality")

        if not matches:
            continue

        all_results[slug] = matches
        total_matched += len(matches)

        if not req.dry_run:
            for img_name in matches:
                statuses[img_name] = "rejected"

            with open(approval_file, "w") as f:
                json.dump(statuses, f, indent=2)

            feedback_file = dataset_path / "feedback.json"
            feedback = {"rejections": [], "rejection_count": 0, "negative_additions": [], "categories": []}
            if feedback_file.exists():
                try:
                    loaded = json.load(open(feedback_file))
                    if isinstance(loaded, dict):
                        feedback.update(loaded)
                except (json.JSONDecodeError, IOError):
                    pass
            # Ensure required keys
            if not isinstance(feedback.get("rejections"), list):
                feedback["rejections"] = []
            if not isinstance(feedback.get("categories"), list):
                feedback["categories"] = []
            category = "not_solo" if req.criteria == "solo_false" else "bad_quality"
            if category not in feedback["categories"]:
                feedback["categories"].append(category)
            # Record individual rejections for the feedback loop
            for img_name in matches:
                feedback["rejections"].append({
                    "image": img_name,
                    "feedback": f"batch_{req.criteria}",
                    "categories": [category],
                    "timestamp": datetime.now().isoformat(),
                })
            feedback["rejection_count"] = len(feedback["rejections"])
            # Keep only last 50 rejections
            if len(feedback["rejections"]) > 50:
                feedback["rejections"] = feedback["rejections"][-50:]
                feedback["rejection_count"] = len(feedback["rejections"])
            with open(feedback_file, "w") as f:
                json.dump(feedback, f, indent=2)

    if req.dry_run:
        return {
            "dry_run": True,
            "project": req.project_name,
            "criteria": req.criteria,
            "total_matched": total_matched,
            "by_character": {slug: len(imgs) for slug, imgs in all_results.items()},
            "matched_images": all_results,
        }

    return {
        "dry_run": False,
        "project": req.project_name,
        "criteria": req.criteria,
        "total_rejected": total_matched,
        "by_character": {slug: len(imgs) for slug, imgs in all_results.items()},
        "rejected_images": all_results,
    }
