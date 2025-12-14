#!/bin/bash
# Download required models for IPAdapter FaceID character consistency

echo "📦 Downloading Required Models for IPAdapter FaceID"
echo "=================================================="

# Create directories if needed
mkdir -p /mnt/1TB-storage/ComfyUI/models/clip_vision/SD1.5/
mkdir -p /mnt/1TB-storage/ComfyUI/models/ipadapter/
mkdir -p /mnt/1TB-storage/ComfyUI/models/insightface/models/

cd /mnt/1TB-storage/ComfyUI/models/

# Download CLIP Vision model for SD1.5
echo ""
echo "1️⃣ Downloading CLIP Vision model for SD1.5..."
if [ ! -f "clip_vision/SD1.5/pytorch_model.bin" ]; then
    wget -O clip_vision/SD1.5/pytorch_model.bin \
        https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/pytorch_model.bin
    echo "✅ CLIP Vision model downloaded"
else
    echo "✅ CLIP Vision model already exists"
fi

# Download IPAdapter FaceID models
echo ""
echo "2️⃣ Downloading IPAdapter FaceID Plus V2 model..."
if [ ! -f "ipadapter/ip-adapter-faceid-plusv2_sd15.bin" ]; then
    wget -O ipadapter/ip-adapter-faceid-plusv2_sd15.bin \
        https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sd15.bin
    echo "✅ IPAdapter FaceID Plus V2 downloaded"
else
    echo "✅ IPAdapter FaceID Plus V2 already exists"
fi

# Download IPAdapter FaceID LoRA (required for FaceID)
echo ""
echo "3️⃣ Downloading IPAdapter FaceID LoRA..."
if [ ! -f "loras/ip-adapter-faceid_sd15_lora.safetensors" ]; then
    wget -O loras/ip-adapter-faceid_sd15_lora.safetensors \
        https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sd15_lora.safetensors
    echo "✅ IPAdapter FaceID LoRA downloaded"
else
    echo "✅ IPAdapter FaceID LoRA already exists"
fi

# Download InsightFace model (antelopev2)
echo ""
echo "4️⃣ Downloading InsightFace Antelope V2 model..."
if [ ! -f "insightface/models/antelopev2.zip" ]; then
    wget -O insightface/models/antelopev2.zip \
        https://huggingface.co/MonsterMMORPG/tools/resolve/main/antelopev2.zip
    cd insightface/models/ && unzip -q antelopev2.zip && rm antelopev2.zip
    echo "✅ InsightFace Antelope V2 extracted"
else
    echo "✅ InsightFace Antelope V2 already exists"
fi

echo ""
echo "=================================================="
echo "✅ All required models downloaded!"
echo ""
echo "📋 Installed Models:"
echo "  • CLIP Vision: SD1.5/pytorch_model.bin"
echo "  • IPAdapter: ip-adapter-faceid-plusv2_sd15.bin"
echo "  • IPAdapter LoRA: ip-adapter-faceid_sd15_lora.safetensors"
echo "  • InsightFace: antelopev2"
echo ""
echo "🎯 Next Steps:"
echo "1. Restart ComfyUI to load new models"
echo "2. Run: python /opt/tower-anime-production/test_ipadapter_consistency.py"
echo "3. Generate character variations with consistency"