#!/usr/bin/env python3
"""
Enhanced Anime API with Multi-Segment Video Generation
Integrates the multi-segment generator into the existing anime production system
"""

import os
import json
import asyncio
import time
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging

# Import our multi-segment generator
from multi_segment_video_generator import MultiSegmentVideoGenerator, generate_long_video_api

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Enhanced Tower Anime Production API", version="2.0.0")

class VideoRequest(BaseModel):
    prompt: str
    character_name: str = "Kai Nakamura"
    duration: float = 5.0
    quality: str = "standard"
    project_name: Optional[str] = None
    episode_number: Optional[int] = None

class VideoResponse(BaseModel):
    success: bool
    video_path: Optional[str] = None
    duration: Optional[float] = None
    segments: Optional[int] = None
    character: Optional[str] = None
    quality: Optional[str] = None
    generation_time: Optional[float] = None
    error: Optional[str] = None

@app.get("/")
async def root():
    """API health check"""
    return {
        "service": "Enhanced Tower Anime Production API",
        "version": "2.0.0",
        "status": "online",
        "features": [
            "Multi-segment video generation",
            "Character consistency",
            "VRAM-optimized workflow",
            "ffmpeg video splicing",
            "Quality presets"
        ]
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    try:
        # Check ComfyUI availability
        import requests
        comfyui_response = requests.get("http://127.0.0.1:8188/system_stats", timeout=5)
        comfyui_status = "online" if comfyui_response.status_code == 200 else "offline"
    except:
        comfyui_status = "offline"

    # Check output directory
    output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
    output_dir_status = "accessible" if output_dir.exists() and output_dir.is_dir() else "inaccessible"

    # Check ffmpeg
    try:
        import subprocess
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        ffmpeg_status = "available"
    except:
        ffmpeg_status = "missing"

    return {
        "status": "healthy",
        "components": {
            "comfyui": comfyui_status,
            "output_directory": output_dir_status,
            "ffmpeg": ffmpeg_status
        },
        "timestamp": time.time()
    }

@app.post("/generate_video", response_model=VideoResponse)
async def generate_video(request: VideoRequest):
    """
    Generate anime video with multi-segment support for longer durations

    Supports:
    - Videos from 1-30+ seconds
    - Character consistency across segments
    - Quality presets: fast, standard, high, ultra
    - Automatic VRAM management
    """
    try:
        start_time = time.time()

        logger.info(f"🎬 Generating video: {request.duration}s, {request.character_name}")

        # Validate inputs
        if request.duration <= 0 or request.duration > 60:
            raise HTTPException(status_code=400, detail="Duration must be between 0 and 60 seconds")

        if request.quality not in ["fast", "standard", "high", "ultra"]:
            raise HTTPException(status_code=400, detail="Quality must be: fast, standard, high, or ultra")

        # Generate output filename
        timestamp = int(time.time())
        if request.project_name:
            output_name = f"{request.project_name}_ep{request.episode_number or 1}_{timestamp}"
        else:
            output_name = f"anime_video_{timestamp}"

        # Generate video using multi-segment approach
        result = await generate_long_video_api(
            prompt=request.prompt,
            character_name=request.character_name,
            duration=request.duration,
            output_name=output_name,
            quality=request.quality
        )

        generation_time = time.time() - start_time

        if result["success"]:
            logger.info(f"✅ Video generated in {generation_time:.2f}s: {result['video_path']}")

            return VideoResponse(
                success=True,
                video_path=result["video_path"],
                duration=result["duration"],
                segments=result["segments"],
                character=result["character"],
                quality=result["quality"],
                generation_time=generation_time
            )
        else:
            logger.error(f"❌ Video generation failed: {result['error']}")
            raise HTTPException(status_code=500, detail=result["error"])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate_video_simple")
async def generate_video_simple(
    prompt: str,
    character: str = "Kai Nakamura",
    duration: float = 5.0,
    quality: str = "standard"
):
    """Simplified video generation endpoint"""

    request = VideoRequest(
        prompt=prompt,
        character_name=character,
        duration=duration,
        quality=quality
    )

    return await generate_video(request)

@app.get("/characters")
async def list_characters():
    """List available characters"""
    generator = MultiSegmentVideoGenerator()

    characters = {}
    for name, info in generator.characters.items():
        characters[name] = {
            "name": name,
            "description": info.get("appearance", ""),
            "style": info.get("style", "")
        }

    return {"characters": characters}

@app.get("/quality_presets")
async def list_quality_presets():
    """List available quality presets"""
    return {
        "presets": {
            "fast": {
                "description": "Quick generation, lower quality",
                "steps": 20,
                "resolution": "512x512",
                "estimated_time": "2-3 minutes per segment"
            },
            "standard": {
                "description": "Balanced quality and speed",
                "steps": 30,
                "resolution": "768x768",
                "estimated_time": "4-5 minutes per segment"
            },
            "high": {
                "description": "High quality, slower generation",
                "steps": 40,
                "resolution": "1024x1024",
                "estimated_time": "6-8 minutes per segment"
            },
            "ultra": {
                "description": "Maximum quality, longest generation",
                "steps": 50,
                "resolution": "1024x1024",
                "estimated_time": "8-12 minutes per segment"
            }
        }
    }

@app.get("/system_info")
async def system_info():
    """Get system information and limits"""
    return {
        "max_duration": 60,  # seconds
        "segment_duration": 5,  # seconds per segment
        "max_frames_per_segment": 120,
        "target_fps": 24,
        "output_directory": "/mnt/1TB-storage/ComfyUI/output",
        "temp_directory": "/tmp/anime_segments",
        "supported_formats": ["mp4"],
        "vram_optimization": "enabled"
    }

# Legacy compatibility endpoints
@app.post("/api/anime/generate")
async def legacy_generate(request: VideoRequest):
    """Legacy endpoint for backward compatibility"""
    return await generate_video(request)

@app.get("/api/anime/health")
async def legacy_health():
    """Legacy health check endpoint"""
    return await health_check()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8328)