#!/usr/bin/env python3
"""
Redis Job Queue Endpoints for Anime Production
Provides non-blocking job management via Redis
"""

import json
import sys
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException

sys.path.insert(0, "/opt/tower-anime-production")
from services.fixes.job_queue import AnimeJobQueue

router = APIRouter(prefix="/api/anime/redis", tags=["redis-jobs"])

# Initialize job queue
job_queue = AnimeJobQueue()


@router.post("/jobs")


async def create_redis_job(project_id: str, job_type: str, params: dict = {}):
    """Create a new job in Redis queue"""
    try:
        job_id = job_queue.add_job(project_id, job_type, params)
        return {"job_id": job_id, "status": "queued", "message": "Job added to Redis queue"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}")


async def get_redis_job_status(job_id: str):
    """Get job status from Redis"""
    try:
        job_data = job_queue.get_job_status(job_id)

        if not job_data:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        # Calculate ETA
        progress = int(job_data.get("progress", 0))
        eta = None

        if progress > 0 and job_data.get("created_at"):
            created_at = datetime.fromisoformat(job_data["created_at"])
            elapsed = (datetime.utcnow() - created_at).total_seconds()
            if progress < 100:
                estimated_total = elapsed / (progress / 100)
                eta = datetime.utcnow() + timedelta(seconds=(estimated_total - elapsed))

        response = {
            "job_id": job_id,
            "project_id": job_data.get("project_id"),
            "status": job_data.get("status", "unknown"),
            "progress": progress,
            "type": job_data.get("type"),
            "created_at": job_data.get("created_at"),
            "updated_at": job_data.get("updated_at"),
            "eta": eta.isoformat() if eta else None,
        }

        if job_data.get("status") == "completed":
            response["completed_at"] = job_data.get("completed_at")
            if job_data.get("result"):
                response["result"] = json.loads(job_data.get("result", "{}"))

        if job_data.get("status") == "failed":
            response["error"] = job_data.get("error")
            response["failed_at"] = job_data.get("failed_at")

        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/progress")


async def update_redis_job_progress(job_id: str, progress: int, status: str = None):
    """Update job progress"""
    try:
        job_queue.update_job_progress(job_id, progress, status)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/status")


async def get_queue_status():
    """Get Redis queue statistics"""
    try:
        return {
            "queue_length": job_queue.get_queue_length(),
            "processing_count": job_queue.get_processing_count(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
