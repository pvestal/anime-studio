#!/usr/bin/env python3
"""
PRODUCTION TEST SUITE
Comprehensive testing framework for Tower Anime Production system

This test suite must PASS before production deployment:
- All security vulnerabilities patched
- Performance meets production requirements
- Error handling robust under all conditions
- Memory management stable under load
- Database integrity maintained
"""

import requests
import time
import json
import asyncio
import threading
import statistics
import os
import psutil
import concurrent.futures
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta


class ProductionTestSuite:
    """Comprehensive test suite for production validation"""

    def __init__(self, api_base: str = "http://localhost:8328"):
        self.api_base = api_base
        self.test_results = {
            'security': {'passed': 0, 'failed': 0, 'tests': []},
            'performance': {'passed': 0, 'failed': 0, 'tests': []},
            'reliability': {'passed': 0, 'failed': 0, 'tests': []},
            'edge_cases': {'passed': 0, 'failed': 0, 'tests': []},
            'memory': {'passed': 0, 'failed': 0, 'tests': []},
        }

    def log_test_result(self, category: str, test_name: str, passed: bool,
                       details: str = "", execution_time: float = 0):
        """Log test result"""
        result = {
            'name': test_name,
            'passed': passed,
            'details': details,
            'execution_time': execution_time,
            'timestamp': datetime.now().isoformat()
        }

        self.test_results[category]['tests'].append(result)

        if passed:
            self.test_results[category]['passed'] += 1
            status = "✅ PASS"
        else:
            self.test_results[category]['failed'] += 1
            status = "❌ FAIL"

        print(f"{status} | {category.upper():<12} | {test_name:<40} | {execution_time:.3f}s")
        if details:
            print(f"      Details: {details}")

    def test_authentication_security(self) -> None:
        """Test authentication is properly implemented"""
        start_time = time.time()

        try:
            # Test that sensitive endpoints require authentication
            sensitive_endpoints = ["/jobs", "/generate", "/jobs/test123"]

            for endpoint in sensitive_endpoints:
                response = requests.get(f"{self.api_base}{endpoint}", timeout=5)

                # Should return 401 Unauthorized if auth is implemented
                if response.status_code == 401:
                    passed = True
                    details = f"Endpoint {endpoint} properly requires authentication"
                else:
                    passed = False
                    details = f"Endpoint {endpoint} accessible without auth (status: {response.status_code})"
                    break
            else:
                passed = True
                details = "All endpoints properly protected"

        except Exception as e:
            passed = False
            details = f"Exception during auth test: {e}"

        execution_time = time.time() - start_time
        self.log_test_result('security', 'Authentication Required', passed, details, execution_time)

    def test_sql_injection_protection(self) -> None:
        """Test SQL injection protection"""
        start_time = time.time()

        malicious_payloads = [
            "'; DROP TABLE anime_api.production_jobs; --",
            "' UNION SELECT password FROM users WHERE '1'='1",
            "'; DELETE FROM anime_api.production_jobs; --"
        ]

        try:
            for payload in malicious_payloads:
                response = requests.post(f"{self.api_base}/generate", json={
                    "prompt": payload,
                    "width": 512,
                    "height": 512
                }, timeout=10)

                # Should reject malicious input
                if response.status_code in [400, 422]:
                    passed = True
                    details = "SQL injection properly blocked"
                else:
                    passed = False
                    details = f"SQL injection accepted (status: {response.status_code})"
                    break
            else:
                passed = True
                details = "All SQL injection attempts properly blocked"

        except Exception as e:
            passed = False
            details = f"Exception during SQL injection test: {e}"

        execution_time = time.time() - start_time
        self.log_test_result('security', 'SQL Injection Protection', passed, details, execution_time)

    def test_rate_limiting(self) -> None:
        """Test rate limiting is implemented"""
        start_time = time.time()

        try:
            # Rapid fire 30 requests in 3 seconds
            responses = []
            for i in range(30):
                start_req = time.time()
                response = requests.get(f"{self.api_base}/health", timeout=2)
                responses.append({
                    'status': response.status_code,
                    'time': time.time() - start_req
                })

                if response.status_code == 429:  # Too Many Requests
                    passed = True
                    details = f"Rate limiting triggered after {i+1} requests"
                    break
            else:
                passed = False
                details = f"No rate limiting detected after 30 requests"

        except Exception as e:
            passed = False
            details = f"Exception during rate limiting test: {e}"

        execution_time = time.time() - start_time
        self.log_test_result('security', 'Rate Limiting Active', passed, details, execution_time)

    def test_performance_single_generation(self) -> None:
        """Test single generation performance"""
        start_time = time.time()

        try:
            response = requests.post(f"{self.api_base}/generate", json={
                "prompt": "performance test anime character",
                "width": 512,
                "height": 768
            }, timeout=15)

            if response.status_code != 200:
                passed = False
                details = f"Generation request failed: {response.status_code}"
            else:
                job_data = response.json()
                job_id = job_data.get('job_id')

                # Wait for completion
                completion_time = self.wait_for_job(job_id, max_wait=60)

                if completion_time and completion_time <= 10:  # 10s threshold
                    passed = True
                    details = f"Generation completed in {completion_time:.2f}s"
                else:
                    passed = False
                    details = f"Generation took {completion_time:.2f}s (>10s threshold)"

        except Exception as e:
            passed = False
            details = f"Exception during performance test: {e}"

        execution_time = time.time() - start_time
        self.log_test_result('performance', 'Single Generation Speed', passed, details, execution_time)

    def test_concurrent_generation_capacity(self) -> None:
        """Test concurrent generation handling"""
        start_time = time.time()

        def single_generation(worker_id: int):
            try:
                response = requests.post(f"{self.api_base}/generate", json={
                    "prompt": f"concurrent test {worker_id}",
                    "width": 512,
                    "height": 512
                }, timeout=10)

                if response.status_code == 200:
                    job_data = response.json()
                    completion_time = self.wait_for_job(job_data.get('job_id'), max_wait=120)
                    return {'success': True, 'time': completion_time}
                else:
                    return {'success': False, 'error': f"HTTP {response.status_code}"}
            except Exception as e:
                return {'success': False, 'error': str(e)}

        try:
            # Test 8 concurrent requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(single_generation, i) for i in range(8)]
                results = []

                for future in concurrent.futures.as_completed(futures, timeout=180):
                    results.append(future.result())

            successful = [r for r in results if r['success']]
            success_rate = len(successful) / len(results)

            if success_rate >= 0.8:  # 80% success rate minimum
                passed = True
                details = f"Concurrent handling: {len(successful)}/8 successful ({success_rate*100:.1f}%)"
            else:
                passed = False
                details = f"Poor concurrent performance: {len(successful)}/8 successful"

        except Exception as e:
            passed = False
            details = f"Exception during concurrent test: {e}"

        execution_time = time.time() - start_time
        self.log_test_result('performance', 'Concurrent Generation Handling', passed, details, execution_time)

    def test_memory_leak_detection(self) -> None:
        """Test for memory leaks during extended operation"""
        start_time = time.time()

        try:
            # Measure initial memory
            initial_memory = self.get_anime_memory_usage()

            # Perform 20 generations
            for i in range(20):
                response = requests.post(f"{self.api_base}/generate", json={
                    "prompt": f"memory test {i}",
                    "width": 512,
                    "height": 512
                }, timeout=15)

                if response.status_code == 200:
                    job_data = response.json()
                    self.wait_for_job(job_data.get('job_id'), max_wait=30)

            # Measure final memory
            final_memory = self.get_anime_memory_usage()
            memory_increase = final_memory - initial_memory

            # Allow 50MB increase for normal operation
            if memory_increase <= 50:
                passed = True
                details = f"Memory stable: +{memory_increase:.1f}MB after 20 generations"
            else:
                passed = False
                details = f"Memory leak detected: +{memory_increase:.1f}MB after 20 generations"

        except Exception as e:
            passed = False
            details = f"Exception during memory test: {e}"

        execution_time = time.time() - start_time
        self.log_test_result('memory', 'Memory Leak Detection', passed, details, execution_time)

    def test_database_integrity_under_load(self) -> None:
        """Test database maintains integrity under load"""
        start_time = time.time()

        try:
            # Get initial job count
            response = requests.get(f"{self.api_base}/jobs?limit=1", timeout=5)
            initial_stats = response.json()['summary'] if response.status_code == 200 else {'total': 0}
            initial_count = initial_stats.get('total', 0)

            # Submit 15 jobs rapidly
            job_ids = []
            for i in range(15):
                response = requests.post(f"{self.api_base}/generate", json={
                    "prompt": f"db integrity test {i}",
                    "width": 512,
                    "height": 512
                }, timeout=10)

                if response.status_code == 200:
                    job_ids.append(response.json().get('job_id'))

            # Wait for all to complete
            time.sleep(30)

            # Check final count
            response = requests.get(f"{self.api_base}/jobs?limit=1", timeout=5)
            final_stats = response.json()['summary'] if response.status_code == 200 else {'total': 0}
            final_count = final_stats.get('total', 0)

            expected_increase = len(job_ids)
            actual_increase = final_count - initial_count

            if actual_increase == expected_increase:
                passed = True
                details = f"Database integrity maintained: {expected_increase} jobs added correctly"
            else:
                passed = False
                details = f"Database inconsistency: expected +{expected_increase}, got +{actual_increase}"

        except Exception as e:
            passed = False
            details = f"Exception during database integrity test: {e}"

        execution_time = time.time() - start_time
        self.log_test_result('reliability', 'Database Integrity Under Load', passed, details, execution_time)

    def test_error_recovery_scenarios(self) -> None:
        """Test system recovery from error conditions"""
        start_time = time.time()

        try:
            # Test invalid input handling
            invalid_requests = [
                {"prompt": "", "width": 512, "height": 512},  # Empty prompt
                {"prompt": "test", "width": -1, "height": 512},  # Invalid dimensions
                {"prompt": "test", "width": 512, "height": 10000}  # Extreme dimensions
            ]

            recovery_successful = True

            for i, invalid_req in enumerate(invalid_requests):
                response = requests.post(f"{self.api_base}/generate",
                                       json=invalid_req, timeout=10)

                # Should return 4xx error, not crash
                if response.status_code >= 500:
                    recovery_successful = False
                    break

            # Test that system still works after errors
            response = requests.post(f"{self.api_base}/generate", json={
                "prompt": "recovery test",
                "width": 512,
                "height": 512
            }, timeout=15)

            if response.status_code == 200 and recovery_successful:
                passed = True
                details = "System properly recovers from error conditions"
            else:
                passed = False
                details = "System failed to recover from errors or crashed"

        except Exception as e:
            passed = False
            details = f"Exception during error recovery test: {e}"

        execution_time = time.time() - start_time
        self.log_test_result('reliability', 'Error Recovery', passed, details, execution_time)

    def wait_for_job(self, job_id: str, max_wait: int = 60) -> Optional[float]:
        """Wait for job completion and return time taken"""
        if not job_id:
            return None

        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                response = requests.get(f"{self.api_base}/jobs/{job_id}", timeout=5)
                if response.status_code == 200:
                    job_data = response.json()
                    if job_data.get('status') == 'completed':
                        return time.time() - start_time
                    elif job_data.get('status') == 'failed':
                        return None

                time.sleep(1)
            except:
                time.sleep(1)

        return None  # Timeout

    def get_anime_memory_usage(self) -> float:
        """Get total memory usage of anime processes in MB"""
        total_memory = 0

        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info']):
            try:
                if any('anime' in str(item).lower() for item in proc.info['cmdline'] or []):
                    total_memory += proc.info['memory_info'].rss / 1024 / 1024
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return total_memory

    def run_production_test_suite(self) -> Dict[str, Any]:
        """Run complete production test suite"""
        print("🧪 PRODUCTION TEST SUITE - Tower Anime Production")
        print("=" * 80)
        print(f"{'Status':<6} | {'Category':<12} | {'Test Name':<40} | {'Time':<8}")
        print("-" * 80)

        # Security Tests
        self.test_authentication_security()
        self.test_sql_injection_protection()
        self.test_rate_limiting()

        # Performance Tests
        self.test_performance_single_generation()
        self.test_concurrent_generation_capacity()

        # Reliability Tests
        self.test_database_integrity_under_load()
        self.test_error_recovery_scenarios()

        # Memory Tests
        self.test_memory_leak_detection()

        # Generate summary
        print("\n" + "=" * 80)
        print("🎯 PRODUCTION TEST RESULTS")
        print("=" * 80)

        total_passed = sum(cat['passed'] for cat in self.test_results.values())
        total_failed = sum(cat['failed'] for cat in self.test_results.values())
        total_tests = total_passed + total_failed
        pass_rate = (total_passed / total_tests) * 100 if total_tests > 0 else 0

        print(f"Total Tests: {total_tests}")
        print(f"Passed: {total_passed}")
        print(f"Failed: {total_failed}")
        print(f"Pass Rate: {pass_rate:.1f}%")

        for category, results in self.test_results.items():
            cat_total = results['passed'] + results['failed']
            cat_pass_rate = (results['passed'] / cat_total) * 100 if cat_total > 0 else 0
            print(f"\n{category.upper()}: {results['passed']}/{cat_total} ({cat_pass_rate:.1f}%)")

        # Production readiness verdict
        print("\n" + "=" * 80)
        print("🚀 PRODUCTION READINESS VERDICT")
        print("=" * 80)

        critical_security_passed = (
            self.test_results['security']['passed'] ==
            len(self.test_results['security']['tests'])
        )

        performance_acceptable = (
            self.test_results['performance']['passed'] >=
            len(self.test_results['performance']['tests']) * 0.8
        )

        if critical_security_passed and pass_rate >= 90:
            verdict = "✅ APPROVED FOR PRODUCTION"
            print(verdict)
            print("All critical security tests passed and overall pass rate ≥90%")
        elif not critical_security_passed:
            verdict = "🚨 BLOCKED - SECURITY FAILURES"
            print(verdict)
            print("Critical security vulnerabilities must be fixed before production")
        elif pass_rate < 80:
            verdict = "❌ NOT READY - LOW PASS RATE"
            print(verdict)
            print(f"Pass rate {pass_rate:.1f}% is below 80% minimum for production")
        else:
            verdict = "⚠️  CONDITIONAL APPROVAL"
            print(verdict)
            print("May proceed to production with close monitoring")

        return {
            'verdict': verdict,
            'pass_rate': pass_rate,
            'total_tests': total_tests,
            'results': self.test_results,
            'production_ready': critical_security_passed and pass_rate >= 90
        }


if __name__ == "__main__":
    test_suite = ProductionTestSuite()
    results = test_suite.run_production_test_suite()

    # Exit with appropriate code for CI/CD
    exit_code = 0 if results['production_ready'] else 1
    exit(exit_code)