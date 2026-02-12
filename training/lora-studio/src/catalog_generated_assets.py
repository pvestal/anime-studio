#!/usr/bin/env python3
"""
Catalog all generated assets from ComfyUI output into the generated_assets DB table.

Indexes PNG images and MP4 videos with file metadata extracted from filenames.

Usage:
    python3 catalog_generated_assets.py [--dry-run]
"""

import os
import re
import sys
import json
import psycopg2
from pathlib import Path
from collections import defaultdict

COMFYUI_OUTPUT = Path("/opt/ComfyUI/output")

DB_CONFIG = {
    "host": "localhost",
    "database": "anime_production",
    "user": "patrick",
    "password": "RP78eIrW7cI2jYvL5akt1yurE",
}

# Known project prefixes
PROJECT_PATTERNS = {
    "TDD": "Tokyo Debt Desire",
    "tdd": "Tokyo Debt Desire",
    "CGS": "Cyberpunk Goblin Slayer",
    "AUTO_Tokyo_Debt_Desire": "Tokyo Debt Desire",
    "AUTO_Cyberpunk_Goblin_Slayer": "Cyberpunk Goblin Slayer",
    "AUTO_Super_Mario_Galaxy": "Super Mario Galaxy",
}

# Known character names for metadata extraction
KNOWN_CHARACTERS = [
    "Mei Kobayashi", "Rina Suzuki", "Takeshi Sato", "Yuki Tanaka",
    "Goblin Slayer", "Kai Nakamura", "Kai", "Hiroshi", "Ryuu",
    "Rosalina", "Mario", "Luigi", "Princess Peach", "Bowser Jr",
    "Corporate Executive", "Cyber Goblin Alpha", "Elena Reyes",
    "Jamal Al-Rashid", "Marcus Thompson", "Street Goblin",
    "Zara Hosseini", "Victim",
    "Akira Yamamoto", "Luna Chen", "Viktor Kozlov",
]
# Sort longest first for matching
KNOWN_CHARACTERS.sort(key=len, reverse=True)


def extract_metadata(filepath):
    """Extract structured metadata from a filename."""
    filename = filepath.stem
    metadata = {}

    # Detect project
    for prefix, project in PROJECT_PATTERNS.items():
        if prefix in filename:
            metadata["project"] = project
            break

    # Detect character
    fn_lower = filename.lower()
    for char in KNOWN_CHARACTERS:
        # Check underscore form and concatenated form
        if char.lower().replace(" ", "_") in fn_lower or char.lower().replace(" ", "") in fn_lower:
            metadata["character"] = char
            break

    # Extract prefix (first part before character name or numbers)
    parts = filename.split("_")
    prefix_parts = []
    for p in parts:
        if p.isdigit() and len(p) > 3:
            break
        prefix_parts.append(p)
    if prefix_parts:
        metadata["prefix"] = "_".join(prefix_parts[:3])

    # Extract timestamp-like numbers from filename
    timestamps = re.findall(r'(\d{10})', filename)
    if timestamps:
        metadata["generation_id"] = timestamps[0]

    return metadata


def catalog_assets(dry_run=False):
    """Catalog all ComfyUI output files into the database."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Get already-cataloged file paths
    cur.execute("SELECT file_path FROM generated_assets")
    existing_paths = {row[0] for row in cur.fetchall()}
    print(f"Already cataloged: {len(existing_paths)} assets")

    # Scan for PNG and MP4 files
    png_files = list(COMFYUI_OUTPUT.glob("*.png"))
    mp4_files = list(COMFYUI_OUTPUT.glob("*.mp4"))
    all_files = sorted(png_files + mp4_files, key=lambda f: f.name)
    print(f"Found on disk: {len(png_files)} PNG + {len(mp4_files)} MP4 = {len(all_files)} total")
    print()

    new_count = 0
    skipped = 0
    type_counts = defaultdict(int)
    project_counts = defaultdict(int)

    for filepath in all_files:
        file_path_str = str(filepath)

        if file_path_str in existing_paths:
            skipped += 1
            continue

        file_size = filepath.stat().st_size
        file_type = "image" if filepath.suffix == ".png" else "video"
        metadata = extract_metadata(filepath)

        type_counts[file_type] += 1
        if "project" in metadata:
            project_counts[metadata["project"]] += 1

        if not dry_run:
            cur.execute("""
                INSERT INTO generated_assets (file_path, file_type, file_size, metadata)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (file_path_str, file_type, file_size, json.dumps(metadata)))

        new_count += 1

    if not dry_run:
        conn.commit()

    conn.close()

    print("=== New Assets by Type ===")
    for ftype, count in sorted(type_counts.items()):
        print(f"  {ftype}: {count}")

    print()
    print("=== New Assets by Project ===")
    for project, count in sorted(project_counts.items(), key=lambda x: -x[1]):
        print(f"  {project}: {count}")
    untagged = new_count - sum(project_counts.values())
    if untagged:
        print(f"  (untagged): {untagged}")

    print()
    print("=== Summary ===")
    print(f"  Already cataloged: {skipped}")
    print(f"  Newly cataloged:   {new_count}")
    print(f"  Total in DB now:   {skipped + new_count + len(existing_paths)}")

    if dry_run:
        print()
        print("  ** DRY RUN - no database changes made **")


def backfill_dataset_metadata(dry_run=False):
    """Create partial .meta.json sidecars for dataset images that don't have one.

    Reads design_prompt from .txt sidecar and project settings from DB.
    """
    _SCRIPT_DIR = Path(__file__).resolve().parent
    datasets_dir = _SCRIPT_DIR.parent / "datasets"
    if not datasets_dir.exists():
        print("No datasets directory found.")
        return

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Load character→project mapping with generation settings
    cur.execute("""
        SELECT c.name,
               REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') as slug,
               c.design_prompt, p.name as project_name,
               gs.checkpoint_model, gs.cfg_scale, gs.steps,
               gs.width, gs.height, gs.sampler, gs.scheduler
        FROM characters c
        JOIN projects p ON c.project_id = p.id
        LEFT JOIN generation_styles gs ON gs.style_name = p.default_style
    """)
    char_map = {}
    for row in cur.fetchall():
        slug = row[1]
        if slug not in char_map or len(row[2] or "") > len(char_map[slug].get("design_prompt") or ""):
            char_map[slug] = {
                "name": row[0], "slug": slug, "design_prompt": row[2],
                "project_name": row[3], "checkpoint_model": row[4],
                "cfg_scale": float(row[5]) if row[5] else None,
                "steps": row[6], "width": row[7], "height": row[8],
                "sampler": row[9], "scheduler": row[10],
            }
    conn.close()

    total_backfilled = 0
    total_skipped = 0

    for char_dir in sorted(datasets_dir.iterdir()):
        if not char_dir.is_dir():
            continue
        images_dir = char_dir / "images"
        if not images_dir.exists():
            continue

        slug = char_dir.name
        db_info = char_map.get(slug, {})

        for png in sorted(images_dir.glob("*.png")):
            meta_path = png.with_suffix(".meta.json")
            if meta_path.exists():
                total_skipped += 1
                continue

            # Build partial metadata from what's available
            caption_file = png.with_suffix(".txt")
            design_prompt = ""
            if caption_file.exists():
                design_prompt = caption_file.read_text().strip()

            meta = {
                "seed": None,
                "full_prompt": design_prompt,
                "negative_prompt": None,
                "design_prompt": db_info.get("design_prompt", design_prompt),
                "checkpoint_model": db_info.get("checkpoint_model", ""),
                "cfg_scale": db_info.get("cfg_scale"),
                "steps": db_info.get("steps"),
                "sampler": db_info.get("sampler"),
                "scheduler": db_info.get("scheduler"),
                "width": db_info.get("width"),
                "height": db_info.get("height"),
                "project_name": db_info.get("project_name", ""),
                "character_name": db_info.get("name", slug.replace("_", " ").title()),
                "source": "backfill",
                "backfilled": True,
                "generated_at": None,
            }

            if not dry_run:
                meta_path.write_text(json.dumps(meta, indent=2))
            total_backfilled += 1

    print(f"=== Metadata Backfill ===")
    print(f"  Already had metadata: {total_skipped}")
    print(f"  Backfilled:           {total_backfilled}")
    if dry_run:
        print(f"  ** DRY RUN - no files written **")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    backfill = "--backfill" in sys.argv

    if backfill:
        backfill_dataset_metadata(dry_run=dry_run)
    else:
        catalog_assets(dry_run=dry_run)
