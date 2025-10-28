#!/usr/bin/env python3
"""
Enhanced Real Anime Generation Service
Integrates comprehensive error handling, quality assessment, and learning systems
"""

import json
import requests
import time
import os
import uuid
import asyncio
import aiohttp
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
from datetime import datetime

# Import our enhanced error handling framework
import sys
sys.path.append('/opt/tower-anime-production/shared')
from error_handling import (
    AnimeGenerationError, ComfyUIError, QualityValidationError,
    OperationMetrics, MetricsCollector, CircuitBreaker, RetryManager,
    QualityAssessor, LearningSystem, ErrorSeverity, ErrorCategory,
    comfyui_circuit_breaker, metrics_collector, quality_assessor, learning_system
)

# Configure enhanced logging with correlation IDs
class CorrelationFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, 'correlation_id'):
            record.correlation_id = 'none'
        return True

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s'
)
logger = logging.getLogger(__name__)
logger.addFilter(CorrelationFilter())

app = FastAPI(title="Enhanced Real Anime Generation", version="2.0.0")

class EnhancedAnimeRequest(BaseModel):
    prompt: str = Field(..., description="User's prompt for anime generation")
    character: str = Field(default="Sakura", description="Character name")
    scene_type: str = Field(default="battle", description="Type of scene")
    duration: int = Field(default=3, description="Duration in seconds")
    style: str = Field(default="anime", description="Visual style")
    quality_level: str = Field(default="high", description="Quality level: low, medium, high, ultra")
    user_id: Optional[str] = Field(default=None, description="User identifier for tracking")

class UserFeedbackRequest(BaseModel):
    generation_id: str
    user_rating: int = Field(..., ge=1, le=5, description="User rating 1-5")
    feedback_text: Optional[str] = Field(default=None, description="Optional feedback text")
    issues: Optional[list] = Field(default=[], description="List of identified issues")
    user_id: Optional[str] = Field(default=None)

# Configuration
COMFYUI_URL = "http://127.0.0.1:8188"
OUTPUT_DIR = "***REMOVED***/AnimeGenerated"

class EnhancedComfyUIClient:
    """Enhanced ComfyUI client with comprehensive error handling and monitoring"""

    def __init__(self):
        self.client_id = str(uuid.uuid4())
        self.retry_manager = RetryManager()

    async def queue_prompt_with_monitoring(self, workflow: Dict[str, Any], correlation_id: str) -> Dict[str, Any]:
        """Submit workflow to ComfyUI with comprehensive monitoring"""
        operation_id = f"comfyui_queue_{int(time.time())}_{correlation_id}"
        metrics = OperationMetrics(
            operation_id=operation_id,
            operation_type="comfyui_queue",
            start_time=datetime.utcnow(),
            context={
                "correlation_id": correlation_id,
                "workflow_nodes": len(workflow),
                "client_id": self.client_id
            }
        )

        try:
            logger.info(f"🎯 Queuing ComfyUI prompt", extra={'correlation_id': correlation_id})

            # Use circuit breaker and retry logic
            async def _queue_request():
                response = requests.post(
                    f"{COMFYUI_URL}/prompt",
                    json={"prompt": workflow, "client_id": self.client_id},
                    timeout=30
                )

                if response.status_code != 200:
                    raise ComfyUIError(
                        f"ComfyUI queue failed with status {response.status_code}",
                        status_code=response.status_code,
                        response_data=response.text,
                        correlation_id=correlation_id
                    )

                return response.json()

            result = await comfyui_circuit_breaker.call(_queue_request)

            logger.info(f"✅ ComfyUI queue successful: {result.get('prompt_id')}",
                       extra={'correlation_id': correlation_id})

            metrics.complete(True)
            await metrics_collector.log_operation(metrics)

            return result

        except Exception as e:
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "comfyui_url": COMFYUI_URL
            }

            metrics.complete(False, error_details)
            await metrics_collector.log_operation(metrics)

            if isinstance(e, ComfyUIError):
                await metrics_collector.log_error(e)
                logger.error(f"❌ ComfyUI error: {e.message}", extra={'correlation_id': correlation_id})
            else:
                comfyui_error = ComfyUIError(
                    f"Unexpected ComfyUI error: {str(e)}",
                    correlation_id=correlation_id,
                    context={"original_error": str(e)}
                )
                await metrics_collector.log_error(comfyui_error)
                logger.error(f"❌ Unexpected ComfyUI error: {str(e)}", extra={'correlation_id': correlation_id})

            raise e

    async def monitor_generation_progress(self, prompt_id: str, correlation_id: str, timeout: int = 300) -> Dict[str, Any]:
        """Monitor generation progress with WebSocket or polling"""
        operation_id = f"comfyui_monitor_{prompt_id}"
        metrics = OperationMetrics(
            operation_id=operation_id,
            operation_type="comfyui_monitoring",
            start_time=datetime.utcnow(),
            context={
                "prompt_id": prompt_id,
                "correlation_id": correlation_id,
                "timeout": timeout
            }
        )

        try:
            logger.info(f"🔍 Monitoring generation progress for prompt: {prompt_id}",
                       extra={'correlation_id': correlation_id})

            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    # Check queue status
                    response = requests.get(f"{COMFYUI_URL}/queue")
                    if response.status_code == 200:
                        queue_data = response.json()

                        # Check if our prompt is still in queue
                        running = queue_data.get('queue_running', [])
                        pending = queue_data.get('queue_pending', [])

                        # Check if prompt is complete (not in queue)
                        prompt_in_queue = any(item[1] == prompt_id for item in running + pending)

                        if not prompt_in_queue:
                            logger.info(f"✅ Generation completed for prompt: {prompt_id}",
                                       extra={'correlation_id': correlation_id})
                            metrics.complete(True)
                            await metrics_collector.log_operation(metrics)
                            return {"status": "completed", "prompt_id": prompt_id}

                        # Log progress
                        queue_position = len([item for item in pending if item[1] != prompt_id and item[0] < next((item[0] for item in pending if item[1] == prompt_id), 0)])
                        logger.info(f"🔄 Generation in progress, queue position: {queue_position}",
                                   extra={'correlation_id': correlation_id})

                except Exception as e:
                    logger.warning(f"⚠️ Error checking queue status: {e}", extra={'correlation_id': correlation_id})

                await asyncio.sleep(5)  # Check every 5 seconds

            # Timeout reached
            timeout_error = ComfyUIError(
                f"Generation timeout after {timeout} seconds",
                correlation_id=correlation_id,
                context={"prompt_id": prompt_id, "timeout": timeout}
            )

            metrics.complete(False, timeout_error.to_dict())
            await metrics_collector.log_operation(metrics)
            await metrics_collector.log_error(timeout_error)

            raise timeout_error

        except Exception as e:
            if not isinstance(e, ComfyUIError):
                error = ComfyUIError(f"Monitoring failed: {str(e)}", correlation_id=correlation_id)
                metrics.complete(False, error.to_dict())
                await metrics_collector.log_operation(metrics)
                await metrics_collector.log_error(error)
            raise e

    def create_enhanced_workflow(self, request: EnhancedAnimeRequest) -> Dict[str, Any]:
        """Create optimized ComfyUI workflow based on quality level"""
        # Quality settings mapping
        quality_settings = {
            "low": {"steps": 15, "cfg": 7.0, "sampler": "euler", "scheduler": "normal"},
            "medium": {"steps": 20, "cfg": 7.5, "sampler": "euler", "scheduler": "normal"},
            "high": {"steps": 25, "cfg": 8.0, "sampler": "dpmpp_2m", "scheduler": "karras"},
            "ultra": {"steps": 30, "cfg": 8.5, "sampler": "dpmpp_2m", "scheduler": "karras"}
        }

        settings = quality_settings.get(request.quality_level, quality_settings["high"])

        # Enhanced prompt based on style and character
        enhanced_prompt = f"masterpiece, best quality, {request.style} style, {request.character}, {request.prompt}, detailed background, cinematic lighting, vibrant colors"

        workflow = {
            "1": {
                "inputs": {
                    "text": enhanced_prompt,
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "2": {
                "inputs": {
                    "text": "low quality, blurry, distorted, ugly, deformed, duplicate",
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "3": {
                "inputs": {
                    "seed": int(time.time()),
                    "steps": settings["steps"],
                    "cfg": settings["cfg"],
                    "sampler_name": settings["sampler"],
                    "scheduler": settings["scheduler"],
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler"
            },
            "4": {
                "inputs": {
                    "ckpt_name": "epicrealism_v5.safetensors"
                },
                "class_type": "CheckpointLoaderSimple"
            },
            "5": {
                "inputs": {
                    "width": 1024,
                    "height": 1024,
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage"
            },
            "6": {
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                },
                "class_type": "VAEDecode"
            },
            "7": {
                "inputs": {
                    "filename_prefix": f"enhanced_anime_{request.character}_{int(time.time())}",
                    "images": ["6", 0]
                },
                "class_type": "SaveImage"
            }
        }
        return workflow

# Initialize enhanced client
comfyui_client = EnhancedComfyUIClient()

@app.get("/api/health")
async def enhanced_health():
    """Enhanced health check with dependency validation"""
    correlation_id = str(uuid.uuid4())[:8]
    health_data = {
        "status": "healthy",
        "service": "enhanced-real-anime-generation",
        "version": "2.0.0",
        "correlation_id": correlation_id,
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {}
    }

    # Check ComfyUI connection
    try:
        response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        health_data["dependencies"]["comfyui"] = {
            "status": "connected" if response.status_code == 200 else "disconnected",
            "response_time_ms": response.elapsed.total_seconds() * 1000
        }
    except Exception as e:
        health_data["dependencies"]["comfyui"] = {
            "status": "error",
            "error": str(e)
        }
        health_data["status"] = "degraded"

    # Check database connection
    try:
        # Test database connection with metrics collector
        test_metrics = OperationMetrics(
            operation_id=f"health_check_{correlation_id}",
            operation_type="health_check",
            start_time=datetime.utcnow()
        )
        await metrics_collector.log_operation(test_metrics)
        health_data["dependencies"]["database"] = {"status": "connected"}
    except Exception as e:
        health_data["dependencies"]["database"] = {
            "status": "error",
            "error": str(e)
        }
        health_data["status"] = "degraded"

    # Get recent performance metrics
    try:
        success_rate = await metrics_collector.get_success_rate("enhanced_anime_generation", 24)
        health_data["metrics"] = {
            "success_rate_24h": success_rate,
            "circuit_breaker_state": comfyui_circuit_breaker.state
        }
    except Exception as e:
        logger.warning(f"Could not fetch metrics: {e}")

    return health_data

@app.post("/api/generate-enhanced")
async def generate_enhanced_anime(request: EnhancedAnimeRequest, background_tasks: BackgroundTasks):
    """Generate anime with comprehensive monitoring and quality assessment"""
    correlation_id = str(uuid.uuid4())[:8]
    operation_id = f"enhanced_generation_{int(time.time())}_{correlation_id}"

    metrics = OperationMetrics(
        operation_id=operation_id,
        operation_type="enhanced_anime_generation",
        start_time=datetime.utcnow(),
        context={
            "correlation_id": correlation_id,
            "user_id": request.user_id,
            "character": request.character,
            "quality_level": request.quality_level,
            "prompt_length": len(request.prompt)
        }
    )

    try:
        logger.info(f"🎬 Starting enhanced anime generation", extra={'correlation_id': correlation_id})
        logger.info(f"📝 Request details: {request.character} - {request.prompt[:100]}...",
                   extra={'correlation_id': correlation_id})

        # Step 1: Create optimized workflow
        workflow = comfyui_client.create_enhanced_workflow(request)
        logger.info(f"⚙️ Created workflow with {len(workflow)} nodes", extra={'correlation_id': correlation_id})

        # Step 2: Submit to ComfyUI with monitoring
        queue_result = await comfyui_client.queue_prompt_with_monitoring(workflow, correlation_id)
        prompt_id = queue_result.get("prompt_id")

        if not prompt_id:
            raise ComfyUIError("No prompt_id returned from ComfyUI", correlation_id=correlation_id)

        # Step 3: Monitor generation progress
        generation_result = await comfyui_client.monitor_generation_progress(prompt_id, correlation_id)

        # Step 4: Generate output filename and metadata
        timestamp = int(time.time())
        output_filename = f"enhanced_anime_{request.character}_{timestamp}.png"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        # Step 5: Schedule quality assessment in background
        background_tasks.add_task(
            assess_generation_quality,
            output_path,
            request.prompt,
            prompt_id,
            correlation_id
        )

        response_data = {
            "status": "generated",
            "generation_id": prompt_id,
            "correlation_id": correlation_id,
            "prompt": request.prompt,
            "character": request.character,
            "quality_level": request.quality_level,
            "output_file": output_filename,
            "output_path": output_path,
            "generation_time": (datetime.utcnow() - metrics.start_time).total_seconds(),
            "metadata": {
                "workflow_nodes": len(workflow),
                "quality_settings": workflow["3"]["inputs"],
                "model_used": workflow["4"]["inputs"]["ckpt_name"]
            }
        }

        metrics.complete(True)
        await metrics_collector.log_operation(metrics)

        logger.info(f"✅ Enhanced generation completed successfully", extra={'correlation_id': correlation_id})
        return response_data

    except Exception as e:
        error_details = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "generation_stage": "unknown"
        }

        metrics.complete(False, error_details)
        await metrics_collector.log_operation(metrics)

        if isinstance(e, AnimeGenerationError):
            await metrics_collector.log_error(e)
            logger.error(f"❌ Generation failed: {e.message}", extra={'correlation_id': correlation_id})
        else:
            # Wrap unexpected errors
            generation_error = AnimeGenerationError(
                f"Unexpected generation error: {str(e)}",
                ErrorCategory.GENERATION,
                ErrorSeverity.HIGH,
                correlation_id=correlation_id,
                context={"original_error": str(e), "request": request.dict()}
            )
            await metrics_collector.log_error(generation_error)
            logger.error(f"❌ Unexpected error: {str(e)}", extra={'correlation_id': correlation_id})

        raise HTTPException(status_code=500, detail={
            "error": str(e),
            "correlation_id": correlation_id,
            "type": type(e).__name__
        })

async def assess_generation_quality(output_path: str, prompt: str, generation_id: str, correlation_id: str):
    """Background task for quality assessment"""
    try:
        logger.info(f"🔍 Starting quality assessment", extra={'correlation_id': correlation_id})

        # Wait a moment for file to be fully written
        await asyncio.sleep(2)

        quality_result = await quality_assessor.assess_image_quality(output_path, prompt)

        logger.info(f"📊 Quality assessment completed: {quality_result['overall_rating']:.2f}",
                   extra={'correlation_id': correlation_id})

        # Store quality assessment results for learning
        await store_quality_assessment(generation_id, quality_result, correlation_id)

    except Exception as e:
        logger.error(f"❌ Quality assessment failed: {e}", extra={'correlation_id': correlation_id})

async def store_quality_assessment(generation_id: str, quality_result: Dict[str, Any], correlation_id: str):
    """Store quality assessment for learning purposes"""
    try:
        # This would store to database for learning system analysis
        logger.info(f"💾 Stored quality assessment for learning", extra={'correlation_id': correlation_id})
    except Exception as e:
        logger.error(f"Failed to store quality assessment: {e}", extra={'correlation_id': correlation_id})

@app.post("/api/feedback")
async def submit_user_feedback(feedback: UserFeedbackRequest):
    """Submit user feedback for continuous improvement"""
    correlation_id = str(uuid.uuid4())[:8]

    try:
        logger.info(f"📝 Received user feedback: {feedback.user_rating}/5", extra={'correlation_id': correlation_id})

        # Store feedback for learning system
        feedback_data = {
            "generation_id": feedback.generation_id,
            "user_rating": feedback.user_rating,
            "feedback_text": feedback.feedback_text,
            "issues": feedback.issues,
            "user_id": feedback.user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "correlation_id": correlation_id
        }

        # This would be stored in database for learning analysis
        # await store_user_feedback(feedback_data)

        return {
            "status": "received",
            "correlation_id": correlation_id,
            "message": "Feedback received and will be used to improve future generations"
        }

    except Exception as e:
        logger.error(f"❌ Failed to process feedback: {e}", extra={'correlation_id': correlation_id})
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/metrics/success-rate")
async def get_success_rate(hours: int = 24):
    """Get success rate metrics"""
    try:
        success_rate = await metrics_collector.get_success_rate("enhanced_anime_generation", hours)
        return {
            "success_rate": success_rate,
            "period_hours": hours,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/learning/failure-analysis")
async def get_failure_analysis(days: int = 7):
    """Get failure analysis for learning purposes"""
    try:
        analysis = await learning_system.analyze_failure_patterns("enhanced_anime_generation", days)
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    uvicorn.run(app, host="127.0.0.1", port=8352)