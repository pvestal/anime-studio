"""
Job Manager Module
Manages generation job lifecycle
"""
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Job status enumeration"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class JobType(Enum):
    """Job type enumeration"""
    IMAGE = "image"
    VIDEO = "video"
    BATCH = "batch"


class Job:
    """Represents a generation job"""

    def __init__(self, job_id: int, job_type: JobType, prompt: str, parameters: Dict = None):
        self.id = job_id
        self.type = job_type
        self.prompt = prompt
        self.parameters = parameters or {}
        self.status = JobStatus.QUEUED
        self.comfyui_id = None
        self.output_path = None
        self.created_at = datetime.utcnow()
        self.started_at = None
        self.completed_at = None
        self.error_message = None
        self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "prompt": self.prompt,
            "parameters": self.parameters,
            "status": self.status.value,
            "comfyui_id": self.comfyui_id,
            "output_path": self.output_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "metadata": self.metadata
        }


class JobManager:
    """Manages job lifecycle and tracking"""

    def __init__(self, database_manager=None):
        self.jobs = {}  # In-memory storage for now
        self.next_job_id = 1
        self.database = database_manager

    def create_job(self, job_type: JobType, prompt: str, parameters: Dict = None) -> Job:
        """Create a new job"""
        job = Job(self.next_job_id, job_type, prompt, parameters)
        self.jobs[job.id] = job
        self.next_job_id += 1

        logger.info(f"Created job {job.id}: {job_type.value}")

        # Save to database if available
        if self.database:
            self.database.save_job(job)

        return job

    def get_job(self, job_id: int) -> Optional[Job]:
        """Get job by ID"""
        return self.jobs.get(job_id)

    def update_job_status(self, job_id: int, status: JobStatus, **kwargs) -> bool:
        """Update job status and optional fields"""
        job = self.get_job(job_id)
        if not job:
            return False

        job.status = status

        # Update timestamps
        if status == JobStatus.PROCESSING and not job.started_at:
            job.started_at = datetime.utcnow()
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.TIMEOUT]:
            job.completed_at = datetime.utcnow()

        # Update optional fields
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)

        logger.info(f"Updated job {job_id} status to {status.value}")

        # Update in database if available
        if self.database:
            self.database.update_job(job)

        return True

    def list_jobs(self, status: Optional[JobStatus] = None, limit: int = 50) -> List[Job]:
        """List jobs with optional status filter"""
        jobs = list(self.jobs.values())

        if status:
            jobs = [j for j in jobs if j.status == status]

        # Sort by creation time (newest first)
        jobs.sort(key=lambda x: x.created_at, reverse=True)

        return jobs[:limit]

    def cleanup_old_jobs(self, hours: int = 24) -> int:
        """Remove completed jobs older than specified hours"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        removed = 0

        for job_id in list(self.jobs.keys()):
            job = self.jobs[job_id]
            if job.status == JobStatus.COMPLETED and job.completed_at < cutoff:
                del self.jobs[job_id]
                removed += 1

        logger.info(f"Cleaned up {removed} old jobs")
        return removed

    def get_statistics(self) -> Dict[str, Any]:
        """Get job statistics"""
        stats = {
            "total": len(self.jobs),
            "by_status": {},
            "by_type": {}
        }

        for job in self.jobs.values():
            # Count by status
            status_key = job.status.value
            stats["by_status"][status_key] = stats["by_status"].get(status_key, 0) + 1

            # Count by type
            type_key = job.type.value
            stats["by_type"][type_key] = stats["by_type"].get(type_key, 0) + 1

        return stats