#!/usr/bin/env python3
"""
Generate photorealistic videos - ONLY Tokyo debt desire and cyberpunk goblin slayer
Increasing duration: 2s, 5s, 10s, 15s
"""
import json
import requests
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"

def create_photorealistic_workflow(duration_seconds, prompt_text):
    """Create workflow for photorealistic video generation"""
    frames = duration_seconds * 24

    workflow = {
        "1": {
            "inputs": {
                "text": f"photorealistic, cinematic, 8k, ultra detailed, {prompt_text}",
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "2": {
            "inputs": {
                "text": "anime, cartoon, animated, unrealistic, low quality, blurry",
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "3": {
            "inputs": {
                "seed": int(time.time()) % 2147483647,
                "steps": 25,
                "cfg": 7.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["12", 0],
                "positive": ["1", 0],
                "negative": ["2", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler"
        },
        "4": {
            "inputs": {
                "ckpt_name": "AOM3A1B.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "5": {
            "inputs": {
                "width": 1024,
                "height": 1024,
                "length": frames,
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
                "images": ["6", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": f"REAL_{duration_seconds}SEC_",
                "format": "video/h264-mp4",
                "crf": 18
            },
            "class_type": "VHS_VideoCombine"
        },
        "12": {
            "inputs": {
                "model_name": "mm_sd_v15_v2.ckpt",
                "model": ["4", 0]
            },
            "class_type": "AnimateDiffLoader"
        }
    }
    return workflow

def submit_and_wait(workflow, description, duration):
    """Submit workflow and wait for completion"""
    try:
        response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]

        logger.info(f"🎬 Generating {description} ({duration}s) - ID: {prompt_id}")

        start_time = time.time()
        while time.time() - start_time < duration * 60:  # 1 min per second
            try:
                response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
                history = response.json()

                if prompt_id in history:
                    status = history[prompt_id]["status"]
                    if status.get("completed", False):
                        gen_time = time.time() - start_time
                        logger.info(f"✅ {description} completed in {gen_time:.1f}s")
                        return True
                    elif "error" in status:
                        logger.error(f"❌ {description} failed: {status['error']}")
                        return False

                elapsed = time.time() - start_time
                logger.info(f"⏳ {description}: {elapsed:.0f}s elapsed")
                time.sleep(10)

            except Exception as e:
                logger.warning(f"Status check error: {e}")
                time.sleep(10)

        logger.error(f"❌ {description} timeout")
        return False

    except Exception as e:
        logger.error(f"❌ {description} submit failed: {e}")
        return False

def main():
    """Generate the two video series"""

    logger.info("="*60)
    logger.info("🎬 GENERATING PHOTOREALISTIC VIDEOS")
    logger.info("ONLY: Tokyo debt desire + Cyberpunk goblin slayer")
    logger.info("="*60)

    # Define the two themes with photorealistic prompts
    themes = [
        {
            "name": "Tokyo Debt Desire",
            "prompts": [
                "cinematic shot of desperate businessman in Tokyo financial district at night, neon lights reflecting off wet streets, realistic lighting",
                "photorealistic scene of person staring at mounting bills and debt notices in cramped Tokyo apartment, dramatic shadows",
                "cinematic wide shot of Tokyo skyline at dawn, symbolizing financial pressure and urban debt crisis, hyper realistic",
                "photorealistic close-up of hands counting yen bills under harsh fluorescent light, debt and desperation visible"
            ]
        },
        {
            "name": "Cyberpunk Goblin Slayer",
            "prompts": [
                "photorealistic cyberpunk warrior in high-tech armor hunting creatures in neon-lit Tokyo alley, cinematic lighting",
                "realistic shot of armored figure with glowing sword confronting grotesque creatures in futuristic cityscape",
                "cinematic scene of cyberpunk goblin hunter moving through dark industrial complex, volumetric lighting, 8k detail",
                "photorealistic battle scene with armored warrior and cyber-enhanced goblins in dystopian Tokyo setting"
            ]
        }
    ]

    durations = [2, 5, 10, 15]

    for theme in themes:
        logger.info(f"\n🎭 GENERATING: {theme['name']}")

        for i, duration in enumerate(durations):
            prompt = theme['prompts'][i % len(theme['prompts'])]
            description = f"{theme['name']} {duration}s"

            workflow = create_photorealistic_workflow(duration, prompt)

            success = submit_and_wait(workflow, description, duration)
            if success:
                logger.info(f"✅ {description} - COMPLETED")
            else:
                logger.error(f"❌ {description} - FAILED")

            # Brief pause between generations
            time.sleep(5)

    logger.info("="*60)
    logger.info("🎯 GENERATION COMPLETE")
    logger.info("Check /mnt/1TB-storage/ComfyUI/output/ for REAL_*SEC_*.mp4 files")
    logger.info("="*60)

if __name__ == "__main__":
    main()