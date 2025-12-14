#!/usr/bin/env python3
"""ACTUALLY generate lingerie - not swimsuits"""

import httpx
import asyncio
import time

async def generate_real_lingerie(prompt_text: str, seed: int):
    """Generate ACTUAL lingerie with stronger prompts"""

    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "deliberate_v2.safetensors"}  # Better for lingerie
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
            "inputs": {"image": "sakura_reference.png"}
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
                "text": "swimsuit, bikini, bathing suit, sportswear, athletic wear, bad quality, deformed",
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
                "cfg": 12,
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
                "filename_prefix": f"REAL_lingerie_{int(time.time())}",
                "images": ["9", 0]
            }
        }
    }

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post("http://localhost:8188/prompt", json={"prompt": workflow})
            if response.status_code == 200:
                return response.json()['prompt_id']
            else:
                print(f"❌ Failed: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

async def main():
    print("🔧 FIXING LINGERIE GENERATION - NO MORE SWIMSUITS")
    print("=" * 60)

    # Much more specific lingerie prompts
    prompts = [
        "japanese woman wearing intricate black lace lingerie bra with matching panties, delicate straps, bedroom lighting, intimate setting, high quality fashion photography",
        "japanese woman wearing red satin bra and panty set, luxury lingerie, silk texture, romantic pose, boudoir photography, professional lighting",
        "japanese woman wearing white lace teddy lingerie one-piece, elegant intimate apparel, luxury hotel room, soft romantic lighting"
    ]

    print("Testing 3 specific lingerie prompts:")
    for i, prompt in enumerate(prompts, 1):
        print(f"\n[{i}/3] {prompt[:80]}...")
        prompt_id = await generate_real_lingerie(prompt, 1000 + i)
        if prompt_id:
            print(f"    ✅ Queued: {prompt_id[:8]}")
        await asyncio.sleep(3)

    print("\n⏳ Waiting 60 seconds...")
    await asyncio.sleep(60)

    import subprocess
    result = subprocess.run("ls -lt /mnt/1TB-storage/ComfyUI/output/REAL_lingerie_*.png", shell=True, capture_output=True, text=True)
    print("\n📸 Results:")
    if result.stdout:
        print("✅ Generated:")
        print(result.stdout)
    else:
        print("❌ No results - check ComfyUI queue")

if __name__ == "__main__":
    asyncio.run(main())