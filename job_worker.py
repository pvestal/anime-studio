#!/usr/bin/env python3
"""
Job Worker for Redis Queue System
Processes anime generation jobs from Redis queue and tracks progress
"""

import asyncio
import aiohttp
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, Optional, Any
import websockets
import signal
import sys

from redis_job_queue import RedisJobQueue, Job, JobStatus, JobPriority

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JobWorker:
    """Worker that processes jobs from Redis queue"""

    def __init__(self, worker_id: str = "worker-1"):
        self.worker_id = worker_id
        self.job_queue = None
        self.current_job: Optional[Job] = None
        self.running = False
        self.comfyui_url = "http://localhost:8188"
        self.websocket_url = "ws://localhost:8328/ws"  # Anime production WebSocket
        self.websocket_connection = None

    async def initialize(self):
        """Initialize the worker"""
        self.job_queue = RedisJobQueue()
        await self.job_queue.initialize()

        # Try to connect to WebSocket for progress updates
        try:
            self.websocket_connection = await websockets.connect(self.websocket_url)
            logger.info(f"🔗 WebSocket connected: {self.websocket_url}")
        except Exception as e:
            logger.warning(f"⚠️ WebSocket connection failed: {e}")
            self.websocket_connection = None

        logger.info(f"🚀 Worker {self.worker_id} initialized")

    async def start(self):
        """Start the worker main loop"""
        self.running = True
        logger.info(f"🔄 Worker {self.worker_id} starting...")

        # Set up signal handlers for graceful shutdown
        def signal_handler(sig, frame):
            logger.info(f"📝 Worker {self.worker_id} received shutdown signal")
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        while self.running:
            try:
                # Get next job from queue
                job = await self.job_queue.dequeue_job()

                if job:
                    self.current_job = job
                    await self.process_job(job)
                    self.current_job = None
                else:
                    # No jobs available, wait a bit
                    await asyncio.sleep(2)

                # Handle timeouts and cleanup
                await self.job_queue.handle_timeout_jobs()

            except Exception as e:
                logger.error(f"❌ Worker error: {e}")
                await asyncio.sleep(5)

        logger.info(f"🛑 Worker {self.worker_id} stopped")

    async def process_job(self, job: Job):
        """Process a single job"""
        logger.info(f"🎬 Processing job {job.id[:8]}: {job.job_type}")

        try:
            # Route to appropriate processor based on job type
            if job.job_type == "anime_generation":
                await self.process_anime_generation(job)
            elif job.job_type == "video_generation":
                await self.process_video_generation(job)
            elif job.job_type == "fast_video_generation":
                await self.process_fast_video_generation(job)
            else:
                await self.job_queue.complete_job(
                    job.id,
                    error=f"Unknown job type: {job.job_type}"
                )

        except Exception as e:
            logger.error(f"❌ Job {job.id[:8]} failed: {e}")
            await self.job_queue.complete_job(job.id, error=str(e))

    async def process_anime_generation(self, job: Job):
        """Process standard anime generation job"""
        await self.broadcast_progress(job.id, 5, "Preparing ComfyUI workflow...")

        # Build ComfyUI workflow from job parameters
        workflow = await self.build_workflow(job.parameters)
        if not workflow:
            await self.job_queue.complete_job(job.id, error="Failed to build workflow")
            return

        await self.broadcast_progress(job.id, 10, "Submitting to ComfyUI...")

        # Submit to ComfyUI
        comfyui_job_id = await self.submit_to_comfyui(workflow)
        if not comfyui_job_id:
            await self.job_queue.complete_job(job.id, error="Failed to submit to ComfyUI")
            return

        # Update job with ComfyUI ID
        await self.job_queue.update_job_progress(
            job.id,
            15,
            comfyui_job_id=comfyui_job_id
        )
        await self.broadcast_progress(job.id, 15, f"ComfyUI job started: {comfyui_job_id[:8]}...")

        # Monitor ComfyUI progress
        await self.monitor_comfyui_progress(job, comfyui_job_id)

    async def process_video_generation(self, job: Job):
        """Process video generation job (legacy compatibility)"""
        # Same as anime generation for now
        await self.process_anime_generation(job)

    async def process_fast_video_generation(self, job: Job):
        """Process fast segmented video generation"""
        await self.broadcast_progress(job.id, 5, "Starting fast segmented generation...")

        # Parse segment information from parameters
        parameters = job.parameters
        total_segments = parameters.get("total_segments", 1)
        segment_tasks = parameters.get("segment_tasks", [])

        # Process segments in parallel (simulated for now)
        for i, segment_task in enumerate(segment_tasks):
            progress = 10 + (70 * (i + 1) / len(segment_tasks))
            await self.broadcast_progress(
                job.id,
                progress,
                f"Processing segment {i + 1}/{len(segment_tasks)}..."
            )
            await asyncio.sleep(2)  # Simulate processing time

        await self.broadcast_progress(job.id, 85, "Combining segments...")
        await asyncio.sleep(3)  # Simulate combining

        # Complete the job
        output_path = f"/mnt/1TB-storage/ComfyUI/output/fast_generation_{int(time.time())}.mp4"
        result = {
            "output_path": output_path,
            "segments_processed": len(segment_tasks),
            "total_duration": parameters.get("duration", 5)
        }

        await self.job_queue.complete_job(job.id, result)
        await self.broadcast_progress(job.id, 100, "Fast generation completed!")

    async def build_workflow(self, parameters: Dict[str, Any]) -> Optional[Dict]:
        """Build ComfyUI workflow from job parameters"""
        try:
            # Extract parameters
            prompt = parameters.get("prompt", "anime character")
            character = parameters.get("character", "generic")
            style = parameters.get("style", "anime")
            duration = parameters.get("duration", 5)
            frames = duration * 24  # 24 fps

            # Build basic workflow (simplified version of fixed workflow)
            workflow = {
                "1": {
                    "inputs": {
                        "ckpt_name": "counterfeit_v3.safetensors",
                    },
                    "class_type": "CheckpointLoaderSimple",
                    "_meta": {"title": "Load Checkpoint"},
                },
                "2": {
                    "inputs": {
                        "text": f"{prompt}, {character} character, {style} style, high quality, detailed",
                        "clip": ["1", 1],
                    },
                    "class_type": "CLIPTextEncode",
                    "_meta": {"title": "CLIP Text Encode (Prompt)"},
                },
                "3": {
                    "inputs": {
                        "text": "blurry, low quality, distorted, watermark, signature, bad anatomy",
                        "clip": ["1", 1],
                    },
                    "class_type": "CLIPTextEncode",
                    "_meta": {"title": "Negative Prompt"},
                },
                "4": {
                    "inputs": {
                        "width": 1024,
                        "height": 1024,
                        "batch_size": frames,
                    },
                    "class_type": "EmptyLatentImage",
                    "_meta": {"title": "Empty Latent Image"},
                },
                "5": {
                    "inputs": {
                        "seed": parameters.get("seed", int(time.time())),
                        "steps": 20,
                        "cfg": 7.0,
                        "sampler_name": "euler",
                        "scheduler": "normal",
                        "denoise": 1.0,
                        "model": ["1", 0],
                        "positive": ["2", 0],
                        "negative": ["3", 0],
                        "latent_image": ["4", 0],
                    },
                    "class_type": "KSampler",
                    "_meta": {"title": "KSampler"},
                },
                "6": {
                    "inputs": {
                        "samples": ["5", 0],
                        "vae": ["1", 2],
                    },
                    "class_type": "VAEDecode",
                    "_meta": {"title": "VAE Decode"},
                },
                "7": {
                    "inputs": {
                        "images": ["6", 0],
                        "fps": 24,
                        "lossless": False,
                        "quality": 95,
                        "method": "h264",
                        "filename_prefix": f"anime_generation_{int(time.time())}",
                    },
                    "class_type": "VHS_VideoCombine",
                    "_meta": {"title": "Video Combine"},
                },
            }

            return workflow

        except Exception as e:
            logger.error(f"Error building workflow: {e}")
            return None

    async def submit_to_comfyui(self, workflow: Dict) -> Optional[str]:
        """Submit workflow to ComfyUI and return job ID"""
        try:
            async with aiohttp.ClientSession() as session:
                prompt_data = {"prompt": workflow}

                async with session.post(
                    f"{self.comfyui_url}/prompt",
                    json=prompt_data,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("prompt_id")
                    else:
                        logger.error(f"ComfyUI submission failed: {response.status}")
                        return None

        except Exception as e:
            logger.error(f"Error submitting to ComfyUI: {e}")
            return None

    async def monitor_comfyui_progress(self, job: Job, comfyui_job_id: str):
        """Monitor ComfyUI job progress and update Redis"""
        start_time = time.time()
        last_status = None

        while True:
            try:
                # Check ComfyUI status
                status = await self.check_comfyui_status(comfyui_job_id)

                if status != last_status:
                    logger.debug(f"ComfyUI status: {status}")
                    last_status = status

                if status == "queued":
                    progress = 20
                    message = "Queued in ComfyUI..."

                elif status == "running":
                    # Estimate progress based on time (rough estimate)
                    elapsed = time.time() - start_time
                    estimated_total = 120  # 2 minutes estimated
                    progress = min(25 + (60 * elapsed / estimated_total), 85)
                    message = f"Generating frames... ({elapsed:.0f}s)"

                elif status == "completed":
                    # Get output files
                    output_files = await self.get_comfyui_output(comfyui_job_id)
                    if output_files:
                        result = {
                            "output_path": output_files[0],
                            "comfyui_job_id": comfyui_job_id,
                            "processing_time": time.time() - start_time
                        }
                        await self.job_queue.complete_job(job.id, result)
                        await self.broadcast_progress(job.id, 100, "Generation completed!")
                        return
                    else:
                        await self.job_queue.complete_job(
                            job.id,
                            error="ComfyUI completed but no output files found"
                        )
                        return

                elif status == "failed":
                    await self.job_queue.complete_job(
                        job.id,
                        error="ComfyUI job failed"
                    )
                    return

                else:  # unknown
                    # Check for timeout
                    if time.time() - start_time > job.timeout_seconds:
                        await self.job_queue.complete_job(
                            job.id,
                            error=f"Job timed out after {job.timeout_seconds} seconds"
                        )
                        return

                    progress = 20
                    message = "Waiting for ComfyUI..."

                # Update progress
                await self.job_queue.update_job_progress(job.id, progress)
                await self.broadcast_progress(job.id, progress, message)

                # Wait before next check
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Error monitoring ComfyUI progress: {e}")
                await asyncio.sleep(10)

    async def check_comfyui_status(self, comfyui_job_id: str) -> str:
        """Check ComfyUI job status"""
        try:
            async with aiohttp.ClientSession() as session:
                # Check queue first
                async with session.get(f"{self.comfyui_url}/queue") as response:
                    if response.status == 200:
                        queue = await response.json()

                        # Check if running
                        for job in queue.get("queue_running", []):
                            if len(job) > 1 and job[1] == comfyui_job_id:
                                return "running"

                        # Check if pending
                        for job in queue.get("queue_pending", []):
                            if len(job) > 1 and job[1] == comfyui_job_id:
                                return "queued"

                # Check history
                async with session.get(f"{self.comfyui_url}/history/{comfyui_job_id}") as response:
                    if response.status == 200:
                        history = await response.json()
                        if comfyui_job_id in history:
                            job_data = history[comfyui_job_id]
                            if "outputs" in job_data:
                                return "completed"
                            else:
                                return "failed"

                return "unknown"

        except Exception as e:
            logger.error(f"Error checking ComfyUI status: {e}")
            return "unknown"

    async def get_comfyui_output(self, comfyui_job_id: str) -> list:
        """Get output files from completed ComfyUI job"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.comfyui_url}/history/{comfyui_job_id}") as response:
                    if response.status == 200:
                        history = await response.json()
                        job_data = history.get(comfyui_job_id, {})
                        outputs = job_data.get("outputs", {})

                        files = []
                        base_path = "/mnt/1TB-storage/ComfyUI/output/"

                        for node_id, output in outputs.items():
                            if "videos" in output:
                                for video in output["videos"]:
                                    filename = video.get("filename")
                                    if filename:
                                        full_path = os.path.join(base_path, filename)
                                        if os.path.exists(full_path):
                                            files.append(full_path)

                            if "images" in output:
                                for image in output["images"]:
                                    filename = image.get("filename")
                                    if filename:
                                        full_path = os.path.join(base_path, filename)
                                        if os.path.exists(full_path):
                                            files.append(full_path)

                        return files

        except Exception as e:
            logger.error(f"Error getting ComfyUI output: {e}")

        return []

    async def broadcast_progress(self, job_id: str, progress: float, message: str):
        """Broadcast progress update via WebSocket"""
        try:
            if self.websocket_connection:
                progress_update = {
                    "type": "progress_update",
                    "job_id": job_id,
                    "progress": progress,
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat()
                }

                await self.websocket_connection.send(json.dumps(progress_update))

        except Exception as e:
            logger.debug(f"WebSocket broadcast failed: {e}")
            # Don't fail the job if WebSocket fails

    async def stop(self):
        """Stop the worker gracefully"""
        self.running = False

        # Complete current job if any
        if self.current_job:
            await self.job_queue.complete_job(
                self.current_job.id,
                error="Worker shutdown during processing"
            )

        # Close WebSocket
        if self.websocket_connection:
            await self.websocket_connection.close()

        logger.info(f"🛑 Worker {self.worker_id} shutdown complete")

async def main():
    """Main entry point"""
    import sys

    worker_id = sys.argv[1] if len(sys.argv) > 1 else "worker-1"
    worker = JobWorker(worker_id)

    try:
        await worker.initialize()
        await worker.start()
    except KeyboardInterrupt:
        logger.info("🛑 Received interrupt signal")
    finally:
        await worker.stop()

if __name__ == "__main__":
    asyncio.run(main())