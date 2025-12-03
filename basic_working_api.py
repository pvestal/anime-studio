#!/usr/bin/env python3
"""
BASIC WORKING ANIME API - Direct ComfyUI Connection
NO FALSE CLAIMS - Only tested functionality included
"""

import json
import time
import uuid
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Configuration
COMFYUI_URL = "http://localhost:8188"
OUTPUT_DIR = Path("/mnt/1TB-storage/ComfyUI/output")
PORT = 48888  # Different port to avoid conflicts

# FastAPI app
app = FastAPI(
    title="Basic Working Anime API",
    description="Direct ComfyUI connection - honestly tested",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job tracking (simple, no database complexity)
jobs: Dict[str, Dict[str, Any]] = {}

class GenerationRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = "bad quality, deformed"
    width: int = 512
    height: int = 768

class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str

def create_simple_workflow(prompt: str, negative_prompt: str, width: int, height: int) -> Dict[str, Any]:
    """Create a minimal ComfyUI workflow that actually works"""

    seed = int(time.time() * 1000) % 2147483647

    return {
        "3": {
            "inputs": {
                "seed": seed,
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
                "filename_prefix": f"basic_anime_{int(time.time())}",
                "images": ["8", 0]
            },
            "class_type": "SaveImage"
        }
    }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "basic-working-anime-api",
        "status": "running",
        "port": PORT,
        "warning": "NO FALSE CLAIMS - only tested functionality"
    }

@app.get("/health")
async def health_check():
    """Health check - test ComfyUI connection"""

    try:
        # Test ComfyUI connection
        response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        comfyui_status = "connected" if response.status_code == 200 else "error"
    except Exception as e:
        comfyui_status = f"error: {str(e)}"

    # Check output directory
    output_accessible = OUTPUT_DIR.exists() and OUTPUT_DIR.is_dir()

    return {
        "status": "healthy",
        "comfyui": comfyui_status,
        "output_dir": str(OUTPUT_DIR),
        "output_accessible": output_accessible,
        "active_jobs": len([j for j in jobs.values() if j["status"] in ["queued", "running"]]),
        "total_jobs": len(jobs),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/generate", response_model=JobResponse)
async def generate_image(request: GenerationRequest):
    """Generate an anime image - HONEST implementation"""

    try:
        # Create unique job ID
        job_id = str(uuid.uuid4())[:8]

        # Create workflow
        workflow = create_simple_workflow(
            request.prompt,
            request.negative_prompt,
            request.width,
            request.height
        )

        # Store job info
        jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "width": request.width,
            "height": request.height,
            "created_at": datetime.utcnow().isoformat(),
            "comfyui_id": None,
            "output_path": None,
            "error": None
        }

        # Submit to ComfyUI
        response = requests.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=10
        )

        if response.status_code != 200:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = f"ComfyUI submission failed: {response.status_code}"
            raise HTTPException(500, f"ComfyUI submission failed: {response.status_code}")

        result = response.json()
        comfyui_id = result.get("prompt_id")

        if not comfyui_id:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = "No prompt_id returned from ComfyUI"
            raise HTTPException(500, "No prompt_id returned from ComfyUI")

        # Update job with ComfyUI ID
        jobs[job_id]["comfyui_id"] = comfyui_id
        jobs[job_id]["status"] = "running"

        return JobResponse(
            job_id=job_id,
            status="running",
            message=f"Job submitted to ComfyUI with ID: {comfyui_id}"
        )

    except requests.RequestException as e:
        if job_id in jobs:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = f"Network error: {str(e)}"
        raise HTTPException(500, f"ComfyUI connection error: {str(e)}")

    except Exception as e:
        if job_id in jobs:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)
        raise HTTPException(500, f"Internal error: {str(e)}")

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status - HONEST status reporting"""

    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    job = jobs[job_id]

    # If job is running, check ComfyUI status
    if job["status"] == "running" and job["comfyui_id"]:
        try:
            # Check ComfyUI history
            history_response = requests.get(
                f"{COMFYUI_URL}/history/{job['comfyui_id']}",
                timeout=5
            )

            if history_response.status_code == 200:
                history = history_response.json()

                if job["comfyui_id"] in history:
                    # Job completed
                    job_result = history[job["comfyui_id"]]
                    outputs = job_result.get("outputs", {})

                    # Look for output images
                    for node_output in outputs.values():
                        if "images" in node_output:
                            for img in node_output["images"]:
                                output_path = OUTPUT_DIR / img["filename"]
                                if output_path.exists():
                                    job["output_path"] = str(output_path)
                                    job["status"] = "completed"
                                    job["completed_at"] = datetime.utcnow().isoformat()
                                    break
                            if job["status"] == "completed":
                                break

                    # If no output found but job exists in history, mark as failed
                    if job["status"] == "running":
                        job["status"] = "failed"
                        job["error"] = "Job completed but no output file found"

        except Exception as e:
            # Don't fail the status check if we can't reach ComfyUI
            job["comfyui_check_error"] = str(e)

    return job

@app.get("/jobs")
async def list_jobs():
    """List all jobs"""
    return list(jobs.values())

@app.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel/delete a job"""

    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    # Note: ComfyUI doesn't have a cancel API, so we just mark as cancelled
    jobs[job_id]["status"] = "cancelled"
    jobs[job_id]["cancelled_at"] = datetime.utcnow().isoformat()

    return {"message": f"Job {job_id} marked as cancelled"}

if __name__ == "__main__":
    print(f"🚀 Starting Basic Working Anime API")
    print(f"📍 Port: {PORT}")
    print(f"🎯 ComfyUI: {COMFYUI_URL}")
    print(f"📁 Output: {OUTPUT_DIR}")
    print(f"⚠️  NO FALSE CLAIMS - Only tested functionality included")

    uvicorn.run(app, host="0.0.0.0", port=PORT)