#!/usr/bin/env bash
# Anime Studio smoke test — verifies core infrastructure is healthy.
# Exit 0 if all green, 1 if any check fails.

API="http://localhost:8401"
PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  [OK] $label"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $label"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Anime Studio Smoke Test ==="

# 1. Service health
check "API health" curl -sf "$API/api/system/health"

# 2. DB health
check "DB health" curl -sf "$API/api/system/db-health"

# 3. GPU status endpoint responds
check "GPU status endpoint" curl -sf "$API/api/system/gpu/status"

# 4. Project list returns data
check "Project list" bash -c "curl -sf '$API/api/story/projects' | python3 -c 'import sys,json; d=json.load(sys.stdin); assert len(d)>0'"

# 5. Scenes endpoint responds
check "Scenes endpoint" curl -sf "$API/api/scenes/?project_id=57"

# 6. CLIP model cache directory exists
check "CLIP cache dir" test -d /home/patrick/.cache/huggingface

# 7. ComfyUI reachable
check "ComfyUI reachable" curl -sf "http://127.0.0.1:8188/system_stats"

# 8. Ollama reachable
check "Ollama reachable" curl -sf "http://localhost:11434/api/tags"

# 9. Log file exists and recent
check "Log file exists" test -f /opt/anime-studio/logs/anime-studio.log

# 10. Datasets directory has characters
check "Datasets populated" bash -c "ls /opt/anime-studio/datasets/*/images/*.png 2>/dev/null | head -1 | grep -q '.'"

echo ""
echo "Results: $PASS passed, $FAIL failed"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
echo "All checks passed."
