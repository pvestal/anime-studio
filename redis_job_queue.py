#!/usr/bin/env python3
"""
Redis-based Job Queue System for Anime Production
Replaces the broken ComfyUI direct queue with reliable Redis queue management
"""

import redis
import json
import uuid
import time
import asyncio
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass, asdict
import aioredis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JobPriority(Enum):
    URGENT = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4

class JobStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

@dataclass
class Job:
    """Job data structure"""
    id: str
    job_type: str
    prompt: str
    parameters: Dict[str, Any]
    priority: JobPriority
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: int = 1800  # 30 minutes default
    comfyui_job_id: Optional[str] = None
    database_job_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Redis storage"""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        for field in ['created_at', 'started_at', 'completed_at']:
            if data[field]:
                data[field] = data[field].isoformat()
        # Convert enums to values
        data['priority'] = data['priority'].value
        data['status'] = data['status'].value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Job':
        """Create Job from dictionary"""
        # Convert ISO strings back to datetime objects
        for field in ['created_at', 'started_at', 'completed_at']:
            if data[field]:
                data[field] = datetime.fromisoformat(data[field])
        # Convert values back to enums
        data['priority'] = JobPriority(data['priority'])
        data['status'] = JobStatus(data['status'])
        return cls(**data)

class RedisJobQueue:
    """Redis-based job queue with priority handling and progress tracking"""

    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.redis_client = None
        self.async_redis_client = None

        # Queue names for different priorities
        self.queue_names = {
            JobPriority.URGENT: "anime_queue:urgent",
            JobPriority.HIGH: "anime_queue:high",
            JobPriority.NORMAL: "anime_queue:normal",
            JobPriority.LOW: "anime_queue:low"
        }

        # Keys for job storage
        self.jobs_key = "anime_jobs"
        self.processing_key = "anime_processing"
        self.results_key = "anime_results"
        self.stats_key = "anime_stats"

        # Database configuration for anime_production
        self.db_config = {
            "host": "localhost",
            "database": "anime_production",
            "user": "patrick",
            "password": "tower_echo_brain_secret_key_2025",
            "port": 5432,
            "options": "-c search_path=anime_api,public"
        }

    async def initialize(self):
        """Initialize Redis connections"""
        self.redis_client = redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            db=self.redis_db,
            decode_responses=True
        )

        self.async_redis_client = await aioredis.from_url(
            f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}",
            decode_responses=True
        )

        logger.info(f"✅ Redis job queue initialized: {self.redis_host}:{self.redis_port}")

    def get_db_connection(self):
        """Get PostgreSQL database connection"""
        return psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)

    async def enqueue_job(self, job_type: str, prompt: str, parameters: Dict[str, Any],
                         priority: JobPriority = JobPriority.NORMAL,
                         database_job_id: Optional[int] = None) -> str:
        """Add a job to the appropriate priority queue"""

        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            job_type=job_type,
            prompt=prompt,
            parameters=parameters,
            priority=priority,
            status=JobStatus.QUEUED,
            created_at=datetime.utcnow(),
            database_job_id=database_job_id
        )

        # Store job data
        await self.async_redis_client.hset(
            self.jobs_key,
            job_id,
            json.dumps(job.to_dict())
        )

        # Add to appropriate priority queue
        queue_name = self.queue_names[priority]
        await self.async_redis_client.lpush(queue_name, job_id)

        # Update database status if linked
        if database_job_id:
            await self.update_database_job_status(database_job_id, JobStatus.QUEUED, job_id)

        # Update stats
        await self.async_redis_client.hincrby(self.stats_key, "jobs_queued", 1)

        logger.info(f"📋 Job {job_id[:8]} queued with {priority.name} priority")
        return job_id

    async def dequeue_job(self) -> Optional[Job]:
        """Get the next job from highest priority queue"""

        # Check queues in priority order
        for priority in [JobPriority.URGENT, JobPriority.HIGH, JobPriority.NORMAL, JobPriority.LOW]:
            queue_name = self.queue_names[priority]

            # Use blocking pop with timeout
            result = await self.async_redis_client.brpop(queue_name, timeout=1)
            if result:
                _, job_id = result

                # Get job data
                job_data = await self.async_redis_client.hget(self.jobs_key, job_id)
                if job_data:
                    job = Job.from_dict(json.loads(job_data))

                    # Mark as processing
                    job.status = JobStatus.PROCESSING
                    job.started_at = datetime.utcnow()

                    # Update stored job data
                    await self.async_redis_client.hset(
                        self.jobs_key,
                        job_id,
                        json.dumps(job.to_dict())
                    )

                    # Add to processing set
                    await self.async_redis_client.sadd(self.processing_key, job_id)

                    # Update database if linked
                    if job.database_job_id:
                        await self.update_database_job_status(job.database_job_id, JobStatus.PROCESSING)

                    logger.info(f"🔄 Job {job_id[:8]} dequeued for processing")
                    return job

        return None

    async def update_job_progress(self, job_id: str, progress: float,
                                status: Optional[JobStatus] = None,
                                comfyui_job_id: Optional[str] = None):
        """Update job progress and optionally status"""

        job_data = await self.async_redis_client.hget(self.jobs_key, job_id)
        if not job_data:
            logger.warning(f"Job {job_id[:8]} not found for progress update")
            return False

        job = Job.from_dict(json.loads(job_data))
        job.progress = max(0.0, min(100.0, progress))

        if status:
            job.status = status
        if comfyui_job_id:
            job.comfyui_job_id = comfyui_job_id

        # Update stored data
        await self.async_redis_client.hset(
            self.jobs_key,
            job_id,
            json.dumps(job.to_dict())
        )

        # Update database if linked
        if job.database_job_id:
            await self.update_database_job_progress(job.database_job_id, progress)

        logger.debug(f"📊 Job {job_id[:8]} progress: {progress:.1f}%")
        return True

    async def complete_job(self, job_id: str, result: Optional[Dict[str, Any]] = None,
                          error: Optional[str] = None):
        """Mark job as completed or failed"""

        job_data = await self.async_redis_client.hget(self.jobs_key, job_id)
        if not job_data:
            logger.warning(f"Job {job_id[:8]} not found for completion")
            return False

        job = Job.from_dict(json.loads(job_data))
        job.completed_at = datetime.utcnow()
        job.progress = 100.0 if not error else job.progress

        if error:
            job.status = JobStatus.FAILED
            job.error = error
            await self.async_redis_client.hincrby(self.stats_key, "jobs_failed", 1)
        else:
            job.status = JobStatus.COMPLETED
            job.result = result
            await self.async_redis_client.hincrby(self.stats_key, "jobs_completed", 1)

        # Update stored data
        await self.async_redis_client.hset(
            self.jobs_key,
            job_id,
            json.dumps(job.to_dict())
        )

        # Remove from processing set
        await self.async_redis_client.srem(self.processing_key, job_id)

        # Store result for retrieval
        if result:
            await self.async_redis_client.hset(
                self.results_key,
                job_id,
                json.dumps(result)
            )

        # Update database if linked
        if job.database_job_id:
            final_status = JobStatus.COMPLETED if not error else JobStatus.FAILED
            await self.update_database_job_completion(
                job.database_job_id,
                final_status,
                result.get('output_path') if result else None,
                error
            )

        processing_time = (job.completed_at - job.started_at).total_seconds() if job.started_at else 0
        status_emoji = "✅" if not error else "❌"
        logger.info(f"{status_emoji} Job {job_id[:8]} {job.status.value} in {processing_time:.1f}s")

        return True

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job (if not yet processing)"""

        job_data = await self.async_redis_client.hget(self.jobs_key, job_id)
        if not job_data:
            return False

        job = Job.from_dict(json.loads(job_data))

        # Can only cancel queued jobs
        if job.status != JobStatus.QUEUED:
            logger.warning(f"Cannot cancel job {job_id[:8]} - status: {job.status.value}")
            return False

        # Remove from queue
        queue_name = self.queue_names[job.priority]
        removed = await self.async_redis_client.lrem(queue_name, 0, job_id)

        if removed:
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.utcnow()

            # Update stored data
            await self.async_redis_client.hset(
                self.jobs_key,
                job_id,
                json.dumps(job.to_dict())
            )

            # Update database if linked
            if job.database_job_id:
                await self.update_database_job_status(job.database_job_id, JobStatus.CANCELLED)

            await self.async_redis_client.hincrby(self.stats_key, "jobs_cancelled", 1)
            logger.info(f"🚫 Job {job_id[:8]} cancelled")
            return True

        return False

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get current job status and progress"""

        job_data = await self.async_redis_client.hget(self.jobs_key, job_id)
        if not job_data:
            return None

        job = Job.from_dict(json.loads(job_data))

        # Calculate estimated time remaining
        eta_seconds = None
        if job.status == JobStatus.PROCESSING and job.started_at and job.progress > 0:
            elapsed = (datetime.utcnow() - job.started_at).total_seconds()
            if job.progress < 100:
                eta_seconds = (elapsed / job.progress) * (100 - job.progress)

        return {
            "job_id": job.id,
            "status": job.status.value,
            "progress": job.progress,
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "eta_seconds": int(eta_seconds) if eta_seconds else None,
            "retry_count": job.retry_count,
            "error": job.error,
            "comfyui_job_id": job.comfyui_job_id,
            "database_job_id": job.database_job_id
        }

    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""

        stats = {}

        # Queue lengths
        for priority, queue_name in self.queue_names.items():
            length = await self.async_redis_client.llen(queue_name)
            stats[f"queue_{priority.name.lower()}"] = length

        # Processing count
        processing_count = await self.async_redis_client.scard(self.processing_key)
        stats["processing"] = processing_count

        # Overall stats
        redis_stats = await self.async_redis_client.hgetall(self.stats_key)
        for key, value in redis_stats.items():
            stats[key] = int(value)

        # Total queued
        stats["total_queued"] = sum(stats[f"queue_{p.name.lower()}"] for p in JobPriority)

        return stats

    async def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Clean up old completed/failed jobs"""

        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        cleaned_count = 0

        # Get all job IDs
        all_jobs = await self.async_redis_client.hgetall(self.jobs_key)

        for job_id, job_data in all_jobs.items():
            try:
                job = Job.from_dict(json.loads(job_data))

                # Clean up old completed/failed jobs
                if (job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
                    and job.completed_at and job.completed_at < cutoff_time):

                    # Remove job data
                    await self.async_redis_client.hdel(self.jobs_key, job_id)
                    await self.async_redis_client.hdel(self.results_key, job_id)
                    cleaned_count += 1

            except Exception as e:
                logger.warning(f"Error cleaning job {job_id[:8]}: {e}")

        if cleaned_count > 0:
            logger.info(f"🧹 Cleaned up {cleaned_count} old jobs")

        return cleaned_count

    async def retry_failed_jobs(self) -> int:
        """Retry failed jobs that haven't exceeded max retries"""

        retried_count = 0
        all_jobs = await self.async_redis_client.hgetall(self.jobs_key)

        for job_id, job_data in all_jobs.items():
            try:
                job = Job.from_dict(json.loads(job_data))

                if (job.status == JobStatus.FAILED and
                    job.retry_count < job.max_retries):

                    # Reset job for retry
                    job.status = JobStatus.QUEUED
                    job.retry_count += 1
                    job.started_at = None
                    job.completed_at = None
                    job.progress = 0.0
                    job.error = None

                    # Update stored data
                    await self.async_redis_client.hset(
                        self.jobs_key,
                        job_id,
                        json.dumps(job.to_dict())
                    )

                    # Re-queue job
                    queue_name = self.queue_names[job.priority]
                    await self.async_redis_client.lpush(queue_name, job_id)

                    # Update database if linked
                    if job.database_job_id:
                        await self.update_database_job_status(job.database_job_id, JobStatus.QUEUED)

                    retried_count += 1
                    logger.info(f"🔄 Retrying job {job_id[:8]} (attempt {job.retry_count})")

            except Exception as e:
                logger.warning(f"Error retrying job {job_id[:8]}: {e}")

        return retried_count

    # Database integration methods

    async def update_database_job_status(self, database_job_id: int, status: JobStatus,
                                       redis_job_id: Optional[str] = None):
        """Update production_jobs table status"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            # Map our statuses to database statuses
            status_map = {
                JobStatus.QUEUED: "queued",
                JobStatus.PROCESSING: "processing",
                JobStatus.COMPLETED: "completed",
                JobStatus.FAILED: "failed",
                JobStatus.CANCELLED: "failed",
                JobStatus.TIMEOUT: "failed"
            }

            db_status = status_map.get(status, "processing")

            if redis_job_id:
                cursor.execute("""
                    UPDATE production_jobs
                    SET status = %s, comfyui_job_id = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (db_status, redis_job_id, database_job_id))
            else:
                cursor.execute("""
                    UPDATE production_jobs
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (db_status, database_job_id))

            conn.commit()
            cursor.close()
            conn.close()

        except Exception as e:
            logger.error(f"Error updating database job status: {e}")

    async def update_database_job_progress(self, database_job_id: int, progress: float):
        """Update job progress in database (if column exists)"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            # Note: production_jobs table doesn't have progress column yet
            # This is a placeholder for future enhancement
            cursor.execute("""
                UPDATE production_jobs
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (database_job_id,))

            conn.commit()
            cursor.close()
            conn.close()

        except Exception as e:
            logger.debug(f"Note: Database progress update not implemented: {e}")

    async def update_database_job_completion(self, database_job_id: int, status: JobStatus,
                                          output_path: Optional[str] = None,
                                          error: Optional[str] = None):
        """Update job completion in database"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            status_map = {
                JobStatus.COMPLETED: "completed",
                JobStatus.FAILED: "failed",
                JobStatus.CANCELLED: "failed",
                JobStatus.TIMEOUT: "failed"
            }

            db_status = status_map.get(status, "failed")

            if output_path:
                cursor.execute("""
                    UPDATE production_jobs
                    SET status = %s, output_path = %s,
                        generation_end_time = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (db_status, output_path, database_job_id))
            else:
                cursor.execute("""
                    UPDATE production_jobs
                    SET status = %s, failure_reason = %s,
                        generation_end_time = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (db_status, error, database_job_id))

            conn.commit()
            cursor.close()
            conn.close()

        except Exception as e:
            logger.error(f"Error updating database job completion: {e}")

    async def handle_timeout_jobs(self):
        """Check for timed out jobs and mark them as failed"""
        current_time = datetime.utcnow()
        timeout_count = 0

        processing_jobs = await self.async_redis_client.smembers(self.processing_key)

        for job_id in processing_jobs:
            job_data = await self.async_redis_client.hget(self.jobs_key, job_id)
            if not job_data:
                continue

            try:
                job = Job.from_dict(json.loads(job_data))

                # Check if job has timed out
                if (job.started_at and
                    (current_time - job.started_at).total_seconds() > job.timeout_seconds):

                    await self.complete_job(
                        job_id,
                        error=f"Job timed out after {job.timeout_seconds} seconds"
                    )
                    timeout_count += 1

            except Exception as e:
                logger.warning(f"Error checking timeout for job {job_id[:8]}: {e}")

        if timeout_count > 0:
            logger.warning(f"⏰ {timeout_count} jobs timed out")

        return timeout_count

# Convenience functions for easy integration

async def create_job_queue() -> RedisJobQueue:
    """Create and initialize a job queue instance"""
    queue = RedisJobQueue()
    await queue.initialize()
    return queue

async def submit_anime_generation_job(prompt: str, parameters: Dict[str, Any],
                                     database_job_id: Optional[int] = None,
                                     priority: JobPriority = JobPriority.NORMAL) -> str:
    """Submit an anime generation job to the queue"""
    queue = await create_job_queue()
    job_id = await queue.enqueue_job(
        job_type="anime_generation",
        prompt=prompt,
        parameters=parameters,
        priority=priority,
        database_job_id=database_job_id
    )
    return job_id

if __name__ == "__main__":
    # Test the job queue
    async def test_queue():
        queue = await create_job_queue()

        # Submit test job
        job_id = await queue.enqueue_job(
            job_type="test",
            prompt="Generate a test anime scene",
            parameters={"style": "anime", "duration": 5},
            priority=JobPriority.HIGH
        )

        print(f"✅ Test job queued: {job_id}")

        # Check status
        status = await queue.get_job_status(job_id)
        print(f"📊 Job status: {status}")

        # Get queue stats
        stats = await queue.get_queue_stats()
        print(f"📈 Queue stats: {stats}")

    asyncio.run(test_queue())