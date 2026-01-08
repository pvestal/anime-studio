#!/usr/bin/env python3
"""
Example integration of all optimization components for Tower Anime Production.

This demonstrates how to integrate:
1. OptimizedWorkflows - for speed/quality configurations
2. GPUOptimizer - for memory and resource management
3. GenerationCache - for avoiding duplicate work
4. PerformanceMonitor - for tracking and improvement

Usage: Replace the generation logic in secured_api.py with this optimized version.
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path

# Import our optimization modules
from optimized_workflows import OptimizedWorkflows
from gpu_optimization import GPUOptimizer
from generation_cache import GenerationCache
from performance_monitor import PerformanceMonitor

logger = logging.getLogger(__name__)

class OptimizedAnimeGenerator:
    """Optimized anime generator with all performance enhancements"""

    def __init__(self):
        """Initialize all optimization components"""
        self.workflows = OptimizedWorkflows()
        self.gpu_optimizer = GPUOptimizer()
        self.cache = GenerationCache()
        self.monitor = PerformanceMonitor()

        logger.info("Optimized anime generator initialized")

    async def generate_optimized(
        self,
        prompt: str,
        generation_type: str = "image",
        time_budget_seconds: int = 60,
        quality_preference: str = "balanced",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate anime content with full optimization

        Args:
            prompt: Text prompt for generation
            generation_type: "image" or "animation"
            time_budget_seconds: Maximum time to spend on generation
            quality_preference: "speed", "balanced", "quality"
            **kwargs: Additional generation parameters

        Returns:
            Generation result with performance metrics
        """

        generation_id = f"gen_{int(time.time() * 1000)}"
        start_time = time.time()

        try:
            # Step 1: Determine optimal workflow based on time budget
            workflow_mode = self._determine_workflow_mode(
                generation_type, time_budget_seconds, quality_preference
            )

            logger.info(f"Using {workflow_mode} workflow for {time_budget_seconds}s budget")

            # Step 2: Get generation parameters with optimizations
            generation_params = await self._prepare_generation_params(
                prompt, generation_type, workflow_mode, **kwargs
            )

            # Step 3: Check cache for existing results
            async with self.cache.cached_generation(prompt, generation_params) as cached:
                if cached:
                    logger.info(f"Cache hit! Returning cached result: {cached.output_path}")
                    return {
                        "success": True,
                        "generation_id": generation_id,
                        "output_path": cached.output_path,
                        "cached": True,
                        "generation_time": time.time() - start_time,
                        "quality_score": cached.quality_score,
                        "workflow_mode": workflow_mode
                    }

            # Step 4: Start performance monitoring
            self.monitor.start_monitoring(generation_id, generation_type, generation_params)

            # Step 5: Check GPU resources and optimize
            required_vram = self.gpu_optimizer.estimate_generation_vram(
                generation_params["model"],
                generation_params["width"],
                generation_params["height"],
                generation_params.get("batch_size", 1),
                generation_type
            )

            if not self.gpu_optimizer.check_vram_availability(required_vram):
                raise RuntimeError(f"Insufficient VRAM: {required_vram}MB required")

            # Step 6: Generate with GPU session management
            async with self.gpu_optimizer.gpu_session(required_vram):
                result = await self._execute_generation(
                    generation_id, prompt, generation_params, workflow_mode
                )

            # Step 7: Complete monitoring and cache result
            metric = self.monitor.complete_monitoring(
                generation_id,
                success=result["success"],
                output_path=result.get("output_path")
            )

            if result["success"] and result.get("output_path"):
                # Cache the successful result
                self.cache.cache_output(
                    prompt,
                    generation_params,
                    result["output_path"],
                    quality_score=result.get("quality_score", 7.0)
                )

            # Step 8: Add performance data to result
            result.update({
                "generation_id": generation_id,
                "workflow_mode": workflow_mode,
                "performance": {
                    "total_time": metric.total_time_seconds,
                    "vram_peak_mb": metric.vram_peak_mb,
                    "gpu_utilization": metric.gpu_utilization_percent,
                    "temperature": metric.temperature_celsius
                },
                "optimizations_used": {
                    "cached": False,
                    "gpu_optimized": True,
                    "workflow_optimized": True,
                    "vae_tiling": generation_params.get("vae_tiling", False)
                }
            })

            return result

        except Exception as e:
            # Complete monitoring even on failure
            self.monitor.complete_monitoring(generation_id, success=False)

            logger.error(f"Generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "generation_id": generation_id,
                "generation_time": time.time() - start_time
            }

    def _determine_workflow_mode(
        self,
        generation_type: str,
        time_budget: int,
        quality_preference: str
    ) -> str:
        """Determine optimal workflow mode based on constraints"""

        # Get recommendation from workflows module
        base_recommendation = self.workflows.recommend_workflow(
            generation_type, time_budget, quality_preference
        )

        # Override based on quality preference
        if quality_preference == "speed":
            return "draft"
        elif quality_preference == "quality":
            return "high_quality"
        else:
            return base_recommendation

    async def _prepare_generation_params(
        self,
        prompt: str,
        generation_type: str,
        workflow_mode: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Prepare optimized generation parameters"""

        # Get GPU optimization config for the workflow mode
        gpu_config = self.gpu_optimizer.get_performance_config(workflow_mode)

        # Start with GPU-optimized config
        params = {
            "prompt": prompt,
            "model": gpu_config["model_recommendation"],
            "steps": gpu_config["steps"],
            "cfg": gpu_config["cfg_scale"],
            "sampler": gpu_config["sampler"],
            "scheduler": gpu_config["scheduler"],
            "width": kwargs.get("width", gpu_config["max_resolution"]),
            "height": kwargs.get("height", gpu_config["max_resolution"]),
            "batch_size": gpu_config["batch_size"],
            "optimization_level": workflow_mode
        }

        # Override with user-provided kwargs
        params.update({k: v for k, v in kwargs.items() if k not in ["prompt"]})

        # Ensure resolution doesn't exceed GPU limits
        max_res = gpu_config["max_resolution"]
        params["width"] = min(params["width"], max_res)
        params["height"] = min(params["height"], max_res)

        # Add VAE tiling if needed
        vae_config = self.gpu_optimizer.get_vae_tiling_config(
            params["width"], params["height"]
        )
        params.update(vae_config)

        # Add negative prompt if not provided
        if "negative_prompt" not in params:
            if workflow_mode == "draft":
                params["negative_prompt"] = "low quality, blurry"
            elif workflow_mode == "high_quality":
                params["negative_prompt"] = "low quality, bad anatomy, blurry, jpeg artifacts"
            else:
                params["negative_prompt"] = "low quality, bad anatomy, blurry"

        # Animation-specific parameters
        if generation_type == "animation":
            params.update({
                "frames": kwargs.get("frames", 16 if workflow_mode == "standard" else 8),
                "fps": kwargs.get("fps", 8),
            })

        return params

    async def _execute_generation(
        self,
        generation_id: str,
        prompt: str,
        params: Dict[str, Any],
        workflow_mode: str
    ) -> Dict[str, Any]:
        """Execute the actual generation with ComfyUI"""

        try:
            # Get the appropriate workflow
            if params.get("frames"):  # Animation
                workflow = self.workflows.get_optimized_animation_workflow(
                    prompt=params["prompt"],
                    negative_prompt=params["negative_prompt"],
                    width=params["width"],
                    height=params["height"],
                    frames=params["frames"],
                    fps=params.get("fps", 8),
                    seed=params.get("seed", -1),
                    filename_prefix=f"optimized_{generation_id}",
                    quality_mode=workflow_mode
                )
            else:  # Image
                if workflow_mode == "draft":
                    workflow = self.workflows.get_draft_workflow(
                        prompt=params["prompt"],
                        negative_prompt=params["negative_prompt"],
                        width=params["width"],
                        height=params["height"],
                        seed=params.get("seed", -1),
                        filename_prefix=f"draft_{generation_id}"
                    )
                elif workflow_mode == "high_quality":
                    workflow = self.workflows.get_high_quality_workflow(
                        prompt=params["prompt"],
                        negative_prompt=params["negative_prompt"],
                        width=params["width"],
                        height=params["height"],
                        seed=params.get("seed", -1),
                        filename_prefix=f"hq_{generation_id}",
                        use_xl=params["width"] > 768 or params["height"] > 768
                    )
                else:  # standard
                    workflow = self.workflows.get_standard_workflow(
                        prompt=params["prompt"],
                        negative_prompt=params["negative_prompt"],
                        width=params["width"],
                        height=params["height"],
                        seed=params.get("seed", -1),
                        filename_prefix=f"std_{generation_id}"
                    )

            # Submit to ComfyUI
            import httpx
            async with httpx.AsyncClient(timeout=300) as client:

                # Update monitoring - queue phase
                self.monitor.update_monitoring(generation_id, "queue_complete")

                response = await client.post(
                    "http://localhost:8188/prompt",
                    json={"prompt": workflow, "client_id": generation_id}
                )

                if response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"ComfyUI error: {response.text}"
                    }

                prompt_id = response.json()["prompt_id"]

                # Update monitoring - generation phase
                self.monitor.update_monitoring(generation_id, "generation_complete")

                # Wait for completion with progress updates
                output_path = await self._wait_for_completion(
                    prompt_id, generation_id, timeout=300
                )

                if output_path:
                    # Update monitoring - VAE decode phase
                    self.monitor.update_monitoring(
                        generation_id, "vae_decode_complete",
                        {"output_file_size_mb": self._get_file_size_mb(output_path)}
                    )

                    return {
                        "success": True,
                        "prompt_id": prompt_id,
                        "output_path": output_path,
                        "quality_score": 7.0,  # Would be calculated by quality assessment
                        "workflow_used": workflow_mode
                    }
                else:
                    return {
                        "success": False,
                        "error": "Generation timed out or failed"
                    }

        except Exception as e:
            logger.error(f"Generation execution failed: {e}")
            return {
                "success": False,
                "error": f"Execution error: {str(e)}"
            }

    async def _wait_for_completion(
        self,
        prompt_id: str,
        generation_id: str,
        timeout: int = 300
    ) -> Optional[str]:
        """Wait for ComfyUI generation to complete"""

        import httpx

        start_time = time.time()

        async with httpx.AsyncClient() as client:
            while time.time() - start_time < timeout:
                try:
                    # Check ComfyUI history
                    response = await client.get(f"http://localhost:8188/history/{prompt_id}")

                    if response.status_code == 200:
                        history = response.json()

                        if prompt_id in history:
                            outputs = history[prompt_id].get("outputs", {})

                            for node_id, output in outputs.items():
                                # Check for images
                                if "images" in output:
                                    filename = output["images"][0]["filename"]
                                    full_path = f"/mnt/1TB-storage/ComfyUI/output/{filename}"
                                    if Path(full_path).exists():
                                        return full_path

                                # Check for videos (animations)
                                if "videos" in output or "gifs" in output:
                                    video_key = "videos" if "videos" in output else "gifs"
                                    filename = output[video_key][0]["filename"]
                                    full_path = f"/mnt/1TB-storage/ComfyUI/output/{filename}"
                                    if Path(full_path).exists():
                                        return full_path

                    await asyncio.sleep(2)  # Check every 2 seconds

                except Exception as e:
                    logger.error(f"Error checking completion: {e}")
                    await asyncio.sleep(2)

        return None

    def _get_file_size_mb(self, file_path: str) -> float:
        """Get file size in MB"""
        try:
            size_bytes = Path(file_path).stat().st_size
            return size_bytes / (1024 * 1024)
        except:
            return 0.0

    def get_optimization_status(self) -> Dict[str, Any]:
        """Get current optimization system status"""

        gpu_stats = self.gpu_optimizer.get_gpu_stats()
        cache_stats = self.cache.get_cache_stats()

        return {
            "gpu": {
                "vram_free_mb": gpu_stats.free_mb,
                "vram_used_mb": gpu_stats.used_mb,
                "utilization_percent": gpu_stats.utilization_percent,
                "temperature_celsius": gpu_stats.temperature
            },
            "cache": cache_stats,
            "workflows": {
                "available_modes": ["draft", "standard", "high_quality"],
                "fast_models": list(self.workflows.FAST_MODELS.keys()),
                "quality_models": list(self.workflows.QUALITY_MODELS.keys())
            },
            "monitoring": {
                "database_path": str(self.monitor.db_path),
                "active_monitoring": len(self.monitor.current_metrics)
            }
        }

    async def cleanup_optimization_system(self):
        """Cleanup optimization system resources"""

        # Clear expired cache entries
        self.cache.clear_expired_entries()

        # Force GPU memory cleanup
        await self.gpu_optimizer._cleanup_gpu_memory()

        logger.info("Optimization system cleanup completed")


# Factory function for easy integration
def get_optimized_generator() -> OptimizedAnimeGenerator:
    """Get configured optimized anime generator"""
    return OptimizedAnimeGenerator()


# Example usage for integration into secured_api.py
async def optimized_generate_endpoint(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Example endpoint function that can replace the existing generation logic

    This shows how to integrate the optimizer into the existing API
    """

    generator = get_optimized_generator()

    # Extract request parameters
    prompt = request_data.get("prompt", "anime character")
    generation_type = request_data.get("type", "image")
    quality = request_data.get("quality", "balanced")  # "speed", "balanced", "quality"
    time_budget = request_data.get("time_budget", 60)  # seconds

    # Optional parameters
    kwargs = {
        k: v for k, v in request_data.items()
        if k in ["width", "height", "seed", "negative_prompt", "frames", "fps"]
    }

    # Generate with optimization
    result = await generator.generate_optimized(
        prompt=prompt,
        generation_type=generation_type,
        time_budget_seconds=time_budget,
        quality_preference=quality,
        **kwargs
    )

    return result


if __name__ == "__main__":
    async def test_optimized_generation():
        """Test the optimized generation system"""

        generator = get_optimized_generator()

        # Test different workflow modes
        test_cases = [
            {
                "prompt": "anime girl with blue hair, high quality",
                "time_budget_seconds": 30,
                "quality_preference": "speed"
            },
            {
                "prompt": "anime warrior with sword, detailed",
                "time_budget_seconds": 60,
                "quality_preference": "balanced",
                "width": 768,
                "height": 768
            },
            {
                "prompt": "anime character portrait, masterpiece",
                "time_budget_seconds": 120,
                "quality_preference": "quality",
                "width": 1024,
                "height": 1024
            }
        ]

        for i, test_case in enumerate(test_cases):
            print(f"\n=== Test Case {i+1} ===")
            print(f"Budget: {test_case['time_budget_seconds']}s, Quality: {test_case['quality_preference']}")

            result = await generator.generate_optimized(**test_case)

            if result["success"]:
                perf = result.get("performance", {})
                print(f"✓ Generated in {perf.get('total_time', 0):.1f}s")
                print(f"  VRAM peak: {perf.get('vram_peak_mb', 0)}MB")
                print(f"  GPU usage: {perf.get('gpu_utilization', 0):.1f}%")
                print(f"  Workflow: {result['workflow_mode']}")
                print(f"  Output: {result.get('output_path', 'Unknown')}")
            else:
                print(f"✗ Failed: {result.get('error', 'Unknown error')}")

        # Print system status
        print(f"\n=== Optimization Status ===")
        status = generator.get_optimization_status()
        print(f"GPU VRAM: {status['gpu']['vram_used_mb']}/{status['gpu']['vram_used_mb'] + status['gpu']['vram_free_mb']}MB")
        print(f"Cache: {status['cache']['models']['count']} models, {status['cache']['outputs']['count']} outputs")

        # Generate performance report
        report = generator.monitor.get_performance_report(hours=1)
        print(f"Performance: {report.total_generations} generations, avg {report.avg_generation_time:.1f}s")

    # Run test
    asyncio.run(test_optimized_generation())