#!/usr/bin/env python3
"""Find characters in trailer frames using CLIP visual similarity.

Replaces the old vision-model approach (~18s/frame, hallucinated) with CLIP
embedding matching (~50ms/frame, accurate).

Default: scans /tmp/yoshi_frames/ for Yoshi frames and saves to datasets/yoshi/images/.

Usage:
    python3 scripts/classify_yoshi_frames.py --dry-run --limit 20
    python3 scripts/classify_yoshi_frames.py --target yoshi
    python3 scripts/classify_yoshi_frames.py --target mario --frames-dir /tmp/mario_frames
    python3 scripts/classify_yoshi_frames.py --resume
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

from packages.visual_pipeline.clip_classifier import (
    build_reference_embeddings,
    classify_frames_batch,
    verify_assignments,
)
from packages.lora_training.dedup import is_duplicate, register_hash
from packages.lora_training.feedback import register_pending_image
from packages.core.config import BASE_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_FRAMES_DIR = Path("/tmp/yoshi_frames")
HITS_FILE = Path("/tmp/yoshi_frame_hits.json")
PROJECT_NAME = "Super Mario Galaxy Anime Adventure"

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
    parser = argparse.ArgumentParser(description="CLIP-based character classification for trailer frames")
    parser.add_argument("--dry-run", action="store_true", help="Classify only, don't save")
    parser.add_argument("--resume", action="store_true", help="Skip already-processed frames")
    parser.add_argument("--limit", type=int, default=0, help="Process only N frames (0=all)")
    parser.add_argument("--target", type=str, default="yoshi", help="Target character slug")
    parser.add_argument("--frames-dir", type=str, default=str(DEFAULT_FRAMES_DIR), help="Directory of frames")
    parser.add_argument("--video", type=str, default=None, help="Source video for clip extraction")
    args = parser.parse_args()

    frames_dir = Path(args.frames_dir)
    target = args.target

    if not frames_dir.exists():
        logger.error(f"Frames directory not found: {frames_dir}")
        sys.exit(1)

    # Gather frames
    frames = sorted(frames_dir.glob("*.jpg"))
    if not frames:
        frames = sorted(frames_dir.glob("*.png"))
    if not frames:
        logger.error(f"No image files found in {frames_dir}")
        sys.exit(1)

    logger.info(f"Found {len(frames)} frames — target: {target}")

    # Resume support
    hits = load_existing_hits()
    processed_files = set()
    if args.resume and hits:
        processed_files = {h["file"] for h in hits}
        logger.info(f"Resuming: {len(processed_files)} already processed")

    remaining = [f for f in frames if f.name not in processed_files]
    if args.limit > 0:
        remaining = remaining[:args.limit]
        logger.info(f"Limited to {len(remaining)} frames")

    if not remaining:
        logger.info("No frames to process")
        return

    # Build reference embeddings
    logger.info("Building CLIP reference embeddings...")
    start = time.time()
    refs = build_reference_embeddings(PROJECT_NAME, ALL_SLUGS)
    ref_time = time.time() - start
    logger.info(f"References built in {ref_time:.1f}s: {', '.join(f'{k}:{v.shape[0]}' for k, v in refs.items())}")

    if not refs:
        logger.error("No reference embeddings could be built — need approved images")
        sys.exit(1)

    if target not in refs:
        logger.warning(f"No references for target '{target}' — classification will still work for other characters")

    # Batch classify
    logger.info(f"Classifying {len(remaining)} frames...")
    start = time.time()
    classifications = classify_frames_batch(remaining, refs)
    classify_time = time.time() - start
    logger.info(f"Classification done in {classify_time:.1f}s ({len(remaining)/max(classify_time,0.01):.0f} fps)")

    # Verification pass
    logger.info("Running verification pass...")
    classifications = verify_assignments(classifications)

    # Stats
    per_char: dict[str, int] = {}
    for c in classifications:
        slug = c["matched_slug"]
        if slug:
            per_char[slug] = per_char.get(slug, 0) + 1

    logger.info(f"Classification results: {json.dumps(per_char, indent=2)}")

    target_hits = [c for c in classifications if c["matched_slug"] == target]
    logger.info(f"{target} frames: {len(target_hits)} / {len(remaining)}")

    # Save target frames
    dataset_images = BASE_PATH / target / "images"
    dataset_images.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved = 0
    duplicates = 0

    for c in classifications:
        frame_path = Path(c["frame_path"])
        hit = {
            "file": frame_path.name,
            "matched_slug": c["matched_slug"],
            "similarity": c.get("similarity", 0),
            "verified": c.get("verified", False),
        }
        # Legacy compat field
        hit[target] = c["matched_slug"] == target

        if c["matched_slug"] == target:
            if args.dry_run:
                saved += 1
                logger.info(f"  {target.upper()}: {frame_path.name} (sim={c['similarity']:.3f})")
            else:
                if is_duplicate(frame_path, target):
                    duplicates += 1
                    hits.append(hit)
                    continue

                idx = saved + 1
                dest_name = f"trailer_{target}_{timestamp}_{idx:04d}.png"
                dest = dataset_images / dest_name

                try:
                    from PIL import Image
                    img = Image.open(frame_path)
                    if img.mode in ("RGBA", "LA", "P"):
                        img = img.convert("RGB")
                    img.save(dest, "PNG")
                except ImportError:
                    shutil.copy2(frame_path, dest)

                meta = {
                    "seed": None,
                    "full_prompt": None,
                    "design_prompt": "",
                    "checkpoint_model": None,
                    "source": "clip_classify",
                    "frame_number": c.get("frame_index", 0) + 1,
                    "project_name": PROJECT_NAME,
                    "character_name": target.replace("_", " ").title(),
                    "generated_at": datetime.now().isoformat(),
                    "clip_similarity": c.get("similarity", 0),
                    "clip_verified": c.get("verified", False),
                    "original_file": frame_path.name,
                }
                dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
                dest.with_suffix(".txt").write_text(
                    f"{target.replace('_', ' ')} character frame"
                )
                register_pending_image(target, dest_name)
                register_hash(dest, target)
                saved += 1
                logger.info(f"  {target.upper()}: {frame_path.name} -> {dest_name} (sim={c['similarity']:.3f})")

        hits.append(hit)

        if len(hits) % 100 == 0:
            save_hits(hits)

    save_hits(hits)

    total_time = ref_time + classify_time
    logger.info(f"\n{'DRY RUN ' if args.dry_run else ''}COMPLETE in {total_time:.1f}s")
    logger.info(f"  Frames scanned: {len(remaining)}")
    logger.info(f"  {target} frames found: {saved}")
    logger.info(f"  Duplicates: {duplicates}")
    logger.info(f"  All characters: {json.dumps(per_char)}")
    logger.info(f"  Speed: {len(remaining)/max(total_time,0.01):.0f} frames/sec (vs ~0.05 fps with vision model)")


if __name__ == "__main__":
    main()
