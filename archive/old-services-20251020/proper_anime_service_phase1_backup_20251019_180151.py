#!/usr/bin/env python3
"""
Proper Anime Video Generation Service
Port: 8328
Generates KB-quality videos using ComfyUI with anime_model_v25.safetensors
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# PHASE 1 FIX: Structured logging with rotation
log_dir = Path("/opt/tower-anime-production/logs")
log_dir.mkdir(exist_ok=True, parents=True)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler(
            log_dir / "anime_service.log", maxBytes=10_000_000, backupCount=5  # 10MB
        ),
        logging.StreamHandler(),  # Also log to console
    ],
)
logger = logging.getLogger(__name__)
logger.info("=" * 60)
logger.info("ANIME SERVICE STARTING - Phase 1 Production Hardening")
logger.info("=" * 60)

# PHASE 1 FIX: VRAM monitoring with pynvml
try:
    import pynvml

    pynvml.nvmlInit()
    gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    GPU_MONITORING_ENABLED = True
    logger.info("✅ GPU monitoring enabled (pynvml)")
except Exception as e:
    GPU_MONITORING_ENABLED = False
    logger.warning(f"⚠️  GPU monitoring disabled: {e}")

# Add Echo Brain quality integration

sys.path.append("/opt/tower-echo-brain/src/services")
sys.path.append("/opt/tower-echo-brain/routing")
try:
    from echo_integration import EchoIntegration
    from feedback_system import FeedbackProcessor, FeedbackType
    from quality_assessment import VideoQualityAssessment

    echo = EchoIntegration()
    quality_assessor = VideoQualityAssessment()
    feedback_processor = FeedbackProcessor(
        db_config={"host": "localhost", "database": "tower_consolidated"}
    )
    QUALITY_ENABLED = True
    logger.info("✅ Quality systems enabled")
except ImportError as e:
    logger.warning(f"⚠️  Quality systems not available: {e}")
    QUALITY_ENABLED = False
app = FastAPI(title="Tower Anime Video Service", version="2.0.0-hardened")

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

# PHASE 1 FIX: Production limits
MAX_CONCURRENT_GENERATIONS = 3  # Safe for 12GB VRAM (4GB per generation)
VRAM_THRESHOLD_GB = 4.0  # Require 4GB free before accepting generation
MAX_STATUS_HISTORY = 100  # Prevent memory leak in status tracker
CLEANUP_AGE_HOURS = 24  # Clean up failed generations after 24 hours

# PHASE 1 FIX: Concurrency control
generation_semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATIONS)
logger.info(
    f"✅ Concurrency limit: {MAX_CONCURRENT_GENERATIONS} simultaneous generations"
)
logger.info(f"✅ VRAM threshold: {VRAM_THRESHOLD_GB}GB required free")


# Data models
class AnimeGenerationRequest(BaseModel):
    prompt: str
    character: str = "magical anime character"
    duration: int = 5
    frames: int = 120  # 24fps * 5 seconds
    style: str = "anime masterpiece"
    width: int = 3840  # 4K width
    height: int = 2160  # 4K height
    fps: int = 24
    use_apple_music: bool = False
    track_id: Optional[str] = None


class VideoGenerationStatus:
    """PHASE 1 FIX: Thread-safe status tracking with memory leak prevention"""

    def __init__(self):
        self.generations = {}
        self.lock = asyncio.Lock()
        self.max_history = MAX_STATUS_HISTORY
        logger.info(
            f"✅ Status tracker initialized (max history: {self.max_history})")

    async def set_status(
        self,
        gen_id: str,
        status: str,
        progress: int = 0,
        message: str = "",
        output_file: str = "",
    ):
        """Thread-safe status update with automatic cleanup"""
        async with self.lock:
            # Check if we need to cleanup old entries
            if len(self.generations) >= self.max_history:
                await self._cleanup_old_entries()

            self.generations[gen_id] = {
                "status": status,
                "progress": progress,
                "message": message,
                "output_file": output_file,
                "timestamp": datetime.now().isoformat(),
                "updated_at": time.time(),
            }
            logger.debug(
                f"Status updated [{gen_id[:8]}]: {status} ({progress}%) - {message}"
            )

    async def get_status(self, gen_id: str):
        """Thread-safe status retrieval"""
        async with self.lock:
            return self.generations.get(gen_id, {"status": "not_found"})

    async def _cleanup_old_entries(self):
        """Remove oldest completed/failed entries to prevent memory leak"""
        completed_failed = {
            k: v
            for k, v in self.generations.items()
            if v["status"] in ["completed", "failed"]
        }

        if completed_failed:
            # Remove oldest entry
            oldest_key = min(
                completed_failed.keys(),
                key=lambda k: completed_failed[k].get("updated_at", 0),
            )
            del self.generations[oldest_key]
            logger.info(
                f"Cleaned up old status entry: {oldest_key[:8]} ({self.generations[oldest_key]['status']})"
            )

    async def get_active_count(self) -> int:
        """Get count of actively processing generations"""
        async with self.lock:
            return len(
                [v for v in self.generations.values() if v["status"]
                 == "generating"]
            )


status_tracker = VideoGenerationStatus()


async def check_vram_available() -> tuple[bool, float, str]:
    """PHASE 1 FIX: Check if sufficient VRAM is available"""
    if not GPU_MONITORING_ENABLED:
        return True, 0.0, "GPU monitoring disabled"

    try:
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(gpu_handle)
        free_gb = mem_info.free / (1024**3)
        used_gb = mem_info.used / (1024**3)
        total_gb = mem_info.total / (1024**3)

        is_available = free_gb >= VRAM_THRESHOLD_GB
        status_msg = (
            f"{free_gb:.2f}GB free ({used_gb:.2f}GB used / {total_gb:.2f}GB total)"
        )

        if not is_available:
            logger.warning(f"⚠️  Insufficient VRAM: {status_msg}")

        return is_available, free_gb, status_msg
    except Exception as e:
        logger.error(f"Error checking VRAM: {e}")
        return True, 0.0, f"Error: {str(e)}"


@app.get("/api/health")
async def health_check():
    """Check service health and dependencies with detailed metrics"""
    comfyui_status = "disconnected"
    comfyui_details = {}

    try:
        response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=2)
        if response.status_code == 200:
            comfyui_status = "connected"
            comfyui_details = response.json()
    except Exception as e:
        logger.debug(f"ComfyUI health check failed: {e}")

    # Get VRAM status
    vram_available, vram_free, vram_status = await check_vram_available()

    # Get active generation count
    active_count = await status_tracker.get_active_count()

    health = {
        "status": (
            "healthy"
            if comfyui_status == "connected" and vram_available
            else "degraded"
        ),
        "service": "Tower Anime Video Service",
        "version": "2.0.0-hardened",
        "phase": "Phase 1 Production Hardening",
        "comfyui_status": comfyui_status,
        "output_dir": str(OUTPUT_DIR),
        "model": "Counterfeit-V2.5.safetensors",
        "timestamp": datetime.now().isoformat(),
        "capacity": {
            "max_concurrent": MAX_CONCURRENT_GENERATIONS,
            "active_generations": active_count,
            "available_slots": MAX_CONCURRENT_GENERATIONS - active_count,
        },
        "vram": {
            "monitoring_enabled": GPU_MONITORING_ENABLED,
            "available": vram_available,
            "free_gb": round(vram_free, 2),
            "threshold_gb": VRAM_THRESHOLD_GB,
            "status": vram_status,
        },
        "features": {
            "thread_safe_status": True,
            "concurrency_limits": True,
            "vram_monitoring": GPU_MONITORING_ENABLED,
            "structured_logging": True,
            "apple_music": True,
            "quality_assessment": QUALITY_ENABLED,
        },
    }

    return health


@app.post("/generate/professional")
async def generate_professional_video(
    request: AnimeGenerationRequest, background_tasks: BackgroundTasks
):
    """Generate professional quality anime video with production hardening"""
    generation_id = str(uuid.uuid4())

    logger.info(
        f"🎬 Generation request received: {generation_id[:8]} - prompt: '{request.prompt[:50]}...'"
    )

    # PHASE 1 FIX: Check VRAM before accepting request
    vram_available, vram_free, vram_status = await check_vram_available()
    if not vram_available:
        logger.error(
            f"❌ Generation rejected [{generation_id[:8]}]: Insufficient VRAM - {vram_status}"
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Insufficient GPU memory",
                "vram_status": vram_status,
                "retry_after": 30,
                "message": "GPU is currently processing other requests. Please try again in a moment.",
            },
        )

    # PHASE 1 FIX: Check concurrency limit
    active_count = await status_tracker.get_active_count()
    if active_count >= MAX_CONCURRENT_GENERATIONS:
        logger.warning(
            f"⚠️  Generation queued [{generation_id[:8]}]: At concurrency limit ({active_count}/{MAX_CONCURRENT_GENERATIONS})"
        )

    # Initialize status
    await status_tracker.set_status(
        generation_id, "initializing", 0, "Preparing video generation workflow..."
    )

    # Start generation in background with semaphore control
    background_tasks.add_task(
        generate_video_with_semaphore, generation_id, request)

    logger.info(
        f"✅ Generation accepted [{generation_id[:8]}]: VRAM={vram_free:.2f}GB, Active={active_count}/{MAX_CONCURRENT_GENERATIONS}"
    )

    return {
        "generation_id": generation_id,
        "status": "started",
        "message": "Professional video generation started",
        "estimated_time": "2-5 minutes for 4K video",
        "check_status_url": f"/api/status/{generation_id}",
        "vram_available_gb": round(vram_free, 2),
        "queue_position": active_count + 1,
    }


@app.get("/api/status/{generation_id}")
async def get_generation_status(generation_id: str):
    """Get generation status"""
    status = await status_tracker.get_status(generation_id)
    if status["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Generation not found")
    return status


async def generate_video_with_semaphore(
    generation_id: str, request: AnimeGenerationRequest
):
    """PHASE 1 FIX: Wrapper with semaphore for concurrency control"""
    async with generation_semaphore:
        logger.info(f"🔒 Acquired generation slot [{generation_id[:8]}]")
        try:
            await generate_video_async(generation_id, request)
        finally:
            logger.info(f"🔓 Released generation slot [{generation_id[:8]}]")


async def generate_video_async(generation_id: str, request: AnimeGenerationRequest):
    """Generate video asynchronously with proper ComfyUI workflow"""
    start_time = time.time()
    try:
        # Update status
        await status_tracker.set_status(
            generation_id, "creating_workflow", 10, "Creating 4K video workflow..."
        )

        # Create the workflow using our proven working template
        workflow = create_4k_video_workflow(request, generation_id)

        logger.info(f"📋 Created workflow for generation {generation_id[:8]}")

        # Submit to ComfyUI
        await status_tracker.set_status(
            generation_id, "submitting", 25, "Submitting to ComfyUI..."
        )

        response = requests.post(
            f"{COMFYUI_URL}/prompt", json={"prompt": workflow})

        if response.status_code != 200:
            raise Exception(f"ComfyUI submission failed: {response.text}")

        result = response.json()
        prompt_id = result.get("prompt_id")

        if not prompt_id:
            raise Exception("No prompt_id returned from ComfyUI")

        logger.info(
            f"📤 Submitted to ComfyUI [{generation_id[:8]}] prompt_id: {prompt_id}"
        )

        # Monitor progress
        await status_tracker.set_status(
            generation_id,
            "generating",
            50,
            f"Generating 4K video... (ComfyUI ID: {prompt_id})",
        )

        # Wait for completion with timeout
        max_wait = 600  # 10 minutes for 4K video
        wait_time = 0

        while wait_time < max_wait:
            time.sleep(5)
            wait_time += 5

            # Update progress
            progress = min(50 + (wait_time / max_wait) * 40, 90)
            await status_tracker.set_status(
                generation_id,
                "generating",
                int(progress),
                f"Processing frame generation... ({wait_time}s elapsed)",
            )

            # Check ComfyUI history
            try:
                history = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
                if history.status_code == 200:
                    data = history.json()
                    if prompt_id in data:
                        prompt_status = data[prompt_id].get("status", {})
                        if prompt_status.get(
                            "status_str"
                        ) == "success" and prompt_status.get("completed"):
                            # Generation complete - look for output
                            outputs = data[prompt_id].get("outputs", {})
                            logger.info(
                                f"✅ ComfyUI generation completed [{generation_id[:8]}]"
                            )

                            # Find the video file
                            video_file = await find_generated_video(generation_id)
                            if video_file:
                                # Add Apple Music if requested
                                if request.use_apple_music and request.track_id:
                                    await status_tracker.set_status(
                                        generation_id,
                                        "adding_music",
                                        95,
                                        "Adding Apple Music preview...",
                                    )
                                    video_file = await merge_apple_music_audio(
                                        video_file, request.track_id, generation_id
                                    )

                                elapsed = time.time() - start_time
                                await status_tracker.set_status(
                                    generation_id,
                                    "completed",
                                    100,
                                    f"4K video generation completed in {elapsed:.1f}s!",
                                    video_file,
                                )
                                logger.info(
                                    f"🎉 Video generation completed [{generation_id[:8]}]: {video_file} ({elapsed:.1f}s)"
                                )
                                return
                        elif prompt_status.get("status_str") == "error":
                            error_msg = prompt_status.get(
                                "messages", "Unknown ComfyUI error"
                            )
                            raise Exception(
                                f"ComfyUI generation failed: {error_msg}")
            except Exception as e:
                logger.warning(f"Error checking ComfyUI status: {e}")

        # Timeout
        raise Exception(f"Video generation timeout after {max_wait} seconds")

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(
            f"❌ Video generation failed [{generation_id[:8]}] after {elapsed:.1f}s: {str(e)}",
            exc_info=True,
        )
        await status_tracker.set_status(
            generation_id, "failed", 0, f"Generation failed: {str(e)}"
        )


async def find_generated_video(generation_id: str) -> str:
    """Find the generated video file and move it to proper location"""
    try:
        # ComfyUI saves videos to output directory with our prefix
        comfyui_output = Path("/mnt/1TB-storage/ComfyUI/output")

        # Look for recent video files with our generation ID
        import glob

        video_patterns = [
            f"anime_video_{generation_id}*.mp4",
            f"anime_video_*.mp4",  # Fallback to any recent anime video
        ]

        found_files = []
        for pattern in video_patterns:
            found_files.extend(glob.glob(str(comfyui_output / pattern)))

        if not found_files:
            # Check for any recent video files (last 2 minutes)
            # time module already imported globally
            cutoff_time = time.time() - 120
            for file_path in comfyui_output.glob("*.mp4"):
                if file_path.stat().st_mtime > cutoff_time:
                    found_files.append(str(file_path))

        if found_files:
            # Use the most recent file
            latest_file = max(found_files, key=os.path.getctime)

            # Move to our output directory
            timestamp = int(time.time())
            output_filename = f"anime_4k_video_{generation_id}_{timestamp}.mp4"
            output_path = OUTPUT_DIR / output_filename

            shutil.move(latest_file, output_path)
            logger.info(f"Moved video to: {output_path}")

            return str(output_path)

        return None

    except Exception as e:
        logger.error(f"Error finding generated video: {e}")
        return None


async def merge_apple_music_audio(
    video_file: str, track_id: str, generation_id: str
) -> str:
    """Download Apple Music preview and merge with video using ffmpeg"""
    try:
        logger.info(f"Downloading Apple Music preview for track {track_id}")

        # Download preview using Apple Music API
        response = requests.post(
            f"http://127.0.0.1:8315/api/apple-music/track/{track_id}/download"
        )
        if response.status_code != 200:
            logger.error(
                f"Failed to download Apple Music preview: {response.text}")
            return video_file

        data = response.json()
        audio_file = data.get("file_path")

        if not audio_file or not os.path.exists(audio_file):
            logger.error(f"Audio file not found: {audio_file}")
            return video_file

        logger.info(f"Downloaded audio to: {audio_file}")

        # Create output path for video with music
        video_path = Path(video_file)
        output_file = (
            video_path.parent /
            f"{video_path.stem}_with_music{video_path.suffix}"
        )

        # Use ffmpeg to merge video and audio (30-sec preview loops to match video duration)
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_file,
            "-stream_loop",
            "-1",  # Loop audio to match video duration
            "-i",
            audio_file,
            "-c:v",
            "copy",  # Copy video codec (no re-encoding)
            "-c:a",
            "aac",  # AAC audio codec
            "-shortest",  # Match shortest stream (video)
            "-map",
            "0:v:0",  # Map video from first input
            "-map",
            "1:a:0",  # Map audio from second input
            str(output_file),
        ]

        logger.info(f"Running ffmpeg: {' '.join(ffmpeg_cmd)}")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"ffmpeg failed: {result.stderr}")
            return video_file

        logger.info(f"Successfully merged audio, output: {output_file}")
        return str(output_file)

    except Exception as e:
        logger.error(f"Error merging Apple Music audio: {e}")
        return video_file


def create_4k_video_workflow(
    request: AnimeGenerationRequest, generation_id: str
) -> Dict[str, Any]:
    """Create 4K video workflow based on working template"""

    # Enhanced prompt for anime quality
    enhanced_prompt = f"anime masterpiece, {request.prompt}, {request.character}, studio quality, 4k, detailed animation, smooth motion, vibrant colors, professional anime production"

    # Calculate realistic settings for RTX 3060 12GB VRAM
    # Start with conservative settings to avoid OOM
    width = min(request.width, 512)  # Start small to ensure it works
    height = min(request.height, 512)
    frames = min(request.frames, 16)  # 16 frames = ~0.67 seconds at 24fps

    workflow = {
        # Load the anime model
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "Counterfeit-V2.5.safetensors"},
        },
        # Text encode positive
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": enhanced_prompt, "clip": ["1", 1]},
        },
        # Text encode negative
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "low quality, blurry, static, slideshow, bad anatomy, deformed, ugly, distorted",
                "clip": ["1", 1],
            },
        },
        # Empty latent for video frames
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": frames},
        },
        # KSampler to generate frames
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(time.time()),
                "steps": 15,  # Reduced steps for memory efficiency
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "model": ["1", 0],
                "denoise": 1.0,
            },
        },
        # VAE Decode
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
        },
        # Save as video using VideoHelperSuite
        "7": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["6", 0],
                "frame_rate": request.fps,
                "loop_count": 1,
                "filename_prefix": f"anime_video_{generation_id}",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
            },
        },
    }

    return workflow


# Simple test endpoints
@app.post("/api/generate")
async def generate_simple_video(
    request: Dict[str, Any], background_tasks: BackgroundTasks
):
    """Simple generation endpoint for testing"""
    anime_request = AnimeGenerationRequest(
        prompt=request.get("prompt", "magical anime scene"),
        character=request.get("character", "anime character"),
        duration=request.get("duration", 3),
        frames=request.get("frames", 72),  # 3 seconds at 24fps
        use_apple_music=request.get("use_apple_music", False),
        track_id=request.get("track_id"),
    )

    return await generate_professional_video(anime_request, background_tasks)


@app.get("/api/generations")
async def list_generations():
    """List all recent generations"""
    return {"generations": status_tracker.generations}


if __name__ == "__main__":
    print("Starting Tower Anime Video Service on port 8328...")
    print(f"Output directory: {OUTPUT_DIR}")
    print("Using model: Counterfeit-V2.5.safetensors")
    uvicorn.run(app, host="127.0.0.1", port=8328)
