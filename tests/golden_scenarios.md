# Golden Test Scenarios — Video Pipeline QA

## GOLDEN: Rosa reference_v2v (validated 2026-03-01)

- **Shot ID**: `10867ec2-75db-430d-ad1a-5fa7258186c4`
- **Scene**: Rosa Introduction (e22c0f04-012e-4b60-a216-63437d9a894f)
- **Input**: `rosa/images/rosa_wan_frame_0002.png` + `_movies/rosa_caliente/rosa_wan_test_01.mp4` (5s)
- **Engine**: `reference_v2v` (LoRA-free — rosa_framepack.safetensors incompatible, safety gate skips it)
- **Output**: `rosa_caliente_ep00_sc01_sh01_reference_v2v_10867ec2_00001_final.mp4`
- **Settings**: denoise=0.45, steps=25, guidance=6.0, resolution=544x704
- **Generation time**: ~15 min on RTX 3060 12GB
- **QA criteria**:
  - [x] Temporal coherence: no flickering between frames
  - [x] Resolution: 544x704 (FramePack V2V default)
  - [x] Denoise visible but layout preserved from source video
  - [x] Post-processing: RIFE interpolation applied (16→30fps)
  - [ ] Character identity — LoRA-free, relies on source video likeness only
- **Notes**: LoRA (rosa_framepack.safetensors) trained with wrong network module (musubi/diffusers format). Retrain with `networks.lora_framepack` using scaffolding in `/mnt/1TB-storage/lora_training/rosa_framepack/`

## Rosa Caliente: Solo + LoRA + Image (framepack I2V)

- **Input**: Best approved Rosa image as source
- **Engine path**: solo + image → `framepack` + `rosa_framepack.safetensors` LoRA
- **Expected output**: FramePack I2V video, LoRA identity visible
- **QA criteria**:
  - [ ] Character matches Rosa reference
  - [ ] Natural motion from still image
  - [ ] LoRA influence visible in style/identity

## GOLDEN: Fury reference_v2v — Roxy Bedroom (validated 2026-03-01)

- **Shot ID**: `b3d1f939-f826-468d-8195-881916407416`
- **Scene**: Bedroom Moments (a624bc46-0b85-421d-839c-b0f57f5a7141)
- **Input**: Roxy continuity frame + `_movies/fury/roxy_fox_bed_01.mp4`
- **Engine**: `reference_v2v` (no FramePack LoRA for roxy — runs LoRA-free)
- **Expected output**: `fury_ep00_sc08_sh01_reference_v2v_b3d1f939_00001_final.mp4`
- **Settings**: denoise=0.45, steps=25, guidance=6.0, resolution=544x704
- **Generation time**: 1546s (~25.8 min) on RTX 3060 12GB
- **Output**: 6s, 544x704, 1.6MB (RIFE interpolated)
- **QA criteria**:
  - [x] Resolution: 544x704
  - [x] DB status updated to `completed`
  - [x] Shot hash `b3d1f939` visible in output filename
  - [x] Post-processing: RIFE interpolation applied (output is `_final.mp4`)
  - [ ] Temporal coherence: needs visual review
  - [ ] Source motion from roxy_fox_bed_01.mp4 preserved: needs visual review
  - [ ] Character appearance consistent with Roxy design: needs visual review
- **Regression script**: `tests/run_golden_fury_v2v.sh`

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
