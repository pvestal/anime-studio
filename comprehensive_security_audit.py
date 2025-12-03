#!/usr/bin/env python3
"""
COMPREHENSIVE SECURITY AND PERFORMANCE AUDIT
Tower Anime Production System

CRITICAL FINDINGS:
1. HARDCODED CREDENTIALS in database.py (HIGH RISK)
2. NO INPUT VALIDATION on prompts (SQL injection risk)
3. NO AUTHENTICATION on API endpoints (CRITICAL)
4. NO RATE LIMITING (DoS vulnerability)
5. UNFILTERED CORS allowing ALL origins (SECURITY RISK)
"""

import asyncio
import json
import time
import requests
import psycopg2
import concurrent.futures
from typing import List, Dict, Any
import threading
import sys


class SecurityAudit:
    def __init__(self):
        self.api_base = "http://localhost:8328"
        self.findings = []

    def log_finding(self, severity: str, category: str, description: str, file_path: str = "", line_num: int = 0):
        """Log security finding"""
        self.findings.append({
            "severity": severity,
            "category": category,
            "description": description,
            "file": file_path,
            "line": line_num,
            "timestamp": time.time()
        })

    def test_sql_injection_vulnerabilities(self):
        """Test for SQL injection in various endpoints"""
        print("\n🔒 SQL INJECTION VULNERABILITY TESTS")
        print("-" * 50)

        # Test malicious prompts
        malicious_prompts = [
            "'; DROP TABLE anime_api.production_jobs; --",
            "' UNION SELECT * FROM pg_user WHERE '1'='1",
            "'; INSERT INTO anime_api.production_jobs (prompt) VALUES ('hacked'); --",
            "' OR 1=1; DELETE FROM anime_api.production_jobs WHERE '1'='1",
        ]

        for prompt in malicious_prompts:
            try:
                response = requests.post(f"{self.api_base}/generate", json={
                    "prompt": prompt,
                    "width": 512,
                    "height": 512
                }, timeout=10)

                if response.status_code == 200:
                    self.log_finding(
                        "HIGH",
                        "SQL_INJECTION",
                        f"Malicious SQL prompt accepted: {prompt[:50]}...",
                        "anime_generation_api_with_db.py",
                        214
                    )
                    print(f"⚠️  SQL injection attempt ACCEPTED: {prompt[:50]}...")
                else:
                    print(f"✅ SQL injection blocked: {response.status_code}")

            except Exception as e:
                print(f"🛡️  SQL injection failed: {str(e)[:50]}...")

    def test_authentication_bypass(self):
        """Test for missing authentication"""
        print("\n🔐 AUTHENTICATION BYPASS TESTS")
        print("-" * 50)

        sensitive_endpoints = [
            "/jobs",
            "/generate",
            "/health",
            "/jobs/test123"
        ]

        for endpoint in sensitive_endpoints:
            try:
                response = requests.get(f"{self.api_base}{endpoint}", timeout=5)

                if response.status_code in [200, 201, 202]:
                    self.log_finding(
                        "CRITICAL",
                        "NO_AUTHENTICATION",
                        f"Endpoint accessible without auth: {endpoint}",
                        "anime_generation_api_with_db.py"
                    )
                    print(f"❌ NO AUTH required for: {endpoint}")
                else:
                    print(f"✅ Auth required for: {endpoint}")

            except Exception as e:
                print(f"🔍 Endpoint test failed: {endpoint} - {e}")

    def test_rate_limiting(self):
        """Test for rate limiting vulnerabilities"""
        print("\n🚀 RATE LIMITING TESTS")
        print("-" * 50)

        # Rapid fire 50 requests
        start_time = time.time()
        success_count = 0

        for i in range(50):
            try:
                response = requests.get(f"{self.api_base}/health", timeout=1)
                if response.status_code == 200:
                    success_count += 1
            except:
                pass

        elapsed = time.time() - start_time

        if success_count > 40 and elapsed < 5:
            self.log_finding(
                "MEDIUM",
                "NO_RATE_LIMITING",
                f"50 requests completed in {elapsed:.2f}s (no rate limiting)",
                "anime_generation_api_with_db.py"
            )
            print(f"❌ NO RATE LIMITING: {success_count}/50 requests in {elapsed:.2f}s")
        else:
            print(f"✅ Rate limiting active: {success_count}/50 in {elapsed:.2f}s")

    def test_concurrent_generation_stress(self):
        """Test concurrent generation requests"""
        print("\n⚡ CONCURRENT GENERATION STRESS TEST")
        print("-" * 50)

        def make_generation_request(worker_id: int):
            """Single generation request"""
            try:
                start_time = time.time()
                response = requests.post(f"{self.api_base}/generate", json={
                    "prompt": f"stress test worker {worker_id}",
                    "width": 512,
                    "height": 512
                }, timeout=15)

                elapsed = time.time() - start_time

                if response.status_code == 200:
                    job_data = response.json()
                    return {
                        "worker_id": worker_id,
                        "success": True,
                        "job_id": job_data.get("job_id"),
                        "response_time": elapsed,
                        "status_code": response.status_code
                    }
                else:
                    return {
                        "worker_id": worker_id,
                        "success": False,
                        "error": f"HTTP {response.status_code}",
                        "response_time": elapsed
                    }

            except Exception as e:
                return {
                    "worker_id": worker_id,
                    "success": False,
                    "error": str(e),
                    "response_time": time.time() - start_time
                }

        # Test with 15 concurrent requests
        print("Launching 15 concurrent generation requests...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(make_generation_request, i) for i in range(15)]
            results = []

            for future in concurrent.futures.as_completed(futures, timeout=60):
                try:
                    result = future.result()
                    results.append(result)

                    if result["success"]:
                        print(f"✅ Worker {result['worker_id']}: Job {result['job_id']} in {result['response_time']:.2f}s")
                    else:
                        print(f"❌ Worker {result['worker_id']}: {result['error']} in {result['response_time']:.2f}s")

                except Exception as e:
                    print(f"💥 Worker failed: {e}")

        # Analyze results
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]

        print(f"\n📊 CONCURRENT TEST RESULTS:")
        print(f"   Success: {len(successful)}/15 ({(len(successful)/15)*100:.1f}%)")
        print(f"   Failed: {len(failed)}/15")

        if len(successful) > 0:
            avg_response = sum(r["response_time"] for r in successful) / len(successful)
            print(f"   Avg Response Time: {avg_response:.2f}s")

        if len(failed) > 10:
            self.log_finding(
                "HIGH",
                "CONCURRENT_FAILURE",
                f"High failure rate under load: {len(failed)}/15 requests failed",
                "anime_generation_api_with_db.py"
            )

    def test_database_vulnerabilities(self):
        """Test database security issues"""
        print("\n💾 DATABASE SECURITY AUDIT")
        print("-" * 50)

        # Check for hardcoded credentials
        try:
            with open("/opt/tower-anime-production/database.py", "r") as f:
                content = f.read()

            if "password" in content and "***REMOVED***" in content:
                self.log_finding(
                    "CRITICAL",
                    "HARDCODED_CREDENTIALS",
                    "Database password hardcoded in source code",
                    "database.py",
                    24
                )
                print("❌ CRITICAL: Hardcoded database password found")
            else:
                print("✅ No hardcoded credentials detected")

        except Exception as e:
            print(f"🔍 Could not check database.py: {e}")

    def test_cors_configuration(self):
        """Test CORS security"""
        print("\n🌐 CORS SECURITY AUDIT")
        print("-" * 50)

        # Check CORS headers
        try:
            response = requests.options(f"{self.api_base}/generate", headers={
                "Origin": "https://malicious-site.com",
                "Access-Control-Request-Method": "POST"
            })

            cors_header = response.headers.get("Access-Control-Allow-Origin")

            if cors_header == "*":
                self.log_finding(
                    "MEDIUM",
                    "INSECURE_CORS",
                    "CORS allows all origins (*) - security risk",
                    "anime_generation_api_with_db.py",
                    47
                )
                print("❌ INSECURE CORS: All origins allowed")
            else:
                print(f"✅ CORS properly configured: {cors_header}")

        except Exception as e:
            print(f"🔍 CORS test failed: {e}")

    def test_input_validation(self):
        """Test input validation vulnerabilities"""
        print("\n📝 INPUT VALIDATION TESTS")
        print("-" * 50)

        invalid_inputs = [
            {"prompt": "x" * 10000, "width": 512, "height": 512},  # Extremely long prompt
            {"prompt": "test", "width": -1, "height": 512},  # Negative width
            {"prompt": "test", "width": 512, "height": 99999},  # Huge height
            {"prompt": "test", "width": "invalid", "height": 512},  # String width
            {"prompt": None, "width": 512, "height": 512},  # Null prompt
        ]

        for i, invalid_input in enumerate(invalid_inputs):
            try:
                response = requests.post(f"{self.api_base}/generate",
                                       json=invalid_input, timeout=10)

                if response.status_code == 200:
                    self.log_finding(
                        "MEDIUM",
                        "INSUFFICIENT_VALIDATION",
                        f"Invalid input accepted: {str(invalid_input)[:50]}...",
                        "anime_generation_api_with_db.py",
                        214
                    )
                    print(f"❌ Invalid input {i+1} ACCEPTED")
                else:
                    print(f"✅ Invalid input {i+1} properly rejected: {response.status_code}")

            except Exception as e:
                print(f"✅ Invalid input {i+1} caused exception (good): {str(e)[:50]}...")

    def run_comprehensive_audit(self):
        """Run all security tests"""
        print("🔒 COMPREHENSIVE SECURITY AUDIT - Tower Anime Production")
        print("=" * 60)

        # Run all tests
        self.test_database_vulnerabilities()
        self.test_authentication_bypass()
        self.test_cors_configuration()
        self.test_input_validation()
        self.test_sql_injection_vulnerabilities()
        self.test_rate_limiting()
        self.test_concurrent_generation_stress()

        # Summary report
        print("\n" + "=" * 60)
        print("🚨 SECURITY AUDIT SUMMARY")
        print("=" * 60)

        critical_findings = [f for f in self.findings if f["severity"] == "CRITICAL"]
        high_findings = [f for f in self.findings if f["severity"] == "HIGH"]
        medium_findings = [f for f in self.findings if f["severity"] == "MEDIUM"]

        print(f"CRITICAL Issues: {len(critical_findings)}")
        print(f"HIGH Issues: {len(high_findings)}")
        print(f"MEDIUM Issues: {len(medium_findings)}")
        print(f"TOTAL Issues: {len(self.findings)}")

        # Detailed findings
        for finding in self.findings:
            severity_emoji = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "⚡"}
            emoji = severity_emoji.get(finding["severity"], "🔍")

            print(f"\n{emoji} {finding['severity']} - {finding['category']}")
            print(f"   📄 {finding['description']}")
            if finding['file']:
                print(f"   📂 File: {finding['file']}")
            if finding['line']:
                print(f"   📍 Line: {finding['line']}")

        # Recommendations
        print("\n" + "=" * 60)
        print("💡 CRITICAL RECOMMENDATIONS")
        print("=" * 60)

        print("1. IMMEDIATE: Move database credentials to environment variables")
        print("2. IMMEDIATE: Implement API authentication (JWT/OAuth)")
        print("3. HIGH: Add input validation and sanitization")
        print("4. HIGH: Implement rate limiting (per IP/user)")
        print("5. MEDIUM: Restrict CORS to specific domains")
        print("6. MEDIUM: Add request logging and monitoring")
        print("7. LOW: Implement HTTPS in production")

        return len(critical_findings), len(high_findings), len(medium_findings)


if __name__ == "__main__":
    audit = SecurityAudit()
    critical, high, medium = audit.run_comprehensive_audit()

    # Exit with appropriate code
    if critical > 0:
        sys.exit(2)  # Critical issues found
    elif high > 0:
        sys.exit(1)  # High issues found
    else:
        sys.exit(0)  # No critical/high issues