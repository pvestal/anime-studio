#!/usr/bin/env bash
# Prompt test grid for Fury project (Wan22 + V2V)
#
# Tests multiple actions with fixed character identity, engine, and LoRA stack.
# Results stored in prompt_tests table for comparison.
#
# Usage: ./tests/run_prompt_grid_fury.sh [engine_override]
# Example: ./tests/run_prompt_grid_fury.sh reference_v2v

set -euo pipefail

API="http://localhost:8401/api"
ENGINE="${1:-framepack}"
PROJECT_ID=57  # Fury

echo "=== Fury Prompt Test Grid ==="
echo "Engine: $ENGINE"
echo ""

# Define action grid — each action tests a specific pose/scene type
PAYLOAD=$(cat <<'EOF'
{
  "project_id": 57,
  "character_slugs": ["roxy"],
  "actions": [
    {"label": "standing_pose", "prompt": "standing confidently, hands on hips, urban alley background, neon lighting, full body"},
    {"label": "bedroom_scene", "prompt": "lying on bed, looking at viewer, dim warm lighting, bedroom background, medium shot"},
    {"label": "action_scene", "prompt": "running through rain, leather jacket flowing, wet fur, dynamic pose, night city background"},
    {"label": "close_portrait", "prompt": "face close-up, smirking expression, neon green eye glow, dramatic lighting"},
    {"label": "seductive_pose", "prompt": "leaning against wall, one leg bent, looking over shoulder, sultry expression, dim lighting"}
  ],
  "seeds": [42, 1337, 7777],
  "camera_setups": ["medium", "close_up"],
  "engine_override": "ENGINE_PLACEHOLDER"
}
EOF
)

# Replace engine placeholder
PAYLOAD="${PAYLOAD//ENGINE_PLACEHOLDER/$ENGINE}"

echo "Submitting grid: 5 actions × 3 seeds × 2 cameras = 30 tests"
RESP=$(curl -s -X POST "$API/testing/generate-prompt-grid" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

BATCH_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('batch_id','error'))" 2>/dev/null || echo "fail")
TOTAL=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_tests',0))" 2>/dev/null || echo "0")

if [ "$BATCH_ID" = "fail" ] || [ "$BATCH_ID" = "error" ]; then
    echo "FAIL: Could not start grid"
    echo "$RESP"
    exit 1
fi

echo "Batch: $BATCH_ID ($TOTAL tests queued)"
echo ""

# Poll for completion
echo "Polling for completion..."
TIMEOUT=10800  # 3 hours for full grid
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    BATCH=$(curl -s "$API/testing/batches/$BATCH_ID")
    COMPLETED=$(echo "$BATCH" | python3 -c "
import sys, json
d = json.load(sys.stdin)
tests = d.get('tests', [])
c = sum(1 for t in tests if t.get('status') == 'completed')
f = sum(1 for t in tests if t.get('status') == 'failed')
p = sum(1 for t in tests if t.get('status') == 'pending')
print(f'{c} completed, {f} failed, {p} pending')
" 2>/dev/null || echo "unknown")

    printf "  %d min — %s\r" $((ELAPSED / 60)) "$COMPLETED"

    # Check if all done
    PENDING=$(echo "$BATCH" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(sum(1 for t in d.get('tests', []) if t.get('status') == 'pending'))
" 2>/dev/null || echo "1")

    if [ "$PENDING" = "0" ]; then
        break
    fi

    sleep 60
    ELAPSED=$((ELAPSED + 60))
done

echo ""
echo ""

# Print results summary
echo "=== Results ==="
curl -s "$API/testing/batches/$BATCH_ID" | python3 -c "
import sys, json
d = json.load(sys.stdin)
tests = d.get('tests', [])
completed = [t for t in tests if t.get('status') == 'completed']
failed = [t for t in tests if t.get('status') == 'failed']
print(f'Total: {len(tests)}, Completed: {len(completed)}, Failed: {len(failed)}')
print()
if failed:
    print('--- Failures ---')
    for t in failed:
        print(f\"  {t['action_label']} (seed={t['seed']}, cam={t['camera_setup']}): {t.get('error_message', 'unknown')}\")
    print()
print('--- Completed ---')
for t in completed:
    time_s = t.get('generation_time_seconds', 0)
    time_m = time_s / 60 if time_s else 0
    print(f\"  {t['action_label']} seed={t['seed']} cam={t['camera_setup']}: {time_m:.1f}min {t.get('output_path', 'no output')}\")
"

echo ""
echo "Batch ID: $BATCH_ID"
echo "Score results: curl -s -X POST '$API/testing/batches/$BATCH_ID/score?test_id=ID&score=8.0&notes=good'"
