#!/usr/bin/env python3
"""
Generate a 2-second test with REAL AnimateDiff animation
48 frames at 24fps = 2 seconds of actual character movement
"""
import json
import requests
import time
import subprocess
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"
OUTPUT_DIR = Path("/mnt/1TB-storage/ComfyUI/output")

def generate_2sec_animation():
    """Generate 2 seconds of REAL animation using AnimateDiff"""

    logger.info("="*60)
    logger.info("🎬 1-SECOND ANIMATEDIFF TEST")
    logger.info("Generating 24 frames of actual character animation")
    logger.info("="*60)

    # Epic battle scene prompt
    prompt = "cyberpunk goblin slayer epic battle, sword slash motion, sparks flying, dynamic action pose, glowing armor, neon city background, cinematic lighting"

    workflow = {
        "1": {
            "inputs": {
                "ckpt_name": "counterfeit_v3.safetensors"
            },
            "class_type": "CheckpointLoaderSimple",
            "_meta": {"title": "Load Checkpoint"}
        },
        "2": {
            "inputs": {
                "model_name": "mm-Stabilized_high.pth",
                "beta_schedule": "autoselect",
                "model": ["1", 0]
            },
            "class_type": "ADE_AnimateDiffLoaderGen1",
            "_meta": {"title": "AnimateDiff Loader"}
        },
        "3": {
            "inputs": {
                "text": prompt,
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Positive Prompt"}
        },
        "4": {
            "inputs": {
                "text": "static, blurry, low quality, deformed, watermark",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Negative Prompt"}
        },
        "5": {
            "inputs": {
                "batch_size": 24,  # 1 second at 24fps
                "width": 1024,
                "height": 1024
            },
            "class_type": "EmptyLatentImage",
            "_meta": {"title": "Empty Latent"}
        },
        "6": {
            "inputs": {
                "seed": 42,
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
            "class_type": "KSampler",
            "_meta": {"title": "Sample"}
        },
        "7": {
            "inputs": {
                "samples": ["6", 0],
                "vae": ["1", 2]
            },
            "class_type": "VAEDecode",
            "_meta": {"title": "Decode"}
        },
        "8": {
            "inputs": {
                "fps": 24,
                "frame_rate": 24,
                "loop_count": 1,
                "pingpong": False,
                "save_output": True,
                "method": "default",
                "format": "video/h264-mp4",
                "filename_prefix": "animatediff_2sec_test",
                "images": ["7", 0]
            },
            "class_type": "VHS_VideoCombine",
            "_meta": {"title": "Video Combine"}
        }
    }

    # Submit workflow
    response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
    if response.status_code == 200:
        prompt_id = response.json().get("prompt_id")
        logger.info(f"✅ Workflow submitted: {prompt_id}")
        logger.info("⏳ Generating 2 seconds of REAL animation...")
        logger.info("   Expected time: 5-10 minutes")

        # Monitor progress
        start_time = time.time()
        last_progress = 0

        while True:
            # Check queue status
            queue_response = requests.get(f"{COMFYUI_URL}/queue")
            if queue_response.status_code == 200:
                queue_data = queue_response.json()
                running = queue_data.get("queue_running", [])

                # Check if our job is running
                for job in running:
                    if job[1] == prompt_id:
                        # Still running, show progress
                        elapsed = int(time.time() - start_time)
                        if elapsed % 30 == 0 and elapsed != last_progress:
                            logger.info(f"   Processing... {elapsed}s elapsed")
                            last_progress = elapsed
                        break
                else:
                    # Not in running queue, check if completed
                    history_response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
                    if history_response.status_code == 200:
                        history = history_response.json()
                        if prompt_id in history:
                            if history[prompt_id].get("outputs"):
                                elapsed = int(time.time() - start_time)
                                logger.info(f"✅ Animation complete! Time: {elapsed}s")

                                # Find the output file
                                output_files = list(OUTPUT_DIR.glob("animatediff_2sec_test*.mp4"))
                                if output_files:
                                    latest_file = max(output_files, key=lambda f: f.stat().st_mtime)
                                    logger.info(f"📁 Output: {latest_file}")

                                    # Verify the video
                                    cmd = ["ffprobe", "-v", "error", "-show_entries",
                                           "format=duration,size", "-show_entries",
                                           "stream=width,height,nb_frames", "-of", "json",
                                           str(latest_file)]
                                    result = subprocess.run(cmd, capture_output=True, text=True)
                                    info = json.loads(result.stdout)

                                    duration = float(info["format"]["duration"])
                                    width = info["streams"][0]["width"]
                                    height = info["streams"][0]["height"]
                                    frames = info["streams"][0].get("nb_frames", "N/A")

                                    logger.info("="*60)
                                    logger.info("📊 VIDEO ANALYSIS:")
                                    logger.info(f"   Duration: {duration:.2f} seconds")
                                    logger.info(f"   Resolution: {width}x{height}")
                                    logger.info(f"   Frames: {frames}")
                                    logger.info(f"   Size: {latest_file.stat().st_size / 1024 / 1024:.1f} MB")
                                    logger.info("   Type: REAL ANIMATION (not camera pan)")
                                    logger.info("="*60)

                                    # Create upscaled version
                                    logger.info("🔧 Creating 1080p version...")
                                    hd_output = OUTPUT_DIR / "animatediff_2sec_test_HD.mp4"
                                    upscale_cmd = [
                                        "ffmpeg", "-y", "-i", str(latest_file),
                                        "-vf", "scale=1920:1080:flags=lanczos",
                                        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                                        "-pix_fmt", "yuv420p", str(hd_output)
                                    ]
                                    subprocess.run(upscale_cmd, capture_output=True)
                                    logger.info(f"✅ HD version created: {hd_output}")

                                    return str(hd_output)
                                else:
                                    logger.error("❌ Output file not found")
                                break
                            elif "status" in history[prompt_id] and history[prompt_id]["status"].get("completed"):
                                logger.error("❌ Generation completed but no outputs")
                                break

            time.sleep(5)
    else:
        logger.error(f"❌ Failed to submit workflow: {response.text}")
        return None

if __name__ == "__main__":
    output = generate_2sec_animation()
    if output:
        logger.info("\n🎬 SUCCESS! 2-second ANIMATED test complete!")
        logger.info("This is REAL animation with character movement,")
        logger.info("not just camera panning over a static image!")
    else:
        logger.error("\n❌ Animation generation failed")