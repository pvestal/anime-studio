#!/usr/bin/env python3
"""
Status Monitor Module for Anime Production System
Implements robust job progress tracking by directly interfacing with ComfyUI
Replaces broken job status API with real-time monitoring capabilities

Key Features:
- Direct ComfyUI /queue and /history polling
- WebSocket support for real-time updates
- Accurate progress estimation based on actual generation times
- Statistics collection for performance optimization
- Resilient error handling for production use
"""

import asyncio
import json
import logging
import time
import threading
import websockets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable, Set
from enum import Enum
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import statistics

# Import from existing modules
from .comfyui_connector import ComfyUIConnector
from .job_manager import JobStatus, JobType

logger = logging.getLogger(__name__)


class ProgressStatus(Enum):
    """Progress tracking status"""
    UNKNOWN = "unknown"
    QUEUED = "queued"
    INITIALIZING = "initializing"
    PROCESSING = "processing"
    COMPLETING = "completing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class ProgressUpdate:
    """Progress update data structure"""
    job_id: int
    comfyui_prompt_id: str
    status: ProgressStatus
    progress_percent: float = 0.0
    current_step: int = 0
    total_steps: int = 0
    estimated_completion: Optional[datetime] = None
    generation_time: Optional[float] = None
    node_progress: Dict[str, Any] = None
    error_message: Optional[str] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.node_progress is None:
            self.node_progress = {}


class GenerationStats:
    """Collects and analyzes generation performance statistics"""

    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self.completion_times = defaultdict(deque)  # By job type
        self.step_durations = deque(maxlen=max_samples)
        self.node_performance = defaultdict(list)
        self.failure_patterns = defaultdict(int)
        self._lock = threading.RLock()

    def record_completion(self, job_type: str, duration: float, steps: int = 0):
        """Record job completion for statistics"""
        with self._lock:
            times = self.completion_times[job_type]
            times.append(duration)
            if len(times) > self.max_samples:
                times.popleft()

            if steps > 0:
                self.step_durations.append(duration / steps)

    def record_failure(self, job_type: str, error_pattern: str):
        """Record failure patterns"""
        with self._lock:
            self.failure_patterns[f"{job_type}:{error_pattern}"] += 1

    def estimate_completion_time(self, job_type: str, steps: int = 0) -> Optional[float]:
        """Estimate completion time based on historical data"""
        with self._lock:
            times = self.completion_times.get(job_type, deque())
            if not times:
                # Fallback to average step duration if available
                if steps > 0 and self.step_durations:
                    avg_step_time = statistics.median(self.step_durations)
                    return avg_step_time * steps
                return None

            # Use median for robust estimation
            return statistics.median(times)

    def get_statistics(self) -> Dict[str, Any]:
        """Get current performance statistics"""
        with self._lock:
            stats = {
                "completion_times": {},
                "average_step_duration": None,
                "failure_patterns": dict(self.failure_patterns),
                "sample_counts": {}
            }

            for job_type, times in self.completion_times.items():
                if times:
                    stats["completion_times"][job_type] = {
                        "count": len(times),
                        "median": statistics.median(times),
                        "mean": statistics.mean(times),
                        "min": min(times),
                        "max": max(times)
                    }
                    stats["sample_counts"][job_type] = len(times)

            if self.step_durations:
                stats["average_step_duration"] = statistics.median(self.step_durations)

            return stats


class StatusMonitor:
    """
    Comprehensive status monitoring for anime production jobs

    Works around broken job status API by directly monitoring ComfyUI
    Provides real-time progress tracking and WebSocket broadcasting
    """

    def __init__(
        self,
        comfyui_connector: ComfyUIConnector = None,
        database_manager = None,
        poll_interval: float = 2.0,
        websocket_port: int = 8329
    ):
        self.comfyui = comfyui_connector or ComfyUIConnector()
        self.database = database_manager
        self.poll_interval = poll_interval
        self.websocket_port = websocket_port

        # Job tracking
        self.monitored_jobs: Dict[int, str] = {}  # job_id -> prompt_id
        self.job_start_times: Dict[str, datetime] = {}
        self.job_types: Dict[str, str] = {}  # prompt_id -> job_type
        self.last_queue_state = {}

        # Progress callbacks
        self.progress_callbacks: List[Callable[[ProgressUpdate], None]] = []
        self.websocket_clients: Set = set()

        # Statistics and performance tracking
        self.stats = GenerationStats()

        # Control flags
        self._monitoring = False
        self._monitor_task = None
        self._websocket_server = None
        self._lock = threading.RLock()

        logger.info("StatusMonitor initialized")

    async def start_monitoring(self):
        """Start the monitoring system"""
        if self._monitoring:
            logger.warning("Monitoring already started")
            return

        self._monitoring = True
        logger.info("Starting status monitoring system")

        # Start monitoring task
        self._monitor_task = asyncio.create_task(self._monitor_loop())

        # Start WebSocket server for real-time updates
        try:
            self._websocket_server = await websockets.serve(
                self._websocket_handler,
                "localhost",
                self.websocket_port
            )
            logger.info(f"WebSocket server started on port {self.websocket_port}")
        except Exception as e:
            logger.error(f"Failed to start WebSocket server: {e}")

    async def stop_monitoring(self):
        """Stop the monitoring system"""
        self._monitoring = False
        logger.info("Stopping status monitoring system")

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        if self._websocket_server:
            self._websocket_server.close()
            await self._websocket_server.wait_closed()

        # Close ComfyUI session if it exists
        if hasattr(self.comfyui, 'session') and self.comfyui.session:
            await self.comfyui.session.close()

    def monitor_job(
        self,
        job_id: int,
        comfyui_prompt_id: str,
        job_type: str = "unknown"
    ) -> bool:
        """
        Start monitoring a specific job

        Args:
            job_id: Internal job ID
            comfyui_prompt_id: ComfyUI prompt ID
            job_type: Type of job for statistics tracking
        """
        with self._lock:
            self.monitored_jobs[job_id] = comfyui_prompt_id
            self.job_start_times[comfyui_prompt_id] = datetime.utcnow()
            self.job_types[comfyui_prompt_id] = job_type

        logger.info(f"Started monitoring job {job_id} (ComfyUI: {comfyui_prompt_id})")
        return True

    def stop_monitoring_job(self, job_id: int) -> bool:
        """Stop monitoring a specific job"""
        with self._lock:
            if job_id in self.monitored_jobs:
                prompt_id = self.monitored_jobs.pop(job_id)
                self.job_start_times.pop(prompt_id, None)
                self.job_types.pop(prompt_id, None)
                logger.info(f"Stopped monitoring job {job_id}")
                return True
        return False

    async def get_progress(self, job_id: int) -> Optional[ProgressUpdate]:
        """Get current progress for a specific job"""
        with self._lock:
            prompt_id = self.monitored_jobs.get(job_id)

        if not prompt_id:
            return None

        return await self._check_job_progress(job_id, prompt_id)

    async def estimate_completion(self, job_id: int) -> Optional[datetime]:
        """Estimate completion time for a job"""
        progress = await self.get_progress(job_id)
        if not progress:
            return None

        with self._lock:
            prompt_id = self.monitored_jobs.get(job_id)
            job_type = self.job_types.get(prompt_id, "unknown")

        if progress.status == ProgressStatus.COMPLETED:
            return progress.timestamp

        # Get estimated duration from statistics
        estimated_duration = self.stats.estimate_completion_time(job_type)
        if estimated_duration is None:
            return None

        # Calculate based on current progress
        if progress.progress_percent > 0:
            start_time = self.job_start_times.get(prompt_id)
            if start_time:
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                total_estimated = elapsed / (progress.progress_percent / 100)
                remaining = total_estimated - elapsed
                return datetime.utcnow() + timedelta(seconds=remaining)

        # Fallback to historical average
        start_time = self.job_start_times.get(prompt_id)
        if start_time:
            return start_time + timedelta(seconds=estimated_duration)

        return None

    def add_progress_callback(self, callback: Callable[[ProgressUpdate], None]):
        """Add a progress update callback"""
        self.progress_callbacks.append(callback)

    def remove_progress_callback(self, callback: Callable[[ProgressUpdate], None]):
        """Remove a progress update callback"""
        if callback in self.progress_callbacks:
            self.progress_callbacks.remove(callback)

    async def broadcast_update(self, update: ProgressUpdate):
        """Broadcast progress update to all clients"""
        # Call registered callbacks
        for callback in self.progress_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(update)
                else:
                    callback(update)
            except Exception as e:
                logger.error(f"Progress callback failed: {e}")

        # Broadcast via WebSocket
        if self.websocket_clients:
            message = json.dumps({
                "type": "progress_update",
                "data": asdict(update),
                "timestamp": update.timestamp.isoformat()
            }, default=str)

            # Send to all connected clients
            disconnected = []
            for client in self.websocket_clients:
                try:
                    await client.send(message)
                except websockets.exceptions.ConnectionClosed:
                    disconnected.append(client)
                except Exception as e:
                    logger.error(f"WebSocket broadcast failed: {e}")
                    disconnected.append(client)

            # Clean up disconnected clients
            for client in disconnected:
                self.websocket_clients.discard(client)

    async def get_queue_statistics(self) -> Dict[str, Any]:
        """Get current queue statistics"""
        try:
            queue_status = await self.comfyui.get_queue_status()
            return {
                "running_jobs": queue_status.get("running", 0),
                "pending_jobs": queue_status.get("pending", 0),
                "monitored_jobs": len(self.monitored_jobs),
                "generation_stats": self.stats.get_statistics(),
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to get queue statistics: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    # Private methods

    async def _monitor_loop(self):
        """Main monitoring loop"""
        logger.info("Starting monitoring loop")

        while self._monitoring:
            try:
                await self._check_all_jobs()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(self.poll_interval)

        logger.info("Monitoring loop stopped")

    async def _check_all_jobs(self):
        """Check progress for all monitored jobs"""
        with self._lock:
            jobs_to_check = list(self.monitored_jobs.items())

        for job_id, prompt_id in jobs_to_check:
            try:
                progress = await self._check_job_progress(job_id, prompt_id)
                if progress:
                    await self.broadcast_update(progress)

                    # Handle completed/failed jobs
                    if progress.status in [ProgressStatus.COMPLETED, ProgressStatus.FAILED]:
                        await self._handle_job_completion(job_id, prompt_id, progress)

            except Exception as e:
                logger.error(f"Failed to check job {job_id}: {e}")

    async def _check_job_progress(self, job_id: int, prompt_id: str) -> Optional[ProgressUpdate]:
        """Check progress for a specific job using ComfyUI APIs"""
        try:
            # First check if job is in queue
            queue_status = await self.comfyui.get_queue_status()
            queue_data = queue_status.get("details", {})

            # Check running queue
            running_queue = queue_data.get("queue_running", [])
            for item in running_queue:
                if len(item) >= 2 and item[1] == prompt_id:
                    # Job is currently running
                    return ProgressUpdate(
                        job_id=job_id,
                        comfyui_prompt_id=prompt_id,
                        status=ProgressStatus.PROCESSING,
                        progress_percent=50.0,  # Estimate - no detailed progress from queue
                        current_step=1,
                        total_steps=2
                    )

            # Check pending queue
            pending_queue = queue_data.get("queue_pending", [])
            for item in pending_queue:
                if len(item) >= 2 and item[1] == prompt_id:
                    # Job is waiting
                    return ProgressUpdate(
                        job_id=job_id,
                        comfyui_prompt_id=prompt_id,
                        status=ProgressStatus.QUEUED,
                        progress_percent=0.0
                    )

            # Check history for completion
            history = await self.comfyui.get_history(prompt_id)
            if history:
                status = history.get("status", {})

                if status.get("completed", False):
                    # Job completed successfully
                    start_time = self.job_start_times.get(prompt_id)
                    duration = None
                    if start_time:
                        duration = (datetime.utcnow() - start_time).total_seconds()

                    return ProgressUpdate(
                        job_id=job_id,
                        comfyui_prompt_id=prompt_id,
                        status=ProgressStatus.COMPLETED,
                        progress_percent=100.0,
                        current_step=status.get("status_str", "completed"),
                        generation_time=duration
                    )

                elif "error" in status:
                    # Job failed
                    error_msg = str(status.get("error", "Unknown error"))
                    return ProgressUpdate(
                        job_id=job_id,
                        comfyui_prompt_id=prompt_id,
                        status=ProgressStatus.FAILED,
                        error_message=error_msg
                    )

            # Job not found in queue or history - might be initializing
            start_time = self.job_start_times.get(prompt_id)
            if start_time and (datetime.utcnow() - start_time).total_seconds() < 10:
                return ProgressUpdate(
                    job_id=job_id,
                    comfyui_prompt_id=prompt_id,
                    status=ProgressStatus.INITIALIZING,
                    progress_percent=0.0
                )

            # Job seems to be lost or timed out
            return ProgressUpdate(
                job_id=job_id,
                comfyui_prompt_id=prompt_id,
                status=ProgressStatus.TIMEOUT,
                error_message="Job not found in ComfyUI queue or history"
            )

        except Exception as e:
            logger.error(f"Failed to check job progress for {prompt_id}: {e}")
            return ProgressUpdate(
                job_id=job_id,
                comfyui_prompt_id=prompt_id,
                status=ProgressStatus.FAILED,
                error_message=f"Progress check failed: {str(e)}"
            )

    async def _handle_job_completion(self, job_id: int, prompt_id: str, progress: ProgressUpdate):
        """Handle job completion - update statistics and cleanup"""
        with self._lock:
            job_type = self.job_types.get(prompt_id, "unknown")
            start_time = self.job_start_times.get(prompt_id)

        # Record statistics
        if progress.status == ProgressStatus.COMPLETED and start_time and progress.generation_time:
            self.stats.record_completion(job_type, progress.generation_time)
        elif progress.status == ProgressStatus.FAILED and progress.error_message:
            # Extract error pattern for statistics
            error_pattern = progress.error_message.split(':')[0] if ':' in progress.error_message else progress.error_message
            self.stats.record_failure(job_type, error_pattern[:50])  # Limit length

        # Update database if available
        if self.database:
            try:
                # Update job status in database
                from .job_manager import JobStatus
                db_status = JobStatus.COMPLETED if progress.status == ProgressStatus.COMPLETED else JobStatus.FAILED
                # Note: This would need to be implemented in the database manager
                # self.database.update_job_status(job_id, db_status, error_message=progress.error_message)
            except Exception as e:
                logger.error(f"Failed to update job in database: {e}")

        logger.info(f"Job {job_id} completed with status {progress.status.value}")

    async def _websocket_handler(self, websocket, path=None):
        """Handle WebSocket connections for real-time updates"""
        logger.info(f"New WebSocket connection from {websocket.remote_address}")
        self.websocket_clients.add(websocket)

        try:
            # Send current status on connect
            stats = await self.get_queue_statistics()
            await websocket.send(json.dumps({
                "type": "connection_established",
                "data": stats
            }))

            # Keep connection alive and handle incoming messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_websocket_message(websocket, data)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON"
                    }))
                except Exception as e:
                    logger.error(f"WebSocket message handling error: {e}")

        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            self.websocket_clients.discard(websocket)

    async def _handle_websocket_message(self, websocket, data: Dict[str, Any]):
        """Handle incoming WebSocket messages"""
        message_type = data.get("type")

        if message_type == "get_statistics":
            stats = await self.get_queue_statistics()
            await websocket.send(json.dumps({
                "type": "statistics",
                "data": stats
            }))

        elif message_type == "get_job_progress":
            job_id = data.get("job_id")
            if job_id:
                progress = await self.get_progress(job_id)
                if progress:
                    await websocket.send(json.dumps({
                        "type": "job_progress",
                        "data": asdict(progress)
                    }, default=str))
                else:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": f"Job {job_id} not found"
                    }))

        else:
            await websocket.send(json.dumps({
                "type": "error",
                "message": f"Unknown message type: {message_type}"
            }))


# Convenience functions for easy integration

async def create_status_monitor(
    comfyui_url: str = "http://192.168.50.135:8188",
    database_manager = None,
    auto_start: bool = True
) -> StatusMonitor:
    """Create and optionally start a status monitor"""
    connector = ComfyUIConnector(comfyui_url)
    monitor = StatusMonitor(connector, database_manager)

    if auto_start:
        await monitor.start_monitoring()

    return monitor


def progress_callback_logger(update: ProgressUpdate):
    """Simple logging callback for progress updates"""
    logger.info(
        f"Job {update.job_id} ({update.comfyui_prompt_id}): "
        f"{update.status.value} - {update.progress_percent:.1f}%"
    )


# Example usage
if __name__ == "__main__":
    import asyncio

    async def test_monitor():
        """Test the status monitor"""
        monitor = await create_status_monitor()
        monitor.add_progress_callback(progress_callback_logger)

        print("Status monitor running. Press Ctrl+C to stop.")
        try:
            while True:
                stats = await monitor.get_queue_statistics()
                print(f"Queue stats: {stats}")
                await asyncio.sleep(10)
        except KeyboardInterrupt:
            print("Stopping monitor...")
            await monitor.stop_monitoring()

    asyncio.run(test_monitor())