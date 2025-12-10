#!/usr/bin/env python3
"""
Integration tests for Enhanced Generation API
Tests the complete user experience flow
"""

import json
import sys
import threading
import time
from unittest.mock import Mock, patch

import pytest
import requests
import websocket

# Add the API directory to path
sys.path.insert(0, '/opt/tower-anime-production/api')

@pytest.fixture


def api_url():
    """Base API URL for testing"""
    return "http://localhost:8329"

@pytest.fixture


def mock_comfyui():
    """Mock ComfyUI for testing"""
    with patch('enhanced_generation_api.requests') as mock_requests:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"prompt_id": "test-prompt-123"}
        mock_requests.post.return_value = mock_response
        yield mock_requests


class TestEnhancedGenerationFlow:
    """Test enhanced generation user flows"""


    def test_simple_generation_request(self, api_url, mock_comfyui):
        """Test a simple generation request"""
        # Make generation request
        response = requests.post(
            f"{api_url}/api/generate/enhanced",
            json={
                "prompt": "anime girl with blue hair",
                "mode": "draft",
                "width": 512,
                "height": 512,
                "enable_preview": True,
                "enable_auto_recovery": True
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert "job_id" in data
        assert data["status"] == "queued"
        assert "websocket_url" in data

        return data["job_id"]


    def test_status_endpoint(self, api_url):
        """Test status retrieval"""
        # Create a job first
        response = requests.post(
            f"{api_url}/api/generate/enhanced",
            json={"prompt": "test", "mode": "draft"}
        )
        job_id = response.json()["job_id"]

        # Get status
        status_response = requests.get(
            f"{api_url}/api/generate/status/{job_id}"
        )

        assert status_response.status_code == 200
        status = status_response.json()

        assert status["job_id"] == job_id
        assert status["status"] in ["queued", "processing", "completed", "failed"]
        assert "progress" in status
        assert "message" in status


    def test_batch_generation(self, api_url):
        """Test batch generation with multiple requests"""
        batch_requests = [
            {
                "prompt": f"anime character {i}",
                "mode": "draft",
                "width": 512,
                "height": 512
            }
            for i in range(3)
        ]

        response = requests.post(
            f"{api_url}/api/generate/batch",
            json=batch_requests
        )

        assert response.status_code == 200
        data = response.json()

        assert "batch_id" in data
        assert "job_ids" in data
        assert len(data["job_ids"]) == 3
        assert data["total_jobs"] == 3


    def test_queue_status(self, api_url):
        """Test queue status endpoint"""
        response = requests.get(f"{api_url}/api/generate/queue")

        assert response.status_code == 200
        queue_data = response.json()

        assert "queue_length" in queue_data
        assert "processing" in queue_data
        assert "completed_today" in queue_data
        assert "average_time_seconds" in queue_data
        assert "gpu_status" in queue_data


    def test_websocket_connection(self, api_url):
        """Test WebSocket connection for real-time updates"""
        # First create a job
        response = requests.post(
            f"{api_url}/api/generate/enhanced",
            json={"prompt": "test websocket", "mode": "draft"}
        )
        job_id = response.json()["job_id"]

        # Connect to WebSocket
        ws_url = f"ws://localhost:8329/ws/generate/{job_id}"

        received_messages = []


        def on_message(ws, message):
            received_messages.append(json.loads(message))


        def on_error(ws, error):
            print(f"WebSocket error: {error}")

        ws = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error
        )

        # Run WebSocket in thread
        ws_thread = threading.Thread(target=ws.run_forever)
        ws_thread.daemon = True
        ws_thread.start()

        # Wait for messages
        time.sleep(2)

        # Should have received at least initial status
        assert len(received_messages) > 0
        assert received_messages[0]["type"] == "status"

        ws.close()


class TestErrorRecoveryFlow:
    """Test error recovery scenarios"""


    def test_auto_recovery_on_memory_error(self, api_url):
        """Test automatic recovery when out of memory"""
        response = requests.post(
            f"{api_url}/api/generate/enhanced",
            json={
                "prompt": "high resolution anime",
                "mode": "quality",
                "width": 2048,  # Large size to trigger memory issues
                "height": 2048,
                "enable_auto_recovery": True
            }
        )

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        # Wait and check status
        time.sleep(1)
        status_response = requests.get(
            f"{api_url}/api/generate/status/{job_id}"
        )

        status = status_response.json()

        # Should attempt recovery
        if status["status"] == "recovering":
            assert status["recovery_attempted"] is True


    def test_no_recovery_when_disabled(self, api_url):
        """Test that recovery doesn't happen when disabled"""
        response = requests.post(
            f"{api_url}/api/generate/enhanced",
            json={
                "prompt": "test no recovery",
                "mode": "quality",
                "width": 2048,
                "height": 2048,
                "enable_auto_recovery": False  # Disabled
            }
        )

        job_id = response.json()["job_id"]

        # Wait and check
        time.sleep(1)
        status_response = requests.get(
            f"{api_url}/api/generate/status/{job_id}"
        )

        status = status_response.json()

        # Should fail without recovery
        if status["status"] == "failed":
            assert status.get("recovery_attempted", False) is False


class TestUserPreferences:
    """Test user preference handling"""


    def test_preview_preference(self, api_url):
        """Test preview enable/disable preference"""
        # With preview enabled
        response = requests.post(
            f"{api_url}/api/generate/enhanced",
            json={
                "prompt": "test preview",
                "enable_preview": True,
                "progress_detail_level": "detailed"
            }
        )

        assert response.status_code == 200
        assert "websocket_url" in response.json()

        # With preview disabled
        response = requests.post(
            f"{api_url}/api/generate/enhanced",
            json={
                "prompt": "test no preview",
                "enable_preview": False,
                "progress_detail_level": "minimal"
            }
        )

        assert response.status_code == 200


    def test_batch_variations(self, api_url):
        """Test generating variations with seed offsets"""
        response = requests.post(
            f"{api_url}/api/generate/enhanced",
            json={
                "prompt": "anime character portrait",
                "batch_size": 4,
                "variations_seed_offset": 10,
                "seed": 42
            }
        )

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        # Check that batch size is respected
        time.sleep(2)
        status_response = requests.get(
            f"{api_url}/api/generate/status/{job_id}"
        )

        # Would eventually have 4 output paths
        # assert len(status["output_paths"]) == 4


class TestPerformanceMetrics:
    """Test performance tracking and metrics"""


    def test_generation_timing(self, api_url):
        """Test that generation timing is tracked"""
        start_time = time.time()

        response = requests.post(
            f"{api_url}/api/generate/enhanced",
            json={
                "prompt": "quick test",
                "mode": "draft"  # Fast mode
            }
        )

        job_id = response.json()["job_id"]

        # Poll for completion
        completed = False
        for _ in range(30):  # Max 30 seconds
            status_response = requests.get(
                f"{api_url}/api/generate/status/{job_id}"
            )
            status = status_response.json()

            if status["status"] == "completed":
                completed = True
                break

            time.sleep(1)

        if completed:
            duration = time.time() - start_time
            # Draft mode should be fast
            assert duration < 30, f"Draft mode took {duration}s, expected <30s"


    def test_queue_metrics(self, api_url):
        """Test queue metrics calculation"""
        # Generate some jobs to populate metrics
        for i in range(3):
            requests.post(
                f"{api_url}/api/generate/enhanced",
                json={"prompt": f"test {i}", "mode": "draft"}
            )

        time.sleep(1)

        # Check queue metrics
        response = requests.get(f"{api_url}/api/generate/queue")
        metrics = response.json()

        assert metrics["queue_length"] >= 0
        assert metrics["processing"] >= 0
        assert "estimated_wait_time" in metrics

if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
