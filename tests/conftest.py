"""
Pytest configuration and fixtures for Tower Anime Production tests
"""

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


# Register custom markers


def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers", "performance: mark test as a performance benchmark"
    )
    config.addinivalue_line("markers", "e2e: mark test as an end-to-end test")
    config.addinivalue_line("markers", "slow: mark test as slow running")


# ============= Mock Services =============


@pytest.fixture
def mock_comfyui():
    """Mock ComfyUI API client"""
    mock = Mock()
    mock.url = "http://localhost:8188"

    # Mock workflow execution
    mock.queue_prompt.return_value = "test-prompt-123"

    # Mock status checking
    mock.get_status.side_effect = [
        {"status": "queued", "progress": 0},
        {"status": "processing", "progress": 25},
        {"status": "processing", "progress": 50},
        {"status": "processing", "progress": 75},
        {"status": "completed", "progress": 100, "output": "/path/to/output.png"},
    ]

    # Mock history
    mock.get_history.return_value = {
        "test-prompt-123": {
            "outputs": {"9": {"images": [{"filename": "test_output.png"}]}}
        }
    }

    return mock


@pytest.fixture
def mock_database():
    """Mock database connection"""
    mock_db = Mock()

    # Mock query results
    mock_query = Mock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = None
    mock_query.all.return_value = []
    mock_query.offset.return_value = mock_query
    mock_query.limit.return_value = mock_query

    mock_db.query.return_value = mock_query
    mock_db.add = Mock()
    mock_db.commit = Mock()
    mock_db.refresh = Mock()
    mock_db.delete = Mock()
    mock_db.rollback = Mock()

    return mock_db


@pytest.fixture
def mock_echo_brain():
    """Mock Echo Brain service"""
    mock = AsyncMock()
    mock.url = "http://localhost:8309"

    # Mock query responses
    mock.query.return_value = {
        "response": "Generated story content",
        "confidence": 0.95,
        "model": "qwen2.5-coder:32b",
    }

    # Mock quality assessment
    mock.assess_quality.return_value = {
        "score": 0.88,
        "feedback": "Good consistency, minor artifacts detected",
    }

    return mock


@pytest.fixture
def mock_apple_music():
    """Mock Apple Music service"""
    mock = Mock()
    mock.url = "http://localhost:8315"

    # Mock BPM analysis
    mock.analyze_video_tempo.return_value = 120.0

    # Mock track search
    mock.search_by_bpm.return_value = [
        {"id": "track1", "name": "Test Track", "bpm": 120, "artist": "Test Artist"},
        {
            "id": "track2",
            "name": "Another Track",
            "bpm": 118,
            "artist": "Another Artist",
        },
    ]

    # Mock sync
    mock.sync_to_video.return_value = "/path/to/synced_video.mp4"

    return mock


# ============= Sample Data =============


@pytest.fixture
def sample_project():
    """Sample project data"""
    return {
        "id": 1,
        "name": "Test Anime Project",
        "description": "Automated test project",
        "type": "series",
        "bible": {
            "genre": "shounen",
            "themes": ["friendship", "adventure"],
            "target_audience": "13-18",
        },
        "status": "active",
        "created_at": "2025-12-10T00:00:00",
    }


@pytest.fixture
def sample_character():
    """Sample character data"""
    return {
        "id": 1,
        "name": "Kai Nakamura",
        "project_id": 1,
        "description": "Main protagonist",
        "personality_traits": ["brave", "determined", "kind"],
        "visual_description": "Spiky black hair, blue eyes, athletic build",
        "reference_image": "/path/to/reference.png",
        "embedding_data": [0.1] * 512,
        "color_palette": {
            "hair": [30, 30, 35],
            "eyes": [100, 150, 200],
            "skin": [250, 220, 190],
        },
    }


@pytest.fixture
def sample_generation_job():
    """Sample generation job data"""
    return {
        "id": 123,
        "project_id": 1,
        "prompt": "anime character in action scene",
        "status": "processing",
        "progress": 45,
        "comfyui_prompt_id": "test-prompt-123",
        "output_path": None,
        "created_at": "2025-12-10T12:00:00",
        "workflow_params": {
            "model": "AOM3A1B",
            "steps": 15,
            "cfg_scale": 7.0,
            "seed": 42,
        },
    }


@pytest.fixture
def sample_image():
    """Create a sample image array"""
    np.random.seed(42)
    return np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8)


@pytest.fixture
def sample_embedding():
    """Generate a sample embedding vector"""
    np.random.seed(42)
    return np.random.randn(512).tolist()


# ============= File System =============


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create temporary project directory structure"""
    project_dir = tmp_path / "projects" / "test_project"
    project_dir.mkdir(parents=True)

    # Create subdirectories
    (project_dir / "characters").mkdir()
    (project_dir / "scenes").mkdir()
    (project_dir / "output").mkdir()

    return project_dir


@pytest.fixture
def sample_workflow():
    """Sample ComfyUI workflow"""
    return {
        "prompt": {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 42,
                    "steps": 15,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
            }
        }
    }


# ============= API Client =============


@pytest.fixture
def api_base_url():
    """Base URL for API tests"""
    return "http://localhost:8328/api/anime"


@pytest.fixture
def auth_headers():
    """Authentication headers for protected endpoints"""
    return {
        "Authorization": "Bearer test_token_12345",
        "Content-Type": "application/json",
    }


# ============= Async Support =============


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============= Performance Testing =============


@pytest.fixture
def benchmark_timer():
    """Simple benchmark timer"""
    import time

    class Timer:

        def __init__(self):
            self.times = []

        def __enter__(self):
            self.start = time.time()
            return self

        def __exit__(self, *args):
            self.times.append(time.time() - self.start)

        @property
        def average(self):
            return sum(self.times) / len(self.times) if self.times else 0

        @property
        def total(self):
            return sum(self.times)

    return Timer()


# ============= WebSocket Testing =============


@pytest.fixture
async def mock_websocket():
    """Mock WebSocket connection"""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    ws.close = AsyncMock()

    # Mock receiving progress updates
    ws.recv.side_effect = [
        json.dumps({"type": "progress", "progress": 0}),
        json.dumps({"type": "progress", "progress": 25}),
        json.dumps({"type": "progress", "progress": 50}),
        json.dumps({"type": "progress", "progress": 75}),
        json.dumps({"type": "progress", "progress": 100, "status": "completed"}),
    ]

    return ws
