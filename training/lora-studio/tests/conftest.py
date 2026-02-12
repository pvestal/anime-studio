"""Shared fixtures for LoRA Studio backend tests."""

import os
import sys
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set env vars BEFORE importing the app module so Vault/DB init is bypassed
os.environ["VAULT_TOKEN"] = ""
os.environ["DB_HOST"] = "localhost"
os.environ["DB_NAME"] = "test_db"
os.environ["DB_USER"] = "test"
os.environ["DB_PASSWORD"] = "test"

# Add src to path so we can import the API module
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import dataset_approval_api as api_module


# ---- Character data fixtures ----

@pytest.fixture
def sample_char_map():
    """Canonical test character data matching DB schema."""
    return {
        "mario": {
            "name": "Mario",
            "slug": "mario",
            "project_name": "Super Mario Galaxy Anime Adventure",
            "design_prompt": "Mario, red cap and blue overalls, mustache, Illumination 3D CGI style",
            "default_style": "illumination_3d",
            "checkpoint_model": "realcartoonPixar_v12.safetensors",
            "cfg_scale": 8.5,
            "steps": 40,
            "sampler": "DPM++ 2M Karras",
            "scheduler": "karras",
            "width": 512,
            "height": 768,
            "resolution": "512x768",
        },
        "mei_kobayashi": {
            "name": "Mei Kobayashi",
            "slug": "mei_kobayashi",
            "project_name": "Tokyo Debt Desire",
            "design_prompt": "Mei Kobayashi, young woman with short black hair, office outfit",
            "default_style": "realistic_anime",
            "checkpoint_model": "realistic_vision_v51.safetensors",
            "cfg_scale": 7.0,
            "steps": 25,
            "sampler": "DPM++ 2M Karras",
            "scheduler": "karras",
            "width": 512,
            "height": 768,
            "resolution": "512x768",
        },
    }


@pytest.fixture
def mock_char_project_map(sample_char_map):
    """Patch _get_char_project_map to return test data without DB."""
    async def _fake_map():
        return sample_char_map

    with patch.object(api_module, "_get_char_project_map", side_effect=_fake_map):
        yield sample_char_map


@pytest.fixture
def mock_comfyui_submit():
    """Patch _submit_comfyui_workflow to return a fake prompt_id."""
    with patch.object(
        api_module, "_submit_comfyui_workflow", return_value="test-prompt-id-123"
    ) as mock:
        yield mock


@pytest.fixture
def mock_comfyui_progress():
    """Patch _get_comfyui_progress to return staged status dicts."""
    def _fake_progress(prompt_id):
        return {"status": "completed", "progress": 1.0, "images": ["output_001.png"]}

    with patch.object(api_module, "_get_comfyui_progress", side_effect=_fake_progress) as mock:
        yield mock


@pytest.fixture
def mock_echo_brain_urlopen():
    """Patch urllib.request.urlopen for Echo Brain calls."""
    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps({
        "result": {
            "content": [{"type": "text", "text": "Echo Brain test response about the character."}]
        }
    }).encode()
    fake_response.__enter__ = lambda s: s
    fake_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=fake_response) as mock:
        yield mock


@pytest.fixture
def mock_subprocess():
    """Patch subprocess.Popen to prevent real process spawning."""
    fake_proc = MagicMock()
    fake_proc.pid = 99999
    with patch.object(api_module.subprocess, "Popen", return_value=fake_proc) as mock:
        yield mock


@pytest.fixture
def tmp_datasets(tmp_path):
    """Create temp dataset dirs with test images + approval_status.json."""
    datasets = tmp_path / "datasets"

    # Mario dataset with 2 images
    mario_dir = datasets / "mario" / "images"
    mario_dir.mkdir(parents=True)
    (mario_dir / "test_001.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    (mario_dir / "test_002.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    (mario_dir / "test_001.txt").write_text("Mario standing in a field")

    approval = {"test_001.png": "approved", "test_002.png": "pending"}
    (datasets / "mario" / "approval_status.json").write_text(json.dumps(approval))

    # Mei dataset (empty)
    mei_dir = datasets / "mei_kobayashi" / "images"
    mei_dir.mkdir(parents=True)

    return datasets


@pytest.fixture
async def client():
    """httpx AsyncClient with ASGI transport for testing the FastAPI app."""
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=api_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
