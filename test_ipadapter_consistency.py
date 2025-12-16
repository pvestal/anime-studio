#!/usr/bin/env python3
"""
Test IPAdapter FaceID workflow for character consistency
Quick verification that the setup works with ComfyUI
"""

import httpx
import asyncio
import json
from pathlib import Path

async def test_ipadapter_workflow():
    """Test basic IPAdapter FaceID workflow"""

    comfyui_url = "http://localhost:8188"

    # Simple test workflow - minimal version for testing
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
                "image": "yuki_var_1765508404_00001_.png"  # Using existing image
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
                "text": "beautiful japanese woman, wearing red dress, standing in restaurant",
                "clip": ["1", 1]
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "ugly, deformed, bad quality",
                "clip": ["1", 1]
            }
        },
        "8": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": 512,
                "height": 768,
                "batch_size": 1
            }
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 7.5,
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
                "filename_prefix": "ipadapter_test",
                "images": ["10", 0]
            }
        }
    }

    print("🧪 TESTING IPADAPTER FACEID WORKFLOW")
    print("="*60)
    print("\n📋 Test Configuration:")
    print("  • IPAdapter Model: ip-adapter-plus_sd15.bin")
    print("  • CLIP Vision: SD1.5/pytorch_model.bin")
    print("  • Checkpoint: realisticVision_v51.safetensors")
    print("  • Reference Image: Existing Yuki image")
    print("  • Weight: 0.8")
    print("\n" + "="*60)

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            print("\n📤 Sending workflow to ComfyUI...")
            response = await client.post(
                f"{comfyui_url}/prompt",
                json={"prompt": workflow}
            )

            if response.status_code == 200:
                result = response.json()
                prompt_id = result.get('prompt_id')
                print(f"✅ Success! Prompt ID: {prompt_id}")

                print("\n⏳ Waiting for generation...")
                await asyncio.sleep(30)

                # Check result
                history_response = await client.get(f"{comfyui_url}/history/{prompt_id}")
                if history_response.status_code == 200:
                    history = history_response.json()
                    if prompt_id in history:
                        status = history[prompt_id].get('status', {})
                        if 'completed' in str(status):
                            print("✅ Generation completed!")
                        else:
                            print(f"⏳ Status: {status}")

                return True
            else:
                print(f"❌ Failed: {response.status_code}")
                print(f"Response: {response.text[:500]}")
                return False

        except Exception as e:
            print(f"❌ Error: {e}")
            return False

async def check_models():
    """Check if required models are present"""

    print("\n🔍 Checking required models...")
    print("-" * 40)

    required_files = {
        "Checkpoint": Path("/mnt/1TB-storage/ComfyUI/models/checkpoints/realisticVision_v51.safetensors"),
        "IPAdapter": Path("/mnt/1TB-storage/ComfyUI/models/ipadapter/ip-adapter-plus_sd15.bin"),
        "CLIP Vision": Path("/mnt/1TB-storage/ComfyUI/models/clip_vision/SD1.5/pytorch_model.bin"),
        "Reference Image": Path("/mnt/1TB-storage/ComfyUI/output/yuki_var_1765508404_00001_.png")
    }

    all_present = True
    for name, path in required_files.items():
        if path.exists():
            print(f"✅ {name}: {path.name}")
        else:
            print(f"❌ {name}: NOT FOUND at {path}")
            all_present = False

    return all_present

async def main():
    print("🎯 IPADAPTER CONSISTENCY TEST")
    print("="*60)

    # Check models first
    if not await check_models():
        print("\n⚠️ Missing required models!")
        print("Please ensure all models are downloaded.")
        return

    # Run test
    success = await test_ipadapter_workflow()

    if success:
        print("\n" + "="*60)
        print("✅ IPADAPTER WORKFLOW TEST SUCCESSFUL")
        print("="*60)
        print("\n📝 Next Steps:")
        print("1. Check output in /mnt/1TB-storage/ComfyUI/output/")
        print("2. Look for: ipadapter_test_*.png")
        print("3. Verify face consistency is maintained")
        print("4. If successful, proceed with full character generation")
    else:
        print("\n" + "="*60)
        print("❌ TEST FAILED - TROUBLESHOOTING REQUIRED")
        print("="*60)
        print("\n🔧 Possible Issues:")
        print("1. InsightFace not properly installed")
        print("2. IPAdapter custom node not loaded")
        print("3. Missing model files")
        print("4. ComfyUI needs restart after InsightFace install")

if __name__ == "__main__":
    asyncio.run(main())