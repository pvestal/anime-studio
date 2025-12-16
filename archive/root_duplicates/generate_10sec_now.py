#!/usr/bin/env python3
"""
Generate ONE 10-second video RIGHT NOW
No bullshit, no series, just prove it works
"""
import json
import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"

def generate_10_second_video():
    """Generate ONE 10-second video to prove it works"""

    # 10 seconds at 8fps = 80 frames
    frames = 80

    workflow = {
        "1": {
            "inputs": {
                "text": "photorealistic cyberpunk warrior with glowing sword hunting creatures in dark Tokyo alley, neon lights, cinematic action sequence",
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "2": {
            "inputs": {
                "text": "anime, cartoon, low quality, blurry, ugly, distorted, static, still image, text, watermark",
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
                "batch_size": frames
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
                "frame_rate": 8,
                "loop_count": 0,
                "filename_prefix": "PROOF_10SEC_VIDEO",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 20,
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

    logger.info("🎬 GENERATING ONE 10-SECOND VIDEO")
    logger.info("80 frames at 8fps = 10 seconds")
    logger.info("Cyberpunk goblin slayer theme, photorealistic")

    try:
        response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]

        logger.info(f"✅ Submitted 10-second video - ID: {prompt_id}")

        start_time = time.time()
        max_wait = 1200  # 20 minutes max

        while time.time() - start_time < max_wait:
            try:
                response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
                history = response.json()

                if prompt_id in history:
                    status = history[prompt_id]["status"]
                    if status.get("completed", False):
                        gen_time = time.time() - start_time
                        logger.info(f"✅ 10-SECOND VIDEO COMPLETED in {gen_time:.1f} seconds")
                        logger.info("📁 File: /mnt/1TB-storage/ComfyUI/output/PROOF_10SEC_VIDEO_*.mp4")
                        return True
                    elif "error" in status:
                        logger.error(f"❌ 10-second video FAILED: {status['error']}")
                        return False

                elapsed = time.time() - start_time
                logger.info(f"⏳ 10-second video generating... {elapsed:.0f}s / {max_wait}s")
                time.sleep(30)  # Check every 30 seconds

            except Exception as e:
                logger.warning(f"Status check error: {e}")
                time.sleep(10)

        logger.error(f"❌ 10-second video TIMEOUT after {max_wait} seconds")
        return False

    except Exception as e:
        logger.error(f"❌ 10-second video submit failed: {e}")
        return False

if __name__ == "__main__":
    if generate_10_second_video():
        print("\n🎯 SUCCESS! 10-second video generated.")
        print("Now you have proof it works for longer videos.")
    else:
        print("\n💥 FAILED! 10-second generation failed.")