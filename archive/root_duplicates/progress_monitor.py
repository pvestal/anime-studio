#!/usr/bin/env python3
"""
Real-time progress monitoring for ComfyUI jobs.
Tracks job progress and updates database status.
"""

import asyncio
import aiohttp
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import time
from datetime import datetime
from typing import Dict, Optional, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ComfyUIProgressMonitor:
    def __init__(self):
        self.comfyui_url = "http://localhost:8188"
        self.db_config = {
            "host": "localhost",
            "database": "anime_production",
            "user": "patrick",
            "password": "***REMOVED***",
            "port": 5432,
            "options": "-c search_path=anime_api,public"
        }
        self.active_jobs: Dict[str, dict] = {}

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)

    async def check_comfyui_progress(self, prompt_id: str) -> Dict:
        """Check progress of a specific ComfyUI job"""
        async with aiohttp.ClientSession() as session:
            try:
                # Check queue status
                async with session.get(f"{self.comfyui_url}/queue") as response:
                    if response.status == 200:
                        queue = await response.json()

                        # Check if running
                        for job in queue.get("queue_running", []):
                            if len(job) > 1 and job[1] == prompt_id:
                                # Get node progress if available
                                return {
                                    "status": "running",
                                    "progress": 50,  # Estimate since ComfyUI doesn't give exact %
                                    "message": "Generating frames..."
                                }

                        # Check if pending
                        for idx, job in enumerate(queue.get("queue_pending", [])):
                            if len(job) > 1 and job[1] == prompt_id:
                                return {
                                    "status": "queued",
                                    "progress": 0,
                                    "position": idx + 1,
                                    "message": f"Position {idx + 1} in queue"
                                }

                # Check history to see if completed
                async with session.get(f"{self.comfyui_url}/history/{prompt_id}") as response:
                    if response.status == 200:
                        history = await response.json()
                        if prompt_id in history:
                            job_data = history[prompt_id]

                            # Check for outputs
                            if "outputs" in job_data:
                                outputs = []
                                for node_id, node_output in job_data["outputs"].items():
                                    if "videos" in node_output:
                                        for video in node_output["videos"]:
                                            outputs.append({
                                                "type": "video",
                                                "filename": video.get("filename"),
                                                "subfolder": video.get("subfolder", ""),
                                                "format": video.get("format", "mp4")
                                            })
                                    if "images" in node_output:
                                        for image in node_output["images"]:
                                            outputs.append({
                                                "type": "image",
                                                "filename": image.get("filename"),
                                                "subfolder": image.get("subfolder", "")
                                            })

                                return {
                                    "status": "completed",
                                    "progress": 100,
                                    "outputs": outputs,
                                    "message": f"Completed with {len(outputs)} outputs"
                                }
                            else:
                                # Completed but no outputs (might be error)
                                return {
                                    "status": "failed",
                                    "progress": 0,
                                    "message": "Completed without outputs"
                                }
                        else:
                            # Not in history, might be new
                            return {
                                "status": "unknown",
                                "progress": 0,
                                "message": "Job not found in queue or history"
                            }

            except Exception as e:
                logger.error(f"Error checking ComfyUI progress: {e}")
                return {
                    "status": "error",
                    "progress": 0,
                    "message": str(e)
                }

    async def update_job_status(self, job_id: int, comfyui_id: str, status: Dict):
        """Update job status in database"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            # Map ComfyUI status to our status
            status_map = {
                "queued": "queued",
                "running": "processing",
                "completed": "completed",
                "failed": "failed",
                "unknown": "processing",  # Keep as processing if unknown
                "error": "failed"
            }

            new_status = status_map.get(status["status"], "processing")

            # Update job
            if new_status == "completed" and status.get("outputs"):
                # Save output information
                output_path = "/mnt/1TB-storage/ComfyUI/output/"
                for output in status["outputs"]:
                    if output.get("filename"):
                        output_path += output["filename"]
                        break

                cursor.execute("""
                    UPDATE production_jobs
                    SET status = %s,
                        output_path = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (new_status, output_path, job_id))

                logger.info(f"Job {job_id} completed with output: {output_path}")

            else:
                cursor.execute("""
                    UPDATE production_jobs
                    SET status = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (new_status, job_id))

                logger.info(f"Job {job_id} status updated to: {new_status}")

            conn.commit()
            cursor.close()
            conn.close()

            return True

        except Exception as e:
            logger.error(f"Error updating job status: {e}")
            return False

    async def get_active_jobs(self) -> List[Dict]:
        """Get all jobs that need monitoring"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, comfyui_job_id, status, prompt, created_at
                FROM production_jobs
                WHERE status IN ('processing', 'queued', 'pending')
                AND comfyui_job_id IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 50
            """)

            jobs = cursor.fetchall()
            cursor.close()
            conn.close()

            return jobs

        except Exception as e:
            logger.error(f"Error getting active jobs: {e}")
            return []

    async def monitor_loop(self):
        """Main monitoring loop"""
        logger.info("Starting ComfyUI progress monitor...")

        while True:
            try:
                # Get active jobs
                jobs = await self.get_active_jobs()

                if jobs:
                    logger.info(f"Monitoring {len(jobs)} active jobs...")

                    for job in jobs:
                        job_id = job["id"]
                        comfyui_id = job["comfyui_job_id"]

                        # Check progress
                        status = await self.check_comfyui_progress(comfyui_id)

                        # Log progress
                        logger.info(f"Job {job_id} ({comfyui_id[:8]}...): {status['status']} - {status['message']}")

                        # Update database if status changed
                        if status["status"] != job["status"]:
                            await self.update_job_status(job_id, comfyui_id, status)

                        # Small delay between checks
                        await asyncio.sleep(0.5)

                # Wait before next cycle
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(10)

    async def test_specific_job(self, job_id: int):
        """Test monitoring a specific job"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, comfyui_job_id, status, prompt
                FROM production_jobs
                WHERE id = %s
            """, (job_id,))

            job = cursor.fetchone()
            cursor.close()
            conn.close()

            if job and job["comfyui_job_id"]:
                logger.info(f"Testing job {job_id}: {job['comfyui_job_id']}")

                status = await self.check_comfyui_progress(job["comfyui_job_id"])

                print(f"\nJob {job_id} Status:")
                print(f"  ComfyUI ID: {job['comfyui_job_id']}")
                print(f"  Current Status: {job['status']}")
                print(f"  ComfyUI Status: {status['status']}")
                print(f"  Progress: {status.get('progress', 0)}%")
                print(f"  Message: {status['message']}")

                if status.get("outputs"):
                    print(f"  Outputs:")
                    for output in status["outputs"]:
                        print(f"    - {output['type']}: {output['filename']}")

                # Update if needed
                if status["status"] != job["status"]:
                    await self.update_job_status(job_id, job["comfyui_job_id"], status)
                    print(f"  ✅ Status updated to: {status['status']}")

                return status
            else:
                print(f"Job {job_id} not found or has no ComfyUI ID")
                return None

        except Exception as e:
            logger.error(f"Error testing job: {e}")
            return None

async def main():
    """Main entry point"""
    import sys

    monitor = ComfyUIProgressMonitor()

    if len(sys.argv) > 1:
        # Test specific job
        job_id = int(sys.argv[1])
        await monitor.test_specific_job(job_id)
    else:
        # Run monitoring loop
        await monitor.monitor_loop()

if __name__ == "__main__":
    asyncio.run(main())