"""Unit tests for the LoRA safety gate in builder.py.

The safety gate validates LoRA format before attaching to FramePack V2V workflows.
Only kohya/comfyui format LoRAs (keys starting with 'lora_unet_') are compatible
with the FramePackLoraSelect node. Musubi/diffusers format LoRAs must be rejected.

Tests:
- Kohya-format LoRA passes validation and is attached
- Musubi/diffusers-format LoRA is rejected with warning
- Missing LoRA file results in no LoRA (graceful)
- Corrupted/unreadable LoRA file is skipped safely
- Character with no LoRA on disk runs LoRA-free
"""

import struct
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Marker for fast unit tests
pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers: Create minimal safetensors files for testing
# ---------------------------------------------------------------------------

def _make_safetensors(path: Path, key_name: str):
    """Create a minimal valid safetensors file with a single zero tensor.

    safetensors format:
      8 bytes: header_size (little-endian u64)
      header_size bytes: JSON header mapping tensor names to metadata
      remainder: raw tensor data
    """
    import json

    # Single float32 scalar tensor
    tensor_data = struct.pack("<f", 0.0)
    header = {
        key_name: {
            "dtype": "F32",
            "shape": [1],
            "data_offsets": [0, 4],
        }
    }
    header_bytes = json.dumps(header).encode("utf-8")
    header_size = struct.pack("<Q", len(header_bytes))

    path.write_bytes(header_size + header_bytes + tensor_data)


def _make_kohya_lora(path: Path):
    """Create a safetensors file with kohya-format key (lora_unet_*)."""
    _make_safetensors(path, "lora_unet_single_transformer_blocks_0_attn_to_k.alpha")


def _make_diffusers_lora(path: Path):
    """Create a safetensors file with musubi/diffusers-format key."""
    _make_safetensors(path, "diffusion_model.layers.0.attention.to_k.lora_A.weight")


def _make_corrupt_file(path: Path):
    """Create a file that isn't valid safetensors."""
    path.write_bytes(b"this is not a safetensors file")


# ---------------------------------------------------------------------------
# The actual validation logic extracted for testability
# ---------------------------------------------------------------------------

def validate_framepack_lora(lora_path: Path) -> str | None:
    """Validate a FramePack LoRA file for komfyui/kohya compatibility.

    Returns the lora filename if valid, None if incompatible/missing/corrupt.
    This mirrors the logic in builder.py's V2V and refinement paths.
    """
    if not lora_path.exists():
        return None

    try:
        from safetensors import safe_open
        with safe_open(str(lora_path), framework="pt") as sf:
            k0 = list(sf.keys())[0] if sf.keys() else ""
        if k0.startswith("lora_unet_"):
            return lora_path.name
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoRASafetyGate:
    """Test the LoRA format validation used in builder.py V2V paths."""

    def test_kohya_format_passes(self, tmp_path):
        """Kohya/ComfyUI format LoRA (lora_unet_* keys) should be accepted."""
        lora_path = tmp_path / "test_char_framepack.safetensors"
        _make_kohya_lora(lora_path)

        result = validate_framepack_lora(lora_path)
        assert result == "test_char_framepack.safetensors"

    def test_diffusers_format_rejected(self, tmp_path):
        """Musubi/diffusers format LoRA (diffusion_model.* keys) must be rejected."""
        lora_path = tmp_path / "rosa_framepack.safetensors"
        _make_diffusers_lora(lora_path)

        result = validate_framepack_lora(lora_path)
        assert result is None

    def test_missing_file_returns_none(self, tmp_path):
        """Non-existent LoRA file should return None, not raise."""
        lora_path = tmp_path / "nonexistent_framepack.safetensors"

        result = validate_framepack_lora(lora_path)
        assert result is None

    def test_corrupt_file_returns_none(self, tmp_path):
        """Corrupt/unreadable LoRA file should return None, not raise."""
        lora_path = tmp_path / "corrupt_framepack.safetensors"
        _make_corrupt_file(lora_path)

        result = validate_framepack_lora(lora_path)
        assert result is None

    def test_empty_keys_returns_none(self, tmp_path):
        """LoRA file with no tensors should return None."""
        import json

        lora_path = tmp_path / "empty_framepack.safetensors"
        header = {}
        header_bytes = json.dumps(header).encode("utf-8")
        header_size = struct.pack("<Q", len(header_bytes))
        lora_path.write_bytes(header_size + header_bytes)

        result = validate_framepack_lora(lora_path)
        assert result is None


class TestLoRADetectionByCharacter:
    """Test the character-slug-based LoRA lookup matching builder.py logic."""

    def _find_fp_lora(self, lora_dir: Path, character_slug: str) -> str | None:
        """Replicate builder.py's LoRA detection with safety gate."""
        for suffix in ("_framepack_lora", "_framepack"):
            lp = lora_dir / f"{character_slug}{suffix}.safetensors"
            if lp.exists():
                result = validate_framepack_lora(lp)
                return result  # Return even if None (incompatible), stop searching
        return None

    def test_character_with_kohya_lora(self, tmp_path):
        """Character with a valid kohya LoRA gets it attached."""
        _make_kohya_lora(tmp_path / "goblin_slayer_framepack_lora.safetensors")
        result = self._find_fp_lora(tmp_path, "goblin_slayer")
        assert result == "goblin_slayer_framepack_lora.safetensors"

    def test_character_with_incompatible_lora(self, tmp_path):
        """Character with diffusers-format LoRA gets None (runs LoRA-free)."""
        _make_diffusers_lora(tmp_path / "rosa_framepack.safetensors")
        result = self._find_fp_lora(tmp_path, "rosa")
        assert result is None

    def test_character_with_no_lora(self, tmp_path):
        """Character with no LoRA file on disk runs LoRA-free."""
        result = self._find_fp_lora(tmp_path, "roxy")
        assert result is None

    def test_prefers_framepack_lora_suffix(self, tmp_path):
        """_framepack_lora suffix is checked before _framepack suffix."""
        _make_kohya_lora(tmp_path / "test_framepack_lora.safetensors")
        _make_diffusers_lora(tmp_path / "test_framepack.safetensors")

        result = self._find_fp_lora(tmp_path, "test")
        # Should find the _framepack_lora variant first (kohya format)
        assert result == "test_framepack_lora.safetensors"

    def test_incompatible_first_suffix_blocks_second(self, tmp_path):
        """If _framepack_lora exists but is incompatible, don't fall through to _framepack."""
        _make_diffusers_lora(tmp_path / "rosa_framepack_lora.safetensors")
        _make_kohya_lora(tmp_path / "rosa_framepack.safetensors")

        result = self._find_fp_lora(tmp_path, "rosa")
        # First match (_framepack_lora) is incompatible → returns None
        # Does NOT try _framepack — matches builder.py's break-after-find behavior
        assert result is None
