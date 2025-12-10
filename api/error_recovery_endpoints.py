"""
Error Recovery API Endpoints
Provides comprehensive error recovery and job monitoring capabilities
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..modules.intelligent_job_processor import IntelligentJobProcessor
from ..modules.job_manager import JobType

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/error-recovery", tags=["Error Recovery"])

# Global processor instance (in production, use dependency injection)
processor = None


class JobSubmissionRequest(BaseModel):
    prompt: str
    workflow_data: Dict[str, Any]
    job_type: str = "image"  # image, video, batch
    parameters: Optional[Dict[str, Any]] = None
    timeout_minutes: int = 30


class JobRecoveryRequest(BaseModel):
    job_id: int
    force_retry: bool = False


class JobProgressResponse(BaseModel):
    job_id: int
    status: str
    progress_percent: float
    elapsed_time: float
    recovery_attempts: int
    last_error: Optional[str] = None


class RecoveryStatistics(BaseModel):
    total_errors: int
    successful_recoveries: int
    failed_recoveries: int
    recovery_rate: float
    error_distribution: Dict[str, int]


async def get_processor() -> IntelligentJobProcessor:
    """Get or create the intelligent job processor"""
    global processor
    if not processor:
        processor = IntelligentJobProcessor()
        await processor.__aenter__()
    return processor


@router.post("/jobs/submit")


async def submit_job_with_recovery(
    request: JobSubmissionRequest, processor: IntelligentJobProcessor = Depends(get_processor)
) -> Dict[str, Any]:
    """
    Submit a job with intelligent error recovery

    Features:
    - Automatic retry on failure
    - Parameter degradation for OOM errors
    - Checkpoint recovery for timeouts
    - Detailed error reporting
    """
    try:
        # Convert string job type to enum
        job_type = JobType.IMAGE
        if request.job_type.lower() == "video":
            job_type = JobType.VIDEO
        elif request.job_type.lower() == "batch":
            job_type = JobType.BATCH

        # Submit and monitor job
        result = await processor.submit_and_monitor_job(
            prompt=request.prompt,
            workflow_data=request.workflow_data,
            job_type=job_type,
            parameters=request.parameters,
            timeout_minutes=request.timeout_minutes,
        )

        return {
            "success": True,
            "message": "Job submitted with intelligent recovery",
            "data": result,
        }

    except Exception as e:
        logger.error(f"Failed to submit job: {e}")
        raise HTTPException(status_code=500, detail=f"Job submission failed: {str(e)}")


@router.get("/jobs/{job_id}/status")


async def get_job_status_with_recovery(
    job_id: int, processor: IntelligentJobProcessor = Depends(get_processor)
) -> Dict[str, Any]:
    """
    Get comprehensive job status including recovery information

    Returns:
    - Job details with recovery history
    - Current status and progress
    - Error information if applicable
    - Available checkpoints
    """
    try:
        status = await processor.get_job_status(job_id)

        if not status:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        return {"success": True, "job_id": job_id, "data": status}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.post("/jobs/{job_id}/retry")


async def retry_failed_job(
    job_id: int,
    request: JobRecoveryRequest,
    processor: IntelligentJobProcessor = Depends(get_processor),
) -> Dict[str, Any]:
    """
    Manually retry a failed job with error recovery

    Features:
    - Force retry even if max attempts reached (if force_retry=True)
    - Apply error recovery strategies
    - Reset job status for retry
    """
    try:
        # Get job status first
        job_status = await processor.get_job_status(job_id)
        if not job_status:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        # Check if job is in a state that can be retried
        current_status = job_status.get("status")
        if current_status not in ["failed", "timeout", "cancelled"] and not request.force_retry:
            raise HTTPException(
                status_code=400,
                detail=f"Job is in '{current_status}' state and cannot be retried. Use force_retry=true to override.",
            )

        # Use the retry mechanism from job manager
        retried_jobs = await processor.retry_failed_jobs(max_jobs=1)

        if job_id in retried_jobs["retried_job_ids"]:
            return {
                "success": True,
                "message": f"Job {job_id} queued for retry with error recovery",
                "job_id": job_id,
            }
        else:
            return {
                "success": False,
                "message": f"Job {job_id} could not be retried - may have exceeded max attempts",
                "job_id": job_id,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Retry failed: {str(e)}")


@router.post("/jobs/retry-failed")


async def retry_multiple_failed_jobs(
    max_jobs: int = 5, processor: IntelligentJobProcessor = Depends(get_processor)
) -> Dict[str, Any]:
    """
    Retry multiple failed jobs that might be recoverable

    Parameters:
    - max_jobs: Maximum number of jobs to retry (default: 5)
    """
    try:
        result = await processor.retry_failed_jobs(max_jobs)

        return {
            "success": True,
            "message": f"Attempted to retry {result['count']} failed jobs",
            "retried_job_ids": result["retried_job_ids"],
            "count": result["count"],
        }

    except Exception as e:
        logger.error(f"Failed to retry multiple jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Bulk retry failed: {str(e)}")


@router.get("/statistics")


async def get_recovery_statistics(
    processor: IntelligentJobProcessor = Depends(get_processor),
) -> RecoveryStatistics:
    """
    Get comprehensive error recovery statistics

    Returns:
    - Total errors and recoveries
    - Success rates
    - Error type distribution
    - Processing metrics
    """
    try:
        stats = await processor.get_processing_statistics()
        recovery_stats = stats.get("job_manager", {}).get("recovery", {})

        return RecoveryStatistics(
            total_errors=recovery_stats.get("total_errors", 0),
            successful_recoveries=recovery_stats.get("successful_recoveries", 0),
            failed_recoveries=recovery_stats.get("failed_recoveries", 0),
            recovery_rate=recovery_stats.get("recovery_rate", 0.0),
            error_distribution=recovery_stats.get("error_distribution", {}),
        )

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Statistics failed: {str(e)}")


@router.get("/statistics/detailed")


async def get_detailed_statistics(
    processor: IntelligentJobProcessor = Depends(get_processor),
) -> Dict[str, Any]:
    """
    Get detailed processing and recovery statistics

    Returns:
    - All processing metrics
    - Job manager statistics
    - Recovery performance data
    - Error analysis
    """
    try:
        stats = await processor.get_processing_statistics()

        return {
            "success": True,
            "data": stats,
            "message": "Detailed statistics retrieved successfully",
        }

    except Exception as e:
        logger.error(f"Failed to get detailed statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Detailed statistics failed: {str(e)}")


@router.post("/emergency-stop")


async def emergency_stop(
    processor: IntelligentJobProcessor = Depends(get_processor),
) -> Dict[str, Any]:
    """
    Emergency stop - cancel all running jobs and clear queue

    Use this endpoint when:
    - System is overloaded
    - Jobs are stuck/hanging
    - Need to free up resources immediately
    """
    try:
        result = await processor.emergency_stop()

        return {
            "success": result["success"],
            "message": f"Emergency stop completed. Cancelled {result['count']} jobs",
            "cancelled_jobs": result["cancelled_jobs"],
            "queue_cleared": result.get("queue_cleared", False),
        }

    except Exception as e:
        logger.error(f"Emergency stop failed: {e}")
        raise HTTPException(status_code=500, detail=f"Emergency stop failed: {str(e)}")


@router.delete("/cleanup")


async def cleanup_old_data(
    hours: int = 24, processor: IntelligentJobProcessor = Depends(get_processor)
) -> Dict[str, Any]:
    """
    Clean up old job data and recovery information

    Parameters:
    - hours: Clean data older than this many hours (default: 24)
    """
    try:
        if hours < 1:
            raise HTTPException(status_code=400, detail="Hours must be at least 1")

        result = await processor.cleanup_old_data(hours)

        return {
            "success": True,
            "message": f"Cleaned up data older than {hours} hours",
            "data": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


@router.get("/health")


async def health_check(
    processor: IntelligentJobProcessor = Depends(get_processor),
) -> Dict[str, Any]:
    """
    Health check for error recovery system

    Returns:
    - System health status
    - ComfyUI connectivity
    - Error recovery readiness
    """
    try:
        # Check ComfyUI connectivity
        comfyui_health = await processor.comfyui_connector.check_health()

        # Check if error recovery manager is available
        recovery_available = processor.job_manager.error_recovery_manager is not None

        # Get basic statistics
        stats = await processor.get_processing_statistics()

        return {
            "success": True,
            "status": "healthy",
            "comfyui_connected": comfyui_health,
            "error_recovery_available": recovery_available,
            "total_jobs_processed": stats.get("total_jobs_processed", 0),
            "recovery_rate": stats.get("job_manager", {})
            .get("recovery", {})
            .get("recovery_rate", 0.0),
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "success": False,
            "status": "unhealthy",
            "error": str(e),
            "comfyui_connected": False,
            "error_recovery_available": False,
        }
