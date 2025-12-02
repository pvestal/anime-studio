#!/usr/bin/env python3
"""Redis-based job queue for non-blocking anime generation operations"""

import redis
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AnimeJobQueue:
    """Manages anime generation jobs using Redis for non-blocking GPU operations"""

    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=1):
        self.redis = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
        self.job_prefix = 'anime:job:'
        self.queue_key = 'anime:job:queue'
        self.processing_key = 'anime:job:processing'

    def add_job(self, project_id: str, job_type: str, params: Dict[str, Any]) -> str:
        """Add a new job to the queue"""
        import uuid
        job_id = str(uuid.uuid4())

        job_data = {
            'id': job_id,
            'project_id': project_id,
            'type': job_type,
            'params': json.dumps(params),
            'status': 'queued',
            'progress': 0,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        # Store job data
        self.redis.hmset(f'{self.job_prefix}{job_id}', job_data)

        # Add to queue
        self.redis.lpush(self.queue_key, job_id)

        logger.info(f"Added job {job_id} to queue for project {project_id}")
        return job_id

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status of a job"""
        job_data = self.redis.hgetall(f'{self.job_prefix}{job_id}')
        if job_data:
            job_data['params'] = json.loads(job_data.get('params', '{}'))
            return job_data
        return None

    def update_job_progress(self, job_id: str, progress: int, status: str = None):
        """Update job progress and optionally status"""
        updates = {
            'progress': progress,
            'updated_at': datetime.now().isoformat()
        }
        if status:
            updates['status'] = status

        self.redis.hmset(f'{self.job_prefix}{job_id}', updates)
        logger.info(f"Updated job {job_id}: progress={progress}, status={status}")

    def get_next_job(self) -> Optional[str]:
        """Get the next job from the queue"""
        # Move job from queue to processing
        job_id = self.redis.rpoplpush(self.queue_key, self.processing_key)
        if job_id:
            self.update_job_progress(job_id, 0, 'processing')
            logger.info(f"Processing job {job_id}")
        return job_id

    def complete_job(self, job_id: str, result: Dict[str, Any] = None):
        """Mark a job as completed"""
        updates = {
            'status': 'completed',
            'progress': 100,
            'completed_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        if result:
            updates['result'] = json.dumps(result)

        self.redis.hmset(f'{self.job_prefix}{job_id}', updates)
        self.redis.lrem(self.processing_key, 1, job_id)
        logger.info(f"Completed job {job_id}")

    def fail_job(self, job_id: str, error: str):
        """Mark a job as failed"""
        updates = {
            'status': 'failed',
            'error': error,
            'failed_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        self.redis.hmset(f'{self.job_prefix}{job_id}', updates)
        self.redis.lrem(self.processing_key, 1, job_id)
        logger.error(f"Failed job {job_id}: {error}")

    def get_queue_length(self) -> int:
        """Get the number of jobs in the queue"""
        return self.redis.llen(self.queue_key)

    def get_processing_count(self) -> int:
        """Get the number of jobs currently being processed"""
        return self.redis.llen(self.processing_key)

async def job_worker(queue: AnimeJobQueue):
    """Worker that processes jobs from the queue"""
    while True:
        try:
            job_id = queue.get_next_job()
            if job_id:
                job_data = queue.get_job_status(job_id)
                logger.info(f"Processing job {job_id}: {job_data['type']}")

                # Simulate processing with progress updates
                for progress in range(10, 100, 10):
                    queue.update_job_progress(job_id, progress)
                    await asyncio.sleep(1)  # Replace with actual ComfyUI interaction

                # Complete the job
                queue.complete_job(job_id, {'output': f'/mnt/1TB-storage/anime-projects/{job_data["project_id"]}/output.mp4'})
            else:
                await asyncio.sleep(1)  # Wait if no jobs

        except Exception as e:
            logger.error(f"Worker error: {e}")
            if job_id:
                queue.fail_job(job_id, str(e))
            await asyncio.sleep(5)

if __name__ == '__main__':
    queue = AnimeJobQueue()
    print(f"Anime job queue initialized. Queue length: {queue.get_queue_length()}")

    # Run worker
    asyncio.run(job_worker(queue))