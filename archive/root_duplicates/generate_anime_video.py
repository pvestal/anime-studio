#!/usr/bin/env python3
"""
Anime Video Generation Pipeline
Batch generates frames via ComfyUI and creates quality videos
"""
import json
import requests
import time
import uuid
import subprocess
import os
from pathlib import Path

COMFYUI_API = "http://127.0.0.1:8188"
OUTPUT_DIR = "***REMOVED***/ComfyUI-Working/output"
VIDEO_DIR = "***REMOVED***"

def generate_frames(base_prompt, num_frames=30, model="animagine_xl_3.1.safetensors"):
    """Generate frames using ComfyUI API"""
    
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": model}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": base_prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "worst quality, low quality", "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {
            "seed": 42, "steps": 20, "cfg": 7.0, "sampler_name": "euler",
            "scheduler": "normal", "denoise": 1.0, "model": ["1", 0],
            "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]
        }},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "anime_frame", "images": ["6", 0]}}
    }
    
    frames = []
    for i in range(num_frames):
        workflow["5"]["inputs"]["seed"] = 42 + i
        workflow["7"]["inputs"]["filename_prefix"] = f"anime_{uuid.uuid4().hex[:8]}"
        
        response = requests.post(f"{COMFYUI_API}/prompt", json={"prompt": workflow})
        if response.status_code == 200:
            prompt_id = response.json().get("prompt_id")
            frames.append(prompt_id)
            print(f"Frame {i+1}/{num_frames} queued")
            time.sleep(3)  # Wait between generations
    
    return frames

def create_video(pattern, output_name, duration=30):
    """Create video from frames using FFmpeg"""
    
    # Calculate framerate for target duration
    frame_count = len(list(Path(OUTPUT_DIR).glob(pattern)))
    fps = max(1, frame_count / duration)
    
    cmd = [
        "ffmpeg", "-y",
        "-pattern_type", "glob",
        "-i", f"{OUTPUT_DIR}/{pattern}",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-vf", f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps={fps}",
        "-pix_fmt", "yuv420p",
        f"{VIDEO_DIR}/{output_name}.mp4"
    ]
    
    subprocess.run(cmd, check=True)
    print(f"Video created: {VIDEO_DIR}/{output_name}.mp4")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python generate_anime_video.py '<prompt>' [num_frames] [duration]")
        sys.exit(1)
    
    prompt = sys.argv[1]
    num_frames = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    duration = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    
    print(f"Generating {num_frames} frames for: {prompt}")
    frames = generate_frames(prompt, num_frames)
    
    print(f"Waiting for generation to complete...")
    time.sleep(num_frames * 3 + 10)
    
    print(f"Creating {duration} second video...")
    create_video("anime_*.png", f"anime_video_{uuid.uuid4().hex[:8]}", duration)
