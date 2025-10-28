#!/usr/bin/env python3
"""
Generate 5-second AnimateDiff animation using context windows
Creates real character animation with motion
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

def generate_5sec_animation():
    """Generate 5 seconds using multiple AnimateDiff segments"""

    logger.info("="*60)
    logger.info("🎬 5-SECOND ANIMATEDIFF TEST")
    logger.info("Generating real character animation")
    logger.info("Using 5x 24-frame segments (model limit)")
    logger.info("="*60)

    scenes = [
        "cyberpunk goblin slayer drawing glowing sword, dramatic pose, neon city",
        "goblin slayer sword slash, sparks flying, dynamic action",
        "cyberpunk battle scene, goblin slayer versus robot goblins",
        "goblin slayer jumping attack, explosions background",
        "goblin slayer victory pose, destroyed robots, smoke rising"
    ]

    prompt_ids = []

    for i, scene in enumerate(scenes):
        logger.info(f"\n📽️ Queuing segment {i+1}/5: {scene[:40]}...")

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
                    "text": scene,
                    "clip": ["1", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "4": {
                "inputs": {
                    "text": "static, blurry, low quality, deformed",
                    "clip": ["1", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "5": {
                "inputs": {
                    "batch_size": 24,
                    "width": 512,
                    "height": 512
                },
                "class_type": "EmptyLatentImage"
            },
            "6": {
                "inputs": {
                    "seed": 42 + i * 100,
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
                    "fps": 24,
                    "frame_rate": 24,
                    "loop_count": 1,
                    "pingpong": False,
                    "save_output": True,
                    "method": "default",
                    "format": "video/h264-mp4",
                    "filename_prefix": f"animatediff_5sec_seg{i:02d}",
                    "images": ["7", 0]
                },
                "class_type": "VHS_VideoCombine"
            }
        }

        response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
        if response.status_code == 200:
            prompt_id = response.json().get("prompt_id")
            prompt_ids.append((prompt_id, i))
            logger.info(f"   ✅ Segment {i+1} queued: {prompt_id[:8]}...")
            time.sleep(2)  # Small delay between submissions

    # Monitor all segments
    logger.info(f"\n⏳ Generating {len(prompt_ids)} segments...")
    start_time = time.time()
    completed = []

    while len(completed) < len(prompt_ids):
        for prompt_id, seg_num in prompt_ids:
            if prompt_id not in [c[0] for c in completed]:
                response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
                if response.status_code == 200:
                    history = response.json()
                    if prompt_id in history and history[prompt_id].get("outputs"):
                        completed.append((prompt_id, seg_num))
                        elapsed = int(time.time() - start_time)
                        logger.info(f"✓ Segment {seg_num+1} complete ({elapsed}s)")

        if len(completed) < len(prompt_ids):
            time.sleep(10)

    # Combine segments into 5-second video
    logger.info("\n🎬 Combining segments into 5-second video...")

    segment_files = []
    for i in range(5):
        files = list(OUTPUT_DIR.glob(f"animatediff_5sec_seg{i:02d}*.mp4"))
        if files:
            segment_files.append(sorted(files)[-1])  # Get latest

    if len(segment_files) == 5:
        # Create file list for concatenation
        with open("/tmp/segments_5sec.txt", "w") as f:
            for seg in segment_files:
                f.write(f"file '{seg}'\n")

        # Concatenate and upscale
        final_output = OUTPUT_DIR / "animatediff_5sec_FINAL.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", "/tmp/segments_5sec.txt",
            "-vf", "scale=1920:1080:flags=lanczos",
            "-c:v", "libx264",
            "-preset", "slow",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            str(final_output)
        ]

        result = subprocess.run(cmd, capture_output=True)

        if result.returncode == 0:
            # Verify duration
            probe_cmd = ["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "json", str(final_output)]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
            duration = json.loads(probe_result.stdout)["format"]["duration"]

            logger.info("="*60)
            logger.info("✅ SUCCESS! 5-second AnimateDiff video created!")
            logger.info(f"📁 Output: {final_output}")
            logger.info(f"⏱️ Duration: {float(duration):.1f} seconds")
            logger.info("🎬 Type: REAL character animation (not camera pans)")
            logger.info("="*60)
            return str(final_output)
        else:
            logger.error(f"FFmpeg error: {result.stderr.decode()}")
    else:
        logger.error(f"Only found {len(segment_files)} segments")

    return None

if __name__ == "__main__":
    output = generate_5sec_animation()
    if output:
        logger.info("\n🚀 Next: Run test_animatediff_10sec.py for 10-second test")