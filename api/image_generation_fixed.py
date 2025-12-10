"""
PRODUCTION-READY Image Generation with Error Handling and Retries
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import aiohttp
from sqlalchemy import text

# Note: ProductionJob is passed from main.py - no import needed

logger = logging.getLogger(__name__)


class ImageGenerationError(Exception):
    """Custom exception for image generation failures"""


class ComfyUIClient:
    """Production-ready ComfyUI client with retries and error handling"""


    def __init__(self, base_url: str = "http://localhost:8188", max_retries: int = 3):
        self.base_url = base_url
        self.max_retries = max_retries
        self.retry_delays = [1, 2, 4]  # Exponential backoff


    async def submit_workflow(self, workflow: Dict[str, Any], job_id: int) -> Optional[str]:
        """
        Submit workflow to ComfyUI with proper error handling and retries

        Returns:
            prompt_id if successful, None if all retries failed
        """

        # Validate workflow structure
        if not workflow:
            logger.error(f"Job {job_id}: Empty workflow provided")
            raise ImageGenerationError("Workflow cannot be empty")

        # Prepare the payload with correct structure
        payload = {
            "prompt": workflow,  # ComfyUI expects workflow under "prompt" key
            "client_id": f"anime_image_{job_id}",
        }

        last_error = None

        for attempt in range(self.max_retries):
            try:
                logger.info(
                    f"Job {job_id}: Attempt {attempt + 1}/{self.max_retries} to submit to ComfyUI"
                )

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/prompt",
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:

                        # Log response status
                        logger.info(
                            f"Job {job_id}: ComfyUI responded with status {response.status}"
                        )

                        # Check HTTP status
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(
                                f"Job {job_id}: ComfyUI returned error {response.status}: {error_text}"
                            )
                            raise ImageGenerationError(
                                f"ComfyUI error {response.status}: {error_text}"
                            )

                        # Parse response
                        result = await response.json()

                        # Validate response structure
                        if "error" in result:
                            error_detail = result.get("error", {})
                            error_msg = error_detail.get("message", "Unknown error")
                            logger.error(f"Job {job_id}: ComfyUI workflow error: {error_msg}")

                            # Check if it's a recoverable error
                            if "no_prompt" in str(error_detail.get("type", "")):
                                # Workflow format issue - don't retry
                                raise ImageGenerationError(f"Workflow format error: {error_msg}")
                            else:
                                # Other error - retry
                                raise ImageGenerationError(f"ComfyUI processing error: {error_msg}")

                        # Extract prompt_id
                        prompt_id = result.get("prompt_id")
                        if not prompt_id:
                            logger.error(f"Job {job_id}: No prompt_id in response: {result}")
                            raise ImageGenerationError("ComfyUI did not return a prompt_id")

                        # Success!
                        logger.info(
                            f"Job {job_id}: Successfully submitted, got prompt_id: {prompt_id}"
                        )
                        return prompt_id

            except asyncio.TimeoutError:
                last_error = "ComfyUI request timed out after 30 seconds"
                logger.error(f"Job {job_id}: {last_error}")

            except aiohttp.ClientError as e:
                last_error = f"Network error: {str(e)}"
                logger.error(f"Job {job_id}: {last_error}")

            except ImageGenerationError as e:
                last_error = str(e)
                if "format error" in last_error.lower():
                    # Don't retry format errors
                    logger.error(f"Job {job_id}: Unrecoverable error: {last_error}")
                    break

            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                logger.error(f"Job {job_id}: {last_error}", exc_info=True)

            # Wait before retry (except on last attempt)
            if attempt < self.max_retries - 1:
                delay = self.retry_delays[attempt]
                logger.info(f"Job {job_id}: Waiting {delay}s before retry...")
                await asyncio.sleep(delay)

        # All retries failed
        logger.error(
            f"Job {job_id}: All {self.max_retries} attempts failed. Last error: {last_error}"
        )
        raise ImageGenerationError(f"Failed after {self.max_retries} attempts: {last_error}")


    async def check_job_status(self, prompt_id: str) -> Dict[str, Any]:
        """Check the status of a ComfyUI job"""

        try:
            async with aiohttp.ClientSession() as session:
                # Check queue status
                async with session.get(f"{self.base_url}/queue") as response:
                    queue_data = await response.json()

                    # Check if job is running
                    for job in queue_data.get("queue_running", []):
                        if job[1] == prompt_id:
                            return {"status": "running", "progress": 0.5}

                    # Check if job is pending
                    for job in queue_data.get("queue_pending", []):
                        if job[1] == prompt_id:
                            return {"status": "pending", "progress": 0.0}

                # Check history for completion
                async with session.get(f"{self.base_url}/history/{prompt_id}") as response:
                    history = await response.json()

                    if prompt_id in history:
                        job_data = history[prompt_id]

                        # Check for outputs
                        if "outputs" in job_data:
                            # Find image outputs
                            for node_id, node_output in job_data["outputs"].items():
                                if "images" in node_output:
                                    image = node_output["images"][0]
                                    return {
                                        "status": "completed",
                                        "progress": 1.0,
                                        "output": {
                                            "filename": image.get("filename"),
                                            "subfolder": image.get("subfolder", ""),
                                            "type": image.get("type", "output"),
                                        },
                                    }

                        # Job finished but no outputs (error?)
                        return {"status": "failed", "error": "No outputs generated"}

                # Job not found anywhere
                return {"status": "not_found"}

        except Exception as e:
            logger.error(f"Error checking job status for {prompt_id}: {str(e)}")
            return {"status": "error", "error": str(e)}


async def generate_anime_image_production(
    prompt: str, quality: str = "high", style: str = "anime", job_id: int = None, db=None
) -> Dict[str, Any]:
    """
    Production-ready image generation with full error handling
    """

    # Quality presets
    quality_settings = {
        "low": {"width": 512, "height": 512, "steps": 15, "cfg": 6.0},
        "medium": {"width": 768, "height": 768, "steps": 20, "cfg": 7.0},
        "high": {"width": 1024, "height": 1024, "steps": 30, "cfg": 8.0},
    }

    settings = quality_settings.get(quality, quality_settings["medium"])
    seed = int(time.time())

    # Build workflow
    workflow = {
        "1": {
            "inputs": {"ckpt_name": "AOM3A1B.safetensors"},
            "class_type": "CheckpointLoaderSimple",
            "_meta": {"title": "Load Checkpoint"},
        },
        "2": {
            "inputs": {
                "text": f"{prompt}, {style} style, masterpiece, best quality, detailed",
                "clip": ["1", 1],
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Positive Prompt"},
        },
        "3": {
            "inputs": {
                "text": "worst quality, low quality, blurry, ugly, distorted, watermark",
                "clip": ["1", 1],
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Negative Prompt"},
        },
        "4": {
            "inputs": {"width": settings["width"], "height": settings["height"], "batch_size": 1},
            "class_type": "EmptyLatentImage",
            "_meta": {"title": "Latent Image"},
        },
        "5": {
            "inputs": {
                "seed": seed,
                "steps": settings["steps"],
                "cfg": settings["cfg"],
                "sampler_name": "euler_ancestral",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
            "class_type": "KSampler",
            "_meta": {"title": "KSampler"},
        },
        "6": {
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            "class_type": "VAEDecode",
            "_meta": {"title": "VAE Decode"},
        },
        "7": {
            "inputs": {"filename_prefix": f"anime_{quality}_{job_id or seed}", "images": ["6", 0]},
            "class_type": "SaveImage",
            "_meta": {"title": "Save Image"},
        },
    }

    # Initialize ComfyUI client
    client = ComfyUIClient()

    try:
        # Submit to ComfyUI with retries
        prompt_id = await client.submit_workflow(workflow, job_id or 0)

        if not prompt_id:
            raise ImageGenerationError("Failed to get prompt_id from ComfyUI")

        # Update database if provided
        if db and job_id:
            # Use raw SQL with text() wrapper to avoid import issues
            # Update production_jobs table with ComfyUI job ID and set status to processing
            db.execute(
                text(
                    "UPDATE anime_api.production_jobs SET comfyui_job_id = :prompt_id, status = 'processing' WHERE id = :job_id"
                ),
                {"prompt_id": prompt_id, "job_id": job_id},
            )
            db.commit()

        return {
            "success": True,
            "job_id": job_id,
            "prompt_id": prompt_id,
            "status": "processing",
            "message": f"Image generation started ({settings['width']}x{settings['height']}, {settings['steps']} steps)",
            "estimated_time": f"{settings['steps'] * 1.5} seconds",
            "quality": quality,
            "settings": settings,
        }

    except ImageGenerationError as e:
        # Log the failure
        logger.error(f"Image generation failed for job {job_id}: {str(e)}")

        # Update database to failed (use raw SQL with text() to avoid import)
        if db and job_id:
            db.execute(
                text(
                    "UPDATE anime_api.production_jobs SET status = 'failed', error = :error WHERE id = :job_id"
                ),
                {"error": str(e), "job_id": job_id},
            )
            db.commit()

        return {
            "success": False,
            "job_id": job_id,
            "error": str(e),
            "status": "failed",
            "message": f"Image generation failed after retries: {str(e)}",
        }

    except Exception as e:
        # Unexpected error
        logger.error(f"Unexpected error in image generation: {str(e)}", exc_info=True)

        return {
            "success": False,
            "job_id": job_id,
            "error": f"Unexpected error: {str(e)}",
            "status": "error",
        }
