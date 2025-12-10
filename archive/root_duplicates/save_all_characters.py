#!/usr/bin/env python3
"""
Save all characters to database
Processes one at a time as per user testing methodology
"""
import sys
sys.path.insert(0, '/opt/tower-anime-production')

from character_db_adapter import CharacterDBAdapter
from pathlib import Path
import time

# Character mapping: (project_id, character_file, image_pattern)
CHARACTERS = [
    # Tokyo Debt Desire (project_id: 1) - photorealistic
    (1, 'tokyo_debt_desire/characters/takeshi_sato.json', 'takeshi_sato_tokyo_debt_512p_00001_.png'),
    (1, 'tokyo_debt_desire/characters/yuki_tanaka.json', 'yuki_tanaka_tokyo_debt_512p_00001_.png'),
    (1, 'tokyo_debt_desire/characters/rina_suzuki.json', 'rina_suzuki_tokyo_debt_512p_00001_.png'),

    # Cyberpunk Goblin Slayer (project_id: 2) - anime style
    (2, 'cyberpunk_goblin_slayer/characters/kai_nakamura.json', 'kai_nakamura_cyberpunk_512p_00001_.png'),
    (2, 'cyberpunk_goblin_slayer/characters/hiroshi_yamamoto.json', 'hiroshi_yamamoto_cyberpunk_512p_00001_.png'),
    (2, 'cyberpunk_goblin_slayer/characters/yuki_tanaka.json', 'yuki_tanaka_cyberpunk_512p_00001_.png'),
    (2, 'cyberpunk_goblin_slayer/characters/raze.json', 'raze_cyberpunk_512p_00001_.png'),
    (2, 'cyberpunk_goblin_slayer/characters/xyrax.json', 'xyrax_cyberpunk_512p_00001_.png'),
]

def main():
    adapter = CharacterDBAdapter()
    base_path = Path('/opt/tower-anime-production/workflows/projects')
    image_base = Path('/mnt/1TB-storage/ComfyUI/output')

    results = []
    failed = []

    print("=== Saving All Characters to Database ===\n")

    for i, (project_id, char_file, image_name) in enumerate(CHARACTERS, 1):
        char_path = base_path / char_file
        image_path = image_base / image_name

        # Get character name from file
        char_name = char_path.stem.replace('_', ' ').title()
        project_name = "Tokyo Debt" if project_id == 1 else "Cyberpunk Goblin Slayer"

        print(f"[{i}/{len(CHARACTERS)}] Processing: {char_name} ({project_name})")
        print(f"  Character file: {char_path}")
        print(f"  Image: {image_path}")

        # Check files exist
        if not char_path.exists():
            print(f"  ❌ Character file not found!")
            failed.append(f"{char_name} - character file missing")
            continue

        if not image_path.exists():
            print(f"  ⚠️  Image not found (will save without image)")
            image_str = None
        else:
            image_str = str(image_path)
            print(f"  ✓ Image found ({image_path.stat().st_size // 1024}KB)")

        # Save to database
        try:
            result = adapter.save_character_to_db(char_path, project_id, image_str)
            char_id = result.get('id')
            print(f"  ✅ Saved successfully (Character ID: {char_id})")
            results.append(f"{char_name} → ID {char_id}")

            # Brief pause between saves (respectful to database)
            if i < len(CHARACTERS):
                time.sleep(0.5)

        except Exception as e:
            print(f"  ❌ Failed: {e}")
            failed.append(f"{char_name} - {str(e)[:50]}")

        print()

    # Summary
    print("\n" + "="*60)
    print(f"COMPLETE: {len(results)}/{len(CHARACTERS)} characters saved")
    print("="*60)

    if results:
        print("\n✅ Successfully saved:")
        for r in results:
            print(f"  - {r}")

    if failed:
        print("\n❌ Failed to save:")
        for f in failed:
            print(f"  - {f}")

    return len(failed) == 0

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
