#!/bin/bash
# Vision review loop — runs every 10 minutes until no pending images remain
# Processes 200 images per pass across all Cyberpunk Goblin Slayer characters
# Auto-rejects < 0.4, auto-approves >= 0.8, updates captions on approve

PROJECT="Cyberpunk Goblin Slayer: Neon Shadows"
BATCH_SIZE=200
INTERVAL=600  # 10 minutes
API="http://localhost:8401/api/visual/approval/vision-review"

echo "$(date) — Vision review loop started for: $PROJECT"
echo "Batch size: $BATCH_SIZE, Interval: ${INTERVAL}s"
echo "---"

while true; do
    # Count pending images for this project
    PENDING=$(curl -s 'http://localhost:8401/api/training/approval/pending' | \
        python3 -c "
import sys, json
d = json.load(sys.stdin)
count = sum(1 for img in d.get('pending_images',[]) if img.get('project_name','') == '$PROJECT')
print(count)
" 2>/dev/null)

    echo "$(date) — Pending images: $PENDING"

    if [ "$PENDING" -eq 0 ] 2>/dev/null; then
        echo "$(date) — No pending images left. Checking if ComfyUI queue is empty..."
        QUEUE=$(curl -s http://localhost:8188/queue | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(len(d.get('queue_running',[])) + len(d.get('queue_pending',[])))
" 2>/dev/null)
        if [ "$QUEUE" -eq 0 ] 2>/dev/null; then
            echo "$(date) — Queue empty and no pending images. Done!"
            break
        fi
        echo "$(date) — Queue still has $QUEUE jobs, waiting for more images..."
        sleep $INTERVAL
        continue
    fi

    echo "$(date) — Running vision review on $BATCH_SIZE images..."
    RESULT=$(curl -s -X POST "$API" \
        -H "Content-Type: application/json" \
        -d "{
            \"project_name\": \"$PROJECT\",
            \"max_images\": $BATCH_SIZE,
            \"auto_reject_threshold\": 0.4,
            \"auto_approve_threshold\": 0.8,
            \"update_captions\": true,
            \"regenerate\": false
        }")

    # Parse results
    python3 -c "
import json, sys
try:
    d = json.loads('''$RESULT''')
    reviewed = d.get('reviewed', 0)
    approved = d.get('auto_approved', 0)
    rejected = d.get('auto_rejected', 0)
    pending = reviewed - approved - rejected
    print(f'  Reviewed: {reviewed}, Auto-approved: {approved}, Auto-rejected: {rejected}, Manual review: {pending}')
except:
    print(f'  Response: {sys.argv[0] if len(sys.argv) > 1 else \"parse error\"} ')
" 2>/dev/null

    echo "---"
    sleep $INTERVAL
done

echo "$(date) — Vision review loop complete!"
