#!/usr/bin/env python3
"""
Generate videos using YOUR WORKING workflow structure
ONLY: Tokyo debt desire and cyberpunk goblin slayer with photorealism
"""
import json
import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"

def create_working_workflow(duration_seconds, prompt_text, theme_name):
    """Use your exact working workflow structure"""

    # Calculate frames: 24 fps base, no interpolation for now
    base_frames = duration_seconds * 8  # Reduced for stability

    workflow = {
        "1": {
            "inputs": {
                "text": f"photorealistic, cinematic, 8k resolution, ultra detailed, {prompt_text}",
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "CLIP Text Encode (Prompt)"}
        },
        "2": {
            "inputs": {
                "text": "anime, cartoon, animated, unrealistic, low quality, blurry, ugly, distorted, static, still image, text, watermark",
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
                "batch_size": base_frames
            },
            "class_type": "EmptyLatentImage",
            "_meta": {"title": f"Empty Latent Image ({base_frames} frames)"}
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
                "frame_rate": 8,  # Match our frame generation rate
                "loop_count": 0,
                "filename_prefix": f"{theme_name}_{duration_seconds}sec",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 18,
                "save_metadata": True,
                "pingpong": False,
                "save_output": True
            },
            "class_type": "VHS_VideoCombine",
            "_meta": {"title": f"Video Combine - {duration_seconds} Second Video"}
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

def submit_and_wait(workflow, description, max_wait_minutes=10):
    """Submit and wait for completion"""
    try:
        response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
        response.raise_for_status()

        result = response.json()
        prompt_id = result["prompt_id"]

        logger.info(f"🎬 Submitted: {description} - ID: {prompt_id}")

        start_time = time.time()
        max_wait = max_wait_minutes * 60

        while time.time() - start_time < max_wait:
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
                logger.info(f"⏳ {description}: {elapsed:.0f}s / {max_wait}s")
                time.sleep(15)

            except Exception as e:
                logger.warning(f"Status check error: {e}")
                time.sleep(10)

        logger.error(f"❌ {description} timeout after {max_wait_minutes} minutes")
        return False

    except Exception as e:
        logger.error(f"❌ {description} submit failed: {e}")
        return False

def main():
    """Generate the video series"""

    logger.info("="*70)
    logger.info("🎬 GENERATING PHOTOREALISTIC VIDEOS")
    logger.info("THEMES: Tokyo debt desire + Cyberpunk goblin slayer")
    logger.info("DURATIONS: 2s, 5s, 10s, 15s")
    logger.info("="*70)

    # Video configurations
    videos = [
        # Tokyo Debt Desire series
        {
            "duration": 2,
            "theme": "TokyoDebt",
            "prompt": "desperate businessman counting yen bills in cramped Tokyo apartment, debt notices scattered on table, harsh fluorescent lighting, photorealistic"
        },
        {
            "duration": 5,
            "theme": "TokyoDebt",
            "prompt": "Tokyo financial district at night, businessman walking through neon-lit streets carrying briefcase, rain reflecting debt and desperation, cinematic realism"
        },
        {
            "duration": 10,
            "theme": "TokyoDebt",
            "prompt": "wide shot of Tokyo skyline transitioning from day to night, symbolizing mounting financial pressure and urban debt crisis, hyper realistic cinematography"
        },
        {
            "duration": 15,
            "theme": "TokyoDebt",
            "prompt": "emotional sequence of person reviewing bank statements and bills, close-ups of worried face and financial documents, dramatic lighting, photorealistic"
        },

        # Cyberpunk Goblin Slayer series
        {
            "duration": 2,
            "theme": "CyberpunkGoblin",
            "prompt": "armored cyberpunk warrior with glowing sword in dark Tokyo alley, hunting grotesque creatures, neon lights, photorealistic"
        },
        {
            "duration": 5,
            "theme": "CyberpunkGoblin",
            "prompt": "cyberpunk goblin slayer moving through industrial complex, high-tech armor gleaming, volumetric lighting through smoke, cinematic realism"
        },
        {
            "duration": 10,
            "theme": "CyberpunkGoblin",
            "prompt": "epic battle scene with cyber-enhanced goblin creatures in futuristic Tokyo setting, sparks and explosions, dramatic action, photorealistic"
        },
        {
            "duration": 15,
            "theme": "CyberpunkGoblin",
            "prompt": "extended combat sequence with armored warrior systematically hunting cyber-goblins through dystopian cityscape, dynamic camera movements, 8k detail"
        }
    ]

    success_count = 0

    for i, video in enumerate(videos, 1):
        logger.info(f"\n📽️ GENERATING VIDEO {i}/8")
        logger.info(f"Theme: {video['theme']}")
        logger.info(f"Duration: {video['duration']}s")
        logger.info(f"Prompt: {video['prompt'][:50]}...")

        workflow = create_working_workflow(
            video['duration'],
            video['prompt'],
            video['theme']
        )

        description = f"{video['theme']} {video['duration']}s"
        max_wait = max(video['duration'] * 2, 5)  # At least 5 min, or 2x duration

        if submit_and_wait(workflow, description, max_wait):
            success_count += 1
            logger.info(f"✅ SUCCESS: {description}")
        else:
            logger.error(f"❌ FAILED: {description}")

        # Pause between generations
        if i < len(videos):
            logger.info("⏸️ Pausing 30s before next generation...")
            time.sleep(30)

    logger.info("="*70)
    logger.info(f"🎯 FINAL RESULTS: {success_count}/{len(videos)} videos completed")
    logger.info("📁 Check: /mnt/1TB-storage/ComfyUI/output/")
    logger.info("Look for: TokyoDebt_*sec_*.mp4 and CyberpunkGoblin_*sec_*.mp4")
    logger.info("="*70)

if __name__ == "__main__":
    main()