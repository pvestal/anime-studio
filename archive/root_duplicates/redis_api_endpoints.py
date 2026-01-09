#!/usr/bin/env python3
"""
Redis-based API Endpoints for Anime Production
Replaces direct ComfyUI integration with Redis job queue system
"""

import asyncio
from fastapi import APIRouter, HTTPException, Depends
try:
    from sqlalchemy.orm import Session
except ImportError:
    # Fallback for non-SQLAlchemy environments
    Session = None
from datetime import datetime
from typing import Dict, Any, Optional
import logging
import json

logger = logging.getLogger(__name__)

# Simplified Redis integration without aioredis dependency issues
import redis
import uuid

REDIS_QUEUE_AVAILABLE = False
try:
    # Test basic Redis connection
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    r.ping()
    REDIS_QUEUE_AVAILABLE = True
    logger.info("✅ Redis server available")
except Exception as e:
    logger.warning(f"Redis server not available: {e}")

# Define job priority and status enums
class JobPriority:
    URGENT = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4

class JobStatus:
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

# Simple Redis job queue implementation
class SimpleRedisJobQueue:
    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

    async def enqueue_job(self, job_type, prompt, parameters, priority=JobPriority.NORMAL, database_job_id=None):
        """Enqueue a job"""
        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id,
            "job_type": job_type,
            "prompt": prompt,
            "parameters": json.dumps(parameters),
            "priority": priority,
            "status": JobStatus.QUEUED,
            "created_at": datetime.utcnow().isoformat(),
            "database_job_id": database_job_id
        }

        # Store job data
        self.redis_client.hset(f"job:{job_id}", mapping=job_data)

        # Add to priority queue
        queue_key = f"queue:priority_{priority}"
        self.redis_client.lpush(queue_key, job_id)

        return job_id

    async def get_job_status(self, job_id):
        """Get job status"""
        job_data = self.redis_client.hgetall(f"job:{job_id}")
        if not job_data:
            return None

        return {
            "id": job_data.get("id"),
            "status": job_data.get("status"),
            "progress": float(job_data.get("progress", 0)),
            "created_at": job_data.get("created_at"),
            "started_at": job_data.get("started_at"),
            "completed_at": job_data.get("completed_at")
        }

    async def get_queue_stats(self):
        """Get queue statistics"""
        stats = {
            "total_queued": 0,
            "jobs_completed": 0,
            "jobs_failed": 0,
            "jobs_cancelled": 0
        }

        # Count jobs in different priority queues
        for priority in [1, 2, 3, 4]:
            queue_key = f"queue:priority_{priority}"
            stats["total_queued"] += self.redis_client.llen(queue_key)

        return stats

    async def cancel_job(self, job_id):
        """Cancel a job"""
        job_data = self.redis_client.hgetall(f"job:{job_id}")
        if not job_data:
            return False

        # Update status to cancelled
        self.redis_client.hset(f"job:{job_id}", "status", JobStatus.CANCELLED)
        return True

# Import database models and dependencies
try:
    from api.main import get_db, ProductionJob
except ImportError:
    # Fallback imports for when running from main anime_api.py
    import sys
    sys.path.append('/opt/tower-anime-production/api')
    from main import get_db, ProductionJob

# Create router for Redis-based endpoints
redis_router = APIRouter()

# Global job queue instance
job_queue_instance: Optional[SimpleRedisJobQueue] = None

# Database configuration
DB_CONFIG = {
    "host": "192.168.50.135",
    "database": "anime_production",
    "user": "patrick",
    "password": "tower_echo_brain_secret_key_2025",
    "port": 5432,
    "options": "-c search_path=anime_api,public",
}

async def get_job_queue() -> SimpleRedisJobQueue:
    """Get or create job queue instance"""
    global job_queue_instance
    if not REDIS_QUEUE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Redis server not available")
    if job_queue_instance is None:
        job_queue_instance = SimpleRedisJobQueue()
    return job_queue_instance

@redis_router.post("/api/anime/generate-redis")
async def generate_anime_video_redis(
    request: dict  # AnimeGenerationRequest
):
    """
    Generate anime video using Redis job queue
    This replaces the broken direct ComfyUI integration
    """
    try:
        # Validate request
        prompt = request.get("prompt", "")
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt is required")

        character = request.get("character", "generic")
        style = request.get("style", "anime")
        duration = request.get("duration", 5)

        # Determine priority based on duration (shorter = higher priority)
        if duration <= 2:
            priority = JobPriority.HIGH
        elif duration <= 5:
            priority = JobPriority.NORMAL
        else:
            priority = JobPriority.LOW

        logger.info(f"🎬 Redis generation request: {prompt[:50]}... (duration: {duration}s)")

        # Create database job record first using PostgreSQL
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(**DB_CONFIG)
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Insert job record
            cursor.execute("""
                INSERT INTO production_jobs (job_type, prompt, parameters, status, generation_start_time)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            """, (
                "redis_video_generation",
                prompt,
                json.dumps(request),
                "queued",
                datetime.utcnow()
            ))

            db_job_id = cursor.fetchone()['id']
            conn.commit()

            # Submit to Redis queue
            job_queue = await get_job_queue()
            redis_job_id = await job_queue.enqueue_job(
                job_type="anime_generation",
                prompt=prompt,
                parameters={
                    "prompt": prompt,
                    "character": character,
                    "style": style,
                    "duration": duration,
                    "seed": request.get("seed", int(datetime.utcnow().timestamp())),
                    "database_job_id": db_job_id
                },
                priority=priority,
                database_job_id=db_job_id
            )

            # Update database job with Redis ID
            cursor.execute("""
                UPDATE production_jobs SET comfyui_job_id = %s WHERE id = %s
            """, (redis_job_id, db_job_id))
            conn.commit()

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

        # Get initial queue position
        stats = await job_queue.get_queue_stats()
        queue_position = stats.get("total_queued", 0)

        logger.info(f"✅ Job queued: DB#{db_job_id}, Redis#{redis_job_id[:8]}, Position: {queue_position}")

        # Convert priority to string
        priority_name = getattr(priority, 'name', str(priority)).lower()

        return {
            "job_id": db_job_id,
            "redis_job_id": redis_job_id,
            "status": "queued",
            "priority": priority_name,
            "queue_position": queue_position,
            "estimated_wait_time": f"{queue_position * 2} minutes",
            "message": "Job queued for processing with Redis job queue",
            "poll_url": f"/api/anime/generation/{db_job_id}/status",
            "redis_poll_url": f"/api/anime/redis-job/{redis_job_id}/status"
        }

    except Exception as e:
        logger.error(f"❌ Redis generation failed: {e}")

        # Update database job if it was created
        if 'db_job_id' in locals():
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE production_jobs SET status = %s WHERE id = %s
                """, ("failed", db_job_id))
                conn.commit()
                conn.close()
            except Exception as db_error:
                logger.error(f"Failed to update database job status: {db_error}")

        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue job: {str(e)}"
        )

@redis_router.get("/api/anime/redis-job/{redis_job_id}/status")
async def get_redis_job_status(redis_job_id: str):
    """Get status of a Redis job by its Redis ID"""
    try:
        job_queue = await get_job_queue()
        status = await job_queue.get_job_status(redis_job_id)

        if not status:
            raise HTTPException(status_code=404, detail="Job not found")

        # Add additional helpful information
        if status["status"] == "queued":
            # Get queue position
            stats = await job_queue.get_queue_stats()
            status["queue_stats"] = stats

        elif status["status"] == "processing":
            # Add processing details
            status["processing_details"] = {
                "phase": "generation" if status["progress"] < 90 else "finalization",
                "comfyui_job_id": status.get("comfyui_job_id")
            }

        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting Redis job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@redis_router.post("/api/anime/redis-job/{redis_job_id}/cancel")
async def cancel_redis_job(redis_job_id: str):
    """Cancel a Redis job"""
    try:
        job_queue = await get_job_queue()
        success = await job_queue.cancel_job(redis_job_id)

        if success:
            return {
                "status": "cancelled",
                "message": "Job cancelled successfully",
                "job_id": redis_job_id
            }
        else:
            return {
                "status": "not_cancelled",
                "message": "Job could not be cancelled (may be already processing or completed)",
                "job_id": redis_job_id
            }

    except Exception as e:
        logger.error(f"❌ Error cancelling Redis job: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@redis_router.get("/api/anime/redis-queue/stats")
async def get_redis_queue_stats():
    """Get Redis queue statistics"""
    try:
        job_queue = await get_job_queue()
        stats = await job_queue.get_queue_stats()

        # Add derived statistics
        total_jobs = sum([
            stats.get("jobs_queued", 0),
            stats.get("jobs_completed", 0),
            stats.get("jobs_failed", 0),
            stats.get("jobs_cancelled", 0)
        ])

        success_rate = 0
        if total_jobs > 0:
            completed = stats.get("jobs_completed", 0)
            success_rate = (completed / total_jobs) * 100

        enhanced_stats = {
            **stats,
            "total_jobs_processed": total_jobs,
            "success_rate_percent": round(success_rate, 2),
            "average_queue_time_estimate": f"{stats.get('total_queued', 0) * 2} minutes"
        }

        return enhanced_stats

    except Exception as e:
        logger.error(f"❌ Error getting queue stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@redis_router.post("/api/anime/redis-queue/maintenance")
async def perform_queue_maintenance():
    """Perform queue maintenance operations"""
    try:
        job_queue = await get_job_queue()

        # Clean up old jobs
        cleaned = await job_queue.cleanup_old_jobs(max_age_hours=24)

        # Retry failed jobs
        retried = await job_queue.retry_failed_jobs()

        # Handle timeouts
        timeouts = await job_queue.handle_timeout_jobs()

        return {
            "status": "completed",
            "operations": {
                "old_jobs_cleaned": cleaned,
                "failed_jobs_retried": retried,
                "timeout_jobs_handled": timeouts
            },
            "message": "Queue maintenance completed successfully"
        }

    except Exception as e:
        logger.error(f"❌ Queue maintenance failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@redis_router.get("/api/anime/generation/{db_job_id}/status")
async def get_generation_status_enhanced(db_job_id: int):
    """
    Enhanced generation status that checks both database and Redis
    This replaces the broken status endpoint
    """
    try:
        # Get database job using PostgreSQL
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(**DB_CONFIG)
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT id, status, prompt, created_at, output_path, comfyui_job_id
                FROM production_jobs WHERE id = %s
            """, (db_job_id,))

            db_job = cursor.fetchone()
            if not db_job:
                raise HTTPException(status_code=404, detail="Job not found")

            # Prepare base response from database
            response = {
                "job_id": db_job["id"],
                "status": db_job["status"],
                "prompt": db_job["prompt"],
                "created_at": db_job["created_at"].isoformat() if db_job["created_at"] else None,
                "output_path": db_job["output_path"]
            }

            # If job has Redis ID, get live Redis status
            redis_job_id = db_job["comfyui_job_id"]  # We store Redis ID here

        finally:
            conn.close()
        if redis_job_id:
            try:
                job_queue = await get_job_queue()
                redis_status = await job_queue.get_job_status(redis_job_id)

                if redis_status:
                    # Override database status with live Redis status
                    response.update({
                        "status": redis_status["status"],
                        "progress": redis_status["progress"],
                        "redis_job_id": redis_job_id,
                        "live_status": True,
                        "eta_seconds": redis_status.get("eta_seconds"),
                        "retry_count": redis_status.get("retry_count", 0),
                        "comfyui_job_id": redis_status.get("comfyui_job_id"),
                        "last_updated": redis_status.get("started_at") or redis_status.get("created_at")
                    })

                    # Add queue position if queued
                    if redis_status["status"] == "queued":
                        stats = await job_queue.get_queue_stats()
                        response["queue_position"] = stats.get("total_queued", 0)

                else:
                    # Redis job not found, but database job exists
                    response["live_status"] = False
                    response["redis_note"] = "Redis job data not available"

            except Exception as redis_error:
                logger.warning(f"Redis status check failed for job {db_job_id}: {redis_error}")
                response["live_status"] = False
                response["redis_error"] = str(redis_error)

        else:
            # No Redis job ID (legacy job or non-Redis job)
            response["live_status"] = False
            response["redis_note"] = "Job not processed through Redis queue"

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting enhanced status for job {db_job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@redis_router.post("/api/anime/generate-priority")
async def generate_anime_video_priority(
    request: dict,
    priority: str = "normal"  # urgent, high, normal, low
):
    """Generate anime video with explicit priority"""

    # Map string priority to enum
    priority_map = {
        "urgent": JobPriority.URGENT,
        "high": JobPriority.HIGH,
        "normal": JobPriority.NORMAL,
        "low": JobPriority.LOW
    }

    if priority not in priority_map:
        raise HTTPException(
            status_code=400,
            detail="Priority must be one of: urgent, high, normal, low"
        )

    # Use the same logic as generate_anime_video_redis but with explicit priority
    request["priority"] = priority_map[priority]
    return await generate_anime_video_redis(request)

# Utility endpoint for testing
@redis_router.post("/api/anime/redis-test")
async def test_redis_queue():
    """Test Redis queue connectivity and basic operations"""
    try:
        job_queue = await get_job_queue()

        # Submit test job
        test_job_id = await job_queue.enqueue_job(
            job_type="test",
            prompt="Test Redis queue integration",
            parameters={"test": True},
            priority=JobPriority.LOW
        )

        # Get status
        status = await job_queue.get_job_status(test_job_id)

        # Get stats
        stats = await job_queue.get_queue_stats()

        # Cancel test job
        await job_queue.cancel_job(test_job_id)

        return {
            "status": "success",
            "message": "Redis queue test completed successfully",
            "test_job_id": test_job_id,
            "test_status": status,
            "queue_stats": stats
        }

    except Exception as e:
        logger.error(f"❌ Redis queue test failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Redis queue test failed: {str(e)}"
        )

# Health check endpoint
@redis_router.get("/api/anime/redis-health")
async def redis_health_check():
    """Check Redis and job queue health"""
    if not REDIS_QUEUE_AVAILABLE:
        return {
            "status": "redis_unavailable",
            "redis_connected": False,
            "error": "Redis queue system not available - aioredis dependency missing",
            "timestamp": datetime.utcnow().isoformat(),
            "fallback_note": "Database operations still work, but Redis queue features are disabled"
        }

    try:
        job_queue = await get_job_queue()

        # Test basic Redis operations
        job_queue.redis_client.ping()

        # Get basic stats
        stats = await job_queue.get_queue_stats()

        return {
            "status": "healthy",
            "redis_connected": True,
            "queue_stats": stats,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Redis health check failed: {e}")
        return {
            "status": "unhealthy",
            "redis_connected": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# Export the router for integration
__all__ = ["redis_router"]