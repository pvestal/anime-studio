"""
Intelligent Error Recovery System for ComfyUI Jobs
Handles automatic retry logic, parameter degradation, and checkpoint recovery
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict
import copy
import re

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Classification of error types for targeted recovery"""
    CUDA_OOM = "cuda_out_of_memory"
    TIMEOUT = "timeout"
    MODEL_MISSING = "model_missing"
    NETWORK_ERROR = "network_error"
    WORKFLOW_ERROR = "workflow_error"
    DISK_FULL = "disk_full"
    UNKNOWN = "unknown"


class RecoveryStrategy(Enum):
    """Available recovery strategies"""
    RETRY = "retry"
    REDUCE_PARAMS = "reduce_parameters"
    SWITCH_MODEL = "switch_model"
    RESUME_CHECKPOINT = "resume_checkpoint"
    SPLIT_BATCH = "split_batch"
    ABORT = "abort"


@dataclass
class ErrorPattern:
    """Error pattern matching for classification"""
    error_type: ErrorType
    patterns: List[str]
    strategy: RecoveryStrategy
    param_adjustments: Dict[str, Any]
    max_retries: int = 3


@dataclass
class JobCheckpoint:
    """Checkpoint data for resuming interrupted jobs"""
    job_id: int
    checkpoint_id: str
    progress_percent: float
    workflow_state: Dict[str, Any]
    completed_nodes: List[str]
    timestamp: datetime
    output_files: List[str]


@dataclass
class RecoveryAttempt:
    """Track recovery attempt details"""
    attempt_number: int
    strategy: RecoveryStrategy
    original_params: Dict[str, Any]
    adjusted_params: Dict[str, Any]
    error_message: str
    timestamp: datetime
    success: bool = False


class ErrorRecoveryManager:
    """Manages intelligent error recovery for ComfyUI jobs"""

    def __init__(self, comfyui_connector, database_manager=None):
        self.comfyui_connector = comfyui_connector
        self.database = database_manager
        self.checkpoints: Dict[int, List[JobCheckpoint]] = {}
        self.recovery_history: Dict[int, List[RecoveryAttempt]] = {}

        # Error pattern definitions
        self.error_patterns = self._initialize_error_patterns()

        # Recovery statistics
        self.stats = {
            "total_errors": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0,
            "recovery_rate": 0.0
        }

    def _initialize_error_patterns(self) -> List[ErrorPattern]:
        """Initialize error pattern matching rules"""
        return [
            ErrorPattern(
                error_type=ErrorType.CUDA_OOM,
                patterns=[
                    "CUDA out of memory",
                    "OutOfMemoryError",
                    "RuntimeError.*out of memory",
                    "insufficient memory",
                    "GPU memory"
                ],
                strategy=RecoveryStrategy.REDUCE_PARAMS,
                param_adjustments={
                    "batch_size": {"operation": "divide", "factor": 2, "min_value": 1},
                    "width": {"operation": "reduce", "factor": 0.8, "min_value": 512},
                    "height": {"operation": "reduce", "factor": 0.8, "min_value": 512},
                    "num_inference_steps": {"operation": "reduce", "factor": 0.8, "min_value": 20}
                },
                max_retries=3
            ),
            ErrorPattern(
                error_type=ErrorType.TIMEOUT,
                patterns=[
                    "TimeoutError",
                    "Request timeout",
                    "Connection timeout",
                    "Read timeout"
                ],
                strategy=RecoveryStrategy.RESUME_CHECKPOINT,
                param_adjustments={},
                max_retries=2
            ),
            ErrorPattern(
                error_type=ErrorType.MODEL_MISSING,
                patterns=[
                    "Model not found",
                    "FileNotFoundError.*models",
                    "No such file.*checkpoint",
                    "Missing model"
                ],
                strategy=RecoveryStrategy.SWITCH_MODEL,
                param_adjustments={
                    "checkpoint_name": {"operation": "fallback", "options": [
                        "sd_xl_base_1.0.safetensors",
                        "v1-5-pruned-emaonly.ckpt",
                        "anything-v4.5-pruned.ckpt"
                    ]}
                },
                max_retries=2
            ),
            ErrorPattern(
                error_type=ErrorType.NETWORK_ERROR,
                patterns=[
                    "ConnectionError",
                    "Network unreachable",
                    "Connection refused",
                    "HTTP.*50[0-9]"
                ],
                strategy=RecoveryStrategy.RETRY,
                param_adjustments={},
                max_retries=3
            ),
            ErrorPattern(
                error_type=ErrorType.DISK_FULL,
                patterns=[
                    "No space left on device",
                    "Disk full",
                    "OSError.*28"
                ],
                strategy=RecoveryStrategy.ABORT,
                param_adjustments={},
                max_retries=0
            )
        ]

    def classify_error(self, error_message: str) -> Tuple[ErrorType, ErrorPattern]:
        """Classify error and return appropriate recovery strategy"""
        for pattern in self.error_patterns:
            for regex_pattern in pattern.patterns:
                if re.search(regex_pattern, error_message, re.IGNORECASE):
                    logger.info(f"Classified error as {pattern.error_type.value}: {error_message[:100]}...")
                    return pattern.error_type, pattern

        # Default to unknown error with retry strategy
        default_pattern = ErrorPattern(
            error_type=ErrorType.UNKNOWN,
            patterns=[],
            strategy=RecoveryStrategy.RETRY,
            param_adjustments={},
            max_retries=1
        )
        return ErrorType.UNKNOWN, default_pattern

    def adjust_parameters(self, original_params: Dict[str, Any],
                         adjustments: Dict[str, Any]) -> Dict[str, Any]:
        """Apply parameter adjustments based on error pattern"""
        adjusted_params = copy.deepcopy(original_params)

        for param_name, adjustment in adjustments.items():
            if param_name not in adjusted_params:
                continue

            operation = adjustment.get("operation")
            current_value = adjusted_params[param_name]

            if operation == "divide":
                factor = adjustment.get("factor", 2)
                min_value = adjustment.get("min_value", 1)
                new_value = max(int(current_value / factor), min_value)
                adjusted_params[param_name] = new_value
                logger.info(f"Reduced {param_name}: {current_value} → {new_value}")

            elif operation == "reduce":
                factor = adjustment.get("factor", 0.8)
                min_value = adjustment.get("min_value", 1)
                new_value = max(int(current_value * factor), min_value)
                adjusted_params[param_name] = new_value
                logger.info(f"Reduced {param_name}: {current_value} → {new_value}")

            elif operation == "fallback":
                options = adjustment.get("options", [])
                if options and current_value not in options:
                    new_value = options[0]  # Use first fallback option
                    adjusted_params[param_name] = new_value
                    logger.info(f"Switched {param_name}: {current_value} → {new_value}")

        return adjusted_params

    def create_checkpoint(self, job_id: int, workflow_state: Dict[str, Any],
                         progress_percent: float, completed_nodes: List[str] = None) -> JobCheckpoint:
        """Create a checkpoint for job recovery"""
        checkpoint = JobCheckpoint(
            job_id=job_id,
            checkpoint_id=f"{job_id}_{int(time.time())}",
            progress_percent=progress_percent,
            workflow_state=workflow_state,
            completed_nodes=completed_nodes or [],
            timestamp=datetime.utcnow(),
            output_files=[]
        )

        if job_id not in self.checkpoints:
            self.checkpoints[job_id] = []

        self.checkpoints[job_id].append(checkpoint)

        # Keep only the 5 most recent checkpoints per job
        self.checkpoints[job_id] = self.checkpoints[job_id][-5:]

        logger.info(f"Created checkpoint {checkpoint.checkpoint_id} for job {job_id} at {progress_percent}%")
        return checkpoint

    def get_latest_checkpoint(self, job_id: int) -> Optional[JobCheckpoint]:
        """Get the latest checkpoint for a job"""
        if job_id not in self.checkpoints or not self.checkpoints[job_id]:
            return None

        return max(self.checkpoints[job_id], key=lambda cp: cp.timestamp)

    async def attempt_recovery(self, job_id: int, error_message: str,
                              original_params: Dict[str, Any],
                              workflow_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
        """
        Attempt to recover from a job failure
        Returns: (success, new_params, recovery_message)
        """
        self.stats["total_errors"] += 1

        # Get or initialize recovery history for this job
        if job_id not in self.recovery_history:
            self.recovery_history[job_id] = []

        recovery_attempts = self.recovery_history[job_id]
        attempt_number = len(recovery_attempts) + 1

        # Classify the error
        error_type, error_pattern = self.classify_error(error_message)

        # Check if we've exceeded max retries
        if attempt_number > error_pattern.max_retries:
            self.stats["failed_recoveries"] += 1
            self._update_recovery_rate()
            return False, original_params, f"Max retries ({error_pattern.max_retries}) exceeded for {error_type.value}"

        recovery_message = ""
        new_params = original_params
        success = False

        try:
            if error_pattern.strategy == RecoveryStrategy.REDUCE_PARAMS:
                # Apply parameter reduction
                new_params = self.adjust_parameters(original_params, error_pattern.param_adjustments)
                recovery_message = f"Reduced parameters for {error_type.value} (attempt {attempt_number}/{error_pattern.max_retries})"
                success = True

            elif error_pattern.strategy == RecoveryStrategy.RESUME_CHECKPOINT:
                # Try to resume from checkpoint
                checkpoint = self.get_latest_checkpoint(job_id)
                if checkpoint and checkpoint.progress_percent > 10:
                    # Modify workflow to resume from checkpoint
                    workflow_data = self._modify_workflow_for_resume(workflow_data, checkpoint)
                    recovery_message = f"Resuming from checkpoint at {checkpoint.progress_percent}% (attempt {attempt_number}/{error_pattern.max_retries})"
                    success = True
                else:
                    recovery_message = f"No suitable checkpoint found, retrying from start (attempt {attempt_number}/{error_pattern.max_retries})"
                    success = True

            elif error_pattern.strategy == RecoveryStrategy.SWITCH_MODEL:
                # Switch to fallback model
                new_params = self.adjust_parameters(original_params, error_pattern.param_adjustments)
                recovery_message = f"Switched to fallback model for {error_type.value} (attempt {attempt_number}/{error_pattern.max_retries})"
                success = True

            elif error_pattern.strategy == RecoveryStrategy.RETRY:
                # Simple retry with exponential backoff
                backoff_time = min(2 ** attempt_number, 30)  # Max 30 second delay
                await asyncio.sleep(backoff_time)
                recovery_message = f"Retrying after {backoff_time}s delay (attempt {attempt_number}/{error_pattern.max_retries})"
                success = True

            elif error_pattern.strategy == RecoveryStrategy.ABORT:
                recovery_message = f"Unrecoverable error: {error_type.value}"
                success = False
                # Don't increment recovery attempts for abort cases
                self.stats["failed_recoveries"] -= 1
                return success, original_params, recovery_message

        except Exception as e:
            logger.error(f"Recovery attempt failed: {e}")
            recovery_message = f"Recovery attempt failed: {str(e)}"
            success = False

        # Record recovery attempt
        recovery_attempt = RecoveryAttempt(
            attempt_number=attempt_number,
            strategy=error_pattern.strategy,
            original_params=original_params,
            adjusted_params=new_params,
            error_message=error_message,
            timestamp=datetime.utcnow(),
            success=success
        )

        self.recovery_history[job_id].append(recovery_attempt)

        if success:
            self.stats["successful_recoveries"] += 1
        else:
            self.stats["failed_recoveries"] += 1

        self._update_recovery_rate()

        logger.info(f"Recovery attempt for job {job_id}: {recovery_message}")

        return success, new_params, recovery_message

    def _modify_workflow_for_resume(self, workflow_data: Dict[str, Any],
                                   checkpoint: JobCheckpoint) -> Dict[str, Any]:
        """Modify workflow to resume from checkpoint"""
        # This is a simplified implementation
        # In practice, you'd need to understand ComfyUI's checkpoint system
        modified_workflow = copy.deepcopy(workflow_data)

        # Add checkpoint loading nodes if needed
        if "checkpoint_loader" in modified_workflow:
            modified_workflow["checkpoint_loader"]["inputs"]["checkpoint_path"] = f"/tmp/checkpoint_{checkpoint.checkpoint_id}.pt"

        return modified_workflow

    def _update_recovery_rate(self):
        """Update recovery success rate statistics"""
        total_attempts = self.stats["successful_recoveries"] + self.stats["failed_recoveries"]
        if total_attempts > 0:
            self.stats["recovery_rate"] = (self.stats["successful_recoveries"] / total_attempts) * 100

    def get_job_recovery_status(self, job_id: int) -> Dict[str, Any]:
        """Get detailed recovery status for a job"""
        recovery_attempts = self.recovery_history.get(job_id, [])
        checkpoints = self.checkpoints.get(job_id, [])

        return {
            "job_id": job_id,
            "total_attempts": len(recovery_attempts),
            "successful_attempts": len([a for a in recovery_attempts if a.success]),
            "latest_attempt": recovery_attempts[-1].__dict__ if recovery_attempts else None,
            "available_checkpoints": len(checkpoints),
            "latest_checkpoint": checkpoints[-1].__dict__ if checkpoints else None
        }

    def get_recovery_statistics(self) -> Dict[str, Any]:
        """Get overall recovery statistics"""
        # Calculate error type distribution
        error_distribution = {}
        for attempts in self.recovery_history.values():
            for attempt in attempts:
                error_type = self.classify_error(attempt.error_message)[0].value
                error_distribution[error_type] = error_distribution.get(error_type, 0) + 1

        return {
            **self.stats,
            "error_distribution": error_distribution,
            "active_jobs_with_recovery": len(self.recovery_history),
            "total_checkpoints": sum(len(cps) for cps in self.checkpoints.values())
        }

    def cleanup_old_data(self, hours: int = 24):
        """Clean up old recovery data and checkpoints"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        cleaned_jobs = 0
        cleaned_checkpoints = 0

        # Clean up recovery history
        for job_id in list(self.recovery_history.keys()):
            attempts = self.recovery_history[job_id]
            recent_attempts = [a for a in attempts if a.timestamp > cutoff_time]

            if not recent_attempts:
                del self.recovery_history[job_id]
                cleaned_jobs += 1
            else:
                self.recovery_history[job_id] = recent_attempts

        # Clean up checkpoints
        for job_id in list(self.checkpoints.keys()):
            checkpoints = self.checkpoints[job_id]
            recent_checkpoints = [cp for cp in checkpoints if cp.timestamp > cutoff_time]

            if not recent_checkpoints:
                del self.checkpoints[job_id]
            else:
                self.checkpoints[job_id] = recent_checkpoints
                cleaned_checkpoints += len(checkpoints) - len(recent_checkpoints)

        logger.info(f"Cleaned up recovery data: {cleaned_jobs} jobs, {cleaned_checkpoints} checkpoints")

        return {
            "cleaned_jobs": cleaned_jobs,
            "cleaned_checkpoints": cleaned_checkpoints,
            "remaining_jobs": len(self.recovery_history),
            "remaining_checkpoints": sum(len(cps) for cps in self.checkpoints.values())
        }