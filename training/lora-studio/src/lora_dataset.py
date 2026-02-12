#!/usr/bin/env python3
"""PyTorch Dataset for LoRA training.

Reads approved images from a character's dataset directory,
loads paired .txt caption files, and returns tokenized training pairs.
"""

import json
import logging
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms

logger = logging.getLogger(__name__)


class LoRADataset(Dataset):
    """Dataset of approved character images with text captions.

    Args:
        dataset_dir: Path to character dataset dir (contains images/ and approval_status.json)
        tokenizer: CLIP tokenizer for caption encoding
        resolution: Target image size (square crop)
    """

    def __init__(self, dataset_dir: str | Path, tokenizer, resolution: int = 512):
        self.dataset_dir = Path(dataset_dir)
        self.images_dir = self.dataset_dir / "images"
        self.tokenizer = tokenizer
        self.resolution = resolution

        # Load approval status — only train on approved images
        approval_file = self.dataset_dir / "approval_status.json"
        if approval_file.exists():
            with open(approval_file) as f:
                approval_status = json.load(f)
        else:
            approval_status = {}

        # Collect approved image paths
        self.image_paths = []
        self.captions = []

        for img_path in sorted(self.images_dir.glob("*.png")):
            status = approval_status.get(img_path.name, "pending")
            if status != "approved":
                continue

            # Load caption from .txt sidecar
            caption_file = img_path.with_suffix(".txt")
            if caption_file.exists():
                caption = caption_file.read_text().strip()
            else:
                caption = ""
                logger.warning(f"No caption file for {img_path.name}, using empty string")

            self.image_paths.append(img_path)
            self.captions.append(caption)

        logger.info(
            f"LoRADataset: {len(self.image_paths)} approved images "
            f"from {self.dataset_dir.name} (resolution={resolution})"
        )

        # Image transforms: resize, center crop, normalize to [-1, 1]
        self.transform = transforms.Compose([
            transforms.Resize(resolution, interpolation=transforms.InterpolationMode.LANCZOS),
            transforms.CenterCrop(resolution),
            transforms.ToTensor(),
            transforms.Normalize([0.5], [0.5]),
        ])

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        img = Image.open(self.image_paths[idx]).convert("RGB")
        pixel_values = self.transform(img)

        caption = self.captions[idx]
        tokens = self.tokenizer(
            caption,
            padding="max_length",
            max_length=self.tokenizer.model_max_length,
            truncation=True,
            return_tensors="pt",
        )

        return {
            "pixel_values": pixel_values,
            "input_ids": tokens.input_ids.squeeze(0),
        }
