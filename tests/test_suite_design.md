# Tower Anime Production - Comprehensive Test Suite Design

## 🎯 Testing Strategy

### Testing Pyramid
```
         /\
        /E2E\      <- End-to-end tests (10%)
       /------\
      /  INTG  \   <- Integration tests (30%)
     /----------\
    /    UNIT    \ <- Unit tests (60%)
   /--------------\
```

## 📦 Test Categories

### 1. Unit Tests (60% coverage target)
- **Character Consistency Engine**
- **Quality Metrics Calculator**
- **BPM Analysis Functions**
- **File Management Utilities**
- **Database Models**

### 2. Integration Tests (30% coverage target)
- **API Endpoints**
- **Service Communication**
- **Database Operations**
- **External Service Mocks**

### 3. End-to-End Tests (10% coverage target)
- **Complete Generation Pipeline**
- **Project Lifecycle**
- **Multi-service Workflows**

## 🧪 Test Implementation

### Directory Structure
```
tests/
├── unit/
│   ├── test_character_consistency.py
│   ├── test_quality_metrics.py
│   ├── test_bpm_analyzer.py
│   └── test_file_manager.py
├── integration/
│   ├── test_api_endpoints.py
│   ├── test_apple_music_integration.py
│   ├── test_comfyui_integration.py
│   └── test_echo_brain_integration.py
├── e2e/
│   ├── test_generation_pipeline.py
│   ├── test_project_workflow.py
│   └── test_character_studio.py
├── performance/
│   ├── benchmark_generation.py
│   ├── benchmark_consistency.py
│   └── benchmark_api_response.py
├── fixtures/
│   ├── sample_images/
│   ├── sample_videos/
│   ├── mock_responses/
│   └── test_data.json
└── conftest.py
```

## 🔬 Unit Test Specifications

### 1. Character Consistency Engine Tests
```python
# test_character_consistency.py
import pytest
from api.character_consistency_engine import CharacterConsistencyEngine

class TestCharacterConsistency:
    """Test character consistency algorithms"""

    def test_embedding_generation(self):
        """Test that embeddings are generated correctly"""
        engine = CharacterConsistencyEngine()
        image_path = "fixtures/sample_images/kai_reference.png"

        embedding = engine.generate_embedding(image_path)

        assert embedding is not None
        assert len(embedding) == 512  # Expected embedding size
        assert all(-1 <= val <= 1 for val in embedding)

    def test_consistency_score_calculation(self):
        """Test consistency score between two embeddings"""
        engine = CharacterConsistencyEngine()

        # Same image should have high consistency
        embedding1 = engine.generate_embedding("fixtures/kai_1.png")
        embedding2 = engine.generate_embedding("fixtures/kai_2.png")

        score = engine.calculate_consistency_score(embedding1, embedding2)

        assert 0.85 <= score <= 1.0  # High consistency expected

    def test_style_preservation(self):
        """Test that style templates are preserved"""
        engine = CharacterConsistencyEngine()

        style = engine.extract_style_template("fixtures/anime_style.png")

        assert "line_weight" in style
        assert "color_saturation" in style
        assert "shading_type" in style

    def test_color_palette_extraction(self):
        """Test color palette extraction from reference"""
        engine = CharacterConsistencyEngine()

        palette = engine.extract_color_palette("fixtures/kai_reference.png")

        assert "hair_color" in palette
        assert "eye_color" in palette
        assert "skin_tone" in palette
        assert all(0 <= val <= 255 for color in palette.values() for val in color)

    @pytest.mark.parametrize("threshold,expected_result", [
        (0.9, False),  # Too strict
        (0.7, True),   # Good threshold
        (0.5, True),   # Too lenient
    ])
    def test_consistency_threshold(self, threshold, expected_result):
        """Test different consistency thresholds"""
        engine = CharacterConsistencyEngine()
        engine.consistency_threshold = threshold

        result = engine.check_consistency("fixtures/kai_1.png", "fixtures/kai_variant.png")

        assert result == expected_result
```

### 2. Quality Metrics Tests
```python
# test_quality_metrics.py
import pytest
import numpy as np
from services.quality_metrics_v2 import QualityMetrics

class TestQualityMetrics:
    """Test generation quality measurement"""

    def test_sharpness_calculation(self):
        """Test image sharpness calculation"""
        metrics = QualityMetrics()

        sharp_image = np.random.randn(512, 512, 3) * 255
        blurry_image = np.ones((512, 512, 3)) * 128

        sharp_score = metrics.calculate_sharpness(sharp_image)
        blurry_score = metrics.calculate_sharpness(blurry_image)

        assert sharp_score > blurry_score
        assert 0 <= sharp_score <= 1

    def test_artifact_detection(self):
        """Test artifact detection in generated images"""
        metrics = QualityMetrics()

        clean_image = "fixtures/clean_generation.png"
        artifact_image = "fixtures/artifact_generation.png"

        clean_artifacts = metrics.detect_artifacts(clean_image)
        bad_artifacts = metrics.detect_artifacts(artifact_image)

        assert clean_artifacts < 0.1  # Few artifacts
        assert bad_artifacts > 0.5    # Many artifacts

    def test_quality_gate_evaluation(self):
        """Test quality gate pass/fail logic"""
        metrics = QualityMetrics()

        good_metrics = {
            "sharpness": 0.9,
            "consistency": 0.88,
            "artifacts": 0.05
        }

        bad_metrics = {
            "sharpness": 0.4,
            "consistency": 0.6,
            "artifacts": 0.7
        }

        assert metrics.passes_quality_gate(good_metrics) == True
        assert metrics.passes_quality_gate(bad_metrics) == False
```

## 🔗 Integration Test Specifications

### 1. API Endpoint Tests
```python
# test_api_endpoints.py
import pytest
from fastapi.testclient import TestClient
from api.secured_api import app

class TestAPIEndpoints:
    """Test all API endpoints"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/api/anime/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert "comfyui" in response.json()["components"]

    def test_project_creation(self, client):
        """Test project creation workflow"""
        project_data = {
            "name": "Test Project",
            "description": "Automated test project",
            "type": "series"
        }

        response = client.post("/api/anime/projects", json=project_data)

        assert response.status_code == 201
        assert response.json()["name"] == "Test Project"
        assert "id" in response.json()

    def test_generation_request(self, client, mock_comfyui):
        """Test generation request with mocked ComfyUI"""
        generation_data = {
            "prompt": "anime girl with blue hair",
            "model": "AOM3A1B",
            "steps": 15,
            "cfg_scale": 7.0
        }

        response = client.post("/api/anime/generate", json=generation_data)

        assert response.status_code == 202
        assert "job_id" in response.json()
        assert response.json()["status"] == "processing"

    @pytest.mark.asyncio
    async def test_job_progress_tracking(self, client):
        """Test real-time job progress"""
        # Start generation
        response = client.post("/api/anime/generate/quick",
                              json={"prompt": "test"})
        job_id = response.json()["job_id"]

        # Check progress multiple times
        progress_values = []
        for _ in range(5):
            await asyncio.sleep(1)
            progress_response = client.get(f"/api/anime/jobs/{job_id}/progress")
            progress_values.append(progress_response.json()["progress"])

        # Progress should increase
        assert progress_values == sorted(progress_values)
        assert progress_values[-1] > progress_values[0]
```

### 2. Apple Music Integration Tests
```python
# test_apple_music_integration.py
import pytest
from unittest.mock import Mock, patch

class TestAppleMusicIntegration:
    """Test Apple Music BPM sync integration"""

    @patch('requests.get')
    def test_bpm_analysis(self, mock_get):
        """Test BPM analysis of video"""
        from integrations.apple_music import AppleMusicClient

        client = AppleMusicClient()
        video_path = "fixtures/sample_videos/action_scene.mp4"

        bpm = client.analyze_video_tempo(video_path)

        assert 60 <= bpm <= 180  # Reasonable BPM range
        assert isinstance(bpm, (int, float))

    @patch('requests.get')
    def test_track_search_by_bpm(self, mock_get):
        """Test finding tracks by BPM"""
        mock_get.return_value.json.return_value = {
            "data": [{
                "id": "123",
                "attributes": {
                    "name": "Test Track",
                    "artistName": "Test Artist",
                    "tempo": 120
                }
            }]
        }

        client = AppleMusicClient()
        tracks = client.find_tracks_by_bpm(120, tolerance=10)

        assert len(tracks) > 0
        assert all(110 <= t["tempo"] <= 130 for t in tracks)

    def test_music_video_sync(self):
        """Test synchronizing music to video"""
        client = AppleMusicClient()

        video_path = "fixtures/sample_videos/5sec_anime.mp4"
        track_id = "test_track_123"

        synced_path = client.sync_music_to_video(video_path, track_id)

        assert synced_path.exists()
        assert synced_path.suffix == ".mp4"
        # Verify audio track was added
        assert has_audio_track(synced_path)
```

## 🚀 End-to-End Test Specifications

### 1. Complete Generation Pipeline
```python
# test_generation_pipeline.py
import pytest
import time

class TestGenerationPipeline:
    """Test complete generation workflow"""

    @pytest.mark.slow
    @pytest.mark.e2e
    def test_full_character_generation(self):
        """Test creating character and generating consistent images"""

        # 1. Create project
        project = create_test_project("E2E Test Project")

        # 2. Create character with reference
        character = create_character(
            project_id=project.id,
            name="Test Character",
            reference_image="fixtures/reference.png"
        )

        # 3. Generate multiple images with consistency
        images = []
        for i in range(3):
            job = request_generation(
                project_id=project.id,
                character_id=character.id,
                prompt=f"character in scene {i}"
            )

            # Wait for completion
            result = wait_for_job(job.id, timeout=600)
            images.append(result.output_path)

        # 4. Verify consistency across all images
        consistency_scores = []
        for i in range(len(images)-1):
            score = calculate_consistency(images[i], images[i+1])
            consistency_scores.append(score)

        assert all(score > 0.85 for score in consistency_scores)

        # 5. Clean up
        cleanup_project(project.id)

    @pytest.mark.slow
    @pytest.mark.e2e
    def test_video_generation_with_music(self):
        """Test video generation with Apple Music sync"""

        # 1. Generate video
        video_job = request_video_generation(
            prompt="action scene with explosions",
            duration=5,
            fps=8
        )

        video_path = wait_for_job(video_job.id)

        # 2. Analyze tempo
        bpm = analyze_video_tempo(video_path)

        # 3. Find matching music
        tracks = search_music_by_bpm(bpm, mood="energetic")
        assert len(tracks) > 0

        # 4. Sync music to video
        final_video = sync_music_to_video(video_path, tracks[0].id)

        # 5. Verify output
        assert final_video.exists()
        assert has_audio_track(final_video)
        assert get_video_duration(final_video) == 5.0
```

## ⚡ Performance Benchmark Tests

### 1. Generation Speed Benchmarks
```python
# benchmark_generation.py
import pytest
import time
from statistics import mean, stdev

class BenchmarkGeneration:
    """Benchmark generation performance"""

    @pytest.mark.benchmark
    def test_image_generation_speed(self, benchmark):
        """Benchmark single image generation"""

        def generate_image():
            response = request_generation(
                prompt="simple test prompt",
                steps=15,
                draft_mode=True
            )
            wait_for_job(response.job_id)

        result = benchmark(generate_image)

        # Target: < 60 seconds for draft mode
        assert result.stats['mean'] < 60

        print(f"Mean time: {result.stats['mean']:.2f}s")
        print(f"Std dev: {result.stats['stddev']:.2f}s")

    @pytest.mark.benchmark
    def test_consistency_calculation_speed(self, benchmark):
        """Benchmark consistency score calculation"""

        engine = CharacterConsistencyEngine()
        img1 = "fixtures/kai_1.png"
        img2 = "fixtures/kai_2.png"

        result = benchmark(engine.calculate_consistency_score, img1, img2)

        # Target: < 100ms
        assert result.stats['mean'] < 0.1

    @pytest.mark.benchmark
    def test_api_response_time(self, benchmark):
        """Benchmark API endpoint response times"""

        client = TestClient(app)

        def call_health():
            response = client.get("/api/anime/health")
            assert response.status_code == 200

        result = benchmark(call_health)

        # Target: < 50ms
        assert result.stats['mean'] < 0.05
```

## 🔄 WebSocket Progress Tests

### 1. Real-time Progress Tracking
```python
# test_websocket_progress.py
import pytest
import asyncio
import websockets

class TestWebSocketProgress:
    """Test WebSocket progress updates"""

    @pytest.mark.asyncio
    async def test_progress_updates(self):
        """Test receiving progress updates via WebSocket"""

        # Start generation job
        job_id = start_test_generation()

        # Connect to WebSocket
        async with websockets.connect(f"ws://localhost:8328/ws/{job_id}") as ws:
            progress_updates = []

            while True:
                message = await ws.recv()
                data = json.loads(message)
                progress_updates.append(data["progress"])

                if data["status"] == "completed":
                    break

            # Verify progress increased monotonically
            assert progress_updates == sorted(progress_updates)
            assert progress_updates[-1] == 100

    @pytest.mark.asyncio
    async def test_multiple_job_tracking(self):
        """Test tracking multiple jobs simultaneously"""

        # Start multiple jobs
        job_ids = [start_test_generation() for _ in range(3)]

        # Track all jobs
        tasks = [track_job_progress(job_id) for job_id in job_ids]
        results = await asyncio.gather(*tasks)

        # All should complete
        assert all(r["final_status"] == "completed" for r in results)
```

## 🧩 Test Fixtures & Mocks

### 1. ComfyUI Mock
```python
# conftest.py
import pytest
from unittest.mock import Mock

@pytest.fixture
def mock_comfyui():
    """Mock ComfyUI API for testing"""
    mock = Mock()

    # Mock workflow execution
    mock.execute_workflow.return_value = {
        "prompt_id": "test-prompt-123",
        "status": "queued"
    }

    # Mock progress checking
    mock.get_progress.side_effect = [
        {"progress": 0},
        {"progress": 25},
        {"progress": 50},
        {"progress": 75},
        {"progress": 100, "status": "completed"}
    ]

    return mock

@pytest.fixture
def sample_character():
    """Provide sample character for testing"""
    return {
        "id": 1,
        "name": "Kai Nakamura",
        "reference_embedding": [0.1] * 512,
        "style_template": {"type": "anime", "subtype": "shounen"},
        "color_palette": {
            "hair": [30, 30, 30],
            "eyes": [100, 150, 200],
            "skin": [250, 220, 190]
        }
    }
```

## 🚦 Test Execution Strategy

### CI/CD Pipeline
```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.12'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-dev.txt

    - name: Run unit tests
      run: pytest tests/unit -v --cov=api --cov-report=xml

    - name: Run integration tests
      run: pytest tests/integration -v

    - name: Run performance benchmarks
      run: pytest tests/performance -v --benchmark-only

    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

### Local Testing Commands
```bash
# Run all tests
pytest tests/

# Run specific test category
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# Run with coverage
pytest --cov=api --cov-report=html

# Run benchmarks
pytest tests/performance/ --benchmark-only

# Run specific test
pytest tests/unit/test_character_consistency.py::test_embedding_generation

# Run with markers
pytest -m "not slow"  # Skip slow tests
pytest -m e2e         # Only E2E tests
```

## 📊 Coverage Targets

| Component | Target | Priority |
|-----------|--------|----------|
| Character Consistency Engine | 90% | Critical |
| API Endpoints | 85% | High |
| Quality Metrics | 80% | High |
| File Management | 75% | Medium |
| Apple Music Integration | 70% | Medium |
| Database Operations | 80% | High |
| WebSocket Progress | 60% | Low |

## 🎯 Success Criteria

1. **Unit Tests**: Pass rate > 98%, execution time < 30s
2. **Integration Tests**: Pass rate > 95%, execution time < 2min
3. **E2E Tests**: Pass rate > 90%, execution time < 10min
4. **Performance**:
   - Image generation < 60s (draft mode)
   - API response < 50ms
   - Consistency calculation < 100ms
5. **Coverage**: Overall > 80%, critical components > 90%

## 📝 Next Steps

1. Implement test fixtures and sample data
2. Set up testing database with migrations
3. Create mock services for external dependencies
4. Write initial unit tests for character consistency
5. Set up CI/CD pipeline with GitHub Actions
6. Create performance baseline measurements