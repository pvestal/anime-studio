#!/usr/bin/env python3
"""
Enhanced Generation API with UX improvements
Integrates real-time preview, contextual progress, and smart error recovery
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, Optional, List, Any
import asyncio
import uuid
import logging
import traceback
from datetime import datetime

from ux_enhancements import (
    UXEnhancementManager, GenerationPhase, ProgressUpdate
)
from optimized_workflows import OptimizedWorkflows
from gpu_optimization import GPUOptimizer
from generation_cache import GenerationCache

logger = logging.getLogger(__name__)

class EnhancedGenerationRequest(BaseModel):
    """Enhanced generation request with UX preferences"""
    prompt: str = Field(..., description="Generation prompt")
    negative_prompt: Optional[str] = Field(None, description="Negative prompt")
    mode: str = Field("balanced", description="Generation mode: draft, balanced, quality")
    width: Optional[int] = Field(768, description="Image width")
    height: Optional[int] = Field(768, description="Image height")
    seed: Optional[int] = Field(-1, description="Random seed")

    # UX preferences
    enable_preview: bool = Field(True, description="Enable real-time preview")
    enable_auto_recovery: bool = Field(True, description="Enable automatic error recovery")
    progress_detail_level: str = Field("detailed", description="Progress detail: minimal, normal, detailed")

    # Batch options
    batch_size: Optional[int] = Field(1, description="Number of variations to generate")
    variations_seed_offset: Optional[int] = Field(1, description="Seed offset for variations")

class GenerationStatus(BaseModel):
    """Generation job status with rich information"""
    job_id: str
    status: str  # queued, processing, completed, failed, recovering
    phase: Optional[str] = None
    progress: float = 0.0
    message: str = ""
    preview_url: Optional[str] = None
    estimated_time_remaining: Optional[float] = None
    output_paths: List[str] = []
    error: Optional[Dict[str, Any]] = None
    recovery_attempted: bool = False
    created_at: datetime
    updated_at: datetime

class EnhancedGenerationAPI:
    """Enhanced API with rich UX features"""

    def __init__(self):
        self.app = FastAPI(title="Enhanced Anime Generation API")
        self.ux_manager = UXEnhancementManager()
        self.workflows = OptimizedWorkflows()
        self.gpu_optimizer = GPUOptimizer()
        self.cache = GenerationCache()

        self.active_jobs: Dict[str, GenerationStatus] = {}
        self.websocket_connections: Dict[str, WebSocket] = {}

        self._setup_routes()

    def _setup_routes(self):
        """Setup API routes with enhanced features"""

        @self.app.post("/api/generate/enhanced")
        async def generate_enhanced(
            request: EnhancedGenerationRequest,
            background_tasks: BackgroundTasks
        ):
            """Enhanced generation endpoint with UX features"""
            job_id = str(uuid.uuid4())

            # Initialize job status
            status = GenerationStatus(
                job_id=job_id,
                status="queued",
                phase=GenerationPhase.INITIALIZING.name,
                message="Preparing your generation...",
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            self.active_jobs[job_id] = status

            # Start background generation
            background_tasks.add_task(
                self._process_generation,
                job_id,
                request
            )

            return {
                "job_id": job_id,
                "status": "queued",
                "message": "Generation queued successfully",
                "websocket_url": f"/ws/generate/{job_id}"
            }

        @self.app.websocket("/ws/generate/{job_id}")
        async def websocket_endpoint(websocket: WebSocket, job_id: str):
            """WebSocket endpoint for real-time updates"""
            await websocket.accept()
            self.websocket_connections[job_id] = websocket

            # Send initial status
            if job_id in self.active_jobs:
                status = self.active_jobs[job_id]
                await websocket.send_json({
                    "type": "status",
                    "data": status.model_dump()
                })

            try:
                # Keep connection alive and handle incoming messages
                while True:
                    data = await websocket.receive_text()
                    # Handle client messages if needed
                    if data == "ping":
                        await websocket.send_text("pong")
            except WebSocketDisconnect:
                if job_id in self.websocket_connections:
                    del self.websocket_connections[job_id]

        @self.app.get("/api/generate/status/{job_id}")
        async def get_status(job_id: str):
            """Get generation status with rich details"""
            if job_id not in self.active_jobs:
                raise HTTPException(status_code=404, detail="Job not found")

            return self.active_jobs[job_id]

        @self.app.post("/api/generate/batch")
        async def generate_batch(
            requests: List[EnhancedGenerationRequest],
            background_tasks: BackgroundTasks
        ):
            """Batch generation with queue management"""
            job_ids = []

            for request in requests:
                job_id = str(uuid.uuid4())

                status = GenerationStatus(
                    job_id=job_id,
                    status="queued",
                    message=f"Queued (position {len(job_ids) + 1} of {len(requests)})",
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                self.active_jobs[job_id] = status
                job_ids.append(job_id)

                # Add to background queue
                background_tasks.add_task(
                    self._process_generation,
                    job_id,
                    request
                )

            return {
                "batch_id": str(uuid.uuid4()),
                "job_ids": job_ids,
                "total_jobs": len(job_ids),
                "message": f"Batch of {len(job_ids)} generations queued"
            }

        @self.app.get("/api/generate/queue")
        async def get_queue_status():
            """Get current queue status with visualization data"""
            queued = [j for j in self.active_jobs.values() if j.status == "queued"]
            processing = [j for j in self.active_jobs.values() if j.status == "processing"]
            completed = [j for j in self.active_jobs.values() if j.status == "completed"]
            failed = [j for j in self.active_jobs.values() if j.status == "failed"]

            # Calculate average processing time
            completed_times = []
            for job in completed:
                duration = (job.updated_at - job.created_at).total_seconds()
                completed_times.append(duration)

            avg_time = sum(completed_times) / len(completed_times) if completed_times else 0

            return {
                "queue_length": len(queued),
                "processing": len(processing),
                "completed_today": len(completed),
                "failed_today": len(failed),
                "average_time_seconds": avg_time,
                "estimated_wait_time": avg_time * len(queued),
                "gpu_status": self.gpu_optimizer.get_gpu_stats().__dict__
            }

    async def _process_generation(self, job_id: str, request: EnhancedGenerationRequest):
        """Process generation with enhanced UX features"""
        try:
            # Update status to processing
            self.active_jobs[job_id].status = "processing"
            self.active_jobs[job_id].updated_at = datetime.now()

            # Setup WebSocket connection for updates
            websocket = self.websocket_connections.get(job_id)

            async def send_update(message: str):
                if websocket:
                    try:
                        await websocket.send_text(message)
                    except:
                        pass

            # Start UX tracking
            await self.ux_manager.track_generation(
                job_id=job_id,
                websocket_send=send_update if request.enable_preview else None,
                total_steps=20 if request.mode == "balanced" else (8 if request.mode == "draft" else 30)
            )

            # Check cache first
            cache_key = f"{request.prompt}_{request.width}_{request.height}_{request.mode}"
            cached_result = self.cache.get_cached_output(cache_key)

            if cached_result:
                # Use cached result
                self.active_jobs[job_id].status = "completed"
                self.active_jobs[job_id].output_paths = [cached_result["output_path"]]
                self.active_jobs[job_id].message = "Retrieved from cache"
                self.active_jobs[job_id].progress = 100.0

                if websocket:
                    await websocket.send_json({
                        "type": "complete",
                        "cached": True,
                        "output_path": cached_result["output_path"]
                    })

                return

            # Prepare generation parameters based on mode
            params = self._prepare_generation_params(request)

            # Check GPU availability
            required_vram = self.gpu_optimizer.estimate_generation_vram(
                model="anime_model",
                width=params["width"],
                height=params["height"],
                batch_size=params.get("batch_size", 1),
                generation_type="image"
            )

            if not self.gpu_optimizer.check_vram_availability(required_vram):
                # Try to recover with reduced settings
                if request.enable_auto_recovery:
                    await self._attempt_recovery(job_id, request, "memory", params)
                    return
                else:
                    raise RuntimeError(f"Insufficient VRAM: {required_vram}MB required")

            # Execute generation with progress tracking
            output_paths = await self._execute_with_progress(job_id, params, request)

            # Update final status
            self.active_jobs[job_id].status = "completed"
            self.active_jobs[job_id].output_paths = output_paths
            self.active_jobs[job_id].progress = 100.0
            self.active_jobs[job_id].phase = GenerationPhase.COMPLETE.name
            self.active_jobs[job_id].message = "Generation complete!"
            self.active_jobs[job_id].updated_at = datetime.now()

            # Cache the result
            if output_paths:
                self.cache.cache_output(
                    prompt=request.prompt,
                    params=params,
                    output_path=output_paths[0],
                    quality_score=8.0  # Would be calculated
                )

            # Send completion via WebSocket
            if websocket:
                await websocket.send_json({
                    "type": "complete",
                    "output_paths": output_paths,
                    "generation_time": (
                        self.active_jobs[job_id].updated_at -
                        self.active_jobs[job_id].created_at
                    ).total_seconds()
                })

        except Exception as e:
            logger.error(f"Generation failed for {job_id}: {e}")
            logger.error(traceback.format_exc())

            # Try auto-recovery if enabled
            if request.enable_auto_recovery and not self.active_jobs[job_id].recovery_attempted:
                await self._attempt_recovery(job_id, request, "error", {"error": str(e)})
            else:
                # Mark as failed
                self.active_jobs[job_id].status = "failed"
                self.active_jobs[job_id].error = {
                    "type": "generation_error",
                    "message": str(e),
                    "traceback": traceback.format_exc()
                }
                self.active_jobs[job_id].updated_at = datetime.now()

                if job_id in self.websocket_connections:
                    await self.websocket_connections[job_id].send_json({
                        "type": "error",
                        "error": str(e)
                    })

        finally:
            # Cleanup
            self.ux_manager.cleanup_job(job_id)

    def _prepare_generation_params(self, request: EnhancedGenerationRequest) -> Dict[str, Any]:
        """Prepare generation parameters based on request"""
        # Get workflow configuration
        if request.mode == "draft":
            base_params = self.workflows.DRAFT_CONFIG
        elif request.mode == "quality":
            base_params = self.workflows.HIGH_QUALITY_CONFIG
        else:
            base_params = self.workflows.STANDARD_CONFIG

        # Override with request parameters
        params = {
            **base_params,
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt or "low quality, blurry",
            "width": request.width,
            "height": request.height,
            "seed": request.seed,
            "batch_size": request.batch_size
        }

        return params

    async def _execute_with_progress(
        self,
        job_id: str,
        params: Dict[str, Any],
        request: EnhancedGenerationRequest
    ) -> List[str]:
        """Execute generation with progress tracking"""
        output_paths = []

        # Simulate generation with progress updates
        total_steps = params.get("steps", 20)

        for step in range(total_steps):
            # Update progress
            await self.ux_manager.update_progress(
                job_id=job_id,
                current_step=step + 1,
                preview_path=None,  # Would get from ComfyUI
                custom_message=None
            )

            # Update job status
            progress = ((step + 1) / total_steps) * 100
            phase = self.ux_manager.progress_tracker._determine_phase(progress)

            self.active_jobs[job_id].progress = progress
            self.active_jobs[job_id].phase = phase.name
            self.active_jobs[job_id].message = phase.message
            self.active_jobs[job_id].updated_at = datetime.now()

            # Simulate work
            await asyncio.sleep(0.5 if request.mode == "draft" else 1.0)

        # Generate output paths (would come from ComfyUI)
        for i in range(request.batch_size):
            output_path = f"/mnt/1TB-storage/ComfyUI/output/{job_id}_{i}.png"
            output_paths.append(output_path)

        return output_paths

    async def _attempt_recovery(
        self,
        job_id: str,
        request: EnhancedGenerationRequest,
        error_type: str,
        context: Dict[str, Any]
    ):
        """Attempt automatic recovery from errors"""
        self.active_jobs[job_id].status = "recovering"
        self.active_jobs[job_id].recovery_attempted = True
        self.active_jobs[job_id].message = "Attempting automatic recovery..."

        # Create modified request based on error type
        if error_type == "memory":
            # Reduce memory usage
            request.width = min(512, request.width)
            request.height = min(512, request.height)
            request.mode = "draft"
            request.batch_size = 1

        # Retry with modified parameters
        try:
            await self._process_generation(job_id, request)
        except Exception as e:
            logger.error(f"Recovery failed for {job_id}: {e}")
            self.active_jobs[job_id].status = "failed"
            self.active_jobs[job_id].error = {
                "type": "recovery_failed",
                "original_error": error_type,
                "recovery_error": str(e)
            }

# Create the enhanced API instance
enhanced_api = EnhancedGenerationAPI()
app = enhanced_api.app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8329)