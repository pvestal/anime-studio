#!/usr/bin/env python3
"""
Video Generation API using Database SSOT
Implements Echo Brain's architectural recommendations
"""

import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import asyncio
import uuid
import time
from pathlib import Path

# Simplified without service dependency for now
# from ..services.video_generation import VideoGenerationService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/video", tags=["video"])

class VideoGenerationRequest(BaseModel):
    prompt: str
    workflow: Optional[str] = None  # Accept 'workflow' from request
    workflow_name: Optional[str] = None  # Also accept 'workflow_name' for compatibility
    character_name: Optional[str] = None
    style: str = "anime"
    width: int = 512
    height: int = 288
    steps: Optional[int] = 20
    negative_prompt: Optional[str] = "worst quality, low quality, blurry"

    def get_workflow(self) -> str:
        """Get the actual workflow name to use"""
        # Priority: workflow > workflow_name > default
        return self.workflow or self.workflow_name or "anime_30sec_rife_workflow"

class VideoGenerationResponse(BaseModel):
    job_id: str
    status: str
    message: str
    estimated_duration: int

class VideoStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: float
    video_url: Optional[str] = None
    error_message: Optional[str] = None

# In-memory job tracking (in production, use Redis or database)
active_jobs = {}

@router.post("/generate", response_model=VideoGenerationResponse)
async def generate_video(request: VideoGenerationRequest, background_tasks: BackgroundTasks):
    """
    Generate animated video using database SSOT workflows
    Following Echo Brain's architectural recommendations
    """

    job_id = str(uuid.uuid4())

    try:
        # Use direct database workflow approach
        # service = VideoGenerationService()

        # Validate workflow exists in database
        # This will be handled by the service layer

        # Get the actual workflow to use
        workflow_to_use = request.get_workflow()

        # Track job
        active_jobs[job_id] = {
            "status": "queued",
            "progress": 0.0,
            "created_at": time.time(),
            "prompt": request.prompt,
            "workflow": workflow_to_use
        }

        # Start background generation
        background_tasks.add_task(
            execute_video_generation,
            job_id,
            request
        )

        logger.info(f"🎬 Video generation job {job_id} queued for workflow {workflow_to_use}")

        return VideoGenerationResponse(
            job_id=job_id,
            status="queued",
            message=f"Video generation started using {workflow_to_use}",
            estimated_duration=30
        )

    except Exception as e:
        logger.error(f"❌ Failed to queue video generation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{job_id}", response_model=VideoStatusResponse)
async def get_video_status(job_id: str):
    """Get video generation job status"""

    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = active_jobs[job_id]

    return VideoStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress=job["progress"],
        video_url=job.get("video_url"),
        error_message=job.get("error_message")
    )

@router.get("/workflows")
async def list_workflows():
    """List available video generation workflows from database SSOT"""

    try:
        # Query database directly for workflows
        import psycopg2

        conn = psycopg2.connect(
            host='localhost',
            database='tower_consolidated',
            user='patrick',
            password='RP78eIrW7cI2jYvL5akt1yurE'
        )

        cur = conn.cursor()
        cur.execute("SELECT name, description, frame_count, fps FROM video_workflow_templates")
        rows = cur.fetchall()
        conn.close()

        workflows = []
        for row in rows:
            workflows.append({
                "name": row[0],
                "description": row[1],
                "frame_count": row[2],
                "fps": row[3],
                "estimated_duration": 30 if row[2] <= 20 else 180
            })

        return {"workflows": workflows}

    except Exception as e:
        logger.error(f"❌ Failed to list workflows: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def execute_video_generation(job_id: str, request: VideoGenerationRequest):
    """Execute video generation in background"""

    try:
        # Update job status
        active_jobs[job_id]["status"] = "processing"
        active_jobs[job_id]["progress"] = 0.1

        logger.info(f"🎬 Starting video generation for job {job_id}")

        # Use the database workflow directly
        import sys
        sys.path.append('/opt/anime-studio')
        from use_database_workflow import use_database_workflow

        # Get the actual workflow to use
        workflow_to_use = request.get_workflow()

        # Generate the video
        video_path = await asyncio.get_event_loop().run_in_executor(
            None, use_database_workflow, workflow_to_use
        )

        if video_path:
            active_jobs[job_id].update({
                "status": "completed",
                "progress": 1.0,
                "video_url": f"/api/video/download/{Path(video_path).name}",
                "completed_at": time.time()
            })

            logger.info(f"✅ Video generation completed for job {job_id}: {video_path}")
        else:
            active_jobs[job_id].update({
                "status": "failed",
                "progress": 0.0,
                "error_message": "Video generation failed"
            })

    except Exception as e:
        logger.error(f"❌ Video generation failed for job {job_id}: {e}")
        active_jobs[job_id].update({
            "status": "failed",
            "progress": 0.0,
            "error_message": str(e)
        })

@router.get("/download/{filename}")
async def download_video(filename: str):
    """Download generated video file"""

    from fastapi.responses import FileResponse

    video_path = Path("/mnt/1TB-storage/ComfyUI/output") / filename

    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=filename
    )

logger.info("✅ Video SSOT API router loaded")