#!/usr/bin/env python3
"""
Anime Production Worker - Actually processes jobs from Redis queue
This is the missing piece that makes anime generation work!
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp
import redis

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AnimeWorker:
    """Worker that processes anime generation jobs from Redis queue"""

    def __init__(self):
        self.redis_client = redis.Redis(
            host="localhost", port=6379, db=1, decode_responses=True
        )
        self.comfyui_url = "http://192.168.50.135:8188"
        self.websocket_redis = redis.Redis(host="localhost", port=6379, db=1)
        self.running = True

        # Import job queue
        import sys

        sys.path.insert(0, "/opt/tower-anime-production")
        from services.fixes.job_queue import AnimeJobQueue

        self.job_queue = AnimeJobQueue()

    async def start(self):
        """Start the worker"""
        logger.info("🚀 Anime Production Worker Starting...")
        logger.info(f"ComfyUI URL: {self.comfyui_url}")
        logger.info(f"Redis Queue Length: {self.job_queue.get_queue_length()}")

        # Process jobs forever
        while self.running:
            try:
                # Get next job from queue
                job_id = self.job_queue.get_next_job()

                if job_id:
                    logger.info(f"📦 Processing job: {job_id}")
                    await self.process_job(job_id)
                else:
                    # No jobs, wait a bit
                    await asyncio.sleep(2)

            except KeyboardInterrupt:
                logger.info("Shutting down worker...")
                self.running = False
            except Exception as e:
                logger.error(f"Worker error: {e}")
                await asyncio.sleep(5)

    async def process_job(self, job_id: str):
        """Process a single job"""
        try:
            # Get job details
            job_data = self.job_queue.get_job_status(job_id)
            if not job_data:
                logger.error(f"Job {job_id} not found")
                return

            project_id = job_data.get("project_id")
            job_type = job_data.get("type")
            # Handle params whether it's already a dict or a JSON string
            params_data = job_data.get("params", "{}")
            if isinstance(params_data, dict):
                params = params_data
            else:
                params = json.loads(params_data)

            logger.info(f"Job type: {job_type}, Project: {project_id}")

            # Update progress
            self.job_queue.update_job_progress(job_id, 10, "preparing")
            await self.broadcast_progress(job_id, 10, "Preparing workflow...")

            # Build ComfyUI workflow
            workflow = await self.build_comfyui_workflow(params)

            # Submit to ComfyUI
            self.job_queue.update_job_progress(job_id, 20, "submitting")
            await self.broadcast_progress(job_id, 20, "Submitting to ComfyUI...")

            comfyui_job_id = await self.submit_to_comfyui(workflow)
            if not comfyui_job_id:
                self.job_queue.fail_job(job_id, "Failed to submit to ComfyUI")
                return

            logger.info(f"✅ Submitted to ComfyUI: {comfyui_job_id}")

            # Monitor ComfyUI progress
            await self.monitor_comfyui_job(job_id, comfyui_job_id, project_id)

        except Exception as e:
            logger.error(f"Failed to process job {job_id}: {e}")
            self.job_queue.fail_job(job_id, str(e))

    async def build_comfyui_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Build a ComfyUI workflow from parameters"""
        # Basic anime generation workflow
        workflow = {
            "3": {
                "inputs": {
                    "seed": params.get("seed", 42),
                    "steps": params.get("steps", 20),
                    "cfg": params.get("cfg", 7.0),
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
                "class_type": "KSampler",
            },
            "4": {
                "inputs": {
                    "ckpt_name": params.get("model", "Counterfeit-V2.5.safetensors")
                },
                "class_type": "CheckpointLoaderSimple",
            },
            "5": {
                "inputs": {
                    "width": params.get("width", 1024),
                    "height": params.get("height", 1024),
                    "batch_size": 1,
                },
                "class_type": "EmptyLatentImage",
            },
            "6": {
                "inputs": {
                    "text": params.get("prompt", "anime girl with blue hair"),
                    "clip": ["4", 1],
                },
                "class_type": "CLIPTextEncode",
            },
            "7": {
                "inputs": {
                    "text": params.get("negative_prompt", "bad quality, blurry"),
                    "clip": ["4", 1],
                },
                "class_type": "CLIPTextEncode",
            },
            "8": {
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
                "class_type": "VAEDecode",
            },
            "9": {
                "inputs": {
                    "filename_prefix": f"anime_{int(time.time())}",
                    "images": ["8", 0],
                },
                "class_type": "SaveImage",
            },
        }

        return workflow

    async def submit_to_comfyui(self, workflow: Dict[str, Any]) -> Optional[str]:
        """Submit workflow to ComfyUI"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"prompt": workflow,
                           "client_id": f"worker_{id(self)}"}

                async with session.post(
                    f"{self.comfyui_url}/prompt",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("prompt_id")
                    else:
                        logger.error(f"ComfyUI returned {response.status}")
                        return None

        except Exception as e:
            logger.error(f"Failed to submit to ComfyUI: {e}")
            return None

    async def monitor_comfyui_job(
        self, job_id: str, comfyui_job_id: str, project_id: str
    ):
        """Monitor ComfyUI job and update progress"""
        start_time = time.time()
        max_wait = 600  # 10 minutes max

        while time.time() - start_time < max_wait:
            try:
                # Check ComfyUI status
                status = await self.check_comfyui_status(comfyui_job_id)

                if status == "completed":
                    # Get output files
                    output_files = await self.get_comfyui_output(comfyui_job_id)

                    if output_files:
                        # Move files to project directory
                        organized_files = await self.organize_output_files(
                            output_files, project_id
                        )

                        # Complete the job
                        self.job_queue.complete_job(
                            job_id,
                            {
                                "output_files": organized_files,
                                "comfyui_job_id": comfyui_job_id,
                                "processing_time": time.time() - start_time,
                            },
                        )

                        await self.broadcast_progress(
                            job_id, 100, "Generation complete!"
                        )
                        logger.info(
                            f"✅ Job {job_id} completed in {time.time() - start_time:.1f}s"
                        )
                        return
                    else:
                        self.job_queue.fail_job(
                            job_id, "No output files generated")
                        return

                elif status == "failed":
                    self.job_queue.fail_job(job_id, "ComfyUI job failed")
                    return

                elif status == "running":
                    # Update progress based on time elapsed
                    elapsed = time.time() - start_time
                    progress = min(
                        30 + int(60 * (elapsed / 120)), 90
                    )  # Estimate 2 minutes
                    self.job_queue.update_job_progress(job_id, progress)
                    await self.broadcast_progress(
                        job_id, progress, f"Generating... ({elapsed:.0f}s)"
                    )

                elif status == "queued":
                    await self.broadcast_progress(job_id, 25, "Queued in ComfyUI...")

                # Wait before checking again
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Error monitoring ComfyUI job: {e}")
                await asyncio.sleep(5)

        # Timeout
        self.job_queue.fail_job(
            job_id, f"Job timed out after {max_wait} seconds")

    async def check_comfyui_status(self, prompt_id: str) -> str:
        """Check ComfyUI job status"""
        try:
            async with aiohttp.ClientSession() as session:
                # Check queue
                async with session.get(f"{self.comfyui_url}/queue") as response:
                    if response.status == 200:
                        queue = await response.json()

                        # Check if running
                        for job in queue.get("queue_running", []):
                            if len(job) > 1 and job[1] == prompt_id:
                                return "running"

                        # Check if queued
                        for job in queue.get("queue_pending", []):
                            if len(job) > 1 and job[1] == prompt_id:
                                return "queued"

                # Check history
                async with session.get(
                    f"{self.comfyui_url}/history/{prompt_id}"
                ) as response:
                    if response.status == 200:
                        history = await response.json()
                        if prompt_id in history:
                            return "completed"

        except Exception as e:
            logger.error(f"Error checking ComfyUI status: {e}")

        return "unknown"

    async def get_comfyui_output(self, prompt_id: str) -> list:
        """Get output files from ComfyUI"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.comfyui_url}/history/{prompt_id}"
                ) as response:
                    if response.status == 200:
                        history = await response.json()
                        job_data = history.get(prompt_id, {})
                        outputs = job_data.get("outputs", {})

                        files = []
                        for node_id, output in outputs.items():
                            if "images" in output:
                                for image in output["images"]:
                                    filename = image.get("filename")
                                    if filename:
                                        files.append(filename)
                            if "videos" in output:
                                for video in output["videos"]:
                                    filename = video.get("filename")
                                    if filename:
                                        files.append(filename)

                        return files

        except Exception as e:
            logger.error(f"Error getting ComfyUI output: {e}")

        return []

    async def organize_output_files(self, files: list, project_id: str) -> list:
        """Move output files to project directory"""
        organized = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create project directory
        project_dir = Path(
            f"/mnt/1TB-storage/anime-projects/{project_id}/{timestamp}")
        project_dir.mkdir(parents=True, exist_ok=True)

        # Move files
        comfyui_output = Path("/mnt/1TB-storage/ComfyUI/output")
        for filename in files:
            source = comfyui_output / filename
            if source.exists():
                dest = project_dir / filename
                source.rename(dest)
                organized.append(str(dest))
                logger.info(f"Moved {filename} to {dest}")

        return organized

    async def broadcast_progress(self, job_id: str, progress: int, message: str):
        """Send progress update via Redis for WebSocket broadcast"""
        try:
            update = {
                "job_id": job_id,
                "progress": progress,
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }

            # Publish to Redis for WebSocket server
            self.websocket_redis.publish(
                "anime:job:updates", json.dumps(update))

        except Exception as e:
            logger.error(f"Failed to broadcast progress: {e}")


async def main():
    """Run the worker"""
    worker = AnimeWorker()
    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
