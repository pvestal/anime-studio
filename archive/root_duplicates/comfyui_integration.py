#!/usr/bin/env python3
"""
ComfyUI Integration Module
Handles proper ComfyUI workflow execution for video generation
"""

import asyncio
import aiohttp
import json
import logging
import time
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

class ComfyUIIntegration:
    """ComfyUI integration for anime video generation"""

    def __init__(self, comfyui_url: str = "http://***REMOVED***:8188"):
        self.comfyui_url = comfyui_url

    async def load_workflow_template(self, duration: int) -> Dict:
        """Load ComfyUI workflow template based on duration"""
        workflow_file = f"/opt/tower-anime-production/workflows/comfyui/anime_30sec_MOTION_FIXED.json"

        try:
            with open(workflow_file, 'r') as f:
                workflow = json.load(f)

            # Echo Brain optimization: AnimateDiff with proper frame handling
            # Use 24fps base for smooth animation, segment if needed
            base_frames = min(120, duration * 24)  # 24fps base, max 120 frames per segment
            target_frames = duration * 24  # Final target: 24fps

            logger.info(f"🧠 Echo optimization: {base_frames} base frames, RIFE interpolation for {duration}s video")

            # Update EmptyLatentImage batch_size for VRAM-optimized generation
            for node_id, node in workflow.items():
                if node.get("class_type") == "EmptyLatentImage":
                    node["inputs"]["batch_size"] = base_frames
                    node["_meta"]["title"] = f"VRAM Optimized: {base_frames} base → {target_frames} final"
                    logger.info(f"🎛️ Updated batch_size to {base_frames} frames for VRAM efficiency")
                    break

            # Echo's adaptive interpolation: conservative multiplier for quality
            rife_multiplier = min(4, max(2, target_frames // base_frames))  # Cap at 4x for stability
            for node_id, node in workflow.items():
                if node.get("class_type") == "RIFE VFI":
                    node["inputs"]["multiplier"] = rife_multiplier
                    node["inputs"]["fast_mode"] = True  # Enable fast mode for VRAM efficiency
                    node["_meta"]["title"] = f"Echo RIFE: {rife_multiplier}x (fast mode)"
                    logger.info(f"🚀 RIFE optimized: {rife_multiplier}x multiplier with fast mode")
                    break

            # Reduce sampling steps for VRAM efficiency (Echo's recommendation)
            for node_id, node in workflow.items():
                if node.get("class_type") == "KSampler":
                    node["inputs"]["steps"] = 20  # Reduced from 30 for faster generation
                    node["inputs"]["cfg"] = 7.5   # Slightly reduced CFG for efficiency
                    logger.info(f"🎯 Sampling optimized: 20 steps, CFG 7.5 for VRAM efficiency")
                    break

            return workflow
        except Exception as e:
            logger.error(f"Failed to load workflow template: {e}")
            return {}

    async def wait_for_completion(self, prompt_id: str) -> Optional[str]:
        """Wait for ComfyUI generation to complete and return output path"""
        max_wait = 7200  # 2 hours
        check_interval = 5  # seconds
        total_waited = 0

        while total_waited < max_wait:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.comfyui_url}/history/{prompt_id}") as response:
                        if response.status == 200:
                            data = await response.json()
                            if prompt_id in data:
                                outputs = data[prompt_id].get('outputs', {})
                                # Find the first video output
                                for node_id, output in outputs.items():
                                    if 'videos' in output:
                                        videos = output['videos']
                                        if videos:
                                            filename = videos[0]['filename']
                                            return f"/mnt/1TB-storage/ComfyUI/output/{filename}"
                                    elif 'images' in output:
                                        images = output['images']
                                        if images:
                                            filename = images[0]['filename']
                                            return f"/mnt/1TB-storage/ComfyUI/output/{filename}"

                await asyncio.sleep(check_interval)
                total_waited += check_interval

            except Exception as e:
                logger.warning(f"Error checking ComfyUI status: {e}")
                await asyncio.sleep(check_interval)
                total_waited += check_interval

        logger.error(f"ComfyUI generation timed out after {max_wait} seconds")
        return None

    async def generate_video(self, prompt: str, duration: int, style: str = "anime") -> Dict[str, Any]:
        """Generate video using ComfyUI"""
        start_time = time.time()

        try:
            # Load and customize workflow
            workflow = await self.load_workflow_template(duration)
            if not workflow:
                raise Exception("Failed to load ComfyUI workflow template")

            # Update positive prompt in workflow
            for node_id, node in workflow.items():
                if node.get("class_type") == "CLIPTextEncode":
                    title = node.get("_meta", {}).get("title", "")
                    if "positive" in title.lower() or "prompt" in title.lower():
                        node["inputs"]["text"] = prompt
                        break

            # Submit to ComfyUI
            async with aiohttp.ClientSession() as session:
                payload = {
                    "prompt": workflow,
                    "client_id": f"orchestrator_{int(time.time())}"
                }

                async with session.post(
                    f"{self.comfyui_url}/prompt",
                    json=payload,
                    timeout=30  # Just for submission
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        prompt_id = data.get("prompt_id")

                        if prompt_id:
                            logger.info(f"🎬 ComfyUI generation started with prompt_id: {prompt_id}")
                            # Wait for completion and get result
                            result_path = await self.wait_for_completion(prompt_id)

                            processing_time = time.time() - start_time

                            return {
                                "success": True,
                                "generation_id": prompt_id,
                                "output_path": result_path,
                                "processing_time_seconds": round(processing_time, 2),
                                "video_specs": {
                                    "duration_seconds": duration,
                                    "style": style,
                                    "frames": duration * 24
                                }
                            }
                        else:
                            raise Exception("No prompt_id returned from ComfyUI")
                    else:
                        response_text = await response.text()
                        return {
                            "success": False,
                            "error": f"ComfyUI submission failed: {response.status} - {response_text}"
                        }

        except Exception as e:
            logger.error(f"ComfyUI generation error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

# Test function
async def test_comfyui_integration():
    """Test ComfyUI integration"""
    integration = ComfyUIIntegration()

    test_prompt = "1girl, anime style, magical transformation, sparkles, dynamic movement"
    test_duration = 5  # 5 seconds

    result = await integration.generate_video(test_prompt, test_duration)

    if result["success"]:
        print(f"✅ Generation successful!")
        print(f"Output: {result.get('output_path', 'N/A')}")
        print(f"Time: {result.get('processing_time_seconds', 0)}s")
    else:
        print(f"❌ Generation failed: {result.get('error', 'Unknown error')}")

    return result

if __name__ == "__main__":
    asyncio.run(test_comfyui_integration())