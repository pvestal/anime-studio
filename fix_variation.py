#!/usr/bin/env python3
import httpx
import asyncio

async def test():
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "realisticVision_v51.safetensors"}},
        "2": {"class_type": "IPAdapterUnifiedLoader", "inputs": {"model": ["1", 0], "preset": "PLUS (high strength)"}},
        "3": {"class_type": "LoadImage", "inputs": {"image": "sakura_reference.png"}},
        "4": {"class_type": "IPAdapter", "inputs": {"weight": 0.5, "weight_type": "standard", "start_at": 0.0, "end_at": 1.0, "model": ["2", 0], "ipadapter": ["2", 1], "image": ["3", 0]}},  # LOWER WEIGHT
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "Sakura completely nude, naked, no clothes, different pose, sitting", "clip": ["1", 1]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "clothing, dressed, bad quality", "clip": ["1", 1]}},
        "7": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 768, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"seed": 999, "steps": 25, "cfg": 9, "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0, "model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "10": {"class_type": "SaveImage", "inputs": {"filename_prefix": "nude_test_lower_weight", "images": ["9", 0]}}
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post("http://localhost:8188/prompt", json={"prompt": workflow})
        if response.status_code == 200:
            print(f"✅ Queued: {response.json()['prompt_id']}")
        else:
            print(f"❌ Failed: {response.text}")

print("Testing with IPAdapter weight 0.5 instead of 0.9")
asyncio.run(test())