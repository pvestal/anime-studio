#!/usr/bin/env python3
"""
Character Consistency Generator using IPAdapter FaceID Plus
Integrates with ComfyUI for consistent character generation
Based on workflows from Civitai and best practices
"""

import httpx
import asyncio
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

class CharacterConsistencyGenerator:
    def __init__(self):
        self.comfyui_url = "http://localhost:8188"
        self.workflow_path = Path("/opt/tower-anime-production/workflows/character_consistency_ipadapter.json")
        self.reference_dir = Path("/opt/tower-anime-production/character_references")
        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")

    def load_workflow_template(self) -> Dict:
        """Load the IPAdapter workflow template"""
        with open(self.workflow_path, 'r') as f:
            workflow_data = json.load(f)
        return workflow_data['workflow']

    def customize_workflow(
        self,
        workflow: Dict,
        character_name: str,
        reference_image: str,
        prompt_variation: str,
        lora_name: Optional[str] = None,
        seed: int = -1
    ) -> Dict:
        """Customize workflow for specific character and variation"""

        # Update reference image
        workflow["2"]["inputs"]["image"] = reference_image

        # Update LoRA if available
        if lora_name:
            workflow["6"]["inputs"]["lora_name"] = lora_name
        else:
            # If no LoRA, bypass the LoRA loader
            workflow["7"]["inputs"]["model"] = ["1", 0]  # Direct from checkpoint

        # Character trigger word
        trigger = f"{character_name.lower()}character"

        # Update positive prompt with variation
        base_prompt = f"beautiful japanese woman {trigger}, {prompt_variation}, professional photography, detailed face, same person as reference, consistent facial features"
        workflow["8"]["inputs"]["text"] = base_prompt

        # Update seed (use random if -1)
        workflow["11"]["inputs"]["seed"] = seed if seed != -1 else None
        workflow["11"]["inputs"]["seed_mode"] = "fixed" if seed != -1 else "random"

        # Update filename prefix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        workflow["13"]["inputs"]["filename_prefix"] = f"{character_name.lower()}_consistent_{timestamp}"

        return workflow

    async def generate_variation(
        self,
        character_name: str,
        variation_type: str,
        variation_desc: str,
        reference_image: str,
        lora_name: Optional[str] = None,
        seed: int = -1
    ) -> Optional[str]:
        """Generate a single character variation"""

        # Load and customize workflow
        workflow = self.load_workflow_template()
        workflow = self.customize_workflow(
            workflow,
            character_name,
            reference_image,
            variation_desc,
            lora_name,
            seed
        )

        # Send to ComfyUI
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                response = await client.post(
                    f"{self.comfyui_url}/prompt",
                    json={"prompt": workflow}
                )

                if response.status_code == 200:
                    result = response.json()
                    prompt_id = result.get('prompt_id')
                    print(f"✅ Queued: {variation_type} - {prompt_id}")
                    return prompt_id
                else:
                    print(f"❌ Failed to queue: {response.status_code}")
                    return None

            except Exception as e:
                print(f"❌ Error: {e}")
                return None

    async def generate_character_set(self, character_name: str, reference_image: str):
        """Generate a complete set of consistent character variations"""

        print(f"\n{'='*60}")
        print(f"🎯 GENERATING CONSISTENT VARIATIONS FOR {character_name.upper()}")
        print(f"Using IPAdapter FaceID Plus + LoRA")
        print(f"Reference: {reference_image}")
        print(f"{'='*60}\n")

        # Check if character LoRA exists
        lora_path = Path(f"/mnt/1TB-storage/ComfyUI/models/loras/{character_name.lower()}_lora_v1.safetensors")
        lora_name = f"{character_name.lower()}_lora_v1.safetensors" if lora_path.exists() else None

        if lora_name:
            print(f"✅ Using trained LoRA: {lora_name}")
        else:
            print(f"⚠️ No LoRA found, using IPAdapter only")

        # Define variations (from Civitai best practices)
        variations = {
            "clothing": [
                "elegant red evening dress in luxury restaurant",
                "professional blue business suit in modern office",
                "casual white t-shirt and jeans in cafe",
                "black cocktail dress at art gallery",
                "traditional japanese kimono in temple garden"
            ],
            "backgrounds": [
                "standing in modern Tokyo office with city view",
                "sitting in traditional japanese tea house",
                "walking through cherry blossom park",
                "at rooftop bar with night cityscape",
                "in cozy bookstore browsing shelves"
            ],
            "poses": [
                "standing confidently, full body visible",
                "sitting elegantly on chair, three-quarter view",
                "walking naturally, side profile",
                "leaning against wall, relaxed pose",
                "close-up portrait, direct eye contact"
            ]
        }

        results = []

        for category, prompts in variations.items():
            print(f"\n📸 Generating {category.upper()} variations:")
            print("-" * 40)

            for i, prompt in enumerate(prompts, 1):
                # Use consistent seeds per category for reproducibility
                seed = 1000 * (list(variations.keys()).index(category) + 1) + i

                prompt_id = await self.generate_variation(
                    character_name,
                    category,
                    prompt,
                    reference_image,
                    lora_name,
                    seed
                )

                if prompt_id:
                    results.append({
                        "character": character_name,
                        "category": category,
                        "prompt": prompt,
                        "prompt_id": prompt_id,
                        "seed": seed,
                        "timestamp": datetime.now().isoformat()
                    })
                    print(f"  [{i}/{len(prompts)}] ✓ {prompt[:50]}...")
                else:
                    print(f"  [{i}/{len(prompts)}] ✗ Failed")

                await asyncio.sleep(2)  # Don't overwhelm ComfyUI

        return results

    async def check_generation_status(self, prompt_id: str) -> Dict:
        """Check the status of a generation"""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.get(f"{self.comfyui_url}/history/{prompt_id}")
                if response.status_code == 200:
                    history = response.json()
                    if prompt_id in history:
                        outputs = history[prompt_id].get('outputs', {})
                        for node_id, output in outputs.items():
                            if 'images' in output:
                                return {
                                    "status": "completed",
                                    "images": output['images']
                                }
                    return {"status": "processing"}
                return {"status": "unknown"}
            except:
                return {"status": "error"}

async def main():
    generator = CharacterConsistencyGenerator()

    # Characters to generate
    characters = [
        {"name": "Yuki", "reference": "yuki_reference_001.png"},
        {"name": "Sakura", "reference": "sakura_reference_001.png"},
        {"name": "Akira", "reference": "akira_reference_001.png"}
    ]

    print("🎨 CHARACTER CONSISTENCY GENERATION SYSTEM")
    print("="*60)
    print("\n📋 Configuration:")
    print("  • Workflow: IPAdapter FaceID Plus + LoRA")
    print("  • Resolution: 768x768")
    print("  • IPAdapter weight: 0.8")
    print("  • LoRA strength: 0.7 (if available)")
    print("  • Sampler: DPM++ 2M Karras, 30 steps")
    print("\n" + "="*60)

    all_results = []

    for char in characters:
        # Check if reference exists
        ref_path = generator.reference_dir / char["reference"]
        if not ref_path.exists():
            print(f"\n⚠️ Reference not found for {char['name']}: {ref_path}")
            print(f"   Using first available image from output directory...")

            # Try to find an existing image
            pattern = f"{char['name'].lower()}_*"
            existing = list(generator.output_dir.glob(f"{pattern}.png"))
            if existing:
                char["reference"] = existing[0].name
                print(f"   Found: {char['reference']}")
            else:
                print(f"   ❌ No images found, skipping {char['name']}")
                continue

        results = await generator.generate_character_set(
            char["name"],
            char["reference"]
        )
        all_results.extend(results)

    # Save results
    results_file = Path("/opt/tower-anime-production/generation_results_ipadapter.json")
    with open(results_file, 'w') as f:
        json.dump(all_results, f, indent=2)

    print("\n" + "="*60)
    print(f"📊 GENERATION SUMMARY")
    print("="*60)
    print(f"Total variations queued: {len(all_results)}")
    print(f"Results saved to: {results_file}")

    print("\n⏳ Waiting 60 seconds for processing...")
    await asyncio.sleep(60)

    # Check completion status
    print("\n📸 Checking generation status...")
    completed = 0
    for result in all_results:
        status = await generator.check_generation_status(result['prompt_id'])
        if status['status'] == 'completed':
            completed += 1
            print(f"✅ {result['character']} - {result['category']}: Complete")

    print(f"\n✅ Completed: {completed}/{len(all_results)}")

    print("\n" + "="*60)
    print("🎯 KEY IMPROVEMENTS OVER IMG2IMG:")
    print("  1. IPAdapter preserves facial identity")
    print("  2. LoRA maintains character style")
    print("  3. Full control over clothing/background")
    print("  4. Consistent seeds for reproducibility")
    print("  5. Based on Civitai best practices")

if __name__ == "__main__":
    asyncio.run(main())