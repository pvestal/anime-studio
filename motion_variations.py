#!/usr/bin/env python3
"""Generate Tokyo characters with motion using AnimateDiff"""

import httpx
import asyncio
import time

async def generate_motion_variation(character_name: str, reference_image: str, prompt_text: str, seed: int, variation_num: int):
    """Generate animated variation with motion"""

    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "realisticVision_v51.safetensors"}
        },
        "2": {
            "class_type": "IPAdapterUnifiedLoader",
            "inputs": {
                "model": ["1", 0],
                "preset": "PLUS (high strength)"
            }
        },
        "3": {
            "class_type": "LoadImage",
            "inputs": {"image": reference_image}
        },
        "4": {
            "class_type": "IPAdapter",
            "inputs": {
                "weight": 0.5,
                "weight_type": "standard",
                "start_at": 0.0,
                "end_at": 1.0,
                "model": ["2", 0],
                "ipadapter": ["2", 1],
                "image": ["3", 0]
            }
        },
        "5": {
            "class_type": "ADE_AnimateDiffLoaderGen1",
            "inputs": {
                "model_name": "mm_sd_v15_v2.ckpt",
                "beta_schedule": "sqrt_linear (AnimateDiff)"
            }
        },
        "6": {
            "class_type": "ADE_AnimateDiffModelSettings",
            "inputs": {
                "min_motion_scale": 1.0,
                "max_motion_scale": 1.3,
                "context_options": "16 Context [LoopedUniform]",
                "sample_rate": 1,
                "model": ["5", 0]
            }
        },
        "7": {
            "class_type": "ADE_UseEvolvedSampling",
            "inputs": {
                "beta_schedule": "sqrt_linear (AnimateDiff)",
                "m_models": ["6", 0]
            }
        },
        "8": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt_text,
                "clip": ["1", 1]
            }
        },
        "9": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "static, still, frozen, small breasts, clothing, dressed, bad quality, deformed",
                "clip": ["1", 1]
            }
        },
        "10": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": 768,
                "height": 768,
                "batch_size": 24  # 24 frames for 1 second at 24fps
            }
        },
        "11": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 28,
                "cfg": 8,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["8", 0],
                "negative": ["9", 0],
                "latent_image": ["10", 0]
            }
        },
        "12": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["11", 0],
                "vae": ["1", 2]
            }
        },
        "13": {
            "class_type": "ADE_AnimateDiffCombine",
            "inputs": {
                "frame_rate": 12,
                "loop_count": 0,
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 19,
                "save_metadata": True,
                "images": ["12", 0],
                "filename_prefix": f"motion_{character_name}_var{variation_num}_{int(time.time())}"
            }
        }
    }

    async with httpx.AsyncClient(timeout=180) as client:  # Longer timeout for video
        try:
            response = await client.post(
                "http://localhost:8188/prompt",
                json={"prompt": workflow}
            )
            if response.status_code == 200:
                result = response.json()
                return result.get('prompt_id')
            else:
                print(f"❌ Failed: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

async def main():
    print("🎬 TOKYO CHARACTERS - MOTION VARIATIONS")
    print("=" * 50)
    print("Face consistency + motion + C+ cup sizes")
    print("=" * 50)

    # Motion variations
    motion_variations = [
        {
            "character": "sakura",
            "prompt": "Sakura with large C cup breasts, nude, swaying gently, breathing motion, bedroom setting",
            "seed": 1300
        },
        {
            "character": "sakura",
            "prompt": "Sakura with large D cup breasts, nude, stretching arms up slowly, graceful movement",
            "seed": 1301
        },
        {
            "character": "yuki",
            "prompt": "Yuki with large C cup breasts, nude, turning head slowly, gentle hair movement",
            "seed": 1400
        },
        {
            "character": "yuki",
            "prompt": "Yuki with large D cup breasts, nude, sitting and leaning forward slightly, subtle motion",
            "seed": 1401
        }
    ]

    all_results = []

    print("\\n🎬 GENERATING MOTION VIDEOS:")
    print("-" * 30)
    for i, var in enumerate(motion_variations, 1):
        print(f"[{i}/4] {var['character'].upper()}: {var['prompt'][:55]}...")
        prompt_id = await generate_motion_variation(
            var['character'],
            f"{var['character']}_reference.png",
            var['prompt'],
            var['seed'],
            i
        )
        if prompt_id:
            print(f"    ✅ {prompt_id[:8]}")
            all_results.append(prompt_id)
        await asyncio.sleep(3)  # Extra time between video generations

    print(f"\\n✅ Queued {len(all_results)}/4 motion videos")
    print("⏳ Waiting 180 seconds for video generation...")
    await asyncio.sleep(180)

    print("\\n📊 CHECKING RESULTS:")
    print("-" * 30)
    import subprocess

    # Check for videos
    video_result = subprocess.run("ls -lt /mnt/1TB-storage/ComfyUI/output/motion_*.mp4 2>/dev/null", shell=True, capture_output=True, text=True)
    if video_result.stdout:
        files = video_result.stdout.strip().split('\\n')
        print(f"✅ Generated {len(files)} motion videos:")
        for f in files:
            print(f"   {f}")
    else:
        print("⚠️ Videos still processing...")

    # Also check for any frame images
    frame_result = subprocess.run("ls -lt /mnt/1TB-storage/ComfyUI/output/motion_*_*.png 2>/dev/null | head -5", shell=True, capture_output=True, text=True)
    if frame_result.stdout:
        print("\\n📸 Frame samples found:")
        print(frame_result.stdout)

    print("\\n🎬 MOTION TYPES GENERATED:")
    print("Sakura: swaying, stretching movements")
    print("Yuki: head turning, leaning motions")
    print("\\nFiles: /mnt/1TB-storage/ComfyUI/output/motion_*.mp4")

if __name__ == "__main__":
    asyncio.run(main())