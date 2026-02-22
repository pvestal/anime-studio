#!/usr/bin/env python3
"""Find Yoshi in trailer frames and save ONLY Yoshi frames to his dataset.

Scans /tmp/yoshi_frames/, classifies each against Yoshi only,
saves hits to datasets/yoshi/images/.

Usage:
    python3 scripts/classify_yoshi_frames.py --dry-run
    python3 scripts/classify_yoshi_frames.py --resume
    python3 scripts/classify_yoshi_frames.py
"""

import argparse
import json
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.visual_pipeline.classification import classify_image
from packages.lora_training.dedup import is_duplicate, register_hash
from packages.lora_training.feedback import register_pending_image
from packages.core.config import BASE_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

FRAMES_DIR = Path("/tmp/yoshi_frames")
HITS_FILE = Path("/tmp/yoshi_frame_hits.json")
PROJECT_NAME = "Super Mario Galaxy Anime Adventure"
TARGET_SLUG = "yoshi"

# Classify against full roster so the model can distinguish characters,
# but only save frames where Yoshi appears.
ALL_SLUGS = [
    "mario", "luigi", "princess_peach", "toad", "yoshi", "rosalina",
    "bowser", "bowser_jr", "kamek", "luma", "birdo", "mouser", "lakitu",
]


def load_existing_hits() -> list[dict]:
    if HITS_FILE.exists():
        try:
            data = json.loads(HITS_FILE.read_text())
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, IOError):
            pass
    return []


def save_hits(hits: list[dict]):
    HITS_FILE.write_text(json.dumps(hits, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Find Yoshi in trailer frames")
    parser.add_argument("--dry-run", action="store_true", help="Classify only, don't save")
    parser.add_argument("--resume", action="store_true", help="Skip already-processed frames")
    parser.add_argument("--limit", type=int, default=0, help="Process only N frames (0=all)")
    args = parser.parse_args()

    if not FRAMES_DIR.exists():
        logger.error(f"Frames directory not found: {FRAMES_DIR}")
        sys.exit(1)

    frames = sorted(FRAMES_DIR.glob("*.jpg"))
    if not frames:
        frames = sorted(FRAMES_DIR.glob("*.png"))
    if not frames:
        logger.error(f"No image files found in {FRAMES_DIR}")
        sys.exit(1)

    logger.info(f"Found {len(frames)} frames — looking for Yoshi only")

    hits = load_existing_hits()
    processed_files = set()
    if args.resume and hits:
        processed_files = {h["file"] for h in hits}
        logger.info(f"Resuming: {len(processed_files)} already processed")

    remaining = [f for f in frames if f.name not in processed_files]
    if args.limit > 0:
        remaining = remaining[:args.limit]
        logger.info(f"Limited to {len(remaining)} frames")

    dataset_images = BASE_PATH / TARGET_SLUG / "images"
    dataset_images.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved = 0
    skipped = 0
    duplicates = 0
    start_time = time.time()

    for idx, frame in enumerate(remaining):
        frame_num = idx + 1
        elapsed = time.time() - start_time

        if frame_num % 10 == 0 or frame_num == 1:
            rate = frame_num / elapsed if elapsed > 0 else 0
            logger.info(
                f"[{frame_num}/{len(remaining)}] {rate:.2f} fps | "
                f"yoshi_hits={saved} skipped={skipped} dupes={duplicates}"
            )

        try:
            # Classify against full roster, then check if Yoshi is in results
            matched, description = classify_image(
                frame,
                allowed_slugs=ALL_SLUGS,
                project_name=PROJECT_NAME,
            )
        except Exception as e:
            logger.warning(f"Classification failed for {frame.name}: {e}")
            hits.append({"file": frame.name, "yoshi": False, "error": str(e)})
            continue

        is_yoshi = TARGET_SLUG in matched

        hit = {
            "file": frame.name,
            "yoshi": is_yoshi,
        }

        if not is_yoshi:
            skipped += 1
            hits.append(hit)
        else:
            if args.dry_run:
                saved += 1
                logger.info(f"  YOSHI: {frame.name}")
            else:
                if is_duplicate(frame, TARGET_SLUG):
                    duplicates += 1
                    hits.append(hit)
                    continue

                dest_name = f"trailer_yoshi_{timestamp}_{frame_num:04d}.png"
                dest = dataset_images / dest_name

                # Convert JPG -> PNG
                try:
                    from PIL import Image
                    img = Image.open(frame)
                    if img.mode in ("RGBA", "LA", "P"):
                        img = img.convert("RGB")
                    img.save(dest, "PNG")
                except ImportError:
                    shutil.copy2(frame, dest)

                meta = {
                    "seed": None,
                    "full_prompt": None,
                    "design_prompt": "",
                    "checkpoint_model": None,
                    "source": "trailer_frames",
                    "frame_number": frame_num,
                    "project_name": PROJECT_NAME,
                    "character_name": "Yoshi",
                    "generated_at": datetime.now().isoformat(),
                    "vision_description": description[:300] if description else "",
                    "original_file": frame.name,
                }
                dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
                dest.with_suffix(".txt").write_text(
                    "green dinosaur with round nose, white belly, and red saddle on back"
                )
                register_pending_image(TARGET_SLUG, dest_name)
                register_hash(dest, TARGET_SLUG)
                saved += 1
                logger.info(f"  YOSHI: {frame.name} -> {dest_name}")

            hits.append(hit)

        if frame_num % 50 == 0:
            save_hits(hits)

    save_hits(hits)

    elapsed = time.time() - start_time
    yoshi_total = sum(1 for h in hits if h.get("yoshi"))
    logger.info(f"\n{'DRY RUN ' if args.dry_run else ''}COMPLETE in {elapsed:.0f}s")
    logger.info(f"  Frames scanned: {len(remaining)}")
    logger.info(f"  Yoshi frames found: {saved}")
    logger.info(f"  Yoshi total (incl. resume): {yoshi_total}")
    logger.info(f"  Skipped (no Yoshi): {skipped}")
    logger.info(f"  Duplicates: {duplicates}")


if __name__ == "__main__":
    main()
