#!/usr/bin/env python3
"""Launch Character LoRA Training.

Thin wrapper that delegates to src/train_lora.py using system Python
(which has the required GPU libraries: torch, diffusers, peft, bitsandbytes).

Usage:
    python train_character.py --character-slug mario --epochs 20
    python train_character.py --character-slug mario --epochs 2  # quick test
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TRAIN_SCRIPT = SCRIPT_DIR / "src" / "train_lora.py"
DATASETS_DIR = SCRIPT_DIR / "datasets"
CHECKPOINTS_DIR = Path("/opt/ComfyUI/models/checkpoints")
LORAS_DIR = Path("/opt/ComfyUI/models/loras")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Train a character LoRA")
    parser.add_argument("--character-slug", required=True, help="Character slug (dataset directory name)")
    parser.add_argument("--checkpoint", default=None, help="Override checkpoint path")
    parser.add_argument("--output", default=None, help="Override output path")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--lora-rank", type=int, default=32)
    parser.add_argument("--grad-accum", type=int, default=4)

    args = parser.parse_args()

    dataset_dir = DATASETS_DIR / args.character_slug
    if not dataset_dir.exists():
        print(f"Error: Dataset directory not found: {dataset_dir}")
        sys.exit(1)

    job_id = f"train_{args.character_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    checkpoint = args.checkpoint or str(CHECKPOINTS_DIR / "realistic_vision_v51.safetensors")
    output = args.output or str(LORAS_DIR / f"{args.character_slug}_lora.safetensors")

    cmd = [
        "/usr/bin/python3", str(TRAIN_SCRIPT),
        f"--job-id={job_id}",
        f"--character-slug={args.character_slug}",
        f"--checkpoint={checkpoint}",
        f"--dataset-dir={dataset_dir}",
        f"--output={output}",
        f"--epochs={args.epochs}",
        f"--learning-rate={args.learning_rate}",
        f"--resolution={args.resolution}",
        f"--lora-rank={args.lora_rank}",
        f"--grad-accum={args.grad_accum}",
    ]

    print(f"Launching training: {job_id}")
    print(f"  Character: {args.character_slug}")
    print(f"  Checkpoint: {checkpoint}")
    print(f"  Output: {output}")
    print(f"  Epochs: {args.epochs}, LR: {args.learning_rate}")

    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR / "src"))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
