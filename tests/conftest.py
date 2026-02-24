"""Shared test fixtures and mocks for the Anime Studio test suite.

Provides:
- mock_db_pool: AsyncMock of asyncpg connection pool
- mock_comfyui: Patches urllib.request for ComfyUI HTTP calls
- mock_ollama: Patches urllib.request for Ollama vision model calls
- mock_filesystem: tmp_path-based dataset directory
- event_bus_spy: Fresh EventBus with captured events
- sample_char_map: Dict matching get_char_project_map() output shape
- app_client: httpx.AsyncClient wrapping the FastAPI app
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the project root is on sys.path so `packages.*` imports resolve
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: live integration test (requires running services)")
    config.addinivalue_line("markers", "slow: test takes > 5 seconds")
    config.addinivalue_line("markers", "unit: fast unit test")


# ---------------------------------------------------------------------------
# Mock DB Pool
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_conn():
    """A single mock asyncpg connection with fetch/fetchrow/fetchval/execute."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    conn.execute = AsyncMock()
    return conn


class _MockAsyncCtx:
    """Async context manager that yields a fixed value."""
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


@pytest.fixture
def mock_db_pool(mock_conn):
    """AsyncMock of asyncpg connection pool.

    Usage in tests:
        async with pool.acquire() as conn:
            conn.fetch.return_value = [...]
    """
    pool = MagicMock()
    pool.acquire.return_value = _MockAsyncCtx(mock_conn)
    return pool


@pytest.fixture
def patch_get_pool(mock_db_pool):
    """Patch get_pool everywhere it's imported to return the mock pool.

    Modules import get_pool via `from .db import get_pool`, so we must
    patch at every usage site, not just the definition.
    """
    targets = [
        "packages.core.db.get_pool",
        "packages.core.audit.get_pool",
        "packages.core.learning.get_pool",
        "packages.core.model_selector.get_pool",
        "packages.core.auto_correction.get_pool",
        "packages.core.replenishment.get_pool",
    ]
    patches = [patch(t, new_callable=AsyncMock, return_value=mock_db_pool) for t in targets]
    for p in patches:
        p.start()
    yield mock_db_pool
    for p in patches:
        p.stop()


# ---------------------------------------------------------------------------
# Mock ComfyUI
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_comfyui():
    """Patches urllib.request.urlopen for ComfyUI HTTP calls.

    Returns a MagicMock whose .return_value.read() can be configured per test.
    """
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"prompt_id": "test-prompt-123"}).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as m:
        m._mock_resp = mock_resp  # expose for per-test configuration
        yield m


# ---------------------------------------------------------------------------
# Mock Ollama
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ollama():
    """Patches urllib.request.urlopen for Ollama vision model HTTP calls."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "response": json.dumps({
            "character_match": 8,
            "is_human": True,
            "solo": True,
            "clarity": 9,
            "completeness": "full",
            "training_value": 8,
            "caption": "Test character in standing pose",
            "issues": [],
        })
    }).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as m:
        m._mock_resp = mock_resp
        yield m


# ---------------------------------------------------------------------------
# Mock Filesystem
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_filesystem(tmp_path):
    """Create a temporary dataset directory structure with sample data.

    Layout:
        tmp_path/
        └── luigi/
            ├── images/
            │   └── gen_luigi_test_001.png  (1x1 white PNG)
            ├── approval_status.json
            └── feedback.json
    """
    char_dir = tmp_path / "luigi" / "images"
    char_dir.mkdir(parents=True)

    # Minimal valid PNG (1x1 white pixel)
    import struct
    import zlib
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc
    raw = zlib.compress(b"\x00\xff\xff\xff")
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + raw) & 0xFFFFFFFF)
    idat = struct.pack(">I", len(raw)) + b"IDAT" + raw + idat_crc
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    iend = struct.pack(">I", 0) + b"IEND" + iend_crc
    png_bytes = sig + ihdr + idat + iend

    test_img = char_dir / "gen_luigi_test_001.png"
    test_img.write_bytes(png_bytes)

    approval_status = {"gen_luigi_test_001.png": "pending"}
    (tmp_path / "luigi" / "approval_status.json").write_text(json.dumps(approval_status))

    feedback = {"rejections": [], "rejection_count": 0, "negative_additions": []}
    (tmp_path / "luigi" / "feedback.json").write_text(json.dumps(feedback))

    return tmp_path


# ---------------------------------------------------------------------------
# EventBus Spy
# ---------------------------------------------------------------------------

@pytest.fixture
def event_bus_spy():
    """Fresh EventBus instance per test with captured events list."""
    from packages.core.events import EventBus

    bus = EventBus()
    captured = []

    async def _capture(data):
        captured.append(data)

    bus._captured = captured
    bus._capture_handler = _capture
    return bus


# ---------------------------------------------------------------------------
# Sample Character Map
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_char_map():
    """Dict matching get_char_project_map() output shape."""
    return {
        "luigi": {
            "name": "Luigi",
            "slug": "luigi",
            "project_name": "Super Mario Galaxy Anime Adventure",
            "design_prompt": "tall thin man in green cap with letter L, green shirt, blue overalls",
            "appearance_data": {"species": "human", "key_colors": {"cap": "green", "overalls": "blue"}},
            "default_style": "mario_galaxy_style",
            "checkpoint_model": "realcartoonPixar_v12.safetensors",
            "cfg_scale": 8.5,
            "steps": 40,
            "sampler": "DPM++ 2M Karras",
            "scheduler": "karras",
            "width": 512,
            "height": 768,
            "resolution": "512x768",
            "positive_prompt_template": "masterpiece, best quality, Illumination 3D CGI",
            "negative_prompt_template": "worst quality, low quality, blurry, deformed",
            "style_preamble": "Illumination Studios style, Pixar 3D render",
        },
        "bowser": {
            "name": "Bowser",
            "slug": "bowser",
            "project_name": "Super Mario Galaxy Anime Adventure",
            "design_prompt": "massive turtle-dragon with spiky green shell, horns, fangs",
            "appearance_data": {
                "species": "dragon-turtle (NOT human)",
                "key_colors": {"shell": "green", "skin": "yellow-orange"},
                "common_errors": ["depicted as child"],
            },
            "default_style": "mario_galaxy_style",
            "checkpoint_model": "realcartoonPixar_v12.safetensors",
            "cfg_scale": 8.5,
            "steps": 40,
            "sampler": "DPM++ 2M Karras",
            "scheduler": "karras",
            "width": 512,
            "height": 768,
            "resolution": "512x768",
            "positive_prompt_template": "masterpiece, best quality, Illumination 3D CGI",
            "negative_prompt_template": "worst quality, low quality, blurry, deformed",
            "style_preamble": None,
        },
    }


# ---------------------------------------------------------------------------
# FastAPI App Client
# ---------------------------------------------------------------------------

@pytest.fixture
async def app_client(patch_get_pool):
    """httpx.AsyncClient wrapping the FastAPI app for endpoint tests.

    The DB pool is mocked — no real database needed.
    """
    import httpx
    from server.app import app

    # Skip startup event (it tries to connect to real DB)
    app.router.on_startup.clear()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client
