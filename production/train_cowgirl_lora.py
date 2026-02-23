#!/usr/bin/env python3
"""
Train Cowgirl/Riding Position LoRA for LTX 2B
A reusable NSFW action LoRA with consistent motion patterns
"""

import os
import json
import time
import logging
from pathlib import Path
import subprocess
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CowgirlLoRATrainer:
    """Train a specific riding/cowgirl position LoRA"""

    def __init__(self):
        self.action_name = "cowgirl_riding"
        self.training_dir = Path("/mnt/1TB-storage/ltx_training/cowgirl_riding")
        self.training_dir.mkdir(parents=True, exist_ok=True)

        # We'll use prone_face_cam as base since it has camera-facing positioning
        self.base_lora = "prone_face_cam_v0_2.safetensors"
        self.comfyui_url = "http://localhost:8188"

    def create_training_config(self):
        """Create optimized config for cowgirl position training"""

        config = {
            "action": "cowgirl_riding",
            "description": "Woman on top, rhythmic up-down motion, facing camera",
            "base_model": "ltxv-2b-fp8.safetensors",
            "base_lora": self.base_lora,
            "training_params": {
                "network_dim": 32,  # LoRA rank
                "network_alpha": 16,  # Alpha for scaling
                "learning_rate": 5e-5,  # Higher for faster learning
                "batch_size": 1,  # Limited by VRAM
                "gradient_accumulation_steps": 4,  # Simulate batch=4
                "max_train_steps": 500,  # Shorter for testing
                "save_every_n_steps": 100,
                "resolution": "512x384",
                "fps": 12,  # Lower FPS for training
                "num_frames": 24,  # 2 seconds at 12fps
            },
            "prompts": {
                "positive_template": "woman riding on top, cowgirl position, rhythmic motion, bouncing movement, facing camera, {attributes}",
                "negative_template": "static, standing, walking, side view, clothed",
                "style_attributes": [
                    "nude, explicit",
                    "intimate motion",
                    "sensual expression",
                    "natural movement"
                ]
            },
            "vram_optimizations": {
                "mixed_precision": "fp16",
                "gradient_checkpointing": True,
                "xformers": True,
                "optimizer": "AdamW8bit",
                "cache_latents": True
            }
        }

        # Save config
        config_path = self.training_dir / "training_config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info(f"✅ Config saved to {config_path}")
        return config

    def generate_synthetic_training_data(self, num_samples=20):
        """Generate training videos using existing NSFW LoRAs"""

        logger.info(f"🎬 Generating {num_samples} synthetic training samples...")

        samples_dir = self.training_dir / "samples"
        samples_dir.mkdir(exist_ok=True)

        # Mix different LoRAs for variety
        lora_combinations = [
            ("prone_face_cam_v0_2.safetensors", 0.7),
            ("SexGod_Nudity_LTX2_v1_5.safetensors", 0.5),
            ("LTX2_SS_Motion_7K.safetensors", 0.3),
        ]

        for i in range(num_samples):
            # Vary the prompts slightly
            variations = [
                "woman on top riding motion, bouncing rhythmically",
                "cowgirl position, up and down movement, facing forward",
                "female riding position, rhythmic hip motion, intimate scene",
                "woman straddling, bouncing motion, sensual movement"
            ]

            prompt = variations[i % len(variations)]

            # Create generation workflow
            workflow = self._create_generation_workflow(
                prompt=prompt,
                lora_name=lora_combinations[i % len(lora_combinations)][0],
                lora_strength=lora_combinations[i % len(lora_combinations)][1],
                seed=42 + i,
                filename=f"training_sample_{i:03d}"
            )

            # Submit to ComfyUI
            try:
                response = requests.post(
                    f"{self.comfyui_url}/prompt",
                    json={"prompt": workflow},
                    timeout=10
                )
                if response.status_code == 200:
                    logger.info(f"  📹 Sample {i+1}/{num_samples} submitted")
                else:
                    logger.error(f"  ❌ Failed to submit sample {i+1}")
            except Exception as e:
                logger.error(f"  ❌ Error: {e}")

            # Small delay between submissions
            time.sleep(2)

        logger.info("⏳ Waiting for generations to complete...")
        logger.info("   Check /mnt/1TB-storage/ComfyUI/output/ for samples")

    def _create_generation_workflow(self, prompt, lora_name, lora_strength, seed, filename):
        """Create workflow for generating training samples"""

        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "ltxv-2b-fp8.safetensors"}
            },
            "2": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": "ltx_vae.safetensors"}
            },
            "3": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "t5xxl_fp8_e4m3fn.safetensors",
                    "type": "ltxv"
                }
            },
            "4": {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": lora_name,
                    "strength_model": lora_strength,
                    "strength_clip": lora_strength,
                    "model": ["1", 0],
                    "clip": ["3", 0]
                }
            },
            "5": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": f"{prompt}, high quality, professional",
                    "clip": ["4", 1]
                }
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "low quality, static, blurry",
                    "clip": ["4", 1]
                }
            },
            "7": {
                "class_type": "EmptyLTXVLatentVideo",
                "inputs": {
                    "width": 512,
                    "height": 384,
                    "length": 24,  # 1 second for training
                    "batch_size": 1
                }
            },
            "8": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 15,
                    "cfg": 4.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "positive": ["5", 0],
                    "negative": ["6", 0],
                    "latent_image": ["7", 0],
                    "model": ["4", 0],
                    "denoise": 1.0
                }
            },
            "9": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["8", 0],
                    "vae": ["2", 0]
                }
            },
            "10": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["9", 0],
                    "frame_rate": 12,
                    "format": "video/mp4",
                    "filename_prefix": filename,
                    "save_output": True
                }
            }
        }

    def create_training_script(self, config):
        """Create the actual training script using kohya_ss"""

        script_content = f"""#!/bin/bash
# Cowgirl Position LoRA Training Script
# Optimized for RTX 3060 12GB VRAM

echo "🚀 Starting Cowgirl LoRA Training"
echo "================================"

# Environment setup
export CUDA_VISIBLE_DEVICES=0
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128

# Paths
BASE_DIR="/mnt/1TB-storage/ltx_training/cowgirl_riding"
MODEL_PATH="/mnt/1TB-storage/ComfyUI/models/checkpoints/ltxv-2b-fp8.safetensors"
OUTPUT_DIR="/mnt/1TB-storage/models/loras"

# Check if kohya_ss is installed
if [ ! -d "/opt/kohya_ss" ]; then
    echo "⚠️  Installing kohya_ss for LoRA training..."
    cd /opt
    git clone https://github.com/kohya-ss/sd-scripts.git kohya_ss
    cd kohya_ss
    pip install -r requirements.txt
fi

cd /opt/kohya_ss

# Training command
accelerate launch --mixed_precision fp16 train_network.py \\
    --pretrained_model_name_or_path="$MODEL_PATH" \\
    --network_module="networks.lora" \\
    --network_dim={config['training_params']['network_dim']} \\
    --network_alpha={config['training_params']['network_alpha']} \\
    --train_data_dir="$BASE_DIR/samples" \\
    --output_dir="$OUTPUT_DIR" \\
    --output_name="cowgirl_riding_lora_v1" \\
    --save_model_as="safetensors" \\
    --resolution={config['training_params']['resolution'].replace('x', ',')} \\
    --batch_size={config['training_params']['batch_size']} \\
    --gradient_accumulation_steps={config['training_params']['gradient_accumulation_steps']} \\
    --max_train_steps={config['training_params']['max_train_steps']} \\
    --learning_rate={config['training_params']['learning_rate']} \\
    --lr_scheduler="cosine_with_restarts" \\
    --lr_warmup_steps=50 \\
    --optimizer_type="AdamW8bit" \\
    --mixed_precision="fp16" \\
    --gradient_checkpointing \\
    --xformers \\
    --cache_latents \\
    --save_every_n_steps={config['training_params']['save_every_n_steps']} \\
    --sample_every_n_steps=50 \\
    --sample_prompts="$BASE_DIR/sample_prompts.txt"

echo ""
echo "✅ Training complete!"
echo "📦 LoRA saved to: $OUTPUT_DIR/cowgirl_riding_lora_v1.safetensors"
"""

        script_path = self.training_dir / "train.sh"
        with open(script_path, 'w') as f:
            f.write(script_content)

        os.chmod(script_path, 0o755)
        logger.info(f"✅ Training script created: {script_path}")

        # Also create sample prompts file
        prompts = [
            "woman riding cowgirl position, rhythmic motion",
            "female on top, bouncing movement, intimate scene",
            "cowgirl pose, up and down motion, facing camera"
        ]

        prompts_path = self.training_dir / "sample_prompts.txt"
        with open(prompts_path, 'w') as f:
            f.write('\n'.join(prompts))

        return str(script_path)

    def test_trained_lora(self):
        """Test the trained LoRA with Mei character"""

        test_workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "ltxv-2b-fp8.safetensors"}
            },
            "2": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": "ltx_vae.safetensors"}
            },
            "3": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "t5xxl_fp8_e4m3fn.safetensors",
                    "type": "ltxv"
                }
            },
            # Load our trained cowgirl LoRA
            "4": {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": "cowgirl_riding_lora_v1.safetensors",
                    "strength_model": 0.8,
                    "strength_clip": 0.8,
                    "model": ["1", 0],
                    "clip": ["3", 0]
                }
            },
            # Stack with character LoRA if available
            "5": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "mei, japanese woman, cowgirl position, riding motion, intimate scene",
                    "clip": ["4", 1]
                }
            },
            "6": {
                "class_type": "EmptyLTXVLatentVideo",
                "inputs": {
                    "width": 512,
                    "height": 384,
                    "length": 49,  # 2 seconds
                    "batch_size": 1
                }
            },
            "7": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 12345,
                    "steps": 20,
                    "cfg": 4.5,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "positive": ["5", 0],
                    "negative": ["5", 0],
                    "latent_image": ["6", 0],
                    "model": ["4", 0],
                    "denoise": 1.0
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["7", 0],
                    "vae": ["2", 0]
                }
            },
            "9": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["8", 0],
                    "frame_rate": 24,
                    "format": "video/mp4",
                    "filename_prefix": "test_cowgirl_lora_mei",
                    "save_output": True
                }
            }
        }

        response = requests.post(
            f"{self.comfyui_url}/prompt",
            json={"prompt": test_workflow}
        )

        if response.status_code == 200:
            logger.info("✅ Test generation submitted!")
            return True
        else:
            logger.error("❌ Test generation failed")
            return False


def main():
    """Execute the focused training pipeline"""

    trainer = CowgirlLoRATrainer()

    logger.info("🎯 FOCUSED TRAINING: Cowgirl/Riding Position LoRA")
    logger.info("="*60)

    # Step 1: Create configuration
    config = trainer.create_training_config()

    # Step 2: Generate synthetic training data
    logger.info("\n📊 Step 1: Generating Training Data")
    trainer.generate_synthetic_training_data(num_samples=10)

    # Step 3: Create training script
    logger.info("\n⚙️ Step 2: Creating Training Script")
    script_path = trainer.create_training_script(config)

    logger.info("\n" + "="*60)
    logger.info("📋 NEXT STEPS:")
    logger.info("="*60)
    logger.info("\n1. Wait for sample generation to complete:")
    logger.info("   ls -la /mnt/1TB-storage/ComfyUI/output/training_sample*.mp4")
    logger.info("\n2. Move samples to training directory:")
    logger.info("   mv /mnt/1TB-storage/ComfyUI/output/training_sample*.mp4 \\")
    logger.info("      /mnt/1TB-storage/ltx_training/cowgirl_riding/samples/")
    logger.info("\n3. Run the training:")
    logger.info(f"   bash {script_path}")
    logger.info("\n4. Test the trained LoRA:")
    logger.info("   python3 /opt/anime-studio/production/train_cowgirl_lora.py --test")
    logger.info("\n⏱️ Estimated training time: 2-3 hours on RTX 3060")
    logger.info("💾 Output: /mnt/1TB-storage/models/loras/cowgirl_riding_lora_v1.safetensors")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        trainer = CowgirlLoRATrainer()
        trainer.test_trained_lora()
    else:
        main()