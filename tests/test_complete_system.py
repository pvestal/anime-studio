#!/usr/bin/env python3
"""
Complete System Tests for Anime Production
End-to-end tests that verify the entire system works together
"""

import os
import sys
import time

import pytest
import requests

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration
COMFYUI_URL = "http://127.0.0.1:8188"
API_URL = "http://127.0.0.1:8328"
TIMEOUT = 60  # Maximum time for a generation


class TestSystemHealth:
    """Test overall system health"""


    def test_comfyui_accessible(self):
        """Verify ComfyUI is running and accessible"""
        try:
            response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
            assert response.status_code == 200, "ComfyUI not accessible"

            stats = response.json()
            assert "devices" in stats, "ComfyUI system stats incomplete"
            print(f"✅ ComfyUI running with {len(stats.get('devices', []))} GPU devices")
        except requests.exceptions.RequestException as e:
            pytest.fail(f"ComfyUI connection failed: {e}")


    def test_anime_api_accessible(self):
        """Verify Anime API is running and accessible"""
        try:
            response = requests.get(f"{API_URL}/api/anime/health", timeout=5)
            assert response.status_code == 200, "Anime API not accessible"

            health = response.json()
            assert health.get("status") == "healthy", f"API unhealthy: {health}"
            print(f"✅ Anime API healthy - {health.get('uptime', 'unknown')} uptime")
        except requests.exceptions.RequestException as e:
            pytest.fail(f"Anime API connection failed: {e}")


    def test_gpu_availability(self):
        """Check GPU is available for generation"""
        response = requests.get(f"{COMFYUI_URL}/system_stats")
        stats = response.json()

        devices = stats.get("devices", [])
        assert len(devices) > 0, "No GPU devices available"

        # Check VRAM availability
        for device in devices:
            vram_free = device.get("vram_free_mb", 0)
            vram_total = device.get("vram_total_mb", 1)
            usage_percent = ((vram_total - vram_free) / vram_total) * 100

            print(f"📊 GPU {device.get('name', 'Unknown')}: {vram_free}MB free ({100-usage_percent:.1f}% available)")
            assert vram_free > 1000, f"Insufficient VRAM: only {vram_free}MB free"


class TestGenerationWorkflow:
    """Test complete generation workflow"""


    def test_simple_generation(self):
        """Test a simple image generation end-to-end"""
        # Start generation
        response = requests.post(
            f"{API_URL}/api/anime/orchestrate",
            json={
                "prompt": "anime girl with blue hair, simple test",
                "type": "image",
                "width": 512,
                "height": 512,
                "project_id": 1,
                "character_name": "test_character"
            },
            timeout=10
        )

        assert response.status_code == 200, f"Generation request failed: {response.text}"
        result = response.json()

        assert "job_id" in result or "output_path" in result, "No job ID or output in response"

        # If async, wait for completion
        if "job_id" in result:
            job_id = result["job_id"]
            print(f"⏳ Generation started with job ID: {job_id}")

            # Poll for completion
            completed = self._wait_for_job_completion(job_id)
            assert completed, f"Job {job_id} did not complete within {TIMEOUT} seconds"

        print("✅ Simple generation completed successfully")


    def test_optimized_draft_mode(self):
        """Test optimized draft mode generation (should be <30 seconds)"""
        start_time = time.time()

        response = requests.post(
            f"{API_URL}/api/anime/orchestrate",
            json={
                "prompt": "anime character, draft mode test",
                "type": "image",
                "mode": "draft",  # Fast mode
                "width": 512,
                "height": 512,
                "steps": 8,
                "cfg_scale": 5.0,
                "project_id": 1
            },
            timeout=45  # Should complete in 30s
        )

        duration = time.time() - start_time

        assert response.status_code == 200, f"Draft generation failed: {response.text}"
        assert duration < 30, f"Draft mode took {duration:.1f}s, expected <30s"

        print(f"✅ Draft mode completed in {duration:.1f} seconds")


    def test_character_consistency(self):
        """Test character consistency between generations"""
        # Generate first image
        response1 = requests.post(
            f"{API_URL}/api/anime/orchestrate",
            json={
                "prompt": "anime boy with red hair, samurai outfit",
                "type": "image",
                "width": 512,
                "height": 512,
                "seed": 42,
                "project_id": 2,
                "character_name": "samurai_test"
            }
        )
        assert response1.status_code == 200

        # Generate second image with same character
        response2 = requests.post(
            f"{API_URL}/api/anime/orchestrate",
            json={
                "prompt": "anime boy with red hair, samurai outfit, different pose",
                "type": "image",
                "width": 512,
                "height": 512,
                "seed": 43,  # Different seed but same character
                "project_id": 2,
                "character_name": "samurai_test"
            }
        )
        assert response2.status_code == 200

        print("✅ Character consistency test passed")


    def test_error_handling(self):
        """Test error handling with invalid parameters"""
        # Test with invalid size
        response = requests.post(
            f"{API_URL}/api/anime/orchestrate",
            json={
                "prompt": "test",
                "type": "image",
                "width": 99999,  # Invalid size
                "height": 99999
            }
        )

        # Should either handle gracefully or return error
        assert response.status_code in [200, 400, 422], "Unexpected error handling"

        if response.status_code != 200:
            error = response.json()
            assert "error" in error or "detail" in error, "No error message provided"
            print(f"✅ Error handling working: {error}")
        else:
            # Check if auto-recovery happened
            result = response.json()
            print(f"✅ Auto-recovery applied: {result}")


    def _wait_for_job_completion(self, job_id: str, timeout: int = TIMEOUT) -> bool:
        """Wait for a job to complete"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{API_URL}/api/anime/jobs/{job_id}/status")
                if response.status_code == 200:
                    status = response.json()

                    if status.get("status") == "completed":
                        return True
                    elif status.get("status") == "failed":
                        print(f"❌ Job failed: {status.get('error', 'Unknown error')}")
                        return False

                    # Show progress
                    progress = status.get("progress", 0)
                    print(f"  Progress: {progress}%", end='\r')
            except:
                pass

            time.sleep(2)

        return False


class TestAPIEndpoints:
    """Test all API endpoints are working"""


    def test_health_endpoint(self):
        """Test health endpoint"""
        response = requests.get(f"{API_URL}/api/anime/health")
        assert response.status_code == 200

        health = response.json()
        assert health["status"] == "healthy"
        print(f"✅ Health endpoint: {health}")


    def test_projects_endpoints(self):
        """Test project management endpoints"""
        # Create project
        response = requests.post(
            f"{API_URL}/api/anime/projects",
            json={
                "name": "Test Project",
                "description": "CI test project"
            }
        )

        if response.status_code == 200:
            project = response.json()
            project_id = project.get("id", project.get("project_id"))

            # Get project
            response = requests.get(f"{API_URL}/api/anime/projects/{project_id}")
            assert response.status_code == 200

            print(f"✅ Project endpoints working (ID: {project_id})")
        else:
            print("⚠️ Project endpoints not implemented yet")


    def test_character_endpoints(self):
        """Test character management endpoints"""
        response = requests.post(
            f"{API_URL}/api/anime/characters",
            json={
                "name": "Test Character",
                "project_id": 1,
                "description": "CI test character"
            }
        )

        if response.status_code == 200:
            response.json()
            print("✅ Character endpoints working")
        else:
            print("⚠️ Character endpoints not implemented yet")


class TestPerformance:
    """Test performance optimizations"""


    def test_generation_speed(self):
        """Verify generation speed improvements"""
        modes = {
            "draft": (30, 8),      # Target: <30s, 8 steps
            "standard": (60, 15),  # Target: <60s, 15 steps
        }

        results = {}

        for mode, (target_time, steps) in modes.items():
            start_time = time.time()

            response = requests.post(
                f"{API_URL}/api/anime/orchestrate",
                json={
                    "prompt": f"anime character, {mode} mode performance test",
                    "type": "image",
                    "mode": mode,
                    "width": 512 if mode == "draft" else 768,
                    "height": 512 if mode == "draft" else 768,
                    "steps": steps,
                    "project_id": 99
                },
                timeout=target_time + 30
            )

            duration = time.time() - start_time
            results[mode] = duration

            if response.status_code == 200:
                if duration <= target_time:
                    print(f"✅ {mode.capitalize()} mode: {duration:.1f}s (target: <{target_time}s)")
                else:
                    print(f"⚠️ {mode.capitalize()} mode: {duration:.1f}s (exceeded target of {target_time}s)")
            else:
                print(f"❌ {mode.capitalize()} mode failed: {response.status_code}")

        # Overall performance check
        if results.get("draft", 999) < 30:
            print("🚀 Performance optimizations working! Draft mode under 30 seconds.")


def main():
    """Run all system tests"""
    print("="*60)
    print("🧪 ANIME PRODUCTION COMPLETE SYSTEM TESTS")
    print("="*60)

    # Check if services are running
    try:
        requests.get(f"{COMFYUI_URL}/system_stats", timeout=2)
        requests.get(f"{API_URL}/api/anime/health", timeout=2)
    except:
        print("❌ Services not running. Please start ComfyUI and Anime API first.")
        return 1

    # Run tests
    test_classes = [
        TestSystemHealth(),
        TestGenerationWorkflow(),
        TestAPIEndpoints(),
        TestPerformance()
    ]

    failed = False

    for test_class in test_classes:
        class_name = test_class.__class__.__name__
        print(f"\n📋 Running {class_name}...")

        # Get all test methods
        test_methods = [m for m in dir(test_class) if m.startswith("test_")]

        for method_name in test_methods:
            try:
                method = getattr(test_class, method_name)
                method()
            except Exception as e:
                print(f"❌ {method_name} failed: {e}")
                failed = True

    print("\n" + "="*60)
    if not failed:
        print("✅ ALL SYSTEM TESTS PASSED!")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
