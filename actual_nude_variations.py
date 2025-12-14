#!/usr/bin/env python3
"""Generate ACTUAL nude female characters with different poses and scenes"""

import httpx
import asyncio
import time

async def generate_variation(prompt_text: str, seed: int, var_number: int, character: str):
    """Generate actual nude variation with corrected prompts"""

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
                "weight": 0.7,
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
                "text": "bad quality, deformed, different person, different face, lowres",
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
                "steps": 28,
                "cfg": 9,
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
                "filename_prefix": f"actual_nude_{character}_{var_number}_{int(time.time())}",
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
    print("🎯 ACTUAL NUDE VARIATIONS - CORRECTED PROMPTS")
    print("=" * 60)
    print("Stronger nude prompts with varied scenes and poses")
    print("Reference: yuki_var_1765508404_00001_.png")
    print("=" * 60)

    # Stronger nude prompts with explicit scene variations
    variations = [
        {
            "prompt": "japanese woman completely naked, nude, no clothes, full body, standing arms up pose, luxury bedroom, dramatic lighting, photorealistic",
            "seed": 400,
            "character": "A",
            "scene": "bedroom"
        },
        {
            "prompt": "japanese woman completely naked, nude, no clothes, full body, sitting cross-legged pose, japanese onsen hot springs, steam, natural lighting",
            "seed": 401,
            "character": "A",
            "scene": "onsen"
        },
        {
            "prompt": "japanese woman completely naked, nude, no clothes, full body, reclining pose, modern bathroom marble tiles, soft morning light",
            "seed": 402,
            "character": "A",
            "scene": "bathroom"
        },
        {
            "prompt": "japanese woman completely naked, nude, no clothes, full body, dancing pose arms outstretched, moonlit garden, artistic shadows",
            "seed": 403,
            "character": "A",
            "scene": "garden"
        },
        {
            "prompt": "japanese woman completely naked, nude, no clothes, full body, yoga meditation pose, zen temple interior, golden hour lighting",
            "seed": 404,
            "character": "A",
            "scene": "temple"
        },
        {
            "prompt": "japanese woman completely naked, nude, no clothes, full body, elegant standing pose, penthouse window city view, sunset glow",
            "seed": 500,
            "character": "B",
            "scene": "penthouse"
        },
        {
            "prompt": "japanese woman completely naked, nude, no clothes, full body, stretching pose, yoga studio mirrors, bright daylight",
            "seed": 501,
            "character": "B",
            "scene": "studio"
        },
        {
            "prompt": "japanese woman completely naked, nude, no clothes, full body, lying on side pose, beach at sunset, ocean waves, golden light",
            "seed": 502,
            "character": "B",
            "scene": "beach"
        },
        {
            "prompt": "japanese woman completely naked, nude, no clothes, full body, graceful pose by fireplace, cozy cabin interior, warm lighting",
            "seed": 503,
            "character": "B",
            "scene": "cabin"
        },
        {
            "prompt": "japanese woman completely naked, nude, no clothes, full body, artistic pose, photography studio, professional lighting setup",
            "seed": 504,
            "character": "B",
            "scene": "studio"
        }
    ]

    results = []
    print("\\n📸 GENERATING ACTUAL NUDE VARIATIONS:")
    print("-" * 40)

    for i, var in enumerate(variations, 1):
        print(f"\\n[{i}/10] Character {var['character']} - {var['scene']}: {var['prompt'][:60]}...")

        prompt_id = await generate_variation(var['prompt'], var['seed'], i, var['character'])

        if prompt_id:
            print(f"    ✅ Queued: {prompt_id[:8]}...")
            results.append(prompt_id)
        else:
            print(f"    ❌ Failed to queue")

        await asyncio.sleep(3)

    print("\\n" + "=" * 60)
    print(f"✅ Successfully queued {len(results)}/10 nude variations")
    print("⏳ Waiting 150 seconds for generation...")

    await asyncio.sleep(150)

    print("\\n📊 CHECKING RESULTS:")
    print("-" * 40)

    # Check for generated files
    import subprocess
    result = subprocess.run(
        "ls -lt /mnt/1TB-storage/ComfyUI/output/actual_nude_*.png 2>/dev/null | head -15",
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
    print("🎯 SCENE VARIATIONS GENERATED:")
    print("Character A: bedroom, onsen, bathroom, garden, temple")
    print("Character B: penthouse, studio, beach, cabin, photography")
    print("\\nPOSE VARIATIONS:")
    print("Standing, sitting, reclining, dancing, meditation, stretching, lying, graceful")
    print("\\nImages saved to: /mnt/1TB-storage/ComfyUI/output/actual_nude_*.png")

if __name__ == "__main__":
    asyncio.run(main())