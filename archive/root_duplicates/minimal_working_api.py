#!/usr/bin/env python3
"""
Minimal Working Anime API
Based on PROVEN direct ComfyUI integration (16s generation)
NO Echo Brain technical guidance, NO 1800-line monoliths
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import json
import time
import uuid
import glob
import os
from typing import Optional

app = FastAPI(title="Minimal Working Anime API", version="1.0.0")

class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = "blurry, low quality, multiple body parts, distorted"
    width: int = 768
    height: int = 768
    steps: int = 15

class GenerateResponse(BaseModel):
    success: bool
    job_id: str
    status: str
    image_path: Optional[str] = None
    generation_time: Optional[float] = None
    error: Optional[str] = None

# Available models (REAL ones, not Echo fabrications)
AVAILABLE_MODELS = [
    "Counterfeit-V2.5.safetensors",
    "counterfeit_v3.safetensors",
    "juggernautXL_v9.safetensors"
]

def create_comfyui_workflow(prompt: str, negative_prompt: str, width: int, height: int, steps: int) -> dict:
    """Create REAL ComfyUI workflow with ACTUAL available models"""
    return {
        "1": {
            "inputs": {"ckpt_name": AVAILABLE_MODELS[0]},  # Use verified model
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {
                "text": f"{prompt}, anime, high quality, detailed",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "3": {
            "inputs": {
                "text": negative_prompt,
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "4": {
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1
            },
            "class_type": "EmptyLatentImage"
        },
        "5": {
            "inputs": {
                "seed": int(time.time()),
                "steps": steps,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0]
            },
            "class_type": "KSampler"
        },
        "6": {
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            "class_type": "VAEDecode"
        },
        "7": {
            "inputs": {
                "images": ["6", 0],
                "filename_prefix": f"minimal_api_{int(time.time())}"
            },
            "class_type": "SaveImage"
        }
    }

@app.post("/generate", response_model=GenerateResponse)
async def generate_image(request: GenerateRequest):
    """Generate anime image using PROVEN direct ComfyUI integration"""

    client_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        # Create workflow with REAL models (not Echo fabrications)
        workflow = create_comfyui_workflow(
            request.prompt,
            request.negative_prompt,
            request.width,
            request.height,
            request.steps
        )

        # Submit to ComfyUI
        response = requests.post(
            "http://localhost:8188/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=10
        )

        if response.status_code != 200:
            return GenerateResponse(
                success=False,
                job_id=client_id,
                status="failed",
                error=f"ComfyUI submission failed: {response.text}"
            )

        result = response.json()
        prompt_id = result.get("prompt_id")

        # Wait for completion with realistic timeout
        timeout = 60  # 1 minute max (proven: direct takes ~16s)
        check_interval = 2

        for attempt in range(timeout // check_interval):
            time.sleep(check_interval)

            # Check ComfyUI history
            history_response = requests.get(f"http://localhost:8188/history/{prompt_id}")

            if history_response.status_code == 200:
                history = history_response.json()

                if prompt_id in history:
                    job_info = history[prompt_id]
                    status = job_info.get("status", {})

                    if status.get("status_str") == "success":
                        generation_time = time.time() - start_time

                        # Find output file
                        output_files = glob.glob(f"/mnt/1TB-storage/ComfyUI/output/minimal_api_{int(start_time)}_*.png")

                        if output_files:
                            image_path = max(output_files, key=os.path.getctime)

                            return GenerateResponse(
                                success=True,
                                job_id=client_id,
                                status="completed",
                                image_path=image_path,
                                generation_time=generation_time
                            )
                        else:
                            return GenerateResponse(
                                success=False,
                                job_id=client_id,
                                status="failed",
                                error="Generation completed but no output file found"
                            )

                    elif "error" in status:
                        return GenerateResponse(
                            success=False,
                            job_id=client_id,
                            status="failed",
                            error=str(status.get("error"))
                        )

        # Timeout
        return GenerateResponse(
            success=False,
            job_id=client_id,
            status="timeout",
            error="Generation timed out after 60 seconds"
        )

    except Exception as e:
        return GenerateResponse(
            success=False,
            job_id=client_id,
            status="error",
            error=str(e)
        )

@app.get("/health")
async def health_check():
    """Health check with ComfyUI verification"""
    try:
        response = requests.get("http://localhost:8188/system_stats", timeout=5)
        comfyui_working = response.status_code == 200

        return {
            "status": "healthy" if comfyui_working else "degraded",
            "comfyui_connected": comfyui_working,
            "available_models": AVAILABLE_MODELS
        }
    except:
        return {
            "status": "unhealthy",
            "comfyui_connected": False,
            "error": "Cannot connect to ComfyUI"
        }

@app.get("/models")
async def list_models():
    """List REAL available models (not Echo fabrications)"""
    return {"models": AVAILABLE_MODELS}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting MINIMAL WORKING Anime API")
    print("✅ Based on PROVEN direct ComfyUI integration")
    print("❌ NO Echo Brain technical guidance")
    print("❌ NO 1800-line monoliths")
    uvicorn.run(app, host="0.0.0.0", port=8331)