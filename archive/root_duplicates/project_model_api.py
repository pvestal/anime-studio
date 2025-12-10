#!/usr/bin/env python3
"""
PROJECT MODEL API - Multiple checkpoint support for different content types
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
PORT = 50001

# Available models for different content types
MODELS = {
    "anime": "Counterfeit-V2.5.safetensors",
    "anime_v3": "counterfeit_v3.safetensors",
    "realistic": "juggernautXL_v9.safetensors",
    "flux": "flux1-dev-fp8.safetensors",
    "sdxl": "sd_xl_base_1.0.safetensors",
    "turbo": "sdxl_turbo_1.0.safetensors"
}

app = FastAPI(
    title="Project Model API",
    description="Multi-model anime generation for different content types",
    version="1.0.0"
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

jobs: Dict[str, Dict[str, Any]] = {}

class GenerationRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = "bad quality, deformed, blurry"
    width: int = 768
    height: int = 768
    model_type: str = "anime"  # anime, anime_v3, realistic, flux, sdxl, turbo

def create_model_workflow(prompt: str, negative_prompt: str, width: int, height: int, model_type: str) -> Dict[str, Any]:
    """Create workflow with specific model selection"""
    if model_type not in MODELS:
        raise ValueError(f"Invalid model type: {model_type}. Available: {list(MODELS.keys())}")

    model_name = MODELS[model_type]
    seed = int(time.time() * 1000) % 2147483647
    filename_prefix = f"project_{model_type}_{int(time.time())}"

    return {
        "4": {
            "inputs": {"ckpt_name": model_name},
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
        "3": {
            "inputs": {
                "seed": seed,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler"
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

@app.get("/health")
async def health_check():
    try:
        response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        comfyui_status = "connected" if response.status_code == 200 else "disconnected"

        vram_info = "Unknown"
        if response.status_code == 200:
            stats = response.json()
            if "system" in stats:
                vram_free = stats["system"].get("vram_free", 0) // (1024**2)
                vram_total = stats["system"].get("vram_total", 0) // (1024**2)
                vram_info = f"{vram_free}MB free / {vram_total}MB total"

        return {
            "status": "healthy",
            "comfyui": comfyui_status,
            "vram": vram_info,
            "output_dir": str(OUTPUT_DIR),
            "output_accessible": OUTPUT_DIR.exists(),
            "active_jobs": sum(1 for job in jobs.values() if job["status"] == "running"),
            "completed_jobs": sum(1 for job in jobs.values() if job["status"] == "completed"),
            "available_models": list(MODELS.keys()),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {"status": "degraded", "error": str(e)}

@app.post("/generate")
async def generate_image(request: GenerationRequest):
    job_id = str(uuid.uuid4())[:8]

    try:
        workflow = create_model_workflow(
            request.prompt,
            request.negative_prompt,
            request.width,
            request.height,
            request.model_type
        )

        jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "width": request.width,
            "height": request.height,
            "model_type": request.model_type,
            "model_file": MODELS[request.model_type],
            "created_at": datetime.utcnow().isoformat(),
            "comfyui_id": None,
            "output_path": None,
            "error": None
        }

        payload = {"prompt": workflow}
        response = requests.post(f"{COMFYUI_URL}/prompt", json=payload, timeout=10)

        if response.status_code == 200:
            result = response.json()
            comfyui_id = result["prompt_id"]

            jobs[job_id]["status"] = "running"
            jobs[job_id]["comfyui_id"] = comfyui_id
            jobs[job_id]["start_time"] = time.time()

            return {"job_id": job_id, "status": "started", "comfyui_id": comfyui_id}
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = f"ComfyUI error: {response.status_code}"
            raise HTTPException(status_code=500, detail=f"ComfyUI error: {response.status_code}")

    except Exception as e:
        if job_id in jobs:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    if job["status"] == "running" and job["comfyui_id"]:
        try:
            response = requests.get(f"{COMFYUI_URL}/history/{job['comfyui_id']}")

            if response.status_code == 200:
                history = response.json()
                if job["comfyui_id"] in history:
                    job_info = history[job["comfyui_id"]]

                    if "outputs" in job_info:
                        for node_id, node_output in job_info["outputs"].items():
                            if "images" in node_output:
                                image_info = node_output["images"][0]
                                filename = image_info["filename"]
                                output_path = OUTPUT_DIR / filename

                                if output_path.exists():
                                    job["status"] = "completed"
                                    job["output_path"] = str(output_path)
                                    job["completed_at"] = datetime.utcnow().isoformat()
                                    job["total_time"] = time.time() - job["start_time"]
                                    break
        except Exception as e:
            job["error"] = f"Status check error: {str(e)}"

    return job

@app.get("/models")
async def list_models():
    """List available models and their types"""
    return {
        "models": MODELS,
        "descriptions": {
            "anime": "Counterfeit v2.5 - Anime/manga style",
            "anime_v3": "Counterfeit v3 - Updated anime model",
            "realistic": "JuggernautXL v9 - Photorealistic SDXL",
            "flux": "FLUX Dev FP8 - High quality (17GB model)",
            "sdxl": "Stable Diffusion XL Base - General purpose",
            "turbo": "SDXL Turbo - Fast generation"
        }
    }

if __name__ == "__main__":
    print(f"🚀 Starting Project Model API")
    print(f"📍 Port: {PORT}")
    print(f"🎯 ComfyUI: {COMFYUI_URL}")
    print(f"📁 Output: {OUTPUT_DIR}")
    print(f"🎨 Available models: {list(MODELS.keys())}")
    print("⚙️  Multi-model support for different content types")

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")