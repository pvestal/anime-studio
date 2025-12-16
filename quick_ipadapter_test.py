#!/usr/bin/env python3
"""Quick IPAdapter test to verify face consistency"""

import httpx
import asyncio
import json
import time

async def test_simple():
    """Minimal IPAdapter test"""

    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "realisticVision_v51.safetensors"}
        },
        "2": {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": "SD1.5/pytorch_model.bin"}
        },
        "3": {
            "class_type": "IPAdapterModelLoader",
            "inputs": {"ipadapter_file": "ip-adapter-plus_sd15.bin"}
        },
        "4": {
            "class_type": "LoadImage",
            "inputs": {"image": "yuki_var_1765508404_00001_.png"}
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
                "text": "beautiful woman wearing red dress",
                "clip": ["1", 1]
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "ugly",
                "clip": ["1", 1]
            }
        },
        "8": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 512, "batch_size": 1}
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
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
                "filename_prefix": f"ipadapter_test_{int(time.time())}",
                "images": ["10", 0]
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
            print(f"✅ Workflow submitted: {result['prompt_id']}")
            return result['prompt_id']
        else:
            print(f"❌ Failed: {response.text[:200]}")
            return None

async def main():
    print("🧪 Quick IPAdapter Test")
    print("-" * 40)

    prompt_id = await test_simple()

    if prompt_id:
        print("⏳ Waiting 30 seconds...")
        await asyncio.sleep(30)

        # Check for output
        import subprocess
        result = subprocess.run(
            "ls -lt /mnt/1TB-storage/ComfyUI/output/*.png | head -5",
            shell=True,
            capture_output=True,
            text=True
        )
        print("\n📸 Latest outputs:")
        print(result.stdout)

if __name__ == "__main__":
    asyncio.run(main())