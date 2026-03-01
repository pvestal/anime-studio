"""Automatic video engine selection for shots.

Picks the best engine based on shot characteristics:
  1. Character has trained LoRA on disk → ltx (native LoRA injection)
  2. Solo shot with source image → framepack (I2V preserves source style — critical for realistic projects)
  3. Multi-char / no source image → wan (T2V, A/B test winner for multi-char — no IP-Adapter artifacts)

A/B test (2026-02-27): Wan+postprocess beat Composite+FramePack for MULTI-CHARACTER shots.
Solo shots still use FramePack to preserve the photorealistic style from source images.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

LORA_DIR = Path("/opt/ComfyUI/models/loras")
VALID_ENGINES = {"framepack", "framepack_f1", "ltx", "wan", "wan22", "reference_v2v"}
ESTABLISHING_SHOT_TYPES = {"establishing", "wide_establishing", "aerial", "environment"}

# GPU VRAM budget (RTX 3060 12 GB, single GPU):
#   framepack / reference_v2v: ~10 GB (HunyuanVideo backbone) — exclusive
#   wan / wan22 GGUF:          ~6-8 GB (1.3B quantized)
#   ltx:                       ~8 GB
#   CLIP classifier:           ~400 MB (coexists with any engine)
# builder.py uses Semaphore(1) to serialize GPU jobs — correct for 12 GB.


@dataclass
class EngineSelection:
    engine: str                       # "framepack" | "ltx" | "wan" | "wan22" | "reference_v2v"
    reason: str                       # human-readable explanation
    lora_name: str | None = None      # filename if LTX/Wan22 + LoRA
    lora_strength: float = 0.8


def _find_video_lora(character_slug: str) -> tuple[str | None, str | None]:
    """Check if a character has a LoRA file on disk.

    Searches for both LTX LoRAs ({slug}_lora.safetensors) and
    FramePack LoRAs ({slug}_framepack.safetensors).

    Returns (filename, architecture) where architecture is "ltx" or "framepack",
    or (None, None) if not found.
    """
    # FramePack LoRA (HunyuanVideo architecture) — preferred for V2V
    fp_path = LORA_DIR / f"{character_slug}_framepack.safetensors"
    if fp_path.exists():
        return fp_path.name, "framepack"
    # LTX LoRA (SD-format)
    ltx_path = LORA_DIR / f"{character_slug}_lora.safetensors"
    if ltx_path.exists():
        return ltx_path.name, "ltx"
    return None, None


def _pick_best_lora(characters: list[str]) -> tuple[str | None, str | None, str | None]:
    """Find the first character with a LoRA file.

    Returns (lora_filename, slug, architecture) or (None, None, None).
    """
    for slug in characters:
        lora_name, lora_arch = _find_video_lora(slug)
        if lora_name:
            return lora_name, slug, lora_arch
    return None, None, None


def _find_wan_lora() -> str | None:
    """Detect a Wan 2.2-compatible LoRA in the loras directory.

    Naming convention: *wan22*.safetensors (e.g. furrynsfw_wan22_v1.safetensors).
    Returns the filename if found, None otherwise.
    """
    for p in LORA_DIR.glob("*wan22*.safetensors"):
        return p.name
    return None


def select_engine(
    shot_type: str,
    characters_present: list[str],
    has_source_image: bool,
    blacklisted_engines: list[str] | None = None,
    has_source_video: bool = False,
    project_wan_lora: str | None = None,
) -> EngineSelection:
    """Pick best video engine based on shot characteristics.

    Args:
        shot_type: Shot type string (e.g. "establishing", "medium", "close_up").
        characters_present: List of character slugs in the shot.
        has_source_image: Whether a source image is assigned.
        blacklisted_engines: Engines to exclude from selection.
        has_source_video: Whether a source video clip is assigned (for V2V style transfer).
        project_wan_lora: Wan 2.2 LoRA filename if detected for this project.
            When set, ALL shots route to wan22 engine (highest priority after V2V).

    Returns:
        EngineSelection with chosen engine, reason, and optional LoRA info.
    """
    blocked = set(blacklisted_engines or [])

    # Build priority-ordered candidates
    candidates: list[EngineSelection] = []

    is_establishing = (
        shot_type in ESTABLISHING_SHOT_TYPES or not characters_present
    )
    is_multi_char = len(characters_present) > 1
    lora_name, lora_slug, lora_arch = _pick_best_lora(characters_present) if characters_present else (None, None, None)

    # Rule 0: Solo shot with reference video clip → reference_v2v (V2V style transfer)
    # Attach FramePack LoRA if available for enhanced identity lock
    if has_source_video and not is_multi_char and not is_establishing:
        candidates.append(EngineSelection(
            engine="reference_v2v",
            reason="solo shot with reference video clip, V2V style transfer"
                + (f" + FramePack LoRA ({lora_name})" if lora_arch == "framepack" else ""),
            lora_name=lora_name if lora_arch == "framepack" else None,
            lora_strength=0.8,
        ))

    # Rule 0.5: Project has Wan 2.2 LoRA → route ALL shots to wan22
    # Solo shots use I2V mode (with ref image), multi-char/establishing use T2V mode.
    # This takes priority over all other rules except V2V.
    # LoRA 0.5 is the sweet spot — 0.8 causes exaggerated proportions, 0.3 loses influence.
    if project_wan_lora:
        mode = "I2V" if (has_source_image and not is_multi_char and not is_establishing) else "T2V"
        candidates.append(EngineSelection(
            engine="wan22",
            reason=f"project Wan LoRA ({project_wan_lora}), {mode} mode",
            lora_name=project_wan_lora,
            lora_strength=0.5,
        ))

    # Rule 1: Establishing / environment shot → wan (no characters, T2V is fine)
    if is_establishing:
        candidates.append(EngineSelection(
            engine="wan",
            reason=f"establishing shot (type={shot_type})",
        ))

    # Rule 2: Multi-character → wan (MUST come before LoRA check — LTX can't handle multi-char)
    if is_multi_char:
        candidates.append(EngineSelection(
            engine="wan",
            reason=f"multi-character shot ({len(characters_present)} chars), A/B test winner",
        ))

    # Rule 3a: Solo character with FramePack LoRA + source image → framepack with LoRA
    if lora_name and lora_arch == "framepack" and has_source_image and not is_multi_char:
        candidates.append(EngineSelection(
            engine="framepack",
            reason=f"character '{lora_slug}' has FramePack LoRA ({lora_name}) + source image",
            lora_name=lora_name,
            lora_strength=0.8,
        ))

    # Rule 3b: Solo character with LTX LoRA → ltx
    if lora_name and lora_arch == "ltx" and not is_multi_char:
        candidates.append(EngineSelection(
            engine="ltx",
            reason=f"character '{lora_slug}' has LTX LoRA ({lora_name})",
            lora_name=lora_name,
            lora_strength=0.8,
        ))

    # Rule 4: Solo shot with source image → framepack (preserves realistic style from source)
    if has_source_image and not is_multi_char:
        candidates.append(EngineSelection(
            engine="framepack",
            reason="solo shot with source image, preserves source style",
        ))

    # Rule 5: No source image + characters → wan T2V fallback
    if not has_source_image and characters_present:
        candidates.append(EngineSelection(
            engine="wan",
            reason="no source image available, using T2V",
        ))

    # Default fallback
    candidates.append(EngineSelection(
        engine="wan",
        reason="default engine",
    ))

    # Apply blacklist — pick first non-blocked candidate
    for candidate in candidates:
        if candidate.engine not in blocked:
            return candidate

    # Everything blocked — return last candidate with warning
    logger.warning(
        f"All engines blocked by blacklist {blocked}, "
        f"falling back to '{candidates[-1].engine}' anyway"
    )
    return candidates[-1]
