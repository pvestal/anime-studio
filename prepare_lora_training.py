#!/usr/bin/env python3
"""
Prepare character reference images for LoRA training
Processes existing ComfyUI output images and prepares them for kohya_ss training
"""

import os
import json
import shutil
from pathlib import Path
from PIL import Image
import hashlib
from datetime import datetime

class LoRATrainingPreparer:
    def __init__(self):
        self.comfyui_output = Path("/mnt/1TB-storage/ComfyUI/output")
        self.training_base = Path("/opt/tower-anime-production/training_data")
        self.required_size = (768, 768)

    def find_character_images(self, character_name: str, limit: int = 20):
        """Find existing character images from ComfyUI output"""
        character_images = []

        # Search for images with character name in filename
        patterns = [
            f"{character_name.lower()}_*",
            f"*{character_name.lower()}*",
            f"{character_name.lower()[0:3]}*"  # First 3 letters
        ]

        for pattern in patterns:
            for img_path in self.comfyui_output.glob(f"{pattern}.png"):
                if len(character_images) >= limit:
                    break
                character_images.append(img_path)

        print(f"Found {len(character_images)} images for {character_name}")
        return character_images

    def prepare_training_image(self, img_path: Path, output_path: Path):
        """Process image for LoRA training"""
        img = Image.open(img_path)

        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Resize to training size (center crop if needed)
        if img.size != self.required_size:
            # Calculate crop for center
            width, height = img.size
            target_w, target_h = self.required_size

            # Scale to fit
            scale = max(target_w / width, target_h / height)
            new_w = int(width * scale)
            new_h = int(height * scale)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Center crop
            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            img = img.crop((left, top, left + target_w, top + target_h))

        # Save with consistent format
        img.save(output_path, "PNG", optimize=True)
        return True

    def generate_caption_file(self, character_name: str, img_path: Path, index: int):
        """Generate caption file for training image"""
        trigger_word = f"{character_name.lower()}character"

        # Different caption variations for diversity
        captions = [
            f"a photo of {trigger_word}, beautiful japanese woman, elegant appearance",
            f"{trigger_word}, professional photo, high quality, detailed face",
            f"portrait of {trigger_word}, photorealistic, studio lighting",
            f"{trigger_word} in elegant dress, full body visible, white background",
            f"beautiful {trigger_word}, distinctive facial features, clear photo"
        ]

        caption = captions[index % len(captions)]
        caption_path = img_path.with_suffix('.txt')

        with open(caption_path, 'w') as f:
            f.write(caption)

        return caption_path

    def prepare_character_dataset(self, character_name: str):
        """Prepare complete dataset for a character"""
        print(f"\n{'='*60}")
        print(f"Preparing LoRA training data for: {character_name}")
        print(f"{'='*60}\n")

        # Find existing images
        source_images = self.find_character_images(character_name)

        if not source_images:
            print(f"⚠️ No images found for {character_name}")
            print(f"Need to generate character reference images first!")
            return False

        # Setup character directories
        char_dir = self.training_base / character_name.lower()
        img_dir = char_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)

        # Process images
        processed = 0
        for i, src_img in enumerate(source_images):
            try:
                # Copy and process image
                dest_img = img_dir / f"{character_name.lower()}_{i:03d}.png"

                print(f"Processing: {src_img.name} → {dest_img.name}")
                self.prepare_training_image(src_img, dest_img)

                # Generate caption
                self.generate_caption_file(character_name, dest_img, i)
                processed += 1

            except Exception as e:
                print(f"❌ Error processing {src_img}: {e}")

        print(f"\n✅ Processed {processed}/{len(source_images)} images")

        # Create training config
        self.create_training_config(character_name, processed)

        return processed > 0

    def create_training_config(self, character_name: str, image_count: int):
        """Create kohya_ss training configuration"""
        config = {
            "model_name": f"{character_name.lower()}_lora_v1",
            "trigger_word": f"{character_name.lower()}character",
            "base_model": "realisticVision_v51.safetensors",
            "training_params": {
                "resolution": "768,768",
                "batch_size": 1,
                "num_epochs": 20,
                "save_every_n_epochs": 5,
                "learning_rate": "1e-4",
                "lr_scheduler": "cosine_with_restarts",
                "network_dim": 32,
                "network_alpha": 32,
                "train_batch_size": 1,
                "gradient_accumulation_steps": 1,
                "mixed_precision": "fp16",
                "save_precision": "fp16",
                "cache_latents": True,
                "gradient_checkpointing": True,
                "max_train_steps": image_count * 20 * 10,  # images * epochs * repeats
                "save_model_as": "safetensors"
            },
            "dataset": {
                "image_dir": str(self.training_base / character_name.lower() / "images"),
                "caption_extension": ".txt",
                "num_repeats": 10,
                "flip_augmentation": True,
                "color_augmentation": False,
                "resolution": [768, 768]
            },
            "output": {
                "output_dir": f"/mnt/1TB-storage/ComfyUI/models/loras/{character_name.lower()}_lora",
                "output_name": f"{character_name.lower()}_lora_v1",
                "save_every_n_epochs": 5,
                "save_last": True
            },
            "metadata": {
                "character": character_name,
                "created": datetime.now().isoformat(),
                "image_count": image_count,
                "trigger_word": f"{character_name.lower()}character",
                "base_model": "realisticVision_v51"
            }
        }

        config_path = self.training_base / character_name.lower() / "training_config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"📄 Saved training config: {config_path}")

        # Also create a simple kohya_ss compatible toml config
        self.create_kohya_toml(character_name, config)

        return config_path

    def create_kohya_toml(self, character_name: str, config: dict):
        """Create kohya_ss compatible TOML configuration"""
        toml_content = f"""# LoRA training configuration for {character_name}
[model_arguments]
pretrained_model_name_or_path = "/mnt/1TB-storage/ComfyUI/models/checkpoints/{config['base_model']}"
v2 = false
v_parameterization = false

[training_arguments]
output_dir = "{config['output']['output_dir']}"
output_name = "{config['output']['output_name']}"
save_model_as = "safetensors"
save_every_n_epochs = {config['training_params']['save_every_n_epochs']}
save_last = true

train_batch_size = {config['training_params']['batch_size']}
learning_rate = {config['training_params']['learning_rate']}
lr_scheduler = "{config['training_params']['lr_scheduler']}"
max_train_epochs = {config['training_params']['num_epochs']}

mixed_precision = "{config['training_params']['mixed_precision']}"
save_precision = "{config['training_params']['save_precision']}"
cache_latents = true
gradient_checkpointing = true
gradient_accumulation_steps = {config['training_params']['gradient_accumulation_steps']}

network_module = "networks.lora"
network_dim = {config['training_params']['network_dim']}
network_alpha = {config['training_params']['network_alpha']}

[dataset_arguments]
train_data_dir = "{config['dataset']['image_dir']}"
resolution = {config['dataset']['resolution']}
caption_extension = "{config['dataset']['caption_extension']}"
enable_bucket = true
min_bucket_reso = 320
max_bucket_reso = 960
bucket_reso_steps = 64

[[dataset_arguments.subsets]]
image_dir = "{config['dataset']['image_dir']}"
num_repeats = {config['dataset']['num_repeats']}
flip_aug = {"true" if config['dataset']['flip_augmentation'] else "false"}
color_aug = {"true" if config['dataset']['color_augmentation'] else "false"}
"""

        toml_path = self.training_base / character_name.lower() / "kohya_config.toml"
        with open(toml_path, 'w') as f:
            f.write(toml_content)

        print(f"📄 Saved kohya config: {toml_path}")
        return toml_path

def main():
    preparer = LoRATrainingPreparer()

    # Characters to prepare
    characters = ["Yuki", "Sakura", "Akira"]

    print("🎯 LoRA Training Data Preparation")
    print("="*60)
    print("\nThis will prepare existing character images for LoRA training")
    print("Using images from: /mnt/1TB-storage/ComfyUI/output/")
    print("Training data will be saved to: /opt/tower-anime-production/training_data/")

    results = {}
    for character in characters:
        success = preparer.prepare_character_dataset(character)
        results[character] = success

    print("\n" + "="*60)
    print("📊 PREPARATION SUMMARY")
    print("="*60)

    for char, success in results.items():
        status = "✅ Ready" if success else "❌ Needs images"
        print(f"{char}: {status}")

    print("\n🔧 Next Steps:")
    print("1. Review training configs in training_data/{character}/")
    print("2. Install kohya_ss for LoRA training")
    print("3. Run training with: accelerate launch train_network.py --config kohya_config.toml")
    print("4. Models will be saved to: /mnt/1TB-storage/ComfyUI/models/loras/")

    # Save preparation status
    status_file = Path("/opt/tower-anime-production/training_data/preparation_status.json")
    with open(status_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "characters": results,
            "ready_for_training": all(results.values()),
            "training_data_path": str(preparer.training_base),
            "output_path": "/mnt/1TB-storage/ComfyUI/models/loras/"
        }, f, indent=2)

    print(f"\n📄 Status saved to: {status_file}")

if __name__ == "__main__":
    main()