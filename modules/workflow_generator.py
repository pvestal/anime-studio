"""
Workflow Generator Module
Builds ComfyUI workflows for different generation types
"""
from typing import Dict, Any, Optional
import random
import logging

logger = logging.getLogger(__name__)


class WorkflowGenerator:
    """Generates ComfyUI workflows"""

    def __init__(self):
        self.default_model = "counterfeit_v3.safetensors"
        self.available_models = [
            "counterfeit_v3.safetensors",
            "AOM3A1B.safetensors",
            "anything_v5.safetensors"
        ]

    def generate_image_workflow(
        self,
        prompt: str,
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        cfg: float = 7.0,
        seed: int = None,
        model: str = None,
        negative_prompt: str = ""
    ) -> Dict[str, Any]:
        """Generate a simple image workflow"""

        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        if model is None:
            model = self.default_model

        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": model
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
                    "text": negative_prompt or "low quality, blurry, ugly",
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
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "euler",
                    "scheduler": "normal",
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
                    "filename_prefix": f"anime_gen",
                    "images": ["6", 0]
                }
            }
        }

        logger.info(f"Generated image workflow: {width}x{height}, {steps} steps")
        return workflow

    def generate_video_workflow(
        self,
        prompt: str,
        duration: int = 2,
        fps: int = 12,
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        model: str = None
    ) -> Dict[str, Any]:
        """Generate a video workflow using AnimateDiff"""

        if model is None:
            model = self.default_model

        frame_count = duration * fps

        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": model
                }
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": f"{prompt}, animated, smooth motion",
                    "clip": ["1", 1]
                }
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "static, still, no motion",
                    "clip": ["1", 1]
                }
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": frame_count
                }
            },
            "5": {
                "class_type": "ADE_AnimateDiffLoaderGen1",
                "inputs": {
                    "model_name": "mm_sd_v15_v2.ckpt",
                    "beta_schedule": "default",
                    "model": ["1", 0]
                }
            },
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": random.randint(0, 2**32 - 1),
                    "steps": steps,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["5", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0]
                }
            },
            "7": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["6", 0],
                    "vae": ["1", 2]
                }
            },
            "8": {
                "class_type": "ADE_AnimateDiffCombine",
                "inputs": {
                    "images": ["7", 0],
                    "frame_rate": fps,
                    "loop_count": 0,
                    "filename_prefix": "anime_video",
                    "format": "video/mp4",
                    "save_image": True
                }
            }
        }

        logger.info(f"Generated video workflow: {duration}s @ {fps}fps")
        return workflow

    def generate_batch_workflow(
        self,
        prompts: list,
        width: int = 512,
        height: int = 512,
        steps: int = 20
    ) -> Dict[str, Any]:
        """Generate batch of images in one workflow"""

        batch_size = len(prompts)
        combined_prompt = " BREAK ".join(prompts)

        workflow = self.generate_image_workflow(
            prompt=combined_prompt,
            width=width,
            height=height,
            steps=steps
        )

        # Modify for batch processing
        workflow["4"]["inputs"]["batch_size"] = batch_size

        logger.info(f"Generated batch workflow for {batch_size} images")
        return workflow

    def validate_workflow(self, workflow: Dict[str, Any]) -> bool:
        """Validate workflow structure"""
        try:
            # Check for required nodes
            required_nodes = ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler", "VAEDecode", "SaveImage"]
            node_types = [node.get("class_type") for node in workflow.values()]

            for required in required_nodes:
                if not any(required in node_type for node_type in node_types if node_type):
                    logger.error(f"Missing required node: {required}")
                    return False

            return True
        except Exception as e:
            logger.error(f"Workflow validation failed: {e}")
            return False