#!/usr/bin/env bash
# Prompt test grid for Tokyo Debt Desire (photo-real SD1.5/XL)
#
# Tests Mei and Rina with photo-realistic engine settings.
# Results stored in prompt_tests table for comparison.
#
# Usage: ./tests/run_prompt_grid_tdd.sh [engine_override]

set -euo pipefail

API="http://localhost:8401/api"
ENGINE="${1:-framepack}"
PROJECT_ID=24  # Tokyo Debt Desire

echo "=== TDD Prompt Test Grid ==="
echo "Engine: $ENGINE"
echo ""

# Mei Kobayashi grid
echo "--- Mei Kobayashi ---"
MEI_PAYLOAD=$(cat <<EOF
{
  "project_id": 24,
  "character_slugs": ["mei_kobayashi"],
  "actions": [
    {"label": "bedroom_intimate", "prompt": "lying on bed, dim lighting, looking at viewer, realistic style, warm tones"},
    {"label": "standing_apartment", "prompt": "standing in small Tokyo apartment, casual outfit, natural lighting, window background"},
    {"label": "close_face", "prompt": "face close-up, soft expression, natural makeup, warm lighting, portrait"},
    {"label": "shower_scene", "prompt": "in shower, water streaming, steam, wet hair, natural lighting"}
  ],
  "seeds": [42, 1337],
  "camera_setups": ["medium", "close_up"],
  "engine_override": "$ENGINE"
}
EOF
)

RESP=$(curl -s -X POST "$API/testing/generate-prompt-grid" \
  -H "Content-Type: application/json" \
  -d "$MEI_PAYLOAD")
BATCH1=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('batch_id','error'))" 2>/dev/null)
TOTAL1=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_tests',0))" 2>/dev/null)
echo "Mei batch: $BATCH1 ($TOTAL1 tests)"

# Rina Suzuki grid
echo "--- Rina Suzuki ---"
RINA_PAYLOAD=$(cat <<EOF
{
  "project_id": 24,
  "character_slugs": ["rina_suzuki"],
  "actions": [
    {"label": "bedroom_pose", "prompt": "sitting on edge of bed, short hair, casual wear, warm apartment lighting"},
    {"label": "office_scene", "prompt": "at office desk, professional outfit, fluorescent lighting, focused expression"},
    {"label": "bar_scene", "prompt": "sitting at bar, night scene, neon lighting, drink in hand, relaxed pose"}
  ],
  "seeds": [42, 1337],
  "camera_setups": ["medium"],
  "engine_override": "$ENGINE"
}
EOF
)

RESP=$(curl -s -X POST "$API/testing/generate-prompt-grid" \
  -H "Content-Type: application/json" \
  -d "$RINA_PAYLOAD")
BATCH2=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('batch_id','error'))" 2>/dev/null)
TOTAL2=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_tests',0))" 2>/dev/null)
echo "Rina batch: $BATCH2 ($TOTAL2 tests)"

echo ""
echo "=== Batches Started ==="
echo "Mei:  $BATCH1 ($TOTAL1 tests)"
echo "Rina: $BATCH2 ($TOTAL2 tests)"
echo ""
echo "Monitor: curl -s $API/testing/batches | python3 -m json.tool"
