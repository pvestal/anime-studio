#!/usr/bin/env bash
# Setup voice cloning engines (GPT-SoVITS + RVC v2) for LoRA Studio voice pipeline.
# Each engine runs in its own venv to avoid dependency conflicts.
set -euo pipefail

echo "=== Tower Voice Engine Setup ==="

# --- GPT-SoVITS (fast prototyping: 5s min audio, 5-10min training) ---
SOVITS_DIR="/opt/GPT-SoVITS"
if [ -d "$SOVITS_DIR" ]; then
    echo "[GPT-SoVITS] Already installed at $SOVITS_DIR"
else
    echo "[GPT-SoVITS] Cloning..."
    cd /opt
    git clone https://github.com/RVC-Boss/GPT-SoVITS.git
    cd "$SOVITS_DIR"
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
    echo "[GPT-SoVITS] Installed at $SOVITS_DIR"
fi

# --- RVC v2 (production quality: 5min+ audio recommended, ~45min training) ---
RVC_DIR="/opt/rvc-v2"
if [ -d "$RVC_DIR" ]; then
    echo "[RVC v2] Already installed at $RVC_DIR"
else
    echo "[RVC v2] Cloning..."
    cd /opt
    git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git rvc-v2
    cd "$RVC_DIR"
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
    echo "[RVC v2] Installed at $RVC_DIR"
fi

# --- edge-tts (fallback TTS, pip install in anime-studio venv) ---
LORA_VENV="/opt/anime-studio/anime-studio/venv"
if [ -f "$LORA_VENV/bin/edge-tts" ]; then
    echo "[edge-tts] Already installed"
else
    echo "[edge-tts] Installing..."
    "$LORA_VENV/bin/pip" install edge-tts
    echo "[edge-tts] Installed"
fi

echo ""
echo "=== Setup Complete ==="
echo "GPT-SoVITS: $SOVITS_DIR"
echo "RVC v2:     $RVC_DIR"
echo "edge-tts:   $(which edge-tts 2>/dev/null || echo "$LORA_VENV/bin/edge-tts")"
echo ""
echo "Note: pyannote-audio requires a HuggingFace token."
echo "Set HF_TOKEN env var or store in Vault at secret/anime/huggingface"
