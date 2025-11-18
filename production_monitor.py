#!/usr/bin/env python3
"""
Tower Anime Production Monitor - Production-grade monitoring and retry system
Location: /opt/tower-anime-production/production_monitor.py
Purpose: Real-time generation monitoring, failure detection, retry logic, and quality validation
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import httpx
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            "/opt/tower-anime-production/logs/production_monitor.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class ProductionMonitor:
    """Production-grade monitoring system for anime generation"""

    def __init__(self):
        self.db_config = {
            "host": "***REMOVED***",
            "database": "anime_production",
            "user": "patrick",
            "password": "***REMOVED***",
            "port": 5432,
            "options": "-c search_path=anime_api,public",
        }
        self.comfyui_url = "http://***REMOVED***:8188"
        self.echo_url = "https://***REMOVED***/api/echo"
        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
        self.max_generation_time = 1800  # 30 minutes max
        self.retry_attempts = 3
        self.quality_threshold = 0.6  # Minimum quality score

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config)

    async def check_comfyui_queue(self) -> Dict[str, Any]:
        """Check ComfyUI queue status"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.comfyui_url}/queue")
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(
                        f"ComfyUI queue check failed: {response.status_code}")
                    return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"Failed to check ComfyUI queue: {e}")
            return {"error": str(e)}

    async def get_generating_projects(self) -> List[Dict[str, Any]]:
        """Get all projects in generating status"""
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute(
                    """
                    SELECT id, name, description, status, created_at, updated_at,
                           metadata, generation_start_time, retry_count
                    FROM projects
                    WHERE status = 'generating'
                    ORDER BY created_at DESC
                """
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get generating projects: {e}")
            return []

    async def check_generation_timeout(self, project: Dict[str, Any]) -> bool:
        """Check if generation has timed out"""
        if not project.get("generation_start_time"):
            # If no start time, use created_at
            start_time = project["created_at"]
        else:
            start_time = project["generation_start_time"]

        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(
                start_time.replace("Z", "+00:00"))

        elapsed = datetime.now() - start_time.replace(tzinfo=None)
        return elapsed.total_seconds() > self.max_generation_time

    async def validate_output_quality(self, project_id: int) -> Dict[str, Any]:
        """Validate quality of generated video output"""
        try:
            # Find latest output file for this project
            output_files = list(self.output_dir.glob("*.mp4"))
            if not output_files:
                return {"valid": False, "reason": "No output files found"}

            # Get most recent file
            latest_file = max(output_files, key=os.path.getctime)

            # Basic video validation
            cap = cv2.VideoCapture(str(latest_file))
            if not cap.isOpened():
                return {"valid": False, "reason": "Cannot open video file"}

            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = frame_count / fps if fps > 0 else 0

            # Quality checks
            quality_score = 1.0
            issues = []

            # Check duration (should be > 1 second)
            if duration < 1.0:
                quality_score -= 0.3
                issues.append(f"Too short: {duration:.1f}s")

            # Check frame count (should have reasonable frames)
            if frame_count < 24:  # Less than 1 second at 24fps
                quality_score -= 0.3
                issues.append(f"Too few frames: {frame_count}")

            # Sample frames for visual quality
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            sample_frames = min(10, total_frames)

            for i in range(sample_frames):
                frame_pos = (i * total_frames) // sample_frames
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                ret, frame = cap.read()

                if ret:
                    # Check for completely black frames
                    if np.mean(frame) < 10:
                        quality_score -= 0.1
                        issues.append("Black frame detected")

                    # Check for very low variance (solid color)
                    if np.var(frame) < 100:
                        quality_score -= 0.05
                        issues.append("Low variance frame")

            cap.release()

            return {
                "valid": quality_score >= self.quality_threshold,
                "score": quality_score,
                "duration": duration,
                "frame_count": frame_count,
                "fps": fps,
                "file_path": str(latest_file),
                "issues": issues,
            }

        except Exception as e:
            logger.error(f"Quality validation failed: {e}")
            return {"valid": False, "reason": f"Validation error: {e}"}

    async def retry_failed_generation(self, project: Dict[str, Any]) -> bool:
        """Retry failed generation with exponential backoff"""
        try:
            retry_count = project.get("retry_count", 0)
            if retry_count >= self.retry_attempts:
                logger.warning(f"Project {project['id']} exceeded max retries")
                await self.mark_project_failed(project["id"])
                return False

            # Increment retry count
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE projects
                    SET retry_count = %s,
                        generation_start_time = %s,
                        updated_at = %s
                    WHERE id = %s
                """,
                    (retry_count + 1, datetime.now(),
                     datetime.now(), project["id"]),
                )
                conn.commit()

            # Wait with exponential backoff
            wait_time = (2**retry_count) * 60  # 1, 2, 4 minutes
            logger.info(
                f"Retrying project {project['id']} after {wait_time}s wait")
            await asyncio.sleep(wait_time)

            # Trigger retry via Echo Brain
            await self.trigger_retry_via_echo(project)
            return True

        except Exception as e:
            logger.error(f"Retry failed for project {project['id']}: {e}")
            return False

    async def trigger_retry_via_echo(self, project: Dict[str, Any]):
        """Trigger retry via Echo Brain's autonomous system"""
        try:
            retry_request = {
                "query": f"Retry anime generation for project {project['id']}: {project['name']}. Previous attempt failed or timed out. Use autonomous system to restart generation with quality validation.",
                "conversation_id": f"monitor_retry_{project['id']}",
                "metadata": {
                    "project_id": project["id"],
                    "retry_count": project.get("retry_count", 0) + 1,
                    "original_description": project.get("description", ""),
                    "trigger": "production_monitor",
                },
            }

            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                response = await client.post(
                    f"{self.echo_url}/query", json=retry_request
                )

                if response.status_code == 200:
                    logger.info(
                        f"Echo retry triggered for project {project['id']}")
                    return True
                else:
                    logger.error(f"Echo retry failed: {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"Failed to trigger Echo retry: {e}")
            return False

    async def mark_project_completed(
        self, project_id: int, output_info: Dict[str, Any]
    ):
        """Mark project as completed with output information"""
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE projects
                    SET status = 'completed',
                        updated_at = %s,
                        output_path = %s,
                        quality_score = %s,
                        completion_metadata = %s
                    WHERE id = %s
                """,
                    (
                        datetime.now(),
                        output_info.get("file_path"),
                        output_info.get("score"),
                        json.dumps(output_info),
                        project_id,
                    ),
                )
                conn.commit()
                logger.info(f"Project {project_id} marked as completed")

                # Notify Echo of completion
                await self.notify_echo_completion(project_id, output_info)

        except Exception as e:
            logger.error(f"Failed to mark project {project_id} completed: {e}")

    async def mark_project_failed(self, project_id: int):
        """Mark project as failed after max retries"""
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE projects
                    SET status = 'failed',
                        updated_at = %s,
                        failure_reason = %s
                    WHERE id = %s
                """,
                    (datetime.now(), "Max retries exceeded", project_id),
                )
                conn.commit()
                logger.warning(f"Project {project_id} marked as failed")

                # Notify Echo of failure
                await self.notify_echo_failure(project_id)

        except Exception as e:
            logger.error(f"Failed to mark project {project_id} as failed: {e}")

    async def notify_echo_completion(
        self, project_id: int, output_info: Dict[str, Any]
    ):
        """Notify Echo Brain of successful completion"""
        try:
            notification = {
                "query": f"Anime project {project_id} completed successfully. Quality score: {output_info.get('score', 'N/A')}. File: {output_info.get('file_path', 'N/A')}",
                "conversation_id": f"monitor_completion_{project_id}",
                "metadata": {
                    "event": "generation_completed",
                    "project_id": project_id,
                    "output_info": output_info,
                },
            }

            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                await client.post(f"{self.echo_url}/query", json=notification)

        except Exception as e:
            logger.error(f"Failed to notify Echo of completion: {e}")

    async def notify_echo_failure(self, project_id: int):
        """Notify Echo Brain of generation failure"""
        try:
            notification = {
                "query": f"Anime project {project_id} failed after max retries. Requires manual intervention.",
                "conversation_id": f"monitor_failure_{project_id}",
                "metadata": {
                    "event": "generation_failed",
                    "project_id": project_id,
                    "action_required": "manual_review",
                },
            }

            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                await client.post(f"{self.echo_url}/query", json=notification)

        except Exception as e:
            logger.error(f"Failed to notify Echo of failure: {e}")

    async def monitor_cycle(self):
        """Main monitoring cycle"""
        logger.info("Starting production monitoring cycle")

        # Get all generating projects
        generating_projects = await self.get_generating_projects()
        logger.info(
            f"Found {len(generating_projects)} projects in generating status")

        for project in generating_projects:
            try:
                project_id = project["id"]
                logger.info(
                    f"Monitoring project {project_id}: {project['name']}")

                # Check for timeout
                if await self.check_generation_timeout(project):
                    logger.warning(f"Project {project_id} timed out")
                    await self.retry_failed_generation(project)
                    continue

                # Check if output exists and validate quality
                quality_result = await self.validate_output_quality(project_id)

                if quality_result["valid"]:
                    logger.info(
                        f"Project {project_id} completed with quality score {quality_result['score']}"
                    )
                    await self.mark_project_completed(project_id, quality_result)
                elif "file_path" in quality_result:
                    # Output exists but low quality - retry
                    logger.warning(
                        f"Project {project_id} low quality: {quality_result['issues']}"
                    )
                    await self.retry_failed_generation(project)
                else:
                    # No output yet - check if still generating
                    queue_status = await self.check_comfyui_queue()
                    if not queue_status.get("queue_running") and not queue_status.get(
                        "queue_pending"
                    ):
                        # Nothing in queue but project still generating - likely failed
                        logger.warning(f"Project {project_id} appears stalled")
                        await self.retry_failed_generation(project)

            except Exception as e:
                logger.error(
                    f"Error monitoring project {project.get('id', 'unknown')}: {e}"
                )

    async def run_continuous_monitoring(self, interval: int = 60):
        """Run continuous monitoring every interval seconds"""
        logger.info(f"Starting continuous monitoring (interval: {interval}s)")

        while True:
            try:
                await self.monitor_cycle()
                await asyncio.sleep(interval)
            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Monitoring cycle error: {e}")
                await asyncio.sleep(interval)


async def main():
    """Main entry point"""
    monitor = ProductionMonitor()

    # Add missing database columns
    try:
        with monitor.get_db_connection() as conn:
            cursor = conn.cursor()
            # Add monitoring columns if they don't exist
            columns_to_add = [
                ("retry_count", "INTEGER DEFAULT 0"),
                ("generation_start_time", "TIMESTAMP"),
                ("output_path", "TEXT"),
                ("quality_score", "FLOAT"),
                ("completion_metadata", "TEXT"),
                ("failure_reason", "TEXT"),
            ]

            for column_name, column_def in columns_to_add:
                try:
                    cursor.execute(
                        f"ALTER TABLE projects ADD COLUMN {column_name} {column_def}"
                    )
                    logger.info(f"Added column {column_name}")
                except psycopg2.errors.DuplicateColumn:
                    pass  # Column already exists
                except Exception as e:
                    logger.warning(f"Could not add column {column_name}: {e}")

            conn.commit()
    except Exception as e:
        logger.error(f"Database setup error: {e}")

    # Start monitoring
    await monitor.run_continuous_monitoring()


if __name__ == "__main__":
    asyncio.run(main())
