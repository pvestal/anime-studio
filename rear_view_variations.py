#!/usr/bin/env python3
"""Generate Tokyo characters with rear view poses showing off their assets"""

import httpx
import asyncio
import time

async def generate_rear_variation(character_name: str, reference_image: str, prompt_text: str, seed: int, variation_num: int):
    """Generate rear view variation with nice assets"""

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
                "weight": 0.4,  # Lower weight for more variation in poses
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
                "text": "front view, face visible, small ass, flat butt, clothing, dressed, bad quality, deformed, different face",
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
                "steps": 30,
                "cfg": 9.5,
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
                "filename_prefix": f"rear_{character_name}_var{variation_num}_{int(time.time())}",
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
    print("🍑 TOKYO CHARACTERS - REAR VIEW ASSETS")
    print("=" * 50)
    print("Face consistency + rear poses + nice assets")
    print("=" * 50)

    # Sakura rear view variations
    sakura_variations = [
        {"prompt": "Sakura with large C cup breasts and round curvy ass, completely nude, rear view, looking back over shoulder, bedroom", "seed": 1500},
        {"prompt": "Sakura with large D cup breasts and perfect round butt, nude, bending over pose from behind, luxury suite", "seed": 1501},
        {"prompt": "Sakura with large C cup breasts and curvy ass, nude, standing rear view, hands on hips, bathroom", "seed": 1502},
        {"prompt": "Sakura with large D cup breasts and round butt, nude, kneeling rear view pose, looking back, candlelit room", "seed": 1503},
        {"prompt": "Sakura with large C cup breasts and perfect ass, nude, lying on stomach rear view, bed", "seed": 1504}
    ]

    # Yuki rear view variations
    yuki_variations = [
        {"prompt": "Yuki with large C cup breasts and round curvy ass, completely nude, rear view, graceful pose, penthouse", "seed": 1600},
        {"prompt": "Yuki with large D cup breasts and perfect round butt, nude, bending forward rear view, yoga studio", "seed": 1601},
        {"prompt": "Yuki with large C cup breasts and curvy ass, nude, side rear view, stretching pose, modern bedroom", "seed": 1602},
        {"prompt": "Yuki with large D cup breasts and round butt, nude, sitting rear view, looking back, feminine room", "seed": 1603},
        {"prompt": "Yuki with large C cup breasts and perfect ass, nude, standing rear three-quarter view, garden", "seed": 1604}
    ]

    all_results = []

    print("\\n🍑 GENERATING SAKURA REAR VIEWS:")
    print("-" * 40)
    for i, var in enumerate(sakura_variations, 1):
        print(f"[{i}/5] {var['prompt'][:65]}...")
        prompt_id = await generate_rear_variation(
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

    print("\\n🍑 GENERATING YUKI REAR VIEWS:")
    print("-" * 40)
    for i, var in enumerate(yuki_variations, 1):
        print(f"[{i}/5] {var['prompt'][:65]}...")
        prompt_id = await generate_rear_variation(
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

    print(f"\\n✅ Queued {len(all_results)}/10 rear view variations")
    print("⏳ Waiting 90 seconds for generation...")
    await asyncio.sleep(90)

    print("\\n📊 CHECKING RESULTS:")
    print("-" * 30)
    import subprocess
    result = subprocess.run("ls -lt /mnt/1TB-storage/ComfyUI/output/rear_*.png 2>/dev/null", shell=True, capture_output=True, text=True)
    if result.stdout:
        files = result.stdout.strip().split('\\n')
        print(f"✅ Generated {len(files)} rear view images:")
        for f in files[:10]:
            print(f"   {f}")
    else:
        print("⚠️ Still processing...")

    print("\\n🍑 REAR VIEW POSES GENERATED:")
    print("Sakura: looking back, bending over, hands on hips, kneeling, lying")
    print("Yuki: graceful, bending forward, side rear, sitting, three-quarter")
    print("Assets: C/D cup breasts + round curvy asses")
    print("\\nFiles: /mnt/1TB-storage/ComfyUI/output/rear_*.png")

if __name__ == "__main__":
    asyncio.run(main())