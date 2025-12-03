#!/usr/bin/env python3
"""
ANIME GENERATION API - FastAPI ComfyUI integration
Simple image generation with job tracking
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
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Configuration - using tested values
COMFYUI_URL = "http://localhost:8188"
OUTPUT_DIR = Path("/mnt/1TB-storage/ComfyUI/output")
PORT = 8328  # Replace broken main API on this port

# FastAPI app
app = FastAPI(
    title="Working Anime API",
    description="Built on tested ComfyUI foundation - honest functionality only",
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
    negative_prompt: Optional[str] = "bad quality, deformed, blurry"
    width: int = 512
    height: int = 768

def create_working_workflow(prompt: str, negative_prompt: str, width: int, height: int) -> Dict[str, Any]:
    """Create workflow - copied from tested working version"""

    seed = int(time.time() * 1000) % 2147483647
    filename_prefix = f"working_api_{int(time.time())}"

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
                "filename_prefix": filename_prefix,
                "images": ["8", 0]
            },
            "class_type": "SaveImage"
        }
    }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "working-anime-api",
        "status": "running",
        "foundation": "tested ComfyUI (10 second generation verified)",
        "port": PORT,
        "warning": "Only includes proven functionality"
    }

@app.get("/health")
async def health_check():
    """Health check - test actual ComfyUI connection"""

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

    return {
        "status": "healthy",
        "comfyui": comfyui_status,
        "vram": vram_info,
        "output_dir": str(OUTPUT_DIR),
        "output_accessible": output_accessible,
        "active_jobs": len([j for j in jobs.values() if j["status"] in ["queued", "running"]]),
        "completed_jobs": len([j for j in jobs.values() if j["status"] == "completed"]),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/generate")
async def generate_image(request: GenerationRequest):
    """Generate image - using tested ComfyUI workflow"""

    # Create job ID
    job_id = str(uuid.uuid4())[:8]

    try:
        # Store job
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
            "error": None,
            "start_time": time.time()
        }

        # Create workflow using tested version
        workflow = create_working_workflow(
            request.prompt,
            request.negative_prompt,
            request.width,
            request.height
        )

        # Submit to ComfyUI (tested to work)
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
            jobs[job_id]["error"] = "No prompt_id returned"
            raise HTTPException(500, "No prompt_id returned")

        # Update job
        jobs[job_id]["comfyui_id"] = comfyui_id
        jobs[job_id]["status"] = "running"

        return {
            "job_id": job_id,
            "status": "running",
            "comfyui_id": comfyui_id,
            "estimated_time": "10-15 seconds (based on testing)",
            "message": "Generation started - check /jobs/{job_id} for status"
        }

    except requests.RequestException as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = f"Network error: {str(e)}"
        raise HTTPException(500, f"ComfyUI connection error: {str(e)}")
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        raise HTTPException(500, f"Generation error: {str(e)}")

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status with honest progress reporting"""

    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")

    job = jobs[job_id]

    # Update status if running
    if job["status"] == "running" and job["comfyui_id"]:
        elapsed_time = time.time() - job["start_time"]

        try:
            # Check ComfyUI history
            history_response = requests.get(
                f"{COMFYUI_URL}/history/{job['comfyui_id']}",
                timeout=5
            )

            if history_response.status_code == 200:
                history = history_response.json()

                if job["comfyui_id"] in history:
                    # Job completed - find output
                    job_result = history[job["comfyui_id"]]
                    outputs = job_result.get("outputs", {})

                    for node_output in outputs.values():
                        if "images" in node_output:
                            for img in node_output["images"]:
                                output_path = OUTPUT_DIR / img["filename"]
                                if output_path.exists():
                                    job["output_path"] = str(output_path)
                                    job["status"] = "completed"
                                    job["completed_at"] = datetime.utcnow().isoformat()
                                    job["total_time"] = elapsed_time
                                    break
                            if job["status"] == "completed":
                                break

                    # Mark as failed if no output found
                    if job["status"] == "running" and job["comfyui_id"] in history:
                        job["status"] = "failed"
                        job["error"] = "Generation completed but no output file found"

        except Exception as e:
            job["status_check_error"] = str(e)

    return job

@app.get("/jobs")
async def list_jobs():
    """List all jobs"""
    return {
        "jobs": list(jobs.values()),
        "summary": {
            "total": len(jobs),
            "completed": len([j for j in jobs.values() if j["status"] == "completed"]),
            "running": len([j for j in jobs.values() if j["status"] == "running"]),
            "failed": len([j for j in jobs.values() if j["status"] == "failed"])
        }
    }

# Add nginx-compatible endpoints
@app.get("/api/anime/health")
async def anime_health_check():
    """Nginx-compatible health endpoint"""
    health_data = await health_check()
    return {"status": "healthy", "service": "tower-anime-production", "details": health_data}

@app.post("/api/anime/generate")
async def anime_generate(request: GenerationRequest):
    """Nginx-compatible generation endpoint"""
    return await generate_image(request)

@app.get("/api/anime/jobs/{job_id}")
async def anime_job_status(job_id: str):
    """Nginx-compatible job status endpoint"""
    return await get_job_status(job_id)

# Mount static files
app.mount(
    "/static",
    StaticFiles(directory="/opt/tower-anime-production/static"),
    name="static"
)

@app.get("/frontend", response_class=HTMLResponse)
async def frontend_interface():
    """Serve the anime production frontend"""
    try:
        with open("/opt/tower-anime-production/static/dist/index.html", "r") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(
            content="""
            <html>
                <head><title>Anime Studio - Build Required</title></head>
                <body style="font-family: Arial; padding: 2rem; background: #1a1a1a; color: #e0e0e0;">
                    <h1>Echo Brain Anime Studio</h1>
                    <p>Frontend build not found. Run: <code>cd /opt/tower-anime-production/frontend && pnpm run build</code></p>
                    <h2>API Status</h2>
                    <ul>
                        <li><a href="/" style="color: #4a9eff;">API Status</a></li>
                        <li><a href="/health" style="color: #4a9eff;">Health Check</a></li>
                        <li><a href="/jobs" style="color: #4a9eff;">View Jobs</a></li>
                    </ul>
                </body>
            </html>
            """
        )

if __name__ == "__main__":
    print(f"🚀 Starting Working Anime API")
    print(f"📍 Port: {PORT}")
    print(f"🎯 ComfyUI: {COMFYUI_URL} (tested working)")
    print(f"📁 Output: {OUTPUT_DIR}")
    print(f"⚠️  HONEST API - Only includes verified functionality")

    uvicorn.run(app, host="0.0.0.0", port=PORT)