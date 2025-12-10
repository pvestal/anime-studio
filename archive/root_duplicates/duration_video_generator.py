#!/usr/bin/env python3
"""
WORKING IMPLEMENTATION - Generate videos with exact durations
5 seconds, 10 seconds, 15 seconds using correct RIFE multipliers
"""
import json
import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"

def generate_video(duration_seconds, rife_multiplier, prompt, filename):
    """Generate one video with specified duration using RIFE multiplier"""

    # EXACT workflow structure from user's working 30-second setup
    workflow = {
        "1": {
            "inputs": {
                "text": f"photorealistic, cinematic, {prompt}",
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "2": {
            "inputs": {
                "text": "anime, cartoon, static, blurry, low quality, deformed",
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "3": {
            "inputs": {
                "seed": int(time.time()) % 2147483647,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
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
                "width": 512,
                "height": 512,
                "batch_size": 24  # Always 24 base frames
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
                "filename_prefix": f"{filename}_1sec",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 20,
                "save_metadata": True,
                "pingpong": False,
                "save_output": True
            },
            "class_type": "VHS_VideoCombine"
        },
        "8": {
            "inputs": {
                "ckpt_name": "rife47.pth",
                "frames": ["6", 0],  # Takes frames not images
                "clear_cache_after_n_frames": 10,
                "multiplier": rife_multiplier,  # KEY: This determines duration
                "fast_mode": False,
                "ensemble": False,
                "scale_factor": 1.0
            },
            "class_type": "RIFE VFI"
        },
        "9": {
            "inputs": {
                "images": ["8", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": filename,
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 18,
                "save_metadata": True,
                "pingpong": False,
                "save_output": True
            },
            "class_type": "VHS_VideoCombine"
        },
        "10": {
            "inputs": {
                "model_name": "mm-Stabilized_high.pth"
            },
            "class_type": "ADE_LoadAnimateDiffModel"
        },
        "11": {
            "inputs": {
                "motion_model": ["10", 0]
            },
            "class_type": "ADE_ApplyAnimateDiffModelSimple"
        },
        "12": {
            "inputs": {
                "model": ["4", 0],
                "beta_schedule": "autoselect",
                "m_models": ["11", 0]
            },
            "class_type": "ADE_UseEvolvedSampling"
        }
    }

    expected_frames = 24 * rife_multiplier
    logger.info(f"🎬 Generating {duration_seconds}s video: {filename}")
    logger.info(f"📊 RIFE multiplier: {rife_multiplier} → {expected_frames} frames")

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
    """Generate videos with exact durations using calculated RIFE multipliers"""

    logger.info("🎬 GENERATING VIDEOS WITH EXACT DURATIONS")
    logger.info("📐 Math: 24 base frames × RIFE multiplier = total frames")
    logger.info("⏱️ At 24fps: total frames ÷ 24 = duration seconds")

    videos = [
        # (duration, rife_multiplier, prompt, filename)
        (5, 5, "Tokyo businessman counting yen bills, debt notices, harsh neon lighting", "tokyo_debt_5sec"),
        (10, 10, "Tokyo financial district at night, businessman walking, debt collection", "tokyo_debt_10sec"),
        (15, 15, "cyberpunk warrior with glowing sword hunting goblins in dark alley", "cyberpunk_goblin_15sec")
    ]

    for duration, rife_multiplier, prompt, filename in videos:
        expected_frames = 24 * rife_multiplier
        logger.info(f"\n📽️ NEXT: {duration}s = {rife_multiplier}x multiplier = {expected_frames} frames")

        success = generate_video(duration, rife_multiplier, prompt, filename)

        if success:
            logger.info(f"✅ SUCCESS: {filename}.mp4")
        else:
            logger.error(f"❌ FAILED: {filename}")

        # Pause between videos
        time.sleep(10)

    logger.info("\n🎯 CHECK OUTPUT: /mnt/1TB-storage/ComfyUI/output/")
    logger.info("FILES: tokyo_debt_5sec_*.mp4, tokyo_debt_10sec_*.mp4, cyberpunk_goblin_15sec_*.mp4")

if __name__ == "__main__":
    main()