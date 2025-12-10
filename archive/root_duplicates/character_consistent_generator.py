#!/usr/bin/env python3
"""
Character-Consistent Anime Generator
Fixes the root issue: generates correct characters instead of just rejecting wrong ones
"""

import os
import json
import asyncio
import requests
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

class CharacterConsistentGenerator:
    def __init__(self):
        self.comfyui_url = "http://127.0.0.1:8188"
        self.client_id = str(uuid.uuid4())
        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")

        # Character database with detailed descriptions
        self.characters = {
            "Kai Nakamura": {
                "appearance": "anime girl, young Japanese woman, beautiful female, feminine face, delicate features, black hair, brown eyes, athletic build, 18 years old, tomboy style, female character",
                "clothing": "dark jacket, casual pants, sneakers",
                "style": "photorealistic anime, detailed shading, masterpiece quality, Tokyo street background, urban setting, beautiful anime girl art",
                "negative": "male, man, boy, masculine, masculine features, beard, mustache, multiple people, crowd, schoolgirl uniform"
            },
            "Hiroshi Yamamoto": {
                "appearance": "middle-aged Japanese male, short brown hair, glasses, professional",
                "clothing": "business suit, tie",
                "style": "professional anime style, clean lines",
                "negative": "young, teenager, casual clothes, female"
            }
        }

    def create_character_consistent_workflow(self, character_name: str, prompt: str, action: str = "standing"):
        """Create workflow with character-specific parameters"""

        if character_name not in self.characters:
            raise ValueError(f"Unknown character: {character_name}")

        char_data = self.characters[character_name]

        # Build detailed character-specific prompt
        detailed_prompt = f"""
        {char_data['appearance']}, {char_data['clothing']},
        {action}, {prompt}, {char_data['style']},
        single character, solo, detailed character design,
        consistent appearance, anime character sheet style,
        high quality, masterpiece, best quality, detailed
        """.strip().replace('\n', ' ').replace('  ', ' ')

        # Strong negative prompt to prevent wrong characters
        negative_prompt = f"""
        {char_data['negative']}, multiple characters, crowd,
        low quality, blurry, distorted, bad anatomy,
        inconsistent character, wrong gender, wrong age,
        noise, artifacts, static, slideshow, flickering
        """.strip().replace('\n', ' ').replace('  ', ' ')

        # Use better checkpoint for character consistency
        workflow = {
            "1": {
                "inputs": {"ckpt_name": "Counterfeit-V2.5.safetensors"},  # Better for female characters
                "class_type": "CheckpointLoaderSimple"
            },
            "2": {
                "inputs": {
                    "text": detailed_prompt,
                    "clip": ["1", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "3": {
                "inputs": {
                    "text": negative_prompt,
                    "clip": ["1", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "4": {
                "inputs": {
                    "width": 768,    # Good balance of quality/speed
                    "height": 1024,  # Portrait for character focus
                    "batch_size": 16
                },
                "class_type": "EmptyLatentImage"
            },
            "5": {
                "inputs": {
                    "seed": int(time.time()),
                    "steps": 28,     # More steps for character detail
                    "cfg": 8.0,      # Balanced CFG
                    "sampler_name": "dpmpp_2m",  # Better sampler for character consistency
                    "scheduler": "karras",       # Better scheduler
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0]
                },
                "class_type": "KSampler"
            },
            "6": {
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
                "class_type": "VAEDecode"
            },
            "7": {
                "inputs": {
                    "images": ["6", 0],
                    "filename_prefix": f"female_{character_name.replace(' ', '_')}_{int(time.time())}"
                },
                "class_type": "SaveImage"
            }
        }

        return workflow, detailed_prompt, negative_prompt

    async def generate_character_consistent_image(self, character_name: str, prompt: str, action: str = "standing"):
        """Generate image with character consistency"""

        try:
            # Create character-specific workflow
            workflow, detailed_prompt, negative_prompt = self.create_character_consistent_workflow(
                character_name, prompt, action
            )

            print(f"🎭 Generating {character_name}")
            print(f"📝 Prompt: {detailed_prompt[:100]}...")
            print(f"🚫 Negative: {negative_prompt[:100]}...")

            # Submit to ComfyUI
            response = requests.post(
                f"{self.comfyui_url}/prompt",
                json={"prompt": workflow, "client_id": self.client_id}
            )

            if response.status_code != 200:
                print(f"ComfyUI error: {response.text}")
                return None

            prompt_id = response.json().get("prompt_id")
            print(f"Submitted to ComfyUI: {prompt_id}")

            # Wait for completion
            for _ in range(60):  # 5-minute timeout
                await asyncio.sleep(5)

                # Check for new images
                latest_image = self._find_latest_character_image(character_name)
                if latest_image:
                    print(f"✅ Image generated: {latest_image}")
                    return str(latest_image)

            print("⏰ Timeout waiting for generation")
            return None

        except Exception as e:
            print(f"Generation error: {e}")
            return None

    def _find_latest_character_image(self, character_name: str) -> Optional[Path]:
        """Find the most recently generated character image"""
        try:
            pattern = f"female_{character_name.replace(' ', '_')}_*.png"
            image_files = list(self.output_dir.glob(pattern))
            if image_files:
                return max(image_files, key=lambda p: p.stat().st_mtime)
            return None
        except Exception as e:
            print(f"Error finding image: {e}")
            return None

    def check_available_models(self):
        """Check what models are available in ComfyUI"""
        try:
            response = requests.get(f"{self.comfyui_url}/object_info")
            if response.status_code == 200:
                object_info = response.json()
                checkpoints = object_info.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [])
                if isinstance(checkpoints, list) and len(checkpoints) > 0:
                    available_models = checkpoints[0] if isinstance(checkpoints[0], list) else []
                    print("Available checkpoints:")
                    for model in available_models[:10]:  # Show first 10
                        print(f"  - {model}")
                    return available_models
        except Exception as e:
            print(f"Error checking models: {e}")
        return []

# Test the character-consistent generation
async def test_character_generation():
    """Test character-consistent generation"""

    print("🎭 Testing Character-Consistent Generation")

    generator = CharacterConsistentGenerator()

    # Check available models
    print("\n📦 Checking available models...")
    models = generator.check_available_models()

    # Test with Kai Nakamura
    print(f"\n🚀 Generating Kai Nakamura...")
    result = await generator.generate_character_consistent_image(
        character_name="Kai Nakamura",
        prompt="walking forward confidently",
        action="walking forward"
    )

    if result:
        print(f"✅ SUCCESS: Generated character image at {result}")

        # Copy to Videos directory for inspection
        import shutil
        shutil.copy(result, "***REMOVED***/character_consistent_kai.png")
        print("📁 Copied to ***REMOVED***/character_consistent_kai.png")

    else:
        print("❌ FAILED: Could not generate character image")

    return result

if __name__ == "__main__":
    asyncio.run(test_character_generation())