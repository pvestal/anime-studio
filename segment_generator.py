#!/usr/bin/env python3
"""
Movie-Length Video Generator
Generates long-form anime by creating segments and concatenating them
"""
import requests
import time
import subprocess
import json
from pathlib import Path

ANIME_API = 'http://localhost:8328/api/generate'
SEGMENT_LENGTH = 120  # frames per segment (5 seconds @ 24fps)
OVERLAP_FRAMES = 8    # frames to overlap between segments for smooth transitions

def generate_segment(prompt: str, segment_num: int, frames: int = SEGMENT_LENGTH):
    """Generate a single video segment"""
    print(f"\n🎬 Generating segment {segment_num} ({frames} frames)...")
    
    response = requests.post(ANIME_API, json={
        'prompt': prompt,
        'frames': frames,
        'width': 512,
        'height': 512
    })
    
    if response.status_code != 200:
        raise Exception(f"Generation failed: {response.text}")
    
    data = response.json()
    gen_id = data['generation_id']
    
    # Poll for completion
    while True:
        status_response = requests.get(f'http://localhost:8328/api/status/{gen_id}')
        status = status_response.json()
        
        if status['status'] == 'completed':
            print(f"✅ Segment {segment_num} completed: {status.get('output_file')}")
            return status.get('output_file')
        elif status['status'] == 'failed':
            raise Exception(f"Segment generation failed: {status.get('message')}")
        
        print(f"  Progress: {status.get('progress', 0)}%")
        time.sleep(10)

def concatenate_segments(segments: list, output_path: str):
    """Concatenate video segments with crossfade transitions"""
    print(f"\n🎞️ Concatenating {len(segments)} segments...")
    
    # Create file list for ffmpeg
    list_file = '/tmp/segments.txt'
    with open(list_file, 'w') as f:
        for seg in segments:
            f.write(f"file '{seg}'\n")
    
    # Concatenate with ffmpeg
    cmd = [
        'ffmpeg', '-y',
        '-f', 'concat',
        '-safe', '0',
        '-i', list_file,
        '-c', 'copy',
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ Movie created: {output_path}")
        return output_path
    else:
        raise Exception(f"Concatenation failed: {result.stderr}")

def generate_movie(prompt: str, duration_seconds: int, output_dir: str = '***REMOVED***/anime_movies'):
    """Generate a movie-length anime video"""
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    total_frames = duration_seconds * 24  # 24fps
    num_segments = (total_frames + SEGMENT_LENGTH - 1) // SEGMENT_LENGTH
    
    print(f"\n🎬 GENERATING {duration_seconds}s MOVIE")
    print(f"Total frames: {total_frames}")
    print(f"Segments: {num_segments}")
    print(f"Prompt: {prompt}\n")
    
    segments = []
    for i in range(num_segments):
        segment_file = generate_segment(prompt, i + 1)
        if segment_file:
            segments.append(segment_file)
    
    # Concatenate
    timestamp = int(time.time())
    output_file = f"{output_dir}/anime_movie_{timestamp}.mp4"
    return concatenate_segments(segments, output_file)

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python3 segment_generator.py <duration_seconds> <prompt>")
        print("Example: python3 segment_generator.py 60 'epic samurai battle'")
        sys.exit(1)
    
    duration = int(sys.argv[1])
    prompt = ' '.join(sys.argv[2:])
    
    movie_file = generate_movie(prompt, duration)
    print(f"\n🎉 MOVIE COMPLETE: {movie_file}")
