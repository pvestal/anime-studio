#!/usr/bin/env python3
"""
Enhanced ComfyUI Integration with Comprehensive Error Handling
Provides robust error recovery, retry logic, circuit breakers, and graceful degradation
"""

import asyncio
import hashlib
import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import aiohttp
import psutil
# Import our error handling framework
from shared.error_handling import (AnimeGenerationError, CircuitBreaker,
                                   ComfyUIError, ErrorCategory, ErrorSeverity,
                                   MetricsCollector, OperationMetrics,
                                   ResourceExhaustionError, RetryManager)

logger = logging.getLogger(__name__)


class ComfyUIHealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    OVERLOADED = "overloaded"


@dataclass
class ComfyUIConfig:
    """Configuration for ComfyUI integration"""

    base_url: str = "http://192.168.50.135:8188"
    timeout_seconds: int = 600  # 10 minutes - reasonable for anime generation
    max_retries: int = 1  # Reduce retries to stop job spiral
    retry_delay: float = 5.0
    max_concurrent_jobs: int = 2
    health_check_interval: int = 30
    vram_threshold_gb: float = 1.0  # Minimum VRAM for new jobs
    workflow_dir: str = "/opt/tower-anime-production/workflows/comfyui"
    output_dir: str = "/mnt/1TB-storage/ComfyUI/output"
    fallback_output_dir: str = "/opt/tower-anime-production/output/fallback"


@dataclass
class GenerationRequest:
    """Structure for generation requests"""

    request_id: str
    prompt: str
    duration: int
    style: str
    priority: int = 5  # 1-10, 1 is highest
    timeout_override: Optional[int] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


class ResourceMonitor:
    """Monitors system resources for ComfyUI operations"""

    def __init__(self):
        self.gpu_available = self._check_gpu_availability()

    def _check_gpu_availability(self) -> bool:
        """Check if GPU monitoring is available"""
        try:
            import pynvml

            pynvml.nvmlInit()
            return True
        except Exception:
            return False

    async def get_vram_usage(self) -> Dict[str, float]:
        """Get current VRAM usage"""
        try:
            if not self.gpu_available:
                return {"total_gb": 0.0, "used_gb": 0.0, "free_gb": 0.0}

            import pynvml

            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)

            total_gb = info.total / (1024**3)
            used_gb = info.used / (1024**3)
            free_gb = (info.total - info.used) / (1024**3)

            return {
                "total_gb": total_gb,
                "used_gb": used_gb,
                "free_gb": free_gb,
                "utilization_percent": (used_gb / total_gb) * 100,
            }
        except Exception as e:
            logger.warning(f"Failed to get VRAM usage: {e}")
            return {
                "total_gb": 12.0,
                "used_gb": 8.0,
                "free_gb": 4.0,
            }  # Fallback estimates

    async def get_disk_usage(self, path: str) -> Dict[str, float]:
        """Get disk usage for output directory"""
        try:
            usage = shutil.disk_usage(path)
            total_gb = usage.total / (1024**3)
            used_gb = usage.used / (1024**3)
            free_gb = usage.free / (1024**3)

            return {
                "total_gb": total_gb,
                "used_gb": used_gb,
                "free_gb": free_gb,
                "utilization_percent": (used_gb / total_gb) * 100,
            }
        except Exception as e:
            logger.error(f"Failed to get disk usage for {path}: {e}")
            return {"total_gb": 1000.0, "used_gb": 500.0, "free_gb": 500.0}

    async def get_system_load(self) -> Dict[str, float]:
        """Get system CPU and memory load"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()

            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": memory.available / (1024**3),
            }
        except Exception as e:
            logger.error(f"Failed to get system load: {e}")
            return {
                "cpu_percent": 50.0,
                "memory_percent": 50.0,
                "memory_available_gb": 8.0,
            }


class WorkflowManager:
    """Manages ComfyUI workflow templates with error handling"""

    def __init__(self, config: ComfyUIConfig):
        self.config = config
        self.workflow_cache = {}

    async def load_workflow_template(
        self, duration: int, quality_preset: str = "standard"
    ) -> Dict:
        """Load and validate workflow template"""
        cache_key = f"{duration}s_{quality_preset}"

        if cache_key in self.workflow_cache:
            return self.workflow_cache[cache_key].copy()

        workflow_file = Path(self.config.workflow_dir) / \
            "anime_30sec_standard.json"

        try:
            if not workflow_file.exists():
                raise ComfyUIError(
                    f"Workflow template not found: {workflow_file}",
                    context={"workflow_file": str(
                        workflow_file), "duration": duration},
                )

            with open(workflow_file, "r") as f:
                workflow = json.load(f)

            # Validate workflow structure
            if not self._validate_workflow(workflow):
                raise ComfyUIError(
                    "Invalid workflow template structure",
                    context={"workflow_file": str(workflow_file)},
                )

            # Optimize workflow for duration and quality
            optimized_workflow = await self._optimize_workflow(
                workflow, duration, quality_preset
            )

            # Cache the optimized workflow
            self.workflow_cache[cache_key] = optimized_workflow.copy()

            return optimized_workflow

        except Exception as e:
            if isinstance(e, ComfyUIError):
                raise
            raise ComfyUIError(
                f"Failed to load workflow template: {str(e)}",
                context={
                    "workflow_file": str(workflow_file),
                    "error_type": type(e).__name__,
                },
            )

    def _validate_workflow(self, workflow: Dict) -> bool:
        """Validate workflow has required nodes"""
        required_node_types = ["EmptyLatentImage",
                               "CLIPTextEncode", "KSampler"]

        found_types = set()
        for node_id, node in workflow.items():
            if node.get("class_type"):
                found_types.add(node["class_type"])

        missing_types = set(required_node_types) - found_types
        if missing_types:
            logger.error(
                f"Workflow missing required node types: {missing_types}")
            return False

        return True

    async def _optimize_workflow(
        self, workflow: Dict, duration: int, quality_preset: str
    ) -> Dict:
        """Optimize workflow for given parameters"""
        optimized = workflow.copy()

        # Calculate frame counts based on duration - Fixed for longer videos
        # 24fps base, max 120 frames per segment
        base_frames = min(120, duration * 24)
        target_frames = duration * 24  # Final target: 24fps

        # Quality presets
        quality_settings = {
            "fast": {"steps": 15, "cfg": 7.0, "resolution_factor": 0.8},
            "standard": {"steps": 20, "cfg": 7.5, "resolution_factor": 1.0},
            "high": {"steps": 30, "cfg": 8.0, "resolution_factor": 1.0},
            "ultra": {"steps": 40, "cfg": 8.5, "resolution_factor": 1.2},
        }

        settings = quality_settings.get(
            quality_preset, quality_settings["standard"])

        # Update workflow nodes
        for node_id, node in optimized.items():
            class_type = node.get("class_type", "")

            if class_type == "EmptyLatentImage":
                node["inputs"]["batch_size"] = base_frames
                # Adjust resolution based on quality preset
                if "width" in node["inputs"]:
                    node["inputs"]["width"] = int(
                        node["inputs"]["width"] * settings["resolution_factor"]
                    )
                if "height" in node["inputs"]:
                    node["inputs"]["height"] = int(
                        node["inputs"]["height"] *
                        settings["resolution_factor"]
                    )

            elif class_type == "KSampler":
                node["inputs"]["steps"] = settings["steps"]
                node["inputs"]["cfg"] = settings["cfg"]

            elif class_type == "RIFE VFI":
                rife_multiplier = min(4, max(2, target_frames // base_frames))
                node["inputs"]["multiplier"] = rife_multiplier
                node["inputs"]["fast_mode"] = quality_preset in [
                    "fast", "standard"]

        logger.info(
            f"Optimized workflow: {base_frames} base frames, {quality_preset} quality"
        )
        return optimized


class EnhancedComfyUIIntegration:
    """Enhanced ComfyUI integration with comprehensive error handling"""

    def __init__(
        self, config: ComfyUIConfig = None, metrics_collector: MetricsCollector = None
    ):
        self.config = config or ComfyUIConfig()
        self.metrics_collector = metrics_collector
        self.resource_monitor = ResourceMonitor()
        self.workflow_manager = WorkflowManager(self.config)
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3, recovery_timeout=60)
        self.active_jobs = {}
        self.job_queue = []
        self.health_status = ComfyUIHealthStatus.HEALTHY
        self.last_health_check = None

        # Ensure output directories exist
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.fallback_output_dir).mkdir(
            parents=True, exist_ok=True)

    async def check_health(self) -> ComfyUIHealthStatus:
        """Check ComfyUI service health"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.config.base_url}/system_stats",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        # Check system resources
                        vram_info = await self.resource_monitor.get_vram_usage()
                        system_load = await self.resource_monitor.get_system_load()

                        # Determine health based on resources
                        if vram_info["free_gb"] < self.config.vram_threshold_gb:
                            self.health_status = ComfyUIHealthStatus.OVERLOADED
                        elif (
                            system_load["cpu_percent"] > 90
                            or system_load["memory_percent"] > 90
                        ):
                            self.health_status = ComfyUIHealthStatus.DEGRADED
                        else:
                            self.health_status = ComfyUIHealthStatus.HEALTHY
                    else:
                        self.health_status = ComfyUIHealthStatus.DEGRADED

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.health_status = ComfyUIHealthStatus.UNAVAILABLE

        self.last_health_check = datetime.utcnow()
        return self.health_status

    async def can_accept_job(self) -> bool:
        """Check if service can accept new jobs"""
        if len(self.active_jobs) >= self.config.max_concurrent_jobs:
            return False

        # Check health if stale
        if (
            not self.last_health_check
            or (datetime.utcnow() - self.last_health_check).seconds
            > self.config.health_check_interval
        ):
            await self.check_health()

        return self.health_status in [
            ComfyUIHealthStatus.HEALTHY,
            ComfyUIHealthStatus.DEGRADED,
        ]

    async def generate_video_robust(self, request: GenerationRequest) -> Dict[str, Any]:
        """Generate video with comprehensive error handling and recovery"""
        operation_id = f"video_generation_{request.request_id}"
        metrics = OperationMetrics(
            operation_id=operation_id,
            operation_type="video_generation",
            start_time=datetime.utcnow(),
            context={
                "request_id": request.request_id,
                "duration": request.duration,
                "style": request.style,
                "retry_count": request.retry_count,
            },
        )

        try:
            # Pre-flight checks
            await self._perform_preflight_checks(request)

            # Resource monitoring
            initial_resources = await self._capture_resource_snapshot()

            # Generate with circuit breaker protection
            result = await self.circuit_breaker.call(
                self._generate_video_internal, request, metrics
            )

            # Post-generation validation
            validated_result = await self._validate_generation_result(result, request)

            # Update metrics
            metrics.complete(True)
            if self.metrics_collector:
                await self.metrics_collector.log_operation(metrics)

            return validated_result

        except Exception as e:
            error_context = {
                "request_id": request.request_id,
                "retry_count": request.retry_count,
                "health_status": self.health_status.value,
            }

            # Determine if retry is appropriate
            should_retry = (
                request.retry_count < request.max_retries
                and self._is_retryable_error(e)
                and await self.can_accept_job()
            )

            if should_retry:
                logger.warning(
                    f"Retrying generation for {request.request_id} (attempt {request.retry_count + 1})"
                )
                request.retry_count += 1
                await asyncio.sleep(self.config.retry_delay * (2**request.retry_count))
                return await self.generate_video_robust(request)

            # Handle non-retryable or max retries exceeded
            error = self._create_appropriate_error(e, error_context)

            metrics.complete(False, error.to_dict())
            if self.metrics_collector:
                await self.metrics_collector.log_operation(metrics)
                await self.metrics_collector.log_error(error)

            # Try fallback generation
            if request.retry_count > 0:
                fallback_result = await self._attempt_fallback_generation(request)
                if fallback_result:
                    return fallback_result

            raise error

    async def _perform_preflight_checks(self, request: GenerationRequest):
        """Perform pre-generation validation checks"""
        # Check if we can accept the job
        if not await self.can_accept_job():
            raise ComfyUIError(
                f"Service overloaded: {len(self.active_jobs)} active jobs, health: {self.health_status.value}",
                context={
                    "active_jobs": len(self.active_jobs),
                    "health_status": self.health_status.value,
                },
            )

        # Check VRAM availability
        vram_info = await self.resource_monitor.get_vram_usage()
        if vram_info["free_gb"] < self.config.vram_threshold_gb:
            raise ResourceExhaustionError(
                f"Insufficient VRAM: {vram_info['free_gb']:.2f}GB available, {self.config.vram_threshold_gb}GB required",
                resource_type="vram",
                current_usage=vram_info["used_gb"],
            )

        # Check disk space
        disk_info = await self.resource_monitor.get_disk_usage(self.config.output_dir)
        if disk_info["free_gb"] < 5.0:  # Require at least 5GB free
            raise ResourceExhaustionError(
                f"Insufficient disk space: {disk_info['free_gb']:.2f}GB available",
                resource_type="disk",
                current_usage=disk_info["used_gb"],
            )

        # Validate request parameters
        if request.duration <= 0 or request.duration > 120:
            raise ComfyUIError(
                f"Invalid duration: {request.duration}s (must be 1-120)",
                context={"duration": request.duration},
            )

        if not request.prompt or len(request.prompt.strip()) == 0:
            raise ComfyUIError(
                "Empty prompt provided", context={"prompt": request.prompt}
            )

    async def _capture_resource_snapshot(self) -> Dict[str, Any]:
        """Capture current resource usage for monitoring"""
        return {
            "vram": await self.resource_monitor.get_vram_usage(),
            "disk": await self.resource_monitor.get_disk_usage(self.config.output_dir),
            "system": await self.resource_monitor.get_system_load(),
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _generate_video_internal(
        self, request: GenerationRequest, metrics: OperationMetrics
    ) -> Dict[str, Any]:
        """Internal video generation with timeout and monitoring"""
        self.active_jobs[request.request_id] = {
            "started_at": datetime.utcnow(),
            "request": request,
            "status": "preparing",
        }

        try:
            # Load and prepare workflow
            self.active_jobs[request.request_id]["status"] = "loading_workflow"
            workflow = await self.workflow_manager.load_workflow_template(
                request.duration, getattr(
                    request, "quality_preset", "standard")
            )

            # Update workflow with prompt
            self._update_workflow_prompt(workflow, request.prompt)

            # Submit to ComfyUI
            self.active_jobs[request.request_id]["status"] = "submitting"
            prompt_id = await self._submit_workflow(workflow, request)

            # Monitor generation
            self.active_jobs[request.request_id]["status"] = "generating"
            self.active_jobs[request.request_id]["prompt_id"] = prompt_id

            result_path = await self._monitor_generation(prompt_id, request)

            processing_time = (datetime.utcnow() -
                               request.created_at).total_seconds()

            return {
                "success": True,
                "request_id": request.request_id,
                "prompt_id": prompt_id,
                "output_path": result_path,
                "processing_time_seconds": round(processing_time, 2),
                "retry_count": request.retry_count,
                "video_specs": {
                    "duration_seconds": request.duration,
                    "style": request.style,
                    "frames": request.duration * 24,
                },
            }

        finally:
            # Clean up active job tracking
            if request.request_id in self.active_jobs:
                del self.active_jobs[request.request_id]

    def _update_workflow_prompt(self, workflow: Dict, prompt: str):
        """Update workflow with the generation prompt"""
        for node_id, node in workflow.items():
            if node.get("class_type") == "CLIPTextEncode":
                title = node.get("_meta", {}).get("title", "")
                if "positive" in title.lower() or "prompt" in title.lower():
                    node["inputs"]["text"] = prompt
                    break

    async def _submit_workflow(self, workflow: Dict, request: GenerationRequest) -> str:
        """Submit workflow to ComfyUI with error handling"""
        timeout = request.timeout_override or self.config.timeout_seconds

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "prompt": workflow,
                    "client_id": f"enhanced_integration_{request.request_id}",
                }

                async with session.post(
                    f"{self.config.base_url}/prompt",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        prompt_id = data.get("prompt_id")
                        if not prompt_id:
                            raise ComfyUIError(
                                "No prompt_id returned from ComfyUI")
                        return prompt_id
                    else:
                        response_text = await response.text()
                        raise ComfyUIError(
                            f"ComfyUI submission failed: {response.status}",
                            status_code=response.status,
                            response_data={"text": response_text},
                        )

        except asyncio.TimeoutError:
            raise ComfyUIError(
                "Timeout submitting workflow to ComfyUI",
                context={"timeout_seconds": 30},
            )
        except aiohttp.ClientError as e:
            raise ComfyUIError(
                f"Network error communicating with ComfyUI: {str(e)}",
                context={"error_type": type(e).__name__},
            )

    async def _monitor_generation(
        self, prompt_id: str, request: GenerationRequest
    ) -> str:
        """Monitor generation progress with timeout and error handling"""
        timeout = request.timeout_override or self.config.timeout_seconds
        check_interval = 5
        total_waited = 0
        last_progress_update = datetime.utcnow()

        while total_waited < timeout:
            try:
                async with aiohttp.ClientSession() as session:
                    # Check if generation is complete
                    async with session.get(
                        f"{self.config.base_url}/history/{prompt_id}",
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            if prompt_id in data:
                                result_path = self._extract_result_path(
                                    data[prompt_id])
                                if result_path:
                                    return result_path

                    # Check queue status for progress updates
                    async with session.get(
                        f"{self.config.base_url}/queue",
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        if response.status == 200:
                            queue_data = await response.json()
                            if self._is_job_in_queue(prompt_id, queue_data):
                                last_progress_update = datetime.utcnow()
                            elif (
                                datetime.utcnow() - last_progress_update
                            ).seconds > 300:
                                # No progress for 5 minutes, likely stuck
                                raise ComfyUIError(
                                    f"Generation appears stuck: no progress for 5 minutes",
                                    context={
                                        "prompt_id": prompt_id,
                                        "waited_seconds": total_waited,
                                    },
                                )

                await asyncio.sleep(check_interval)
                total_waited += check_interval

                # Update job status
                if request.request_id in self.active_jobs:
                    self.active_jobs[request.request_id][
                        "waited_seconds"
                    ] = total_waited

            except ComfyUIError:
                raise  # Re-raise ComfyUI specific errors
            except Exception as e:
                logger.warning(f"Error monitoring generation {prompt_id}: {e}")
                await asyncio.sleep(check_interval)
                total_waited += check_interval

        raise ComfyUIError(
            f"Generation timeout after {timeout} seconds",
            context={"prompt_id": prompt_id, "timeout_seconds": timeout},
        )

    def _extract_result_path(self, history_data: Dict) -> Optional[str]:
        """Extract result file path from ComfyUI history data"""
        outputs = history_data.get("outputs", {})
        for node_id, output in outputs.items():
            if "videos" in output and output["videos"]:
                filename = output["videos"][0]["filename"]
                return f"{self.config.output_dir}/{filename}"
            elif "images" in output and output["images"]:
                filename = output["images"][0]["filename"]
                return f"{self.config.output_dir}/{filename}"
        return None

    def _is_job_in_queue(self, prompt_id: str, queue_data: Dict) -> bool:
        """Check if job is still in ComfyUI queue"""
        for queue_type in ["queue_running", "queue_pending"]:
            if queue_type in queue_data:
                for item in queue_data[queue_type]:
                    if len(item) > 1 and item[1] == prompt_id:
                        return True
        return False

    async def _validate_generation_result(
        self, result: Dict[str, Any], request: GenerationRequest
    ) -> Dict[str, Any]:
        """Validate generation result and file integrity"""
        if not result.get("success"):
            return result

        output_path = result.get("output_path")
        if not output_path or not Path(output_path).exists():
            raise ComfyUIError(
                f"Generated file not found: {output_path}",
                context={"output_path": output_path,
                         "request_id": request.request_id},
            )

        # Check file size
        file_size = Path(output_path).stat().st_size
        if file_size < 1000:  # Less than 1KB likely indicates failure
            raise ComfyUIError(
                f"Generated file too small: {file_size} bytes",
                context={"output_path": output_path, "file_size": file_size},
            )

        # Add file validation info to result
        result["file_info"] = {
            "size_bytes": file_size,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "exists": True,
            "validated_at": datetime.utcnow().isoformat(),
        }

        return result

    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable"""
        if isinstance(error, ComfyUIError):
            # Retry network errors and timeouts, not validation errors
            return error.severity in [ErrorSeverity.MEDIUM, ErrorSeverity.HIGH]
        elif isinstance(error, ResourceExhaustionError):
            # Retry resource errors after delay
            return True
        elif isinstance(error, (asyncio.TimeoutError, aiohttp.ClientError)):
            # Retry timeout and network errors
            return True
        else:
            # Don't retry unknown errors
            return False

    def _create_appropriate_error(
        self, original_error: Exception, context: Dict[str, Any]
    ) -> AnimeGenerationError:
        """Create appropriate error type based on original error"""
        if isinstance(original_error, AnimeGenerationError):
            return original_error
        elif isinstance(original_error, asyncio.TimeoutError):
            return ComfyUIError(
                f"Generation timeout: {str(original_error)}", context=context
            )
        elif isinstance(original_error, aiohttp.ClientError):
            return ComfyUIError(
                f"Network error: {str(original_error)}", context=context
            )
        else:
            return ComfyUIError(
                f"Unexpected generation error: {str(original_error)}",
                context={**context,
                         "error_type": type(original_error).__name__},
            )

    async def _attempt_fallback_generation(
        self, request: GenerationRequest
    ) -> Optional[Dict[str, Any]]:
        """Attempt fallback generation with simpler parameters"""
        try:
            logger.info(
                f"Attempting fallback generation for {request.request_id}")

            # Create simplified request
            fallback_request = GenerationRequest(
                request_id=f"{request.request_id}_fallback",
                prompt=request.prompt,
                duration=min(request.duration, 10),  # Shorter duration
                style="simple anime",  # Simpler style
                priority=1,  # High priority
                max_retries=1,  # Single retry only
            )

            # Try with fast quality preset
            fallback_request.quality_preset = "fast"

            result = await self.generate_video_robust(fallback_request)

            # Mark as fallback result
            result["is_fallback"] = True
            result["original_request_id"] = request.request_id
            result["fallback_reason"] = "Original generation failed after retries"

            return result

        except Exception as e:
            logger.error(f"Fallback generation also failed: {e}")
            return None

    async def get_service_status(self) -> Dict[str, Any]:
        """Get comprehensive service status"""
        health_status = await self.check_health()
        resources = await self._capture_resource_snapshot()

        return {
            "health_status": health_status.value,
            "active_jobs": len(self.active_jobs),
            "max_concurrent_jobs": self.config.max_concurrent_jobs,
            "can_accept_jobs": await self.can_accept_job(),
            "circuit_breaker_state": self.circuit_breaker.state,
            "resources": resources,
            "job_details": {
                job_id: {
                    "started_at": job_info["started_at"].isoformat(),
                    "status": job_info["status"],
                    "duration": job_info["request"].duration,
                    "waited_seconds": job_info.get("waited_seconds", 0),
                }
                for job_id, job_info in self.active_jobs.items()
            },
        }


# Factory function for creating configured instances
def create_comfyui_integration(
    db_config: Dict[str, str] = None,
) -> EnhancedComfyUIIntegration:
    """Create configured ComfyUI integration instance"""
    config = ComfyUIConfig()

    metrics_collector = None
    if db_config:
        from shared.error_handling import MetricsCollector

        metrics_collector = MetricsCollector(db_config)

    return EnhancedComfyUIIntegration(config, metrics_collector)


# Example usage
async def test_enhanced_integration():
    """Test the enhanced ComfyUI integration"""
    integration = create_comfyui_integration()

    # Test health check
    status = await integration.get_service_status()
    print("Service Status:", json.dumps(status, indent=2, default=str))

    # Test generation
    request = GenerationRequest(
        request_id="test_001",
        prompt="1girl, anime style, magical transformation, sparkles",
        duration=5,
        style="anime",
    )

    try:
        result = await integration.generate_video_robust(request)
        print("Generation successful:", json.dumps(
            result, indent=2, default=str))
    except Exception as e:
        print("Generation failed:", str(e))


if __name__ == "__main__":
    asyncio.run(test_enhanced_integration())
