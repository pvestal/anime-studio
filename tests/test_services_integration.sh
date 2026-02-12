#!/bin/bash
# =================================================================
# Tower Anime + LoRA Studio Integration Tests
# Tests: services, Vault, nginx routing, API endpoints, frontends
# =================================================================

PASS=0
FAIL=0
WARN=0
RESULTS=""

pass() { PASS=$((PASS + 1)); RESULTS+="  PASS  $1\n"; }
fail() { FAIL=$((FAIL + 1)); RESULTS+="  FAIL  $1\n"; }
warn() { WARN=$((WARN + 1)); RESULTS+="  WARN  $1\n"; }

echo ""
echo "========================================================"
echo "  TOWER SERVICES INTEGRATION TEST"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "========================================================"

# ------- Service Health -------
echo -e "\n--- Service Status ---"

if systemctl is-active --quiet tower-anime-production; then
    pass "tower-anime-production service: active"
else
    fail "tower-anime-production service: NOT running"
fi

if systemctl is-active --quiet tower-lora-studio; then
    pass "tower-lora-studio service: active"
else
    fail "tower-lora-studio service: NOT running"
fi

if systemctl is-active --quiet nginx; then
    pass "nginx: active"
else
    fail "nginx: NOT running"
fi

if systemctl is-active --quiet vault; then
    pass "vault: active (unsealed)"
else
    fail "vault: NOT running"
fi

# ------- Vault Integration -------
echo -e "\n--- Vault Integration ---"

anime_log=$(journalctl -u tower-anime-production --no-pager --boot 2>/dev/null)
if echo "$anime_log" | grep -q "Loaded secret from Vault"; then
    pass "Anime API loads credentials from Vault"
else
    fail "Anime API NOT using Vault (check logs)"
fi

lora_log=$(journalctl -u tower-lora-studio --no-pager --boot 2>/dev/null)
if echo "$lora_log" | grep -q "Loaded database credentials from Vault"; then
    pass "LoRA Studio loads credentials from Vault"
else
    fail "LoRA Studio NOT using Vault (check logs)"
fi

# Verify no hardcoded passwords in source
if grep -q "tower_echo_brain_secret_key_2025" /opt/tower-anime-production/api/main.py 2>/dev/null; then
    fail "main.py still has old hardcoded password"
else
    pass "main.py: no hardcoded password (uses Vault)"
fi

if grep -q "tower_echo_brain_secret_key_2025" /opt/tower-anime-production/training/lora-studio/src/dataset_approval_api.py 2>/dev/null; then
    fail "dataset_approval_api.py still has old hardcoded password"
else
    pass "dataset_approval_api.py: no hardcoded password (uses Vault)"
fi

# ------- Direct API (bypass nginx) -------
echo -e "\n--- Direct API Endpoints ---"

resp=$(curl -s http://127.0.0.1:8328/api/anime/health 2>/dev/null)
if echo "$resp" | grep -q '"healthy"'; then
    pass "Anime API health (port 8328): healthy"
else
    fail "Anime API health (port 8328): $resp"
fi

resp=$(curl -s http://127.0.0.1:8328/api/anime/projects 2>/dev/null)
if echo "$resp" | grep -q '"name"'; then
    count=$(echo "$resp" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
    pass "Anime API projects: $count projects returned"
else
    fail "Anime API projects: no data"
fi

resp=$(curl -s http://127.0.0.1:8401/api/lora/health 2>/dev/null)
if echo "$resp" | grep -q '"healthy"'; then
    pass "LoRA Studio health (port 8401): healthy"
else
    fail "LoRA Studio health (port 8401): $resp"
fi

resp=$(curl -s http://127.0.0.1:8401/api/lora/characters 2>/dev/null)
if echo "$resp" | grep -q '"characters"'; then
    count=$(echo "$resp" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['characters']))" 2>/dev/null)
    pass "LoRA Studio characters: $count characters returned"
else
    fail "LoRA Studio characters: no data"
fi

resp=$(curl -s http://127.0.0.1:8401/api/lora/approval/pending 2>/dev/null)
if echo "$resp" | grep -q '"pending_images"'; then
    pass "LoRA Studio pending approvals: endpoint works"
else
    fail "LoRA Studio pending approvals: $resp"
fi

resp=$(curl -s http://127.0.0.1:8401/api/lora/training/jobs 2>/dev/null)
if echo "$resp" | grep -q '"training_jobs"'; then
    pass "LoRA Studio training jobs: endpoint works"
else
    fail "LoRA Studio training jobs: $resp"
fi

# ------- Nginx Proxied Endpoints -------
echo -e "\n--- Nginx Proxied API (HTTPS) ---"

resp=$(curl -sk https://localhost/api/anime/health 2>/dev/null)
if echo "$resp" | grep -q '"healthy"'; then
    pass "Nginx -> Anime API /api/anime/health"
else
    fail "Nginx -> Anime API: $resp"
fi

resp=$(curl -sk https://localhost/api/anime/projects 2>/dev/null)
if echo "$resp" | grep -q '"name"'; then
    pass "Nginx -> Anime API /api/anime/projects"
else
    fail "Nginx -> Anime API projects: no data"
fi

resp=$(curl -sk https://localhost/api/lora/health 2>/dev/null)
if echo "$resp" | grep -q '"healthy"'; then
    pass "Nginx -> LoRA Studio /api/lora/health"
else
    fail "Nginx -> LoRA Studio health: $resp"
fi

resp=$(curl -sk https://localhost/api/lora/characters 2>/dev/null)
if echo "$resp" | grep -q '"characters"'; then
    pass "Nginx -> LoRA Studio /api/lora/characters"
else
    fail "Nginx -> LoRA Studio characters: no data"
fi

resp=$(curl -sk https://localhost/api/lora/approval/pending 2>/dev/null)
if echo "$resp" | grep -q '"pending_images"'; then
    pass "Nginx -> LoRA Studio /api/lora/approval/pending"
else
    fail "Nginx -> LoRA Studio pending: $resp"
fi

resp=$(curl -sk https://localhost/api/lora/training/jobs 2>/dev/null)
if echo "$resp" | grep -q '"training_jobs"'; then
    pass "Nginx -> LoRA Studio /api/lora/training/jobs"
else
    fail "Nginx -> LoRA Studio training: $resp"
fi

# ------- Frontend Serving -------
echo -e "\n--- Frontend Serving ---"

resp=$(curl -sk https://localhost/anime/ 2>/dev/null)
if echo "$resp" | grep -q "Anime Studio"; then
    pass "Anime frontend loads at /anime/"
else
    fail "Anime frontend at /anime/: not loading"
fi

# Check assets have correct base path
if echo "$resp" | grep -q '/anime/assets/'; then
    pass "Anime frontend: assets use /anime/ base path"
else
    fail "Anime frontend: assets NOT using /anime/ base path"
fi

resp=$(curl -sk https://localhost/lora-studio/ 2>/dev/null)
if echo "$resp" | grep -q "LoRA"; then
    pass "LoRA Studio frontend loads at /lora-studio/"
else
    fail "LoRA Studio frontend at /lora-studio/: not loading"
fi

if echo "$resp" | grep -q '/lora-studio/assets/'; then
    pass "LoRA Studio frontend: assets use /lora-studio/ base path"
else
    fail "LoRA Studio frontend: assets NOT using /lora-studio/ base path"
fi

# Check JS/CSS assets actually serve (200)
anime_js=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost/anime/assets/index-CWsU75hU.js 2>/dev/null)
if [ "$anime_js" = "200" ]; then
    pass "Anime JS bundle: HTTP 200"
else
    fail "Anime JS bundle: HTTP $anime_js"
fi

lora_js=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost/lora-studio/assets/index-CdgW5GUc.js 2>/dev/null)
if [ "$lora_js" = "200" ]; then
    pass "LoRA Studio JS bundle: HTTP 200"
else
    fail "LoRA Studio JS bundle: HTTP $lora_js"
fi

# ------- Vault Secret Freshness -------
echo -e "\n--- Vault Secret Verification ---"

vault_check=$(VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=${VAULT_TOKEN:-} vault kv get -field=password secret/anime/database 2>/dev/null)
if [ "$vault_check" = "${DB_PASSWORD:-}" ]; then
    pass "Vault secret/anime/database: correct password stored"
else
    fail "Vault secret/anime/database: wrong password ($vault_check)"
fi

vault_tower=$(VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=${VAULT_TOKEN:-} vault kv get -field=password secret/tower/database 2>/dev/null)
if [ "$vault_tower" = "${DB_PASSWORD:-}" ]; then
    pass "Vault secret/tower/database: correct password stored"
else
    fail "Vault secret/tower/database: wrong password"
fi

# ------- Database Connectivity (proves Vault password works) -------
echo -e "\n--- Database Connectivity ---"

db_check=$(PGPASSWORD=${DB_PASSWORD:-} psql -h localhost -U patrick -d anime_production -c "SELECT count(*) FROM projects;" -t 2>/dev/null | tr -d ' ')
if [ -n "$db_check" ] && [ "$db_check" -gt 0 ] 2>/dev/null; then
    pass "PostgreSQL anime_production: $db_check projects (Vault password works)"
else
    fail "PostgreSQL anime_production: connection failed"
fi

# ------- Summary -------
echo ""
echo "========================================================"
echo "  RESULTS"
echo "========================================================"
echo -e "$RESULTS"
echo "--------------------------------------------------------"
TOTAL=$((PASS + FAIL + WARN))
echo "  Total: $TOTAL | Passed: $PASS | Failed: $FAIL | Warnings: $WARN"
echo ""

if [ $FAIL -eq 0 ]; then
    echo "  ALL TESTS PASSED"
else
    echo "  $FAIL TEST(S) FAILED"
fi
echo "========================================================"

exit $FAIL
