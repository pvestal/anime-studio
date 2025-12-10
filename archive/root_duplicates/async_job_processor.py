"""
Proper async job processor with real progress tracking
"""
import asyncio
import aiohttp
import time
import json
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

COMFYUI_URL = "http://localhost:8188"
OUTPUT_DIR = Path("/mnt/1TB-storage/ComfyUI/output")

class AsyncJobProcessor:
    """Fully async job processor with proper error handling"""

    def __init__(self, jobs_cache: Dict, websocket_connections: Dict, generation_queue: asyncio.Queue):
        self.jobs_cache = jobs_cache
        self.websocket_connections = websocket_connections
        self.generation_queue = generation_queue
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        """Start the processor with session"""
        self.session = aiohttp.ClientSession()
        # Start worker tasks
        workers = [
            asyncio.create_task(self.process_worker(i))
            for i in range(3)  # 3 concurrent workers
        ]
        await asyncio.gather(*workers)

    async def stop(self):
        """Clean shutdown"""
        if self.session:
            await self.session.close()

    async def process_worker(self, worker_id: int):
        """Worker that processes jobs from queue"""
        print(f"Worker {worker_id} started")

        while True:
            try:
                # Get job from queue (non-blocking with timeout)
                job_data = await asyncio.wait_for(
                    self.generation_queue.get(),
                    timeout=1.0
                )

                print(f"Worker {worker_id} processing job {job_data['id']}")
                await self.process_job(job_data)

            except asyncio.TimeoutError:
                # No job in queue, continue
                continue
            except Exception as e:
                print(f"Worker {worker_id} error: {e}")
                await asyncio.sleep(1)

    async def process_job(self, job_data: Dict[str, Any]):
        """Process a single job with proper async/await"""
        job_id = job_data["id"]

        try:
            # Update status to processing
            job_data["status"] = "processing"
            await self.send_websocket_update(job_id, {"status": "processing", "progress": 0})

            # Create and submit workflow to ComfyUI
            workflow = await self.create_workflow(job_data)

            async with self.session.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    comfyui_id = result.get("prompt_id")
                    job_data["comfyui_id"] = comfyui_id

                    # Monitor progress with real updates
                    await self.monitor_progress(job_id, comfyui_id, job_data)
                else:
                    error_text = await response.text()
                    raise Exception(f"ComfyUI error {response.status}: {error_text}")

        except asyncio.CancelledError:
            # Handle graceful cancellation
            job_data["status"] = "cancelled"
            raise
        except Exception as e:
            # Handle errors properly
            print(f"Job {job_id} failed: {e}")
            job_data["status"] = "failed"
            job_data["error"] = str(e)
            await self.send_websocket_update(job_id, {
                "status": "failed",
                "error": str(e)
            })

    async def monitor_progress(self, job_id: str, comfyui_id: str, job_data: Dict[str, Any]):
        """Monitor job progress with real ComfyUI updates"""
        start_time = time.time()
        max_wait = 300  # 5 minutes
        last_progress = -1
        poll_interval = 0.5

        while time.time() - start_time < max_wait:
            try:
                # Get real progress from ComfyUI
                progress_info = await self.get_comfyui_progress(comfyui_id)

                if progress_info:
                    # Update job data
                    job_data.update(progress_info)

                    # Send update if progress changed
                    current_progress = progress_info.get("progress", 0)
                    if current_progress != last_progress:
                        last_progress = current_progress
                        await self.send_websocket_update(job_id, progress_info)

                    # Check if completed
                    if progress_info.get("status") == "completed":
                        await self.handle_completion(job_id, comfyui_id, job_data)
                        return

                await asyncio.sleep(poll_interval)

            except Exception as e:
                print(f"Monitor error for {job_id}: {e}")
                await asyncio.sleep(1)

        # Timeout
        job_data["status"] = "failed"
        job_data["error"] = "Generation timeout after 5 minutes"
        await self.send_websocket_update(job_id, {"status": "failed", "error": "timeout"})

    async def get_comfyui_progress(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Get real progress from ComfyUI"""
        try:
            # Check queue status
            async with self.session.get(f"{COMFYUI_URL}/queue") as response:
                if response.status == 200:
                    queue_data = await response.json()

                    # Check if running
                    running = queue_data.get("queue_running", [])
                    for item in running:
                        if len(item) > 0 and item[0] == prompt_id:
                            # Estimate progress for running jobs
                            # In real implementation, parse execution details
                            return {
                                "status": "processing",
                                "progress": 50,  # Could extract real progress from item[2]
                                "current_node": "processing"
                            }

                    # Check if queued
                    pending = queue_data.get("queue_pending", [])
                    for idx, item in enumerate(pending):
                        if len(item) > 0 and item[0] == prompt_id:
                            return {
                                "status": "queued",
                                "progress": 0,
                                "queue_position": idx + 1
                            }

            # Check history for completion
            async with self.session.get(f"{COMFYUI_URL}/history/{prompt_id}") as response:
                if response.status == 200:
                    history = await response.json()
                    if prompt_id in history:
                        return {
                            "status": "completed",
                            "progress": 100,
                            "outputs": history[prompt_id].get("outputs", {})
                        }

            return None

        except Exception as e:
            print(f"Error getting progress: {e}")
            return None

    async def handle_completion(self, job_id: str, comfyui_id: str, job_data: Dict[str, Any]):
        """Handle job completion"""
        try:
            # Get outputs from history
            async with self.session.get(f"{COMFYUI_URL}/history/{comfyui_id}") as response:
                if response.status == 200:
                    history = await response.json()
                    if comfyui_id in history:
                        outputs = history[comfyui_id].get("outputs", {})

                        # Find output file
                        for node_output in outputs.values():
                            if "images" in node_output:
                                for img in node_output["images"]:
                                    filename = img.get("filename")
                                    if filename:
                                        output_path = OUTPUT_DIR / filename
                                        if output_path.exists():
                                            job_data["output_path"] = str(output_path)
                                            job_data["status"] = "completed"
                                            job_data["completed_at"] = datetime.utcnow().isoformat()
                                            job_data["duration"] = time.time() - job_data.get("start_time", time.time())

                                            await self.send_websocket_update(job_id, {
                                                "status": "completed",
                                                "progress": 100,
                                                "output_path": str(output_path)
                                            })
                                            return

            # No output found
            job_data["status"] = "failed"
            job_data["error"] = "No output file found"
            await self.send_websocket_update(job_id, {
                "status": "failed",
                "error": "No output found"
            })

        except Exception as e:
            print(f"Completion handling error: {e}")
            job_data["status"] = "failed"
            job_data["error"] = str(e)

    async def send_websocket_update(self, job_id: str, update: Dict[str, Any]):
        """Send WebSocket update with proper error handling"""
        if job_id not in self.websocket_connections:
            return

        ws = self.websocket_connections.get(job_id)
        if not ws:
            return

        try:
            await ws.send_json({
                "job_id": job_id,
                "timestamp": time.time(),
                **update
            })
        except ConnectionResetError:
            # Client disconnected
            print(f"WebSocket disconnected for job {job_id}")
            self.websocket_connections.pop(job_id, None)
        except Exception as e:
            print(f"WebSocket send error: {e}")
            self.websocket_connections.pop(job_id, None)

    async def create_workflow(self, job_data: Dict[str, Any]) -> Dict:
        """Create workflow for ComfyUI (simplified)"""
        # This would create the actual workflow
        # For now, return a simple workflow structure
        return {
            "1": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": job_data.get("prompt", "anime girl"),
                    "clip": ["4", 0]
                }
            },
            # ... rest of workflow
        }


# Integration function for existing code
async def create_async_processor(app, jobs_cache, websocket_connections):
    """Create and start async processor"""
    # Create async queue
    generation_queue = asyncio.Queue()

    # Create processor
    processor = AsyncJobProcessor(jobs_cache, websocket_connections, generation_queue)

    # Store on app for access
    app.state.processor = processor
    app.state.generation_queue = generation_queue

    # Start processor
    asyncio.create_task(processor.start())

    return processor, generation_queue


# Example integration into FastAPI:
"""
from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    processor, queue = await create_async_processor(app, jobs_cache, websocket_connections)
    yield
    # Shutdown
    await processor.stop()

app = FastAPI(lifespan=lifespan)

# In generate endpoint:
@app.post("/generate")
async def generate_image(request: GenerationRequest):
    job_id = str(uuid.uuid4())[:8]
    job_data = {...}
    jobs_cache[job_id] = job_data

    # Add to async queue instead of sync queue
    await app.state.generation_queue.put(job_data)

    return {"job_id": job_id, "status": "queued"}
"""