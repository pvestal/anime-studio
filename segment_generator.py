#!/usr/bin/env python3
"""
Segment-based video generator - generates 1-second segments and merges them
Much faster than single long generation!
"""
import asyncio
import httpx
import subprocess
import os
import time
from pathlib import Path

async def generate_1_second_segment(prompt, segment_num, style="anime"):
    """Generate a 1-second video segment"""
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            "http://localhost:8328/api/anime/generate",
            json={
                "prompt": f"{prompt}, continuation part {segment_num}",
                "duration": 1,  # 1 second = 24 frames, FAST!
                "character": None,
                "style": style
            }
        )
        return response.json()

async def generate_segments_parallel(prompt, num_seconds=5, style="anime"):
    """Generate multiple 1-second segments in parallel"""
    print(f"Generating {num_seconds} segments in parallel...")
    
    # Create tasks for parallel generation
    tasks = []
    for i in range(num_seconds):
        task = generate_1_second_segment(prompt, i+1, style)
        tasks.append(task)
    
    # Wait for all segments
    results = await asyncio.gather(*tasks)
    print(f"All {num_seconds} segments queued!")
    return results

def wait_for_completion(job_ids, timeout=300):
    """Wait for all jobs to complete"""
    start_time = time.time()
    completed = []
    
    while len(completed) < len(job_ids) and (time.time() - start_time) < timeout:
        for job_id in job_ids:
            if job_id not in completed:
                # Check if job completed (simplified check)
                result = subprocess.run(
                    f"ls /mnt/1TB-storage/ComfyUI/output/*{job_id}*.mp4 2>/dev/null",
                    shell=True, capture_output=True, text=True
                )
                if result.stdout.strip():
                    completed.append(job_id)
                    print(f"Segment {job_id} completed!")
        
        if len(completed) < len(job_ids):
            time.sleep(5)
    
    return completed

def merge_segments(video_files, output_path):
    """Merge video segments using ffmpeg"""
    if not video_files:
        print("No video files to merge!")
        return None
    
    # Create concat list file
    list_file = "/tmp/concat_list.txt"
    with open(list_file, "w") as f:
        for video in video_files:
            f.write(f"file '{video}'\n")
    
    # Merge videos
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Successfully merged to {output_path}")
        return output_path
    else:
        print(f"Merge failed: {result.stderr}")
        return None

async def generate_5_second_video_fast(prompt, style="anime"):
    """Generate a 5-second video using segment approach"""
    print(f"Starting fast 5-second generation for: {prompt}")
    
    # Step 1: Generate segments in parallel
    job_results = await generate_segments_parallel(prompt, 5, style)
    job_ids = [r.get("comfyui_job_id") for r in job_results if "comfyui_job_id" in r]
    
    print(f"Waiting for {len(job_ids)} segments to complete...")
    
    # Step 2: Wait for segments to complete
    completed = wait_for_completion(job_ids, timeout=300)
    
    # Step 3: Find the generated files
    video_files = []
    for job_id in completed:
        result = subprocess.run(
            f"ls /mnt/1TB-storage/ComfyUI/output/*{job_id}*.mp4 2>/dev/null | head -1",
            shell=True, capture_output=True, text=True
        )
        if result.stdout.strip():
            video_files.append(result.stdout.strip())
    
    print(f"Found {len(video_files)} video segments")
    
    # Step 4: Merge segments
    if video_files:
        timestamp = int(time.time())
        output_path = f"/mnt/1TB-storage/ComfyUI/output/merged_5sec_{timestamp}.mp4"
        final_video = merge_segments(sorted(video_files), output_path)
        
        if final_video:
            # Check duration
            result = subprocess.run(
                f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {final_video}",
                shell=True, capture_output=True, text=True
            )
            duration = float(result.stdout.strip()) if result.stdout.strip() else 0
            
            return {
                "success": True,
                "output": final_video,
                "duration": duration,
                "segments": len(video_files)
            }
    
    return {"success": False, "error": "Failed to generate segments"}

if __name__ == "__main__":
    # Test with a simple prompt
    result = asyncio.run(generate_5_second_video_fast(
        "anime girl walking through cherry blossoms, dynamic movement",
        style="anime"
    ))
    print(f"Result: {result}")
