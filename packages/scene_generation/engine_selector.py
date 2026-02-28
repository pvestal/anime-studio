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
VALID_ENGINES = {"framepack", "framepack_f1", "ltx", "wan", "reference_v2v"}
ESTABLISHING_SHOT_TYPES = {"establishing", "wide_establishing", "aerial", "environment"}


@dataclass
class EngineSelection:
    engine: str                       # "framepack" | "ltx" | "wan" | "reference_v2v"
    reason: str                       # human-readable explanation
    lora_name: str | None = None      # filename if LTX + LoRA
    lora_strength: float = 0.8


def _find_video_lora(character_slug: str) -> str | None:
    """Check if a character has a LoRA file on disk.

    Video LoRAs for LTX are always SD-format: {slug}_lora.safetensors.
    Returns the filename (not full path) if found, None otherwise.
    """
    lora_path = LORA_DIR / f"{character_slug}_lora.safetensors"
    if lora_path.exists():
        return lora_path.name
    return None


def _pick_best_lora(characters: list[str]) -> tuple[str | None, str | None]:
    """Find the first character with a LoRA file. Returns (lora_filename, slug)."""
    for slug in characters:
        lora = _find_video_lora(slug)
        if lora:
            return lora, slug
    return None, None


def select_engine(
    shot_type: str,
    characters_present: list[str],
    has_source_image: bool,
    blacklisted_engines: list[str] | None = None,
    has_source_video: bool = False,
) -> EngineSelection:
    """Pick best video engine based on shot characteristics.

    Args:
        shot_type: Shot type string (e.g. "establishing", "medium", "close_up").
        characters_present: List of character slugs in the shot.
        has_source_image: Whether a source image is assigned.
        blacklisted_engines: Engines to exclude from selection.
        has_source_video: Whether a source video clip is assigned (for V2V style transfer).

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
    lora_name, lora_slug = _pick_best_lora(characters_present) if characters_present else (None, None)

    # Rule 0: Solo shot with reference video clip → reference_v2v (V2V style transfer)
    if has_source_video and not is_multi_char and not is_establishing:
        candidates.append(EngineSelection(
            engine="reference_v2v",
            reason="solo shot with reference video clip, V2V style transfer",
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

    # Rule 3: Solo character with trained LoRA → ltx
    if lora_name and not is_multi_char:
        candidates.append(EngineSelection(
            engine="ltx",
            reason=f"character '{lora_slug}' has LoRA ({lora_name})",
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
