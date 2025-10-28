#!/usr/bin/env python3
"""
Simple Anime Video Generation Service
Port: 8328
Uses the proven working video generation workflow
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Optional
import uvicorn
import requests
import uuid
import os
import time
import shutil
from pathlib import Path
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Simple Anime Video Service", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
COMFYUI_URL = "http://127.0.0.1:8188"
OUTPUT_DIR = Path("/mnt/10TB2/Anime/AI_Generated")
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# Data models
class AnimeRequest(BaseModel):
    prompt: str
    character: str = "anime character"
    frames: int = 16

# Simple status tracking
generations = {}

@app.get("/api/health")
async def health_check():
    """Check service health"""
    comfyui_status = "disconnected"
    try:
        response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=2)
        if response.status_code == 200:
            comfyui_status = "connected"
    except:
        pass

    return {
        "status": "healthy",
        "service": "Simple Anime Video Service",
        "version": "1.0.0",
        "comfyui_status": comfyui_status,
        "output_dir": str(OUTPUT_DIR),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/generate/professional")
async def generate_professional(request: AnimeRequest):
    """Generate professional anime video using proven workflow"""
    generation_id = str(uuid.uuid4())

    logger.info(f"Starting generation {generation_id}: {request.prompt}")

    try:
        # Create the proven working workflow
        workflow = create_working_video_workflow(request.prompt, request.frames)

        # Submit to ComfyUI
        response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"ComfyUI failed: {response.text}")

        result = response.json()
        prompt_id = result.get('prompt_id')

        if not prompt_id:
            raise HTTPException(status_code=500, detail="No prompt_id returned")

        # Store generation info
        generations[generation_id] = {
            "prompt_id": prompt_id,
            "request": request.dict(),
            "status": "processing",
            "timestamp": datetime.now().isoformat()
        }

        logger.info(f"Submitted to ComfyUI: {prompt_id}")

        return {
            "generation_id": generation_id,
            "prompt_id": prompt_id,
            "status": "processing",
            "message": "Video generation started",
            "check_status": f"/api/status/{generation_id}"
        }

    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status/{generation_id}")
async def get_status(generation_id: str):
    """Get generation status"""
    if generation_id not in generations:
        raise HTTPException(status_code=404, detail="Generation not found")

    gen_info = generations[generation_id]
    prompt_id = gen_info["prompt_id"]

    try:
        # Check ComfyUI history
        history = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
        if history.status_code == 200:
            data = history.json()
            if prompt_id in data:
                status = data[prompt_id].get('status', {})
                if status.get('status_str') == 'success' and status.get('completed'):
                    outputs = data[prompt_id].get('outputs', {})

                    # Look for video output
                    video_info = find_video_output(outputs)
                    if video_info:
                        gen_info["status"] = "completed"
                        gen_info["output"] = video_info

                        # Copy to output directory
                        copy_video_to_output(video_info, generation_id)

                    return gen_info
                elif status.get('status_str') == 'error':
                    gen_info["status"] = "failed"
                    gen_info["error"] = status.get('messages', 'Unknown error')
                    return gen_info

        return gen_info

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        gen_info["status"] = "error"
        gen_info["error"] = str(e)
        return gen_info

@app.get("/api/generations")
async def list_generations():
    """List all generations"""
    return {"generations": generations}

def create_working_video_workflow(prompt, frames=16):
    """Create the proven working video workflow"""
    return {
        # Load checkpoint
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "anime_model_v25.safetensors"
            }
        },

        # Text encode positive
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": f"anime masterpiece, {prompt}, studio quality, 4k, detailed",
                "clip": ["1", 1]
            }
        },

        # Text encode negative
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "low quality, blurry, static, slideshow, bad anatomy",
                "clip": ["1", 1]
            }
        },

        # Empty latent for video frames
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": 512,
                "height": 512,
                "batch_size": frames
            }
        },

        # KSampler to generate frames
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "model": ["1", 0],
                "denoise": 1.0
            }
        },

        # VAE Decode
        "6": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["5", 0],
                "vae": ["1", 2]
            }
        },

        # Save as video
        "7": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["6", 0],
                "frame_rate": 8,
                "loop_count": 1,
                "filename_prefix": "anime_video",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True
            }
        }
    }

def find_video_output(outputs):
    """Find video file in ComfyUI outputs"""
    for node_id, node_output in outputs.items():
        if 'gifs' in node_output:
            for gif_info in node_output['gifs']:
                if gif_info.get('format') == 'video/h264-mp4':
                    return gif_info
    return None

def copy_video_to_output(video_info, generation_id):
    """Copy video to output directory"""
    try:
        source_path = video_info.get('fullpath')
        if source_path and os.path.exists(source_path):
            timestamp = int(time.time())
            filename = f"anime_professional_{generation_id}_{timestamp}.mp4"
            dest_path = OUTPUT_DIR / filename
            shutil.copy(source_path, dest_path)
            logger.info(f"Copied video to: {dest_path}")
            return str(dest_path)
    except Exception as e:
        logger.error(f"Failed to copy video: {e}")
    return None

# Simple test endpoint
@app.post("/api/generate")
async def generate_simple(request: Dict):
    """Simple generate endpoint"""
    anime_req = AnimeRequest(
        prompt=request.get("prompt", "magical anime scene"),
        character=request.get("character", "anime character"),
        frames=request.get("frames", 16)
    )
    return await generate_professional(anime_req)

if __name__ == "__main__":
    print("Starting Simple Anime Video Service on port 8328...")
    print(f"Output directory: {OUTPUT_DIR}")
    print("Using model: anime_model_v25.safetensors")
    uvicorn.run(app, host="127.0.0.1", port=8328)