"""
ComfyUI Connector Module
Handles all communication with ComfyUI server
"""
import aiohttp
import asyncio
import json
import time
from typing import Dict, Any, Optional, Tuple, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ComfyUIConnector:
    """Manages all ComfyUI interactions"""

    def __init__(self, base_url: str = "http://192.168.50.135:8188"):
        self.base_url = base_url
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def submit_workflow(self, workflow: Dict[str, Any], client_id: str = None) -> Optional[str]:
        """Submit workflow to ComfyUI and return prompt_id"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            payload = {
                "prompt": workflow,
                "client_id": client_id or f"anime_{id(self)}"
            }

            async with self.session.post(
                f"{self.base_url}/prompt",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    prompt_id = result.get("prompt_id")
                    logger.info(f"Submitted workflow to ComfyUI: {prompt_id}")
                    return prompt_id
                else:
                    logger.error(f"ComfyUI returned status {response.status}")
                    return None

        except Exception as e:
            logger.error(f"Failed to submit to ComfyUI: {e}")
            return None

    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(f"{self.base_url}/queue") as response:
                data = await response.json()
                return {
                    "running": len(data.get("queue_running", [])),
                    "pending": len(data.get("queue_pending", [])),
                    "details": data
                }
        except Exception as e:
            logger.error(f"Failed to get queue status: {e}")
            return {"running": 0, "pending": 0, "error": str(e)}

    async def get_history(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Get generation history for a specific prompt"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(f"{self.base_url}/history/{prompt_id}") as response:
                if response.status == 200:
                    history = await response.json()
                    return history.get(prompt_id)
                return None
        except Exception as e:
            logger.error(f"Failed to get history: {e}")
            return None

    async def interrupt_generation(self) -> bool:
        """Interrupt current generation"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.post(f"{self.base_url}/interrupt") as response:
                return response.status == 200
        except:
            return False

    async def check_health(self) -> bool:
        """Check if ComfyUI is responding"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(
                f"{self.base_url}/system_stats",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status == 200
        except:
            return False

    async def monitor_job_progress(self, prompt_id: str,
                                 progress_callback=None,
                                 checkpoint_callback=None,
                                 timeout_minutes: int = 30) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Monitor job progress with error detection and checkpointing"""
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        last_progress = 0
        stall_count = 0
        max_stall_checks = 10  # Allow 10 checks with no progress before considering stalled

        while True:
            try:
                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    return False, f"Job timeout after {timeout_minutes} minutes", None

                # Get current status
                history = await self.get_history(prompt_id)
                if history:
                    # Job completed successfully
                    if "outputs" in history:
                        logger.info(f"Job {prompt_id} completed successfully")
                        return True, None, history

                    # Check for errors in history
                    if "error" in history or "exception" in history:
                        error_info = history.get("error", history.get("exception", {}))
                        error_message = self._extract_error_message(error_info)
                        return False, error_message, history

                # Check queue status for progress estimation
                queue_status = await self.get_queue_status()
                if "error" in queue_status:
                    return False, f"ComfyUI queue error: {queue_status['error']}", None

                # Estimate progress based on queue position
                running_jobs = queue_status.get("running", 0)
                pending_jobs = queue_status.get("pending", 0)

                if running_jobs == 0 and pending_jobs == 0:
                    # No jobs in queue, check if our job is done
                    await asyncio.sleep(2)
                    continue

                # Calculate rough progress (this is an estimation)
                estimated_progress = min(85, (elapsed / timeout_seconds) * 100)

                # Check for stalled progress
                if abs(estimated_progress - last_progress) < 1:
                    stall_count += 1
                    if stall_count >= max_stall_checks:
                        return False, "Job appears to be stalled with no progress", None
                else:
                    stall_count = 0
                    last_progress = estimated_progress

                # Call progress callback if provided
                if progress_callback:
                    await progress_callback(prompt_id, estimated_progress, elapsed)

                # Create checkpoint every 25% progress if callback provided
                if checkpoint_callback and estimated_progress > 0:
                    checkpoint_thresholds = [25, 50, 75]
                    for threshold in checkpoint_thresholds:
                        if (estimated_progress >= threshold and
                            last_progress < threshold):
                            await checkpoint_callback(
                                prompt_id,
                                threshold,
                                {"elapsed_time": elapsed, "queue_status": queue_status}
                            )

                await asyncio.sleep(3)  # Check every 3 seconds

            except Exception as e:
                logger.error(f"Error monitoring job {prompt_id}: {e}")
                return False, f"Monitoring error: {str(e)}", None

    def _extract_error_message(self, error_info: Any) -> str:
        """Extract meaningful error message from ComfyUI error info"""
        if isinstance(error_info, dict):
            # Try different error fields
            for field in ["message", "error", "exception", "traceback"]:
                if field in error_info and error_info[field]:
                    error_text = str(error_info[field])
                    # Extract key error patterns
                    if "CUDA out of memory" in error_text:
                        return "CUDA out of memory - GPU memory insufficient"
                    elif "FileNotFoundError" in error_text:
                        return f"File not found: {error_text}"
                    elif "TimeoutError" in error_text:
                        return "Request timeout during generation"
                    elif "ConnectionError" in error_text:
                        return "Network connection error"
                    return error_text[:200]  # Truncate long messages

        elif isinstance(error_info, str):
            return error_info[:200]

        return "Unknown error occurred"

    async def get_system_stats(self) -> Dict[str, Any]:
        """Get ComfyUI system statistics for monitoring"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(f"{self.base_url}/system_stats") as response:
                if response.status == 200:
                    return await response.json()
                return {"error": f"HTTP {response.status}"}
        except Exception as e:
            return {"error": str(e)}

    async def clear_queue(self) -> bool:
        """Clear the ComfyUI queue (emergency use only)"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.post(f"{self.base_url}/queue",
                                       json={"clear": True}) as response:
                return response.status == 200
        except:
            return False

    async def cancel_job(self, prompt_id: str) -> bool:
        """Cancel a specific job"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            payload = {"delete": [prompt_id]}
            async with self.session.post(f"{self.base_url}/queue",
                                       json=payload) as response:
                return response.status == 200
        except:
            return False