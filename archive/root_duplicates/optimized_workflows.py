#!/usr/bin/env python3
"""
Optimized ComfyUI workflows for different speed/quality targets.

Key optimizations:
- Draft mode: 8-12 steps, optimized sampler, lower CFG (target: <30 seconds)
- Standard mode: 15-20 steps, balanced quality (target: <1 minute)
- High quality mode: 25-30 steps, maximum quality (target: <2 minutes)
"""

import time
from typing import Dict, Any, Optional

class OptimizedWorkflows:
    """Optimized workflow configurations for different speed/quality requirements"""

    # Fast models that load quickly and require less VRAM
    FAST_MODELS = {
        "counterfeit_v3.safetensors": {"vram_mb": 2800, "load_time": 8},
        "realisticVision_v51.safetensors": {"vram_mb": 2900, "load_time": 10},
        "deliberate_v2.safetensors": {"vram_mb": 2700, "load_time": 7},
        "AOM3A1B.safetensors": {"vram_mb": 2600, "load_time": 6}
    }

    # High quality models (slower loading, more VRAM)
    QUALITY_MODELS = {
        "juggernautXL_v9.safetensors": {"vram_mb": 4200, "load_time": 18},
        "sd_xl_base_1.0.safetensors": {"vram_mb": 4500, "load_time": 22}
    }

    @staticmethod
    def get_draft_workflow(
        prompt: str,
        negative_prompt: str = "low quality, blurry",
        width: int = 512,
        height: int = 512,
        seed: int = -1,
        filename_prefix: str = "draft"
    ) -> Dict[str, Any]:
        """
        Draft mode workflow - optimized for speed (<30 seconds target)

        Optimizations:
        - 8 steps (vs 20)
        - Fast sampler (dpm_fast)
        - Lower CFG (5.0 vs 7.0)
        - Smaller resolution
        - Fast model
        """

        if seed < 0:
            seed = int(time.time() * 1000) % 2147483647

        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "AOM3A1B.safetensors"  # Fast loading anime model
                }
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["1", 1]
                }
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative_prompt,
                    "clip": ["1", 1]
                }
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1
                }
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 8,  # Very low steps for speed
                    "cfg": 5.0,  # Lower CFG for faster convergence
                    "sampler_name": "dpm_fast",  # Fastest sampler
                    "scheduler": "simple",  # Simple scheduler
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0]
                }
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["5", 0],
                    "vae": ["1", 2]
                }
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": filename_prefix,
                    "images": ["6", 0]
                }
            }
        }

    @staticmethod
    def get_standard_workflow(
        prompt: str,
        negative_prompt: str = "low quality, bad anatomy, blurry",
        width: int = 768,
        height: int = 768,
        seed: int = -1,
        filename_prefix: str = "standard"
    ) -> Dict[str, Any]:
        """
        Standard mode workflow - balanced speed/quality (<1 minute target)

        Optimizations:
        - 15 steps (vs 20)
        - Optimized sampler (dpmpp_2m)
        - Balanced CFG (6.5)
        - Moderate resolution
        """

        if seed < 0:
            seed = int(time.time() * 1000) % 2147483647

        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "counterfeit_v3.safetensors"  # Good balance of quality/speed
                }
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["1", 1]
                }
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative_prompt,
                    "clip": ["1", 1]
                }
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1
                }
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 15,  # Reduced from 20
                    "cfg": 6.5,  # Slightly lower CFG
                    "sampler_name": "dpmpp_2m",  # Efficient sampler
                    "scheduler": "karras",  # Good quality scheduler
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0]
                }
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["5", 0],
                    "vae": ["1", 2]
                }
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": filename_prefix,
                    "images": ["6", 0]
                }
            }
        }

    @staticmethod
    def get_high_quality_workflow(
        prompt: str,
        negative_prompt: str = "low quality, bad anatomy, blurry, jpeg artifacts",
        width: int = 1024,
        height: int = 1024,
        seed: int = -1,
        filename_prefix: str = "hq",
        use_xl: bool = False
    ) -> Dict[str, Any]:
        """
        High quality mode workflow - maximum quality (<2 minutes target)

        Features:
        - 25-30 steps
        - High quality sampler
        - Higher CFG for detail
        - Option for SDXL models
        """

        if seed < 0:
            seed = int(time.time() * 1000) % 2147483647

        model_name = "juggernautXL_v9.safetensors" if use_xl else "realisticVision_v51.safetensors"
        steps = 30 if use_xl else 25

        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": model_name
                }
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["1", 1]
                }
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative_prompt,
                    "clip": ["1", 1]
                }
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1
                }
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": steps,  # Higher step count
                    "cfg": 7.5,  # Higher CFG for more detail
                    "sampler_name": "dpmpp_2m_sde",  # High quality sampler
                    "scheduler": "karras",  # Quality scheduler
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0]
                }
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["5", 0],
                    "vae": ["1", 2]
                }
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": filename_prefix,
                    "images": ["6", 0]
                }
            }
        }

    @staticmethod
    def get_optimized_animation_workflow(
        prompt: str,
        negative_prompt: str = "worst quality, low quality, blurry, static",
        width: int = 512,
        height: int = 512,
        frames: int = 16,
        fps: int = 8,
        seed: int = -1,
        filename_prefix: str = "anim",
        quality_mode: str = "standard"
    ) -> Dict[str, Any]:
        """
        Optimized animation workflow with quality modes

        Quality modes:
        - draft: 8 steps, 512x512, 8 frames
        - standard: 12 steps, 512x512, 16 frames
        - high: 20 steps, 768x768, 24 frames
        """

        if seed < 0:
            seed = int(time.time() * 1000) % 2147483647

        # Adjust parameters based on quality mode
        if quality_mode == "draft":
            steps = 8
            width = min(width, 512)
            height = min(height, 512)
            frames = min(frames, 8)
            sampler = "dpm_fast"
            cfg = 6.0
        elif quality_mode == "standard":
            steps = 12
            width = min(width, 512)
            height = min(height, 512)
            frames = min(frames, 16)
            sampler = "dpmpp_2m"
            cfg = 7.0
        else:  # high quality
            steps = 20
            sampler = "dpmpp_2m_sde"
            cfg = 8.0

        return {
            "1": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["4", 1]
                }
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative_prompt,
                    "clip": ["4", 1]
                }
            },
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": sampler,
                    "scheduler": "karras",
                    "denoise": 1.0,
                    "model": ["12", 0],  # AnimateDiff-wrapped model
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                    "latent_image": ["5", 0]
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "counterfeit_v3.safetensors"  # Fast anime model
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": frames
                }
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                }
            },
            "7": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["6", 0],
                    "frame_rate": fps,
                    "loop_count": 0,
                    "filename_prefix": filename_prefix,
                    "format": "video/h264-mp4",
                    "pix_fmt": "yuv420p",
                    "crf": 23,  # Slightly higher CRF for smaller files
                    "save_metadata": False,  # Skip metadata to save time
                    "pingpong": False,
                    "save_output": True
                }
            },
            "10": {
                "class_type": "ADE_LoadAnimateDiffModel",
                "inputs": {
                    "model_name": "mm-Stabilized_mid.pth"  # Mid-quality for balance
                }
            },
            "11": {
                "class_type": "ADE_ApplyAnimateDiffModelSimple",
                "inputs": {
                    "motion_model": ["10", 0]
                }
            },
            "12": {
                "class_type": "ADE_UseEvolvedSampling",
                "inputs": {
                    "model": ["4", 0],
                    "beta_schedule": "autoselect",
                    "m_models": ["11", 0]
                }
            }
        }

    @staticmethod
    def recommend_workflow(
        generation_type: str,
        time_budget_seconds: int,
        quality_preference: str = "balanced"
    ) -> str:
        """
        Recommend optimal workflow based on time budget and quality preference

        Args:
            generation_type: "image" or "animation"
            time_budget_seconds: Target generation time
            quality_preference: "speed", "balanced", "quality"

        Returns:
            Recommended workflow name
        """

        if generation_type == "image":
            if time_budget_seconds <= 30:
                return "draft"
            elif time_budget_seconds <= 60:
                return "standard"
            else:
                return "high_quality"

        else:  # animation
            if time_budget_seconds <= 60:
                return "animation_draft"
            elif time_budget_seconds <= 120:
                return "animation_standard"
            else:
                return "animation_high_quality"


# Example usage and testing
if __name__ == "__main__":
    workflows = OptimizedWorkflows()

    # Test workflow generation
    draft = workflows.get_draft_workflow(
        "anime girl with blue hair",
        width=512,
        height=512
    )

    print(f"Draft workflow steps: {draft['5']['inputs']['steps']}")
    print(f"Draft workflow sampler: {draft['5']['inputs']['sampler_name']}")
    print(f"Draft workflow CFG: {draft['5']['inputs']['cfg']}")

    # Test recommendations
    rec = workflows.recommend_workflow("image", 45, "speed")
    print(f"Recommendation for 45s image: {rec}")