#!/usr/bin/env python3
"""
PostgreSQL Job Monitor - The REAL fix for anime production
Monitors production_jobs in PostgreSQL and updates them based on ComfyUI status
This is the missing piece that was never implemented!
"""

import asyncio
import logging
import time
import aiohttp
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from pathlib import Path
import os
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PostgreSQLJobMonitor:
    """Monitors PostgreSQL production_jobs and syncs with ComfyUI"""

    def __init__(self):
        self.db_config = {
            "host": "localhost",
            "database": "anime_production",
            "user": "patrick",
            "password": "tower_echo_brain_secret_key_2025",
            "port": 5432,
            "options": "-c search_path=anime_api,public"
        }
        self.comfyui_url = "http://localhost:8188"
        self.running = True

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config)

    async def start(self):
        """Start monitoring loop"""
        logger.info("🚀 PostgreSQL Job Monitor Starting...")
        logger.info("This is the REAL fix - monitoring production_jobs table")

        while self.running:
            try:
                await self.monitor_jobs()
                await asyncio.sleep(5)  # Check every 5 seconds
            except KeyboardInterrupt:
                logger.info("Shutting down monitor...")
                self.running = False
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(10)

    async def monitor_jobs(self):
        """Check and update job statuses"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Get all processing jobs with ComfyUI IDs
            cursor.execute("""
                SELECT id, comfyui_job_id, status, created_at, job_type
                FROM production_jobs
                WHERE status IN ('processing', 'submitted')
                AND comfyui_job_id IS NOT NULL
            """)
            jobs = cursor.fetchall()

            if jobs:
                logger.info(f"Monitoring {len(jobs)} active jobs")

            for job in jobs:
                await self.check_job_status(job, conn)

            # Also check for stuck jobs without ComfyUI IDs
            cursor.execute("""
                SELECT id, status, created_at
                FROM production_jobs
                WHERE status = 'processing'
                AND comfyui_job_id IS NULL
                AND created_at < NOW() - INTERVAL '5 minutes'
            """)
            stuck_jobs = cursor.fetchall()

            for job in stuck_jobs:
                logger.warning(f"Job {job['id']} stuck without ComfyUI ID, marking as failed")
                cursor.execute("""
                    UPDATE production_jobs
                    SET status = 'failed',
                        updated_at = NOW()
                    WHERE id = %s
                """, (job['id'],))
                conn.commit()

    async def check_job_status(self, job, conn):
        """Check ComfyUI status for a job"""
        job_id = job['id']
        comfyui_id = job['comfyui_job_id']

        try:
            # Check ComfyUI queue
            async with aiohttp.ClientSession() as session:
                # Check if still in queue
                async with session.get(f"{self.comfyui_url}/queue") as response:
                    if response.status == 200:
                        queue_data = await response.json()

                        # Check if running
                        for running_job in queue_data.get("queue_running", []):
                            if len(running_job) > 1 and running_job[1] == comfyui_id:
                                logger.debug(f"Job {job_id} still running in ComfyUI")
                                return

                        # Check if pending
                        for pending_job in queue_data.get("queue_pending", []):
                            if len(pending_job) > 1 and pending_job[1] == comfyui_id:
                                logger.debug(f"Job {job_id} still pending in ComfyUI")
                                return

                # Not in queue, check history
                async with session.get(f"{self.comfyui_url}/history/{comfyui_id}") as response:
                    if response.status == 200:
                        history = await response.json()

                        if comfyui_id in history:
                            job_data = history[comfyui_id]
                            outputs = job_data.get("outputs", {})

                            # Check for output files
                            output_files = []
                            for node_id, output in outputs.items():
                                if "images" in output:
                                    for image in output["images"]:
                                        filename = image.get("filename")
                                        if filename:
                                            full_path = f"/mnt/1TB-storage/ComfyUI/output/{filename}"
                                            if os.path.exists(full_path):
                                                output_files.append(full_path)

                                if "videos" in output:
                                    for video in output["videos"]:
                                        filename = video.get("filename")
                                        if filename:
                                            full_path = f"/mnt/1TB-storage/ComfyUI/output/{filename}"
                                            if os.path.exists(full_path):
                                                output_files.append(full_path)

                            if output_files:
                                # Job completed successfully
                                logger.info(f"✅ Job {job_id} completed with {len(output_files)} outputs")

                                # Organize files to project directory
                                organized_path = await self.organize_output(job_id, output_files[0])

                                # Update database
                                cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE production_jobs
                                    SET status = 'completed',
                                        output_path = %s,
                                        updated_at = NOW()
                                    WHERE id = %s
                                """, (organized_path, job_id))
                                conn.commit()
                            else:
                                # Job finished but no outputs
                                logger.warning(f"Job {job_id} finished but no outputs found")
                                cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE production_jobs
                                    SET status = 'failed',
                                        updated_at = NOW()
                                    WHERE id = %s
                                """, (job_id,))
                                conn.commit()
                        else:
                            # Check for timeout
                            created_at = job['created_at']
                            if isinstance(created_at, str):
                                created_at = datetime.fromisoformat(created_at)

                            if datetime.now() - created_at > timedelta(minutes=10):
                                logger.warning(f"Job {job_id} timed out")
                                cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE production_jobs
                                    SET status = 'timeout',
                                        updated_at = NOW()
                                    WHERE id = %s
                                """, (job_id,))
                                conn.commit()

        except Exception as e:
            logger.error(f"Error checking job {job_id}: {e}")

    async def organize_output(self, job_id, source_path):
        """Move output file to organized location"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_dir = Path(f"/mnt/1TB-storage/anime-projects/job_{job_id}/{timestamp}")
            target_dir.mkdir(parents=True, exist_ok=True)

            source = Path(source_path)
            target = target_dir / source.name

            # Copy file (don't move in case ComfyUI needs it)
            import shutil
            shutil.copy2(source, target)

            logger.info(f"Organized output to {target}")
            return str(target)

        except Exception as e:
            logger.error(f"Failed to organize output: {e}")
            return source_path

async def main():
    """Run the monitor"""
    monitor = PostgreSQLJobMonitor()
    await monitor.start()

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("POSTGRESQL JOB MONITOR - THE REAL FIX")
    logger.info("This monitors production_jobs and updates them")
    logger.info("This is what was missing all along!")
    logger.info("=" * 50)
    asyncio.run(main())