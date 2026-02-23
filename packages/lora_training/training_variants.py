"""Training variant generation — IP-Adapter variants, multi-checkpoint comparison, scene-driven generation."""

import json
import logging
import random
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from packages.core.config import BASE_PATH, COMFYUI_URL, COMFYUI_INPUT_DIR, normalize_sampler
from packages.core.comfyui import build_ipadapter_workflow
from packages.core.db import get_char_project_map, get_pool

logger = logging.getLogger(__name__)
variant_router = APIRouter()


# ===================================================================
# Variant generation — faithful IP-Adapter variants from approved images
# ===================================================================

class VariantRequest(BaseModel):
    count: int = 3
    weight: float = 0.95
    denoise: float = 0.30
    prompt_override: Optional[str] = None
    seed_offset: int = 1


@variant_router.post("/variant/{character_slug}/{image_name}")
async def generate_variant(character_slug: str, image_name: str, body: VariantRequest = VariantRequest()):
    """Generate faithful variants of an approved image using IP-Adapter + original params."""
    import urllib.request as _ur

    image_dir = BASE_PATH / character_slug / "images"
    image_path = image_dir / image_name
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {image_name}")

    meta_path = image_path.with_suffix(".meta.json")
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, IOError):
            pass

    char_map = await get_char_project_map()
    db_info = char_map.get(character_slug, {})

    prompt_text = body.prompt_override or meta.get("full_prompt") or db_info.get("design_prompt", "")
    negative_text = meta.get("negative_prompt") or "worst quality, low quality, blurry, watermark, deformed"
    checkpoint = meta.get("checkpoint_model") or db_info.get("checkpoint_model", "realcartoonPixar_v12.safetensors")
    steps = meta.get("steps") or db_info.get("steps") or 25
    cfg = meta.get("cfg_scale") or db_info.get("cfg_scale") or 7.0
    width = meta.get("width") or db_info.get("width") or 768
    height = meta.get("height") or db_info.get("height") or 768
    original_seed = meta.get("seed")

    sampler_name, scheduler = normalize_sampler(
        meta.get("sampler") or db_info.get("sampler"),
        meta.get("scheduler") or db_info.get("scheduler"),
    )

    comfyui_ref_name = f"variant_ref_{character_slug}.png"
    comfyui_ref_path = COMFYUI_INPUT_DIR / comfyui_ref_name
    COMFYUI_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(image_path, comfyui_ref_path)

    results = []
    for i in range(body.count):
        if original_seed is not None:
            variant_seed = int(original_seed) + body.seed_offset + i
        else:
            variant_seed = random.randint(1, 2**31)

        workflow = build_ipadapter_workflow(
            prompt_text=prompt_text,
            negative_text=negative_text,
            checkpoint=checkpoint,
            ref_image_name=comfyui_ref_name,
            seed=variant_seed,
            steps=steps,
            cfg=cfg,
            denoise=body.denoise,
            weight=body.weight,
            width=width,
            height=height,
            filename_prefix=f"variant_{character_slug}",
            sampler_name=sampler_name,
            scheduler=scheduler,
        )

        try:
            payload = json.dumps({"prompt": workflow}).encode()
            req = _ur.Request(
                f"{COMFYUI_URL}/prompt", data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = _ur.urlopen(req)
            prompt_id = json.loads(resp.read()).get("prompt_id", "")
            results.append({"prompt_id": prompt_id, "seed": variant_seed})
            logger.info(f"Variant queued: {character_slug}/{image_name} seed={variant_seed} prompt_id={prompt_id}")
        except Exception as e:
            logger.error(f"Variant queue failed: {e}")
            results.append({"error": str(e)})

    return {
        "message": f"Queued {body.count} variant(s) for {character_slug}/{image_name}",
        "reference_image": image_name,
        "variants": results,
    }


class RegenerateBody(BaseModel):
    prompt_override: Optional[str] = None
    custom_poses: Optional[list[str]] = None


@variant_router.post("/regenerate/{character_slug}")
async def regenerate_character(character_slug: str, count: int = 1,
                               seed: Optional[int] = None,
                               prompt_override: Optional[str] = None,
                               style_override: Optional[str] = None,
                               checkpoint_override: Optional[str] = None,
                               body: Optional[RegenerateBody] = None):
    """Manually trigger image regeneration for a character."""
    import asyncio
    from packages.core.generation import generate_batch

    dataset_path = BASE_PATH / character_slug
    if not dataset_path.exists():
        (dataset_path / "images").mkdir(parents=True, exist_ok=True)

    effective_prompt_override = (body.prompt_override if body else None) or prompt_override
    effective_custom_poses = (body.custom_poses if body else None)

    asyncio.create_task(
        generate_batch(
            character_slug=character_slug,
            count=count,
            seed=seed,
            prompt_override=effective_prompt_override,
            style_override=style_override,
            checkpoint_override=checkpoint_override,
            custom_poses=effective_custom_poses,
        )
    )
    msg = f"Regeneration started for {character_slug} ({count} images)"
    if seed is not None:
        msg += f" with seed={seed}"
    if style_override:
        msg += f" with style={style_override}"
    if checkpoint_override:
        msg += f" with checkpoint={checkpoint_override}"
    logger.info(msg)
    return {"message": msg}


class CompareRequest(BaseModel):
    checkpoints: list[str]
    characters: list[str] | None = None
    project_name: str | None = None
    count_per_checkpoint: int = 5

_compare_task: dict | None = None


@variant_router.post("/regenerate-compare")
async def regenerate_compare(req: CompareRequest):
    """Serialized multi-checkpoint comparison."""
    import asyncio
    from packages.core.generation import generate_batch
    from packages.core.db import log_model_change

    global _compare_task

    if not req.checkpoints:
        raise HTTPException(400, "checkpoints list is required")

    if req.characters:
        char_slugs = req.characters
    elif req.project_name:
        char_map = await get_char_project_map()
        char_slugs = [
            slug for slug, info in char_map.items()
            if info.get("project_name") == req.project_name
        ]
        if not char_slugs:
            raise HTTPException(404, f"No characters found for project '{req.project_name}'")
    else:
        raise HTTPException(400, "Provide characters list or project_name")

    total_jobs = len(req.checkpoints) * len(char_slugs)
    total_images = total_jobs * req.count_per_checkpoint

    work = []
    for ckpt in req.checkpoints:
        for slug in char_slugs:
            work.append((ckpt, slug))

    _compare_task = {
        "status": "running",
        "total_combos": total_jobs,
        "completed_combos": 0,
        "total_images": total_images,
        "completed_images": 0,
        "failed_images": 0,
        "current_checkpoint": None,
        "current_character": None,
        "checkpoints": req.checkpoints,
        "characters": char_slugs,
        "count_per_checkpoint": req.count_per_checkpoint,
        "started_at": datetime.utcnow().isoformat(),
    }

    async def _run_compare():
        global _compare_task
        for ckpt in req.checkpoints:
            await log_model_change(
                action="compare_start",
                checkpoint_model=ckpt,
                project_name=req.project_name,
                reason=f"Multi-checkpoint comparison: {len(char_slugs)} characters x {req.count_per_checkpoint} images",
                metadata={"characters": char_slugs, "count_per_checkpoint": req.count_per_checkpoint},
            )
        for ckpt, slug in work:
            _compare_task["current_checkpoint"] = ckpt
            _compare_task["current_character"] = slug

            dataset_path = BASE_PATH / slug
            if not dataset_path.exists():
                (dataset_path / "images").mkdir(parents=True, exist_ok=True)

            try:
                results = await generate_batch(
                    character_slug=slug,
                    count=req.count_per_checkpoint,
                    checkpoint_override=ckpt,
                )
                ok = sum(1 for r in results if r.get("status") == "completed")
                fail = sum(1 for r in results if r.get("status") != "completed")
                _compare_task["completed_images"] += ok
                _compare_task["failed_images"] += fail
            except Exception as e:
                logger.error(f"regenerate-compare: {slug} x {ckpt} failed: {e}")
                _compare_task["failed_images"] += req.count_per_checkpoint

            _compare_task["completed_combos"] += 1
            logger.info(
                f"regenerate-compare: [{_compare_task['completed_combos']}/{total_jobs}] "
                f"{slug} x {ckpt} done"
            )

        _compare_task["status"] = "completed"
        _compare_task["finished_at"] = datetime.utcnow().isoformat()
        logger.info(
            f"regenerate-compare: FINISHED -- {_compare_task['completed_images']} images, "
            f"{_compare_task['failed_images']} failures"
        )

    asyncio.create_task(_run_compare())

    return {
        "message": f"Comparison started: {len(req.checkpoints)} checkpoints x {len(char_slugs)} characters x {req.count_per_checkpoint} images = {total_images} total",
        "checkpoints": req.checkpoints,
        "characters": char_slugs,
        "total_images": total_images,
    }


@variant_router.get("/regenerate-compare/status")
async def compare_status():
    """Check progress of the active multi-checkpoint comparison."""
    if _compare_task is None:
        return {"status": "idle", "message": "No comparison running"}
    return _compare_task


class SceneTrainingRequest(BaseModel):
    project_name: str
    images_per_scene: int = 3
    characters: list[str] | None = None


@variant_router.post("/generate-for-scenes")
async def generate_training_for_scenes(req: SceneTrainingRequest):
    """Generate training images with prompts derived from scene descriptions."""
    import asyncio
    from packages.core.generation import generate_batch

    pool = await get_pool()
    async with pool.acquire() as conn:
        proj = await conn.fetchrow("SELECT id, name FROM projects WHERE name = $1", req.project_name)
        if not proj:
            raise HTTPException(404, f"Project {req.project_name!r} not found")

        scenes = await conn.fetch(
            "SELECT id, title, description, mood, location, time_of_day "
            "FROM scenes WHERE project_id = $1 ORDER BY created_at",
            proj["id"],
        )
        if not scenes:
            raise HTTPException(404, f"No scenes found for project {req.project_name!r}")

        chars = await conn.fetch(
            "SELECT c.name, REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') as slug, "
            "c.design_prompt "
            "FROM characters c WHERE c.project_id = $1",
            proj["id"],
        )

    char_by_name: dict[str, dict] = {}
    for c in chars:
        char_by_name[c["name"].lower()] = {"slug": c["slug"], "name": c["name"], "design_prompt": c["design_prompt"] or ""}

    char_poses: dict[str, list[str]] = {}

    for scene in scenes:
        desc = scene["description"] or ""
        title = scene["title"] or ""
        mood = scene["mood"] or ""
        location = scene["location"] or ""
        time_of_day = scene["time_of_day"] or ""

        scene_text = f"{title} {desc}".lower()
        matched_chars = []
        for name_lower, cinfo in char_by_name.items():
            first_name = name_lower.split()[0]
            if first_name in scene_text or name_lower in scene_text:
                matched_chars.append(cinfo)

        if not matched_chars:
            continue

        for cinfo in matched_chars:
            slug = cinfo["slug"]
            if req.characters and slug not in req.characters:
                continue

            scene_ctx_parts = []
            if location:
                scene_ctx_parts.append(location)
            if mood:
                scene_ctx_parts.append(f"{mood} mood")
            if time_of_day:
                scene_ctx_parts.append(time_of_day)
            scene_ctx = ", ".join(scene_ctx_parts)

            pose_hints = _extract_pose_hints(desc, cinfo["name"])

            for i in range(req.images_per_scene):
                hint = pose_hints[i % len(pose_hints)] if pose_hints else ""
                pose = ", ".join(filter(None, [hint, scene_ctx]))
                char_poses.setdefault(slug, []).append(pose)

    if not char_poses:
        raise HTTPException(400, "No characters matched any scene descriptions")

    total = sum(len(p) for p in char_poses.values())

    async def _run():
        for slug, poses in char_poses.items():
            try:
                await generate_batch(
                    character_slug=slug,
                    count=len(poses),
                    custom_poses=poses,
                )
            except Exception as e:
                logger.error(f"generate-for-scenes: {slug} failed: {e}")

    asyncio.create_task(_run())

    summary = {slug: len(poses) for slug, poses in char_poses.items()}
    logger.info(f"generate-for-scenes: queued {total} images for {len(char_poses)} characters")
    return {
        "message": f"Queued {total} scene-matched training images for {len(char_poses)} characters",
        "total_images": total,
        "per_character": summary,
        "scenes_analyzed": len(scenes),
    }


def _extract_pose_hints(description: str, char_name: str) -> list[str]:
    """Extract pose/action phrases from a scene description for a character."""
    if not description:
        return []

    clauses = re.split(r'[.!;]\s*', description)

    first_name = char_name.split()[0].lower()
    name_lower = char_name.lower()
    hints = []

    for clause in clauses:
        clause_lower = clause.lower().strip()
        if not clause_lower:
            continue
        if first_name in clause_lower or name_lower in clause_lower:
            cleaned = clause.strip()
            if cleaned and len(cleaned) > 10:
                hints.append(cleaned)

    if not hints:
        chunks = [c.strip() for c in description.split(",") if len(c.strip()) > 10]
        hints = chunks[:5] if chunks else [description[:200]]

    return hints
