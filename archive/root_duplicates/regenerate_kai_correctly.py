#!/usr/bin/env python3
"""
Regenerate female Kai with CORRECT dark/black hair.
Uses unbiased validation to ensure correctness.
"""

import time
import json
import requests
from pathlib import Path
from unbiased_qc_validator import UnbiasedQCValidator

def generate_with_validation(prompt, negative, name_prefix, requirements, max_attempts=3):
    """Generate and validate until requirements are met."""

    validator = UnbiasedQCValidator()

    for attempt in range(1, max_attempts + 1):
        print(f"\n🎨 Generation attempt {attempt}/{max_attempts}")

        # Workflow with strengthened prompt
        workflow = {
            "3": {
                "inputs": {
                    "seed": int(time.time() * 1000 + attempt) % 2147483647,
                    "steps": 30,  # More steps for better adherence
                    "cfg": 8.5,   # Higher CFG for stronger prompt following
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
                    "text": negative,
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
                    "filename_prefix": f"{name_prefix}_attempt{attempt}_{int(time.time())}",
                    "images": ["8", 0]
                },
                "class_type": "SaveImage"
            }
        }

        # Submit to ComfyUI
        response = requests.post(
            "http://localhost:8188/prompt",
            json={"prompt": workflow}
        )

        if response.status_code != 200:
            print(f"   ❌ ComfyUI error: {response.status_code}")
            continue

        result = response.json()
        prompt_id = result.get("prompt_id")
        print(f"   Generating (ID: {prompt_id[:8]})")

        # Wait for generation
        time.sleep(10)

        # Get result
        history = requests.get(f"http://localhost:8188/history/{prompt_id}").json()

        if prompt_id not in history:
            print("   ❌ Generation not found")
            continue

        # Find output file
        image_path = None
        outputs = history[prompt_id].get("outputs", {})
        for node_id, node_output in outputs.items():
            if "images" in node_output:
                for img in node_output["images"]:
                    image_path = Path("/mnt/1TB-storage/ComfyUI/output") / img["filename"]
                    break
                if image_path:
                    break

        if not image_path:
            print("   ❌ No output image")
            continue

        print(f"   ✅ Generated: {image_path.name}")

        # Validate with unbiased QC
        print("   🔍 Running unbiased validation...")
        validation = validator.validate_image(str(image_path), requirements)

        # Check what was actually observed
        obs = validation.get('observations', {})
        print(f"   • Observed hair color: {obs.get('hair_color_observed', '?')}")
        print(f"   • Valid: {'✅' if validation['valid'] else '❌'}")

        if validation['valid']:
            print(f"\n✅ SUCCESS! Generated correct image on attempt {attempt}")
            return image_path

        print(f"   ❌ Failed validation: {', '.join(validation.get('mismatches', []))}")

    print(f"\n❌ Failed after {max_attempts} attempts")
    return None


def main():
    print("🔧 REGENERATING FEMALE KAI WITH CORRECT ATTRIBUTES")
    print("=" * 70)

    # VERY explicit prompt for dark/black hair
    kai_prompt = (
        "solo, single person only, one character, "
        "Kai Nakamura, female anime protagonist, "
        "BLACK HAIR, dark black hair color, jet black hair, NOT red hair, "
        "long flowing black hair, dark colored hair, "
        "serious expression, sharp dark eyes, "
        "military uniform with red accents on clothing only, "
        "female warrior, standing pose"
    )

    # Strong negatives against wrong colors
    kai_negative = (
        "red hair, pink hair, brown hair, blonde hair, colored hair, "
        "multiple people, crowd, extra person, "
        "bad anatomy, deformed, ugly"
    )

    requirements = {
        "people_count": 1,
        "gender": "female",
        "hair_color": "dark black",
        "outfit": "military uniform"
    }

    print("\n📝 Requirements:")
    print(f"   - Gender: {requirements['gender']}")
    print(f"   - Hair: {requirements['hair_color']} (NOT red)")
    print(f"   - Outfit: {requirements['outfit']}")
    print("-" * 70)

    # Generate with validation
    result = generate_with_validation(
        kai_prompt,
        kai_negative,
        "female_kai_corrected",
        requirements,
        max_attempts=5
    )

    if result:
        print(f"\n📁 Final image: {result}")
        print("✅ Female Kai successfully regenerated with correct attributes")

        # Clean up old incorrect version
        old_file = Path("/mnt/1TB-storage/ComfyUI/output/female_kai_1764634362_00001_.png")
        if old_file.exists():
            old_file.rename(old_file.with_suffix('.png.incorrect'))
            print(f"🗑️ Renamed incorrect version to .incorrect")
    else:
        print("\n❌ Failed to generate correct female Kai")


if __name__ == "__main__":
    main()