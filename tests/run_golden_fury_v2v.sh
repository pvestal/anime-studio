#!/usr/bin/env bash
# Golden regression test: Fury reference_v2v shot (Roxy Bedroom)
#
# Validates V2V pipeline for Fury project (no LoRA, character-from-clip):
#   DB shot → engine selector → FramePack V2V (LoRA-free) → post-process → DB update
#
# Usage: ./tests/run_golden_fury_v2v.sh
# Exit code: 0 = pass, 1 = fail

set -euo pipefail

API="http://localhost:8401/api"
DB_PASS="RP78eIrW7cI2jYvL5akt1yurE"
SHOT_ID="b3d1f939-f826-468d-8195-881916407416"
SCENE_ID="a624bc46-0b85-421d-839c-b0f57f5a7141"
EXPECTED_ENGINE="reference_v2v"
EXPECTED_PREFIX="fury_ep00_sc08_sh01_reference_v2v_b3d1f939"
MIN_DURATION=2  # seconds

echo "=== Golden Test: Fury reference_v2v (Roxy Bedroom) ==="

# ── Step 1: Reset shot to pending ─────────────────────────────────────
echo "Resetting shot $SHOT_ID..."
PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -q -c "
  UPDATE shots SET status = 'pending', error_message = NULL, output_video_path = NULL, generation_time_seconds = NULL
  WHERE id = '$SHOT_ID';
  UPDATE scenes SET generation_status = 'draft' WHERE id = '$SCENE_ID';"

# ── Step 2: Trigger generation ────────────────────────────────────────
echo "Triggering generation..."
RESP=$(curl -s -X POST "$API/scenes/$SCENE_ID/generate" -H "Content-Type: application/json")
MSG=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('message','error'))" 2>/dev/null || echo "fail")
if [[ "$MSG" != *"started"* ]]; then
    echo "FAIL: Generation did not start: $MSG"
    exit 1
fi
echo "  $MSG"

# ── Step 3: Poll for completion ───────────────────────────────────────
echo "Waiting for completion (timeout: 45 min)..."
TIMEOUT=2700
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    STATUS=$(PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -t -A -c "
      SELECT status FROM shots WHERE id = '$SHOT_ID';")

    if [ "$STATUS" = "completed" ]; then
        break
    elif [ "$STATUS" = "failed" ]; then
        ERR=$(PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -t -A -c "
          SELECT error_message FROM shots WHERE id = '$SHOT_ID';")
        echo "FAIL: Shot failed with: $ERR"
        exit 1
    fi

    sleep 30
    ELAPSED=$((ELAPSED + 30))
    printf "  %d min elapsed...\r" $((ELAPSED / 60))
done

if [ "$STATUS" != "completed" ]; then
    echo "FAIL: Timed out after $((TIMEOUT / 60)) minutes"
    exit 1
fi

# ── Step 4: Validate output ──────────────────────────────────────────
echo "Validating output..."
FAILURES=0

OUTPUT_PATH=$(PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -t -A -c "
  SELECT output_video_path FROM shots WHERE id = '$SHOT_ID';")
ENGINE=$(PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -t -A -c "
  SELECT video_engine FROM shots WHERE id = '$SHOT_ID';")
GEN_TIME=$(PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -t -A -c "
  SELECT generation_time_seconds FROM shots WHERE id = '$SHOT_ID';")

# Assert engine
if [ "$ENGINE" != "$EXPECTED_ENGINE" ]; then
    echo "  FAIL: engine=$ENGINE, expected=$EXPECTED_ENGINE"
    FAILURES=$((FAILURES + 1))
else
    echo "  OK: engine=$ENGINE"
fi

# Assert output file exists and is non-empty
if [ -z "$OUTPUT_PATH" ] || [ ! -f "$OUTPUT_PATH" ]; then
    echo "  FAIL: output file missing: $OUTPUT_PATH"
    FAILURES=$((FAILURES + 1))
else
    SIZE=$(stat -c%s "$OUTPUT_PATH" 2>/dev/null || echo "0")
    if [ "$SIZE" -lt 10000 ]; then
        echo "  FAIL: output file too small (${SIZE} bytes)"
        FAILURES=$((FAILURES + 1))
    else
        echo "  OK: output file exists ($(du -h "$OUTPUT_PATH" | cut -f1))"
    fi
fi

# Assert filename contains shot hash
if [[ "$OUTPUT_PATH" != *"$EXPECTED_PREFIX"* ]]; then
    echo "  FAIL: filename missing expected prefix ($EXPECTED_PREFIX)"
    FAILURES=$((FAILURES + 1))
else
    echo "  OK: shot hash in filename"
fi

# Assert duration
if [ -f "$OUTPUT_PATH" ]; then
    DURATION=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$OUTPUT_PATH" 2>/dev/null | cut -d. -f1)
    if [ "${DURATION:-0}" -lt "$MIN_DURATION" ]; then
        echo "  FAIL: duration=${DURATION}s, minimum=${MIN_DURATION}s"
        FAILURES=$((FAILURES + 1))
    else
        echo "  OK: duration=${DURATION}s"
    fi

    RES=$(ffprobe -v quiet -show_entries stream=width,height -of csv=p=0 "$OUTPUT_PATH" 2>/dev/null | head -1)
    if [ "$RES" != "544,704" ]; then
        echo "  WARN: resolution=$RES (expected 544,704)"
    else
        echo "  OK: resolution=544x704"
    fi
fi

# Assert generation_time_seconds
if [ -z "$GEN_TIME" ] || [ "$GEN_TIME" = "" ]; then
    echo "  WARN: generation_time_seconds not recorded"
else
    echo "  OK: generation_time_seconds=${GEN_TIME}s"
fi

# Assert no LoRA was used (Roxy has no FramePack LoRA)
# Check the most recent log entry for this shot
LORA_LOG=$(grep "$SHOT_ID" /opt/anime-studio/logs/anime-studio.log 2>/dev/null | grep -i "lora" | tail -1)
if [[ "$LORA_LOG" == *"rosa_framepack"* ]] || [[ "$LORA_LOG" == *"roxy_framepack"* ]]; then
    echo "  WARN: unexpected LoRA reference in logs: $LORA_LOG"
else
    echo "  OK: no incompatible LoRA attached"
fi

# ── Result ────────────────────────────────────────────────────────────
echo ""
if [ $FAILURES -gt 0 ]; then
    echo "RESULT: FAIL ($FAILURES assertions failed)"
    exit 1
else
    echo "RESULT: PASS — Fury reference_v2v golden test passed"
    exit 0
fi
