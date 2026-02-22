"""Batch generate 100 images per character for Cyberpunk Goblin Slayer LoRA training.

Runs generate_batch for each character sequentially (semaphore handles ComfyUI queueing).
Also runs vision review on completed images to auto-triage approve/reject.
"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/tower-anime-production")

from packages.core.db import get_char_project_map
from packages.core.generation import generate_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/opt/tower-anime-production/logs/batch_lora_gen.log"),
    ],
)
logger = logging.getLogger("batch_lora_gen")

PROJECT_NAME = "Cyberpunk Goblin Slayer: Neon Shadows"
TARGET_PER_CHAR = 100
BATCH_SIZE = 10  # Generate in batches of 10 to allow progress tracking


async def count_existing(slug: str) -> dict:
    """Count existing pending + approved images for a character."""
    approval_file = Path(f"/opt/tower-anime-production/datasets/{slug}/approval_status.json")
    approved = pending = 0
    if approval_file.exists():
        statuses = json.loads(approval_file.read_text())
        for v in statuses.values():
            if v == "approved":
                approved += 1
            elif v == "pending":
                pending += 1
    return {"approved": approved, "pending": pending, "total": approved + pending}


async def main():
    start = time.time()
    char_map = await get_char_project_map()
    cyberpunk_chars = sorted([
        slug for slug, info in char_map.items()
        if info.get("project_name") == PROJECT_NAME
    ])

    logger.info(f"Starting batch generation for {len(cyberpunk_chars)} characters")
    logger.info(f"Target: {TARGET_PER_CHAR} images per character")

    total_generated = 0
    total_failed = 0

    for i, slug in enumerate(cyberpunk_chars):
        counts = await count_existing(slug)
        still_needed = max(0, TARGET_PER_CHAR - counts["total"])

        if still_needed == 0:
            logger.info(f"[{i+1}/{len(cyberpunk_chars)}] {slug}: already has {counts['total']} images, skipping")
            continue

        logger.info(
            f"[{i+1}/{len(cyberpunk_chars)}] {slug}: "
            f"has {counts['approved']} approved + {counts['pending']} pending = {counts['total']}, "
            f"generating {still_needed} more"
        )

        # Generate in batches of BATCH_SIZE
        generated_for_char = 0
        remaining = still_needed
        batch_num = 0

        while remaining > 0:
            batch_num += 1
            count = min(BATCH_SIZE, remaining)
            batch_start = time.time()

            try:
                results = await generate_batch(
                    character_slug=slug,
                    count=count,
                    pose_variation=True,
                    include_feedback_negatives=True,
                    include_learned_negatives=True,
                    fire_events=True,
                )

                completed = sum(1 for r in results if r["status"] == "completed")
                failed = sum(1 for r in results if r["status"] != "completed")
                images = sum(len(r.get("images", [])) for r in results)
                elapsed = time.time() - batch_start

                generated_for_char += images
                total_generated += images
                total_failed += failed

                logger.info(
                    f"  {slug} batch {batch_num}: {images} images in {elapsed:.0f}s "
                    f"({completed} ok, {failed} failed) — "
                    f"{generated_for_char}/{still_needed} done"
                )

            except Exception as e:
                logger.error(f"  {slug} batch {batch_num} FAILED: {e}")
                total_failed += count
                # Continue to next batch despite errors

            remaining -= count

        logger.info(f"  {slug}: finished — {generated_for_char} new images generated")

    elapsed_total = time.time() - start
    logger.info(
        f"\n{'='*60}\n"
        f"BATCH GENERATION COMPLETE\n"
        f"  Total generated: {total_generated}\n"
        f"  Total failed: {total_failed}\n"
        f"  Time: {elapsed_total/60:.1f} minutes\n"
        f"{'='*60}"
    )

    # Print final counts
    for slug in cyberpunk_chars:
        counts = await count_existing(slug)
        logger.info(f"  {slug}: {counts['approved']} approved, {counts['pending']} pending, {counts['total']} total")


if __name__ == "__main__":
    asyncio.run(main())
