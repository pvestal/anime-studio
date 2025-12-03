#!/usr/bin/env python3
"""
Update Kai to female and generate images.
"""

import time
import json
import requests
from pathlib import Path
from character_version_manager import CharacterVersionManager
from llava_validator import LLaVAValidator

def update_kai_to_female():
    """Update Kai Nakamura to female version."""
    manager = CharacterVersionManager()

    female_definition = {
        "gender": "female",
        "appearance": {
            "hair": "dark, long flowing hair",
            "eyes": "sharp, intense dark eyes",
            "build": "athletic, graceful",
            "height": "average to tall"
        },
        "personality": {
            "traits": ["serious", "determined", "strategic", "protective"],
            "role": "protagonist"
        },
        "outfit": {
            "default": "military-style uniform fitted for female",
            "colors": ["black", "dark red accents"],
            "accessories": ["tactical belt", "combat boots"]
        },
        "prompt_template": "Kai Nakamura, female anime protagonist, dark long haired young woman, serious expression, sharp eyes, military uniform with red accents, solo, single person only"
    }

    # Update to female
    version = manager.update_character(
        "Kai Nakamura",
        female_definition,
        "Changed to female version as requested by user"
    )

    print(f"✅ Updated Kai to female (version {version[:8] if version else 'error'})")
    return manager.get_character("Kai Nakamura")

def generate_character(prompt, name_prefix):
    """Generate a character image using ComfyUI."""

    workflow = {
        "3": {
            "inputs": {
                "seed": int(time.time() * 1000) % 2147483647,
                "steps": 28,
                "cfg": 7.5,
                "sampler_name": "dpmpp_2m_sde",
                "scheduler": "karras",
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler"
        },
        "4": {
            "inputs": {
                "ckpt_name": "Counterfeit-V2.5.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "5": {
            "inputs": {
                "width": 512,
                "height": 768,
                "batch_size": 1
            },
            "class_type": "EmptyLatentImage"
        },
        "6": {
            "inputs": {
                "text": prompt,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "7": {
            "inputs": {
                "text": "multiple people, crowd, extra person, bad anatomy, deformed",
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "8": {
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            },
            "class_type": "VAEDecode"
        },
        "9": {
            "inputs": {
                "filename_prefix": f"{name_prefix}_{int(time.time())}",
                "images": ["8", 0]
            },
            "class_type": "SaveImage"
        }
    }

    response = requests.post(
        "http://localhost:8188/prompt",
        json={"prompt": workflow}
    )

    if response.status_code != 200:
        print(f"❌ ComfyUI error for {name_prefix}: {response.status_code}")
        return None

    result = response.json()
    prompt_id = result.get("prompt_id")
    print(f"  Generating {name_prefix} (ID: {prompt_id[:8]})")

    # Wait for generation
    time.sleep(8)

    # Get result
    history = requests.get(f"http://localhost:8188/history/{prompt_id}").json()

    if prompt_id in history:
        outputs = history[prompt_id].get("outputs", {})
        for node_id, node_output in outputs.items():
            if "images" in node_output:
                for img in node_output["images"]:
                    return Path("/mnt/1TB-storage/ComfyUI/output") / img["filename"]

    return None

def main():
    print("🎨 Anime Character Generation Session")
    print("=" * 60)

    # Update Kai to female
    print("\n📝 Updating Kai Nakamura to female...")
    kai_data = update_kai_to_female()

    if not kai_data:
        print("❌ Failed to update Kai")
        return

    # Characters to generate
    characters = [
        {
            "name": "Female Kai Nakamura",
            "prompt": kai_data['definition']['prompt_template'],
            "prefix": "female_kai"
        },
        {
            "name": "Hiroshi Yamamoto",
            "prompt": "Hiroshi Yamamoto, male anime character, silver white hair, calm intelligent expression, glasses, lab coat over dark clothes, solo, single person only",
            "prefix": "hiroshi"
        },
        {
            "name": "Sakura Tanaka",
            "prompt": "Sakura Tanaka, female anime character, pink hair in twin tails, cheerful energetic expression, school uniform with red ribbon, solo, single person only",
            "prefix": "sakura"
        },
        {
            "name": "Akira Shadow",
            "prompt": "Akira Shadow, mysterious anime character, dark purple hair, heterochromia eyes (one red one blue), dark cloak, enigmatic expression, solo, single person only",
            "prefix": "akira"
        },
        {
            "name": "Rei Kurosawa",
            "prompt": "Rei Kurosawa, female anime character, short black hair with blue highlights, serious tactical expression, special ops gear, combat ready, solo, single person only",
            "prefix": "rei"
        }
    ]

    validator = LLaVAValidator()
    results = []

    print("\n🚀 Generating characters...")
    print("-" * 40)

    for char in characters:
        print(f"\n🎯 Generating: {char['name']}")
        image_path = generate_character(char['prompt'], char['prefix'])

        if image_path:
            print(f"  ✅ Generated: {image_path.name}")

            # Validate
            validation = validator.validate_portrait(str(image_path))

            status = "✅" if validation['valid'] else "❌"
            print(f"  {status} Validation: {validation['subject_count']} subject(s)")

            results.append({
                "character": char['name'],
                "file": str(image_path),
                "valid": validation['valid'],
                "subjects": validation['subject_count']
            })
        else:
            print(f"  ❌ Generation failed")
            results.append({
                "character": char['name'],
                "file": None,
                "valid": False,
                "subjects": 0
            })

        time.sleep(2)  # Pause between generations

    # Summary
    print("\n" + "=" * 60)
    print("📊 GENERATION SUMMARY")
    print("-" * 40)

    for r in results:
        status = "✅" if r['valid'] else "❌"
        print(f"{status} {r['character']}: {r['subjects']} subject(s)")
        if r['file']:
            print(f"   📁 {Path(r['file']).name}")

    success_rate = sum(1 for r in results if r['valid']) / len(results) * 100
    print(f"\n🎯 Success Rate: {success_rate:.0f}%")

if __name__ == "__main__":
    main()