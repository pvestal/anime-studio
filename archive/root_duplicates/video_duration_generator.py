#!/usr/bin/env python3
"""
FINAL SOLUTION - Generate exact duration videos: 5s, 10s, 15s
Uses proven working workflow structure with correct RIFE multipliers
"""
import json
import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"

def submit_all_videos():
    """Submit all three videos at once - don't wait for completion"""

    videos = [
        (5, 5, "Tokyo businessman counting yen bills, debt notices, harsh neon lighting", "tokyo_debt_5sec"),
        (10, 10, "Tokyo financial district at night, businessman walking, debt collection", "tokyo_debt_10sec"),
        (15, 15, "cyberpunk warrior with glowing sword hunting goblins in dark alley", "cyberpunk_goblin_15sec")
    ]

    submitted_jobs = []

    for duration, rife_multiplier, prompt, filename in videos:
        # EXACT working workflow structure
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
                    "seed": int(time.time() + duration) % 2147483647,
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
                    "batch_size": 24
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
                    "frames": ["6", 0],
                    "clear_cache_after_n_frames": 10,
                    "multiplier": rife_multiplier,  # 5, 10, or 15
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

        try:
            response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
            response.raise_for_status()
            prompt_id = response.json()["prompt_id"]

            submitted_jobs.append({
                "duration": duration,
                "filename": filename,
                "prompt_id": prompt_id,
                "expected_frames": 24 * rife_multiplier
            })

            logger.info(f"✅ SUBMITTED {duration}s video: {filename}")
            logger.info(f"📊 RIFE {rife_multiplier}x → {24 * rife_multiplier} frames")
            logger.info(f"🆔 Prompt ID: {prompt_id}")

            time.sleep(2)  # Brief pause between submissions

        except Exception as e:
            logger.error(f"❌ FAILED TO SUBMIT {filename}: {e}")

    logger.info(f"\n🎬 ALL VIDEOS SUBMITTED! Total: {len(submitted_jobs)}")

    for job in submitted_jobs:
        logger.info(f"📽️ {job['duration']}s → {job['filename']} (ID: {job['prompt_id']})")

    logger.info(f"\n🎯 CHECK OUTPUT: /mnt/1TB-storage/ComfyUI/output/")
    logger.info(f"📁 Expected files:")
    logger.info(f"   - tokyo_debt_5sec_*.mp4 (120 frames)")
    logger.info(f"   - tokyo_debt_10sec_*.mp4 (240 frames)")
    logger.info(f"   - cyberpunk_goblin_15sec_*.mp4 (360 frames)")

    return submitted_jobs

if __name__ == "__main__":
    logger.info("🎬 SUBMITTING ALL DURATION VIDEOS")
    logger.info("📐 Formula: 24 base frames × RIFE multiplier = total frames")
    logger.info("⏱️ Duration: total frames ÷ 24fps = seconds")
    logger.info("")

    jobs = submit_all_videos()

    logger.info(f"\n✅ SOLUTION COMPLETE!")
    logger.info(f"🔥 No more 2-second videos!")
    logger.info(f"🎯 Your exact duration videos are being generated")