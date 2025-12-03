#!/usr/bin/env python3
"""
Comprehensive test suite for anime production system
Tests security, performance, concurrency, and reliability
"""

import asyncio
import time
import requests
import json
import threading
import psutil
import subprocess
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

API_BASE = "http://localhost:8328"

class AnimeSystemTester:
    def __init__(self):
        self.results = {
            "security": [],
            "performance": [],
            "concurrency": [],
            "reliability": [],
            "database": []
        }

    def test_sql_injection(self):
        """Test for SQL injection vulnerabilities"""
        print("\n🔒 TESTING SQL INJECTION VULNERABILITIES...")

        sql_payloads = [
            "'; DROP TABLE anime_api.production_jobs; --",
            "' OR '1'='1",
            "' UNION SELECT * FROM pg_user WHERE '1'='1",
            "'; INSERT INTO anime_api.production_jobs (prompt) VALUES ('hacked'); --",
            "1; DELETE FROM anime_api.production_jobs WHERE id > 0; --"
        ]

        vulnerable = []
        for payload in sql_payloads:
            try:
                # Try injection in job lookup
                response = requests.get(f"{API_BASE}/jobs/{payload}")
                if response.status_code != 404:
                    vulnerable.append(f"Job lookup vulnerable to: {payload}")

                # Try injection in generation
                response = requests.post(f"{API_BASE}/generate",
                    json={"prompt": payload})
                if "error" not in response.text.lower():
                    vulnerable.append(f"Generation vulnerable to: {payload}")

            except Exception as e:
                pass

        self.results["security"].append({
            "test": "SQL Injection",
            "vulnerable": len(vulnerable) > 0,
            "details": vulnerable
        })
        return vulnerable

    def test_authentication(self):
        """Test if API requires authentication"""
        print("\n🔐 TESTING AUTHENTICATION...")

        endpoints = [
            ("/health", "GET"),
            ("/jobs", "GET"),
            ("/generate", "POST"),
            ("/jobs/test123", "GET")
        ]

        unprotected = []
        for endpoint, method in endpoints:
            try:
                if method == "GET":
                    response = requests.get(f"{API_BASE}{endpoint}")
                else:
                    response = requests.post(f"{API_BASE}{endpoint}",
                        json={"prompt": "test"})

                if response.status_code != 401 and response.status_code != 403:
                    unprotected.append(f"{method} {endpoint} - No auth required")
            except:
                pass

        self.results["security"].append({
            "test": "Authentication",
            "unprotected_endpoints": unprotected,
            "secure": len(unprotected) == 0
        })
        return unprotected

    def test_concurrent_generation(self):
        """Test concurrent generation handling"""
        print("\n🔄 TESTING CONCURRENT GENERATION...")

        def make_request(index):
            start = time.time()
            try:
                response = requests.post(f"{API_BASE}/generate",
                    json={"prompt": f"concurrent test {index}"})
                result = response.json()
                job_id = result.get("job_id")

                # Wait for completion
                max_wait = 120
                while max_wait > 0:
                    job_response = requests.get(f"{API_BASE}/jobs/{job_id}")
                    job = job_response.json()
                    if job.get("status") == "completed":
                        elapsed = time.time() - start
                        return {
                            "index": index,
                            "job_id": job_id,
                            "time": elapsed,
                            "success": True
                        }
                    time.sleep(1)
                    max_wait -= 1

                return {"index": index, "success": False, "error": "timeout"}

            except Exception as e:
                return {"index": index, "success": False, "error": str(e)}

        # Test with 5 concurrent requests
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(5)]
            results = []
            for future in as_completed(futures):
                results.append(future.result())

        results.sort(key=lambda x: x.get("index", 0))

        # Check if truly concurrent or sequential
        times = [r.get("time", 0) for r in results if r.get("success")]
        is_sequential = all(times[i] < times[i+1] for i in range(len(times)-1))

        self.results["concurrency"].append({
            "test": "Concurrent Generation",
            "requests": 5,
            "results": results,
            "is_sequential": is_sequential,
            "average_time": sum(times) / len(times) if times else 0
        })
        return results

    def test_performance_single(self):
        """Test single generation performance"""
        print("\n⚡ TESTING SINGLE GENERATION PERFORMANCE...")

        times = []
        for i in range(3):
            start = time.time()
            try:
                response = requests.post(f"{API_BASE}/generate",
                    json={"prompt": f"performance test {i}"})
                result = response.json()
                job_id = result.get("job_id")

                # Wait for completion
                max_wait = 120
                while max_wait > 0:
                    job_response = requests.get(f"{API_BASE}/jobs/{job_id}")
                    job = job_response.json()
                    if job.get("status") == "completed":
                        elapsed = time.time() - start
                        times.append(elapsed)
                        break
                    time.sleep(0.5)
                    max_wait -= 0.5

            except Exception as e:
                print(f"Error in performance test: {e}")

        avg_time = sum(times) / len(times) if times else 0

        self.results["performance"].append({
            "test": "Single Generation",
            "runs": len(times),
            "times": times,
            "average": avg_time,
            "meets_4s_claim": avg_time <= 5.0
        })
        return avg_time

    def test_database_integrity(self):
        """Test database integrity and persistence"""
        print("\n🗄️ TESTING DATABASE INTEGRITY...")

        # Create a test job
        response = requests.post(f"{API_BASE}/generate",
            json={"prompt": "database integrity test"})
        job_id = response.json().get("job_id")

        # Wait for completion
        time.sleep(10)

        # Check if in database
        import psycopg2
        try:
            conn = psycopg2.connect(
                host="localhost",
                database="anime_production",
                user="patrick",
                password="***REMOVED***"
            )
            cur = conn.cursor()
            cur.execute(
                "SELECT job_id, status, prompt FROM anime_api.production_jobs WHERE job_id = %s",
                (job_id,)
            )
            result = cur.fetchone()
            cur.close()
            conn.close()

            self.results["database"].append({
                "test": "Database Persistence",
                "job_id": job_id,
                "found_in_db": result is not None,
                "data": result
            })
            return result is not None

        except Exception as e:
            self.results["database"].append({
                "test": "Database Persistence",
                "error": str(e)
            })
            return False

    def test_memory_usage(self):
        """Test memory and resource usage"""
        print("\n💾 TESTING MEMORY & RESOURCE USAGE...")

        # Get current memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Generate 10 images
        for i in range(10):
            try:
                requests.post(f"{API_BASE}/generate",
                    json={"prompt": f"memory test {i}"})
            except:
                pass

        # Check memory after
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        self.results["performance"].append({
            "test": "Memory Usage",
            "initial_mb": initial_memory,
            "final_mb": final_memory,
            "increase_mb": memory_increase,
            "potential_leak": memory_increase > 100
        })
        return memory_increase

    def test_rate_limiting(self):
        """Test if rate limiting exists"""
        print("\n🚦 TESTING RATE LIMITING...")

        # Send 50 rapid requests
        start = time.time()
        blocked = 0
        success = 0

        for i in range(50):
            try:
                response = requests.get(f"{API_BASE}/health", timeout=0.5)
                if response.status_code == 429:  # Too Many Requests
                    blocked += 1
                else:
                    success += 1
            except:
                pass

        elapsed = time.time() - start

        self.results["security"].append({
            "test": "Rate Limiting",
            "requests": 50,
            "blocked": blocked,
            "success": success,
            "time": elapsed,
            "rate_limiting_active": blocked > 0
        })
        return blocked > 0

    def test_input_validation(self):
        """Test input validation"""
        print("\n✅ TESTING INPUT VALIDATION...")

        invalid_inputs = [
            {"prompt": ""},  # Empty
            {"prompt": "x" * 10000},  # Very long
            {"prompt": None},  # Null
            {"width": -1},  # Negative
            {"height": 999999},  # Too large
            {"prompt": "<script>alert('xss')</script>"},  # XSS attempt
            {},  # No prompt
        ]

        rejected = []
        accepted = []

        for input_data in invalid_inputs:
            try:
                response = requests.post(f"{API_BASE}/generate", json=input_data)
                if response.status_code >= 400:
                    rejected.append(str(input_data))
                else:
                    accepted.append(str(input_data))
            except:
                pass

        self.results["security"].append({
            "test": "Input Validation",
            "invalid_rejected": rejected,
            "invalid_accepted": accepted,
            "validation_working": len(accepted) == 0
        })
        return len(accepted) == 0

    def run_all_tests(self):
        """Run all tests and generate report"""
        print("=" * 60)
        print("🧪 COMPREHENSIVE ANIME SYSTEM TESTING")
        print("=" * 60)

        # Security tests
        self.test_authentication()
        self.test_sql_injection()
        self.test_rate_limiting()
        self.test_input_validation()

        # Performance tests
        self.test_performance_single()
        self.test_concurrent_generation()
        self.test_memory_usage()

        # Reliability tests
        self.test_database_integrity()

        # Generate report
        self.generate_report()

    def generate_report(self):
        """Generate comprehensive test report"""
        print("\n" + "=" * 60)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 60)

        # Security summary
        print("\n🔒 SECURITY:")
        for result in self.results["security"]:
            print(f"  - {result['test']}: ", end="")
            if result.get("secure"):
                print("✅ SECURE")
            elif result.get("vulnerable") or not result.get("rate_limiting_active") or not result.get("validation_working"):
                print("❌ VULNERABLE")
            else:
                print("⚠️ PARTIAL")

        # Performance summary
        print("\n⚡ PERFORMANCE:")
        for result in self.results["performance"]:
            if "average" in result:
                print(f"  - {result['test']}: {result['average']:.2f}s average")
            elif "increase_mb" in result:
                print(f"  - {result['test']}: {result['increase_mb']:.2f}MB increase")

        # Concurrency summary
        print("\n🔄 CONCURRENCY:")
        for result in self.results["concurrency"]:
            print(f"  - Sequential processing: {result.get('is_sequential')}")
            print(f"  - Average time: {result.get('average_time', 0):.2f}s")

        # Database summary
        print("\n🗄️ DATABASE:")
        for result in self.results["database"]:
            print(f"  - {result['test']}: ", end="")
            if result.get("found_in_db"):
                print("✅ WORKING")
            else:
                print("❌ FAILED")

        # Save detailed report
        with open("/opt/tower-anime-production/test_results.json", "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        print(f"\n📝 Detailed results saved to test_results.json")

if __name__ == "__main__":
    tester = AnimeSystemTester()
    tester.run_all_tests()