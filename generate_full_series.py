#!/usr/bin/env python3
"""
Generate full video series using PROVEN working workflow
2s, 5s, 10s, 15s for both projects
"""
import json
import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"

def create_working_workflow(frames, prompt, filename_prefix):
    """Use EXACT working workflow, just change frames and prompt"""

    workflow = {
        "1": {
            "inputs": {
                "text": prompt,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "CLIP Text Encode (Prompt)"}
        },
        "2": {
            "inputs": {
                "text": "anime, cartoon, low quality, blurry, ugly, distorted, static, still image, text, watermark",
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "CLIP Text Encode (Negative)"}
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
            "class_type": "KSampler",
            "_meta": {"title": "KSampler"}
        },
        "4": {
            "inputs": {
                "ckpt_name": "AOM3A1B.safetensors"
            },
            "class_type": "CheckpointLoaderSimple",
            "_meta": {"title": "Load Checkpoint"}
        },
        "5": {
            "inputs": {
                "width": 512,
                "height": 512,
                "batch_size": frames
            },
            "class_type": "EmptyLatentImage",
            "_meta": {"title": f"Empty Latent Image ({frames} frames)"}
        },
        "6": {
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            },
            "class_type": "VAEDecode",
            "_meta": {"title": "VAE Decode"}
        },
        "7": {
            "inputs": {
                "images": ["6", 0],
                "frame_rate": 8,
                "loop_count": 0,
                "filename_prefix": filename_prefix,
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 20,
                "save_metadata": True,
                "pingpong": False,
                "save_output": True
            },
            "class_type": "VHS_VideoCombine",
            "_meta": {"title": "Video Combine"}
        },
        "10": {
            "inputs": {
                "model_name": "mm-Stabilized_high.pth"
            },
            "class_type": "ADE_LoadAnimateDiffModel",
            "_meta": {"title": "Load AnimateDiff Model"}
        },
        "11": {
            "inputs": {
                "motion_model": ["10", 0]
            },
            "class_type": "ADE_ApplyAnimateDiffModelSimple",
            "_meta": {"title": "Apply AnimateDiff Model Simple"}
        },
        "12": {
            "inputs": {
                "model": ["4", 0],
                "beta_schedule": "autoselect",
                "m_models": ["11", 0]
            },
            "class_type": "ADE_UseEvolvedSampling",
            "_meta": {"title": "Use Evolved Sampling"}
        }
    }

    return workflow

def generate_one_video(frames, prompt, filename_prefix, duration_desc):
    """Generate one video using proven workflow"""

    logger.info(f"🎬 Generating: {filename_prefix} ({duration_desc})")
    logger.info(f"Frames: {frames}")

    workflow = create_working_workflow(frames, prompt, filename_prefix)

    try:
        response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]

        logger.info(f"✅ Submitted - ID: {prompt_id}")

        start_time = time.time()
        max_wait = frames * 10  # 10 seconds per frame max

        while time.time() - start_time < max_wait:
            try:
                response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
                history = response.json()

                if prompt_id in history:
                    status = history[prompt_id]["status"]
                    if status.get("completed", False):
                        gen_time = time.time() - start_time
                        logger.info(f"✅ SUCCESS! {filename_prefix} in {gen_time:.1f}s")
                        return True
                    elif "error" in status:
                        logger.error(f"❌ FAILED: {status['error']}")
                        return False

                elapsed = time.time() - start_time
                if elapsed % 20 == 0:
                    logger.info(f"⏳ {elapsed:.0f}s / {max_wait}s")
                time.sleep(10)

            except Exception as e:
                logger.warning(f"Status check error: {e}")
                time.sleep(5)

        logger.error(f"❌ TIMEOUT after {max_wait}s")
        return False

    except Exception as e:
        logger.error(f"❌ Submit failed: {e}")
        return False

def main():
    """Generate all videos using proven approach"""

    logger.info("="*70)
    logger.info("🎬 GENERATING FULL VIDEO SERIES")
    logger.info("Using PROVEN working workflow")
    logger.info("="*70)

    videos = [
        # Tokyo Debt Desire
        {
            "frames": 16,
            "duration": "2s",
            "prompt": "photorealistic businessman in Tokyo apartment counting yen bills, debt notices scattered, harsh fluorescent lighting, cinematic",
            "filename": "TokyoDebt_2sec"
        },
        {
            "frames": 40,
            "duration": "5s",
            "prompt": "photorealistic Tokyo financial district at night, businessman walking through neon-lit streets, rain reflecting debt desperation, cinematic realism",
            "filename": "TokyoDebt_5sec"
        },
        {
            "frames": 80,
            "duration": "10s",
            "prompt": "photorealistic wide shot Tokyo skyline transitioning day to night, symbolizing mounting financial pressure and urban debt crisis, hyper realistic",
            "filename": "TokyoDebt_10sec"
        },
        {
            "frames": 120,
            "duration": "15s",
            "prompt": "photorealistic emotional sequence person reviewing bank statements, close-ups worried face and financial documents, dramatic lighting",
            "filename": "TokyoDebt_15sec"
        },

        # Cyberpunk Goblin Slayer
        {
            "frames": 16,
            "duration": "2s",
            "prompt": "photorealistic cyberpunk warrior with glowing sword in dark Tokyo alley, hunting grotesque creatures, neon lights, cinematic",
            "filename": "CyberpunkGoblin_2sec"
        },
        {
            "frames": 40,
            "duration": "5s",
            "prompt": "photorealistic cyberpunk goblin slayer moving through industrial complex, high-tech armor gleaming, volumetric lighting through smoke",
            "filename": "CyberpunkGoblin_5sec"
        },
        {
            "frames": 80,
            "duration": "10s",
            "prompt": "photorealistic epic battle cyber-enhanced goblin creatures in futuristic Tokyo, sparks explosions, dramatic action sequence",
            "filename": "CyberpunkGoblin_10sec"
        },
        {
            "frames": 120,
            "duration": "15s",
            "prompt": "photorealistic extended combat sequence armored warrior hunting cyber-goblins through dystopian cityscape, dynamic camera, 8k detail",
            "filename": "CyberpunkGoblin_15sec"
        }
    ]

    success_count = 0
    total_videos = len(videos)

    for i, video in enumerate(videos, 1):
        logger.info(f"\n📽️ VIDEO {i}/{total_videos}")

        if generate_one_video(
            video["frames"],
            video["prompt"],
            video["filename"],
            video["duration"]
        ):
            success_count += 1

        # Pause between videos
        if i < total_videos:
            logger.info("⏸️ Pausing 15s before next video...")
            time.sleep(15)

    logger.info("="*70)
    logger.info(f"🎯 FINAL RESULTS: {success_count}/{total_videos} videos completed")
    logger.info("📁 Output directory: /mnt/1TB-storage/ComfyUI/output/")
    logger.info("📁 Files: TokyoDebt_*sec_*.mp4 and CyberpunkGoblin_*sec_*.mp4")
    logger.info("="*70)

if __name__ == "__main__":
    main()