"""
Intelligent Job Processor
Orchestrates job execution with error recovery, progress monitoring, and checkpointing
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable

from .job_manager import JobManager, JobStatus, JobType
from .comfyui_connector import ComfyUIConnector
from .error_recovery_manager import ErrorRecoveryManager

logger = logging.getLogger(__name__)


class IntelligentJobProcessor:
    """
    Intelligent job processor that handles ComfyUI workflows with:
    - Automatic error recovery
    - Progress monitoring with checkpoints
    - Smart parameter adjustment
    - Comprehensive error reporting
    """

    def __init__(self, comfyui_url: str = "http://192.168.50.135:8188", database_manager=None):
        self.comfyui_connector = ComfyUIConnector(comfyui_url)
        self.job_manager = JobManager(database_manager, self.comfyui_connector)
        self.database = database_manager

        # Statistics tracking
        self.processing_stats = {
            "total_jobs_processed": 0,
            "successful_jobs": 0,
            "failed_jobs": 0,
            "recovered_jobs": 0,
            "total_processing_time": 0.0
        }

    async def __aenter__(self):
        await self.comfyui_connector.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.comfyui_connector.__aexit__(exc_type, exc_val, exc_tb)

    async def submit_and_monitor_job(self,
                                   prompt: str,
                                   workflow_data: Dict[str, Any],
                                   job_type: JobType = JobType.IMAGE,
                                   parameters: Dict[str, Any] = None,
                                   progress_callback: Optional[Callable] = None,
                                   timeout_minutes: int = 30) -> Dict[str, Any]:
        """
        Submit a job and monitor it with intelligent error recovery

        Returns:
            Dict with job status, results, and recovery information
        """
        start_time = time.time()

        # Create job
        job = self.job_manager.create_job(job_type, prompt, parameters or {})
        job_id = job.id

        logger.info(f"Starting intelligent processing for job {job_id}")

        try:
            # Submit to ComfyUI
            comfyui_job_id = await self.comfyui_connector.submit_workflow(workflow_data)

            if not comfyui_job_id:
                await self._handle_submission_failure(job_id, "Failed to submit workflow to ComfyUI")
                return self._create_failure_result(job_id, "Submission failed")

            # Update job with ComfyUI ID
            self.job_manager.update_job_status(
                job_id, JobStatus.PROCESSING,
                comfyui_id=comfyui_job_id,
                started_at=datetime.utcnow()
            )

            # Monitor job with progress tracking
            success, error_message, result_data = await self._monitor_with_recovery(
                job_id, comfyui_job_id, workflow_data, progress_callback, timeout_minutes
            )

            processing_time = time.time() - start_time

            if success:
                return await self._handle_successful_completion(
                    job_id, result_data, processing_time
                )
            else:
                return await self._handle_final_failure(
                    job_id, error_message, processing_time
                )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Unexpected error processing job {job_id}: {e}")
            return await self._handle_final_failure(
                job_id, f"Unexpected error: {str(e)}", processing_time
            )

    async def _monitor_with_recovery(self,
                                   job_id: int,
                                   comfyui_job_id: str,
                                   workflow_data: Dict[str, Any],
                                   progress_callback: Optional[Callable],
                                   timeout_minutes: int) -> tuple[bool, Optional[str], Optional[Dict]]:
        """Monitor job with automatic error recovery"""

        # Create progress callback that also creates checkpoints
        async def enhanced_progress_callback(prompt_id: str, progress: float, elapsed: float):
            # Create checkpoint every 25%
            if progress > 0 and progress % 25 < 5:  # Rough checkpoint timing
                self.job_manager.create_checkpoint(
                    job_id,
                    progress,
                    {"workflow": workflow_data, "elapsed": elapsed}
                )

            # Call user callback if provided
            if progress_callback:
                await progress_callback(job_id, progress, elapsed)

        # Create checkpoint callback
        async def checkpoint_callback(prompt_id: str, progress: float, state: Dict[str, Any]):
            self.job_manager.create_checkpoint(job_id, progress, state)
            logger.info(f"Created checkpoint for job {job_id} at {progress}%")

        # Monitor the job
        success, error_message, result_data = await self.comfyui_connector.monitor_job_progress(
            comfyui_job_id,
            enhanced_progress_callback,
            checkpoint_callback,
            timeout_minutes
        )

        # If job failed, attempt recovery
        if not success and error_message:
            logger.warning(f"Job {job_id} failed, attempting recovery: {error_message}")

            recovery_success = await self.job_manager.handle_job_failure(
                job_id, error_message, workflow_data
            )

            if recovery_success:
                # Retry the job with adjusted parameters
                job = self.job_manager.get_job(job_id)
                if job and job.status == JobStatus.QUEUED:
                    logger.info(f"Retrying job {job_id} with adjusted parameters")

                    # Submit with new parameters
                    new_workflow = self._update_workflow_parameters(workflow_data, job.parameters)
                    new_comfyui_id = await self.comfyui_connector.submit_workflow(new_workflow)

                    if new_comfyui_id:
                        self.job_manager.update_job_status(
                            job_id, JobStatus.PROCESSING,
                            comfyui_id=new_comfyui_id
                        )

                        # Monitor the retry (recursive call with reduced timeout)
                        retry_timeout = max(timeout_minutes - 10, 10)  # Reduce timeout for retry
                        return await self._monitor_with_recovery(
                            job_id, new_comfyui_id, new_workflow,
                            progress_callback, retry_timeout
                        )

        return success, error_message, result_data

    def _update_workflow_parameters(self, workflow_data: Dict[str, Any],
                                  new_parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Update workflow data with new parameters"""
        updated_workflow = workflow_data.copy()

        # Update common workflow parameters
        # This is a simplified implementation - adjust based on your workflow structure
        for node_id, node_data in updated_workflow.items():
            if isinstance(node_data, dict) and "inputs" in node_data:
                inputs = node_data["inputs"]

                # Update batch size
                if "batch_size" in new_parameters and "batch_size" in inputs:
                    inputs["batch_size"] = new_parameters["batch_size"]

                # Update resolution
                if "width" in new_parameters and "width" in inputs:
                    inputs["width"] = new_parameters["width"]
                if "height" in new_parameters and "height" in inputs:
                    inputs["height"] = new_parameters["height"]

                # Update steps
                if "num_inference_steps" in new_parameters and "steps" in inputs:
                    inputs["steps"] = new_parameters["num_inference_steps"]

                # Update model checkpoint
                if "checkpoint_name" in new_parameters and "ckpt_name" in inputs:
                    inputs["ckpt_name"] = new_parameters["checkpoint_name"]

        return updated_workflow

    async def _handle_submission_failure(self, job_id: int, error_message: str):
        """Handle failure to submit job to ComfyUI"""
        self.job_manager.update_job_status(
            job_id, JobStatus.FAILED,
            error_message=error_message,
            completed_at=datetime.utcnow()
        )

    async def _handle_successful_completion(self,
                                          job_id: int,
                                          result_data: Dict[str, Any],
                                          processing_time: float) -> Dict[str, Any]:
        """Handle successful job completion"""

        # Extract output paths from ComfyUI result
        output_files = self._extract_output_files(result_data)
        output_path = output_files[0] if output_files else None

        self.job_manager.update_job_status(
            job_id, JobStatus.COMPLETED,
            output_path=output_path,
            completed_at=datetime.utcnow()
        )

        # Update statistics
        self.processing_stats["total_jobs_processed"] += 1
        self.processing_stats["successful_jobs"] += 1
        self.processing_stats["total_processing_time"] += processing_time

        job_with_recovery = self.job_manager.get_job_with_recovery_status(job_id)

        logger.info(f"Job {job_id} completed successfully in {processing_time:.2f}s")

        return {
            "success": True,
            "job_id": job_id,
            "processing_time": processing_time,
            "output_files": output_files,
            "job_details": job_with_recovery,
            "recovery_used": len(job_with_recovery.get("recovery_history", [])) > 0
        }

    async def _handle_final_failure(self,
                                  job_id: int,
                                  error_message: str,
                                  processing_time: float) -> Dict[str, Any]:
        """Handle final job failure after all recovery attempts"""

        self.job_manager.update_job_status(
            job_id, JobStatus.FAILED,
            error_message=error_message,
            completed_at=datetime.utcnow()
        )

        # Update statistics
        self.processing_stats["total_jobs_processed"] += 1
        self.processing_stats["failed_jobs"] += 1
        self.processing_stats["total_processing_time"] += processing_time

        job_with_recovery = self.job_manager.get_job_with_recovery_status(job_id)

        logger.error(f"Job {job_id} failed after {processing_time:.2f}s: {error_message}")

        return {
            "success": False,
            "job_id": job_id,
            "error_message": error_message,
            "processing_time": processing_time,
            "job_details": job_with_recovery,
            "recovery_attempts": len(job_with_recovery.get("recovery_history", []))
        }

    def _create_failure_result(self, job_id: int, error_message: str) -> Dict[str, Any]:
        """Create a failure result dictionary"""
        return {
            "success": False,
            "job_id": job_id,
            "error_message": error_message,
            "processing_time": 0.0,
            "recovery_attempts": 0
        }

    def _extract_output_files(self, result_data: Dict[str, Any]) -> List[str]:
        """Extract output file paths from ComfyUI result data"""
        output_files = []

        if not result_data or "outputs" not in result_data:
            return output_files

        outputs = result_data["outputs"]
        for node_id, node_outputs in outputs.items():
            if isinstance(node_outputs, dict):
                # Look for image/video outputs
                for output_type, files in node_outputs.items():
                    if output_type in ["images", "videos", "gifs"] and isinstance(files, list):
                        for file_info in files:
                            if isinstance(file_info, dict) and "filename" in file_info:
                                output_files.append(file_info["filename"])

        return output_files

    async def get_job_status(self, job_id: int) -> Dict[str, Any]:
        """Get comprehensive job status including recovery information"""
        return self.job_manager.get_job_with_recovery_status(job_id)

    async def retry_failed_jobs(self, max_jobs: int = 5) -> Dict[str, Any]:
        """Retry recently failed jobs that might be recoverable"""
        retried_jobs = await self.job_manager.retry_failed_jobs(max_jobs)

        return {
            "retried_job_ids": retried_jobs,
            "count": len(retried_jobs)
        }

    async def get_processing_statistics(self) -> Dict[str, Any]:
        """Get comprehensive processing and recovery statistics"""
        base_stats = self.processing_stats.copy()

        # Calculate success rate
        if base_stats["total_jobs_processed"] > 0:
            base_stats["success_rate"] = (
                base_stats["successful_jobs"] / base_stats["total_jobs_processed"]
            ) * 100

            base_stats["average_processing_time"] = (
                base_stats["total_processing_time"] / base_stats["total_jobs_processed"]
            )

        # Add job manager statistics
        job_stats = self.job_manager.get_enhanced_statistics()
        base_stats["job_manager"] = job_stats

        return base_stats

    async def cleanup_old_data(self, hours: int = 24) -> Dict[str, Any]:
        """Clean up old job data and recovery information"""
        job_cleanup = self.job_manager.cleanup_old_jobs(hours)

        recovery_cleanup = {}
        if self.job_manager.error_recovery_manager:
            recovery_cleanup = self.job_manager.error_recovery_manager.cleanup_old_data(hours)

        return {
            "cleaned_jobs": job_cleanup,
            "recovery_cleanup": recovery_cleanup
        }

    async def emergency_stop(self) -> Dict[str, Any]:
        """Emergency stop - clear ComfyUI queue and cancel all processing jobs"""
        try:
            # Clear ComfyUI queue
            queue_cleared = await self.comfyui_connector.clear_queue()

            # Mark all processing jobs as cancelled
            cancelled_jobs = []
            for job in self.job_manager.jobs.values():
                if job.status == JobStatus.PROCESSING:
                    self.job_manager.update_job_status(
                        job.id, JobStatus.CANCELLED,
                        error_message="Emergency stop initiated",
                        completed_at=datetime.utcnow()
                    )
                    cancelled_jobs.append(job.id)

            return {
                "success": True,
                "queue_cleared": queue_cleared,
                "cancelled_jobs": cancelled_jobs,
                "count": len(cancelled_jobs)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "cancelled_jobs": [],
                "count": 0
            }