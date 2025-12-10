#!/usr/bin/env python3
"""
Fast 5-second video generator using 5x 1-second segments
"""
import subprocess
import time
import json

def generate_1_second(prompt, part_num):
    """Generate a single 1-second segment"""
    cmd = f'''curl -s -X POST http://localhost:8328/api/anime/generate \
        -H "Content-Type: application/json" \
        -d '{{"prompt": "{prompt} part {part_num}", "duration": 1}}' '''
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    try:
        response = json.loads(result.stdout)
        job_id = response.get("comfyui_job_id")
        print(f"Segment {part_num} queued: {job_id}")
        return job_id
    except:
        print(f"Failed to queue segment {part_num}")
        return None

def wait_and_find_videos(job_ids, max_wait=300):
    """Wait for videos to complete and find their paths"""
    print(f"Waiting for {len(job_ids)} segments to complete...")
    start = time.time()
    video_files = []
    
    while time.time() - start < max_wait:
        # Check ComfyUI history for completed jobs
        for job_id in job_ids:
            if job_id and job_id not in [v[0] for v in video_files]:
                # Look for output file
                cmd = f"ls /mnt/1TB-storage/ComfyUI/output/*.mp4 2>/dev/null | xargs -I {{}} sh -c 'echo {{}} && stat -c %Y {{}}' | paste -d' ' - - | sort -k2 -rn | head -20 | cut -d' ' -f1"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                files = result.stdout.strip().split('\n') if result.stdout.strip() else []
                
                # Check if any recent file matches our pattern
                for f in files[:10]:  # Check last 10 files
                    if f and job_id not in [v[0] for v in video_files]:
                        video_files.append((job_id, f))
                        print(f"Found segment {len(video_files)}: {f}")
                        break
        
        if len(video_files) >= len([j for j in job_ids if j]):
            break
        
        time.sleep(5)
        print(f"Still waiting... {len(video_files)}/{len(job_ids)} complete")
    
    return [v[1] for v in video_files]

def merge_videos(video_files, output_name="merged_5sec"):
    """Merge video files using ffmpeg"""
    if len(video_files) < 2:
        print("Not enough videos to merge")
        return None
    
    # Create concat file
    concat_file = "/tmp/concat.txt"
    with open(concat_file, "w") as f:
        for video in video_files[:5]:  # Max 5 segments
            f.write(f"file '{video}'\n")
    
    # Merge
    output = f"/mnt/1TB-storage/ComfyUI/output/{output_name}_{int(time.time())}.mp4"
    cmd = f"ffmpeg -y -f concat -safe 0 -i {concat_file} -c copy {output}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0:
        # Check duration
        cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {output}"
        duration_result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        duration = duration_result.stdout.strip()
        print(f"✅ Created 5-second video: {output} (duration: {duration}s)")
        return output
    else:
        print(f"Merge failed: {result.stderr}")
        return None

def generate_5_second_video_fast(prompt):
    """Main function to generate 5-second video quickly"""
    print(f"🚀 Fast 5-second generation: {prompt}")
    
    # Step 1: Queue all 5 segments
    job_ids = []
    for i in range(5):
        job_id = generate_1_second(prompt, i+1)
        job_ids.append(job_id)
        time.sleep(0.5)  # Small delay between submissions
    
    # Step 2: Wait for completion and find files
    video_files = wait_and_find_videos(job_ids)
    
    if len(video_files) < 2:
        # Fallback: just find the latest 5 videos
        print("Fallback: Finding latest videos...")
        cmd = "ls -t /mnt/1TB-storage/ComfyUI/output/*.mp4 2>/dev/null | head -5"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        video_files = result.stdout.strip().split('\n') if result.stdout.strip() else []
    
    # Step 3: Merge
    if video_files:
        return merge_videos(video_files)
    else:
        print("No videos found to merge")
        return None

if __name__ == "__main__":
    result = generate_5_second_video_fast("anime character running through city, dynamic action")
    if result:
        print(f"SUCCESS! Video saved to: {result}")
    else:
        print("Failed to generate video")
