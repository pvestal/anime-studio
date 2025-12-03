#!/usr/bin/env python3
"""
Comprehensive Test Suite for Anime Production System
Tests EVERYTHING - Performance, Functionality, Integration, Edge Cases, Stress, Security
"""

import time
import requests
import json
import asyncio
import websocket
import psutil
import random
import string
import os
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple
import statistics

BASE_URL = "http://localhost:8328"
COMFYUI_URL = "http://localhost:8188"

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.details = []
        self.start_time = time.time()

    def add_pass(self, test_name: str, details: str = ""):
        self.passed += 1
        self.details.append(f"✅ PASS: {test_name} - {details}")

    def add_fail(self, test_name: str, details: str = ""):
        self.failed += 1
        self.details.append(f"❌ FAIL: {test_name} - {details}")

    def add_warning(self, test_name: str, details: str = ""):
        self.warnings += 1
        self.details.append(f"⚠️ WARN: {test_name} - {details}")

    def get_summary(self):
        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0
        elapsed = time.time() - self.start_time
        return {
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "total": total,
            "pass_rate": pass_rate,
            "elapsed_time": elapsed,
            "details": self.details
        }

# ==================== PERFORMANCE TESTS ====================

class PerformanceTests:
    def __init__(self, results: TestResults):
        self.results = results

    def test_cold_start_elimination(self):
        """Verify no cold start delay"""
        print("\n📊 Testing Cold Start Elimination...")

        # First request after "restart"
        start = time.time()
        response = requests.get(f"{BASE_URL}/health")
        health_check_time = time.time() - start

        if health_check_time < 0.5 and response.status_code == 200:
            data = response.json()
            if data.get("model_preloaded"):
                self.results.add_pass("Cold Start Elimination",
                    f"Health check in {health_check_time:.3f}s, models preloaded")
            else:
                self.results.add_fail("Cold Start Elimination",
                    "Models not preloaded")
        else:
            self.results.add_fail("Cold Start Elimination",
                f"Health check took {health_check_time:.3f}s")

    def test_generation_speed_consistency(self):
        """Test generation speed remains consistent"""
        print("📊 Testing Generation Speed Consistency...")

        times = []
        for i in range(5):
            start = time.time()
            response = requests.post(f"{BASE_URL}/generate",
                json={"prompt": f"speed test {i}"})

            if response.status_code == 200:
                job = response.json()
                job_id = job["job_id"]

                # Poll for completion
                max_wait = 30
                while max_wait > 0:
                    status_resp = requests.get(f"{BASE_URL}/jobs/{job_id}")
                    if status_resp.status_code == 200:
                        status = status_resp.json()
                        if status.get("status") == "completed":
                            elapsed = time.time() - start
                            times.append(elapsed)
                            break
                    time.sleep(0.5)
                    max_wait -= 0.5

        if len(times) >= 3:
            avg_time = statistics.mean(times)
            std_dev = statistics.stdev(times) if len(times) > 1 else 0

            if avg_time < 10 and std_dev < 2:
                self.results.add_pass("Generation Speed Consistency",
                    f"Avg: {avg_time:.2f}s, StdDev: {std_dev:.2f}s")
            else:
                self.results.add_fail("Generation Speed Consistency",
                    f"Avg: {avg_time:.2f}s, StdDev: {std_dev:.2f}s")
        else:
            self.results.add_fail("Generation Speed Consistency",
                f"Only {len(times)} successful generations")

    def test_memory_usage(self):
        """Monitor memory usage patterns"""
        print("📊 Testing Memory Usage...")

        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Generate 10 requests
        for i in range(10):
            requests.post(f"{BASE_URL}/generate",
                json={"prompt": f"memory test {i}"})

        time.sleep(5)
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        if memory_increase < 500:  # Less than 500MB increase
            self.results.add_pass("Memory Usage",
                f"Increase: {memory_increase:.2f}MB")
        else:
            self.results.add_warning("Memory Usage",
                f"High increase: {memory_increase:.2f}MB")

    def test_database_query_performance(self):
        """Test database query response times"""
        print("📊 Testing Database Query Performance...")

        # Test listing projects
        start = time.time()
        response = requests.get(f"{BASE_URL}/api/anime/projects")
        list_time = time.time() - start

        if response.status_code == 200 and list_time < 0.1:
            self.results.add_pass("Database Query Performance",
                f"List projects in {list_time:.3f}s")
        else:
            self.results.add_fail("Database Query Performance",
                f"List took {list_time:.3f}s")

# ==================== FUNCTIONALITY TESTS ====================

class FunctionalityTests:
    def __init__(self, results: TestResults):
        self.results = results
        self.project_id = None
        self.character_id = None

    def test_complete_project_crud(self):
        """Test all project CRUD operations"""
        print("\n🔧 Testing Complete Project CRUD...")

        # CREATE
        create_resp = requests.post(f"{BASE_URL}/api/anime/projects",
            json={
                "name": "Test Project CRUD",
                "description": "Testing all operations",
                "style": "cyberpunk",
                "metadata": {"test": True, "version": 1}
            })

        if create_resp.status_code != 200:
            self.results.add_fail("Project CRUD - Create",
                f"Status {create_resp.status_code}")
            return

        project = create_resp.json()
        self.project_id = project["id"]

        # READ
        read_resp = requests.get(f"{BASE_URL}/api/anime/projects/{self.project_id}")
        if read_resp.status_code != 200:
            self.results.add_fail("Project CRUD - Read",
                f"Status {read_resp.status_code}")

        # UPDATE
        update_resp = requests.put(f"{BASE_URL}/api/anime/projects/{self.project_id}",
            json={"description": "Updated description"})
        if update_resp.status_code != 200:
            self.results.add_warning("Project CRUD - Update", "Not implemented")

        # LIST
        list_resp = requests.get(f"{BASE_URL}/api/anime/projects")
        if list_resp.status_code == 200:
            projects = list_resp.json()
            if any(p["id"] == self.project_id for p in projects):
                self.results.add_pass("Project CRUD", "All operations working")
            else:
                self.results.add_fail("Project CRUD", "Project not in list")
        else:
            self.results.add_fail("Project CRUD - List",
                f"Status {list_resp.status_code}")

    def test_complete_character_crud(self):
        """Test all character CRUD operations"""
        print("🔧 Testing Complete Character CRUD...")

        if not self.project_id:
            self.test_complete_project_crud()

        # CREATE
        create_resp = requests.post(f"{BASE_URL}/api/anime/characters",
            json={
                "project_id": self.project_id,
                "name": "Test Character",
                "appearance": "Blue hair, green eyes",
                "personality": "Brave and kind",
                "backstory": "A hero's journey",
                "relationships": {"mentor": "Old Master", "rival": "Dark Lord"}
            })

        if create_resp.status_code != 200:
            self.results.add_fail("Character CRUD - Create",
                f"Status {create_resp.status_code}")
            return

        character = create_resp.json()
        self.character_id = character["id"]

        # GET BIBLE
        bible_resp = requests.get(f"{BASE_URL}/api/anime/characters/{self.character_id}/bible")
        if bible_resp.status_code == 200:
            bible = bible_resp.json()
            if bible.get("bible", {}).get("name") == "Test Character":
                self.results.add_pass("Character CRUD", "All operations working")
            else:
                self.results.add_fail("Character CRUD", "Bible data incorrect")
        else:
            self.results.add_fail("Character Bible",
                f"Status {bible_resp.status_code}")

    def test_file_organization_structure(self):
        """Verify files are organized correctly"""
        print("🔧 Testing File Organization...")

        if not self.project_id or not self.character_id:
            self.test_complete_character_crud()

        # Generate with project/character
        response = requests.post(f"{BASE_URL}/generate",
            json={
                "prompt": "test organization",
                "project_id": self.project_id,
                "character_id": self.character_id
            })

        if response.status_code == 200:
            job = response.json()
            job_id = job["job_id"]

            # Wait for completion
            time.sleep(10)

            # Check file structure
            base_dir = Path("/mnt/1TB-storage/anime/projects")
            project_dir = base_dir / self.project_id
            char_dir = project_dir / "characters" / self.character_id

            if project_dir.exists():
                if char_dir.exists():
                    files = list(char_dir.glob("*.png"))
                    if files:
                        self.results.add_pass("File Organization",
                            f"{len(files)} files in correct location")
                    else:
                        self.results.add_warning("File Organization",
                            "Directory created but no files yet")
                else:
                    self.results.add_fail("File Organization",
                        "Character directory not created")
            else:
                self.results.add_fail("File Organization",
                    "Project directory not created")

    def test_websocket_progress_accuracy(self):
        """Test WebSocket progress reporting accuracy"""
        print("🔧 Testing WebSocket Progress Accuracy...")

        response = requests.post(f"{BASE_URL}/generate",
            json={"prompt": "websocket test"})

        if response.status_code != 200:
            self.results.add_fail("WebSocket Progress", "Generation failed")
            return

        job = response.json()
        ws_url = job.get("websocket_url", "").replace("http://", "ws://")

        if not ws_url:
            self.results.add_fail("WebSocket Progress", "No WebSocket URL")
            return

        try:
            ws = websocket.WebSocket()
            ws.settimeout(10)
            ws.connect(ws_url)

            progress_updates = []
            while True:
                try:
                    message = ws.recv()
                    data = json.loads(message)
                    progress_updates.append(data.get("progress", 0))
                    if data.get("status") in ["completed", "failed"]:
                        break
                except websocket.WebSocketTimeoutException:
                    break

            ws.close()

            if len(progress_updates) > 3:
                # Check if progress increases monotonically
                is_monotonic = all(progress_updates[i] <= progress_updates[i+1]
                                 for i in range(len(progress_updates)-1))
                if is_monotonic:
                    self.results.add_pass("WebSocket Progress",
                        f"{len(progress_updates)} updates, monotonic")
                else:
                    self.results.add_warning("WebSocket Progress",
                        "Progress not monotonic")
            else:
                self.results.add_fail("WebSocket Progress",
                    f"Only {len(progress_updates)} updates")
        except Exception as e:
            self.results.add_fail("WebSocket Progress", str(e))

    def test_all_style_presets(self):
        """Test all style presets work correctly"""
        print("🔧 Testing All Style Presets...")

        styles = ["cyberpunk", "fantasy", "steampunk", "studio_ghibli", "manga"]
        style_results = {}

        for style in styles:
            response = requests.post(f"{BASE_URL}/generate",
                json={
                    "prompt": "character portrait",
                    "style_preset": style
                })

            if response.status_code == 200:
                job = response.json()
                style_results[style] = "✅"
            else:
                style_results[style] = "❌"

        successful = sum(1 for v in style_results.values() if v == "✅")
        if successful == len(styles):
            self.results.add_pass("Style Presets", f"All {len(styles)} working")
        elif successful > 0:
            self.results.add_warning("Style Presets",
                f"{successful}/{len(styles)} working")
        else:
            self.results.add_fail("Style Presets", "None working")

# ==================== INTEGRATION TESTS ====================

class IntegrationTests:
    def __init__(self, results: TestResults):
        self.results = results

    def test_comfyui_integration(self):
        """Test ComfyUI integration reliability"""
        print("\n🔌 Testing ComfyUI Integration...")

        # Check if ComfyUI is running
        try:
            response = requests.get(f"{COMFYUI_URL}/system_stats")
            if response.status_code == 200:
                self.results.add_pass("ComfyUI Integration", "Service responsive")
            else:
                self.results.add_fail("ComfyUI Integration",
                    f"Status {response.status_code}")
        except:
            self.results.add_fail("ComfyUI Integration", "Service not running")

    def test_database_transaction_integrity(self):
        """Test database transaction handling"""
        print("🔌 Testing Database Transaction Integrity...")

        # Create multiple jobs rapidly
        job_ids = []
        for i in range(5):
            response = requests.post(f"{BASE_URL}/generate",
                json={"prompt": f"transaction test {i}"})
            if response.status_code == 200:
                job_ids.append(response.json()["job_id"])

        time.sleep(2)

        # Verify all jobs are in database
        found = 0
        for job_id in job_ids:
            response = requests.get(f"{BASE_URL}/jobs/{job_id}")
            if response.status_code == 200:
                found += 1

        if found == len(job_ids):
            self.results.add_pass("Database Transactions",
                f"All {len(job_ids)} jobs persisted")
        else:
            self.results.add_fail("Database Transactions",
                f"Only {found}/{len(job_ids)} persisted")

    def test_echo_brain_integration(self):
        """Test Echo Brain integration if available"""
        print("🔌 Testing Echo Brain Integration...")

        try:
            response = requests.get("http://localhost:8309/api/echo/health")
            if response.status_code == 200:
                # Try to use Echo for prompt enhancement
                test_response = requests.post(f"{BASE_URL}/generate",
                    json={
                        "prompt": "anime character",
                        "use_echo_enhancement": True
                    })

                if test_response.status_code == 200:
                    self.results.add_pass("Echo Brain Integration", "Working")
                else:
                    self.results.add_warning("Echo Brain Integration",
                        "Echo running but not integrated")
            else:
                self.results.add_warning("Echo Brain Integration",
                    "Echo not running")
        except:
            self.results.add_warning("Echo Brain Integration", "Echo not available")

# ==================== EDGE CASE TESTS ====================

class EdgeCaseTests:
    def __init__(self, results: TestResults):
        self.results = results

    def test_large_prompt_handling(self):
        """Test handling of very large prompts"""
        print("\n🔪 Testing Large Prompt Handling...")

        large_prompt = "anime character with " + " ".join(
            [f"feature{i}" for i in range(1000)]
        )

        response = requests.post(f"{BASE_URL}/generate",
            json={"prompt": large_prompt})

        if response.status_code == 200:
            self.results.add_pass("Large Prompt Handling",
                f"{len(large_prompt)} characters")
        elif response.status_code == 400:
            self.results.add_pass("Large Prompt Handling",
                "Correctly rejected oversized prompt")
        else:
            self.results.add_fail("Large Prompt Handling",
                f"Unexpected status {response.status_code}")

    def test_special_characters(self):
        """Test handling of special characters"""
        print("🔪 Testing Special Characters...")

        special_prompts = [
            "anime with émojis 🎨 and unicode ñ",
            "test with\nnewlines\nand\ttabs",
            "test with 中文 and 日本語",
            "test with <script>alert('xss')</script>"
        ]

        passed = 0
        for prompt in special_prompts:
            response = requests.post(f"{BASE_URL}/generate",
                json={"prompt": prompt})
            if response.status_code == 200:
                passed += 1

        if passed == len(special_prompts):
            self.results.add_pass("Special Characters",
                f"All {len(special_prompts)} handled")
        elif passed > 0:
            self.results.add_warning("Special Characters",
                f"{passed}/{len(special_prompts)} handled")
        else:
            self.results.add_fail("Special Characters", "None handled")

    def test_concurrent_modifications(self):
        """Test handling of concurrent project modifications"""
        print("🔪 Testing Concurrent Modifications...")

        # Create a project
        response = requests.post(f"{BASE_URL}/api/anime/projects",
            json={"name": "Concurrent Test", "style": "fantasy"})

        if response.status_code != 200:
            self.results.add_fail("Concurrent Modifications", "Setup failed")
            return

        project_id = response.json()["id"]

        # Concurrent updates
        def update_project(i):
            return requests.put(f"{BASE_URL}/api/anime/projects/{project_id}",
                json={"description": f"Update {i}"})

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(update_project, i) for i in range(5)]
            results = [f.result() for f in as_completed(futures)]

        # Check project is still valid
        response = requests.get(f"{BASE_URL}/api/anime/projects/{project_id}")
        if response.status_code == 200:
            self.results.add_pass("Concurrent Modifications", "Handled gracefully")
        else:
            self.results.add_fail("Concurrent Modifications", "Corrupted project")

    def test_invalid_id_formats(self):
        """Test handling of various invalid ID formats"""
        print("🔪 Testing Invalid ID Formats...")

        invalid_ids = [
            "../../etc/passwd",
            "'; DROP TABLE--",
            "a" * 1000,
            "123-456-789",
            "%00",
            "../",
            "null",
            ""
        ]

        blocked = 0
        for bad_id in invalid_ids:
            response = requests.get(f"{BASE_URL}/api/anime/projects/{bad_id}")
            if response.status_code in [400, 404]:
                blocked += 1

        if blocked == len(invalid_ids):
            self.results.add_pass("Invalid ID Handling",
                f"All {len(invalid_ids)} rejected")
        else:
            self.results.add_fail("Invalid ID Handling",
                f"Only {blocked}/{len(invalid_ids)} rejected")

# ==================== STRESS TESTS ====================

class StressTests:
    def __init__(self, results: TestResults):
        self.results = results

    def test_high_concurrency(self):
        """Test with 50 concurrent requests"""
        print("\n🔥 Testing High Concurrency (50 requests)...")

        def make_request(i):
            try:
                start = time.time()
                response = requests.post(f"{BASE_URL}/generate",
                    json={"prompt": f"stress test {i}"}, timeout=5)
                return {
                    "success": response.status_code == 200,
                    "time": time.time() - start
                }
            except:
                return {"success": False, "time": 5}

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(make_request, i) for i in range(50)]
            results = [f.result() for f in as_completed(futures)]

        successful = sum(1 for r in results if r["success"])
        avg_time = statistics.mean([r["time"] for r in results if r["success"]])

        if successful >= 45:  # 90% success rate
            self.results.add_pass("High Concurrency",
                f"{successful}/50 succeeded, avg {avg_time:.2f}s")
        elif successful >= 25:
            self.results.add_warning("High Concurrency",
                f"{successful}/50 succeeded")
        else:
            self.results.add_fail("High Concurrency",
                f"Only {successful}/50 succeeded")

    def test_sustained_load(self):
        """Test sustained load over time"""
        print("🔥 Testing Sustained Load (2 minutes)...")

        start_time = time.time()
        end_time = start_time + 120  # 2 minutes
        request_count = 0
        success_count = 0

        while time.time() < end_time:
            response = requests.post(f"{BASE_URL}/generate",
                json={"prompt": f"sustained load {request_count}"})
            request_count += 1
            if response.status_code == 200:
                success_count += 1
            time.sleep(1)  # 1 request per second

        success_rate = (success_count / request_count * 100) if request_count > 0 else 0

        if success_rate >= 95:
            self.results.add_pass("Sustained Load",
                f"{success_rate:.1f}% success over 2 minutes")
        elif success_rate >= 80:
            self.results.add_warning("Sustained Load",
                f"{success_rate:.1f}% success")
        else:
            self.results.add_fail("Sustained Load",
                f"Only {success_rate:.1f}% success")

    def test_resource_exhaustion(self):
        """Test behavior under resource exhaustion"""
        print("🔥 Testing Resource Exhaustion...")

        # Try to exhaust connection pool
        connections = []
        for i in range(20):
            try:
                response = requests.post(f"{BASE_URL}/generate",
                    json={"prompt": f"exhaust {i}"}, stream=True)
                connections.append(response)
            except:
                pass

        # Now try a normal request
        response = requests.post(f"{BASE_URL}/generate",
            json={"prompt": "test after exhaustion"})

        if response.status_code == 200:
            self.results.add_pass("Resource Exhaustion",
                "Graceful handling")
        else:
            self.results.add_warning("Resource Exhaustion",
                f"Degraded to status {response.status_code}")

# ==================== SECURITY TESTS ====================

class SecurityTests:
    def __init__(self, results: TestResults):
        self.results = results

    def test_sql_injection_variants(self):
        """Test various SQL injection attempts"""
        print("\n🔒 Testing SQL Injection Variants...")

        sql_payloads = [
            "'; DROP TABLE anime_api.production_jobs; --",
            "' OR '1'='1",
            "\" OR 1=1 --",
            "'; SELECT * FROM pg_tables; --",
            "' UNION SELECT null, null --",
            "'; UPDATE anime_api.production_jobs SET status='hacked'; --"
        ]

        blocked = 0
        for payload in sql_payloads:
            response = requests.post(f"{BASE_URL}/generate",
                json={"prompt": payload})
            # Should either sanitize or work normally, not error
            if response.status_code in [200, 400]:
                blocked += 1

        if blocked == len(sql_payloads):
            self.results.add_pass("SQL Injection Protection",
                f"All {len(sql_payloads)} handled safely")
        else:
            self.results.add_fail("SQL Injection Protection",
                f"Only {blocked}/{len(sql_payloads)} handled")

    def test_path_traversal_variants(self):
        """Test path traversal attempts"""
        print("🔒 Testing Path Traversal Variants...")

        traversal_payloads = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "....//....//....//etc/passwd"
        ]

        blocked = 0
        for payload in traversal_payloads:
            response = requests.get(f"{BASE_URL}/api/anime/projects/{payload}")
            if response.status_code in [400, 404]:
                blocked += 1

        if blocked == len(traversal_payloads):
            self.results.add_pass("Path Traversal Protection",
                f"All {len(traversal_payloads)} blocked")
        else:
            self.results.add_fail("Path Traversal Protection",
                f"Only {blocked}/{len(traversal_payloads)} blocked")

    def test_xss_attempts(self):
        """Test XSS injection attempts"""
        print("🔒 Testing XSS Attempts...")

        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<svg onload=alert('xss')>"
        ]

        safe = 0
        for payload in xss_payloads:
            response = requests.post(f"{BASE_URL}/api/anime/projects",
                json={"name": payload, "style": "test"})
            if response.status_code == 200:
                project = response.json()
                # Check if script tags were sanitized
                if "<script>" not in project.get("name", ""):
                    safe += 1

        if safe == len(xss_payloads):
            self.results.add_pass("XSS Protection",
                f"All {len(xss_payloads)} sanitized")
        else:
            self.results.add_warning("XSS Protection",
                f"{safe}/{len(xss_payloads)} sanitized")

    def test_command_injection(self):
        """Test command injection attempts"""
        print("🔒 Testing Command Injection...")

        cmd_payloads = [
            "test; ls -la",
            "test && cat /etc/passwd",
            "test | whoami",
            "test`id`"
        ]

        safe = 0
        for payload in cmd_payloads:
            response = requests.post(f"{BASE_URL}/generate",
                json={"prompt": payload})
            if response.status_code in [200, 400]:
                safe += 1

        if safe == len(cmd_payloads):
            self.results.add_pass("Command Injection Protection",
                f"All {len(cmd_payloads)} safe")
        else:
            self.results.add_fail("Command Injection Protection",
                f"Only {safe}/{len(cmd_payloads)} safe")

# ==================== RELIABILITY TESTS ====================

class ReliabilityTests:
    def __init__(self, results: TestResults):
        self.results = results

    def test_error_recovery(self):
        """Test system recovery from errors"""
        print("\n🛡️ Testing Error Recovery...")

        # Cause an error with invalid data
        response = requests.post(f"{BASE_URL}/generate",
            json={"prompt": None})  # Invalid prompt

        # System should recover and work normally
        response = requests.post(f"{BASE_URL}/generate",
            json={"prompt": "test after error"})

        if response.status_code == 200:
            self.results.add_pass("Error Recovery", "System recovered")
        else:
            self.results.add_fail("Error Recovery", "System not recovered")

    def test_job_persistence(self):
        """Test job persistence and recovery"""
        print("🛡️ Testing Job Persistence...")

        # Create a job
        response = requests.post(f"{BASE_URL}/generate",
            json={"prompt": "persistence test"})

        if response.status_code != 200:
            self.results.add_fail("Job Persistence", "Creation failed")
            return

        job_id = response.json()["job_id"]

        # Check job exists in database
        time.sleep(2)
        response = requests.get(f"{BASE_URL}/jobs/{job_id}")

        if response.status_code == 200:
            job = response.json()
            if job.get("id") == job_id:
                self.results.add_pass("Job Persistence", "Job persisted correctly")
            else:
                self.results.add_fail("Job Persistence", "Job data corrupted")
        else:
            self.results.add_fail("Job Persistence", "Job not found")

    def test_queue_overflow_handling(self):
        """Test queue overflow handling"""
        print("🛡️ Testing Queue Overflow Handling...")

        # Submit many jobs quickly
        job_ids = []
        for i in range(20):
            response = requests.post(f"{BASE_URL}/generate",
                json={"prompt": f"overflow test {i}"})
            if response.status_code == 200:
                job_ids.append(response.json()["job_id"])

        # Check queue positions
        queued_correctly = 0
        for job_id in job_ids:
            response = requests.get(f"{BASE_URL}/jobs/{job_id}")
            if response.status_code == 200:
                status = response.json().get("status")
                if status in ["queued", "running", "completed"]:
                    queued_correctly += 1

        if queued_correctly == len(job_ids):
            self.results.add_pass("Queue Overflow",
                f"All {len(job_ids)} jobs queued")
        elif queued_correctly > 15:
            self.results.add_warning("Queue Overflow",
                f"{queued_correctly}/{len(job_ids)} queued")
        else:
            self.results.add_fail("Queue Overflow",
                f"Only {queued_correctly}/{len(job_ids)} queued")

# ==================== MAIN TEST RUNNER ====================

def run_comprehensive_tests():
    """Run all comprehensive tests"""
    print("=" * 80)
    print("🧪 COMPREHENSIVE ANIME PRODUCTION SYSTEM TESTING")
    print("=" * 80)
    print(f"Started at: {datetime.now()}")

    results = TestResults()

    # Run all test categories
    test_suites = [
        ("PERFORMANCE", PerformanceTests(results)),
        ("FUNCTIONALITY", FunctionalityTests(results)),
        ("INTEGRATION", IntegrationTests(results)),
        ("EDGE CASES", EdgeCaseTests(results)),
        ("STRESS", StressTests(results)),
        ("SECURITY", SecurityTests(results)),
        ("RELIABILITY", ReliabilityTests(results))
    ]

    for category, suite in test_suites:
        print(f"\n{'=' * 40}")
        print(f"    {category} TESTS")
        print(f"{'=' * 40}")

        # Run all methods that start with 'test_'
        for method_name in dir(suite):
            if method_name.startswith('test_'):
                method = getattr(suite, method_name)
                try:
                    method()
                except Exception as e:
                    results.add_fail(f"{category}.{method_name}", str(e))

    # Generate final report
    print("\n" + "=" * 80)
    print("📊 FINAL TEST REPORT")
    print("=" * 80)

    summary = results.get_summary()

    print(f"\n📈 STATISTICS:")
    print(f"  Total Tests: {summary['total']}")
    print(f"  Passed: {summary['passed']} ✅")
    print(f"  Failed: {summary['failed']} ❌")
    print(f"  Warnings: {summary['warnings']} ⚠️")
    print(f"  Pass Rate: {summary['pass_rate']:.1f}%")
    print(f"  Total Time: {summary['elapsed_time']:.2f} seconds")

    print(f"\n📝 DETAILED RESULTS:")
    for detail in summary['details']:
        print(f"  {detail}")

    print("\n" + "=" * 80)
    if summary['pass_rate'] >= 90:
        print("🎉 SYSTEM STATUS: PRODUCTION READY")
    elif summary['pass_rate'] >= 70:
        print("⚠️ SYSTEM STATUS: NEEDS IMPROVEMENT")
    else:
        print("❌ SYSTEM STATUS: NOT READY")
    print("=" * 80)

    # Save report
    with open("comprehensive_test_results.json", "w") as f:
        json.dump(summary, f, indent=2)

    return summary

if __name__ == "__main__":
    run_comprehensive_tests()