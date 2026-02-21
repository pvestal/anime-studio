"""LoRA Training router — dataset and approval endpoints, with sub-routers for training and ingestion."""

import base64
import json
import logging
import os
import re
import shutil
import urllib.request as _ur
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from packages.core.config import BASE_PATH, _PROJECT_DIR, OLLAMA_URL, VISION_MODEL
from packages.core.db import get_char_project_map, invalidate_char_cache, connect_direct
from packages.core.models import (
    ApprovalRequest,
    ReassignRequest,
    DatasetImageCreate,
    BulkRejectRequest,
)
from .feedback import (
    record_rejection,
    queue_regeneration,
)
from .ingest_router import ingest_router
from .training_router import training_router

logger = logging.getLogger(__name__)
router = APIRouter()
router.include_router(ingest_router)
router.include_router(training_router)

# ===================================================================
# Dataset endpoints
# ===================================================================

@router.get("/dataset/{character_name}")
async def get_dataset_info(character_name: str):
    """Get dataset images and approval status."""
    safe_name = character_name.lower().replace(" ", "_")
    dataset_path = BASE_PATH / safe_name
    images_path = dataset_path / "images"

    if not images_path.exists():
        return {"character": character_name, "images": []}

    approval_file = dataset_path / "approval_status.json"
    approval_status = {}
    if approval_file.exists():
        with open(approval_file) as f:
            approval_status = json.load(f)

    images = []
    for img in sorted(images_path.glob("*.png")):
        status = approval_status.get(img.name, "pending")
        caption_file = img.with_suffix(".txt")
        prompt = ""
        if caption_file.exists():
            prompt = caption_file.read_text().strip()
        images.append({
            "id": f"{safe_name}/{img.name}",
            "name": img.name,
            "status": status,
            "prompt": prompt,
            "created_at": datetime.fromtimestamp(img.stat().st_ctime).isoformat(),
        })

    return {"character": character_name, "images": images}

@router.post("/dataset/{character_name}/images")
async def add_dataset_image(character_name: str, image: DatasetImageCreate):
    """Add an image entry to a character's dataset."""
    safe_name = character_name.lower().replace(" ", "_")
    dataset_path = BASE_PATH / safe_name / "images"

    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail="Character dataset not found")

    image_id = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return {"message": "Image entry created", "image_id": image_id}

@router.get("/characters/{character_slug}/reference-images")
async def list_reference_images(character_slug: str):
    """List reference images for a character (used by IP-Adapter)."""
    ref_dir = BASE_PATH / character_slug / "reference_images"
    if not ref_dir.exists():
        return {"character_slug": character_slug, "images": [], "count": 0}
    images = sorted([f.name for f in ref_dir.iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")])
    return {"character_slug": character_slug, "images": images, "count": len(images)}

@router.post("/characters/{character_slug}/reference-images")
async def add_reference_image(character_slug: str, body: dict):
    """Copy an approved image to reference_images/ for IP-Adapter conditioning."""
    ref_dir = BASE_PATH / character_slug / "reference_images"
    ref_dir.mkdir(parents=True, exist_ok=True)

    image_name = body.get("image_name")
    if image_name:
        source = BASE_PATH / character_slug / "images" / image_name
        if not source.exists():
            raise HTTPException(status_code=404, detail=f"Image '{image_name}' not found")
        dest = ref_dir / image_name
        shutil.copy2(source, dest)
        logger.info(f"Reference image added: {character_slug}/{image_name}")
        return {"message": f"Added {image_name} as reference", "path": str(dest)}

    raise HTTPException(status_code=400, detail="Provide image_name")

@router.delete("/characters/{character_slug}/reference-images/{image_name}")
async def remove_reference_image(character_slug: str, image_name: str):
    """Remove a reference image."""
    ref_path = BASE_PATH / character_slug / "reference_images" / image_name
    if not ref_path.exists():
        raise HTTPException(status_code=404, detail="Reference image not found")
    ref_path.unlink()
    return {"message": f"Removed reference image {image_name}"}

@router.get("/dataset/{character_name}/image/{image_name}")
async def get_image(character_name: str, image_name: str):
    """Serve an image file."""
    safe_name = character_name.lower().replace(" ", "_")
    image_path = BASE_PATH / safe_name / "images" / image_name

    if not image_path.exists():
        placeholder = _PROJECT_DIR / "static" / "placeholder.png"
        if placeholder.exists():
            return FileResponse(placeholder)
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(image_path)

@router.get("/dataset/{character_name}/image/{image_name}/metadata")
async def get_image_metadata(character_name: str, image_name: str):
    """Get generation metadata for a specific image."""
    safe_name = character_name.lower().replace(" ", "_")
    image_path = BASE_PATH / safe_name / "images" / image_name
    meta_path = image_path.with_suffix(".meta.json")

    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    if meta_path.exists():
        with open(meta_path) as f:
            return json.load(f)

    # Fallback: partial metadata from .txt sidecar + project info
    char_map = await get_char_project_map()
    db_info = char_map.get(safe_name, {})
    caption_file = image_path.with_suffix(".txt")
    return {
        "seed": None,
        "design_prompt": db_info.get("design_prompt", ""),
        "full_prompt": caption_file.read_text().strip() if caption_file.exists() else "",
        "checkpoint_model": db_info.get("checkpoint_model", ""),
        "cfg_scale": db_info.get("cfg_scale"),
        "steps": db_info.get("steps"),
        "source": "backfill_partial",
        "backfilled": True,
    }


# ===================================================================
# Library endpoint (single call for all approved images)
# ===================================================================

@router.get("/library")
async def get_library():
    """Get all approved images across all characters in one fast call."""
    if not BASE_PATH.exists():
        return {"images": [], "characters": []}

    char_map = await get_char_project_map()
    images = []
    char_counts: dict[str, dict] = {}

    for char_dir in sorted(BASE_PATH.iterdir()):
        if not char_dir.is_dir():
            continue
        images_path = char_dir / "images"
        if not images_path.exists():
            continue

        slug = char_dir.name
        if slug == "_unclassified":
            db_info = {"name": "Unclassified"}
        else:
            db_info = char_map.get(slug)
            if not db_info:
                continue

        approval_file = char_dir / "approval_status.json"
        if not approval_file.exists():
            continue
        with open(approval_file) as f:
            approval_status = json.load(f)

        approved_names = {name for name, st in approval_status.items() if st == "approved"}
        if not approved_names:
            continue

        # Filter out stale entries (files moved/deleted but still in approval_status)
        existing_files = set(f.name for f in images_path.iterdir() if f.suffix == ".png")
        approved_names &= existing_files
        if not approved_names:
            continue

        char_name = db_info["name"]
        project_name = db_info.get("project_name", "Unknown")
        checkpoint_model = db_info.get("checkpoint_model", "unknown")
        char_counts[slug] = {
            "slug": slug, "name": char_name, "approved": len(approved_names),
            "project_name": project_name, "checkpoint_model": checkpoint_model,
        }

        for name in sorted(approved_names):
            images.append({
                "slug": slug,
                "characterName": char_name,
                "name": name,
                "project_name": project_name,
                "checkpoint_model": checkpoint_model,
            })

    characters = sorted(char_counts.values(), key=lambda c: c["name"])

    # Deduplicated filter lists for frontend pills
    projects = sorted({c["project_name"] for c in char_counts.values()})
    models = sorted({c["checkpoint_model"] for c in char_counts.values() if c["checkpoint_model"]})

    return {"images": images, "characters": characters, "projects": projects, "models": models}


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
            feedback = {}
            if feedback_file.exists():
                with open(feedback_file) as f:
                    feedback = json.load(f)
            category = "not_solo" if req.criteria == "solo_false" else "bad_quality"
            existing = feedback.get("categories", [])
            if category not in existing:
                existing.append(category)
            feedback["categories"] = existing
            feedback["rejection_count"] = feedback.get("rejection_count", 0) + len(matches)
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


# ===================================================================
# Dataset statistics (real filesystem counts for Analytics)
# ===================================================================

@router.get("/dataset-stats")
async def dataset_stats(project_name: str = None):
    """Aggregate real dataset stats from filesystem approval_status.json files.

    Returns per-character approved/pending/rejected counts and totals.
    Optionally filtered by project_name.
    """
    if not BASE_PATH.exists():
        return {"characters": [], "totals": {"approved": 0, "pending": 0, "rejected": 0, "total": 0}}

    char_map = await get_char_project_map()
    characters = []
    totals = {"approved": 0, "pending": 0, "rejected": 0, "total": 0}

    for char_dir in sorted(BASE_PATH.iterdir()):
        if not char_dir.is_dir():
            continue
        images_path = char_dir / "images"
        if not images_path.exists():
            continue

        slug = char_dir.name
        if slug == "_unclassified":
            db_info = {"name": "Unclassified", "project_name": ""}
            # For project filter, skip _unclassified unless no filter
            if project_name:
                continue
        else:
            db_info = char_map.get(slug)
            if not db_info:
                continue
            if project_name and db_info.get("project_name") != project_name:
                continue

        approval_file = char_dir / "approval_status.json"
        approval_status = {}
        if approval_file.exists():
            try:
                with open(approval_file) as f:
                    approval_status = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        image_files = list(images_path.glob("*.png"))
        approved = 0
        pending = 0
        rejected = 0
        for img in image_files:
            status = approval_status.get(img.name, "pending")
            if status == "approved":
                approved += 1
            elif status == "rejected":
                rejected += 1
            else:
                pending += 1

        total = approved + pending + rejected
        if total == 0:
            continue

        characters.append({
            "slug": slug,
            "name": db_info.get("name", slug),
            "project_name": db_info.get("project_name", ""),
            "approved": approved,
            "pending": pending,
            "rejected": rejected,
            "total": total,
            "approval_rate": round(approved / total, 3) if total else 0,
        })

        totals["approved"] += approved
        totals["pending"] += pending
        totals["rejected"] += rejected
        totals["total"] += total

    return {"characters": characters, "totals": totals}


# ===================================================================
# Vision identify (open-ended character recognition)
# ===================================================================

@router.get("/identify/{character_slug}/{image_name}")
async def identify_character(character_slug: str, image_name: str):
    """Ask vision model to identify the character in an image (open-ended)."""
    image_path = BASE_PATH / character_slug / "images" / image_name
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    img_b64 = base64.b64encode(image_path.read_bytes()).decode()

    prompt = (
        "Describe the primary character in this frame — species, appearance, colors, "
        "clothing, accessories. If you recognize them from any franchise, say who they are.\n\n"
        'Reply with JSON: {"description": "...", "suggested_name": "..."}'
    )

    payload = json.dumps({
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": prompt, "images": [img_b64]}],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 300},
    }).encode()

    try:
        req = _ur.Request(
            f"{OLLAMA_URL}/api/chat", data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = json.loads(_ur.urlopen(req, timeout=30).read())
        raw = resp.get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.error(f"Vision identify failed for {character_slug}/{image_name}: {e}")
        raise HTTPException(status_code=502, detail=f"Vision model error: {e}")

    # Try to extract JSON from response
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(raw[start:end + 1])
            return {
                "description": parsed.get("description", raw),
                "suggested_name": parsed.get("suggested_name", ""),
            }
        except json.JSONDecodeError:
            pass

    return {"description": raw, "suggested_name": ""}
