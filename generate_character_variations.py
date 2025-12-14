#!/usr/bin/env python3
"""
Generate character variations using working IPAdapter configuration
Tests face consistency with different clothing and backgrounds
"""

import httpx
import asyncio
import json
from datetime import datetime
from pathlib import Path

async def generate_variation(prompt_text: str, seed: int = -1):
    """Generate a single variation using IPAdapter"""

    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "realisticVision_v51.safetensors"
            }
        },
        "2": {
            "class_type": "CLIPVisionLoader",
            "inputs": {
                "clip_name": "SD1.5/pytorch_model.bin"
            }
        },
        "3": {
            "class_type": "IPAdapterModelLoader",
            "inputs": {
                "ipadapter_file": "ip-adapter-plus_sd15.bin"
            }
        },
        "4": {
            "class_type": "LoadImage",
            "inputs": {
                "image": "yuki_var_1765508404_00001_.png"  # Reference face
            }
        },
        "5": {
            "class_type": "IPAdapter",
            "inputs": {
                "weight": 0.8,
                "weight_type": "standard",
                "start_at": 0.0,
                "end_at": 1.0,
                "model": ["1", 0],
                "ipadapter": ["3", 0],
                "image": ["4", 0],
                "clip_vision": ["2", 0]
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt_text,
                "clip": ["1", 1]
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "ugly, deformed, bad quality, different face, inconsistent",
                "clip": ["1", 1]
            }
        },
        "8": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": 768,
                "height": 768,
                "batch_size": 1
            }
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed if seed != -1 else None,
                "steps": 25,
                "cfg": 7.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["5", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["8", 0]
            }
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["9", 0],
                "vae": ["1", 2]
            }
        },
        "11": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": f"yuki_ipadapter_{datetime.now().strftime('%H%M%S')}",
                "images": ["10", 0]
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
    print("🎯 CHARACTER CONSISTENCY TESTING WITH IPADAPTER")
    print("="*60)
    print("\nUsing IPAdapter to maintain face consistency")
    print("Reference: yuki_var_1765508404_00001_.png")
    print("\n" + "="*60)

    # Test variations - different clothing and backgrounds
    variations = [
        {
            "prompt": "beautiful japanese woman, wearing elegant red evening dress, in luxury restaurant, professional photography",
            "seed": 42,
            "category": "clothing"
        },
        {
            "prompt": "beautiful japanese woman, wearing blue business suit, in modern office, professional photography",
            "seed": 43,
            "category": "clothing"
        },
        {
            "prompt": "beautiful japanese woman, wearing casual t-shirt and jeans, in coffee shop, professional photography",
            "seed": 44,
            "category": "clothing"
        },
        {
            "prompt": "beautiful japanese woman, wearing traditional kimono, in japanese garden, professional photography",
            "seed": 45,
            "category": "clothing"
        },
        {
            "prompt": "beautiful japanese woman, wearing black cocktail dress, at art gallery, professional photography",
            "seed": 46,
            "category": "clothing"
        }
    ]

    results = []

    print("\n📸 GENERATING VARIATIONS:")
    print("-" * 40)

    for i, var in enumerate(variations, 1):
        print(f"\n[{i}/{len(variations)}] {var['category'].upper()}: {var['prompt'][:50]}...")

        prompt_id = await generate_variation(var['prompt'], var['seed'])

        if prompt_id:
            print(f"    ✅ Queued: {prompt_id}")
            results.append({
                "prompt": var['prompt'],
                "category": var['category'],
                "seed": var['seed'],
                "prompt_id": prompt_id,
                "timestamp": datetime.now().isoformat()
            })
        else:
            print(f"    ❌ Failed to queue")

        await asyncio.sleep(2)  # Don't overwhelm ComfyUI

    print("\n" + "="*60)
    print(f"✅ Queued {len(results)}/{len(variations)} variations")

    # Save results
    results_file = Path("/opt/tower-anime-production/ipadapter_test_results.json")
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"📄 Results saved to: {results_file}")

    print("\n⏳ Waiting 60 seconds for generation...")
    await asyncio.sleep(60)

    print("\n📊 CHECKING RESULTS:")
    print("-" * 40)

    # Check what was generated
    import subprocess
    result = subprocess.run(
        ["ls", "-lt", "/mnt/1TB-storage/ComfyUI/output/yuki_ipadapter_*.png"],
        capture_output=True,
        text=True,
        shell=True
    )

    if result.returncode == 0:
        files = result.stdout.strip().split('\n')
        print(f"✅ Found {len(files)} generated images")
        for f in files[:5]:
            print(f"   {f}")
    else:
        print("⚠️ No images found yet - may need more time")

    print("\n" + "="*60)
    print("🎯 KEY POINTS TO CHECK:")
    print("1. Are the faces consistent across all variations?")
    print("2. Did clothing change as requested?")
    print("3. Did backgrounds change as requested?")
    print("4. Is the quality photorealistic?")

if __name__ == "__main__":
    asyncio.run(main())