#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Critical Anime Pipeline Reliability Fix
Fixes completion tracking and stuck job monitoring

Issues Fixed:
1. 60+ jobs stuck in "processing" status that never complete
2. Missing completion callbacks between ComfyUI and anime service
3. No job timeout monitoring or recovery mechanisms
4. No automated status updates when ComfyUI completes jobs

Author: Claude Code
Date: November 7, 2025
"""

import asyncio
import aiohttp
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import os
import signal
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/opt/tower-anime-production/logs/completion_tracking.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'anime_production',
    'user': 'patrick',
    'password': 'tower_echo_brain_secret_key_2025',
    'port': 5432
}

# ComfyUI configuration
COMFYUI_URL = "http://192.168.50.135:8188"

class JobCompletionTracker:
    """Monitors ComfyUI jobs and updates database status when complete"""

    def __init__(self):
        self.running = True
        self.check_interval = 30  # Check every 30 seconds
        self.timeout_threshold = timedelta(hours=2)  # 2 hour timeout

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**DB_CONFIG)

    async def get_comfyui_history(self, prompt_id: str) -> Optional[Dict]:
        """Check ComfyUI history for job completion"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{COMFYUI_URL}/history/{prompt_id}") as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get(prompt_id)
                    else:
                        logger.warning(f"ComfyUI history check failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error checking ComfyUI history: {e}")
            return None

    def extract_job_output_path(self, comfyui_output: Dict) -> Optional[str]:
        """Extract final output file path from ComfyUI job result"""
        try:
            outputs = comfyui_output.get('outputs', {})
            for node_id, output in outputs.items():
                # Check for videos first (priority)
                if 'videos' in output and output['videos']:
                    filename = output['videos'][0]['filename']
                    return f"/mnt/1TB-storage/ComfyUI/output/{filename}"
                # Then check for images
                elif 'images' in output and output['images']:
                    filename = output['images'][0]['filename']
                    return f"/mnt/1TB-storage/ComfyUI/output/{filename}"
            return None
        except Exception as e:
            logger.error(f"Error extracting output path: {e}")
            return None

    def verify_output_file_exists(self, output_path: str) -> bool:
        """Verify the output file actually exists on disk"""
        try:
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception:
            return False

    async def check_job_completion(self, job_id: int, comfyui_job_id: str, output_path: str) -> bool:
        """Check if a specific job has completed and update database"""
        try:
            # Check ComfyUI history
            comfyui_result = await self.get_comfyui_history(comfyui_job_id)

            if comfyui_result is None:
                return False  # Still processing or not found

            # Extract actual output path
            actual_output_path = self.extract_job_output_path(comfyui_result)
            if not actual_output_path:
                logger.warning(f"Job {job_id}: No output path found in ComfyUI result")
                return False

            # Verify file exists
            if not self.verify_output_file_exists(actual_output_path):
                logger.warning(f"Job {job_id}: Output file does not exist: {actual_output_path}")
                return False

            # Update database status to completed
            with self.get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("""
                    UPDATE anime_api.production_jobs
                    SET status = 'completed', output_path = %s
                    WHERE id = %s
                """, (actual_output_path, job_id))
                conn.commit()

                logger.info(f" Job {job_id} marked as completed: {actual_output_path}")
                return True

        except Exception as e:
            logger.error(f"Error checking job {job_id} completion: {e}")
            return False

    def get_processing_jobs(self) -> List[Dict]:
        """Get all jobs currently in processing status"""
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("""
                    SELECT id, output_path, created_at, parameters, prompt
                    FROM anime_api.production_jobs
                    WHERE status = 'processing'
                    ORDER BY created_at DESC
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting processing jobs: {e}")
            return []

    def extract_comfyui_job_id_from_output_path(self, output_path: str) -> Optional[str]:
        """Extract ComfyUI job ID from output path pattern"""
        if not output_path:
            return None

        # Pattern: /mnt/1TB-storage/ComfyUI/output/animatediff_5sec_72frames_1762530371
        # The timestamp at the end is often the ComfyUI job ID
        try:
            # Split by underscore and get last part (timestamp)
            parts = output_path.split('_')
            if len(parts) >= 2:
                timestamp = parts[-1]
                if timestamp.isdigit():
                    return timestamp
        except Exception:
            pass

        return None

    def timeout_old_jobs(self) -> int:
        """Mark jobs older than timeout threshold as 'timeout'"""
        try:
            cutoff_time = datetime.now() - self.timeout_threshold

            with self.get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("""
                    UPDATE anime_api.production_jobs
                    SET status = 'timeout'
                    WHERE status = 'processing'
                    AND created_at < %s
                """, (cutoff_time,))

                timeout_count = cursor.rowcount
                conn.commit()

                if timeout_count > 0:
                    logger.warning(f"� Marked {timeout_count} jobs as timed out (older than {self.timeout_threshold})")

                return timeout_count

        except Exception as e:
            logger.error(f"Error timing out old jobs: {e}")
            return 0

    async def monitor_processing_jobs(self):
        """Main monitoring loop"""
        logger.info("<� Starting job completion monitoring")

        while self.running:
            try:
                # Get all processing jobs
                processing_jobs = self.get_processing_jobs()

                if not processing_jobs:
                    logger.debug("No processing jobs found")
                    await asyncio.sleep(self.check_interval)
                    continue

                logger.info(f"=� Monitoring {len(processing_jobs)} processing jobs")

                completed_count = 0

                for job in processing_jobs:
                    job_id = job['id']
                    output_path = job['output_path']

                    # Try to extract ComfyUI job ID from output path
                    comfyui_job_id = self.extract_comfyui_job_id_from_output_path(output_path)

                    if not comfyui_job_id:
                        logger.debug(f"Job {job_id}: Could not extract ComfyUI job ID from {output_path}")
                        continue

                    # Check if job completed
                    if await self.check_job_completion(job_id, comfyui_job_id, output_path):
                        completed_count += 1

                if completed_count > 0:
                    logger.info(f" Completed {completed_count} jobs this cycle")

                # Check for and timeout old jobs
                timeout_count = self.timeout_old_jobs()

                # Brief pause between checks
                await asyncio.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.check_interval)

    def stop(self):
        """Stop monitoring"""
        self.running = False
        logger.info("=� Stopping job completion monitoring")


class JobCleanupManager:
    """Provides endpoints and utilities for cleaning up stuck jobs"""

    def __init__(self):
        self.db_config = DB_CONFIG

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config)

    def get_stuck_jobs_summary(self) -> Dict:
        """Get summary of all stuck jobs"""
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                # Count by status
                cursor.execute("""
                    SELECT status, COUNT(*) as count
                    FROM anime_api.production_jobs
                    GROUP BY status
                """)
                status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

                # Get oldest processing jobs
                cursor.execute("""
                    SELECT id, prompt, created_at, output_path
                    FROM anime_api.production_jobs
                    WHERE status = 'processing'
                    ORDER BY created_at ASC
                    LIMIT 10
                """)
                oldest_stuck = cursor.fetchall()

                # Get processing jobs older than 2 hours
                cutoff_time = datetime.now() - timedelta(hours=2)
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM anime_api.production_jobs
                    WHERE status = 'processing' AND created_at < %s
                """, (cutoff_time,))
                old_processing = cursor.fetchone()['count']

                return {
                    'status_summary': status_counts,
                    'total_stuck': status_counts.get('processing', 0),
                    'old_processing_jobs': old_processing,
                    'oldest_stuck_jobs': [
                        {
                            'id': job['id'],
                            'prompt': job['prompt'][:100] + ('...' if len(job['prompt']) > 100 else ''),
                            'created_at': job['created_at'].isoformat(),
                            'age_hours': (datetime.now() - job['created_at']).total_seconds() / 3600,
                            'output_path': job['output_path']
                        }
                        for job in oldest_stuck
                    ]
                }

        except Exception as e:
            logger.error(f"Error getting stuck jobs summary: {e}")
            return {'error': str(e)}

    def fix_stuck_jobs_by_checking_files(self) -> Dict:
        """Fix stuck jobs by checking if their output files actually exist"""
        try:
            fixed_jobs = []

            with self.get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                # Get all processing jobs
                cursor.execute("""
                    SELECT id, output_path, created_at
                    FROM anime_api.production_jobs
                    WHERE status = 'processing' AND output_path IS NOT NULL
                """)
                processing_jobs = cursor.fetchall()

                for job in processing_jobs:
                    job_id = job['id']
                    output_path = job['output_path']

                    # Check if there are any files matching the expected pattern
                    base_path = output_path.replace('/mnt/1TB-storage/ComfyUI/output/', '')
                    potential_files = [
                        f"{output_path}_00001.mp4",
                        f"{output_path}.mp4",
                        f"{output_path}_00001.png",
                        f"{output_path}.png",
                    ]

                    actual_file = None
                    for potential_file in potential_files:
                        if os.path.exists(potential_file) and os.path.getsize(potential_file) > 0:
                            actual_file = potential_file
                            break

                    if actual_file:
                        # Update job status to completed
                        cursor.execute("""
                            UPDATE anime_api.production_jobs
                            SET status = 'completed', output_path = %s
                            WHERE id = %s
                        """, (actual_file, job_id))

                        fixed_jobs.append({
                            'job_id': job_id,
                            'output_file': actual_file,
                            'age_hours': (datetime.now() - job['created_at']).total_seconds() / 3600
                        })

                conn.commit()

                logger.info(f" Fixed {len(fixed_jobs)} stuck jobs by checking output files")

                return {
                    'success': True,
                    'fixed_jobs': len(fixed_jobs),
                    'details': fixed_jobs
                }

        except Exception as e:
            logger.error(f"Error fixing stuck jobs: {e}")
            return {'error': str(e)}

    def force_timeout_old_jobs(self, hours: int = 2) -> Dict:
        """Force timeout jobs older than specified hours"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)

            with self.get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                # Get jobs to be timed out (for logging)
                cursor.execute("""
                    SELECT id, prompt, created_at
                    FROM anime_api.production_jobs
                    WHERE status = 'processing' AND created_at < %s
                """, (cutoff_time,))
                to_timeout = cursor.fetchall()

                # Timeout the jobs
                cursor.execute("""
                    UPDATE anime_api.production_jobs
                    SET status = 'timeout'
                    WHERE status = 'processing' AND created_at < %s
                """, (cutoff_time,))

                timeout_count = cursor.rowcount
                conn.commit()

                logger.warning(f"� Force timed out {timeout_count} jobs older than {hours} hours")

                return {
                    'success': True,
                    'timed_out_count': timeout_count,
                    'cutoff_time': cutoff_time.isoformat(),
                    'jobs': [
                        {
                            'id': job['id'],
                            'prompt': job['prompt'][:50] + '...',
                            'age_hours': (datetime.now() - job['created_at']).total_seconds() / 3600
                        }
                        for job in to_timeout
                    ]
                }

        except Exception as e:
            logger.error(f"Error force timing out jobs: {e}")
            return {'error': str(e)}


# Global tracker instance
tracker = None

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global tracker
    logger.info(f"Received signal {signum}, shutting down...")
    if tracker:
        tracker.stop()
    sys.exit(0)

async def main():
    """Main function to start monitoring"""
    global tracker

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    tracker = JobCompletionTracker()

    logger.info("=� Starting Anime Pipeline Completion Tracking Service")
    logger.info(f"=� ComfyUI URL: {COMFYUI_URL}")
    logger.info(f"=� Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    logger.info(f"� Check interval: {tracker.check_interval} seconds")
    logger.info(f"� Timeout threshold: {tracker.timeout_threshold}")

    await tracker.monitor_processing_jobs()

if __name__ == "__main__":
    asyncio.run(main())