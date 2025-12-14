#!/usr/bin/env python3
"""Generate Tokyo characters with sexy lingerie variations"""

import httpx
import asyncio
import time

async def generate_lingerie_variation(character_name: str, reference_image: str, prompt_text: str, seed: int, variation_num: int):
    """Generate lingerie variation while keeping character face consistent"""

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
                "weight": 0.9,
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
                "text": "bad quality, deformed, different face, different person, swimsuit, bikini",
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
                "cfg": 8.5,
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
                "filename_prefix": f"lingerie_{character_name}_var{variation_num}_{int(time.time())}",
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
    print("🔥 TOKYO CHARACTERS - SEXY LINGERIE VARIATIONS")
    print("=" * 55)
    print("Face consistency + lingerie variations")
    print("=" * 55)

    # Sakura lingerie variations
    sakura_variations = [
        {"prompt": "Sakura wearing black lace lingerie bra and panties, seductive pose, luxury bedroom", "seed": 900},
        {"prompt": "Sakura wearing red satin lingerie set, alluring pose, candlelit room", "seed": 901},
        {"prompt": "Sakura wearing white lace teddy lingerie, elegant pose, hotel suite", "seed": 902},
        {"prompt": "Sakura wearing purple silk lingerie with garters, playful pose, boudoir setting", "seed": 903},
        {"prompt": "Sakura wearing sheer black babydoll lingerie, sensual pose, dim lighting", "seed": 904}
    ]

    # Yuki lingerie variations
    yuki_variations = [
        {"prompt": "Yuki wearing blue lace lingerie bra and thong, confident pose, modern bedroom", "seed": 950},
        {"prompt": "Yuki wearing pink satin corset and panties, cute pose, feminine room", "seed": 951},
        {"prompt": "Yuki wearing black mesh bodysuit lingerie, bold pose, urban loft", "seed": 952},
        {"prompt": "Yuki wearing emerald green silk lingerie set, graceful pose, luxury apartment", "seed": 953},
        {"prompt": "Yuki wearing white lace chemise lingerie, innocent pose, soft lighting", "seed": 954}
    ]

    all_results = []

    print("\\n🔥 GENERATING SAKURA LINGERIE VARIATIONS:")
    print("-" * 40)
    for i, var in enumerate(sakura_variations, 1):
        print(f"[{i}/5] {var['prompt'][:55]}...")
        prompt_id = await generate_lingerie_variation(
            "sakura",
            "sakura_reference.png",
            var['prompt'],
            var['seed'],
            i
        )
        if prompt_id:
            print(f"    ✅ {prompt_id[:8]}")
            all_results.append(prompt_id)
        await asyncio.sleep(2)

    print("\\n🔥 GENERATING YUKI LINGERIE VARIATIONS:")
    print("-" * 40)
    for i, var in enumerate(yuki_variations, 1):
        print(f"[{i}/5] {var['prompt'][:55]}...")
        prompt_id = await generate_lingerie_variation(
            "yuki",
            "yuki_reference.png",
            var['prompt'],
            var['seed'],
            i
        )
        if prompt_id:
            print(f"    ✅ {prompt_id[:8]}")
            all_results.append(prompt_id)
        await asyncio.sleep(2)

    print(f"\\n✅ Queued {len(all_results)}/10 lingerie variations")
    print("⏳ Waiting 90 seconds for generation...")
    await asyncio.sleep(90)

    print("\\n📊 CHECKING RESULTS:")
    print("-" * 30)
    import subprocess
    result = subprocess.run("ls -lt /mnt/1TB-storage/ComfyUI/output/lingerie_*.png 2>/dev/null", shell=True, capture_output=True, text=True)
    if result.stdout:
        files = result.stdout.strip().split('\\n')
        print(f"✅ Generated {len(files)} lingerie images:")
        for f in files[:10]:
            print(f"   {f}")
    else:
        print("⚠️ Still processing...")

    print("\\n🔥 LINGERIE TYPES GENERATED:")
    print("Sakura: black lace, red satin, white teddy, purple silk, sheer babydoll")
    print("Yuki: blue lace, pink corset, black mesh, emerald silk, white chemise")
    print("\\nFiles: /mnt/1TB-storage/ComfyUI/output/lingerie_*.png")

if __name__ == "__main__":
    asyncio.run(main())