#!/usr/bin/env python3
"""Generate 10 character variations with different clothing and poses using working IPAdapter workflow"""

import httpx
import asyncio
import time

async def generate_variation(prompt_text: str, seed: int, var_number: int):
    """Generate a single variation using the working IPAdapter setup"""

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
            "inputs": {"image": "yuki_var_1765508404_00001_.png"}
        },
        "4": {
            "class_type": "IPAdapter",
            "inputs": {
                "weight": 0.8,
                "weight_type": "standard",
                "start_at": 0.0,
                "end_at": 1.0,
                "model": ["2", 0],
                "ipadapter": ["2", 1],
                "image": ["3", 0]
            }
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt_text,
                "clip": ["1", 1]
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "ugly, deformed, bad quality, different person, different face",
                "clip": ["1", 1]
            }
        },
        "7": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 768, "batch_size": 1}
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["5", 0],
                "negative": ["6", 0],
                "latent_image": ["7", 0]
            }
        },
        "9": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["8", 0],
                "vae": ["1", 2]
            }
        },
        "10": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": f"yuki_10var_{var_number}_{int(time.time())}",
                "images": ["9", 0]
            }
        }
    }

    async with httpx.AsyncClient(timeout=60) as client:
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
    print("🎯 10 CHARACTER VARIATIONS - CLOTHING & POSES")
    print("=" * 60)
    print("Using working IPAdapterUnifiedLoader + IPAdapter workflow")
    print("Reference: yuki_var_1765508404_00001_.png")
    print("=" * 60)

    # 10 variations with different clothing and poses
    variations = [
        {
            "prompt": "beautiful japanese woman wearing elegant red evening dress, standing pose, in luxury restaurant",
            "seed": 100
        },
        {
            "prompt": "beautiful japanese woman wearing blue business suit, confident pose with arms crossed, in modern office",
            "seed": 101
        },
        {
            "prompt": "beautiful japanese woman wearing casual white t-shirt and jeans, sitting pose, in coffee shop",
            "seed": 102
        },
        {
            "prompt": "beautiful japanese woman wearing traditional kimono, graceful bowing pose, in japanese garden",
            "seed": 103
        },
        {
            "prompt": "beautiful japanese woman wearing black cocktail dress, elegant pose with hand on hip, at art gallery",
            "seed": 104
        },
        {
            "prompt": "beautiful japanese woman wearing yellow summer dress, twirling pose, in flower garden",
            "seed": 105
        },
        {
            "prompt": "beautiful japanese woman wearing leather jacket and pants, cool pose leaning on wall, urban street background",
            "seed": 106
        },
        {
            "prompt": "beautiful japanese woman wearing pink sweater, thoughtful pose with hand to chin, in library",
            "seed": 107
        },
        {
            "prompt": "beautiful japanese woman wearing white wedding dress, graceful pose with bouquet, in chapel",
            "seed": 108
        },
        {
            "prompt": "beautiful japanese woman wearing green hiking outfit, active pose stretching, mountain landscape background",
            "seed": 109
        }
    ]

    results = []
    print("\\n📸 GENERATING 10 VARIATIONS:")
    print("-" * 40)

    for i, var in enumerate(variations, 1):
        print(f"\\n[{i}/10] {var['prompt'][:50]}...")

        prompt_id = await generate_variation(var['prompt'], var['seed'], i)

        if prompt_id:
            print(f"    ✅ Queued: {prompt_id[:8]}...")
            results.append(prompt_id)
        else:
            print(f"    ❌ Failed to queue")

        await asyncio.sleep(2)  # Don't overwhelm ComfyUI

    print("\\n" + "=" * 60)
    print(f"✅ Successfully queued {len(results)}/10 variations")
    print("⏳ Waiting 90 seconds for generation...")

    await asyncio.sleep(90)

    print("\\n📊 CHECKING RESULTS:")
    print("-" * 40)

    # Check for generated files
    import subprocess
    result = subprocess.run(
        "ls -lt /mnt/1TB-storage/ComfyUI/output/yuki_10var_*.png 2>/dev/null | head -15",
        shell=True,
        capture_output=True,
        text=True
    )

    if result.stdout:
        files = result.stdout.strip().split('\\n')
        print(f"✅ Found {len(files)} generated images:")
        for f in files[:10]:
            print(f"   {f}")
    else:
        print("⚠️ Images still processing - check output directory manually")

    print("\\n" + "=" * 60)
    print("🎯 CONSISTENCY ANALYSIS:")
    print("1. Face consistency across all 10 variations")
    print("2. Clothing variation success")
    print("3. Pose variation success")
    print("4. Background/setting variation")
    print("5. Overall quality and realism")
    print("\\nImages saved to: /mnt/1TB-storage/ComfyUI/output/yuki_10var_*.png")

if __name__ == "__main__":
    asyncio.run(main())