#!/usr/bin/env python3
"""
Fixed version of secure_api with proper async handling and real progress
"""
import asyncio
import aiohttp
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
import time
from datetime import datetime
from pathlib import Path
import uuid
from typing import Dict, Any, Optional
import json

# Configuration
PORT = 8328
COMFYUI_URL = "http://localhost:8188"
OUTPUT_DIR = Path("/mnt/1TB-storage/ComfyUI/output")

# Global state
jobs_cache: Dict[str, Dict[str, Any]] = {}
websocket_connections: Dict[str, WebSocket] = {}


class AsyncJobProcessor:
    """Async job processor with real ComfyUI progress tracking"""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.queue = asyncio.Queue()
        self.workers = []

    async def start(self):
        """Start the processor"""
        self.session = aiohttp.ClientSession()
        # Start 3 concurrent workers
        self.workers = [
            asyncio.create_task(self.worker(i))
            for i in range(3)
        ]

    async def stop(self):
        """Stop the processor"""
        # Cancel workers
        for worker in self.workers:
            worker.cancel()
        # Close session
        if self.session:
            await self.session.close()

    async def worker(self, worker_id: int):
        """Process jobs from queue"""
        print(f"Worker {worker_id} started")

        while True:
            try:
                # Get job with timeout to allow checking for cancellation
                job_data = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                await self.process_job(job_data)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                print(f"Worker {worker_id} cancelled")
                break
            except Exception as e:
                print(f"Worker {worker_id} error: {e}")
                await asyncio.sleep(1)

    async def process_job(self, job_data: Dict[str, Any]):
        """Process a single job"""
        job_id = job_data["id"]

        try:
            # Update status
            job_data["status"] = "processing"
            await self.send_progress(job_id, 0, "processing")

            # Submit to ComfyUI
            workflow = self.create_workflow(job_data)
            async with self.session.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    comfyui_id = result.get("prompt_id")

                    # Monitor with real progress
                    await self.monitor_job(job_id, comfyui_id, job_data)
                else:
                    raise Exception(f"ComfyUI error: {response.status}")

        except Exception as e:
            print(f"Job {job_id} failed: {e}")
            job_data["status"] = "failed"
            job_data["error"] = str(e)
            await self.send_progress(job_id, 0, "failed", error=str(e))

    async def monitor_job(self, job_id: str, comfyui_id: str, job_data: Dict[str, Any]):
        """Monitor job with real progress"""
        start_time = time.time()
        max_wait = 300  # 5 minutes
        last_progress = -1

        while time.time() - start_time < max_wait:
            try:
                # Check queue status
                async with self.session.get(f"{COMFYUI_URL}/queue") as response:
                    if response.status == 200:
                        queue_data = await response.json()

                        # Check if running
                        running = queue_data.get("queue_running", [])
                        for item in running:
                            if item and item[0] == comfyui_id:
                                # Extract real progress if available
                                progress = 50  # Default to 50% when running
                                if len(item) > 2 and isinstance(item[2], dict):
                                    exec_info = item[2]
                                    if "execution" in exec_info:
                                        total = exec_info["execution"].get("total", 10)
                                        done = exec_info["execution"].get("done", 0)
                                        if total > 0:
                                            progress = int((done / total) * 100)

                                if progress != last_progress:
                                    last_progress = progress
                                    job_data["progress"] = progress
                                    await self.send_progress(job_id, progress, "processing")
                                break

                        # Check if queued
                        pending = queue_data.get("queue_pending", [])
                        for idx, item in enumerate(pending):
                            if item and item[0] == comfyui_id:
                                if last_progress != 0:
                                    last_progress = 0
                                    job_data["queue_position"] = idx + 1
                                    await self.send_progress(job_id, 0, "queued", queue_position=idx+1)
                                break

                # Check history for completion
                async with self.session.get(f"{COMFYUI_URL}/history/{comfyui_id}") as response:
                    if response.status == 200:
                        history = await response.json()
                        if comfyui_id in history:
                            # Job completed
                            outputs = history[comfyui_id].get("outputs", {})
                            for node_output in outputs.values():
                                if "images" in node_output:
                                    for img in node_output["images"]:
                                        filename = img.get("filename")
                                        if filename:
                                            output_path = OUTPUT_DIR / filename
                                            if output_path.exists():
                                                job_data["output_path"] = str(output_path)
                                                job_data["status"] = "completed"
                                                job_data["progress"] = 100
                                                job_data["duration"] = time.time() - job_data.get("start_time", start_time)
                                                await self.send_progress(job_id, 100, "completed", output_path=str(output_path))
                                                return

                            # No output found
                            raise Exception("No output file found")

                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"Monitor error: {e}")
                await asyncio.sleep(1)

        # Timeout
        job_data["status"] = "failed"
        job_data["error"] = "Timeout"
        await self.send_progress(job_id, 0, "failed", error="Generation timeout")

    async def send_progress(self, job_id: str, progress: int, status: str, **extra):
        """Send progress update via WebSocket"""
        if job_id in websocket_connections:
            ws = websocket_connections[job_id]
            try:
                await ws.send_json({
                    "job_id": job_id,
                    "progress": progress,
                    "status": status,
                    "timestamp": time.time(),
                    **extra
                })
            except Exception as e:
                print(f"WebSocket error for {job_id}: {e}")
                websocket_connections.pop(job_id, None)

    def create_workflow(self, job_data: Dict[str, Any]) -> Dict:
        """Create ComfyUI workflow"""
        # Simplified workflow creation
        prompt = job_data.get("prompt", "anime girl")
        negative = job_data.get("negative_prompt", "bad quality")
        width = job_data.get("width", 512)
        height = job_data.get("height", 768)

        # Return basic workflow
        return {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 42,
                    "steps": 20,
                    "cfg": 7,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "animagineXLV31_v30.safetensors"
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1
                }
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["4", 1]
                }
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative,
                    "clip": ["4", 1]
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                }
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["8", 0],
                    "filename_prefix": "anime"
                }
            }
        }


# Global processor instance
processor = AsyncJobProcessor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle"""
    # Startup
    await processor.start()
    print(f"API server started on port {PORT}")
    yield
    # Shutdown
    await processor.stop()
    print("API server shutting down")


# Create FastAPI app
app = FastAPI(title="Anime Generation API", lifespan=lifespan)


@app.post("/generate")
async def generate_image(request: dict):
    """Generate image with async processing"""
    job_id = str(uuid.uuid4())[:8]

    job_data = {
        "id": job_id,
        "status": "queued",
        "prompt": request.get("prompt", "anime girl"),
        "negative_prompt": request.get("negative_prompt", "bad quality"),
        "width": request.get("width", 512),
        "height": request.get("height", 768),
        "created_at": datetime.utcnow().isoformat(),
        "start_time": time.time(),
        "progress": 0
    }

    # Store in cache
    jobs_cache[job_id] = job_data

    # Add to async queue
    await processor.queue.put(job_data)

    return {
        "job_id": job_id,
        "status": "queued",
        "queue_size": processor.queue.qsize(),
        "websocket_url": f"ws://localhost:{PORT}/ws/{job_id}"
    }


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status"""
    if job_id not in jobs_cache:
        raise HTTPException(404, f"Job {job_id} not found")

    return jobs_cache[job_id]


@app.websocket("/ws/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    """WebSocket for real-time progress"""
    await websocket.accept()
    websocket_connections[job_id] = websocket

    try:
        while True:
            # Keep connection alive and send updates
            await asyncio.sleep(1)

            if job_id in jobs_cache:
                job = jobs_cache[job_id]

                # Send current status
                await websocket.send_json({
                    "job_id": job_id,
                    "status": job["status"],
                    "progress": job.get("progress", 0),
                    "queue_position": job.get("queue_position"),
                    "output_path": job.get("output_path")
                })

                # Close if completed or failed
                if job["status"] in ["completed", "failed"]:
                    break

    except WebSocketDisconnect:
        print(f"WebSocket disconnected for {job_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        websocket_connections.pop(job_id, None)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "jobs_in_memory": len(jobs_cache),
        "active_websockets": len(websocket_connections),
        "queue_size": processor.queue.qsize()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)