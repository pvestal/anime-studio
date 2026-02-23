"""Automatic video engine selection for shots.

Picks the best engine based on shot characteristics:
  1. Establishing shot, no characters → wan (T2V, no source image needed)
  2. Character has trained LoRA on disk → ltx (native LoRA injection)
  3. Has source image, no LoRA → framepack (best I2V at 30fps)
  4. No source image + has characters → wan fallback (T2V)
  5. Engine blacklist overrides → fall through to next valid engine
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

LORA_DIR = Path("/opt/ComfyUI/models/loras")
VALID_ENGINES = {"framepack", "framepack_f1", "ltx", "wan"}
ESTABLISHING_SHOT_TYPES = {"establishing", "wide_establishing", "aerial", "environment"}


@dataclass
class EngineSelection:
    engine: str                       # "framepack" | "ltx" | "wan"
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
) -> EngineSelection:
    """Pick best video engine based on shot characteristics.

    Args:
        shot_type: Shot type string (e.g. "establishing", "medium", "close_up").
        characters_present: List of character slugs in the shot.
        has_source_image: Whether a source image is assigned.
        blacklisted_engines: Engines to exclude from selection.

    Returns:
        EngineSelection with chosen engine, reason, and optional LoRA info.
    """
    blocked = set(blacklisted_engines or [])

    # Build priority-ordered candidates
    candidates: list[EngineSelection] = []

    is_establishing = (
        shot_type in ESTABLISHING_SHOT_TYPES or not characters_present
    )
    lora_name, lora_slug = _pick_best_lora(characters_present) if characters_present else (None, None)

    # Rule 1: Establishing / environment shot → wan
    if is_establishing:
        candidates.append(EngineSelection(
            engine="wan",
            reason=f"establishing shot (type={shot_type}, no characters)" if not characters_present
                   else f"establishing shot type '{shot_type}'",
        ))

    # Rule 2: Character with trained LoRA → ltx
    if lora_name:
        candidates.append(EngineSelection(
            engine="ltx",
            reason=f"character '{lora_slug}' has LoRA ({lora_name})",
            lora_name=lora_name,
            lora_strength=0.8,
        ))

    # Rule 3: Has source image → framepack
    if has_source_image:
        candidates.append(EngineSelection(
            engine="framepack",
            reason="source image available, best I2V quality",
        ))

    # Rule 4: Fallback — no source image + characters → wan T2V
    if not has_source_image and characters_present:
        candidates.append(EngineSelection(
            engine="wan",
            reason="no source image available, using T2V fallback",
        ))

    # Default fallback
    candidates.append(EngineSelection(
        engine="framepack",
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
