#!/usr/bin/env python3
"""
Integration Example: Using StatusMonitor with Anime Production API
Shows how to integrate the StatusMonitor into the existing anime generation workflow
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any

# Import the new modules
from modules.status_monitor import StatusMonitor, ProgressUpdate, ProgressStatus
from modules.comfyui_connector import ComfyUIConnector
from modules.job_manager import JobManager, JobType

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class EnhancedAnimeAPI:
    """
    Enhanced Anime API with real-time progress monitoring
    Demonstrates integration with StatusMonitor
    """

    def __init__(self):
        self.job_manager = JobManager()
        self.status_monitor = None
        self.active_jobs = {}  # job_id -> metadata

    async def initialize(self):
        """Initialize the enhanced API with monitoring"""
        logger.info("Initializing Enhanced Anime API...")

        # Start the status monitor
        self.status_monitor = StatusMonitor(
            poll_interval=1.0,  # Poll every second for demo
            websocket_port=8333  # Use different port for demo
        )

        # Add progress callbacks
        self.status_monitor.add_progress_callback(self._handle_progress_update)
        self.status_monitor.add_progress_callback(self._log_progress)

        # Start monitoring
        await self.status_monitor.start_monitoring()
        logger.info("Status monitoring started")

    async def shutdown(self):
        """Shutdown the API"""
        if self.status_monitor:
            await self.status_monitor.stop_monitoring()
        logger.info("Enhanced Anime API shutdown")

    async def generate_video(self, prompt: str, duration: int = 5) -> Dict[str, Any]:
        """
        Enhanced video generation with real-time progress tracking
        """
        logger.info(f"Starting video generation: '{prompt}' ({duration}s)")

        # Create job
        job = self.job_manager.create_job(
            job_type=JobType.VIDEO,
            prompt=prompt,
            parameters={"duration": duration}
        )

        # Store job metadata
        self.active_jobs[job.id] = {
            "prompt": prompt,
            "duration": duration,
            "started_at": datetime.utcnow(),
            "type": "video"
        }

        try:
            # Submit to ComfyUI
            workflow = self._create_video_workflow(prompt, duration)

            async with ComfyUIConnector() as connector:
                prompt_id = await connector.submit_workflow(workflow)

                if prompt_id:
                    # Start monitoring this job
                    self.status_monitor.monitor_job(
                        job_id=job.id,
                        comfyui_prompt_id=prompt_id,
                        job_type="video"
                    )

                    logger.info(f"Job {job.id} submitted to ComfyUI as {prompt_id}")

                    return {
                        "success": True,
                        "job_id": job.id,
                        "comfyui_prompt_id": prompt_id,
                        "status": "submitted",
                        "websocket_url": f"ws://localhost:8333",
                        "progress_endpoint": f"/api/jobs/{job.id}/progress"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to submit to ComfyUI"
                    }

        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_job_progress(self, job_id: int) -> Dict[str, Any]:
        """Get detailed progress for a job"""
        if self.status_monitor:
            progress = await self.status_monitor.get_progress(job_id)
            if progress:
                return {
                    "job_id": progress.job_id,
                    "comfyui_prompt_id": progress.comfyui_prompt_id,
                    "status": progress.status.value,
                    "progress_percent": progress.progress_percent,
                    "current_step": progress.current_step,
                    "total_steps": progress.total_steps,
                    "estimated_completion": progress.estimated_completion.isoformat() if progress.estimated_completion else None,
                    "generation_time": progress.generation_time,
                    "error_message": progress.error_message,
                    "timestamp": progress.timestamp.isoformat()
                }

        # Fallback to job manager
        job = self.job_manager.get_job(job_id)
        if job:
            return {
                "job_id": job.id,
                "status": job.status.value,
                "created_at": job.created_at.isoformat(),
                "error_message": job.error_message
            }

        return {"error": "Job not found"}

    async def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status"""
        if self.status_monitor:
            queue_stats = await self.status_monitor.get_queue_statistics()
            return {
                "system_healthy": True,
                "active_jobs": len(self.active_jobs),
                "comfyui_queue": queue_stats,
                "timestamp": datetime.utcnow().isoformat()
            }

        return {
            "system_healthy": False,
            "error": "Status monitoring not available"
        }

    def _handle_progress_update(self, update: ProgressUpdate):
        """Handle progress updates for business logic"""
        job_id = update.job_id

        # Update job manager status
        if update.status == ProgressStatus.PROCESSING:
            from modules.job_manager import JobStatus
            self.job_manager.update_job_status(job_id, JobStatus.PROCESSING)

        elif update.status == ProgressStatus.COMPLETED:
            from modules.job_manager import JobStatus
            self.job_manager.update_job_status(
                job_id,
                JobStatus.COMPLETED,
                completed_at=update.timestamp
            )

            # Cleanup
            if job_id in self.active_jobs:
                job_meta = self.active_jobs.pop(job_id)
                logger.info(f"Job {job_id} completed: {job_meta['prompt']}")

        elif update.status == ProgressStatus.FAILED:
            from modules.job_manager import JobStatus
            self.job_manager.update_job_status(
                job_id,
                JobStatus.FAILED,
                error_message=update.error_message
            )

            # Cleanup
            if job_id in self.active_jobs:
                self.active_jobs.pop(job_id)

    def _log_progress(self, update: ProgressUpdate):
        """Simple logging callback"""
        logger.info(
            f"Job {update.job_id} ({update.comfyui_prompt_id}): "
            f"{update.status.value} - {update.progress_percent:.1f}%"
        )

    def _create_video_workflow(self, prompt: str, duration: int) -> Dict[str, Any]:
        """Create a simple video workflow for demonstration"""
        # This is a simplified workflow structure
        # In reality, this would be much more complex
        return {
            "1": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["4", 1]
                }
            },
            "2": {
                "class_type": "AnimateDiffEvolve",
                "inputs": {
                    "conditioning": ["1", 0],
                    "frame_count": duration * 24,  # 24 FPS
                    "width": 512,
                    "height": 512
                }
            },
            "3": {
                "class_type": "SaveVideo",
                "inputs": {
                    "images": ["2", 0],
                    "filename_prefix": f"anime_video_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "dreamshaper_8.safetensors"
                }
            }
        }


# Demo usage
async def demo_enhanced_api():
    """Demonstrate the enhanced API with real-time monitoring"""
    print("🎬 Starting Enhanced Anime API Demo")
    print("=" * 50)

    api = EnhancedAnimeAPI()
    await api.initialize()

    try:
        # Test 1: Generate a video
        print("\n🎯 Test 1: Generate Video with Progress Monitoring")
        result = await api.generate_video(
            prompt="A serene anime landscape with cherry blossoms",
            duration=2
        )

        if result["success"]:
            job_id = result["job_id"]
            print(f"✅ Video generation started - Job ID: {job_id}")
            print(f"   ComfyUI Prompt ID: {result['comfyui_prompt_id']}")
            print(f"   WebSocket: {result['websocket_url']}")

            # Monitor progress for a while
            print("\n📊 Monitoring Progress (10 seconds)...")
            for i in range(10):
                progress = await api.get_job_progress(job_id)
                status = progress.get("status", "unknown")
                percent = progress.get("progress_percent", 0)

                print(f"   [{i+1:2d}/10] Status: {status:12} - Progress: {percent:5.1f}%")

                if status in ["completed", "failed"]:
                    break

                await asyncio.sleep(1)

        else:
            print(f"❌ Video generation failed: {result['error']}")

        # Test 2: System status
        print(f"\n🔧 Test 2: System Status")
        status = await api.get_system_status()
        print(f"   System Healthy: {status['system_healthy']}")
        print(f"   Active Jobs: {status['active_jobs']}")

        if "comfyui_queue" in status:
            queue = status["comfyui_queue"]
            print(f"   ComfyUI Queue: {queue['running_jobs']} running, {queue['pending_jobs']} pending")

            if "generation_stats" in queue:
                stats = queue["generation_stats"]
                if stats["completion_times"]:
                    print(f"   Historical Performance:")
                    for job_type, times in stats["completion_times"].items():
                        print(f"     {job_type}: {times['median']:.1f}s median ({times['count']} samples)")

    except Exception as e:
        print(f"❌ Demo failed: {e}")

    finally:
        print("\n🛑 Shutting down...")
        await api.shutdown()
        print("✅ Demo completed")


if __name__ == "__main__":
    try:
        asyncio.run(demo_enhanced_api())
    except KeyboardInterrupt:
        print("\n🛑 Demo interrupted by user")
    except Exception as e:
        print(f"\n💥 Demo crashed: {e}")