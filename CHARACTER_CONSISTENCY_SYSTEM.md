# Character Consistency System - LoRA + IPAdapter Architecture

## 🎯 Overview
A complete character consistency system using LoRA training and IPAdapter for maintaining character identity across different outfits, poses, and backgrounds.

## 🏗️ System Architecture

```
Character Reference Images → Training Pipeline → LoRA Model
                          ↓
                    IPAdapter Embedding
                          ↓
                    ComfyUI Workflow
                          ↓
            [LoRA + IPAdapter + Prompt]
                          ↓
                 Consistent Character Output
```

## 📁 Directory Structure

```
/opt/tower-anime-production/
├── character_data/
│   ├── training_sets/
│   │   ├── yuki/
│   │   │   ├── images/
│   │   │   │   ├── yuki_001.png  (front view, neutral)
│   │   │   │   ├── yuki_002.png  (3/4 view, smiling)
│   │   │   │   ├── yuki_003.png  (profile, serious)
│   │   │   │   └── ... (10-15 images)
│   │   │   ├── captions/
│   │   │   │   ├── yuki_001.txt
│   │   │   │   └── ...
│   │   │   └── config.json
│   │   └── sakura/
│   │       └── ... (same structure)
│   ├── embeddings/
│   │   ├── yuki_face.pt      (CLIP face embedding)
│   │   ├── sakura_face.pt
│   │   └── ...
│   └── lora_models/
│       ├── yuki_v1.safetensors
│       ├── sakura_v1.safetensors
│       └── ...
├── workflows/
│   ├── templates/
│   │   ├── lora_ipadapter_base.json
│   │   ├── outfit_variation.json
│   │   ├── background_variation.json
│   │   └── pose_variation.json
│   └── generated/
│       └── ... (saved successful workflows)
└── training/
    ├── scripts/
    │   ├── prepare_training_data.py
    │   ├── train_lora.py
    │   └── extract_embeddings.py
    └── configs/
        ├── lora_config.yaml
        └── training_params.json
```

## 🎓 LoRA Training Pipeline

### Step 1: Prepare Training Data

```python
#!/usr/bin/env python3
"""prepare_training_data.py - Prepare character images for LoRA training"""

import os
import json
from pathlib import Path
from PIL import Image
import numpy as np

class TrainingDataPreparer:
    def __init__(self, character_name: str):
        self.character_name = character_name
        self.base_path = Path(f"/opt/tower-anime-production/character_data/training_sets/{character_name}")
        self.base_path.mkdir(parents=True, exist_ok=True)

    def prepare_images(self, source_images: list):
        """Prepare and standardize images for training"""

        image_path = self.base_path / "images"
        caption_path = self.base_path / "captions"
        image_path.mkdir(exist_ok=True)
        caption_path.mkdir(exist_ok=True)

        for i, img_path in enumerate(source_images, 1):
            # Load and process image
            img = Image.open(img_path)

            # Standardize to 768x768 for SD training
            img = img.resize((768, 768), Image.Resampling.LANCZOS)

            # Save processed image
            output_name = f"{self.character_name}_{i:03d}.png"
            img.save(image_path / output_name, quality=95)

            # Create caption file
            caption = self.generate_caption(img_path, i)
            with open(caption_path / f"{output_name.replace('.png', '.txt')}", 'w') as f:
                f.write(caption)

        # Create config
        config = {
            "character_name": self.character_name,
            "num_images": len(source_images),
            "resolution": 768,
            "caption_style": "detailed",
            "trigger_word": f"{self.character_name.lower()}character"
        }

        with open(self.base_path / "config.json", 'w') as f:
            json.dump(config, f, indent=2)

    def generate_caption(self, img_path: str, index: int) -> str:
        """Generate training caption for image"""

        # Base caption with trigger word
        trigger = f"{self.character_name.lower()}character"

        # Different captions for variety
        captions = [
            f"a photo of {trigger}, beautiful japanese woman",
            f"{trigger}, elegant woman, detailed face",
            f"portrait of {trigger}, high quality photo",
            f"{trigger} in casual outfit, professional photo",
            f"a beautiful {trigger}, japanese woman, realistic"
        ]

        return captions[index % len(captions)]
```

### Step 2: LoRA Training Configuration

```yaml
# lora_config.yaml
model:
  base_checkpoint: "realisticVision_v51.safetensors"
  vae: "vae-ft-mse-840000-ema-pruned.ckpt"

training:
  resolution: 768
  batch_size: 1
  gradient_accumulation_steps: 1
  learning_rate: 1e-4
  lr_scheduler: "cosine"
  lr_warmup_steps: 100
  train_steps: 2000
  save_every: 500

lora:
  rank: 32  # Higher rank = more capacity but larger file
  alpha: 32
  dropout: 0.1
  target_modules:
    - "to_q"
    - "to_v"
    - "to_k"
    - "to_out"

optimization:
  use_8bit_adam: true
  mixed_precision: "fp16"
  gradient_checkpointing: true

augmentation:
  random_flip: true
  color_jitter: 0.1
  random_crop: false  # Keep false for character consistency
```

### Step 3: Training Script

```bash
#!/bin/bash
# train_character_lora.sh

CHARACTER_NAME=$1
BASE_PATH="/opt/tower-anime-production/character_data/training_sets/${CHARACTER_NAME}"

# Using kohya_ss trainer (needs to be installed)
accelerate launch --num_cpu_threads_per_process=2 train_network.py \
  --pretrained_model_name_or_path="/mnt/1TB-storage/ComfyUI/models/checkpoints/realisticVision_v51.safetensors" \
  --train_data_dir="${BASE_PATH}/images" \
  --output_dir="/opt/tower-anime-production/character_data/lora_models" \
  --output_name="${CHARACTER_NAME}_lora" \
  --resolution=768 \
  --train_batch_size=1 \
  --learning_rate=1e-4 \
  --max_train_steps=2000 \
  --save_every_n_steps=500 \
  --network_module=networks.lora \
  --network_dim=32 \
  --network_alpha=32 \
  --caption_extension=".txt" \
  --mixed_precision="fp16" \
  --save_precision="fp16" \
  --cache_latents \
  --gradient_checkpointing \
  --xformers
```

## 🎭 IPAdapter Integration

### Face Embedding Extraction

```python
#!/usr/bin/env python3
"""extract_embeddings.py - Extract face embeddings for IPAdapter"""

import torch
import cv2
import numpy as np
from insightface.app import FaceAnalysis
from pathlib import Path

class FaceEmbeddingExtractor:
    def __init__(self):
        # Initialize InsightFace
        self.app = FaceAnalysis(providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
        self.app.prepare(ctx_id=0, det_size=(640, 640))

    def extract_face_embedding(self, image_path: str, character_name: str):
        """Extract face embedding for IPAdapter"""

        # Load image
        img = cv2.imread(image_path)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Detect faces
        faces = self.app.get(img_rgb)

        if len(faces) == 0:
            raise ValueError("No face detected in image")

        # Get the largest face (main subject)
        face = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))

        # Extract embedding (512-dimensional)
        embedding = face.normed_embedding

        # Save embedding
        output_path = Path(f"/opt/tower-anime-production/character_data/embeddings/{character_name}_face.pt")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(torch.from_numpy(embedding), output_path)

        # Also save as numpy for compatibility
        np.save(output_path.with_suffix('.npy'), embedding)

        return embedding
```

## 🔧 ComfyUI Workflow Templates

### Base LoRA + IPAdapter Workflow

```python
def create_lora_ipadapter_workflow(
    character_name: str,
    prompt: str,
    lora_strength: float = 0.7,
    ipadapter_strength: float = 0.6,
    seed: int = -1
):
    """Create workflow combining LoRA and IPAdapter for consistency"""

    workflow = {
        # Load checkpoint
        "checkpoint_loader": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "realisticVision_v51.safetensors"
            }
        },

        # Load LoRA
        "lora_loader": {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": f"{character_name}_lora.safetensors",
                "strength_model": lora_strength,
                "strength_clip": lora_strength,
                "model": ["checkpoint_loader", 0],
                "clip": ["checkpoint_loader", 1]
            }
        },

        # Load IPAdapter
        "ipadapter_loader": {
            "class_type": "IPAdapterModelLoader",
            "inputs": {
                "ipadapter_file": "ip-adapter-plus_sd15.bin"
            }
        },

        # Load face embedding
        "load_embedding": {
            "class_type": "LoadImage",
            "inputs": {
                "image": f"{character_name}_reference.png",
                "upload": "image"
            }
        },

        # Apply IPAdapter
        "ipadapter_apply": {
            "class_type": "IPAdapterApply",
            "inputs": {
                "ipadapter": ["ipadapter_loader", 0],
                "model": ["lora_loader", 0],
                "weight": ipadapter_strength,
                "image": ["load_embedding", 0]
            }
        },

        # Positive prompt with trigger word
        "positive_prompt": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": f"{character_name.lower()}character, {prompt}",
                "clip": ["lora_loader", 1]
            }
        },

        # Negative prompt
        "negative_prompt": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "multiple people, different person, inconsistent face, deformed",
                "clip": ["lora_loader", 1]
            }
        },

        # KSampler
        "sampler": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed if seed > 0 else random.randint(0, 2**32),
                "steps": 25,
                "cfg": 7.0,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["ipadapter_apply", 0],
                "positive": ["positive_prompt", 0],
                "negative": ["negative_prompt", 0],
                "latent_image": ["empty_latent", 0]
            }
        }
    }

    return workflow
```

## 🔄 Integration with Echo Brain

### Updated Character Generation Endpoint

```python
@router.post("/character/{character_id}/generate_consistent")
async def generate_with_lora_ipadapter(
    character_id: int,
    prompt: str = Form(...),
    variation_type: str = Form("outfit"),  # outfit, background, pose
    lora_strength: float = Form(0.7),
    ipadapter_strength: float = Form(0.6),
    seed: int = Form(-1)
):
    """Generate using LoRA + IPAdapter for true consistency"""

    # Get character info
    character = await get_character(character_id)

    # Check if LoRA exists
    lora_path = f"/mnt/1TB-storage/ComfyUI/models/loras/{character.name}_lora.safetensors"
    if not Path(lora_path).exists():
        return {"error": "LoRA not trained for this character"}

    # Build appropriate prompt based on variation type
    if variation_type == "outfit":
        full_prompt = f"wearing {prompt}, white background, full body"
    elif variation_type == "background":
        full_prompt = f"standing in {prompt}, same outfit"
    else:  # pose
        full_prompt = f"{prompt}, same outfit, same appearance"

    # Create workflow
    workflow = create_lora_ipadapter_workflow(
        character_name=character.name,
        prompt=full_prompt,
        lora_strength=lora_strength,
        ipadapter_strength=ipadapter_strength,
        seed=seed
    )

    # Queue in ComfyUI
    response = await queue_workflow(workflow)

    return {
        "success": True,
        "prompt_id": response["prompt_id"],
        "method": "lora_ipadapter",
        "consistency_expected": "high"
    }
```

## 📊 Character Profile Management

```python
class CharacterConsistencyProfile:
    """Manage all consistency assets for a character"""

    def __init__(self, character_name: str):
        self.name = character_name
        self.base_path = Path(f"/opt/tower-anime-production/character_data")

    @property
    def has_lora(self) -> bool:
        """Check if LoRA is trained"""
        lora_path = Path(f"/mnt/1TB-storage/ComfyUI/models/loras/{self.name}_lora.safetensors")
        return lora_path.exists()

    @property
    def has_embedding(self) -> bool:
        """Check if face embedding exists"""
        embedding_path = self.base_path / f"embeddings/{self.name}_face.pt"
        return embedding_path.exists()

    @property
    def training_images_count(self) -> int:
        """Count training images"""
        image_dir = self.base_path / f"training_sets/{self.name}/images"
        if image_dir.exists():
            return len(list(image_dir.glob("*.png")))
        return 0

    def get_consistency_method(self) -> str:
        """Determine best consistency method available"""
        if self.has_lora and self.has_embedding:
            return "lora_ipadapter"
        elif self.has_lora:
            return "lora_only"
        elif self.has_embedding:
            return "ipadapter_only"
        else:
            return "img2img_fallback"

    def get_generation_params(self) -> dict:
        """Get optimal generation parameters"""
        method = self.get_consistency_method()

        if method == "lora_ipadapter":
            return {
                "method": "lora_ipadapter",
                "lora_strength": 0.7,
                "ipadapter_strength": 0.6,
                "cfg": 7.0,
                "steps": 25
            }
        elif method == "lora_only":
            return {
                "method": "lora_only",
                "lora_strength": 0.8,
                "cfg": 7.5,
                "steps": 30
            }
        elif method == "ipadapter_only":
            return {
                "method": "ipadapter_only",
                "ipadapter_strength": 0.8,
                "cfg": 8.0,
                "steps": 30
            }
        else:
            return {
                "method": "img2img",
                "denoise": 0.4,
                "cfg": 7.5,
                "steps": 30
            }
```

## 🚀 Implementation Steps

### Phase 1: Training Data Preparation (Week 1)
1. Collect 10-15 high-quality images per character
2. Standardize and caption images
3. Extract face embeddings
4. Create training configurations

### Phase 2: LoRA Training (Week 2)
1. Install kohya_ss or alternative trainer
2. Train LoRA for each character (2-3 hours per character)
3. Test and validate LoRA quality
4. Fine-tune training parameters if needed

### Phase 3: IPAdapter Integration (Week 3)
1. Install IPAdapter nodes in ComfyUI
2. Create embedding extraction pipeline
3. Build workflow templates
4. Test IPAdapter + LoRA combinations

### Phase 4: Echo Brain Integration (Week 4)
1. Update character management endpoints
2. Add consistency profile system
3. Create automatic method selection
4. Implement QC metrics for consistency

### Phase 5: Production Deployment (Week 5)
1. Deploy trained LoRAs to ComfyUI
2. Update Character Studio UI
3. Create documentation
4. Train users on new workflow

## 📈 Expected Results

### Without System:
- Face consistency: 20-40%
- Outfit accuracy: Random
- Background control: Limited

### With LoRA Only:
- Face consistency: 70-80%
- Outfit accuracy: 60%
- Background control: Moderate

### With LoRA + IPAdapter:
- Face consistency: 90-95%
- Outfit accuracy: 85%
- Background control: High

### With Full System:
- Face consistency: 95%+
- Outfit accuracy: 90%+
- Background control: Full
- Pose variation: Controlled

## 🔑 Key Success Factors

1. **Quality Training Data**: 10-15 diverse images per character
2. **Proper Captioning**: Consistent trigger words and descriptions
3. **Balanced Strengths**: LoRA 0.6-0.8, IPAdapter 0.5-0.7
4. **Workflow Templates**: Pre-built for common scenarios
5. **Version Control**: Track LoRA versions as characters evolve

## 📝 Notes

- Each LoRA is ~150MB, store in `/mnt/1TB-storage/ComfyUI/models/loras/`
- Face embeddings are 512D vectors, very small files
- Training requires ~10GB VRAM for 768x768 images
- Can train on RTX 3060 in 2-3 hours per character
- IPAdapter adds ~5% to generation time but massive consistency gain

This is the complete system architecture for true character consistency!