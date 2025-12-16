#!/usr/bin/env python3
"""
FINAL WORKING IMPLEMENTATION - NO MORE BULLSHIT
Generate videos with increasing duration: 24, 48, 72, 96 frames
"""
import json
import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"

def generate_video(frames, prompt, filename):
    """Generate one video with specified frame count"""

    # Use YOUR working workflow structure from test_animatediff_5sec.py
    workflow = {
        "1": {
            "inputs": {
                "ckpt_name": "counterfeit_v3.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {
                "model_name": "mm-Stabilized_high.pth",
                "beta_schedule": "autoselect",
                "model": ["1", 0]
            },
            "class_type": "ADE_AnimateDiffLoaderGen1"
        },
        "3": {
            "inputs": {
                "text": f"photorealistic, cinematic, {prompt}",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "4": {
            "inputs": {
                "text": "anime, cartoon, static, blurry, low quality, deformed",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "5": {
            "inputs": {
                "batch_size": frames,  # THIS IS THE KEY - MORE FRAMES = LONGER VIDEO
                "width": 512,
                "height": 512
            },
            "class_type": "EmptyLatentImage"
        },
        "6": {
            "inputs": {
                "seed": int(time.time()) % 2147483647,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["2", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler"
        },
        "7": {
            "inputs": {
                "samples": ["6", 0],
                "vae": ["1", 2]
            },
            "class_type": "VAEDecode"
        },
        "8": {
            "inputs": {
                "images": ["7", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": filename,
                "format": "video/h264-mp4",
                "crf": 20,
                "save_metadata": True
            },
            "class_type": "VHS_VideoCombine"
        }
    }

    logger.info(f"🎬 Generating {frames} frames: {filename}")

    try:
        response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]

        logger.info(f"✅ Submitted: {prompt_id}")

        # Wait for completion
        start_time = time.time()
        while time.time() - start_time < 600:  # 10 minute timeout
            try:
                response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
                history = response.json()

                if prompt_id in history:
                    status = history[prompt_id]["status"]
                    if status.get("completed", False):
                        gen_time = time.time() - start_time
                        logger.info(f"✅ COMPLETED {filename} in {gen_time:.1f}s")
                        return True
                    elif "error" in status:
                        logger.error(f"❌ FAILED {filename}: {status['error']}")
                        return False

                time.sleep(10)

            except Exception as e:
                logger.warning(f"Status check error: {e}")
                time.sleep(5)

        logger.error(f"❌ TIMEOUT {filename}")
        return False

    except Exception as e:
        logger.error(f"❌ SUBMIT FAILED {filename}: {e}")
        return False

def main():
    """Generate videos with increasing frame counts"""

    logger.info("🎬 GENERATING VIDEOS WITH INCREASING DURATION")

    videos = [
        (24, "Tokyo businessman counting yen bills, debt notices, harsh lighting", "24frames_1sec"),
        (48, "Tokyo financial district at night, businessman walking, neon lights", "48frames_2sec"),
        (72, "cyberpunk warrior with glowing sword hunting creatures in alley", "72frames_3sec"),
        (96, "epic battle cyber goblins futuristic Tokyo explosions action", "96frames_4sec")
    ]

    for frames, prompt, filename in videos:
        logger.info(f"\n📽️ GENERATING: {frames} frames = {frames/24:.1f} seconds")

        success = generate_video(frames, prompt, filename)

        if success:
            logger.info(f"✅ SUCCESS: {filename}")
        else:
            logger.error(f"❌ FAILED: {filename}")

        # Pause between videos
        time.sleep(10)

    logger.info("\n🎯 CHECK OUTPUT: /mnt/1TB-storage/ComfyUI/output/")
    logger.info("FILES: 24frames_*.mp4, 48frames_*.mp4, 72frames_*.mp4, 96frames_*.mp4")

if __name__ == "__main__":
    main()