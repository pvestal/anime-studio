#!/usr/bin/env python3
"""
Simple anime generator that actually works with minimal dependencies
No ML libraries, just ComfyUI API calls
"""

import json
import uuid
import time
import asyncio
from pathlib import Path
from typing import Dict, Optional
import httpx
import logging

logger = logging.getLogger(__name__)

class SimpleAnimeGenerator:
    """Basic anime generation using only ComfyUI API"""

    def __init__(self, comfyui_host: str = "localhost", comfyui_port: int = 8188):
        self.comfyui_url = f"http://{comfyui_host}:{comfyui_port}"
        self.client_id = str(uuid.uuid4())
        self.output_base = "/opt/ComfyUI/output"

    def ensure_project_directories(self, character_name: str = "default"):
        """Ensure project directory structure exists"""
        project_dir = Path(self.output_base) / "projects" / character_name

        # Create directory structure
        dirs_to_create = [
            project_dir / "images",
            project_dir / "animations",
            project_dir / "references",
            project_dir / "metadata"
        ]

        for dir_path in dirs_to_create:
            dir_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Project directories ensured for character: {character_name}")

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "low quality, bad anatomy",
        width: int = 1024,
        height: int = 1024,
        seed: int = -1,
        character_name: str = "default"
    ) -> Dict:
        """Generate a simple image using SDXL"""

        # Ensure project directories exist
        self.ensure_project_directories(character_name)

        if seed < 0:
            seed = int(time.time() * 1000) % 2147483647

        # Basic SDXL workflow
        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "counterfeit_v3.safetensors"
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
                    "steps": 20,
                    "cfg": 7.0,
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
                    "filename_prefix": f"projects/{character_name}/images/anime_{int(time.time())}",
                    "images": ["6", 0]
                }
            }
        }

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                # Submit workflow
                response = await client.post(
                    f"{self.comfyui_url}/prompt",
                    json={"prompt": workflow, "client_id": self.client_id}
                )

                if response.status_code != 200:
                    return {"success": False, "error": f"ComfyUI error: {response.text}"}

                prompt_id = response.json()["prompt_id"]

                # Wait for completion
                output_path = await self._wait_for_output(prompt_id)

                return {
                    "success": True,
                    "prompt_id": prompt_id,
                    "output_path": output_path,
                    "seed": seed,
                    "type": "image"
                }

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return {"success": False, "error": str(e)}

    async def generate_animation_loop(
        self,
        prompt: str,
        negative_prompt: str = "worst quality, low quality, blurry, static, still image",
        width: int = 512,
        height: int = 512,
        frames: int = 4,
        fps: int = 8,
        seed: int = -1,
        character_name: str = "default"
    ) -> Dict:
        """Generate animation loop using existing AnimateDiff workflow"""

        # Ensure project directories exist
        self.ensure_project_directories(character_name)

        if seed < 0:
            seed = int(time.time() * 1000) % 2147483647

        # Create proper AnimateDiff workflow based on working structure
        workflow = {
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
                    "steps": 15,
                    "cfg": 8.0,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1.0,
                    "model": ["12", 0],  # CRITICAL: Use AnimateDiff-wrapped model, not raw checkpoint
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                    "latent_image": ["5", 0]
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "counterfeit_v3.safetensors"
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
                    "filename_prefix": f"projects/{character_name}/animations/anime_loop_{int(time.time())}",
                    "format": "video/h264-mp4",
                    "pix_fmt": "yuv420p",
                    "crf": 18,
                    "save_metadata": True,
                    "pingpong": False,
                    "save_output": True
                }
            },
            "10": {
                "class_type": "ADE_LoadAnimateDiffModel",
                "inputs": {
                    "model_name": "mm-Stabilized_high.pth"
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

        try:
            async with httpx.AsyncClient(timeout=600) as client:
                # Submit workflow
                response = await client.post(
                    f"{self.comfyui_url}/prompt",
                    json={"prompt": workflow, "client_id": self.client_id}
                )

                if response.status_code != 200:
                    return {"success": False, "error": f"ComfyUI error: {response.text}"}

                prompt_id = response.json()["prompt_id"]

                # Return immediately - check status separately
                return {
                    "success": True,
                    "prompt_id": prompt_id,
                    "output_path": None,
                    "seed": seed,
                    "type": "animation_loop",
                    "frames": frames,
                    "fps": fps,
                    "duration": frames / fps,
                    "status": "processing",
                    "message": "Animation generation started - check status endpoint for completion"
                }

        except Exception as e:
            logger.error(f"Animation generation failed: {e}")
            return {"success": False, "error": str(e)}

    async def _wait_for_output(self, prompt_id: str, timeout: int = 300) -> Optional[str]:
        """Wait for ComfyUI to complete generation"""

        async with httpx.AsyncClient() as client:
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    # Check history
                    response = await client.get(f"{self.comfyui_url}/history/{prompt_id}")

                    if response.status_code == 200:
                        history = response.json()

                        if prompt_id in history:
                            prompt_history = history[prompt_id]

                            if "outputs" in prompt_history:
                                # Find image output
                                for node_id, output in prompt_history["outputs"].items():
                                    if "images" in output:
                                        return output["images"][0]["filename"]

                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"Error checking history: {e}")
                    await asyncio.sleep(2)

            return None

    async def _wait_for_video_output(self, prompt_id: str, job_id: str = None, timeout: int = 600) -> Optional[str]:
        """Wait for ComfyUI to complete video generation"""

        async with httpx.AsyncClient() as client:
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    # Check history
                    response = await client.get(f"{self.comfyui_url}/history/{prompt_id}")

                    if response.status_code == 200:
                        history = response.json()

                        if prompt_id in history:
                            prompt_history = history[prompt_id]

                            if "outputs" in prompt_history:
                                # Find video output (VHS_VideoCombine outputs show as images)
                                for node_id, output in prompt_history["outputs"].items():
                                    if "videos" in output:
                                        return output["videos"][0]["filename"]
                                    elif "images" in output:
                                        # Check if it's actually an MP4 file
                                        filename = output["images"][0]["filename"]
                                        if filename.endswith(".mp4"):
                                            return filename

                    await asyncio.sleep(5)  # Check less frequently for videos

                except Exception as e:
                    logger.error(f"Error checking video history: {e}")
                    await asyncio.sleep(5)

            return None


# Integration with v2 tracking
async def generate_with_tracking(
    prompt: str,
    character_name: str = "default",
    project_id: int = 1,
    generation_type: str = "image",
    **kwargs
) -> Dict:
    """Generate image with v2.0 tracking"""

    import sys
    sys.path.append('..')
    from v2_integration import create_tracked_job, complete_job_with_quality

    # Create v2 job
    frames = kwargs.get("frames", 1)
    duration = kwargs.get("duration", 0)

    if generation_type == "animation_loop":
        frames = kwargs.get("frames", 48)
        fps = kwargs.get("fps", 24)
        duration = frames / fps

    v2_job = await create_tracked_job(
        character_name=character_name,
        prompt=prompt,
        project_name=f"project_{project_id}",
        seed=kwargs.get("seed", -1),
        model="animatediff" if generation_type == "animation_loop" else "sdxl",
        width=kwargs.get("width", 1024),
        height=kwargs.get("height", 1024),
        duration=duration,
        frames=frames
    )

    # Generate based on type
    generator = SimpleAnimeGenerator()
    if generation_type == "animation_loop":
        result = await generator.generate_animation_loop(prompt, character_name=character_name, **kwargs)
    else:
        # Filter kwargs for image generation
        image_kwargs = {k: v for k, v in kwargs.items() if k in ['width', 'height', 'seed', 'negative_prompt']}
        result = await generator.generate_image(prompt, character_name=character_name, **image_kwargs)

    # Update v2 tracking and character consistency
    if result["success"] and v2_job:
        output_path = result.get("output_path", "")

        # Check character consistency if image was generated
        face_similarity = 0.75
        if generation_type == "image" and output_path:
            try:
                from character_consistency import check_character_consistency

                full_output_path = f"/opt/ComfyUI/output/{output_path}"
                if Path(full_output_path).exists():
                    consistency_result = await check_character_consistency(
                        full_output_path,
                        character_name,
                        minimum_score=0.7
                    )
                    face_similarity = consistency_result["consistency_score"]
                    result["character_consistency"] = consistency_result
            except Exception as e:
                logger.error(f"Character consistency check failed: {e}")

        await complete_job_with_quality(
            job_id=v2_job["job_id"],
            output_path=output_path,
            face_similarity=face_similarity,
            aesthetic_score=6.0
        )
        result["v2_job_id"] = v2_job["job_id"]

    return result


# Test function
async def test_generation():
    """Test the simple generator"""

    generator = SimpleAnimeGenerator()
    result = await generator.generate_image(
        prompt="anime girl with blue hair, high quality, detailed",
        negative_prompt="low quality, bad anatomy",
        width=512,
        height=768
    )

    print(f"Generation result: {result}")
    return result


if __name__ == "__main__":
    asyncio.run(test_generation())