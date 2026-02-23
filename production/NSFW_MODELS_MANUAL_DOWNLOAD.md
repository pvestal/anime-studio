# NSFW Models Manual Download Instructions

## Required Models for Tower Anime Production

### 1. LTX Orgasm LoRA
- **URL**: https://civitai.com/models/2176039/orgasm
- **Save as**: `/mnt/1TB-storage/ComfyUI/models/loras/ltx_orgasm.safetensors`
- **Usage**: LTX video generation with adult content
- **Trigger**: "[He | She] is having an orgasm"

### 2. LTX-2-I2V NSFW Multi-Purpose LoRA
- **URL**: https://civitai.com/models/2310920/ltx-2-i2v-nsfw-furry-multi-purpose-sex-lora
- **Save as**: `/mnt/1TB-storage/ComfyUI/models/loras/ltx_nsfw_multipurpose.safetensors`
- **Usage**: Multi-purpose adult content for LTX video

### 3. WAN-DR34ML4Y All-in-One NSFW
- **URL**: https://civitai.com/models/1811313/wan-dr34ml4y-all-in-one-nsfw
- **Save as**: `/mnt/1TB-storage/ComfyUI/models/loras/wan_dr34ml4y_nsfw.safetensors`
- **Usage**: General NSFW content generation

## Manual Download Steps

1. **Login to Civitai**
   - Go to https://civitai.com
   - Sign in to your account

2. **Get API Token** (if not working)
   - Go to https://civitai.com/user/account
   - Scroll to API Keys section
   - Create new API key

3. **Download Each Model**
   - Click each URL above
   - Click the download button
   - Save to the specified path

4. **Using wget/curl**
   ```bash
   # After getting the direct download link from browser:
   wget -O /mnt/1TB-storage/ComfyUI/models/loras/ltx_orgasm.safetensors "DIRECT_DOWNLOAD_URL"
   ```

## Current Status
- Token found: `b49c4e3f5c0d4a23b8f1e3d2a7c9b5e6`
- Issue: 401 Unauthorized (token may be expired or invalid)
- Solution: Manual download or regenerate API token

## After Download
Run the test pipeline:
```bash
python3 /opt/anime-studio/production/nsfw_test.py
```