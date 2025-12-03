"""
ComfyUI workflow definitions.
Extracted from main.py to reduce file size.
"""

import time


def get_simple_image_workflow(prompt: str, negative_prompt: str = None, seed: int = None) -> dict:
    """Get a simple image generation workflow."""

    if not negative_prompt:
        negative_prompt = "bad quality, deformed, ugly, multiple people"

    if not seed:
        seed = int(time.time() * 1000) % 2147483647

    return {
        "3": {
            "inputs": {
                "seed": seed,
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler"
        },
        "4": {
            "inputs": {
                "ckpt_name": "Counterfeit-V2.5.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "5": {
            "inputs": {
                "width": 512,
                "height": 768,
                "batch_size": 1
            },
            "class_type": "EmptyLatentImage"
        },
        "6": {
            "inputs": {
                "text": prompt,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "7": {
            "inputs": {
                "text": negative_prompt,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "8": {
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            },
            "class_type": "VAEDecode"
        },
        "9": {
            "inputs": {
                "filename_prefix": f"anime_{int(time.time())}",
                "images": ["8", 0]
            },
            "class_type": "SaveImage"
        }
    }


def get_video_workflow(prompt: str, frames: int = 16) -> dict:
    """Get a video generation workflow using AnimateDiff."""

    return {
        # Simplified video workflow
        # Would contain AnimateDiff nodes
        # Keeping it simple for modularity
        "type": "video",
        "prompt": prompt,
        "frames": frames
    }