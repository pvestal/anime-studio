"""
Job Manager Module
Manages generation job lifecycle
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum
import json
import logging
import asyncio

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Job status enumeration"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    RECOVERING = "recovering"  # New status for error recovery


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
        self.original_parameters = parameters.copy() if parameters else {}  # Store original params
        self.status = JobStatus.QUEUED
        self.comfyui_id = None
        self.output_path = None
        self.created_at = datetime.utcnow()
        self.started_at = None
        self.completed_at = None
        self.error_message = None
        self.metadata = {}
        self.retry_count = 0
        self.recovery_history = []  # Track recovery attempts
        self.last_checkpoint = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "prompt": self.prompt,
            "parameters": self.parameters,
            "original_parameters": self.original_parameters,
            "status": self.status.value,
            "comfyui_id": self.comfyui_id,
            "output_path": self.output_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "retry_count": self.retry_count,
            "recovery_history": self.recovery_history,
            "last_checkpoint": self.last_checkpoint
        }


class JobManager:
    """Manages job lifecycle and tracking with error recovery"""

    def __init__(self, database_manager=None, comfyui_connector=None):
        self.jobs = {}  # In-memory storage for now
        self.next_job_id = 1
        self.database = database_manager
        self.comfyui_connector = comfyui_connector
        self.error_recovery_manager = None

        # Initialize error recovery if ComfyUI connector is available
        if comfyui_connector:
            from .error_recovery_manager import ErrorRecoveryManager
            self.error_recovery_manager = ErrorRecoveryManager(comfyui_connector, database_manager)

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

    async def handle_job_failure(self, job_id: int, error_message: str,
                               workflow_data: Dict[str, Any] = None) -> bool:
        """Handle job failure with intelligent recovery"""
        job = self.get_job(job_id)
        if not job or not self.error_recovery_manager:
            return False

        job.status = JobStatus.RECOVERING
        job.retry_count += 1
        job.error_message = error_message

        logger.warning(f"Job {job_id} failed with error: {error_message[:100]}...")

        # Attempt recovery
        recovery_success, new_params, recovery_message = await self.error_recovery_manager.attempt_recovery(
            job_id, error_message, job.parameters, workflow_data or {}
        )

        if recovery_success:
            # Update job parameters with recovered values
            job.parameters = new_params
            job.recovery_history.append({
                "attempt": job.retry_count,
                "timestamp": datetime.utcnow().isoformat(),
                "message": recovery_message,
                "success": True
            })

            # Reset status to queued for retry
            job.status = JobStatus.QUEUED
            job.error_message = None

            logger.info(f"Job {job_id} recovery successful: {recovery_message}")

            # Update in database if available
            if self.database:
                self.database.update_job(job)

            return True
        else:
            # Recovery failed, mark as failed
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow()
            job.recovery_history.append({
                "attempt": job.retry_count,
                "timestamp": datetime.utcnow().isoformat(),
                "message": recovery_message,
                "success": False
            })

            logger.error(f"Job {job_id} recovery failed: {recovery_message}")

            # Update in database if available
            if self.database:
                self.database.update_job(job)

            return False

    def create_checkpoint(self, job_id: int, progress_percent: float,
                         workflow_state: Dict[str, Any], completed_nodes: List[str] = None) -> bool:
        """Create a checkpoint for job recovery"""
        job = self.get_job(job_id)
        if not job or not self.error_recovery_manager:
            return False

        checkpoint = self.error_recovery_manager.create_checkpoint(
            job_id, workflow_state, progress_percent, completed_nodes
        )

        job.last_checkpoint = checkpoint.checkpoint_id
        job.metadata["last_checkpoint_progress"] = progress_percent

        # Update in database if available
        if self.database:
            self.database.update_job(job)

        return True

    def get_job_with_recovery_status(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get job with detailed recovery information"""
        job = self.get_job(job_id)
        if not job:
            return None

        job_dict = job.to_dict()

        # Add recovery status if error recovery manager is available
        if self.error_recovery_manager:
            recovery_status = self.error_recovery_manager.get_job_recovery_status(job_id)
            job_dict["recovery_status"] = recovery_status

        return job_dict

    def get_enhanced_statistics(self) -> Dict[str, Any]:
        """Get statistics including recovery metrics"""
        base_stats = self.get_statistics()

        if self.error_recovery_manager:
            recovery_stats = self.error_recovery_manager.get_recovery_statistics()
            base_stats["recovery"] = recovery_stats

        return base_stats

    async def retry_failed_jobs(self, max_jobs: int = 5) -> List[int]:
        """Retry failed jobs that might be recoverable"""
        if not self.error_recovery_manager:
            return []

        retried_jobs = []
        failed_jobs = [job for job in self.jobs.values()
                      if job.status == JobStatus.FAILED and job.retry_count < 3]

        for job in failed_jobs[:max_jobs]:
            if job.error_message:
                success = await self.handle_job_failure(
                    job.id, job.error_message, {}
                )
                if success:
                    retried_jobs.append(job.id)

        return retried_jobs