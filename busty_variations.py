#!/usr/bin/env python3
"""Generate Tokyo characters with C+ cup sizes and variations"""

import httpx
import asyncio
import time

async def generate_busty_variation(character_name: str, reference_image: str, prompt_text: str, seed: int, variation_num: int):
    """Generate variation with larger bust size"""

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
                "weight": 0.5,  # Lower weight allows variation
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
                "text": "small breasts, flat chest, A cup, B cup, clothing, dressed, bad quality, deformed, different face",
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
                "filename_prefix": f"busty_{character_name}_var{variation_num}_{int(time.time())}",
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
    print("🔥 BUSTY TOKYO CHARACTERS - C+ CUP VARIATIONS")
    print("=" * 60)
    print("Face consistency + larger bust + pose/clothing variations")
    print("=" * 60)

    # Sakura busty variations
    sakura_variations = [
        {"prompt": "Sakura with large C cup breasts, completely nude, standing pose, bedroom", "seed": 1100},
        {"prompt": "Sakura with large D cup breasts, nude, sitting pose, luxury suite", "seed": 1101},
        {"prompt": "Sakura with large C cup breasts, wearing black lace lingerie bra and panties, seductive pose", "seed": 1102},
        {"prompt": "Sakura with large D cup breasts, wearing red satin lingerie, lying pose, candlelit room", "seed": 1103},
        {"prompt": "Sakura with large C cup breasts, nude, reclining pose, bathroom marble", "seed": 1104}
    ]

    # Yuki busty variations
    yuki_variations = [
        {"prompt": "Yuki with large C cup breasts, completely nude, graceful pose, penthouse", "seed": 1200},
        {"prompt": "Yuki with large D cup breasts, nude, stretching pose, yoga studio", "seed": 1201},
        {"prompt": "Yuki with large C cup breasts, wearing blue lace lingerie, confident pose, modern bedroom", "seed": 1202},
        {"prompt": "Yuki with large D cup breasts, wearing pink corset lingerie, playful pose, feminine room", "seed": 1203},
        {"prompt": "Yuki with large C cup breasts, nude, dancing pose, moonlit garden", "seed": 1204}
    ]

    all_results = []

    print("\\n🔥 GENERATING BUSTY SAKURA VARIATIONS:")
    print("-" * 40)
    for i, var in enumerate(sakura_variations, 1):
        print(f"[{i}/5] {var['prompt'][:60]}...")
        prompt_id = await generate_busty_variation(
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

    print("\\n🔥 GENERATING BUSTY YUKI VARIATIONS:")
    print("-" * 40)
    for i, var in enumerate(yuki_variations, 1):
        print(f"[{i}/5] {var['prompt'][:60]}...")
        prompt_id = await generate_busty_variation(
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

    print(f"\\n✅ Queued {len(all_results)}/10 busty variations")
    print("⏳ Waiting 90 seconds for generation...")
    await asyncio.sleep(90)

    print("\\n📊 CHECKING RESULTS:")
    print("-" * 30)
    import subprocess
    result = subprocess.run("ls -lt /mnt/1TB-storage/ComfyUI/output/busty_*.png 2>/dev/null", shell=True, capture_output=True, text=True)
    if result.stdout:
        files = result.stdout.strip().split('\\n')
        print(f"✅ Generated {len(files)} busty images:")
        for f in files[:10]:
            print(f"   {f}")
    else:
        print("⚠️ Still processing...")

    print("\\n🔥 GENERATED VARIATIONS:")
    print("Sakura: C/D cup nude + lingerie variations")
    print("Yuki: C/D cup nude + lingerie variations")
    print("Poses: standing, sitting, lying, reclining, stretching, dancing")
    print("\\nFiles: /mnt/1TB-storage/ComfyUI/output/busty_*.png")

if __name__ == "__main__":
    asyncio.run(main())