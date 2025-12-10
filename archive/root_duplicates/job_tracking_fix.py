"""
Fix for job tracking and real progress monitoring
"""
import asyncio
import requests
import time
from typing import Dict, Any, Optional
from pathlib import Path

COMFYUI_URL = "http://localhost:8188"

class RealProgressMonitor:
    """Monitor real ComfyUI progress instead of fake progress"""

    def __init__(self, jobs_cache: Dict, websocket_connections: Dict):
        self.jobs_cache = jobs_cache
        self.websocket_connections = websocket_connections

    def get_comfyui_progress(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Get real progress from ComfyUI"""
        try:
            # Check queue status
            response = requests.get(f"{COMFYUI_URL}/queue")
            if response.status_code == 200:
                queue_data = response.json()

                # Check if in running queue
                running = queue_data.get("queue_running", [])
                for item in running:
                    if item[0] == prompt_id:
                        # Get actual progress from the execution
                        exec_info = item[1]
                        if isinstance(exec_info, dict):
                            # Extract progress from execution info
                            return {
                                "status": "running",
                                "progress": exec_info.get("progress", 50),
                                "current_node": exec_info.get("node", "unknown")
                            }

                # Check if in pending queue
                pending = queue_data.get("queue_pending", [])
                for idx, item in enumerate(pending):
                    if item[0] == prompt_id:
                        return {
                            "status": "queued",
                            "progress": 0,
                            "queue_position": idx + 1
                        }

            # Check if completed in history
            response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
            if response.status_code == 200:
                history = response.json()
                if prompt_id in history:
                    return {
                        "status": "completed",
                        "progress": 100,
                        "outputs": history[prompt_id].get("outputs", {})
                    }

            return None

        except Exception as e:
            print(f"Error getting ComfyUI progress: {e}")
            return None

    def monitor_job(self, job_id: str, comfyui_id: str):
        """Monitor job with real progress"""
        max_wait = 300  # 5 minutes max
        start_time = time.time()
        last_progress = -1

        while time.time() - start_time < max_wait:
            try:
                # Get real progress from ComfyUI
                progress_info = self.get_comfyui_progress(comfyui_id)

                if progress_info:
                    # Update job in cache
                    if job_id in self.jobs_cache:
                        job = self.jobs_cache[job_id]
                        job["status"] = progress_info["status"]
                        job["progress"] = progress_info["progress"]

                        if "current_node" in progress_info:
                            job["current_node"] = progress_info["current_node"]

                        if "queue_position" in progress_info:
                            job["queue_position"] = progress_info["queue_position"]

                        # Send real progress update if changed
                        if progress_info["progress"] != last_progress:
                            last_progress = progress_info["progress"]
                            self._send_websocket_update(job_id, progress_info)

                        # Check if completed
                        if progress_info["status"] == "completed":
                            self._handle_completion(job_id, comfyui_id, progress_info.get("outputs", {}))
                            return

                time.sleep(0.5)  # Poll every 500ms

            except Exception as e:
                print(f"Monitor error: {e}")
                time.sleep(1)

        # Timeout
        if job_id in self.jobs_cache:
            self.jobs_cache[job_id]["status"] = "failed"
            self.jobs_cache[job_id]["error"] = "Generation timeout after 5 minutes"

    def _handle_completion(self, job_id: str, comfyui_id: str, outputs: Dict):
        """Handle job completion"""
        if job_id not in self.jobs_cache:
            return

        job = self.jobs_cache[job_id]

        # Find output file
        output_found = False
        for node_output in outputs.values():
            if "images" in node_output:
                for img in node_output["images"]:
                    filename = img.get("filename")
                    if filename:
                        output_path = Path(f"/mnt/1TB-storage/ComfyUI/output/{filename}")
                        if output_path.exists():
                            job["output_path"] = str(output_path)
                            job["status"] = "completed"
                            job["progress"] = 100
                            job["completed_at"] = time.time()
                            job["duration"] = time.time() - job.get("start_time", time.time())
                            output_found = True
                            break
                if output_found:
                    break

        if not output_found:
            job["status"] = "failed"
            job["error"] = "No output file found"

        # Send final update
        self._send_websocket_update(job_id, {
            "status": job["status"],
            "progress": job.get("progress", 100),
            "output_path": job.get("output_path")
        })

    def _send_websocket_update(self, job_id: str, progress_info: Dict):
        """Send WebSocket update (runs in thread context)"""
        if job_id in self.websocket_connections:
            try:
                # Create async task to send update
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    self._async_send_update(job_id, progress_info)
                )
                loop.close()
            except Exception as e:
                print(f"WebSocket update error: {e}")

    async def _async_send_update(self, job_id: str, progress_info: Dict):
        """Async helper to send WebSocket update"""
        if job_id in self.websocket_connections:
            ws = self.websocket_connections[job_id]
            await ws.send_json({
                "job_id": job_id,
                "status": progress_info.get("status"),
                "progress": progress_info.get("progress", 0),
                "current_node": progress_info.get("current_node"),
                "queue_position": progress_info.get("queue_position"),
                "output_path": progress_info.get("output_path")
            })


def get_comfyui_execution_progress(prompt_id: str) -> Optional[int]:
    """
    Get real execution progress from ComfyUI by analyzing the workflow execution
    """
    try:
        # First check if it's in the queue
        response = requests.get(f"{COMFYUI_URL}/queue")
        if response.status_code == 200:
            queue_data = response.json()

            # Check running queue for actual progress
            running = queue_data.get("queue_running", [])
            for item in running:
                if len(item) > 0 and item[0] == prompt_id:
                    # Try to extract progress from execution info
                    if len(item) > 2 and isinstance(item[2], dict):
                        # ComfyUI provides node execution info
                        exec_info = item[2]
                        if "execution" in exec_info:
                            nodes_total = exec_info["execution"].get("total", 10)
                            nodes_done = exec_info["execution"].get("done", 0)
                            if nodes_total > 0:
                                return int((nodes_done / nodes_total) * 100)
                    # Default to 50% if running but no detailed progress
                    return 50

            # Check pending queue
            pending = queue_data.get("queue_pending", [])
            for idx, item in enumerate(pending):
                if len(item) > 0 and item[0] == prompt_id:
                    # Still in queue, not started
                    return 0

        # Check history to see if completed
        response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
        if response.status_code == 200:
            history = response.json()
            if prompt_id in history:
                # Job is completed
                return 100

        # Not found anywhere, assume just started
        return 0

    except Exception as e:
        print(f"Error getting ComfyUI progress: {e}")
        return None


# Example integration into existing code:
def monitor_and_complete_fixed(job_id: str, comfyui_id: str, job_data: Dict[str, Any],
                               jobs_cache: Dict, websocket_connections: Dict):
    """Fixed version with real progress monitoring"""
    monitor = RealProgressMonitor(jobs_cache, websocket_connections)
    monitor.monitor_job(job_id, comfyui_id)


if __name__ == "__main__":
    # Test real progress monitoring
    print("Testing real ComfyUI progress monitoring...")

    # Test with a real prompt ID if one is running
    test_prompt_id = "test-prompt-123"
    progress = get_comfyui_execution_progress(test_prompt_id)
    print(f"Progress for {test_prompt_id}: {progress}%")

    # Test the progress monitor
    print("\nTesting RealProgressMonitor...")
    test_jobs = {}
    test_ws = {}
    monitor = RealProgressMonitor(test_jobs, test_ws)

    # Get current queue status
    progress_info = monitor.get_comfyui_progress(test_prompt_id)
    if progress_info:
        print(f"Status: {progress_info}")
    else:
        print("No active jobs found")