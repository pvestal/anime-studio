#!/usr/bin/env bash
# Anime Studio Pre-Flight Checklist
#
# Verifies infrastructure + engine readiness before running a new project.
# Run this BEFORE starting any new batch generation.
#
# Exit 0 = all green (safe to generate), 1 = failures found
#
# Usage: ./tests/smoke_test.sh

API="http://localhost:8401"
COMFYUI="http://127.0.0.1:8188"
PASS=0
FAIL=0
WARN=0

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

warn() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  [OK] $label"
        PASS=$((PASS + 1))
    else
        echo "  [WARN] $label"
        WARN=$((WARN + 1))
    fi
}

echo "=== Anime Studio Pre-Flight Checklist ==="
echo ""

# ── Core Infrastructure ──────────────────────────────────────────────
echo "--- Core Infrastructure ---"
check "API health" curl -sf "$API/api/system/health"
check "DB health" curl -sf "$API/api/system/db-health"
check "GPU status endpoint" curl -sf "$API/api/system/gpu/status"
check "Project list" bash -c "curl -sf '$API/api/story/projects' | python3 -c 'import sys,json; d=json.load(sys.stdin); assert len(d)>0'"
check "Scenes endpoint" curl -sf "$API/api/scenes/?project_id=57"
check "CLIP cache dir" test -d /home/patrick/.cache/huggingface
check "Log file exists" test -f /opt/anime-studio/logs/anime-studio.log
check "Datasets populated" bash -c "ls /opt/anime-studio/datasets/*/images/*.png 2>/dev/null | head -1 | grep -q '.'"

# ── External Services ────────────────────────────────────────────────
echo ""
echo "--- External Services ---"
check "ComfyUI reachable" curl -sf "$COMFYUI/system_stats"
check "Ollama reachable" curl -sf "http://localhost:11434/api/tags"

# ── Engine: FramePack I2V ────────────────────────────────────────────
echo ""
echo "--- Engine: FramePack I2V ---"
check "DiT model" test -f /opt/ComfyUI/models/diffusion_models/FramePackI2V_HY_fp8_e4m3fn.safetensors
check "VAE (HunyuanVideo)" test -f /opt/ComfyUI/models/vae/hunyuan_video_vae_bf16.safetensors
check "CLIP-L text encoder" test -f /opt/ComfyUI/models/clip/clip_l.safetensors
check "LLaMA text encoder" test -f /opt/ComfyUI/models/text_encoders/llava_llama3_fp16.safetensors
check "SigCLIP vision encoder" test -f /opt/ComfyUI/models/clip_vision/sigclip_vision_patch14_384.safetensors
# Check FramePack custom node is loaded
check "FramePack node loaded" bash -c "curl -sf '$COMFYUI/object_info/FramePackSampler' | python3 -c 'import sys,json; json.load(sys.stdin)'"

# ── Engine: reference_v2v (FramePack V2V) ────────────────────────────
echo ""
echo "--- Engine: reference_v2v ---"
# V2V reuses FramePack models (checked above) + VHS video loader
check "VHS_LoadVideoPath node" bash -c "curl -sf '$COMFYUI/object_info/VHS_LoadVideoPath' | python3 -c 'import sys,json; json.load(sys.stdin)'"
check "FramePackLoraSelect node" bash -c "curl -sf '$COMFYUI/object_info/FramePackLoraSelect' | python3 -c 'import sys,json; json.load(sys.stdin)'"

# ── Engine: Wan22 I2V ────────────────────────────────────────────────
echo ""
echo "--- Engine: Wan22 I2V ---"
warn "Wan 2.2 5B GGUF model" bash -c "ls /opt/ComfyUI/models/diffusion_models/*wan*5b* /opt/ComfyUI/models/diffusion_models/*Wan*5B* 2>/dev/null | head -1 | grep -q '.'"
warn "Wan22 node loaded" bash -c "curl -sf '$COMFYUI/object_info/WanImageToVideo' 2>/dev/null | python3 -c 'import sys,json; json.load(sys.stdin)' 2>/dev/null || curl -sf '$COMFYUI/object_info/Wan21_I2V' | python3 -c 'import sys,json; json.load(sys.stdin)'"

# ── ComfyUI Queue Health ─────────────────────────────────────────────
echo ""
echo "--- ComfyUI Queue ---"
check "Queue accessible" bash -c "curl -sf '$COMFYUI/queue' | python3 -c 'import sys,json; json.load(sys.stdin)'"
QUEUE_STATE=$(curl -sf "$COMFYUI/queue" 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
r = len(d.get('queue_running',[]))
p = len(d.get('queue_pending',[]))
print(f'{r} running, {p} pending')
" 2>/dev/null || echo "unknown")
echo "  [INFO] Queue: $QUEUE_STATE"

# ── Summary ──────────────────────────────────────────────────────────
echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed, $WARN warnings"

if [ "$FAIL" -gt 0 ]; then
    echo "STATUS: NOT READY — fix failures before generating"
    exit 1
fi
if [ "$WARN" -gt 0 ]; then
    echo "STATUS: READY (with warnings — some engines may not work)"
    exit 0
fi
echo "STATUS: ALL GREEN — safe to generate"
