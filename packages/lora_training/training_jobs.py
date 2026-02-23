"""Training job management -- start, stop, status, progress, LoRA listing, gap analysis, feedback."""

import json
import logging
import math
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from packages.core.config import BASE_PATH, _SCRIPT_DIR, _PROJECT_DIR
from packages.core.db import get_char_project_map, get_pool
from packages.core.generation import POSE_VARIATIONS
from packages.core.gpu_router import ensure_gpu_ready
from packages.core.models import TrainingRequest
from .feedback import (
    load_training_jobs,
    save_training_jobs,
    reconcile_training_jobs,
)

logger = logging.getLogger(__name__)
jobs_router = APIRouter()
@jobs_router.get("/jobs")
async def get_training_jobs_endpoint():
    """Get all training jobs."""
    jobs = load_training_jobs()
    return {"training_jobs": jobs}


@jobs_router.post("/start")
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

    MIN_TRAINING_IMAGES = 100
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

    # Auto-detect architecture and prediction type from model profile
    from packages.core.model_profiles import get_model_profile
    _profile = get_model_profile(checkpoint_name)
    is_sdxl = _profile["architecture"] == "sdxl"
    model_type = _profile["architecture"]
    prediction_type = _profile.get("prediction_type", "epsilon")

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
        "prediction_type": prediction_type,
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
        f"--prediction-type={prediction_type}",
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
        "prediction_type": prediction_type,
        "lora_rank": lora_rank,
        "resolution": resolution,
        "output": str(output_path),
        "log_file": str(log_file),
        "gpu": gpu_msg,
    }


@jobs_router.get("/jobs/{job_id}")
async def get_training_job(job_id: str):
    """Get status of a specific training job."""
    jobs = load_training_jobs()
    for job in jobs:
        if job["job_id"] == job_id:
            return job
    raise HTTPException(status_code=404, detail="Job not found")


@jobs_router.get("/jobs/{job_id}/log")
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


@jobs_router.post("/jobs/{job_id}/cancel")
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


@jobs_router.delete("/jobs/{job_id}")
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


@jobs_router.post("/jobs/clear-finished")
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


@jobs_router.post("/jobs/{job_id}/retry")
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


@jobs_router.post("/jobs/{job_id}/invalidate")
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


@jobs_router.post("/reconcile")
async def reconcile_training_jobs_endpoint():
    """Run stale job detection on demand."""
    count = reconcile_training_jobs()
    return {"message": f"Reconciled {count} stale job(s)", "reconciled": count}


@jobs_router.get("/loras")
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


@jobs_router.delete("/loras/{slug}")
async def delete_trained_lora(slug: str):
    """Delete a LoRA .safetensors file from disk."""
    lora_path = Path(f"/opt/ComfyUI/models/loras/{slug}_lora.safetensors")
    if not lora_path.exists():
        raise HTTPException(status_code=404, detail=f"LoRA file not found: {lora_path.name}")
    size_mb = round(lora_path.stat().st_size / (1024 * 1024), 1)
    lora_path.unlink()
    return {"message": f"Deleted {lora_path.name} ({size_mb} MB)", "filename": lora_path.name}


# ===================================================================
# Gap Analysis — production readiness assessment
# ===================================================================

@jobs_router.get("/gap-analysis")
async def gap_analysis(project_name: str | None = None):
    """Analyze training data coverage gaps for production readiness.

    Returns per-character pose distributions, LoRA status, scene appearances,
    and prioritized action items to reach production readiness.
    """
    char_map = await get_char_project_map()

    # Filter to project if specified
    if project_name:
        char_map = {
            slug: info for slug, info in char_map.items()
            if info.get("project_name") == project_name
        }
    if not char_map:
        raise HTTPException(404, f"No characters found{f' for project {project_name!r}' if project_name else ''}")

    # Resolve project_id for scene queries
    project_id = None
    if project_name:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM projects WHERE name = $1", project_name)
            if row:
                project_id = row["id"]

    # Build LoRA lookup from disk
    lora_dir = Path("/opt/ComfyUI/models/loras")
    lora_slugs: set[str] = set()
    if lora_dir.exists():
        for f in lora_dir.glob("*_lora.safetensors"):
            is_xl = f.stem.endswith("_xl_lora")
            slug = f.stem.replace("_xl_lora", "") if is_xl else f.stem.replace("_lora", "")
            lora_slugs.add(slug)

    # Per-character analysis
    characters_out = []
    total_approved = 0
    total_with_lora = 0
    all_pose_coverages = []

    for slug, info in sorted(char_map.items()):
        dataset_path = BASE_PATH / slug
        images_dir = dataset_path / "images"
        approval_file = dataset_path / "approval_status.json"

        # Load approval statuses
        approval_status = {}
        if approval_file.exists():
            try:
                approval_status = json.loads(approval_file.read_text())
            except (json.JSONDecodeError, IOError):
                pass

        approved_images = [name for name, st in approval_status.items() if st == "approved"]
        approved_count = len(approved_images)
        total_approved += approved_count

        # Pose distribution from .meta.json files
        pose_counts: dict[str, int] = {p: 0 for p in POSE_VARIATIONS}
        no_pose_count = 0
        quality_scores = []

        for img_name in approved_images:
            meta_path = images_dir / f"{Path(img_name).stem}.meta.json"
            if not meta_path.exists():
                no_pose_count += 1
                continue
            try:
                meta = json.loads(meta_path.read_text())
            except (json.JSONDecodeError, IOError):
                no_pose_count += 1
                continue

            pose = meta.get("pose", "")
            if pose and pose in pose_counts:
                pose_counts[pose] += 1
            elif pose:
                # Fuzzy match: check if pose text is a substring of any known pose
                matched = False
                for known_pose in POSE_VARIATIONS:
                    if pose.lower() in known_pose.lower() or known_pose.lower() in pose.lower():
                        pose_counts[known_pose] += 1
                        matched = True
                        break
                if not matched:
                    no_pose_count += 1
            else:
                no_pose_count += 1

            qs = meta.get("quality_score")
            if qs is not None:
                quality_scores.append(qs)

        # Pose coverage metrics
        poses_with_images = [p for p, c in pose_counts.items() if c > 0]
        pose_values = [c for c in pose_counts.values() if c > 0]
        pose_coverage = len(poses_with_images)

        # Coefficient of variation (std/mean) — higher = more imbalanced
        pose_skew = 0.0
        if pose_values and len(pose_values) > 1:
            mean_val = sum(pose_values) / len(pose_values)
            if mean_val > 0:
                variance = sum((v - mean_val) ** 2 for v in pose_values) / len(pose_values)
                pose_skew = round(math.sqrt(variance) / mean_val, 3)

        has_lora = slug in lora_slugs
        if has_lora:
            total_with_lora += 1

        avg_quality = round(sum(quality_scores) / len(quality_scores), 3) if quality_scores else None
        all_pose_coverages.append(pose_coverage)

        characters_out.append({
            "slug": slug,
            "name": info.get("name", slug),
            "approved_count": approved_count,
            "has_lora": has_lora,
            "pose_coverage": pose_coverage,
            "pose_total": len(POSE_VARIATIONS),
            "pose_distribution": pose_counts,
            "pose_skew": pose_skew,
            "images_without_pose": no_pose_count,
            "avg_quality": avg_quality,
            "poses_missing": [p for p in POSE_VARIATIONS if pose_counts[p] == 0],
        })

    # Scene analysis
    scenes_out = []
    scenes_ready = 0
    if project_id is not None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            scene_rows = await conn.fetch(
                "SELECT id, title, description, mood, target_duration_seconds FROM scenes WHERE project_id = $1 ORDER BY created_at",
                project_id,
            )
            if scene_rows:
                scene_ids = [r["id"] for r in scene_rows]
                shot_rows = await conn.fetch(
                    "SELECT scene_id, status FROM shots WHERE scene_id = ANY($1::uuid[])",
                    scene_ids,
                )

                shots_by_scene: dict[str, list] = {}
                for sr in shot_rows:
                    sid = str(sr["scene_id"])
                    shots_by_scene.setdefault(sid, []).append(sr["status"])

                for scene in scene_rows:
                    sid = str(scene["id"])
                    desc = (scene["description"] or "").lower()
                    title = (scene["title"] or "").lower()
                    search_text = f"{title} {desc}"

                    # Match characters by name or slug
                    scene_chars = []
                    for slug, info in char_map.items():
                        char_name = info.get("name", "").lower()
                        if char_name and (char_name in search_text or slug in search_text):
                            scene_chars.append({
                                "slug": slug,
                                "name": info.get("name", slug),
                                "has_lora": slug in lora_slugs,
                            })

                    target_dur = scene.get("target_duration_seconds") or 6
                    shots_needed = math.ceil(target_dur / 3)
                    scene_shots = shots_by_scene.get(sid, [])
                    shots_defined = len(scene_shots)
                    shots_completed = sum(1 for s in scene_shots if s == "completed")

                    all_chars_have_lora = all(c["has_lora"] for c in scene_chars) if scene_chars else False
                    is_ready = all_chars_have_lora and shots_defined >= shots_needed

                    if is_ready:
                        scenes_ready += 1

                    scenes_out.append({
                        "id": sid,
                        "title": scene["title"],
                        "mood": scene["mood"],
                        "target_duration_seconds": target_dur,
                        "characters": scene_chars,
                        "shots_defined": shots_defined,
                        "shots_completed": shots_completed,
                        "shots_needed": shots_needed,
                        "production_ready": is_ready,
                    })

    # Prioritized action items
    total_chars = len(characters_out)
    actions = []

    # 1. Train missing LoRAs (highest priority)
    for c in characters_out:
        if not c["has_lora"] and c["approved_count"] >= 10:
            actions.append({
                "type": "train_lora",
                "priority": 1,
                "target": c["name"],
                "slug": c["slug"],
                "reason": f"{c['approved_count']} approved images, no LoRA trained",
            })

    # 2. Rebalance poses (medium priority)
    for c in characters_out:
        if c["pose_skew"] > 1.0 and c["approved_count"] >= 10:
            top_missing = c["poses_missing"][:3]
            actions.append({
                "type": "rebalance_pose",
                "priority": 2,
                "target": c["name"],
                "slug": c["slug"],
                "reason": f"Pose skew {c['pose_skew']:.2f}, missing: {', '.join(p.split(',')[0] for p in top_missing)}",
            })

    # 3. Add shots to scenes (lower priority)
    for s in scenes_out:
        if s["shots_defined"] < s["shots_needed"]:
            actions.append({
                "type": "add_shots",
                "priority": 3,
                "target": s["title"],
                "reason": f"{s['shots_defined']}/{s['shots_needed']} shots defined",
            })

    actions.sort(key=lambda a: a["priority"])

    avg_pose_coverage = round(sum(all_pose_coverages) / len(all_pose_coverages), 1) if all_pose_coverages else 0
    readiness_pct = 0
    if total_chars > 0:
        lora_score = total_with_lora / total_chars * 50  # 50% weight
        pose_score = (avg_pose_coverage / len(POSE_VARIATIONS)) * 30  # 30% weight
        scene_score = (scenes_ready / len(scenes_out) * 20) if scenes_out else 0  # 20% weight
        readiness_pct = round(lora_score + pose_score + scene_score, 1)

    return {
        "project_name": project_name,
        "characters": characters_out,
        "scenes": scenes_out,
        "summary": {
            "total_characters": total_chars,
            "with_lora": total_with_lora,
            "without_lora": total_chars - total_with_lora,
            "avg_pose_coverage": avg_pose_coverage,
            "pose_total": len(POSE_VARIATIONS),
            "scenes_total": len(scenes_out),
            "scenes_ready": scenes_ready,
            "total_approved_images": total_approved,
            "production_readiness_pct": readiness_pct,
        },
        "actions": actions[:10],
        "pose_labels": POSE_VARIATIONS,
    }


# ===================================================================
# Scene-driven training image generation
# ===================================================================


class SceneTrainingRequest(BaseModel):
    project_name: str
    images_per_scene: int = 3
    characters: list[str] | None = None  # filter to specific slugs; None = all


@jobs_router.post("/generate-for-scenes")
async def generate_training_for_scenes(req: SceneTrainingRequest):
    """Generate training images with prompts derived from scene descriptions.

    For each scene, extracts character requirements from the description,
    builds a scene-matched prompt override, and calls generate_batch() so
    the resulting images train the LoRA on poses/situations the character
    actually needs for production.

    Non-blocking — kicks off generation in background and returns immediately.
    """
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

    # Build per-character scene pose list
    # These are passed as custom_poses so translate_prompt() still runs
    # (preserves character identity, appearance_data, model-aware tags)
    char_poses: dict[str, list[str]] = {}  # slug -> [pose_string, ...]

    for scene in scenes:
        desc = scene["description"] or ""
        title = scene["title"] or ""
        mood = scene["mood"] or ""
        location = scene["location"] or ""
        time_of_day = scene["time_of_day"] or ""

        # Find which characters this scene mentions
        scene_text = f"{title} {desc}".lower()
        matched_chars = []
        for name_lower, cinfo in char_by_name.items():
            # Match on first name or full name
            first_name = name_lower.split()[0]
            if first_name in scene_text or name_lower in scene_text:
                matched_chars.append(cinfo)

        if not matched_chars:
            continue

        for cinfo in matched_chars:
            slug = cinfo["slug"]
            if req.characters and slug not in req.characters:
                continue

            # Build scene context as pose string
            scene_ctx_parts = []
            if location:
                scene_ctx_parts.append(location)
            if mood:
                scene_ctx_parts.append(f"{mood} mood")
            if time_of_day:
                scene_ctx_parts.append(time_of_day)
            scene_ctx = ", ".join(scene_ctx_parts)

            # Extract pose hints from description — sentences mentioning this character
            pose_hints = _extract_pose_hints(desc, cinfo["name"])

            # Build N pose strings per scene for this character
            for i in range(req.images_per_scene):
                hint = pose_hints[i % len(pose_hints)] if pose_hints else ""
                pose = ", ".join(filter(None, [hint, scene_ctx]))
                char_poses.setdefault(slug, []).append(pose)

    if not char_poses:
        raise HTTPException(400, "No characters matched any scene descriptions")

    # Kick off generation in background
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
    """Extract pose/action phrases from a scene description for a character.

    Splits on sentence boundaries and looks for action verbs and pose descriptors
    near the character's name.
    """
    if not description:
        return []

    # Split into clauses (sentences, comma-separated phrases)
    import re
    clauses = re.split(r'[.!;]\s*', description)

    first_name = char_name.split()[0].lower()
    name_lower = char_name.lower()
    hints = []

    for clause in clauses:
        clause_lower = clause.lower().strip()
        if not clause_lower:
            continue
        # If clause mentions this character, extract it as a pose hint
        if first_name in clause_lower or name_lower in clause_lower:
            # Clean: remove the character name itself to get the action/pose
            cleaned = clause.strip()
            if cleaned and len(cleaned) > 10:
                hints.append(cleaned)

    # If no name-specific clauses, use the whole description chunked
    if not hints:
        # Use comma-separated chunks as generic pose hints
        chunks = [c.strip() for c in description.split(",") if len(c.strip()) > 10]
        hints = chunks[:5] if chunks else [description[:200]]

    return hints


# ===================================================================
# Feedback endpoints
# ===================================================================

@jobs_router.get("/feedback/{character_slug}")
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


@jobs_router.delete("/feedback/{character_slug}")
async def clear_feedback(character_slug: str):
    """Clear rejection feedback for a character (reset the feedback loop)."""
    feedback_json = BASE_PATH / character_slug / "feedback.json"
    if feedback_json.exists():
        feedback_json.unlink()
    return {"message": f"Feedback cleared for {character_slug}"}
