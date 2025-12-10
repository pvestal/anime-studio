#!/usr/bin/env python3
"""
Working Anime Production API - Minimal but functional
"""
import sys
import uuid
from datetime import datetime

import aiohttp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add vram manager
sys.path.append("/opt/tower-anime-production")
from vram_manager import ensure_vram_available

app = FastAPI(title="Working Anime API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job storage (for testing)
jobs = {}


class GenerateRequest(BaseModel):
    prompt: str
    type: str = "image"  # image or video


class JobStatus(BaseModel):
    id: str
    status: str
    progress: float
    stage: str
    output_path: str = None
    error: str = None


@app.get("/health")


async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "working-anime-api"}


@app.post("/api/anime/generate")


async def generate(request: GenerateRequest):
    """Generate anime content with proper VRAM management"""

    # Check VRAM before starting
    if not ensure_vram_available(8000):
        raise HTTPException(status_code=503, detail="Insufficient GPU memory")

    job_id = str(uuid.uuid4())

    # Create simple workflow for image generation
    workflow = {
        "1": {
            "inputs": {"ckpt_name": "counterfeit_v3.safetensors"},
            "class_type": "CheckpointLoaderSimple",
        },
        "2": {"inputs": {"text": request.prompt, "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
        "3": {
            "inputs": {"text": "blurry, low quality", "clip": ["1", 1]},
            "class_type": "CLIPTextEncode",
        },
        "4": {
            "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["5", 0],
            },
            "class_type": "KSampler",
        },
        "5": {
            "inputs": {"width": 512, "height": 512, "batch_size": 1},
            "class_type": "EmptyLatentImage",
        },
        "6": {"inputs": {"samples": ["4", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
        "7": {
            "inputs": {"filename_prefix": f"anime_{job_id}", "images": ["6", 0]},
            "class_type": "SaveImage",
        },
    }

    # Submit to ComfyUI
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"prompt": workflow, "client_id": job_id}

            async with session.post("http://localhost:8188/prompt", json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    prompt_id = data.get("prompt_id")

                    # Store job info
                    jobs[job_id] = {
                        "id": job_id,
                        "status": "processing",
                        "progress": 0.1,
                        "stage": "submitted",
                        "prompt_id": prompt_id,
                        "created_at": datetime.now().isoformat(),
                    }

                    return {"job_id": job_id, "status": "submitted"}
                else:
                    error = await resp.text()
                    raise HTTPException(status_code=resp.status, detail=f"ComfyUI error: {error}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anime/generation/{job_id}/status")


async def get_status(job_id: str):
    """Get real job status"""

    if job_id not in jobs:
        return {"id": job_id, "status": "not_found", "progress": 0}

    job = jobs[job_id]

    # Check ComfyUI for progress
    if job.get("prompt_id"):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:8188/history/{job['prompt_id']}") as resp:
                    if resp.status == 200:
                        history = await resp.json()
                        if job["prompt_id"] in history:
                            outputs = history[job["prompt_id"]].get("outputs", {})
                            if outputs:
                                # Job completed
                                job["status"] = "completed"
                                job["progress"] = 1.0
                                job["stage"] = "done"

                                # Find output files
                                for node_id, node_output in outputs.items():
                                    if "images" in node_output:
                                        images = node_output["images"]
                                        if images:
                                            job["output_path"] = (
                                                f"/mnt/1TB-storage/ComfyUI/output/{images[0]['filename']}"
                                            )
                                            break
                            else:
                                # Still processing
                                job["progress"] = 0.5
                                job["stage"] = "rendering"
        except Exception as e:
            job["error"] = str(e)

    return JobStatus(**job)


@app.get("/api/anime/jobs")


async def list_jobs():
    """List all jobs"""
    return list(jobs.values())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8330)
