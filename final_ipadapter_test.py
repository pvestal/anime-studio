#!/usr/bin/env python3
"""Final working IPAdapter test with correct parameters"""

import httpx
import asyncio
import time

async def test():
    """Correct IPAdapter workflow"""

    # The clip_vision is already part of the ipadapter model loading process
    # We don't pass it to IPAdapter node directly

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
                "text": "beautiful japanese woman wearing elegant RED EVENING DRESS in luxury restaurant",
                "clip": ["1", 1]
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "ugly, deformed, bad quality, different person",
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
                "seed": 100,
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],  # Use IPAdapterApply output
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
                "filename_prefix": f"ipadapter_red_dress_{int(time.time())}",
                "images": ["9", 0]
            }
        }
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "http://localhost:8188/prompt",
            json={"prompt": workflow}
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ RED DRESS variation queued: {result['prompt_id']}")
            return result['prompt_id']
        else:
            print(f"❌ Failed: {response.text[:200]}")
            return None

async def main():
    print("🎯 IPADAPTER FACE CONSISTENCY TEST")
    print("="*60)
    print("Testing character consistency with clothing variations")
    print("Reference: yuki_var_1765508404_00001_.png")
    print("="*60 + "\n")

    variations = [
        "beautiful japanese woman wearing elegant RED EVENING DRESS in luxury restaurant",
        "beautiful japanese woman wearing BLUE BUSINESS SUIT in modern office",
        "beautiful japanese woman wearing CASUAL T-SHIRT AND JEANS in coffee shop",
        "beautiful japanese woman wearing TRADITIONAL KIMONO in japanese garden",
        "beautiful japanese woman wearing BLACK COCKTAIL DRESS at art gallery"
    ]

    prompt_ids = []

    for i, prompt in enumerate(variations, 1):
        print(f"[{i}/5] Generating: {prompt[:50]}...")

        # Create workflow for this variation
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
                    "text": prompt,
                    "clip": ["1", 1]
                }
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "ugly, deformed, bad quality, different person",
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
                    "seed": 100 + i,
                    "steps": 20,
                    "cfg": 7,
                    "sampler_name": "euler",
                    "scheduler": "normal",
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
                    "filename_prefix": f"ipadapter_var_{i}_{int(time.time())}",
                    "images": ["9", 0]
                }
            }
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "http://localhost:8188/prompt",
                json={"prompt": workflow}
            )

            if response.status_code == 200:
                result = response.json()
                prompt_ids.append(result['prompt_id'])
                print(f"    ✅ Queued: {result['prompt_id'][:8]}...")
            else:
                print(f"    ❌ Failed")

        await asyncio.sleep(2)

    print("\n" + "="*60)
    print(f"✅ Queued {len(prompt_ids)}/5 variations")
    print("⏳ Waiting 60 seconds for generation...")

    await asyncio.sleep(60)

    print("\n📸 CHECKING RESULTS:")
    print("-" * 40)

    # Check for generated files
    import subprocess
    result = subprocess.run(
        "ls -lt /mnt/1TB-storage/ComfyUI/output/ipadapter_var_*.png 2>/dev/null | head -10",
        shell=True,
        capture_output=True,
        text=True
    )

    if result.stdout:
        print("✅ Generated images found:")
        print(result.stdout)
    else:
        print("⚠️ Images still processing or saved with different names")

    print("\n" + "="*60)
    print("🎯 WHAT TO CHECK:")
    print("1. Is the FACE the same across all variations?")
    print("2. Did the CLOTHING change as requested?")
    print("3. Did the BACKGROUNDS change as requested?")
    print("4. Overall consistency score (1-10)?")

if __name__ == "__main__":
    asyncio.run(main())