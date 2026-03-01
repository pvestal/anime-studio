# Video Engine Routing Matrix

Source: `packages/scene_generation/engine_selector.py`

## Priority Order

Rules are evaluated top-to-bottom. First non-blacklisted match wins.

| Priority | Condition | Engine | Mode | LoRA | VRAM (~) |
|----------|-----------|--------|------|------|----------|
| 0 | Solo + source video clip | `reference_v2v` | V2V | FramePack LoRA if available | ~10 GB |
| 0.5 | Project has `project_wan_lora` | `wan22` | I2V (solo+img) or T2V | Wan22 LoRA @ 0.5 | ~6-8 GB |
| 1 | Establishing / no characters | `wan` | T2V | -- | ~6-8 GB |
| 2 | Multi-character shot | `wan` | T2V | -- | ~6-8 GB |
| 3a | Solo + FramePack LoRA + image | `framepack` | I2V | FramePack LoRA @ 0.8 | ~10 GB |
| 3b | Solo + LTX LoRA | `ltx` | T2V | LTX LoRA @ 0.8 | ~8 GB |
| 4 | Solo + source image | `framepack` | I2V | -- | ~10 GB |
| 5 | Characters, no image | `wan` | T2V | -- | ~6-8 GB |
| fallback | Always | `wan` | T2V | -- | ~6-8 GB |

## Valid Engines

`framepack`, `framepack_f1`, `ltx`, `wan`, `wan22`, `reference_v2v`

## Blacklist Mechanism

Pass `blacklisted_engines=["framepack"]` to `select_engine()` to skip matching rules.
The selector picks the next valid candidate. If all are blocked, last candidate is used with a warning.

## Per-Shot Override

`POST /api/scenes/{scene_id}/shots/{shot_id}/override-engine` sets `shots.video_engine`
directly, bypassing the automatic selector. Validates against `VALID_ENGINES`.

## GPU Budget (RTX 3060 12 GB)

- FramePack (I2V/V2V): ~10 GB — single-GPU exclusive
- Wan 1.3B GGUF (T2V): ~6-8 GB — fits with CLIP (~400 MB)
- CLIP classifier: ~400 MB — coexists with anything
- `asyncio.Semaphore(1)` in `builder.py` prevents concurrent GPU jobs
