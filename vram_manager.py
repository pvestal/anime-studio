#!/usr/bin/env python3
"""
VRAM Management for Anime Production
Ensures ComfyUI has enough VRAM for generation
"""
import subprocess
import json
import time
import psutil

def get_gpu_memory():
    """Get current GPU memory usage"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.free,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            total, free, used = map(int, result.stdout.strip().split(", "))
            return {"total": total, "free": free, "used": used}
    except Exception as e:
        print(f"Error getting GPU memory: {e}")
    return None

def clear_vram():
    """Clear VRAM by unloading models"""
    print("Clearing VRAM...")

    # Try to unload ComfyUI models
    try:
        import aiohttp
        import asyncio

        async def unload_models():
            async with aiohttp.ClientSession() as session:
                # ComfyUI free memory endpoint
                async with session.post("http://localhost:8188/free") as resp:
                    if resp.status == 200:
                        print("  ✓ ComfyUI models unloaded")
                    else:
                        print(f"  ✗ ComfyUI unload failed: {resp.status}")

        asyncio.run(unload_models())
    except Exception as e:
        print(f"  ✗ Failed to unload ComfyUI models: {e}")

    # Kill any stuck processes
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'ComfyUI' in cmdline and 'main.py' not in cmdline:
                print(f"  Killing stuck process: {proc.info['pid']}")
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    time.sleep(2)
    return get_gpu_memory()

def ensure_vram_available(required_mb=8000):
    """Ensure enough VRAM is available"""
    memory = get_gpu_memory()
    if not memory:
        return False

    print(f"Current VRAM: {memory['free']}MB free / {memory['total']}MB total")

    if memory['free'] < required_mb:
        print(f"Insufficient VRAM (need {required_mb}MB), clearing...")
        memory = clear_vram()
        if memory and memory['free'] >= required_mb:
            print(f"✓ VRAM cleared: {memory['free']}MB free")
            return True
        else:
            print(f"✗ Still insufficient VRAM: {memory['free']}MB free")
            return False

    print(f"✓ Sufficient VRAM available")
    return True

if __name__ == "__main__":
    ensure_vram_available()