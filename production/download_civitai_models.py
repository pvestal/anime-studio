#!/usr/bin/env python3
"""
Download models from Civitai for Tower Anime Production
Handles NSFW and specialized models for production pipeline
"""

import os
import json
import time
import requests
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

class CivitaiModelDownloader:
    """Download and manage Civitai models"""

    def __init__(self):
        self.models_dir = Path("/mnt/1TB-storage/ComfyUI/models")
        self.checkpoints_dir = self.models_dir / "checkpoints"
        self.loras_dir = self.models_dir / "loras"

        # Civitai API (if you have an API key)
        self.api_key = os.environ.get('CIVITAI_API_KEY', '')

        # Model URLs to download (these would need actual download links)
        self.models_to_download = {
            'ltx_nsfw_lora': {
                'name': 'LTX-2-I2V-NSFW-LoRA',
                'type': 'lora',
                'url': None,  # Would need actual download URL
                'filename': 'ltx_2_i2v_nsfw.safetensors',
                'description': 'LTX Video 2B NSFW LoRA for adult content'
            },
            'ltxv20_uncensored': {
                'name': 'LTXv20 Uncensored Workflow',
                'type': 'workflow',
                'url': None,  # Would need actual download URL
                'filename': 'ltxv20_uncensored_workflow.json',
                'description': 'Uncensored video generation workflow'
            }
        }

    def check_existing_models(self):
        """Check which models are already downloaded"""
        print("🔍 Checking existing models...")

        # Check checkpoints
        checkpoints = list(self.checkpoints_dir.glob("*.safetensors"))
        print(f"📦 Checkpoints: {len(checkpoints)} models")

        # Check LoRAs
        loras = list(self.loras_dir.glob("*.safetensors"))
        print(f"🎨 LoRAs: {len(loras)} models")

        # List NSFW-capable models
        nsfw_models = []
        for model in checkpoints:
            name = model.name.lower()
            if any(x in name for x in ['counterfeit', 'chillout', 'realistic', 'dream']):
                nsfw_models.append(model.name)

        if nsfw_models:
            print(f"🔓 NSFW-capable base models found:")
            for model in nsfw_models:
                print(f"   - {model}")

        # Check for LTX models
        ltx_models = []
        for model in (list(checkpoints) + list(loras)):
            if 'ltx' in model.name.lower():
                ltx_models.append(model.name)

        if ltx_models:
            print(f"🎬 LTX models found:")
            for model in ltx_models:
                print(f"   - {model}")

        return {
            'checkpoints': [p.name for p in checkpoints],
            'loras': [p.name for p in loras],
            'nsfw_capable': nsfw_models,
            'ltx_models': ltx_models
        }

    def download_with_wget(self, url: str, output_path: Path) -> bool:
        """Download model using wget"""
        try:
            print(f"📥 Downloading to: {output_path}")

            # Use wget with resume capability
            cmd = [
                'wget',
                '-c',  # Continue partial downloads
                '--progress=bar:force',
                '-O', str(output_path),
                url
            ]

            result = subprocess.run(cmd, capture_output=False)

            if result.returncode == 0:
                print(f"✅ Downloaded: {output_path.name}")
                return True
            else:
                print(f"❌ Download failed: {output_path.name}")
                return False

        except Exception as e:
            print(f"❌ Error downloading: {e}")
            return False

    def download_from_civitai(self, model_id: str, version_id: str, output_dir: Path) -> Optional[str]:
        """
        Download model from Civitai using their API or direct link
        Note: This requires either a public download link or API key
        """

        # For public models, construct download URL
        # Format: https://civitai.com/api/download/models/{versionId}
        download_url = f"https://civitai.com/api/download/models/{version_id}"

        if self.api_key:
            download_url += f"?token={self.api_key}"

        # Determine filename from model info
        filename = f"model_{version_id}.safetensors"
        output_path = output_dir / filename

        print(f"🌐 Attempting to download from Civitai:")
        print(f"   Model ID: {model_id}")
        print(f"   Version ID: {version_id}")
        print(f"   URL: {download_url}")

        # Note: Actual download would require proper authentication
        # or publicly available links

        return None  # Would return path if successful

    def setup_nsfw_pipeline(self):
        """Set up complete NSFW pipeline with all required models"""

        print("\n🔧 Setting up NSFW Pipeline")
        print("="*50)

        # Check current status
        existing = self.check_existing_models()

        # Required models for complete NSFW pipeline
        required = {
            'base_models': {
                'counterfeit_v3.safetensors': '✅' if 'counterfeit_v3.safetensors' in existing['checkpoints'] else '❌',
                'chilloutmix_NiPrunedFp32Fix.safetensors': '✅' if 'chilloutmix_NiPrunedFp32Fix.safetensors' in existing['checkpoints'] else '❌',
                'realisticVision_v51.safetensors': '✅' if 'realisticVision_v51.safetensors' in existing['checkpoints'] else '❌'
            },
            'character_loras': {
                'mei_working_v1.safetensors': '✅' if 'mei_working_v1.safetensors' in existing['loras'] else '❌',
                'mei_body.safetensors': '✅' if 'mei_body.safetensors' in existing['loras'] else '❌',
                'mei_real_v3.safetensors': '✅' if 'mei_real_v3.safetensors' in existing['loras'] else '❌'
            },
            'video_models': {
                'ltx-2/ltxv-2b-0.9.8-distilled.safetensors': '✅' if any('ltx' in c for c in existing['checkpoints']) else '❌'
            },
            'nsfw_loras_needed': {
                'ltx_2_i2v_nsfw.safetensors': '❌ NEED TO DOWNLOAD',
                'ltxv20_uncensored.safetensors': '❌ NEED TO DOWNLOAD'
            }
        }

        print("\n📋 Pipeline Status:")
        for category, models in required.items():
            print(f"\n{category.replace('_', ' ').title()}:")
            for model, status in models.items():
                print(f"   {status} {model}")

        # Provide download instructions
        print("\n📥 Download Instructions:")
        print("\n1. For LTX NSFW LoRA:")
        print("   URL: https://civitai.com/models/2310920")
        print("   Download the .safetensors file")
        print(f"   Place in: {self.loras_dir}/")

        print("\n2. For LTXv20 Uncensored:")
        print("   URL: https://civitai.com/models/2329764")
        print("   Download workflow and model files")
        print(f"   Place models in: {self.loras_dir}/")

        print("\n3. Manual download command:")
        print("   wget -c 'DOWNLOAD_URL' -O /mnt/1TB-storage/ComfyUI/models/loras/MODEL_NAME.safetensors")

        return required

    def create_download_script(self):
        """Create a shell script for manual downloads"""

        script_content = """#!/bin/bash
# Civitai Model Download Script
# Run this script to download NSFW models for Tower Anime Production

LORA_DIR="/mnt/1TB-storage/ComfyUI/models/loras"
CHECKPOINT_DIR="/mnt/1TB-storage/ComfyUI/models/checkpoints"

echo "🚀 Tower Anime Production - Model Downloader"
echo "==========================================="

# Check if directories exist
if [ ! -d "$LORA_DIR" ]; then
    echo "❌ LoRA directory not found: $LORA_DIR"
    exit 1
fi

echo "📁 LoRA directory: $LORA_DIR"
echo "📁 Checkpoint directory: $CHECKPOINT_DIR"

# Function to download with wget
download_model() {
    local url=$1
    local output=$2
    local name=$3

    echo ""
    echo "📥 Downloading: $name"
    echo "   URL: $url"
    echo "   Output: $output"

    if [ -f "$output" ]; then
        echo "   ✅ Already exists, skipping..."
    else
        wget -c "$url" -O "$output"
        if [ $? -eq 0 ]; then
            echo "   ✅ Downloaded successfully!"
        else
            echo "   ❌ Download failed!"
        fi
    fi
}

# Add your model downloads here
# Example:
# download_model "https://civitai.com/api/download/models/VERSION_ID" \\
#                "$LORA_DIR/model_name.safetensors" \\
#                "Model Display Name"

echo ""
echo "✅ Download script complete!"
echo ""
echo "NOTE: You need to add actual download URLs from Civitai"
echo "      1. Go to the model page"
echo "      2. Click download button"
echo "      3. Copy the actual download link"
echo "      4. Add to this script"
"""

        script_path = Path("/opt/anime-studio/production/download_models.sh")
        script_path.write_text(script_content)
        script_path.chmod(0o755)

        print(f"✅ Created download script: {script_path}")
        print("   Edit this script with actual Civitai download URLs")

        return script_path

def main():
    """Main download and setup function"""
    downloader = CivitaiModelDownloader()

    print("🎬 Tower Anime Production - Model Setup")
    print("="*50)

    # Check existing models
    existing = downloader.check_existing_models()

    # Setup NSFW pipeline
    pipeline_status = downloader.setup_nsfw_pipeline()

    # Create download script
    script_path = downloader.create_download_script()

    print("\n📋 Summary:")
    print(f"   Total checkpoints: {len(existing['checkpoints'])}")
    print(f"   Total LoRAs: {len(existing['loras'])}")
    print(f"   NSFW-capable models: {len(existing['nsfw_capable'])}")
    print(f"   Download script: {script_path}")

    print("\n⚠️  IMPORTANT:")
    print("   1. Visit Civitai model pages")
    print("   2. Get actual download links (need to be logged in)")
    print("   3. Use wget or browser to download")
    print("   4. Place in correct directories")

    return existing

if __name__ == "__main__":
    main()