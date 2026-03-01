# Golden Test Scenarios — Video Pipeline QA

## Rosa Caliente: Solo + LoRA + Video (reference_v2v)

**Best test case** for V2V pipeline — single character with trained FramePack LoRA.

- **Input**: Best approved Rosa image + `_movies/rosa_caliente/rosa_wan_test_01.mp4` (5s)
- **Engine path**: solo + source_video → `reference_v2v` + `rosa_framepack.safetensors` LoRA
- **Expected output**: `fpv2v_` prefixed MP4, source layout preserved, Rosa identity enhanced by LoRA
- **QA criteria**:
  - [ ] Temporal coherence: no flickering between frames
  - [ ] Resolution: 544x704 (FramePack V2V default)
  - [ ] Denoise visible but layout preserved from source video
  - [ ] Character identity matches LoRA training data
  - [ ] Post-processing: RIFE interpolation applied (16→30fps)

## Rosa Caliente: Solo + LoRA + Image (framepack I2V)

- **Input**: Best approved Rosa image as source
- **Engine path**: solo + image → `framepack` + `rosa_framepack.safetensors` LoRA
- **Expected output**: FramePack I2V video, LoRA identity visible
- **QA criteria**:
  - [ ] Character matches Rosa reference
  - [ ] Natural motion from still image
  - [ ] LoRA influence visible in style/identity

## Fury: Solo + Video (reference_v2v, no LoRA)

- **Input**: Fury character image + clip from `_movies/fury/`
- **Engine path**: solo + source_video → `reference_v2v` (no LoRA available)
- **Expected output**: V2V style transfer, source layout preserved
- **QA criteria**:
  - [ ] Compare with Rosa V2V (which has LoRA) — document quality delta
  - [ ] Source motion preserved
  - [ ] Character appearance consistent

## Fury: Multi-character (wan T2V)

- **Input**: Scene with 2+ Fury characters, no source image
- **Engine path**: multi-char → `wan` T2V
- **Expected output**: Wan T2V with anime-style characters
- **QA criteria**:
  - [ ] Both characters recognizable
  - [ ] Scene description followed
  - [ ] No IP-Adapter artifacts (wan T2V doesn't use IPA)

## Fury: Wan22 + LoRA (if project_wan_lora set)

- **Input**: `furrynsfw_wan22_v1.safetensors` as project LoRA
- **T2V mode**: Multi-char establishing shot
- **I2V mode**: Solo shot with source image
- **QA criteria**:
  - [ ] LoRA style influence visible in both modes
  - [ ] I2V preserves source image composition
  - [ ] T2V generates coherent scene
