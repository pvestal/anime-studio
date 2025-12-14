#!/usr/bin/env python3
"""Fix pelvis anatomy for proper nude generations"""

import httpx
import asyncio
import time

async def generate_anatomically_correct(character_name: str, reference_image: str, prompt_text: str, seed: int):
    """Generate anatomically correct nude with proper pelvis area"""

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
                "weight": 0.4,  # Lower for anatomical accuracy
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
                "text": "clothing, dressed, bad anatomy, deformed pelvis, missing parts, censored, bad quality, deformed genitals",
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
                "steps": 35,
                "cfg": 10,
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
                "filename_prefix": f"anatomical_{character_name}_{int(time.time())}",
                "images": ["9", 0]
            }
        }
    }

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post("http://localhost:8188/prompt", json={"prompt": workflow})
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
    print("🔧 ANATOMICAL QC - PELVIS AREA FIX")
    print("=" * 45)
    print("Fixing pelvis anatomy for proper nude generation")
    print("=" * 45)

    # Test variations with anatomical focus
    test_variations = [
        {
            "character": "sakura",
            "prompt": "Sakura with large C cup breasts, completely nude, full body, anatomically correct, proper female anatomy, front view standing, realistic proportions",
            "seed": 2000
        },
        {
            "character": "sakura",
            "prompt": "Sakura with large D cup breasts, nude, anatomically accurate, proper pelvis and hips, rear view standing, realistic female body",
            "seed": 2001
        },
        {
            "character": "yuki",
            "prompt": "Yuki with large C cup breasts, completely nude, full body anatomically correct, proper female anatomy, front view sitting, realistic proportions",
            "seed": 2100
        },
        {
            "character": "yuki",
            "prompt": "Yuki with large D cup breasts, nude, anatomically accurate, proper pelvis area, side view lying, realistic female body",
            "seed": 2101
        }
    ]

    all_results = []

    print("\\n🔧 GENERATING ANATOMICALLY CORRECT VARIATIONS:")
    print("-" * 50)
    for i, var in enumerate(test_variations, 1):
        print(f"[{i}/4] {var['character'].upper()}: {var['prompt'][:70]}...")
        prompt_id = await generate_anatomically_correct(
            var['character'],
            f"{var['character']}_reference.png",
            var['prompt'],
            var['seed']
        )
        if prompt_id:
            print(f"    ✅ {prompt_id[:8]}")
            all_results.append(prompt_id)
        await asyncio.sleep(2)

    print(f"\\n✅ Queued {len(all_results)}/4 anatomical QC tests")
    print("⏳ Waiting 90 seconds for generation...")
    await asyncio.sleep(90)

    print("\\n📊 CHECKING QC RESULTS:")
    print("-" * 30)
    import subprocess
    result = subprocess.run("ls -lt /mnt/1TB-storage/ComfyUI/output/anatomical_*.png 2>/dev/null", shell=True, capture_output=True, text=True)
    if result.stdout:
        files = result.stdout.strip().split('\\n')
        print(f"✅ Generated {len(files)} anatomical QC images:")
        for f in files:
            print(f"   {f}")
    else:
        print("⚠️ Still processing...")

    print("\\n🔧 QC FOCUS AREAS:")
    print("✓ Proper female anatomy")
    print("✓ Correct pelvis proportions")
    print("✓ Anatomically accurate nude")
    print("✓ Realistic body proportions")
    print("\\nFiles: /mnt/1TB-storage/ComfyUI/output/anatomical_*.png")
    print("\\nReview these for pelvis area accuracy before proceeding")

if __name__ == "__main__":
    asyncio.run(main())