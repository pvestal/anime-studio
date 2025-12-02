#!/usr/bin/env python3
"""
Validated anime generation API with LLaVA quality control.
Ensures single-subject portraits and anatomically correct images.
"""

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Dict, Optional
import aiofiles
import aiohttp
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

from llava_validator import LLaVAValidator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
COMFYUI_URL = "http://localhost:8188"
OUTPUT_DIR = "/mnt/1TB-storage/ComfyUI/output"
MAX_RETRIES = 3  # Maximum attempts if validation fails

app = FastAPI(title="Validated Anime Generation API")
validator = LLaVAValidator()


class GenerationRequest(BaseModel):
    prompt: str
    character: Optional[str] = "original"
    style: Optional[str] = "soft_lighting"
    mode: str = "portrait"  # portrait, group, scene
    expected_subjects: int = 1  # How many people should be in the image
    negative_prompt: Optional[str] = None


class SingleSubjectWorkflow:
    """ComfyUI workflow specifically optimized for single subject generation."""

    @staticmethod
    def create(prompt: str, negative_prompt: str = None) -> Dict:
        """Create workflow that strongly enforces single subject."""

        # Enhanced negative prompt to prevent multiple subjects
        default_negative = (
            "multiple people, crowd, group, duo, pair, twins, "
            "multiple characters, multiple faces, extra person, "
            "extra body, extra limbs, extra arms, extra legs, "
            "extra hands, extra feet, extra fingers, "
            "deformed, ugly, mutilated, disfigured, "
            "mutation, bad anatomy, bad proportions, "
            "clone, duplicate, copy, mirror image"
        )

        if negative_prompt:
            negative_prompt = f"{negative_prompt}, {default_negative}"
        else:
            negative_prompt = default_negative

        # Add single subject enforcement to positive prompt
        enhanced_prompt = f"solo, single person, one character only, {prompt}"

        workflow = {
            "3": {
                "inputs": {
                    "seed": int(time.time()),
                    "steps": 28,
                    "cfg": 7.5,
                    "sampler_name": "dpmpp_2m_sde",
                    "scheduler": "karras",
                    "denoise": 1,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler",
                "_meta": {"title": "KSampler"}
            },
            "4": {
                "inputs": {
                    "ckpt_name": "Counterfeit-V2.5.safetensors"
                },
                "class_type": "CheckpointLoaderSimple",
                "_meta": {"title": "Load Checkpoint"}
            },
            "5": {
                "inputs": {
                    "width": 512,
                    "height": 768,  # Portrait orientation
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage",
                "_meta": {"title": "Empty Latent Image"}
            },
            "6": {
                "inputs": {
                    "text": enhanced_prompt,
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Positive Prompt"}
            },
            "7": {
                "inputs": {
                    "text": negative_prompt,
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Negative Prompt"}
            },
            "8": {
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                },
                "class_type": "VAEDecode",
                "_meta": {"title": "VAE Decode"}
            },
            "9": {
                "inputs": {
                    "filename_prefix": f"validated_{int(time.time())}",
                    "images": ["8", 0]
                },
                "class_type": "SaveImage",
                "_meta": {"title": "Save Image"}
            }
        }

        return workflow


async def generate_with_validation(request: GenerationRequest) -> Dict:
    """Generate image with LLaVA validation and retry logic."""

    attempt = 0
    last_issues = []

    while attempt < MAX_RETRIES:
        attempt += 1
        logger.info(f"🎨 Generation attempt {attempt}/{MAX_RETRIES} for {request.mode}")

        # Create workflow based on mode
        if request.mode == "portrait":
            workflow = SingleSubjectWorkflow.create(
                prompt=request.prompt,
                negative_prompt=request.negative_prompt
            )
        else:
            # For now, use same workflow for all modes
            workflow = SingleSubjectWorkflow.create(
                prompt=request.prompt,
                negative_prompt=request.negative_prompt
            )

        # Generate the image
        async with aiohttp.ClientSession() as session:
            prompt_id = str(uuid.uuid4())

            # Submit workflow
            async with session.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow, "client_id": prompt_id}
            ) as resp:
                if resp.status != 200:
                    raise HTTPException(500, f"ComfyUI error: {resp.status}")

                result = await resp.json()
                prompt_id = result.get("prompt_id")

            # Wait for completion
            logger.info(f"⏳ Waiting for generation {prompt_id}")
            await asyncio.sleep(6)  # Typical generation time

            # Get history to find output
            async with session.get(
                f"{COMFYUI_URL}/history/{prompt_id}"
            ) as resp:
                history = await resp.json()

            # Find the output file
            if prompt_id not in history:
                logger.error(f"Generation {prompt_id} not found in history")
                continue

            outputs = history[prompt_id].get("outputs", {})
            image_file = None

            for node_id, node_output in outputs.items():
                if "images" in node_output:
                    for img in node_output["images"]:
                        image_file = img["filename"]
                        break
                    if image_file:
                        break

            if not image_file:
                logger.error("No output image found")
                continue

            image_path = Path(OUTPUT_DIR) / image_file

            # Validate with LLaVA
            logger.info(f"🔍 Validating generated image: {image_file}")
            validation = validator.analyze_image(
                str(image_path),
                expected_subject_count=request.expected_subjects
            )

            if validation["valid"]:
                logger.info(f"✅ Image passed validation!")
                return {
                    "status": "success",
                    "image": str(image_path),
                    "filename": image_file,
                    "validation": validation,
                    "attempts": attempt,
                    "generation_time": 6
                }
            else:
                logger.warning(
                    f"❌ Validation failed: {validation.get('anatomical_issues', [])}"
                )
                last_issues = validation.get('anatomical_issues', [])

                # Enhance negative prompt based on issues found
                if "multiple" in str(last_issues).lower():
                    request.negative_prompt = (
                        f"{request.negative_prompt}, "
                        "multiple people, group photo, crowd"
                    ) if request.negative_prompt else (
                        "multiple people, group photo, crowd"
                    )

                # Continue to next attempt
                continue

    # All retries exhausted
    return {
        "status": "failed",
        "error": "Failed validation after maximum retries",
        "last_issues": last_issues,
        "attempts": attempt
    }


@app.post("/api/generate")
async def generate_image(request: GenerationRequest):
    """Generate anime image with quality validation."""

    logger.info(f"📝 Received request: {request.prompt[:50]}...")

    try:
        result = await generate_with_validation(request)
        return result
    except Exception as e:
        logger.error(f"Generation error: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/health")
async def health_check():
    """Check API health and dependencies."""

    # Check ComfyUI
    comfyui_ok = False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{COMFYUI_URL}/system_stats", timeout=2) as resp:
                comfyui_ok = resp.status == 200
    except:
        pass

    # Check Ollama/LLaVA
    llava_ok = False
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=2)
        models = resp.json().get("models", [])
        llava_ok = any("llava" in m.get("name", "") for m in models)
    except:
        pass

    return {
        "status": "healthy" if (comfyui_ok and llava_ok) else "degraded",
        "services": {
            "comfyui": "✅" if comfyui_ok else "❌",
            "llava": "✅" if llava_ok else "❌"
        },
        "message": "Validated Generation API with LLaVA QC"
    }


@app.post("/api/validate")
async def validate_image(image_path: str, expected_subjects: int = 1):
    """Validate an existing image."""

    result = validator.analyze_image(image_path, expected_subjects)
    return result


if __name__ == "__main__":
    import uvicorn

    print("🚀 Starting Validated Anime Generation API")
    print("📍 Port: 8332")
    print("🔍 LLaVA validation enabled")
    print("🔁 Max retries: 3")

    uvicorn.run(app, host="0.0.0.0", port=8332)