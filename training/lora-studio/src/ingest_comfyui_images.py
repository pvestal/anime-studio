#!/usr/bin/env python3
"""
Ingest ComfyUI output images into LoRA Studio character dataset directories.

Scans /opt/ComfyUI/output/ for PNG images, matches them to characters in the
anime_production database, and copies them into the appropriate dataset
directories with caption sidecar files.

Usage:
    python3 ingest_comfyui_images.py [--dry-run]
"""

import os
import re
import sys
import shutil
import psycopg2
from pathlib import Path
from collections import defaultdict

# Configuration
COMFYUI_OUTPUT = Path("/opt/ComfyUI/output")
DATASETS_BASE = Path("/opt/tower-lora-studio/datasets")

DB_CONFIG = {
    "host": "localhost",
    "database": "anime_production",
    "user": "patrick",
    "password": "RP78eIrW7cI2jYvL5akt1yurE",
}


def get_characters_from_db():
    """Fetch all characters with project associations from the database."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT ON (name)
                c.id, c.name, c.project_id, p.name as project_name,
                c.lora_trigger, c.design_prompt
            FROM characters c
            LEFT JOIN projects p ON c.project_id = p.id
            WHERE c.project_id IS NOT NULL
            ORDER BY name, project_id DESC
        """)
        rows = cur.fetchall()
        characters = []
        for row in rows:
            characters.append({
                "id": row[0],
                "name": row[1],
                "project_id": row[2],
                "project_name": row[3],
                "lora_trigger": row[4],
                "design_prompt": row[5],
            })
        return characters
    finally:
        conn.close()


def safe_name(name):
    """Convert character name to filesystem-safe format."""
    return name.lower().replace(" ", "_").replace("'", "").replace(".", "").replace("#", "")


def build_character_index(characters):
    """Build a matching index sorted by longest name first.

    Returns list of (pattern_regex, safe_name, character_name) tuples.
    """
    # Deduplicate by name (we already used DISTINCT ON in SQL)
    seen = set()
    unique = []
    for c in characters:
        if c["name"] not in seen:
            seen.add(c["name"])
            unique.append(c)

    # Sort by name length descending so longer names match first
    unique.sort(key=lambda c: len(c["name"]), reverse=True)

    index = []
    for c in unique:
        name = c["name"]
        sname = safe_name(name)

        # Build regex patterns for this character
        # Pattern 1: underscore-separated (e.g., Mei_Kobayashi)
        underscore_form = name.replace(" ", "_")
        # Pattern 2: concatenated (e.g., MeiKobayashi, GoblinSlayer)
        concat_form = name.replace(" ", "")
        # Pattern 3: without punctuation (Bowser Jr. → Bowser Jr, bowser_jr)
        clean_name = name.replace(".", "").replace("#", "")
        clean_underscore = clean_name.replace(" ", "_")

        # For short names (<=4 chars), require word boundaries (_ or start/end)
        if len(name) <= 4:
            pattern = r'(?:^|[_\s])' + re.escape(name) + r'(?:$|[_\s\d])'
        else:
            parts = [
                re.escape(underscore_form),
                re.escape(concat_form),
            ]
            # Add cleaned versions if different
            if clean_underscore != underscore_form:
                parts.append(re.escape(clean_underscore))
            pattern = '|'.join(parts)

        index.append({
            "regex": re.compile(pattern, re.IGNORECASE),
            "safe_name": sname,
            "name": name,
            "character": c,
        })

    # Second pass: add first-name-only patterns for multi-word names
    # These go AFTER full-name entries so full names match first
    first_name_map = {}  # first_name -> character entry (only if unambiguous)
    for c in unique:
        name = c["name"]
        words = name.split()
        if len(words) < 2:
            continue
        first = words[0]
        if first in first_name_map:
            first_name_map[first] = None  # Ambiguous, skip
        else:
            first_name_map[first] = c

    for first_name, c in first_name_map.items():
        if c is None:
            continue  # Ambiguous first name
        sname = safe_name(c["name"])
        # Require word boundary for first-name matches
        pattern = r'(?:^|[_\s])' + re.escape(first_name) + r'(?:$|[_\s\d])'
        index.append({
            "regex": re.compile(pattern, re.IGNORECASE),
            "safe_name": sname,
            "name": c["name"],
            "character": c,
        })

    return index


def match_filename(filename, char_index):
    """Match a filename to a character using the index.

    Returns the matched character dict or None.
    """
    for entry in char_index:
        if entry["regex"].search(filename):
            return entry
    return None


def generate_caption(filename, character_name):
    """Generate a caption from the filename for training."""
    # Strip extension and trailing numbers
    base = Path(filename).stem
    # Remove common prefixes
    prefixes_to_strip = [
        "accurate_", "accurate_video_", "anime_", "char_", "clean_",
        "lora_training_", "photorealistic_tdd_", "photorealistic_",
        "real_", "small_test_", "your_character_",
        "AUTO_Tokyo_Debt_Desire_", "AUTO_Cyberpunk_Goblin_Slayer_Neon_Shadows_",
        "AUTO_Cyberpunk_Goblin_Slayer:_Neon_Shadows_",
        "AUTO_Super_Mario_Galaxy_Anime_Adventure_",
        "TDD_DISTINCT_", "TDD_SSOT_", "tdd_", "TEST_", "REAL_TEST_",
        "QUALITY_TDD_", "RV_", "COMPARE_", "SSOT_", "tweak_CGS_",
        "tweak_TDD_",
    ]
    cleaned = base
    for prefix in prefixes_to_strip:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    # Remove trailing number sequences like _1769575816_00001_
    cleaned = re.sub(r'_\d{5,}_\d+_?$', '', cleaned)
    cleaned = re.sub(r'_\d{5}_?$', '', cleaned)
    cleaned = re.sub(r'_\d{10}_?$', '', cleaned)

    # Replace underscores with spaces
    cleaned = cleaned.replace("_", " ").strip()

    # Build caption
    if cleaned.lower() == character_name.lower():
        return f"a portrait of {character_name}, anime style"
    elif cleaned:
        return f"{character_name}, {cleaned}"
    else:
        return f"a portrait of {character_name}, anime style"


def ensure_dataset_structure(sname):
    """Create the dataset directory structure if it doesn't exist."""
    dataset_dir = DATASETS_BASE / sname
    images_dir = dataset_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Also create other standard subdirs
    for subdir in ["captions", "masks", "validation"]:
        (dataset_dir / subdir).mkdir(exist_ok=True)

    return images_dir


def ingest_images(dry_run=False):
    """Main ingestion logic."""
    print("Loading characters from database...")
    characters = get_characters_from_db()
    print(f"  Found {len(characters)} unique characters across {len(set(c['project_id'] for c in characters))} projects")

    char_index = build_character_index(characters)
    print(f"  Built matching index with {len(char_index)} entries")
    print()

    # Scan ComfyUI output
    png_files = sorted(COMFYUI_OUTPUT.glob("*.png"))
    print(f"Scanning {COMFYUI_OUTPUT}: found {len(png_files)} PNG files")
    print()

    # Track results
    matched = defaultdict(list)
    unmatched = []

    for png in png_files:
        entry = match_filename(png.name, char_index)
        if entry:
            matched[entry["safe_name"]].append((png, entry))
        else:
            unmatched.append(png)

    # Process matched files
    total_copied = 0
    total_skipped = 0
    print("=== Matched Characters ===")
    for sname in sorted(matched.keys()):
        files = matched[sname]
        char_name = files[0][1]["name"]
        images_dir = ensure_dataset_structure(sname)

        copied = 0
        skipped = 0
        for png, entry in files:
            dest = images_dir / png.name
            if dest.exists():
                skipped += 1
                continue

            if not dry_run:
                shutil.copy2(png, dest)

                # Write caption sidecar
                caption = generate_caption(png.name, char_name)
                caption_path = dest.with_suffix(".txt")
                caption_path.write_text(caption)

            copied += 1

        status = "(dry run)" if dry_run else ""
        print(f"  {char_name:25s} -> {sname:25s}: {copied} copied, {skipped} already existed {status}")
        total_copied += copied
        total_skipped += skipped

    print()
    print("=== Unmatched Files ===")
    if unmatched:
        # Group unmatched by prefix pattern for readability
        prefixes = defaultdict(int)
        for f in unmatched:
            # Extract a rough prefix (first 2-3 parts before numbers)
            parts = f.stem.split("_")
            prefix_parts = []
            for p in parts:
                if p.isdigit() and len(p) > 3:
                    break
                prefix_parts.append(p)
            prefix = "_".join(prefix_parts[:4]) if prefix_parts else f.stem
            prefixes[prefix] += 1

        for prefix, count in sorted(prefixes.items(), key=lambda x: -x[1]):
            print(f"  {prefix}: {count} files")
    else:
        print("  None!")

    print()
    print("=== Summary ===")
    print(f"  Total PNG files:    {len(png_files)}")
    print(f"  Matched:            {sum(len(v) for v in matched.values())}")
    print(f"  Unmatched:          {len(unmatched)}")
    print(f"  Copied to datasets: {total_copied}")
    print(f"  Already existed:    {total_skipped}")
    print(f"  Characters with images: {len(matched)}")

    if dry_run:
        print()
        print("  ** DRY RUN - no files were actually copied **")
        print("  Run without --dry-run to execute.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    ingest_images(dry_run=dry_run)
