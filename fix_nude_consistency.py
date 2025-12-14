#!/usr/bin/env python3
"""Fix nude consistency with stronger IPAdapter settings"""

import httpx
import asyncio
import time

async def test_consistency(prompt_text: str, seed: int):
    """Test with stronger IPAdapter weight for consistency"""

    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "deliberate_v2.safetensors"}  # Different model
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
                "weight": 1.2,  # Higher weight for stronger consistency
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
                "text": "bad quality, deformed, different face, clothed, dressed",
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
                "filename_prefix": f"fixed_nude_{int(time.time())}",
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
    prompts = [
        "naked japanese woman, nude, no clothing, standing in bathroom",
        "naked japanese woman, nude, no clothing, sitting in bedroom",
        "naked japanese woman, nude, no clothing, reclining on bed"
    ]

    print("🔧 FIXING NUDE CONSISTENCY")
    print("Using deliberate_v2 model + weight 1.2")
    print("-" * 40)

    for i, prompt in enumerate(prompts, 1):
        print(f"[{i}/3] {prompt}")
        prompt_id = await test_consistency(prompt, 600 + i)
        if prompt_id:
            print(f"    ✅ {prompt_id[:8]}")
        await asyncio.sleep(2)

    print("\n⏳ Waiting 60 seconds...")
    await asyncio.sleep(60)

    import subprocess
    result = subprocess.run("ls -lt /mnt/1TB-storage/ComfyUI/output/fixed_nude_*.png", shell=True, capture_output=True, text=True)
    print("📸 Results:")
    print(result.stdout)

if __name__ == "__main__":
    asyncio.run(main())