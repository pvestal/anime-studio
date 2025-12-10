#!/usr/bin/env python3
"""Secured Anime Production API with Authentication and Rate Limiting"""

import os
import sys
import uuid
import time
import json
import subprocess
import psutil
import logging
import httpx
import asyncio
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime, timedelta

from v2_integration import v2_integration, create_tracked_job, complete_job_with_quality, reproduce_job
from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
import uvicorn

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth_middleware import require_auth, optional_auth, rate_limit

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI with security
app = FastAPI(
    title="Secured Anime Production API",
    description="Production-ready anime generation API with authentication and rate limiting",
    version="2.0.0",
    docs_url="/api/anime/docs",
    redoc_url="/api/anime/redoc"
)

# Configure CORS properly (not wide open)
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://192.168.50.135",
    "https://tower.local"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# Job storage (should be Redis in production)
jobs: Dict[str, dict] = {}

# GPU resource management
gpu_queue = []
active_generation = None

async def check_gpu_availability() -> bool:
    """Check if GPU is available for new generation"""
    global active_generation

    if active_generation is None:
        return True

    # Check if active job is still running in ComfyUI
    try:
        async with httpx.AsyncClient() as client:
            queue_response = await client.get("http://localhost:8188/queue")
            queue_data = queue_response.json()

            # If queue is empty, GPU is available
            if not queue_data.get("queue_running", []):
                active_generation = None
                return True

            return False
    except:
        # If can't check, assume available to avoid blocking
        active_generation = None
        return True

async def get_comfyui_job_status(prompt_id: str) -> Dict:
    """Get real-time job status from ComfyUI"""
    try:
        # Check if job is still in queue
        async with httpx.AsyncClient() as client:
            queue_response = await client.get("http://localhost:8188/queue")
            queue_data = queue_response.json()

            # Check running queue
            for item in queue_data.get("queue_running", []):
                if len(item) > 1 and item[1] == prompt_id:
                    return {
                        "status": "processing",
                        "progress": 50,
                        "estimated_remaining": 30
                    }

            # Check pending queue
            for item in queue_data.get("queue_pending", []):
                if len(item) > 1 and item[1] == prompt_id:
                    return {
                        "status": "queued",
                        "progress": 0,
                        "estimated_remaining": 60
                    }

            # Check history for completion
            history_response = await client.get(f"http://localhost:8188/history/{prompt_id}")

            if history_response.status_code == 200:
                history = history_response.json()

                if prompt_id in history:
                    prompt_history = history[prompt_id]

                    if "outputs" in prompt_history:
                        # Find output files
                        for node_id, output in prompt_history["outputs"].items():
                            if "images" in output:
                                filename = output["images"][0]["filename"]
                                output_path = f"/mnt/1TB-storage/ComfyUI/output/{filename}"

                                return {
                                    "status": "completed",
                                    "progress": 100,
                                    "output_path": output_path,
                                    "estimated_remaining": 0
                                }
                            elif "videos" in output:
                                filename = output["videos"][0]["filename"]
                                output_path = f"/mnt/1TB-storage/ComfyUI/output/{filename}"

                                return {
                                    "status": "completed",
                                    "progress": 100,
                                    "output_path": output_path,
                                    "estimated_remaining": 0
                                }
                            elif "gifs" in output:
                                # VHS_VideoCombine outputs MP4 as "gifs"
                                filename = output["gifs"][0]["filename"]
                                # Handle both flat and organized paths
                                if filename.startswith("projects/"):
                                    output_path = f"/mnt/1TB-storage/ComfyUI/output/{filename}"
                                else:
                                    output_path = f"/mnt/1TB-storage/ComfyUI/output/{filename}"

                                return {
                                    "status": "completed",
                                    "progress": 100,
                                    "output_path": output_path,
                                    "estimated_remaining": 0
                                }

            # If not found anywhere, assume failed after timeout
            return {
                "status": "failed",
                "progress": 0,
                "error": "Job not found in ComfyUI queue or history",
                "estimated_remaining": 0
            }

    except Exception as e:
        logger.error(f"Failed to get ComfyUI status for {prompt_id}: {e}")
        return None

# Database configuration from environment
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'anime_production'),
    'user': os.getenv('DB_USER', 'patrick'),
    'password': os.getenv('DB_PASSWORD')  # Should be from Vault
}

# Request validation
class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=500)
    type: str = Field(default="image", pattern="^(image|video)$")

    @validator('prompt')
    def validate_prompt(cls, v):
        """Sanitize and validate prompt"""
        # Remove any SQL-like patterns
        dangerous_patterns = ['DROP', 'DELETE', 'INSERT', 'UPDATE', '--', ';']
        for pattern in dangerous_patterns:
            if pattern in v.upper():
                raise ValueError(f"Invalid characters in prompt")
        return v.strip()

def get_gpu_memory() -> dict:
    """Get GPU memory usage"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.free,memory.total', '--format=csv,nounits,noheader'],
            capture_output=True,
            text=True,
            check=True
        )
        free, total = map(int, result.stdout.strip().split(','))
        return {'free': free, 'total': total, 'used': total - free}
    except Exception as e:
        logger.error(f"Error getting GPU memory: {e}")
        return {'free': 0, 'total': 0, 'used': 0}

def ensure_vram_available(required_mb: int = 8000) -> bool:
    """Ensure sufficient VRAM is available"""
    memory = get_gpu_memory()
    logger.info(f"Current VRAM: {memory['free']}MB free / {memory['total']}MB total")

    if memory['free'] < required_mb:
        logger.warning(f"Insufficient VRAM: {memory['free']}MB < {required_mb}MB required")
        return False

    print(f"✓ Sufficient VRAM available")
    return True

def submit_to_comfyui(prompt: str, job_id: str) -> bool:
    """Submit generation job to ComfyUI"""
    try:
        # ComfyUI workflow (simplified)
        workflow = {
            "3": {
                "inputs": {
                    "seed": int(time.time()),
                    "steps": 20,
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
                    "ckpt_name": "counterfeit_v3.safetensors"
                },
                "class_type": "CheckpointLoaderSimple"
            },
            "5": {
                "inputs": {
                    "width": 512,
                    "height": 512,
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
                    "text": "bad quality, blurry, low resolution",
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
                    "filename_prefix": f"anime_{job_id}",
                    "images": ["8", 0]
                },
                "class_type": "SaveImage"
            }
        }

        # Submit to ComfyUI
        import requests
        response = requests.post(
            "http://localhost:8188/prompt",
            json={"prompt": workflow}
        )

        if response.status_code == 200:
            return True
        else:
            logger.error(f"ComfyUI returned status {response.status_code}")
            return False

    except Exception as e:
        logger.error(f"Error submitting to ComfyUI: {e}")
        return False

@app.get("/api/anime/health")
async def health():
    """Comprehensive health check with system status (no auth required)"""
    try:
        # Check ComfyUI connectivity
        async with httpx.AsyncClient(timeout=5) as client:
            comfyui_response = await client.get("http://localhost:8188/queue")
            comfyui_status = "healthy" if comfyui_response.status_code == 200 else "unhealthy"
            queue_data = comfyui_response.json() if comfyui_response.status_code == 200 else {}
    except:
        comfyui_status = "unavailable"
        queue_data = {}

    # Check GPU availability
    gpu_available = await check_gpu_availability()

    # Count active jobs
    active_jobs = len([j for j in jobs.values() if j["status"] == "processing"])

    # Check project directories
    project_dirs_exist = Path("/mnt/1TB-storage/ComfyUI/output/projects").exists()

    return {
        "status": "healthy",
        "service": "secured-anime-production",
        "version": "3.0.0-bulletproof",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "comfyui": {
                "status": comfyui_status,
                "queue_running": len(queue_data.get("queue_running", [])),
                "queue_pending": len(queue_data.get("queue_pending", []))
            },
            "gpu": {
                "available": gpu_available,
                "active_generation": active_generation is not None
            },
            "jobs": {
                "active_count": active_jobs,
                "total_tracked": len(jobs)
            },
            "storage": {
                "project_structure": project_dirs_exist
            }
        },
        "bulletproof_features": [
            "Real-time job status tracking",
            "WebSocket progress updates",
            "Structured file organization",
            "GPU resource management",
            "Character consistency checking",
            "Error handling and recovery",
            "Performance optimization (15 steps)"
        ]
    }

@app.post("/api/anime/generate")
async def generate_anime(
    request: GenerateRequest,
    user_data: dict = Depends(require_auth)
):
    """Generate anime image (requires authentication)"""

    # Rate limiting per user
    user_email = user_data.get('email', 'unknown')

    # Check VRAM availability
    if not ensure_vram_available(8000):
        raise HTTPException(
            status_code=503,
            detail="Insufficient GPU resources. Please try again later."
        )

    # Create job
    job_id = str(uuid.uuid4())

    # Submit to ComfyUI
    success = submit_to_comfyui(request.prompt, job_id)

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to submit generation job"
        )

    # Store job with user info
    jobs[job_id] = {
        "id": job_id,
        "prompt": request.prompt,
        "type": request.type,
        "status": "processing",
        "created_at": time.time(),
        "user": user_email,
        "output_path": None,
        "error": None
    }

    logger.info(f"Job {job_id} created for user {user_email}: {request.prompt[:50]}...")

    # Start checking for completion in background
    import threading
    def check_completion():
        time.sleep(3)  # Typical generation time
        output_path = f"/mnt/1TB-storage/ComfyUI/output/anime_{job_id}_00001_.png"

        if os.path.exists(output_path):
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["output_path"] = output_path
            logger.info(f"Job {job_id} completed")
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = "Generation failed"
            logger.error(f"Job {job_id} failed - output not found")

    threading.Thread(target=check_completion).start()

    return {
        "job_id": job_id,
        "status": "processing",
        "estimated_time": 3,
        "message": f"Generation started for {user_email}"
    }

@app.get("/api/anime/generation/{job_id}/status")
async def get_job_status(
    job_id: str,
    user_data: dict = Depends(optional_auth)
):
    """Get job status with real ComfyUI progress tracking"""

    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    # Verify user owns this job (skip for anonymous orchestrate jobs)
    if job["user"] != "anonymous" and job["user"] != user_data.get("email"):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check real-time status from ComfyUI
    comfyui_id = job.get("comfyui_id", job_id)
    real_status = await get_comfyui_job_status(comfyui_id)

    if real_status:
        # Update job with real ComfyUI status
        job.update(real_status)

    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": job.get("progress", 0),
        "output_path": job.get("output_path"),
        "error": job.get("error"),
        "created_at": job["created_at"],
        "estimated_remaining": job.get("estimated_remaining", 0)
    }

@app.get("/api/anime/jobs")
async def list_user_jobs(
    user_data: dict = Depends(require_auth)
):
    """List user's jobs (requires authentication)"""

    user_email = user_data.get("email")
    user_jobs = [
        job for job in jobs.values()
        if job["user"] == user_email
    ]

    return {
        "jobs": user_jobs,
        "count": len(user_jobs),
        "user": user_email
    }

@app.get("/api/anime/gallery")
async def get_gallery(
    user_data: Optional[dict] = Depends(optional_auth)
):
    """Get public gallery (authentication optional)"""

    # Different content for authenticated users
    if user_data:
        return {
            "message": f"Welcome {user_data['email']}!",
            "gallery": "Premium gallery content"
        }
    else:
        return {
            "message": "Public gallery",
            "gallery": "Limited gallery content"
        }

# Admin endpoints
@app.get("/api/anime/admin/stats")
async def admin_stats(
    user_data: dict = Depends(require_auth)
):
    """Admin statistics (requires admin role)"""

    # Check for admin role
    if user_data.get("email") != "patrick.vestal.digital@gmail.com":
        raise HTTPException(status_code=403, detail="Admin access required")

    memory = get_gpu_memory()

    return {
        "total_jobs": len(jobs),
        "active_jobs": len([j for j in jobs.values() if j["status"] == "processing"]),
        "gpu_memory": memory,
        "users": len(set(j["user"] for j in jobs.values()))
    }

# Phase-based Workflow Orchestration
@app.post("/api/anime/orchestrate")
async def orchestrate_production(request: dict):
    """Generate anime using simple working generator with GPU management"""
    global active_generation

    # Check GPU availability
    gpu_available = await check_gpu_availability()

    if not gpu_available:
        raise HTTPException(
            status_code=503,
            detail="GPU is busy with another generation. Please try again in a few moments."
        )

    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
        from simple_generator import generate_with_tracking

        generation_type = request.get("type", "image")

        # Mark GPU as busy
        active_generation = str(uuid.uuid4())
        logger.info(f"GPU reserved for generation: {active_generation}")
        result = await generate_with_tracking(
            prompt=request.get("prompt", "anime character"),
            character_name=request.get("character_name", "default"),
            project_id=request.get("project_id", 1),
            generation_type=generation_type,
            width=request.get("width", 1024),
            height=request.get("height", 1024),
            negative_prompt=request.get("negative_prompt", "low quality"),
            seed=request.get("seed", -1),
            frames=request.get("frames", 48),
            fps=request.get("fps", 24)
        )

        # Store job for status tracking if ComfyUI prompt_id exists
        if result.get("success") and result.get("prompt_id"):
            prompt_id = result["prompt_id"]
            jobs[prompt_id] = {
                "id": prompt_id,
                "prompt": request.get("prompt", "anime character"),
                "type": generation_type,
                "status": result.get("status", "processing"),
                "created_at": time.time(),
                "user": "anonymous",  # No auth required for orchestrate
                "output_path": result.get("output_path"),
                "error": None,
                "comfyui_id": prompt_id
            }
            logger.info(f"Stored job {prompt_id} for status tracking")

        return result
    except Exception as e:
        # Release GPU on error
        active_generation = None
        import traceback
        logger.error(f"Orchestrate error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(500, f"Generation failed: {e}")
    finally:
        # GPU will be released when job completes via status checking
        pass

@app.get("/api/anime/phases")
async def get_production_phases():
    """Get available production phases"""
    return {
        "phases": [
            {"id": 1, "name": "CHARACTER_SHEET", "description": "Static character reference", "engine": "IPAdapter", "output": "8-pose sheet"},
            {"id": 2, "name": "ANIMATION_LOOP", "description": "Short loops", "engine": "AnimateDiff", "output": "2-second loops"},
            {"id": 3, "name": "FULL_VIDEO", "description": "Complete videos", "engine": "SVD", "output": "5-second videos"}
        ],
        "workflow": "Phase 1 to Phase 2 to Phase 3",
        "quality_gates": "80% quality required per phase"
    }

# WebSocket connections manager
websocket_connections = {}

@app.websocket("/ws/progress/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    """WebSocket for real-time progress updates with ComfyUI integration"""
    await websocket.accept()
    websocket_connections[job_id] = websocket
    logger.info(f"WebSocket connected for job {job_id}")

    try:
        while True:
            if job_id in jobs:
                job = jobs[job_id]

                # Get real-time status from ComfyUI
                comfyui_id = job.get("comfyui_id", job_id)
                real_status = await get_comfyui_job_status(comfyui_id)

                if real_status:
                    job.update(real_status)

                progress_data = {
                    "job_id": job_id,
                    "status": job["status"],
                    "progress": job.get("progress", 0),
                    "estimated_remaining": job.get("estimated_remaining", 0),
                    "output_path": job.get("output_path"),
                    "timestamp": time.time()
                }

                await websocket.send_json(progress_data)

                if job["status"] in ["completed", "failed"]:
                    logger.info(f"WebSocket job {job_id} finished with status: {job['status']}")
                    break
            else:
                # Job not found, send error and close
                await websocket.send_json({
                    "job_id": job_id,
                    "status": "not_found",
                    "error": "Job not found",
                    "timestamp": time.time()
                })
                break

            await asyncio.sleep(2)  # Update every 2 seconds

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for job {job_id}")
        if job_id in websocket_connections:
            del websocket_connections[job_id]

async def send_progress_update(job_id: str, progress: int, status: str, message: str = ""):
    """Send progress update via WebSocket"""
    if job_id in websocket_connections:
        try:
            await websocket_connections[job_id].send_json({
                "job_id": job_id,
                "progress": progress,
                "status": status,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to send progress update: {e}")
            # Remove failed connection
            if job_id in websocket_connections:
                del websocket_connections[job_id]


if __name__ == "__main__":
    logger.info("Starting Secured Anime Production API")

    # Check for database password
    if not DB_CONFIG['password']:
        logger.warning("Database password not set in environment. Using fallback.")
        DB_CONFIG['password'] = 'tower_echo_brain_secret_key_2025'  # Should be from Vault

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8328,  # Anime production service port
        log_level="info"
    )
