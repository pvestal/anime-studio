#!/bin/bash
# Run all TDD training image batches sequentially
# Recovers orphaned images between batches
set -e

cd /opt/anime-studio
source venv/bin/activate

echo "============================================"
echo "  TDD Full Training Image Generation"
echo "  80 images: 4 chars × 20 images each"
echo "============================================"
echo ""

# Recover any orphaned ComfyUI images (generated but not copied due to polling timeouts)
recover_orphans() {
    echo "[RECOVERY] Checking for orphaned ComfyUI images..."
    for slug in mei_kobayashi rina_suzuki takeshi_sato yuki_tanaka; do
        dest="datasets/${slug}/images"
        mkdir -p "$dest"
        for src in /opt/ComfyUI/output/tokyodebtdesire_${slug}_*_00001_.png; do
            [ -f "$src" ] || continue
            base=$(basename "$src")
            # Check if already copied (by checking if any dataset image matches the ComfyUI timestamp)
            ts=$(stat -c %Y "$src")
            already_copied=false
            for existing in "$dest"/gen_${slug}_*.png; do
                [ -f "$existing" ] || continue
                existing_ts=$(stat -c %Y "$existing")
                diff=$((ts - existing_ts))
                if [ ${diff#-} -lt 5 ]; then
                    already_copied=true
                    break
                fi
            done
            if [ "$already_copied" = false ]; then
                new_name="gen_${slug}_$(date -d @$ts +%Y%m%d_%H%M%S)_recovered.png"
                cp "$src" "$dest/$new_name"
                echo "  Recovered: $new_name"
            fi
        done
    done
    echo "[RECOVERY] Done."
}

echo "=== BATCH 1/3: Scene-based NSFW (10/char) ==="
echo "  (Already running or completed from initial batch)"
echo ""

echo "=== BATCH 2/3: Expression Progression (5/char) ==="
python3 scripts/batch_expression_progression.py 2>&1 | tee -a /tmp/batch_expression_tdd.log
recover_orphans
echo ""

echo "=== BATCH 3/3: Identity Anchors (5/char) ==="
python3 scripts/batch_identity_anchors.py 2>&1 | tee -a /tmp/batch_identity_tdd.log
recover_orphans
echo ""

echo "============================================"
echo "  ALL BATCHES COMPLETE"
echo "============================================"
echo ""
echo "Image counts per character:"
for slug in mei_kobayashi rina_suzuki takeshi_sato yuki_tanaka; do
    count=$(ls datasets/${slug}/images/gen_${slug}_20260222*.png 2>/dev/null | wc -l)
    echo "  ${slug}: ${count} images generated today"
done
