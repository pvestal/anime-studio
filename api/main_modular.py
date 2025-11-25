#!/usr/bin/env python3
"""
Clean Modular Anime Production API
Orchestrates ComfyUI generation with proper job tracking and file management
Fixes the broken job status API and provides actual working progress tracking
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

# Import our modular components
import sys
sys.path.append('/opt/tower-anime-production')
from modules import (
    ComfyUIConnector, JobManager, WorkflowGenerator, DatabaseManager,
    StatusMonitor, FileManager
)
from modules.job_manager import JobType, JobStatus

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# App initialization
app = FastAPI(title="Anime Production API", version="2.0.0")

# Global components
job_manager = None
workflow_generator = None
database_manager = None
comfyui_connector = None

# Configuration
COMFYUI_URL = "http://***REMOVED***:8188"
OUTPUT_BASE_PATH = "/mnt/1TB-storage/ComfyUI/output"

# Request models
class ImageRequest(BaseModel):
    prompt: str = Field(..., description="Text prompt for image generation")
    width: int = Field(512, ge=256, le=2048, description="Image width")
    height: int = Field(512, ge=256, le=2048, description="Image height")
    steps: int = Field(20, ge=1, le=100, description="Generation steps")
    cfg: float = Field(7.0, ge=1.0, le=20.0, description="CFG scale")
    model: Optional[str] = Field(None, description="Model to use")
    negative_prompt: Optional[str] = Field("", description="Negative prompt")

class VideoRequest(BaseModel):
    prompt: str = Field(..., description="Text prompt for video generation")
    duration: int = Field(2, ge=1, le=10, description="Duration in seconds")
    fps: int = Field(12, ge=8, le=30, description="Frames per second")
    width: int = Field(512, ge=256, le=1024, description="Video width")
    height: int = Field(512, ge=256, le=1024, description="Video height")
    steps: int = Field(20, ge=1, le=50, description="Generation steps")
    model: Optional[str] = Field(None, description="Model to use")

# Global instances
file_manager = None
status_monitor = None

@app.on_event("startup")
async def startup_event():
    """Initialize all components"""
    global job_manager, workflow_generator, database_manager, comfyui_connector, status_monitor, file_manager

    try:
        # Initialize database
        database_manager = DatabaseManager()
        database_manager.initialize()

        # Initialize components
        job_manager = JobManager(database_manager)
        workflow_generator = WorkflowGenerator()
        comfyui_connector = ComfyUIConnector(COMFYUI_URL)
        file_manager = FileManager(OUTPUT_BASE_PATH)

        # Initialize status monitor with all dependencies
        status_monitor = StatusMonitor(comfyui_connector, database_manager)
        await status_monitor.start_monitoring()

        # Test ComfyUI connection
        health = await comfyui_connector.check_health()
        if not health:
            logger.warning("⚠️ ComfyUI not responding - generation will fail")
        else:
            logger.info("✅ ComfyUI connection verified")

        logger.info("🚀 Anime Production API started successfully")

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise

@app.post("/api/anime/generate/image")
async def generate_image(request: ImageRequest, background_tasks: BackgroundTasks):
    """Generate a single image"""
    try:
        # Create job
        job = job_manager.create_job(JobType.IMAGE, request.prompt, request.dict())

        # Generate workflow
        workflow = workflow_generator.generate_image_workflow(
            prompt=request.prompt,
            width=request.width,
            height=request.height,
            steps=request.steps,
            cfg=request.cfg,
            model=request.model,
            negative_prompt=request.negative_prompt
        )

        # Submit to ComfyUI in background
        background_tasks.add_task(submit_job_to_comfyui, job.id, workflow)

        return {
            "job_id": job.id,
            "status": job.status.value,
            "message": "Image generation job created",
            "estimated_time": "30-60 seconds"
        }

    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/anime/generate/video")
async def generate_video(request: VideoRequest, background_tasks: BackgroundTasks):
    """Generate a video"""
    try:
        # Create job
        job = job_manager.create_job(JobType.VIDEO, request.prompt, request.dict())

        # Generate workflow
        workflow = workflow_generator.generate_video_workflow(
            prompt=request.prompt,
            duration=request.duration,
            fps=request.fps,
            width=request.width,
            height=request.height,
            steps=request.steps,
            model=request.model
        )

        # Submit to ComfyUI in background
        background_tasks.add_task(submit_job_to_comfyui, job.id, workflow)

        return {
            "job_id": job.id,
            "status": job.status.value,
            "message": "Video generation job created",
            "estimated_time": f"{request.duration * 30}s - {request.duration * 60}s"
        }

    except Exception as e:
        logger.error(f"Video generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/anime/jobs/{job_id}")
async def get_job_status(job_id: int):
    """Get actual job status with ComfyUI verification"""
    try:
        job = job_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get real progress from status monitor
        progress = await status_monitor.get_progress(job_id)

        # Get completion estimate
        estimated_completion = await status_monitor.estimate_completion(job_id)

        # Find output files
        output_files = file_manager.get_output_files(job_id) if hasattr(file_manager, 'get_output_files') else []

        response = {
            **job.to_dict(),
            "progress": progress.__dict__ if progress else None,
            "estimated_completion": estimated_completion.isoformat() if estimated_completion else None,
            "output_files": output_files
        }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/anime/jobs")
async def list_jobs(status: Optional[str] = None, limit: int = 50):
    """List jobs with optional status filter"""
    try:
        status_filter = None
        if status:
            try:
                status_filter = JobStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        jobs = job_manager.list_jobs(status_filter, limit)

        return {
            "jobs": [job.to_dict() for job in jobs],
            "total": len(jobs)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/anime/queue")
async def get_queue_status():
    """Get ComfyUI queue status and job statistics"""
    try:
        # Get comprehensive queue statistics from status monitor
        queue_stats = await status_monitor.get_queue_statistics()

        # Get job statistics
        job_stats = job_manager.get_statistics()

        # Get recent files if available
        recent_files = []
        if hasattr(file_manager, 'get_latest_files'):
            recent_files = file_manager.get_latest_files(5)

        return {
            "queue_statistics": queue_stats,
            "job_statistics": job_stats,
            "recent_files": recent_files,
            "system_status": "operational"
        }

    except Exception as e:
        logger.error(f"Failed to get queue status: {e}")
        return {
            "queue_statistics": {"error": str(e)},
            "job_statistics": job_manager.get_statistics() if job_manager else {},
            "recent_files": [],
            "system_status": "degraded"
        }

async def submit_job_to_comfyui(job_id: int, workflow: Dict[str, Any]):
    """Background task to submit job to ComfyUI"""
    try:
        # Update job status
        job_manager.update_job_status(job_id, JobStatus.PROCESSING)

        # Submit to ComfyUI
        async with ComfyUIConnector(COMFYUI_URL) as comfyui:
            prompt_id = await comfyui.submit_workflow(workflow, f"job_{job_id}")

            if prompt_id:
                # Update job with ComfyUI ID
                job_manager.update_job_status(
                    job_id,
                    JobStatus.PROCESSING,
                    comfyui_id=prompt_id
                )

                # Get job type for monitoring
                job = job_manager.get_job(job_id)
                job_type = job.type.value if job else "unknown"

                # Start monitoring the job with status monitor
                status_monitor.monitor_job(job_id, prompt_id, job_type)

                logger.info(f"✅ Job {job_id} submitted to ComfyUI: {prompt_id}")
            else:
                # Submission failed
                job_manager.update_job_status(
                    job_id,
                    JobStatus.FAILED,
                    error_message="Failed to submit to ComfyUI"
                )
                logger.error(f"❌ Job {job_id} failed to submit to ComfyUI")

    except Exception as e:
        job_manager.update_job_status(
            job_id,
            JobStatus.FAILED,
            error_message=str(e)
        )
        logger.error(f"❌ Job {job_id} background submission failed: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown of all components"""
    try:
        if status_monitor:
            await status_monitor.stop_monitoring()
        logger.info("🛑 Anime Production API shutdown complete")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

if __name__ == "__main__":
    uvicorn.run(
        "main_modular:app",
        host="0.0.0.0",
        port=8328,
        reload=False,
        log_level="info"
    )