"""Training sub-router — training jobs, regeneration, feedback, variant generation, and LoRA management."""

import json
import logging
import os
import random
import re
import shutil
import subprocess
import urllib.request as _ur
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from packages.core.config import BASE_PATH, COMFYUI_URL, COMFYUI_INPUT_DIR, _SCRIPT_DIR, _PROJECT_DIR, normalize_sampler
from packages.core.comfyui import build_ipadapter_workflow
from packages.core.db import get_char_project_map
from packages.core.gpu_router import ensure_gpu_ready
from packages.core.models import TrainingRequest
from .feedback import (
    load_training_jobs,
    save_training_jobs,
    reconcile_training_jobs,
)

logger = logging.getLogger(__name__)
training_router = APIRouter()


# ===================================================================
# Variant generation — faithful IP-Adapter variants from approved images
# ===================================================================

class VariantRequest(BaseModel):
    count: int = 3
    weight: float = 0.95
    denoise: float = 0.30
    prompt_override: Optional[str] = None
    seed_offset: int = 1


@training_router.post("/variant/{character_slug}/{image_name}")
async def generate_variant(character_slug: str, image_name: str, body: VariantRequest = VariantRequest()):
    """Generate faithful variants of an approved image using IP-Adapter + original params."""
    image_dir = BASE_PATH / character_slug / "images"
    image_path = image_dir / image_name
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {image_name}")

    # Read source metadata
    meta_path = image_path.with_suffix(".meta.json")
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, IOError):
            pass

    # Fall back to DB project settings for missing params
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

    # Normalize sampler names for ComfyUI
    sampler_name, scheduler = normalize_sampler(
        meta.get("sampler") or db_info.get("sampler"),
        meta.get("scheduler") or db_info.get("scheduler"),
    )

    # Copy source image to ComfyUI input dir (LoadImage only reads from there)
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


# ===================================================================
# Regeneration endpoint
# ===================================================================

@training_router.post("/regenerate/{character_slug}")
async def regenerate_character(character_slug: str, count: int = 1,
                               seed: Optional[int] = None,
                               prompt_override: Optional[str] = None,
                               style_override: Optional[str] = None):
    """Manually trigger image regeneration for a character."""
    import asyncio
    from packages.core.generation import generate_batch

    dataset_path = BASE_PATH / character_slug
    if not dataset_path.exists():
        (dataset_path / "images").mkdir(parents=True, exist_ok=True)

    # Launch as background task (non-blocking, same as old subprocess)
    asyncio.create_task(
        generate_batch(
            character_slug=character_slug,
            count=count,
            seed=seed,
            prompt_override=prompt_override,
            style_override=style_override,
        )
    )
    msg = f"Regeneration started for {character_slug} ({count} images)"
    if seed is not None:
        msg += f" with seed={seed}"
    if style_override:
        msg += f" with style={style_override}"
    logger.info(msg)
    return {"message": msg}


# ===================================================================
# Training endpoints
# ===================================================================

@training_router.get("/jobs")
async def get_training_jobs_endpoint():
    """Get all training jobs."""
    jobs = load_training_jobs()
    return {"training_jobs": jobs}


@training_router.post("/start")
async def start_training(training: TrainingRequest):
    """Start a LoRA training job for a character."""
    safe_name = re.sub(r'[^a-z0-9_-]', '', training.character_name.lower().replace(' ', '_'))
    dataset_path = BASE_PATH / safe_name
    approval_file = dataset_path / "approval_status.json"

    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail="Character not found")

    approved_count = 0
    if approval_file.exists():
        with open(approval_file) as f:
            statuses = json.load(f)
            approved_count = sum(1 for s in statuses.values() if s == "approved")

    MIN_TRAINING_IMAGES = 10
    if approved_count < MIN_TRAINING_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {MIN_TRAINING_IMAGES} approved images (have {approved_count})"
        )

    char_map = await get_char_project_map()
    db_info = char_map.get(safe_name, {})
    checkpoint_name = db_info.get("checkpoint_model")
    if not checkpoint_name:
        raise HTTPException(status_code=400, detail="No checkpoint model configured for this character's project")

    checkpoint_path = Path("/opt/ComfyUI/models/checkpoints") / checkpoint_name
    if not checkpoint_path.exists():
        raise HTTPException(status_code=400, detail=f"Checkpoint not found: {checkpoint_name}")

    gpu_ready, gpu_msg = ensure_gpu_ready("lora_training")
    if not gpu_ready:
        raise HTTPException(status_code=503, detail=f"GPU not available: {gpu_msg}")

    # Auto-detect architecture from model profile
    from packages.core.model_profiles import get_model_profile
    _profile = get_model_profile(checkpoint_name)
    is_sdxl = _profile["architecture"] == "sdxl"
    model_type = _profile["architecture"]

    # Set architecture-appropriate defaults
    if is_sdxl:
        resolution = training.resolution if training.resolution != 512 else 1024
        lora_rank = training.lora_rank or 64
        lora_suffix = "_xl_lora"
    else:
        resolution = training.resolution
        lora_rank = training.lora_rank or 32
        lora_suffix = "_lora"

    job_id = f"train_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_path = Path("/opt/ComfyUI/models/loras") / f"{safe_name}{lora_suffix}.safetensors"

    job = {
        "job_id": job_id,
        "character_name": training.character_name,
        "character_slug": safe_name,
        "status": "queued",
        "approved_images": approved_count,
        "epochs": training.epochs,
        "learning_rate": training.learning_rate,
        "resolution": resolution,
        "lora_rank": lora_rank,
        "model_type": model_type,
        "checkpoint": checkpoint_name,
        "output_path": str(output_path),
        "created_at": datetime.now().isoformat(),
    }

    jobs = load_training_jobs()
    for existing in jobs:
        if existing.get("status") == "running":
            pid = existing.get("pid")
            if pid:
                try:
                    os.kill(pid, 0)
                    raise HTTPException(
                        status_code=409,
                        detail=f"Training already in progress for {existing.get('character_name', 'unknown')} (job {existing['job_id']})"
                    )
                except (OSError, ProcessLookupError):
                    existing["status"] = "failed"
                    existing["error"] = "Process died without updating status (detected at training start)"
                    existing["failed_at"] = datetime.now().isoformat()
                    save_training_jobs(jobs)
                    jobs = load_training_jobs()
            else:
                existing["status"] = "failed"
                existing["error"] = "Process died without updating status (no PID recorded)"
                existing["failed_at"] = datetime.now().isoformat()
                save_training_jobs(jobs)
                jobs = load_training_jobs()

    jobs.append(job)
    save_training_jobs(jobs)

    train_script = _SCRIPT_DIR / "train_lora.py"
    log_dir = _PROJECT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{job_id}.log"

    cmd = [
        "/usr/bin/python3", str(train_script),
        f"--job-id={job_id}",
        f"--character-slug={safe_name}",
        f"--checkpoint={checkpoint_path}",
        f"--dataset-dir={dataset_path}",
        f"--output={output_path}",
        f"--epochs={training.epochs}",
        f"--learning-rate={training.learning_rate}",
        f"--resolution={resolution}",
        f"--lora-rank={lora_rank}",
        f"--model-type={model_type}",
    ]

    log_fh = open(log_file, "w")
    proc = subprocess.Popen(
        cmd,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        cwd=str(_SCRIPT_DIR),
    )
    log_fh.close()

    jobs = load_training_jobs()
    for j in jobs:
        if j["job_id"] == job_id:
            j["pid"] = proc.pid
            break
    save_training_jobs(jobs)

    logger.info(
        f"Training launched: {job_id} (pid={proc.pid}) for {training.character_name} "
        f"({approved_count} images, {model_type}, rank={lora_rank}, res={resolution})"
    )
    return {
        "message": "Training job started",
        "job_id": job_id,
        "approved_images": approved_count,
        "checkpoint": checkpoint_name,
        "model_type": model_type,
        "lora_rank": lora_rank,
        "resolution": resolution,
        "output": str(output_path),
        "log_file": str(log_file),
        "gpu": gpu_msg,
    }


@training_router.get("/jobs/{job_id}")
async def get_training_job(job_id: str):
    """Get status of a specific training job."""
    jobs = load_training_jobs()
    for job in jobs:
        if job["job_id"] == job_id:
            return job
    raise HTTPException(status_code=404, detail="Job not found")


@training_router.get("/training/jobs/{job_id}/log")
async def get_training_log(job_id: str, tail: int = 50):
    """Tail the log file for a training job."""
    log_file = _PROJECT_DIR / "logs" / f"{job_id}.log"
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    lines = log_file.read_text().splitlines()
    return {
        "job_id": job_id,
        "total_lines": len(lines),
        "lines": lines[-tail:],
    }


@training_router.post("/jobs/{job_id}/cancel")
async def cancel_training_job(job_id: str):
    """Cancel a running training job by sending SIGTERM then SIGKILL."""
    import signal as sig
    import time

    jobs = load_training_jobs()
    for job in jobs:
        if job["job_id"] == job_id:
            if job["status"] not in ("running", "queued"):
                raise HTTPException(status_code=400, detail=f"Job is not running (status: {job['status']})")
            pid = job.get("pid")
            killed = False
            if pid:
                try:
                    os.kill(pid, sig.SIGTERM)
                    for _ in range(10):
                        time.sleep(0.5)
                        try:
                            os.kill(pid, 0)
                        except (OSError, ProcessLookupError):
                            killed = True
                            break
                    if not killed:
                        os.kill(pid, sig.SIGKILL)
                        killed = True
                except (OSError, ProcessLookupError):
                    killed = True
            job["status"] = "failed"
            job["error"] = "Cancelled by user"
            job["failed_at"] = datetime.now().isoformat()
            save_training_jobs(jobs)
            return {"message": f"Job {job_id} cancelled", "pid": pid, "killed": killed}
    raise HTTPException(status_code=404, detail="Job not found")


@training_router.delete("/jobs/{job_id}")
async def delete_training_job(job_id: str):
    """Remove a finished job from the jobs list."""
    jobs = load_training_jobs()
    for i, job in enumerate(jobs):
        if job["job_id"] == job_id:
            if job["status"] in ("running", "queued"):
                raise HTTPException(status_code=400, detail="Cannot delete a running/queued job -- cancel it first")
            jobs.pop(i)
            save_training_jobs(jobs)
            log_file = _PROJECT_DIR / "logs" / f"{job_id}.log"
            if log_file.exists():
                log_file.unlink()
            return {"message": f"Job {job_id} deleted"}
    raise HTTPException(status_code=404, detail="Job not found")


@training_router.post("/jobs/clear-finished")
async def clear_finished_jobs(days: int = 7):
    """Remove all completed/failed/invalidated jobs older than N days."""
    jobs = load_training_jobs()
    cutoff = datetime.now().timestamp() - (days * 86400)
    kept = []
    removed = 0
    for job in jobs:
        if job["status"] in ("completed", "failed", "invalidated"):
            created = datetime.fromisoformat(job["created_at"]).timestamp()
            if created < cutoff:
                log_file = _PROJECT_DIR / "logs" / f"{job['job_id']}.log"
                if log_file.exists():
                    log_file.unlink()
                removed += 1
                continue
        kept.append(job)
    save_training_jobs(kept)
    return {"message": f"Removed {removed} finished jobs older than {days} days", "removed": removed, "remaining": len(kept)}


@training_router.post("/jobs/{job_id}/retry")
async def retry_training_job(job_id: str):
    """Re-launch training with the same parameters as a failed/invalidated job."""
    jobs = load_training_jobs()
    for job in jobs:
        if job["job_id"] == job_id:
            if job["status"] not in ("failed", "invalidated"):
                raise HTTPException(status_code=400, detail=f"Can only retry failed/invalidated jobs (status: {job['status']})")
            training = TrainingRequest(
                character_name=job["character_name"],
                epochs=job.get("epochs", 20),
                learning_rate=job.get("learning_rate", 1e-4),
                resolution=job.get("resolution", 512),
            )
            return await start_training(training)
    raise HTTPException(status_code=404, detail="Job not found")


@training_router.post("/jobs/{job_id}/invalidate")
async def invalidate_training_job(job_id: str, delete_lora: bool = False):
    """Mark a completed job as invalidated (trained on bad data). Optionally delete the LoRA file."""
    jobs = load_training_jobs()
    for job in jobs:
        if job["job_id"] == job_id:
            if job["status"] != "completed":
                raise HTTPException(status_code=400, detail=f"Can only invalidate completed jobs (status: {job['status']})")
            job["status"] = "invalidated"
            job["error"] = "Invalidated by user"
            lora_deleted = False
            if delete_lora and job.get("output_path"):
                lora_path = Path(job["output_path"])
                if lora_path.exists():
                    lora_path.unlink()
                    lora_deleted = True
                    job["error"] = "Invalidated by user -- LoRA file deleted"
            save_training_jobs(jobs)
            return {"message": f"Job {job_id} invalidated", "lora_deleted": lora_deleted}
    raise HTTPException(status_code=404, detail="Job not found")


@training_router.post("/reconcile")
async def reconcile_training_jobs_endpoint():
    """Run stale job detection on demand."""
    count = reconcile_training_jobs()
    return {"message": f"Reconciled {count} stale job(s)", "reconciled": count}


@training_router.get("/loras")
async def list_trained_loras():
    """List all trained LoRA files on disk with metadata."""
    lora_dir = Path("/opt/ComfyUI/models/loras")
    loras = []
    jobs = load_training_jobs()
    job_by_path = {}
    for job in jobs:
        if job.get("output_path"):
            job_by_path[job["output_path"]] = job

    if lora_dir.exists():
        # Match both SD1.5 (*_lora.safetensors) and SDXL (*_xl_lora.safetensors)
        for f in sorted(lora_dir.glob("*_lora.safetensors")):
            stat = f.stat()
            is_xl = f.stem.endswith("_xl_lora")
            slug = f.stem.replace("_xl_lora", "") if is_xl else f.stem.replace("_lora", "")
            architecture = "sdxl" if is_xl else "sd15"
            related_job = job_by_path.get(str(f))
            loras.append({
                "filename": f.name,
                "slug": slug,
                "architecture": architecture,
                "path": str(f),
                "size_mb": round(stat.st_size / (1024 * 1024), 1),
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "job_id": related_job["job_id"] if related_job else None,
                "job_status": related_job["status"] if related_job else None,
            })
    return {"loras": loras}


@training_router.delete("/loras/{slug}")
async def delete_trained_lora(slug: str):
    """Delete a LoRA .safetensors file from disk."""
    lora_path = Path(f"/opt/ComfyUI/models/loras/{slug}_lora.safetensors")
    if not lora_path.exists():
        raise HTTPException(status_code=404, detail=f"LoRA file not found: {lora_path.name}")
    size_mb = round(lora_path.stat().st_size / (1024 * 1024), 1)
    lora_path.unlink()
    return {"message": f"Deleted {lora_path.name} ({size_mb} MB)", "filename": lora_path.name}


# ===================================================================
# Feedback endpoints
# ===================================================================

@training_router.get("/feedback/{character_slug}")
async def get_feedback(character_slug: str):
    """Get rejection feedback analysis for a character."""
    feedback_json = BASE_PATH / character_slug / "feedback.json"
    if not feedback_json.exists():
        return {"character": character_slug, "rejection_count": 0, "rejections": [], "negative_additions": []}
    try:
        data = json.loads(feedback_json.read_text())
        data["character"] = character_slug
        return data
    except (json.JSONDecodeError, IOError):
        return {"character": character_slug, "rejection_count": 0, "rejections": [], "negative_additions": []}


@training_router.delete("/feedback/{character_slug}")
async def clear_feedback(character_slug: str):
    """Clear rejection feedback for a character (reset the feedback loop)."""
    feedback_json = BASE_PATH / character_slug / "feedback.json"
    if feedback_json.exists():
        feedback_json.unlink()
    return {"message": f"Feedback cleared for {character_slug}"}
