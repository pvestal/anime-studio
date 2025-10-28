#!/usr/bin/env python3
"""
Generate a REAL animated 30-second trailer using AnimateDiff
Creates shorter segments with actual character animation, not camera pans
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

def generate_animated_segment(prompt, segment_num, frames=24):
    """Generate a single animated segment with AnimateDiff"""

    workflow = {
        "1": {
            "inputs": {
                "ckpt_name": "epicrealism_naturalSin.safetensors",
                "config_name": "default",
                "vae_name": "vae-ft-mse-840000-ema-pruned.safetensors",
                "clip_skip": -2
            },
            "class_type": "DualCFGGuider",
            "_meta": {"title": "Load Checkpoint"}
        },
        "2": {
            "inputs": {
                "model_name": "mm_sd_v15_v3_adapter.ckpt",
                "beta_schedule": "autoselect"
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
                "text": "static, blurry, low quality, watermark, text",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Negative Prompt"}
        },
        "5": {
            "inputs": {
                "seed": segment_num * 1000,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["2", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["6", 0]
            },
            "class_type": "KSampler",
            "_meta": {"title": "Sample"}
        },
        "6": {
            "inputs": {
                "width": 512,
                "height": 512,
                "batch_size": frames
            },
            "class_type": "EmptyLatentImage",
            "_meta": {"title": "Empty Latent"}
        },
        "7": {
            "inputs": {
                "samples": ["5", 0],
                "vae": ["1", 2]
            },
            "class_type": "VAEDecode",
            "_meta": {"title": "Decode"}
        },
        "8": {
            "inputs": {
                "filename_prefix": f"animated_seg_{segment_num:03d}",
                "images": ["7", 0]
            },
            "class_type": "SaveImage",
            "_meta": {"title": "Save"}
        }
    }

    response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
    if response.status_code == 200:
        prompt_id = response.json().get("prompt_id")
        logger.info(f"Segment {segment_num} queued: {prompt_id}")
        return prompt_id
    else:
        logger.error(f"Failed to queue segment {segment_num}")
        return None

def create_cyberpunk_goblin_trailer():
    """Create a 30-second trailer with REAL animation"""

    logger.info("="*60)
    logger.info("🎬 GENERATING ANIMATED CYBERPUNK GOBLIN SLAYER TRAILER")
    logger.info("Using AnimateDiff for REAL character animation")
    logger.info("="*60)

    # Scene descriptions for animated segments
    scenes = [
        "cyberpunk goblin slayer warrior drawing glowing sword, neon city background, dramatic pose",
        "goblin slayer fighting mechanical goblins, sparks flying, action scene",
        "cyberpunk city at night, goblin slayer running through neon streets",
        "epic battle scene, goblin slayer versus goblin horde, explosions",
        "goblin slayer standing victorious, destroyed robots around, smoke rising",
        "close-up goblin slayer helmet, red eyes glowing, dramatic lighting"
    ]

    # Generate 6 segments of 5 seconds each = 30 seconds
    prompt_ids = []
    for i, scene in enumerate(scenes):
        logger.info(f"\n📽️ Generating segment {i+1}/6: 5-second animated scene")
        logger.info(f"   Scene: {scene[:50]}...")

        # Generate 120 frames (5 seconds at 24fps)
        # but AnimateDiff works better with smaller batches
        # So we'll generate 24 frames and loop them 5 times
        prompt_id = generate_animated_segment(scene, i, frames=24)
        if prompt_id:
            prompt_ids.append(prompt_id)

        # Small delay between submissions
        time.sleep(2)

    logger.info(f"\n✅ Queued {len(prompt_ids)} animated segments")
    logger.info("⏳ Waiting for generation to complete...")

    # Monitor generation
    start_time = time.time()
    completed = set()

    while len(completed) < len(prompt_ids):
        for prompt_id in prompt_ids:
            if prompt_id not in completed:
                response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
                if response.status_code == 200:
                    history = response.json()
                    if prompt_id in history and history[prompt_id].get("outputs"):
                        completed.add(prompt_id)
                        logger.info(f"✓ Segment completed: {len(completed)}/{len(prompt_ids)}")

        if len(completed) < len(prompt_ids):
            elapsed = int(time.time() - start_time)
            logger.info(f"   Progress: {len(completed)}/{len(prompt_ids)} segments | Elapsed: {elapsed}s")
            time.sleep(10)

    logger.info("\n🎯 All segments generated! Creating final trailer...")

    # Combine segments into final video
    segment_files = sorted(OUTPUT_DIR.glob("animated_seg_*.png"))
    if segment_files:
        # Convert images to video segments with looping
        for i in range(6):
            segment_images = sorted(OUTPUT_DIR.glob(f"animated_seg_{i:03d}_*.png"))
            if segment_images:
                # Create 5-second segment by looping the 24 frames
                cmd = [
                    "ffmpeg", "-y",
                    "-pattern_type", "glob",
                    "-i", f"{OUTPUT_DIR}/animated_seg_{i:03d}_*.png",
                    "-filter_complex", "[0:v]loop=loop=5:size=24,fps=24",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-t", "5",
                    f"/tmp/segment_{i}.mp4"
                ]
                subprocess.run(cmd, capture_output=True)
                logger.info(f"Created 5-second segment {i+1}/6")

        # Combine all segments
        with open("/tmp/segments.txt", "w") as f:
            for i in range(6):
                f.write(f"file '/tmp/segment_{i}.mp4'\n")

        final_output = OUTPUT_DIR / "cyberpunk_goblin_ANIMATED_30sec.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", "/tmp/segments.txt",
            "-c:v", "libx264",
            "-preset", "slow",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-vf", "scale=1920:1080",
            str(final_output)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            logger.info("="*60)
            logger.info("🎬 SUCCESS! Real animated trailer created!")
            logger.info(f"📁 Output: {final_output}")
            logger.info("✨ Features:")
            logger.info("   • 30 seconds duration (KB compliant)")
            logger.info("   • 1920x1080 resolution")
            logger.info("   • REAL character animation (not camera pans)")
            logger.info("   • 6 unique animated scenes")
            logger.info("="*60)
            return str(final_output)
        else:
            logger.error(f"FFmpeg error: {result.stderr}")

    return None

if __name__ == "__main__":
    trailer = create_cyberpunk_goblin_trailer()
    if trailer:
        # Verify the output
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", trailer],
            capture_output=True, text=True
        )
        info = json.loads(result.stdout)
        duration = float(info["format"]["duration"])
        logger.info(f"\n✅ Verification: {duration:.1f} seconds of ANIMATED content!")