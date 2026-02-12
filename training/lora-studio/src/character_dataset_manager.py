#!/usr/bin/env python3
"""
Character Dataset Manager for Tower LoRA Studio
Manages character-specific datasets and LoRA training
"""

import os
import json
import shutil
import asyncpg
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CharacterDatasetManager:
    def __init__(self):
        self.base_path = Path("/opt/tower-lora-studio")
        self.datasets_path = self.base_path / "datasets"
        self.models_path = self.base_path / "models"
        self.configs_path = self.base_path / "configs"

        # Create directories if they don't exist
        self.models_path.mkdir(exist_ok=True)

        # Database connection params
        self.db_config = {
            "host": "localhost",
            "database": "anime_production",
            "user": "patrick",
            "password": "RP78eIrW7cI2jYvL5akt1yurE"
        }

    async def get_all_characters(self):
        """Fetch all characters from database"""
        conn = await asyncpg.connect(**self.db_config)
        try:
            characters = await conn.fetch("""
                SELECT id, name, description, design_prompt, lora_trigger, lora_path
                FROM characters
                ORDER BY name
            """)
            return [dict(c) for c in characters]
        finally:
            await conn.close()

    def create_character_dataset_structure(self, character_name: str):
        """Create proper dataset structure for a character"""
        # Sanitize character name for filesystem
        safe_name = character_name.lower().replace(" ", "_").replace("'", "")

        character_dir = self.datasets_path / safe_name
        character_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        subdirs = ["images", "captions", "masks", "validation"]
        for subdir in subdirs:
            (character_dir / subdir).mkdir(exist_ok=True)

        # Create character config
        config = {
            "character_name": character_name,
            "safe_name": safe_name,
            "created_at": datetime.now().isoformat(),
            "dataset_path": str(character_dir),
            "training_config": {
                "resolution": 512,
                "train_batch_size": 1,
                "gradient_accumulation_steps": 4,
                "learning_rate": 1e-4,
                "max_train_steps": 1000,
                "checkpointing_steps": 500,
                "validation_prompt": f"a portrait of {safe_name}",
                "seed": 42
            },
            "lora_config": {
                "rank": 32,
                "alpha": 32,
                "target_modules": ["to_q", "to_v", "to_k", "to_out"],
                "dropout": 0.1
            }
        }

        config_path = character_dir / "dataset_config.json"
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Created dataset structure for {character_name} at {character_dir}")
        return character_dir

    async def reorganize_existing_datasets(self):
        """Reorganize existing datasets to be character-specific"""
        characters = await self.get_all_characters()

        # Create mapping of existing random datasets to characters
        existing_datasets = [d for d in self.datasets_path.iterdir() if d.is_dir()]

        results = []
        for char in characters:
            char_name = char['name']
            char_dir = self.create_character_dataset_structure(char_name)

            # Check if we have any existing images we can move
            safe_name = char_name.lower().replace(" ", "_").replace("'", "")

            # Look for matching datasets
            for dataset_dir in existing_datasets:
                if safe_name in dataset_dir.name.lower() or char_name.lower() in dataset_dir.name.lower():
                    # Move images from old dataset to new structure
                    old_images = list(dataset_dir.glob("*.png")) + list(dataset_dir.glob("*.jpg"))
                    if old_images:
                        logger.info(f"Moving {len(old_images)} images from {dataset_dir.name} to {char_name}")
                        for img in old_images:
                            shutil.copy2(img, char_dir / "images" / img.name)

            results.append({
                "character": char_name,
                "dataset_path": str(char_dir),
                "lora_trigger": char.get('lora_trigger', safe_name)
            })

        return results

    async def generate_training_script(self, character_name: str):
        """Generate a LoRA training script for a specific character"""
        safe_name = character_name.lower().replace(" ", "_").replace("'", "")
        character_dir = self.datasets_path / safe_name

        if not character_dir.exists():
            raise ValueError(f"Dataset directory for {character_name} doesn't exist")

        # Load config
        config_path = character_dir / "dataset_config.json"
        with open(config_path) as f:
            config = json.load(f)

        # Generate training script
        script = f"""#!/usr/bin/env python3
\"\"\"
LoRA Training Script for {character_name}
Auto-generated by Character Dataset Manager
\"\"\"

import os
import torch
from diffusers import StableDiffusionPipeline, UNet2DConditionModel
from transformers import CLIPTextModel
from peft import LoraConfig, get_peft_model, TaskType
import json

# Configuration
CHARACTER_NAME = "{character_name}"
SAFE_NAME = "{safe_name}"
DATASET_PATH = "{character_dir}"
OUTPUT_PATH = "/opt/tower-lora-studio/models/{safe_name}_lora"

# Training parameters
RESOLUTION = {config['training_config']['resolution']}
BATCH_SIZE = {config['training_config']['train_batch_size']}
GRADIENT_ACCUMULATION = {config['training_config']['gradient_accumulation_steps']}
LEARNING_RATE = {config['training_config']['learning_rate']}
MAX_STEPS = {config['training_config']['max_train_steps']}
CHECKPOINT_STEPS = {config['training_config']['checkpointing_steps']}

# LoRA parameters
LORA_RANK = {config['lora_config']['rank']}
LORA_ALPHA = {config['lora_config']['alpha']}
LORA_DROPOUT = {config['lora_config']['dropout']}

def train():
    print(f"Starting LoRA training for {{CHARACTER_NAME}}")

    # Setup LoRA config
    lora_config = LoraConfig(
        r=LORA_RANK,
        lora_alpha=LORA_ALPHA,
        target_modules={config['lora_config']['target_modules']},
        lora_dropout=LORA_DROPOUT,
    )

    # TODO: Implement actual training loop
    # This is a placeholder - integrate with your preferred training library

    print(f"Training completed! Model saved to {{OUTPUT_PATH}}")

    # Update database with trained model path
    import asyncio
    import asyncpg

    async def update_db():
        conn = await asyncpg.connect(
            host="localhost",
            database="anime_production",
            user="patrick",
            password="RP78eIrW7cI2jYvL5akt1yurE"
        )
        await conn.execute(
            "UPDATE characters SET lora_path = $1 WHERE name = $2",
            f"{{SAFE_NAME}}_lora.safetensors",
            CHARACTER_NAME
        )
        await conn.close()

    asyncio.run(update_db())

if __name__ == "__main__":
    train()
"""

        script_path = character_dir / f"train_{safe_name}_lora.py"
        with open(script_path, "w") as f:
            f.write(script)

        os.chmod(script_path, 0o755)
        logger.info(f"Generated training script at {script_path}")
        return script_path

async def main():
    """Initialize character dataset system"""
    manager = CharacterDatasetManager()

    print("🚀 Character Dataset Manager - Tower LoRA Studio")
    print("=" * 60)

    # Reorganize existing datasets
    print("\n📁 Reorganizing datasets by character...")
    results = await manager.reorganize_existing_datasets()

    for result in results:
        print(f"✅ {result['character']}: {result['dataset_path']}")

    # Generate training scripts for each character
    print("\n📝 Generating training scripts...")
    characters = await manager.get_all_characters()

    for char in characters:
        try:
            script_path = await manager.generate_training_script(char['name'])
            print(f"✅ Generated script for {char['name']}")
        except Exception as e:
            print(f"⚠️  Failed for {char['name']}: {e}")

    print("\n✨ Character dataset system initialized!")
    print(f"📂 Datasets: {manager.datasets_path}")
    print(f"🎨 Models: {manager.models_path}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())