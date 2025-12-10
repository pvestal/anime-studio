#!/usr/bin/env python3
"""
Job Cleanup API Endpoints
Provides REST endpoints for cleaning up stuck anime production jobs

Endpoints:
- GET /api/anime/jobs/stuck/summary - Get summary of stuck jobs
- POST /api/anime/jobs/stuck/fix - Fix stuck jobs by checking output files
- POST /api/anime/jobs/stuck/timeout - Force timeout old jobs
- GET /api/anime/jobs/monitoring/status - Get monitoring service status

Author: Claude Code
Date: November 7, 2025
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Optional
import logging
from completion_tracking_fix import JobCleanupManager, JobCompletionTracker

logger = logging.getLogger(__name__)

# Create router for job cleanup endpoints
router = APIRouter(prefix="/api/anime", tags=["job-cleanup"])

# Initialize cleanup manager
cleanup_manager = JobCleanupManager()

class ForceTimeoutRequest(BaseModel):
    hours: Optional[int] = 2
    confirm: bool = False

@router.get("/jobs/stuck/summary")
async def get_stuck_jobs_summary():
    """Get summary of all stuck jobs in the system"""
    try:
        summary = cleanup_manager.get_stuck_jobs_summary()

        if 'error' in summary:
            raise HTTPException(status_code=500, detail=summary['error'])

        return {
            "success": True,
            "data": summary,
            "message": f"Found {summary.get('total_stuck', 0)} stuck jobs"
        }
    except Exception as e:
        logger.error(f"Error getting stuck jobs summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/jobs/stuck/fix")
async def fix_stuck_jobs():
    """Fix stuck jobs by checking if their output files actually exist"""
    try:
        result = cleanup_manager.fix_stuck_jobs_by_checking_files()

        if 'error' in result:
            raise HTTPException(status_code=500, detail=result['error'])

        return {
            "success": True,
            "fixed_jobs": result['fixed_jobs'],
            "details": result['details'],
            "message": f"Successfully fixed {result['fixed_jobs']} stuck jobs"
        }
    except Exception as e:
        logger.error(f"Error fixing stuck jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/jobs/stuck/timeout")
async def force_timeout_old_jobs(request: ForceTimeoutRequest):
    """Force timeout jobs older than specified hours"""
    try:
        if not request.confirm:
            raise HTTPException(
                status_code=400,
                detail="Must set 'confirm: true' to force timeout jobs"
            )

        if request.hours < 1 or request.hours > 24:
            raise HTTPException(
                status_code=400,
                detail="Hours must be between 1 and 24"
            )

        result = cleanup_manager.force_timeout_old_jobs(request.hours)

        if 'error' in result:
            raise HTTPException(status_code=500, detail=result['error'])

        return {
            "success": True,
            "timed_out_count": result['timed_out_count'],
            "cutoff_time": result['cutoff_time'],
            "jobs": result['jobs'],
            "message": f"Force timed out {result['timed_out_count']} jobs older than {request.hours} hours"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error force timing out jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/jobs/monitoring/status")
async def get_monitoring_status():
    """Get status of the job monitoring service"""
    try:
        # Check if monitoring service is running by trying to get processing jobs
        processing_jobs = cleanup_manager.get_stuck_jobs_summary()

        return {
            "success": True,
            "monitoring_active": True,
            "message": "Job cleanup endpoints are operational",
            "endpoints": {
                "summary": "/api/anime/jobs/stuck/summary",
                "fix": "/api/anime/jobs/stuck/fix",
                "timeout": "/api/anime/jobs/stuck/timeout",
                "status": "/api/anime/jobs/monitoring/status"
            },
            "stats": {
                "total_processing": processing_jobs.get('total_stuck', 0),
                "old_processing": processing_jobs.get('old_processing_jobs', 0)
            }
        }
    except Exception as e:
        logger.error(f"Error getting monitoring status: {e}")
        return {
            "success": False,
            "monitoring_active": False,
            "error": str(e)
        }

@router.post("/jobs/monitoring/start")
async def start_monitoring_service(background_tasks: BackgroundTasks):
    """Start the job completion monitoring service in background"""
    try:
        tracker = JobCompletionTracker()

        # Add monitoring to background tasks
        background_tasks.add_task(tracker.monitor_processing_jobs)

        return {
            "success": True,
            "message": "Job completion monitoring started in background",
            "check_interval": tracker.check_interval,
            "timeout_threshold": str(tracker.timeout_threshold)
        }
    except Exception as e:
        logger.error(f"Error starting monitoring service: {e}")
        raise HTTPException(status_code=500, detail=str(e))