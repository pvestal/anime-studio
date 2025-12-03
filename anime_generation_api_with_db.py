#!/usr/bin/env python3
"""
ANIME GENERATION API - With Database Persistence
FastAPI ComfyUI integration with PostgreSQL job tracking
"""

import json
import time
import uuid
import requests
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Import our database manager
from database import db_manager, initialize_database, close_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
COMFYUI_URL = "http://localhost:8188"
OUTPUT_DIR = Path("/mnt/1TB-storage/ComfyUI/output")
PORT = 8328

# FastAPI app
app = FastAPI(
    title="Anime Production API",
    description="Production-ready anime generation with database persistence",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache for quick lookups (backed by database)
jobs_cache: Dict[str, Dict[str, Any]] = {}

class GenerationRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = "bad quality, deformed, blurry"
    width: int = 512
    height: int = 768
    project_id: Optional[str] = None
    character_id: Optional[str] = None

def create_working_workflow(prompt: str, negative_prompt: str, width: int, height: int) -> Dict[str, Any]:
    """Create workflow - optimized for speed"""

    seed = int(time.time() * 1000) % 2147483647
    filename_prefix = f"anime_{int(time.time())}"

    return {
        "3": {
            "inputs": {
                "seed": seed,
                "steps": 20,  # Reduced from 30 for speed
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler"
        },
        "4": {
            "inputs": {
                "ckpt_name": "Counterfeit-V2.5.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "5": {
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1
            },
            "class_type": "EmptyLatentImage"
        },
        "6": {
            "inputs": {
                "text": prompt,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "7": {
            "inputs": {
                "text": negative_prompt,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "8": {
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            },
            "class_type": "VAEDecode"
        },
        "9": {
            "inputs": {
                "filename_prefix": filename_prefix,
                "images": ["8", 0]
            },
            "class_type": "SaveImage"
        }
    }

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    logger.info("Starting anime production API...")
    await initialize_database()
    logger.info("Database initialized")

    # Load recent jobs into cache
    try:
        recent_jobs = await db_manager.list_jobs(limit=50)
        for job in recent_jobs:
            if job['id']:
                jobs_cache[job['id']] = job
        logger.info(f"Loaded {len(recent_jobs)} recent jobs into cache")
    except Exception as e:
        logger.error(f"Failed to load recent jobs: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    logger.info("Shutting down anime production API...")
    await close_database()
    logger.info("Database connections closed")

@app.get("/")
async def root():
    """Root endpoint"""
    stats = await db_manager.get_stats()
    return {
        "service": "anime-production-api",
        "version": "2.0.0",
        "status": "running",
        "database": "connected",
        "stats": stats,
        "port": PORT
    }

@app.get("/health")
async def health_check():
    """Health check with database status"""

    try:
        # Test ComfyUI connection
        response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        comfyui_status = "connected" if response.status_code == 200 else f"error_{response.status_code}"

        # Get VRAM info if connected
        vram_info = "unknown"
        if response.status_code == 200:
            data = response.json()
            devices = data.get("devices", [])
            if devices:
                vram_free = devices[0].get("vram_free", 0)
                vram_total = devices[0].get("vram_total", 0)
                vram_info = f"{vram_free//1024//1024}MB free / {vram_total//1024//1024}MB total"

    except Exception as e:
        comfyui_status = f"connection_error: {str(e)}"
        vram_info = "unknown"

    # Check output directory
    output_accessible = OUTPUT_DIR.exists() and OUTPUT_DIR.is_dir()

    # Get database stats
    try:
        stats = await db_manager.get_stats()
        db_status = "connected"
    except Exception as e:
        stats = {"error": str(e)}
        db_status = "error"

    return {
        "status": "healthy",
        "comfyui": comfyui_status,
        "database": db_status,
        "vram": vram_info,
        "output_dir": str(OUTPUT_DIR),
        "output_accessible": output_accessible,
        "jobs": stats,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/generate")
async def generate_image(request: GenerationRequest, background_tasks: BackgroundTasks):
    """Generate image with database persistence"""

    # Create job ID
    job_id = str(uuid.uuid4())[:8]

    try:
        # Create job object
        job_data = {
            "id": job_id,
            "status": "queued",
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "width": request.width,
            "height": request.height,
            "project_id": request.project_id,
            "character_id": request.character_id,
            "created_at": datetime.utcnow().isoformat(),
            "comfyui_id": None,
            "output_path": None,
            "error": None,
            "start_time": time.time()
        }

        # Store in cache
        jobs_cache[job_id] = job_data

        # Save to database
        try:
            db_id = await db_manager.create_job(job_data)
            job_data['db_id'] = db_id
            logger.info(f"Created job {job_id} in database with ID {db_id}")
        except Exception as e:
            logger.error(f"Failed to save job to database: {e}")
            # Continue anyway - don't fail the request

        # Create workflow
        workflow = create_working_workflow(
            request.prompt,
            request.negative_prompt,
            request.width,
            request.height
        )

        # Submit to ComfyUI
        response = requests.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=10
        )

        if response.status_code != 200:
            error_msg = f"ComfyUI submission failed: {response.status_code}"
            job_data["status"] = "failed"
            job_data["error"] = error_msg

            # Update database
            await db_manager.update_job_status(job_id, "failed", error=error_msg)

            raise HTTPException(500, error_msg)

        result = response.json()
        comfyui_id = result.get("prompt_id")

        if not comfyui_id:
            error_msg = "No prompt_id returned"
            job_data["status"] = "failed"
            job_data["error"] = error_msg

            # Update database
            await db_manager.update_job_status(job_id, "failed", error=error_msg)

            raise HTTPException(500, error_msg)

        # Update job
        job_data["comfyui_id"] = comfyui_id
        job_data["status"] = "running"

        # Update database
        await db_manager.update_job_status(job_id, "running", comfyui_id=comfyui_id)

        # Schedule background task to monitor completion
        background_tasks.add_task(monitor_job_completion, job_id)

        return {
            "job_id": job_id,
            "status": "running",
            "comfyui_id": comfyui_id,
            "estimated_time": "30-60 seconds",
            "message": "Generation started - check /jobs/{job_id} for status"
        }

    except requests.RequestException as e:
        error_msg = f"Network error: {str(e)}"
        job_data["status"] = "failed"
        job_data["error"] = error_msg

        # Update database
        await db_manager.update_job_status(job_id, "failed", error=error_msg)

        raise HTTPException(500, f"ComfyUI connection error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        job_data["status"] = "failed"
        job_data["error"] = error_msg

        # Update database
        await db_manager.update_job_status(job_id, "failed", error=error_msg)

        raise HTTPException(500, f"Generation error: {str(e)}")

async def monitor_job_completion(job_id: str):
    """Background task to monitor job completion"""
    max_wait = 120  # 2 minutes max
    check_interval = 2  # Check every 2 seconds
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(check_interval)
        elapsed += check_interval

        if job_id not in jobs_cache:
            logger.warning(f"Job {job_id} not in cache")
            break

        job = jobs_cache[job_id]

        if job["status"] != "running" or not job["comfyui_id"]:
            break

        try:
            # Check ComfyUI history
            response = requests.get(
                f"{COMFYUI_URL}/history/{job['comfyui_id']}",
                timeout=5
            )

            if response.status_code == 200:
                history = response.json()

                if job["comfyui_id"] in history:
                    # Job completed - find output
                    job_result = history[job["comfyui_id"]]
                    outputs = job_result.get("outputs", {})

                    output_found = False
                    for node_output in outputs.values():
                        if "images" in node_output:
                            for img in node_output["images"]:
                                output_path = OUTPUT_DIR / img["filename"]
                                if output_path.exists():
                                    job["output_path"] = str(output_path)
                                    job["status"] = "completed"
                                    job["completed_at"] = datetime.utcnow().isoformat()
                                    job["total_time"] = time.time() - job["start_time"]
                                    output_found = True

                                    # Update database
                                    await db_manager.update_job_status(
                                        job_id,
                                        "completed",
                                        output_path=str(output_path),
                                        total_time=job["total_time"]
                                    )

                                    logger.info(f"Job {job_id} completed in {job['total_time']:.2f} seconds")
                                    break
                            if output_found:
                                break

                    if not output_found:
                        # Generation finished but no output
                        job["status"] = "failed"
                        job["error"] = "Generation completed but no output file found"

                        await db_manager.update_job_status(
                            job_id,
                            "failed",
                            error=job["error"]
                        )

                        logger.error(f"Job {job_id} failed: no output file")

                    break

        except Exception as e:
            logger.error(f"Error monitoring job {job_id}: {e}")

    if elapsed >= max_wait:
        # Timeout
        job = jobs_cache.get(job_id)
        if job and job["status"] == "running":
            job["status"] = "failed"
            job["error"] = "Generation timeout"

            await db_manager.update_job_status(
                job_id,
                "failed",
                error="Generation timeout"
            )

            logger.error(f"Job {job_id} timed out")

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status from cache or database"""

    # Check cache first
    if job_id in jobs_cache:
        return jobs_cache[job_id]

    # Check database
    job = await db_manager.get_job(job_id)

    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    # Add to cache
    jobs_cache[job_id] = job

    return job

@app.get("/jobs")
async def list_jobs(limit: int = 50, offset: int = 0):
    """List jobs from database"""
    jobs = await db_manager.list_jobs(limit=limit, offset=offset)
    stats = await db_manager.get_stats()

    return {
        "jobs": jobs,
        "summary": stats,
        "limit": limit,
        "offset": offset
    }

@app.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running job"""

    if job_id not in jobs_cache:
        job = await db_manager.get_job(job_id)
        if not job:
            raise HTTPException(404, f"Job {job_id} not found")
        jobs_cache[job_id] = job

    job = jobs_cache[job_id]

    if job["status"] not in ["queued", "running"]:
        raise HTTPException(400, f"Job {job_id} cannot be cancelled (status: {job['status']})")

    # Update status
    job["status"] = "cancelled"
    job["error"] = "Cancelled by user"

    # Update database
    await db_manager.update_job_status(job_id, "cancelled", error="Cancelled by user")

    return {"message": f"Job {job_id} cancelled", "job": job}

if __name__ == "__main__":
    uvicorn.run(
        "anime_generation_api_with_db:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info"
    )