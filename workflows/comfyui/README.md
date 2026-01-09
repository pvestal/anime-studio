# ComfyUI Workflows for 30-Second Anime Generation

This directory contains the critical workflow files for generating 30-second anime videos using ComfyUI with RIFE interpolation.

## Files

### Core Workflows
- **`anime_30sec_working_workflow.json`** - Tested and verified working workflow for 30-second anime generation
- **`anime_30sec_rife_workflow.json`** - RIFE interpolation workflow for frame interpolation
- **`anime_30sec_fixed_workflow.json`** - Fixed version with optimized settings

### Generation Script
- **`generate_30sec_anime.py`** - Python script to trigger the 30-second anime generation workflow

## Usage

1. Load the workflow JSON file into ComfyUI interface at http://192.168.50.135:8188
2. Alternatively, use the Python script to automate generation:
   ```bash
   python3 generate_30sec_anime.py
   ```

## Technical Details

- **Frame Count**: 120 frames for 30 seconds at 4fps
- **Resolution**: 1024x1024 (optimized for RTX 3060 12GB VRAM)
- **Interpolation**: RIFE algorithm for smooth frame transitions
- **Context Window**: Looped uniform context for temporal consistency
- **Generation Time**: ~15-20 minutes on NVIDIA RTX 3060

## Requirements

- ComfyUI running on Tower (192.168.50.135:8188)
- NVIDIA RTX 3060 with 12GB VRAM
- AnimateDiff-Evolved extension
- RIFE extension for frame interpolation
- Required models loaded in ComfyUI

## Output

Generated videos are saved to `/mnt/1TB-storage/ComfyUI/output/` and can be accessed via Jellyfin at `/mnt/10TB2/Anime/AI_Generated/`.