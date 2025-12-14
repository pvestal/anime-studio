#!/usr/bin/env python3
"""Generate nude female characters with different poses and scene variations"""

import httpx
import asyncio
import time

async def generate_variation(prompt_text: str, seed: int, var_number: int, character: str):
    """Generate a nude variation using the working IPAdapter setup"""

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
                "text": "clothing, dressed, covered, ugly, deformed, bad quality, different person, different face",
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
                "steps": 25,
                "cfg": 8,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
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
                "filename_prefix": f"nude_{character}_{var_number}_{int(time.time())}",
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
    print("🎯 NUDE CHARACTER VARIATIONS - DIFFERENT POSES & SCENES")
    print("=" * 60)
    print("Two different female characters with pose and scene variations")
    print("Reference: yuki_var_1765508404_00001_.png")
    print("=" * 60)

    # Character A variations - Different poses and scenes
    character_a_variations = [
        {
            "prompt": "beautiful japanese woman, nude, standing pose with arms raised, in bedroom with soft lighting",
            "seed": 200,
            "character": "A"
        },
        {
            "prompt": "beautiful japanese woman, nude, sitting pose on chair, in artist studio with natural light",
            "seed": 201,
            "character": "A"
        },
        {
            "prompt": "beautiful japanese woman, nude, reclining pose on bed, in luxury hotel room",
            "seed": 202,
            "character": "A"
        },
        {
            "prompt": "beautiful japanese woman, nude, kneeling pose, in japanese onsen hot spring setting",
            "seed": 203,
            "character": "A"
        },
        {
            "prompt": "beautiful japanese woman, nude, dancing pose, in moonlit garden setting",
            "seed": 204,
            "character": "A"
        },
    ]

    # Character B variations - Different poses and scenes
    character_b_variations = [
        {
            "prompt": "beautiful japanese woman, nude, elegant standing pose, in modern bathroom with marble",
            "seed": 300,
            "character": "B"
        },
        {
            "prompt": "beautiful japanese woman, nude, stretching pose, in yoga studio with mirrors",
            "seed": 301,
            "character": "B"
        },
        {
            "prompt": "beautiful japanese woman, nude, lying pose on side, on beach at sunset",
            "seed": 302,
            "character": "B"
        },
        {
            "prompt": "beautiful japanese woman, nude, sitting meditation pose, in zen temple",
            "seed": 303,
            "character": "B"
        },
        {
            "prompt": "beautiful japanese woman, nude, graceful pose by window, in penthouse apartment",
            "seed": 304,
            "character": "B"
        }
    ]

    all_variations = character_a_variations + character_b_variations
    results = []

    print("\\n📸 GENERATING VARIATIONS:")
    print("-" * 40)

    for i, var in enumerate(all_variations, 1):
        print(f"\\n[{i}/10] Character {var['character']}: {var['prompt'][:50]}...")

        prompt_id = await generate_variation(var['prompt'], var['seed'], i, var['character'])

        if prompt_id:
            print(f"    ✅ Queued: {prompt_id[:8]}...")
            results.append(prompt_id)
        else:
            print(f"    ❌ Failed to queue")

        await asyncio.sleep(3)  # Give ComfyUI time between requests

    print("\\n" + "=" * 60)
    print(f"✅ Successfully queued {len(results)}/10 variations")
    print("⏳ Waiting 120 seconds for generation...")

    await asyncio.sleep(120)

    print("\\n📊 CHECKING RESULTS:")
    print("-" * 40)

    # Check for generated files
    import subprocess
    result = subprocess.run(
        "ls -lt /mnt/1TB-storage/ComfyUI/output/nude_*.png 2>/dev/null | head -15",
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
    print("🎯 ANALYSIS POINTS:")
    print("1. Character A face consistency across 5 poses/scenes")
    print("2. Character B face consistency across 5 poses/scenes")
    print("3. Clear distinction between Character A and B")
    print("4. Pose variation success")
    print("5. Scene/background variation")
    print("6. Artistic nude quality and realism")
    print("\\nImages saved to: /mnt/1TB-storage/ComfyUI/output/nude_*.png")

if __name__ == "__main__":
    asyncio.run(main())