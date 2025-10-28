#!/usr/bin/env python3
"""
KB-Compliant Anime Video Service
Generates REAL 30-second videos at 1920x1080
Not loops - actual unique content for each second
"""

import sys
import os
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import uvicorn
import requests
import uuid
import time
from pathlib import Path
import subprocess
import json
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import shutil

# Setup logging
log_dir = Path("/opt/tower-anime-production/logs")
log_dir.mkdir(exist_ok=True, parents=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler(
            log_dir / "kb_compliant_service.log",
            maxBytes=10_000_000,
            backupCount=5
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

app = FastAPI(title="KB-Compliant Anime Video Service", version="3.0.0")

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
OUTPUT_DIR = Path("/mnt/1TB-storage/ComfyUI/output")
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# KB Article 71 Requirements
KB_REQUIREMENTS = {
    "min_resolution_width": 1920,
    "min_resolution_height": 1080,
    "min_duration_seconds": 30,
    "frame_rate": 24,
    "min_bitrate_mbps": 10
}

class VideoGenerationRequest(BaseModel):
    prompt: str
    character: str = "anime character"
    duration: int = 30  # Default to KB minimum
    style: str = "anime masterpiece"
    quality_preset: str = "kb_standard"  # kb_standard, kb_target, quick_test

class GenerationStatus:
    """Track multi-segment generation progress"""

    def __init__(self):
        self.jobs = {}

    def create_job(self, job_id: str, total_segments: int):
        """Create a new generation job"""
        self.jobs[job_id] = {
            "id": job_id,
            "status": "initializing",
            "total_segments": total_segments,
            "completed_segments": 0,
            "current_segment": 0,
            "segment_ids": [],
            "segment_files": [],
            "progress_percent": 0,
            "message": "Initializing generation...",
            "started_at": datetime.now().isoformat(),
            "final_video": None,
            "error": None,
            "kb_compliant": False
        }

    def update_segment(self, job_id: str, segment_num: int, status: str, file_path: str = None):
        """Update segment progress"""
        if job_id not in self.jobs:
            return

        job = self.jobs[job_id]
        job["current_segment"] = segment_num

        if status == "completed" and file_path:
            job["completed_segments"] += 1
            job["segment_files"].append(file_path)

        job["progress_percent"] = int((job["completed_segments"] / job["total_segments"]) * 100)
        job["message"] = f"Segment {segment_num}/{job['total_segments']} - {status}"

    def complete_job(self, job_id: str, final_video: str, kb_compliant: bool):
        """Mark job as complete"""
        if job_id not in self.jobs:
            return

        job = self.jobs[job_id]
        job["status"] = "completed"
        job["final_video"] = final_video
        job["kb_compliant"] = kb_compliant
        job["progress_percent"] = 100
        job["message"] = "Generation complete!"
        job["completed_at"] = datetime.now().isoformat()

    def fail_job(self, job_id: str, error: str):
        """Mark job as failed"""
        if job_id not in self.jobs:
            return

        job = self.jobs[job_id]
        job["status"] = "failed"
        job["error"] = error
        job["message"] = f"Generation failed: {error}"

status_tracker = GenerationStatus()

def create_svd_segment_workflow(prompt: str, segment_num: int, total_segments: int, seed_base: int):
    """
    Create workflow for a single SVD segment (1 second)
    Varies prompts and parameters for each segment to create unique content
    """

    # Vary parameters per segment for diversity
    motion_variations = [127, 140, 160, 180, 200]
    motion_bucket = motion_variations[segment_num % len(motion_variations)]

    # Create scene variations
    scene_descriptions = [
        "wide shot", "close-up action", "dramatic angle", "aerial view", "ground level",
        "slow motion effect", "speed blur", "dynamic camera", "tracking shot", "panning view"
    ]
    scene_type = scene_descriptions[segment_num % len(scene_descriptions)]

    workflow = {
        "prompt": {
            # Load checkpoint
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "AOM3A1B.safetensors"}
            },

            # Unique prompt per segment
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": f"{prompt}, {scene_type}, sequence {segment_num}/{total_segments}, high quality anime",
                    "clip": ["1", 1]
                }
            },

            # Negative prompt
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "static, still image, no motion, blurry, low quality",
                    "clip": ["1", 1]
                }
            },

            # Empty latent
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": 1024,
                    "height": 576,
                    "batch_size": 1
                }
            },

            # Generate base image with unique seed
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed_base + (segment_num * 1000),
                    "steps": 30,
                    "cfg": 7.5,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                    "model": ["1", 0],
                    "denoise": 1.0
                }
            },

            # Decode base image
            "6": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["5", 0],
                    "vae": ["1", 2]
                }
            },

            # Load SVD model
            "7": {
                "class_type": "ImageOnlyCheckpointLoader",
                "inputs": {"ckpt_name": "svd_xt.safetensors"}
            },

            # SVD conditioning with varied motion
            "8": {
                "class_type": "SVD_img2vid_Conditioning",
                "inputs": {
                    "clip_vision": ["7", 1],
                    "init_image": ["6", 0],
                    "vae": ["7", 2],
                    "width": 1024,
                    "height": 576,
                    "video_frames": 25,
                    "motion_bucket_id": motion_bucket,
                    "fps": 24,
                    "augmentation_level": 0.0
                }
            },

            # Video CFG
            "9": {
                "class_type": "VideoLinearCFGGuidance",
                "inputs": {
                    "model": ["7", 0],
                    "min_cfg": 1.0
                }
            },

            # Generate video frames
            "10": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed_base + (segment_num * 2000),
                    "steps": 25,
                    "cfg": 2.5,
                    "sampler_name": "euler",
                    "scheduler": "karras",
                    "positive": ["8", 0],
                    "negative": ["8", 1],
                    "latent_image": ["8", 2],
                    "model": ["9", 0],
                    "denoise": 1.0
                }
            },

            # Decode video
            "11": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["10", 0],
                    "vae": ["7", 2]
                }
            },

            # Save segment
            "12": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["11", 0],
                    "frame_rate": 24.0,
                    "loop_count": 0,
                    "filename_prefix": f"kb_seg_{segment_num:03d}",
                    "format": "video/h264-mp4",
                    "crf": 18,
                    "pingpong": False,
                    "save_output": True
                }
            }
        }
    }

    return workflow

async def generate_kb_compliant_video(job_id: str, request: VideoGenerationRequest):
    """
    Generate a full KB-compliant video by chaining SVD segments
    """

    try:
        # Calculate segments needed
        total_segments = request.duration  # 1 second per segment
        status_tracker.create_job(job_id, total_segments)

        logger.info(f"Starting KB-compliant generation: {job_id}")
        logger.info(f"Target: {total_segments} segments = {request.duration} seconds")

        seed_base = int(time.time())
        segment_files = []

        # Generate each segment
        for segment_num in range(1, total_segments + 1):
            logger.info(f"[{job_id}] Generating segment {segment_num}/{total_segments}")
            status_tracker.update_segment(job_id, segment_num, "generating")

            # Create workflow
            workflow = create_svd_segment_workflow(
                request.prompt,
                segment_num,
                total_segments,
                seed_base
            )

            # Submit to ComfyUI
            response = requests.post(f"{COMFYUI_URL}/prompt", json=workflow)
            result = response.json()

            if 'prompt_id' not in result:
                error_msg = f"Segment {segment_num} submission failed: {result}"
                logger.error(error_msg)
                status_tracker.fail_job(job_id, error_msg)
                return

            prompt_id = result['prompt_id']
            logger.info(f"[{job_id}] Segment {segment_num} submitted: {prompt_id}")

            # Wait for completion (SVD takes about 60-90 seconds)
            max_wait = 180  # 3 minutes max per segment
            wait_time = 0
            segment_completed = False
            check_interval = 10  # Check every 10 seconds

            while wait_time < max_wait:
                await asyncio.sleep(check_interval)
                wait_time += check_interval

                # Check if file exists
                segment_pattern = f"kb_seg_{segment_num:03d}_*.mp4"
                segment_files_found = list(OUTPUT_DIR.glob(segment_pattern))

                if segment_files_found:
                    segment_file = segment_files_found[0]
                    segment_files.append(segment_file)
                    status_tracker.update_segment(job_id, segment_num, "completed", str(segment_file))
                    logger.info(f"[{job_id}] Segment {segment_num} completed: {segment_file.name}")
                    segment_completed = True
                    break

                # Check ComfyUI queue status
                try:
                    queue_response = requests.get(f"{COMFYUI_URL}/queue")
                    if queue_response.ok:
                        queue_data = queue_response.json()
                        if len(queue_data.get('queue_running', [])) == 0:
                            logger.warning(f"[{job_id}] ComfyUI queue empty but segment {segment_num} not found")
                except:
                    pass

            if not segment_completed:
                logger.warning(f"[{job_id}] Segment {segment_num} timed out")
                status_tracker.update_segment(job_id, segment_num, "timeout")

        # Combine all segments
        if len(segment_files) >= total_segments:
            logger.info(f"[{job_id}] Combining {len(segment_files)} segments...")

            # Create concat file
            concat_file = OUTPUT_DIR / f"concat_{job_id}.txt"
            with open(concat_file, 'w') as f:
                for seg in segment_files:
                    f.write(f"file '{seg}'\n")

            # Final output with upscaling to 1920x1080
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            final_output = OUTPUT_DIR / f"KB_COMPLIANT_{job_id}_{timestamp}.mp4"

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-vf", "scale=1920:1080:flags=lanczos",
                "-c:v", "libx264",
                "-crf", "18",
                "-preset", "slow",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(final_output)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                # Verify KB compliance
                kb_compliant = verify_kb_compliance(str(final_output))
                status_tracker.complete_job(job_id, str(final_output), kb_compliant)
                logger.info(f"[{job_id}] Generation complete! KB Compliant: {kb_compliant}")

                # Clean up segment files
                for seg in segment_files:
                    seg.unlink()
                concat_file.unlink()
            else:
                error_msg = f"FFmpeg failed: {result.stderr[:200]}"
                logger.error(error_msg)
                status_tracker.fail_job(job_id, error_msg)
        else:
            error_msg = f"Only {len(segment_files)}/{total_segments} segments generated"
            logger.error(error_msg)
            status_tracker.fail_job(job_id, error_msg)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{job_id}] Generation failed: {error_msg}")
        status_tracker.fail_job(job_id, error_msg)

def verify_kb_compliance(video_path: str) -> bool:
    """Verify if video meets KB Article 71 standards"""

    try:
        probe_cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            video_path
        ]

        result = subprocess.run(probe_cmd, capture_output=True, text=True)

        if result.stdout:
            info = json.loads(result.stdout)

            # Extract properties
            duration = float(info['format'].get('duration', 0))
            width = info['streams'][0].get('width', 0)
            height = info['streams'][0].get('height', 0)
            bitrate = int(info['format'].get('bit_rate', 0)) / 1_000_000  # Convert to Mbps

            # Check compliance
            compliant = (
                width >= KB_REQUIREMENTS["min_resolution_width"] and
                height >= KB_REQUIREMENTS["min_resolution_height"] and
                duration >= KB_REQUIREMENTS["min_duration_seconds"] and
                bitrate >= KB_REQUIREMENTS["min_bitrate_mbps"]
            )

            logger.info(f"KB Compliance Check: {width}x{height}, {duration}s, {bitrate:.1f}Mbps = {compliant}")
            return compliant

    except Exception as e:
        logger.error(f"Compliance check failed: {e}")

    return False

# API Endpoints

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "KB-Compliant Anime Video Service",
        "version": "3.0.0",
        "kb_requirements": KB_REQUIREMENTS,
        "comfyui_status": "connected" if requests.get(f"{COMFYUI_URL}/queue").ok else "disconnected"
    }

@app.post("/api/generate")
async def generate_video(request: VideoGenerationRequest, background_tasks: BackgroundTasks):
    """Generate KB-compliant video"""

    job_id = str(uuid.uuid4())[:8]

    # Start generation in background
    background_tasks.add_task(
        generate_kb_compliant_video,
        job_id,
        request
    )

    return {
        "job_id": job_id,
        "status": "started",
        "message": f"Generating {request.duration}-second KB-compliant video",
        "estimated_time": f"{request.duration * 1.5} minutes",
        "check_status_url": f"/api/status/{job_id}"
    }

@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    """Get generation status"""

    if job_id not in status_tracker.jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    return status_tracker.jobs[job_id]

@app.get("/api/download/{job_id}")
async def download_video(job_id: str):
    """Download completed video"""

    if job_id not in status_tracker.jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = status_tracker.jobs[job_id]

    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Video not ready")

    if not job["final_video"] or not Path(job["final_video"]).exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    return FileResponse(
        job["final_video"],
        media_type="video/mp4",
        filename=Path(job["final_video"]).name
    )

@app.get("/api/jobs")
async def list_jobs():
    """List all generation jobs"""
    return {
        "jobs": list(status_tracker.jobs.values()),
        "total": len(status_tracker.jobs)
    }

if __name__ == "__main__":
    print("=" * 60)
    print("KB-COMPLIANT ANIME VIDEO SERVICE v3.0")
    print("=" * 60)
    print(f"Requirements: {KB_REQUIREMENTS}")
    print(f"Output directory: {OUTPUT_DIR}")
    print("Starting service on port 8329...")

    uvicorn.run(app, host="127.0.0.1", port=8329)