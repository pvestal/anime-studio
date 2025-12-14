#!/usr/bin/env python3
"""Generate variations of Tokyo anime characters with different clothes, poses, scenes"""

import httpx
import asyncio
import time

async def generate_character_variation(character_name: str, reference_image: str, prompt_text: str, seed: int, variation_num: int):
    """Generate variation while keeping character face consistent"""

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
                "weight": 0.9,  # High weight for face consistency
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
                "text": "bad quality, deformed, different face, different person, wrong character",
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
                "filename_prefix": f"tokyo_{character_name}_var{variation_num}_{int(time.time())}",
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
    print("🎯 TOKYO ANIME CHARACTER VARIATIONS")
    print("=" * 50)
    print("Face consistency + clothing/pose/scene variations")
    print("=" * 50)

    # Sakura variations
    sakura_variations = [
        {"prompt": "Sakura wearing red evening dress, elegant pose, luxury restaurant", "seed": 700},
        {"prompt": "Sakura wearing business suit, confident pose, modern office", "seed": 701},
        {"prompt": "Sakura wearing casual jeans and t-shirt, relaxed pose, coffee shop", "seed": 702},
        {"prompt": "Sakura wearing traditional kimono, graceful pose, japanese garden", "seed": 703},
        {"prompt": "Sakura wearing bikini, beach pose, tropical sunset", "seed": 704},
        {"prompt": "Sakura nude, artistic pose, bedroom with soft lighting", "seed": 705}
    ]

    # Yuki variations
    yuki_variations = [
        {"prompt": "Yuki wearing leather jacket, cool pose, urban street", "seed": 800},
        {"prompt": "Yuki wearing school uniform, studying pose, library", "seed": 801},
        {"prompt": "Yuki wearing sports outfit, athletic pose, gym", "seed": 802},
        {"prompt": "Yuki wearing winter coat, walking pose, snowy street", "seed": 803},
        {"prompt": "Yuki wearing sundress, dancing pose, flower field", "seed": 804},
        {"prompt": "Yuki nude, reclining pose, bathroom with marble", "seed": 805}
    ]

    all_results = []

    print("\\n📸 GENERATING SAKURA VARIATIONS:")
    print("-" * 30)
    for i, var in enumerate(sakura_variations, 1):
        print(f"[{i}/6] {var['prompt'][:50]}...")
        prompt_id = await generate_character_variation(
            "sakura",
            "sakura_reference.png",  # Now in ComfyUI input directory
            var['prompt'],
            var['seed'],
            i
        )
        if prompt_id:
            print(f"    ✅ {prompt_id[:8]}")
            all_results.append(prompt_id)
        await asyncio.sleep(2)

    print("\\n📸 GENERATING YUKI VARIATIONS:")
    print("-" * 30)
    for i, var in enumerate(yuki_variations, 1):
        print(f"[{i}/6] {var['prompt'][:50]}...")
        prompt_id = await generate_character_variation(
            "yuki",
            "yuki_reference.png",  # Now in ComfyUI input directory
            var['prompt'],
            var['seed'],
            i
        )
        if prompt_id:
            print(f"    ✅ {prompt_id[:8]}")
            all_results.append(prompt_id)
        await asyncio.sleep(2)

    print(f"\\n✅ Queued {len(all_results)}/12 total variations")
    print("⏳ Waiting 120 seconds for generation...")
    await asyncio.sleep(120)

    print("\\n📊 CHECKING RESULTS:")
    print("-" * 30)
    import subprocess
    result = subprocess.run("ls -lt /mnt/1TB-storage/ComfyUI/output/tokyo_*_var*.png 2>/dev/null", shell=True, capture_output=True, text=True)
    if result.stdout:
        files = result.stdout.strip().split('\\n')
        print(f"✅ Generated {len(files)} images:")
        for f in files[:12]:
            print(f"   {f}")
    else:
        print("⚠️ Still processing...")

    print("\\n🎯 QC CHECKLIST:")
    print("1. Sakura face consistent across all 6 variations?")
    print("2. Yuki face consistent across all 6 variations?")
    print("3. Clothing variations successful?")
    print("4. Pose variations successful?")
    print("5. Scene variations successful?")
    print("\\nFiles: /mnt/1TB-storage/ComfyUI/output/tokyo_*_var*.png")

if __name__ == "__main__":
    asyncio.run(main())