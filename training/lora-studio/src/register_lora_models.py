#!/usr/bin/env python3
"""
Register unregistered LoRA .safetensors models in the lora_models DB table
and update character lora_path references where applicable.

Usage:
    python3 register_lora_models.py [--dry-run]
"""

import re
import sys
import psycopg2
from pathlib import Path

LORAS_DIR = Path("/opt/ComfyUI/models/loras")

DB_CONFIG = {
    "host": "localhost",
    "database": "anime_production",
    "user": "patrick",
    "password": "RP78eIrW7cI2jYvL5akt1yurE",
}

# Type inference rules: (pattern, type)
TYPE_RULES = [
    (r'^test_', "test"),
    (r'^mei_', "character"),
    (r'^rina_', "character"),
    (r'^hiroshi_', "character"),
    (r'^kai_', "character"),
    (r'^ryuu_', "character"),
    (r'^mario_', "character"),
    (r'^rosalina_', "character"),
    (r'cyberpunk_style', "style"),
    (r'dream', "style"),
    (r'motion', "style"),
    (r'distilled', "style"),
    (r'kiss', "nsfw"),
    (r'nsfw', "nsfw"),
    (r'nudity', "nsfw"),
    (r'orgasm', "nsfw"),
    (r'sexgod', "nsfw"),
    (r'fitbutt', "nsfw"),
    (r'cowgirl', "nsfw"),
    (r'prone', "nsfw"),
    (r'riding', "nsfw"),
    (r'redcircle', "test"),
]

# Character-to-LoRA mapping: (lora_filename_pattern, character_name)
CHARACTER_LORA_MAP = [
    ("kai_cyberpunk_slayer", "Kai"),
    ("kai_nakamura_optimized", "Kai Nakamura"),
    ("mei_working_v1", "Mei Kobayashi"),
    ("mei_face", "Mei Kobayashi"),
    ("mei_body", "Mei Kobayashi"),
    ("mei_real_v3", "Mei Kobayashi"),
    ("mei_tdd_real_v2", "Mei Kobayashi"),
    ("hiroshi_optimized_v1", "Hiroshi"),
    ("ryuu_working_v1", "Ryuu"),
    ("rina_tdd_real_v2", "Rina Suzuki"),
    ("mario_lora", "Mario"),
]


def infer_type(filename):
    """Infer LoRA type from filename."""
    name_lower = filename.lower()
    for pattern, lora_type in TYPE_RULES:
        if re.search(pattern, name_lower):
            return lora_type
    return "general"


def infer_base_model(filename):
    """Detect base model from filename."""
    name_lower = filename.lower()
    if "ltx" in name_lower:
        return "LTX-Video"
    return "SD1.5"


def infer_trigger_word(name):
    """Generate a trigger word from the model name."""
    # Strip version suffixes
    cleaned = re.sub(r'[-_]v\d+.*$', '', name)
    cleaned = re.sub(r'[-_]\d{6}$', '', cleaned)
    cleaned = re.sub(r'[-_]step[-_]\d+$', '', cleaned)
    return cleaned.replace("_", " ").replace("-", " ").strip()


def register_models(dry_run=False):
    """Register unregistered LoRA models."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Get existing registered models
    cur.execute("SELECT name, file_path FROM lora_models")
    existing = {row[0]: row[1] for row in cur.fetchall()}
    print(f"Currently registered: {len(existing)} models")

    # Scan LoRA directory
    safetensors = sorted(LORAS_DIR.glob("*.safetensors"))
    print(f"Found on disk: {len(safetensors)} .safetensors files")
    print()

    registered = 0
    skipped = 0
    for lora_file in safetensors:
        name = lora_file.stem  # filename without extension
        file_path = str(lora_file)

        if name in existing:
            skipped += 1
            continue

        lora_type = infer_type(name)
        base_model = infer_base_model(name)
        trigger_word = infer_trigger_word(name)
        strength = 1.0

        # Adjust strength defaults based on type
        if lora_type == "nsfw":
            strength = 0.7
        elif lora_type == "test":
            strength = 0.5
        elif lora_type == "style":
            strength = 0.8

        print(f"  + {name:45s}  type={lora_type:10s}  base={base_model:10s}  trigger='{trigger_word}'")

        if not dry_run:
            cur.execute("""
                INSERT INTO lora_models (name, type, trigger_word, strength_default, file_path, base_model)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (name, lora_type, trigger_word, strength, file_path, base_model))

        registered += 1

    # Update character lora_path references
    print()
    print("=== Updating Character LoRA References ===")
    cur.execute("SELECT id, name, lora_path FROM characters WHERE project_id IS NOT NULL")
    characters = cur.fetchall()

    updated_chars = 0
    for char_id, char_name, current_lora_path in characters:
        for lora_pattern, target_char in CHARACTER_LORA_MAP:
            if char_name == target_char:
                # Find the best matching LoRA file
                matching_files = [f for f in safetensors if lora_pattern in f.stem]
                if matching_files:
                    best = matching_files[-1]  # Latest version
                    new_path = best.name
                    if current_lora_path != new_path:
                        print(f"  {char_name} (id={char_id}): {current_lora_path or '(none)'} -> {new_path}")
                        if not dry_run:
                            cur.execute(
                                "UPDATE characters SET lora_path = %s WHERE id = %s",
                                (new_path, char_id)
                            )
                        updated_chars += 1
                break  # Only first match per character

    if not dry_run:
        conn.commit()

    conn.close()

    print()
    print("=== Summary ===")
    print(f"  Already registered: {skipped}")
    print(f"  Newly registered:   {registered}")
    print(f"  Character refs updated: {updated_chars}")
    print(f"  Total in DB now:    {skipped + registered + len(existing)}")

    if dry_run:
        print()
        print("  ** DRY RUN - no database changes made **")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    register_models(dry_run=dry_run)
