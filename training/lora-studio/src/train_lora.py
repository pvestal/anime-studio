#!/usr/bin/env python3
"""LoRA training script for Tower Anime Production.

Trains a LoRA adapter on approved character images using diffusers + PEFT.
Designed to run as a standalone subprocess via /usr/bin/python3.

Saves ComfyUI-compatible safetensors to /opt/ComfyUI/models/loras/.

Usage:
    /usr/bin/python3 train_lora.py \
        --job-id train_mario_20260212_120000 \
        --character-slug mario \
        --checkpoint /opt/ComfyUI/models/checkpoints/realistic_vision_v51.safetensors \
        --dataset-dir /opt/tower-anime-production/training/lora-studio/datasets/mario \
        --output /opt/ComfyUI/models/loras/mario_lora_v2.safetensors \
        --epochs 20 --learning-rate 1e-4 --resolution 512
"""

import argparse
import gc
import json
import logging
import sys
import time
from pathlib import Path

import torch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Training jobs file (shared with the API)
JOBS_FILE = Path(__file__).resolve().parent.parent / "training_jobs.json"


def update_job_status(job_id: str, status: str, **extra):
    """Update a training job's status in the shared JSON file."""
    try:
        jobs = []
        if JOBS_FILE.exists():
            with open(JOBS_FILE) as f:
                jobs = json.load(f)

        for job in jobs:
            if job["job_id"] == job_id:
                job["status"] = status
                job.update(extra)
                break

        with open(JOBS_FILE, "w") as f:
            json.dump(jobs, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to update job status: {e}")


def train(args):
    """Main training loop."""
    from diffusers import StableDiffusionPipeline
    from diffusers.utils import convert_state_dict_to_kohya
    from peft import LoraConfig, get_peft_model_state_dict
    from safetensors.torch import save_file
    from torch.utils.data import DataLoader

    from lora_dataset import LoRADataset

    update_job_status(args.job_id, "running", started_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    logger.info(f"Job {args.job_id}: Loading checkpoint {args.checkpoint}")

    try:
        # Load the base SD pipeline from single file
        pipe = StableDiffusionPipeline.from_single_file(
            args.checkpoint,
            torch_dtype=torch.float16,
            safety_checker=None,
            requires_safety_checker=False,
        )

        tokenizer = pipe.tokenizer
        text_encoder = pipe.text_encoder
        vae = pipe.vae
        unet = pipe.unet

        # Freeze everything except LoRA layers
        vae.requires_grad_(False)
        text_encoder.requires_grad_(False)
        unet.requires_grad_(False)

        # Move frozen components to GPU in eval mode
        vae.to("cuda", dtype=torch.float16)
        text_encoder.to("cuda", dtype=torch.float16)
        unet.to("cuda", dtype=torch.float16)
        vae.eval()
        text_encoder.eval()

        # Apply LoRA to UNet
        lora_config = LoraConfig(
            r=args.lora_rank,
            lora_alpha=args.lora_rank,  # alpha = rank for stable training
            target_modules=["to_k", "to_q", "to_v", "to_out.0"],
            lora_dropout=0.0,
        )
        unet.add_adapter(lora_config)
        unet.train()

        # Enable gradient checkpointing to save VRAM
        unet.enable_gradient_checkpointing()

        # Count trainable parameters
        trainable = sum(p.numel() for p in unet.parameters() if p.requires_grad)
        total = sum(p.numel() for p in unet.parameters())
        logger.info(f"Trainable params: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")

        # Dataset
        dataset = LoRADataset(args.dataset_dir, tokenizer, resolution=args.resolution)
        if len(dataset) == 0:
            raise RuntimeError("No approved images found in dataset")

        dataloader = DataLoader(
            dataset,
            batch_size=1,
            shuffle=True,
            num_workers=0,  # Single worker to keep VRAM usage low
            pin_memory=True,
        )

        # Optimizer: 8-bit Adam via bitsandbytes
        import bitsandbytes as bnb
        optimizer = bnb.optim.AdamW8bit(
            [p for p in unet.parameters() if p.requires_grad],
            lr=args.learning_rate,
            weight_decay=1e-2,
        )

        # LR scheduler: cosine annealing
        total_steps = args.epochs * len(dataloader) // args.grad_accum
        from torch.optim.lr_scheduler import CosineAnnealingLR
        scheduler = CosineAnnealingLR(optimizer, T_max=total_steps, eta_min=1e-6)

        # Noise scheduler for training
        noise_scheduler = pipe.scheduler
        del pipe  # Free pipeline memory
        gc.collect()
        torch.cuda.empty_cache()

        logger.info(
            f"Training: {len(dataset)} images, {args.epochs} epochs, "
            f"{total_steps} optimizer steps, LR={args.learning_rate}"
        )

        global_step = 0
        best_loss = float("inf")
        loss_history = []

        for epoch in range(args.epochs):
            epoch_loss = 0.0
            num_batches = 0

            for step, batch in enumerate(dataloader):
                pixel_values = batch["pixel_values"].to("cuda", dtype=torch.float16)
                input_ids = batch["input_ids"].to("cuda")

                # Encode images to latent space
                with torch.no_grad():
                    latents = vae.encode(pixel_values).latent_dist.sample()
                    latents = latents * vae.config.scaling_factor

                # Encode text
                with torch.no_grad():
                    encoder_output = text_encoder(input_ids)
                    encoder_hidden_states = encoder_output[0]

                # Sample noise and timesteps
                noise = torch.randn_like(latents)
                timesteps = torch.randint(
                    0, noise_scheduler.config.num_train_timesteps,
                    (latents.shape[0],), device=latents.device,
                ).long()

                # Add noise to latents
                noisy_latents = noise_scheduler.add_noise(latents, noise, timesteps)

                # Predict noise with UNet (mixed precision)
                with torch.autocast("cuda", dtype=torch.float16):
                    noise_pred = unet(
                        noisy_latents,
                        timesteps,
                        encoder_hidden_states=encoder_hidden_states,
                    ).sample

                # MSE loss against target noise
                loss = torch.nn.functional.mse_loss(noise_pred.float(), noise.float())
                loss = loss / args.grad_accum
                loss.backward()

                epoch_loss += loss.item() * args.grad_accum
                num_batches += 1

                # Gradient accumulation step
                if (step + 1) % args.grad_accum == 0 or (step + 1) == len(dataloader):
                    torch.nn.utils.clip_grad_norm_(
                        [p for p in unet.parameters() if p.requires_grad], 1.0
                    )
                    optimizer.step()
                    scheduler.step()
                    optimizer.zero_grad()
                    global_step += 1

            avg_loss = epoch_loss / max(num_batches, 1)
            loss_history.append(avg_loss)
            lr_now = scheduler.get_last_lr()[0]
            logger.info(
                f"Epoch {epoch+1}/{args.epochs} — loss: {avg_loss:.6f}, lr: {lr_now:.2e}, step: {global_step}"
            )

            # Update job progress
            update_job_status(
                args.job_id, "running",
                epoch=epoch + 1,
                total_epochs=args.epochs,
                loss=round(avg_loss, 6),
                global_step=global_step,
            )

            if avg_loss < best_loss:
                best_loss = avg_loss

        # Save LoRA weights in Kohya format (ComfyUI compatible)
        logger.info(f"Training complete. Best loss: {best_loss:.6f}")
        logger.info(f"Saving LoRA to {args.output}")

        unet_lora_state_dict = get_peft_model_state_dict(unet)
        kohya_state_dict = convert_state_dict_to_kohya(unet_lora_state_dict)

        # Convert to float16 for smaller file
        kohya_state_dict = {k: v.half() for k, v in kohya_state_dict.items()}

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_file(kohya_state_dict, str(output_path))

        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.info(f"Saved: {output_path} ({file_size_mb:.1f} MB)")

        update_job_status(
            args.job_id, "completed",
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            output_path=str(output_path),
            file_size_mb=round(file_size_mb, 1),
            best_loss=round(best_loss, 6),
            final_loss=round(loss_history[-1], 6) if loss_history else None,
            total_steps=global_step,
        )

    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        update_job_status(
            args.job_id, "failed",
            failed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            error=str(e),
        )
        sys.exit(1)
    finally:
        gc.collect()
        torch.cuda.empty_cache()


def main():
    parser = argparse.ArgumentParser(description="LoRA training for Tower Anime Production")
    parser.add_argument("--job-id", required=True, help="Training job ID")
    parser.add_argument("--character-slug", required=True, help="Character slug name")
    parser.add_argument("--checkpoint", required=True, help="Path to base checkpoint .safetensors")
    parser.add_argument("--dataset-dir", required=True, help="Path to character dataset directory")
    parser.add_argument("--output", required=True, help="Output path for LoRA .safetensors")
    parser.add_argument("--epochs", type=int, default=20, help="Number of training epochs")
    parser.add_argument("--learning-rate", type=float, default=1e-4, help="Learning rate")
    parser.add_argument("--resolution", type=int, default=512, help="Training resolution")
    parser.add_argument("--lora-rank", type=int, default=32, help="LoRA rank (r)")
    parser.add_argument("--grad-accum", type=int, default=4, help="Gradient accumulation steps")

    args = parser.parse_args()

    logger.info(f"=== LoRA Training: {args.character_slug} ===")
    logger.info(f"Job ID: {args.job_id}")
    logger.info(f"Checkpoint: {args.checkpoint}")
    logger.info(f"Dataset: {args.dataset_dir}")
    logger.info(f"Output: {args.output}")
    logger.info(f"Epochs: {args.epochs}, LR: {args.learning_rate}, Resolution: {args.resolution}")
    logger.info(f"LoRA rank: {args.lora_rank}, Grad accum: {args.grad_accum}")

    train(args)


if __name__ == "__main__":
    main()
