#!/usr/bin/env python3
"""
Generate videos using YOUR actual projects ONLY
Project 1: Tokyo Debt Desire (photorealistic)
Project 2: Cyberpunk Goblin Slayer (photorealistic)
Duration: 2s, 5s, 10s, 15s
"""
import json
import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"

def create_short_workflow(frames, prompt_text, project_name):
    """Create workflow for short videos that actually work"""

    workflow = {
        "1": {
            "inputs": {
                "text": f"photorealistic, cinematic, 8k resolution, {prompt_text}",
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "2": {
            "inputs": {
                "text": "anime, cartoon, low quality, blurry, distorted",
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "3": {
            "inputs": {
                "seed": int(time.time()) % 2147483647,
                "steps": 15,  # Reduced for speed
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
                "filename_prefix": f"PROJECT_{project_name}_{frames}frames",
                "format": "video/h264-mp4",
                "crf": 20,
                "save_metadata": True
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

    return workflow

def generate_video(frames, prompt, project_name, duration_seconds):
    """Generate single video"""

    logger.info(f"🎬 GENERATING: {project_name} - {duration_seconds}s ({frames} frames)")
    logger.info(f"Prompt: {prompt}")

    workflow = create_short_workflow(frames, prompt, project_name)

    try:
        # Submit
        response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]

        logger.info(f"✅ Submitted - ID: {prompt_id}")

        # Wait max 5 minutes
        start_time = time.time()
        max_wait = 300

        while time.time() - start_time < max_wait:
            try:
                response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
                history = response.json()

                if prompt_id in history:
                    status = history[prompt_id]["status"]
                    if status.get("completed", False):
                        gen_time = time.time() - start_time
                        logger.info(f"✅ COMPLETED in {gen_time:.1f}s")
                        return True
                    elif "error" in status:
                        logger.error(f"❌ FAILED: {status['error']}")
                        return False

                elapsed = time.time() - start_time
                if elapsed % 30 == 0:  # Log every 30s
                    logger.info(f"⏳ {elapsed:.0f}s / {max_wait}s")
                time.sleep(5)

            except Exception as e:
                logger.warning(f"Status check error: {e}")
                time.sleep(5)

        logger.error(f"❌ TIMEOUT after {max_wait}s")
        return False

    except Exception as e:
        logger.error(f"❌ Submit failed: {e}")
        return False

def main():
    """Generate videos for YOUR projects"""

    logger.info("="*60)
    logger.info("🎬 GENERATING VIDEOS FOR YOUR PROJECTS")
    logger.info("="*60)

    # YOUR ACTUAL PROJECTS WITH PHOTOREALISTIC PROMPTS
    projects = [
        {
            "name": "TokyoDebtDesire",
            "prompts": {
                2: "businessman in cramped Tokyo apartment counting yen bills, debt notices on table, harsh lighting",
                5: "Tokyo financial district at night, businessman walking through neon streets, rain and desperation",
                10: "wide cinematic shot of Tokyo skyline, dawn light symbolizing financial pressure and debt crisis",
                15: "emotional close-up sequence of person reviewing bank statements, worried expressions, dramatic shadows"
            }
        },
        {
            "name": "CyberpunkGoblinSlayer",
            "prompts": {
                2: "armored cyberpunk warrior with glowing sword in dark Tokyo alley, hunting creatures",
                5: "cyber-enhanced goblin slayer moving through industrial complex, high-tech armor gleaming",
                10: "epic battle with cyber goblins in futuristic Tokyo, sparks and explosions, dynamic action",
                15: "extended combat sequence, warrior hunting through dystopian cityscape, volumetric lighting"
            }
        }
    ]

    durations = [2, 5, 10, 15]
    success_count = 0
    total_videos = len(projects) * len(durations)

    video_num = 1
    for project in projects:
        for duration in durations:
            frames = duration * 6  # 6 fps for stability
            prompt = project["prompts"][duration]

            logger.info(f"\n📽️ VIDEO {video_num}/{total_videos}")

            if generate_video(frames, prompt, project["name"], duration):
                success_count += 1
                logger.info(f"✅ SUCCESS: {project['name']} {duration}s")
            else:
                logger.error(f"❌ FAILED: {project['name']} {duration}s")

            video_num += 1

            # Short pause between videos
            if video_num <= total_videos:
                logger.info("⏸️ Pausing 10s...")
                time.sleep(10)

    logger.info("="*60)
    logger.info(f"🎯 RESULTS: {success_count}/{total_videos} videos completed")
    logger.info("📁 Check: /mnt/1TB-storage/ComfyUI/output/")
    logger.info("Files: PROJECT_TokyoDebtDesire_*frames_*.mp4")
    logger.info("       PROJECT_CyberpunkGoblinSlayer_*frames_*.mp4")
    logger.info("="*60)

if __name__ == "__main__":
    main()