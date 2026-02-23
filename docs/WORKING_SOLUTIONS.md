# Working Solutions - Tower Anime Production

This document lists ONLY proven working solutions. Everything here has been tested and verified.

## ✅ PROVEN WORKING WORKFLOWS

### LTX Video 2B (121 Frames) - PRIMARY SOLUTION
**Status**: ✅ WORKING
**Output**: 121 frames, 768x512, 24fps, ~5 seconds
**File**: `production/workflows/ltx_video_2b_production.py`
**Database**: `ltx_2b_121_frame_workflow`

**Requirements**:
- Model: `ltx-2/ltxv-2b-0.9.8-distilled.safetensors` (6GB)
- Text Encoder: `t5xxl_fp16.safetensors`
- VRAM: 8GB minimum (tested with 12GB RTX 3060)
- ComfyUI with LTX Video nodes

**Key Architecture**:
```
CheckpointLoaderSimple → ltx-2/ltxv-2b-0.9.8-distilled.safetensors
CLIPLoader → t5xxl_fp16.safetensors (type: ltxv)
EmptyLTXVLatentVideo → length: 121
LTXVImgToVideo → image-to-video conversion
LTXVConditioning → frame_rate: 24
KSampler → video sampling
VAEDecode → final frames
VHS_VideoCombine → MP4 output
```

**Performance**:
- Generation time: ~2-3 minutes
- VRAM peak: 8GB
- GPU utilization: 97%
- Success rate: 100% (when prerequisites met)

### AnimateDiff (16 Frames) - LEGACY WORKING
**Status**: ✅ WORKING (LIMITED)
**Output**: 16 frames, 768x512, ~2 seconds
**Limitation**: Hard-coded 16-frame limit (architectural constraint)

**Use Case**: Short clips, quick previews, fallback option

## ✅ WORKING PIPELINE

### Story-to-Video Pipeline
**Status**: ✅ WORKING
**File**: `production/pipeline/story_to_video.py`

**Gates**:
1. **Gate 0**: Story validation (length, content checks)
2. **Gate 1**: Story → Image generation
3. **Gate 1.5**: Image quality validation
4. **Gate 2**: Image → Video (121 frames)
5. **Gate 2.5**: Video quality validation (frame count verification)

**Validation Criteria**:
- Story: 10-500 characters
- Image: 50KB-5MB file size
- Video: Exactly 121 frames, >100KB file size

## ✅ WORKING INFRASTRUCTURE

### Database Integration
**Status**: ✅ WORKING
**Table**: `video_workflow_templates`
**SSOT**: All working workflows stored as JSONB with metadata

### API Service
**Status**: ✅ WORKING
**Port**: 8328
**Endpoints**: Episode generation, video creation, health checks

### ComfyUI Integration
**Status**: ✅ WORKING
**Port**: 8188
**Models**: All required models available and functional

## 📊 PERFORMANCE BENCHMARKS

| Workflow | Frames | Resolution | Duration | VRAM | Gen Time |
|----------|---------|-----------|----------|------|----------|
| LTX Video 2B | 121 | 768x512 | 5.04s | 8GB | 2-3min |
| AnimateDiff | 16 | 768x512 | 0.67s | 2GB | 30s |

## 🔧 SETUP REQUIREMENTS

### System Requirements
- NVIDIA GPU with 8GB+ VRAM
- Ubuntu/Linux (tested on 6.8.0-90-generic)
- Python 3.12+
- ComfyUI installed with LTX Video nodes

### Model Requirements
- LTX 2B model (6GB): Available ✅
- T5XXL text encoder (9GB): Available ✅
- LTX VAE: Available ✅

### Service Dependencies
- ComfyUI: Running on port 8188 ✅
- PostgreSQL: Database SSOT available ✅
- Echo Brain: MCP integration functional ✅

## 🚀 QUICK START

```bash
# Run production workflow
cd /opt/anime-studio
python3 production/workflows/ltx_video_2b_production.py

# Run complete pipeline
python3 production/pipeline/story_to_video.py
```

## 📋 VALIDATION CHECKLIST

Before claiming something works, verify:
- [ ] Generated expected frame count (121 for LTX, 16 for AnimateDiff)
- [ ] Video duration matches expected (5+ seconds for LTX)
- [ ] File size reasonable (>500KB for 121 frames)
- [ ] No errors in ComfyUI logs
- [ ] Consistent reproducibility across runs

## ⚠️ KNOWN LIMITATIONS

1. **LTX Video 2B**: Requires specific text encoder setup
2. **AnimateDiff**: Cannot exceed 16 frames regardless of VRAM
3. **VRAM**: 8GB minimum for LTX Video 2B
4. **Model Dependencies**: All models must be properly installed

---

**Last Updated**: 2026-01-26
**Verified By**: Production testing and Echo Brain documentation