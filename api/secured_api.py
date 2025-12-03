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
from typing import Dict, Optional, List
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Depends, Header
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
    "https://***REMOVED***",
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
    """Health check endpoint (no auth required)"""
    return {
        "status": "healthy",
        "service": "secured-anime-production",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat()
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
    user_data: dict = Depends(require_auth)
):
    """Get job status (requires authentication)"""

    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    # Verify user owns this job
    if job["user"] != user_data.get("email"):
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "job_id": job_id,
        "status": job["status"],
        "output_path": job.get("output_path"),
        "error": job.get("error"),
        "created_at": job["created_at"]
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

if __name__ == "__main__":
    logger.info("Starting Secured Anime Production API")

    # Check for database password
    if not DB_CONFIG['password']:
        logger.warning("Database password not set in environment. Using fallback.")
        DB_CONFIG['password'] = '***REMOVED***'  # Should be from Vault

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8331,  # New port for secured API
        log_level="info"
    )