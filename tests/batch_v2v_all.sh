#!/usr/bin/env bash
# Batch V2V generation — triggers all scenes with pending reference_v2v shots
# Usage: ./tests/batch_v2v_all.sh
#
# Polls each scene until complete, then starts the next.
# Safe to Ctrl-C; shots stay in their current state.

set -euo pipefail
API="http://localhost:8401/api"
DB_PASS="RP78eIrW7cI2jYvL5akt1yurE"

# Get all scene IDs with pending V2V shots
SCENES=$(PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -t -A -c "
SELECT DISTINCT s.id
FROM scenes s
JOIN shots sh ON sh.scene_id = s.id
WHERE sh.video_engine = 'reference_v2v' AND sh.status = 'pending'
ORDER BY s.id;")

if [ -z "$SCENES" ]; then
  echo "No pending V2V scenes found."
  exit 0
fi

TOTAL=$(echo "$SCENES" | wc -l)
echo "=== Batch V2V: $TOTAL scenes with pending shots ==="

IDX=0
for SCENE_ID in $SCENES; do
  IDX=$((IDX + 1))

  # Get scene info
  INFO=$(PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -t -A -c "
    SELECT s.title || ' (' || p.name || ')' || ' — ' || count(sh.id) || ' shots'
    FROM scenes s
    JOIN shots sh ON sh.scene_id = s.id
    JOIN projects p ON s.project_id = p.id
    WHERE s.id = '$SCENE_ID' AND sh.video_engine = 'reference_v2v' AND sh.status = 'pending'
    GROUP BY s.title, p.name;")

  echo ""
  echo "[$IDX/$TOTAL] $INFO"
  echo "  Scene: $SCENE_ID"

  # Check if scene is already generating
  STATUS=$(PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -t -A -c "
    SELECT generation_status FROM scenes WHERE id = '$SCENE_ID';")

  if [ "$STATUS" = "generating" ]; then
    echo "  Already generating, waiting..."
  else
    # Reset scene status to allow generation
    PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -q -c "
      UPDATE scenes SET generation_status = 'draft' WHERE id = '$SCENE_ID' AND generation_status != 'draft';" 2>/dev/null

    # Trigger generation
    RESP=$(curl -s -X POST "$API/scenes/$SCENE_ID/generate" -H "Content-Type: application/json")
    MSG=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('message','error'))" 2>/dev/null || echo "error")
    echo "  $MSG"
  fi

  # Poll until all V2V shots in this scene are done (completed or failed)
  while true; do
    PENDING=$(PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -t -A -c "
      SELECT count(*) FROM shots sh
      JOIN scenes s ON sh.scene_id = s.id
      WHERE s.id = '$SCENE_ID' AND sh.video_engine = 'reference_v2v'
        AND sh.status NOT IN ('completed', 'failed');")

    if [ "$PENDING" -eq 0 ]; then
      # Report results
      COMPLETED=$(PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -t -A -c "
        SELECT count(*) FROM shots sh WHERE sh.scene_id = '$SCENE_ID'
          AND sh.video_engine = 'reference_v2v' AND sh.status = 'completed';")
      FAILED=$(PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -t -A -c "
        SELECT count(*) FROM shots sh WHERE sh.scene_id = '$SCENE_ID'
          AND sh.video_engine = 'reference_v2v' AND sh.status = 'failed';")
      echo "  Done: $COMPLETED completed, $FAILED failed"
      break
    fi

    sleep 30
  done
done

echo ""
echo "=== Batch V2V complete ==="
# Summary
PGPASSWORD="$DB_PASS" psql -h localhost -U patrick -d anime_production -t -c "
SELECT sh.status, count(*) as count
FROM shots sh
WHERE sh.video_engine = 'reference_v2v'
GROUP BY sh.status
ORDER BY sh.status;"
