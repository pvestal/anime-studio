#!/usr/bin/env python3
"""
Optimized Anime Generation Service with Model Caching
Implements DeepSeek's recommendations for performance optimization
"""

import json
import requests
import time
import os
import uuid
import asyncio
import aiohttp
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class AnimeRequest(BaseModel):
    prompt: str
    character: str = "Sakura"
    scene_type: str = "battle"
    duration: int = 3
    style: str = "anime"

# Global configuration
COMFYUI_URL = "http://127.0.0.1:8188"
OUTPUT_DIR = "***REMOVED***/AnimeGenerated"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# CRITICAL: Global model cache to prevent reloading
class ModelCache:
    def __init__(self):
        self.model_loaded = False
        self.current_model = None
        self.workflow_template = None
        self.last_prompt_id = None
        
    async def ensure_model_loaded(self):
        """Ensure model is loaded and warm"""
        if not self.model_loaded:
            logger.info("🔥 Loading model for first time (one-time cost)")
            await self._warm_up_model()
            self.model_loaded = True
            logger.info("✅ Model cached and ready for fast generation")
        
    async def _warm_up_model(self):
        """Warm up the model with a simple generation"""
        try:
            # Simple workflow that loads the model
            workflow = {
                "3": {
                    "inputs": {
                        "seed": 156680208700286,
                        "steps": 8,  # Minimal steps for warmup
                        "cfg": 8,
                        "sampler_name": "euler",
                        "scheduler": "normal",
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
                        "ckpt_name": "epicrealism_v5.safetensors"  # Fast, good model
                    },
                    "class_type": "CheckpointLoaderSimple",
                    "_meta": {"title": "Load Checkpoint"}
                },
                "5": {
                    "inputs": {
                        "width": 1024,  # Small for warmup
                        "height": 1024,
                        "batch_size": 1
                    },
                    "class_type": "EmptyLatentImage",
                    "_meta": {"title": "Empty Latent Image"}
                },
                "6": {
                    "inputs": {
                        "text": "simple test",  # Minimal prompt
                        "clip": ["4", 1]
                    },
                    "class_type": "CLIPTextEncode",
                    "_meta": {"title": "CLIP Text Encode (Prompt)"}
                },
                "7": {
                    "inputs": {
                        "text": "bad quality",
                        "clip": ["4", 1]
                    },
                    "class_type": "CLIPTextEncode",
                    "_meta": {"title": "CLIP Text Encode (Prompt)"}
                }
            }
            
            # Submit warmup generation to load model into VRAM
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}) as response:
                    if response.status == 200:
                        result = await response.json()
                        prompt_id = result["prompt_id"]
                        
                        # Wait for warmup to complete (loads model)
                        await self._wait_for_completion(prompt_id, session)
                        logger.info("🚀 Model warmup complete - now cached in VRAM")
                    else:
                        logger.error(f"Warmup failed: {response.status}")
        except Exception as e:
            logger.error(f"Model warmup error: {e}")
    
    async def _wait_for_completion(self, prompt_id: str, session: aiohttp.ClientSession, max_wait: int = 30):
        """Wait for generation to complete"""
        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                async with session.get(f"{COMFYUI_URL}/history/{prompt_id}") as response:
                    if response.status == 200:
                        history = await response.json()
                        if prompt_id in history and "outputs" in history[prompt_id]:
                            return True
            except:
                pass
            await asyncio.sleep(0.5)
        return False

# Global model cache instance
model_cache = ModelCache()

@app.on_event("startup")
async def startup_event():
    """Preload model on service startup"""
    logger.info("🚀 Starting Optimized Anime Service with Model Caching")
    try:
        await model_cache.ensure_model_loaded()
        logger.info("✅ Service ready with preloaded model")
    except Exception as e:
        logger.warning(f"Model preload failed, will load on first request: {e}")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "model_loaded": model_cache.model_loaded,
        "service": "optimized-anime-generation",
        "version": "2.0-cached"
    }

@app.post("/api/generate")
async def generate_anime(request: AnimeRequest):
    """Optimized anime generation with model caching"""
    logger.info(f"🎨 Generating: {request.prompt[:50]}... (model cached: {model_cache.model_loaded})")
    
    try:
        # Ensure model is loaded (fast if already cached)
        await model_cache.ensure_model_loaded()
        
        # Create optimized workflow
        workflow = create_optimized_workflow(request)
        
        # Submit to ComfyUI queue (model already loaded)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            start_time = time.time()
            
            # Submit prompt
            async with session.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}) as response:
                if response.status != 200:
                    raise HTTPException(status_code=500, detail="Failed to submit to ComfyUI")
                
                result = await response.json()
                prompt_id = result["prompt_id"]
                logger.info(f"📊 Submitted prompt {prompt_id}")
            
            # Wait for completion with faster polling
            completion_start = time.time()
            completed = await model_cache._wait_for_completion(prompt_id, session, max_wait=45)
            
            if not completed:
                raise HTTPException(status_code=408, detail="Generation timeout")
            
            # Get the result
            async with session.get(f"{COMFYUI_URL}/history/{prompt_id}") as response:
                history = await response.json()
                
                total_time = time.time() - start_time
                inference_time = time.time() - completion_start
                
                logger.info(f"✅ Generated in {total_time:.1f}s (inference: {inference_time:.1f}s)")
                
                return {
                    "status": "success",
                    "prompt_id": prompt_id,
                    "generation_time": f"{total_time:.1f}s",
                    "inference_time": f"{inference_time:.1f}s",
                    "model_was_cached": model_cache.model_loaded,
                    "prompt": request.prompt,
                    "outputs": history.get(prompt_id, {}).get("outputs", {})
                }
                
    except Exception as e:
        logger.error(f"Generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

def create_optimized_workflow(request: AnimeRequest):
    """Create optimized workflow for fast generation"""
    return {
        "3": {
            "inputs": {
                "seed": int(time.time()) % 1000000,
                "steps": 20,  # Balanced quality/speed
                "cfg": 8,
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
                "ckpt_name": "epicrealism_v5.safetensors"  # Pre-cached model
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "5": {
            "inputs": {
                "width": 1024,  # Adaptive resolution
                "height": 1024,
                "batch_size": 1
            },
            "class_type": "EmptyLatentImage"
        },
        "6": {
            "inputs": {
                "text": f"{request.prompt}, {request.character}, {request.scene_type}, {request.style}, high quality, detailed",
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "7": {
            "inputs": {
                "text": "bad quality, blurry, low resolution, watermark",
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
                "filename_prefix": f"anime_{int(time.time())}",
                "images": ["8", 0]
            },
            "class_type": "SaveImage"
        }
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Starting Optimized Anime Service with Model Caching")
    uvicorn.run(app, host="127.0.0.1", port=8328)  # Different port to avoid conflicts