#!/usr/bin/env python3
"""
Link character images to database records via SQL update
"""
import psycopg2
from pathlib import Path

# Character ID to image path mapping
IMAGE_LINKS = {
    # Tokyo Debt Desire (photorealistic) - using latest photorealistic versions
    7: '/mnt/1TB-storage/ComfyUI/output/mei_kobayashi_photorealistic_512p_00001_.png',  # Mei (already has image)
    8: '/mnt/1TB-storage/ComfyUI/output/takeshi_sato_photorealistic_FIXED_00001_.png',  # Takeshi (regenerating)
    9: '/mnt/1TB-storage/ComfyUI/output/yuki_tanaka_photorealistic_512p_00001_.png',    # Yuki
    10: '/mnt/1TB-storage/ComfyUI/output/rina_suzuki_photorealistic_512p_00001_.png',   # Rina (already has image)

    # Cyberpunk Goblin Slayer (anime style)
    3: '/mnt/1TB-storage/ComfyUI/output/kai_nakamura_512p_00001_.png',                  # Kai (pre-existing)
    11: '/mnt/1TB-storage/ComfyUI/output/hiroshi_yamamoto_goblin_slayer_512p_00001_.png',  # Hiroshi
    12: '/mnt/1TB-storage/ComfyUI/output/yuki_tanaka_goblin_slayer_512p_00001_.png',    # Yuki (hacker)
    13: '/mnt/1TB-storage/ComfyUI/output/raze_goblin_slayer_512p_00001_.png',           # Raze
    14: '/mnt/1TB-storage/ComfyUI/output/xyrax_goblin_slayer_512p_00001_.png',          # Xyrax
}

def link_images():
    """Update character visual_traits with image paths"""

    # Connect to PostgreSQL
    conn = psycopg2.connect(
        host='localhost',
        database='anime_production',
        user='patrick'
    )
    cur = conn.cursor()

    print("=== Linking Character Images to Database ===\n")

    linked = 0
    skipped = 0
    failed = 0

    for char_id, image_path in IMAGE_LINKS.items():
        # Check if image exists
        if not Path(image_path).exists():
            if 'FIXED' in image_path:
                print(f"[{char_id}] ⏳ Skipping Takeshi - regenerating")
                skipped += 1
                continue
            else:
                print(f"[{char_id}] ❌ Image not found: {Path(image_path).name}")
                failed += 1
                continue

        # Update visual_traits with image path
        try:
            # Use jsonb_set to add/update generated_image key
            cur.execute("""
                UPDATE bible_characters
                SET visual_traits = jsonb_set(
                    COALESCE(visual_traits, '{}'::jsonb),
                    '{generated_image}',
                    %s::jsonb,
                    true
                )
                WHERE id = %s
                RETURNING name
            """, (f'"{image_path}"', char_id))

            result = cur.fetchone()
            if result:
                char_name = result[0]
                img_filename = Path(image_path).name
                file_size = Path(image_path).stat().st_size // 1024
                print(f"[{char_id}] ✅ {char_name:20s} → {img_filename} ({file_size}KB)")
                linked += 1
            else:
                print(f"[{char_id}] ⚠️  Character not found in database")
                failed += 1

        except Exception as e:
            print(f"[{char_id}] ❌ Failed: {e}")
            failed += 1

    # Commit changes
    conn.commit()
    cur.close()
    conn.close()

    # Summary
    print(f"\n{'='*60}")
    print(f"✅ Linked: {linked}")
    print(f"⏳ Skipped: {skipped} (regenerating)")
    print(f"❌ Failed: {failed}")
    print(f"{'='*60}")

    return failed == 0

if __name__ == '__main__':
    import sys
    success = link_images()
    sys.exit(0 if success else 1)
