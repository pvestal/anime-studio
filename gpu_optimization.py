#!/usr/bin/env python3
"""
GPU optimization configuration for Tower Anime Production.

Key optimizations:
- Model loading optimization (keep models in VRAM)
- Batch processing capabilities
- Resolution scaling strategies
- VAE tiling for memory efficiency
- Memory management and monitoring
"""

import json
import time
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

@dataclass
class GPUStats:
    """GPU memory and utilization statistics"""
    free_mb: int
    used_mb: int
    total_mb: int
    utilization_percent: int
    temperature: int = 0

@dataclass
class ModelInfo:
    """Information about a loaded model"""
    name: str
    vram_usage_mb: int
    load_time_seconds: float
    last_used: float
    is_cached: bool = False

class GPUOptimizer:
    """GPU optimization and memory management"""

    def __init__(self, target_vram_usage_mb: int = 10000):
        """
        Initialize GPU optimizer

        Args:
            target_vram_usage_mb: Target maximum VRAM usage (default: 10GB for RTX 3060)
        """
        self.target_vram_mb = target_vram_usage_mb
        self.loaded_models: Dict[str, ModelInfo] = {}
        self.model_cache_path = "/tmp/comfyui_model_cache.json"
        self.vae_tiling_enabled = True
        self.batch_size_limits = {
            "image": 4,      # Max 4 images at once
            "animation": 1   # Max 1 animation at once
        }

        # Load model cache
        self._load_model_cache()

    def get_gpu_stats(self) -> GPUStats:
        """Get current GPU statistics"""
        try:
            result = subprocess.run([
                'nvidia-smi',
                '--query-gpu=memory.free,memory.used,memory.total,utilization.gpu,temperature.gpu',
                '--format=csv,nounits,noheader'
            ], capture_output=True, text=True, check=True)

            values = result.stdout.strip().split(',')
            return GPUStats(
                free_mb=int(values[0]),
                used_mb=int(values[1]),
                total_mb=int(values[2]),
                utilization_percent=int(values[3]),
                temperature=int(values[4])
            )
        except Exception as e:
            logger.error(f"Failed to get GPU stats: {e}")
            return GPUStats(0, 0, 12288, 0, 0)  # Default for RTX 3060

    def _load_model_cache(self):
        """Load model cache from disk"""
        try:
            if Path(self.model_cache_path).exists():
                with open(self.model_cache_path, 'r') as f:
                    cache_data = json.load(f)
                    self.loaded_models = {
                        name: ModelInfo(**info) for name, info in cache_data.items()
                    }
        except Exception as e:
            logger.error(f"Failed to load model cache: {e}")

    def _save_model_cache(self):
        """Save model cache to disk"""
        try:
            cache_data = {
                name: {
                    'name': info.name,
                    'vram_usage_mb': info.vram_usage_mb,
                    'load_time_seconds': info.load_time_seconds,
                    'last_used': info.last_used,
                    'is_cached': info.is_cached
                }
                for name, info in self.loaded_models.items()
            }
            with open(self.model_cache_path, 'w') as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.error(f"Failed to save model cache: {e}")

    def check_vram_availability(self, required_mb: int) -> bool:
        """Check if sufficient VRAM is available"""
        stats = self.get_gpu_stats()
        available_mb = stats.free_mb

        # Conservative estimate - keep 1GB free for other processes
        safety_margin_mb = 1000
        usable_vram = available_mb - safety_margin_mb

        logger.info(f"VRAM check: {required_mb}MB required, {usable_vram}MB available")
        return usable_vram >= required_mb

    def estimate_generation_vram(
        self,
        model_name: str,
        width: int,
        height: int,
        batch_size: int = 1,
        generation_type: str = "image"
    ) -> int:
        """
        Estimate VRAM requirements for generation

        Returns:
            Estimated VRAM usage in MB
        """

        # Base model VRAM usage
        base_vram = {
            "counterfeit_v3.safetensors": 2800,
            "realisticVision_v51.safetensors": 2900,
            "deliberate_v2.safetensors": 2700,
            "AOM3A1B.safetensors": 2600,
            "juggernautXL_v9.safetensors": 4200,
            "sd_xl_base_1.0.safetensors": 4500
        }.get(model_name, 3000)  # Default 3GB

        # Resolution factor (latent space is width*height*4*4 bytes)
        resolution_factor = (width * height) / (512 * 512)
        resolution_vram = int(500 * resolution_factor)  # ~500MB for 512x512

        # Batch size factor
        batch_vram = resolution_vram * batch_size

        # Animation overhead
        animation_overhead = 0
        if generation_type == "animation":
            animation_overhead = 1500  # AnimateDiff overhead

        total_vram = base_vram + batch_vram + animation_overhead

        logger.info(f"VRAM estimate for {model_name} at {width}x{height} batch={batch_size}: {total_vram}MB")
        return total_vram

    def get_optimal_batch_size(
        self,
        model_name: str,
        width: int,
        height: int,
        generation_type: str = "image",
        max_batch: int = 4
    ) -> int:
        """
        Calculate optimal batch size for available VRAM

        Returns:
            Recommended batch size (1-max_batch)
        """

        stats = self.get_gpu_stats()
        available_vram = stats.free_mb - 1000  # Safety margin

        for batch_size in range(max_batch, 0, -1):
            required_vram = self.estimate_generation_vram(
                model_name, width, height, batch_size, generation_type
            )

            if required_vram <= available_vram:
                logger.info(f"Optimal batch size: {batch_size} (requires {required_vram}MB)")
                return batch_size

        return 1  # Fallback to single image

    def get_resolution_recommendations(
        self,
        target_vram_mb: int,
        model_name: str,
        aspect_ratio: float = 1.0
    ) -> List[Tuple[int, int]]:
        """
        Get recommended resolutions that fit in target VRAM

        Returns:
            List of (width, height) tuples sorted by size
        """

        # Common resolutions
        resolutions = [
            (512, 512),
            (768, 768),
            (512, 768),   # Portrait
            (768, 512),   # Landscape
            (1024, 1024),
            (1024, 768),
            (768, 1024),
            (1280, 720),  # HD
            (1920, 1080)  # Full HD
        ]

        valid_resolutions = []
        for width, height in resolutions:
            vram_needed = self.estimate_generation_vram(model_name, width, height)
            if vram_needed <= target_vram_mb:
                valid_resolutions.append((width, height))

        # Sort by total pixels
        valid_resolutions.sort(key=lambda x: x[0] * x[1])

        logger.info(f"Valid resolutions for {target_vram_mb}MB VRAM: {valid_resolutions}")
        return valid_resolutions

    def enable_vae_tiling(self, enable: bool = True):
        """Enable/disable VAE tiling for memory efficiency"""
        self.vae_tiling_enabled = enable
        logger.info(f"VAE tiling {'enabled' if enable else 'disabled'}")

    def get_vae_tiling_config(self, width: int, height: int) -> Dict[str, Any]:
        """
        Get VAE tiling configuration for large images

        VAE tiling processes images in smaller chunks to save VRAM
        """

        if not self.vae_tiling_enabled:
            return {}

        # Enable tiling for images larger than 768x768
        if width > 768 or height > 768:
            tile_size = 512
            return {
                "vae_encode_tiled": True,
                "vae_decode_tiled": True,
                "tile_size": tile_size,
                "overlap": 64
            }

        return {}

    def get_memory_optimization_config(self) -> Dict[str, Any]:
        """Get memory optimization configuration for ComfyUI"""

        stats = self.get_gpu_stats()

        # Adjust based on available VRAM
        if stats.total_mb >= 12000:  # RTX 3060 or better
            return {
                "force_fp16": False,  # Can use full precision
                "model_memory_save": False,
                "free_memory_after_generation": True,
                "cpu_offloading": False
            }
        elif stats.total_mb >= 8000:  # RTX 3070 level
            return {
                "force_fp16": True,
                "model_memory_save": True,
                "free_memory_after_generation": True,
                "cpu_offloading": False
            }
        else:  # Lower VRAM cards
            return {
                "force_fp16": True,
                "model_memory_save": True,
                "free_memory_after_generation": True,
                "cpu_offloading": True
            }

    @asynccontextmanager
    async def gpu_session(self, required_vram_mb: int):
        """
        Context manager for GPU sessions with memory cleanup

        Usage:
            async with gpu_optimizer.gpu_session(required_vram_mb=5000):
                # Perform generation
                result = await generate_image(...)
        """

        # Check if enough VRAM is available
        if not self.check_vram_availability(required_vram_mb):
            stats = self.get_gpu_stats()
            raise RuntimeError(
                f"Insufficient VRAM: {required_vram_mb}MB required, "
                f"only {stats.free_mb}MB available"
            )

        start_time = time.time()
        initial_stats = self.get_gpu_stats()

        try:
            logger.info(f"Starting GPU session, VRAM usage: {initial_stats.used_mb}MB")
            yield
        finally:
            # Force cleanup
            await self._cleanup_gpu_memory()

            final_stats = self.get_gpu_stats()
            session_time = time.time() - start_time

            logger.info(
                f"GPU session completed in {session_time:.1f}s, "
                f"VRAM: {initial_stats.used_mb}MB -> {final_stats.used_mb}MB"
            )

    async def _cleanup_gpu_memory(self):
        """Force GPU memory cleanup"""
        try:
            # Call ComfyUI's free memory endpoint if available
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post("http://localhost:8188/free")
                logger.info("GPU memory cleanup requested")
        except Exception as e:
            logger.warning(f"Failed to cleanup GPU memory: {e}")

    def get_performance_config(self, quality_mode: str = "standard") -> Dict[str, Any]:
        """
        Get performance configuration based on quality mode

        Args:
            quality_mode: "draft", "standard", or "high_quality"

        Returns:
            Configuration dictionary with optimized settings
        """

        base_config = self.get_memory_optimization_config()

        if quality_mode == "draft":
            # Maximum speed configuration
            config = {
                **base_config,
                "steps": 8,
                "sampler": "dpm_fast",
                "scheduler": "simple",
                "cfg_scale": 5.0,
                "max_resolution": 512,
                "batch_size": self.get_optimal_batch_size("AOM3A1B.safetensors", 512, 512),
                "model_recommendation": "AOM3A1B.safetensors"
            }
        elif quality_mode == "standard":
            # Balanced configuration
            config = {
                **base_config,
                "steps": 15,
                "sampler": "dpmpp_2m",
                "scheduler": "karras",
                "cfg_scale": 6.5,
                "max_resolution": 768,
                "batch_size": self.get_optimal_batch_size("counterfeit_v3.safetensors", 768, 768),
                "model_recommendation": "counterfeit_v3.safetensors"
            }
        else:  # high_quality
            # Quality-focused configuration
            config = {
                **base_config,
                "steps": 25,
                "sampler": "dpmpp_2m_sde",
                "scheduler": "karras",
                "cfg_scale": 7.5,
                "max_resolution": 1024,
                "batch_size": 1,  # Single image for quality
                "model_recommendation": "realisticVision_v51.safetensors"
            }

        # Add VAE tiling config
        vae_config = self.get_vae_tiling_config(
            config["max_resolution"], config["max_resolution"]
        )
        config.update(vae_config)

        return config

    def log_performance_metrics(self, generation_start_time: float,
                               generation_type: str, config_used: Dict):
        """Log performance metrics for analysis"""

        generation_time = time.time() - generation_start_time
        stats = self.get_gpu_stats()

        metrics = {
            "timestamp": time.time(),
            "generation_time_seconds": generation_time,
            "generation_type": generation_type,
            "vram_used_mb": stats.used_mb,
            "gpu_utilization": stats.utilization_percent,
            "temperature": stats.temperature,
            "config": config_used
        }

        # Log to file for analysis
        metrics_file = "/opt/tower-anime-production/logs/gpu_performance.jsonl"
        try:
            Path(metrics_file).parent.mkdir(exist_ok=True)
            with open(metrics_file, 'a') as f:
                f.write(json.dumps(metrics) + '\n')
        except Exception as e:
            logger.error(f"Failed to log metrics: {e}")

        logger.info(
            f"Generation completed: {generation_time:.1f}s, "
            f"VRAM: {stats.used_mb}MB, GPU: {stats.utilization_percent}%"
        )


# Factory function for easy integration
def get_gpu_optimizer() -> GPUOptimizer:
    """Get configured GPU optimizer instance"""
    return GPUOptimizer(target_vram_usage_mb=10000)  # RTX 3060 has 12GB


# Example usage
if __name__ == "__main__":
    async def test_gpu_optimizer():
        optimizer = get_gpu_optimizer()

        # Check current GPU state
        stats = optimizer.get_gpu_stats()
        print(f"GPU Stats: {stats}")

        # Get performance config for different modes
        for mode in ["draft", "standard", "high_quality"]:
            config = optimizer.get_performance_config(mode)
            print(f"{mode} config: {json.dumps(config, indent=2)}")

        # Test VRAM estimation
        vram_needed = optimizer.estimate_generation_vram(
            "counterfeit_v3.safetensors", 768, 768, 1, "image"
        )
        print(f"Estimated VRAM for 768x768 image: {vram_needed}MB")

    asyncio.run(test_gpu_optimizer())