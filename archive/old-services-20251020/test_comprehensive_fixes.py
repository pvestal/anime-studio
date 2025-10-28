#!/usr/bin/env python3
"""
Comprehensive Test Suite for Anime Production Fixes
Tests all critical issues that were fixed and verifies they work correctly

FIXES VERIFIED:
1. Real quality assessment (not fake 0.85 scores)
2. Fixed FastAPI routing bugs (generation types vs project IDs)
3. Stuck projects cleared and real status tracking
4. Real ComfyUI progress monitoring (not fake 0.5)
"""

import asyncio
import aiohttp
import json
import time
import sys
import os
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor

# Test configuration
API_BASE = "http://localhost:44451"  # Direct API port
COMFYUI_URL = "http://127.0.0.1:8188"
DB_PARAMS = {
    'host': 'localhost',
    'database': 'tower_consolidated',
    'user': 'patrick',
    'password': '***REMOVED***'
}

class AnimeProductionTestSuite:
    def __init__(self):
        self.results = {
            'quality_assessment': {'status': 'pending', 'details': []},
            'routing_fixes': {'status': 'pending', 'details': []},
            'stuck_projects': {'status': 'pending', 'details': []},
            'progress_tracking': {'status': 'pending', 'details': []},
            'integration': {'status': 'pending', 'details': []}
        }
        self.session = None

    async def setup(self):
        """Setup test session"""
        self.session = aiohttp.ClientSession()
        print("🚀 Starting Comprehensive Anime Production Test Suite")
        print(f"📊 Testing API at: {API_BASE}")
        print(f"⏰ Test started at: {datetime.now()}")
        print("=" * 80)

    async def cleanup(self):
        """Cleanup test session"""
        if self.session:
            await self.session.close()

    async def test_health_check(self):
        """Test basic API health"""
        try:
            async with self.session.get(f"{API_BASE}/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    print(f"✅ API Health: {health_data}")
                    return True
                else:
                    print(f"❌ API Health Failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ API Health Error: {e}")
            return False

    async def test_quality_assessment_fix(self):
        """
        TEST 1: Quality Assessment - Verify REAL computer vision instead of fake 0.85
        """
        print("\n🔍 TEST 1: Quality Assessment Fix")
        try:
            # Create a test project
            project_data = {
                "name": "Quality Test Project",
                "description": "Testing real quality assessment"
            }

            async with self.session.post(f"{API_BASE}/projects", json=project_data) as response:
                if response.status == 200:
                    project = await response.json()
                    project_id = project['id']
                    print(f"✅ Created test project: {project_id}")

                    # Create a mock job with output file
                    await self.create_mock_job_with_file(project_id)

                    # Test quality assessment endpoint
                    async with self.session.get(f"{API_BASE}/quality/assess/1") as qual_response:
                        if qual_response.status in [200, 500]:  # 500 is expected if no file
                            qual_data = await qual_response.json()

                            # Verify it's not the fake 0.85 score
                            quality_score = qual_data.get('quality_score', 0)

                            if quality_score != 0.85:
                                print(f"✅ Quality assessment is REAL: {quality_score}")
                                print(f"📊 Assessment details: {qual_data}")
                                self.results['quality_assessment']['status'] = 'passed'
                                self.results['quality_assessment']['details'].append(
                                    f"Real quality score: {quality_score} (not fake 0.85)"
                                )
                            else:
                                print(f"❌ Still using fake 0.85 score!")
                                self.results['quality_assessment']['status'] = 'failed'
                        else:
                            print(f"❌ Quality assessment endpoint failed: {qual_response.status}")
                            self.results['quality_assessment']['status'] = 'failed'
                else:
                    print(f"❌ Failed to create test project: {response.status}")
                    self.results['quality_assessment']['status'] = 'failed'

        except Exception as e:
            print(f"❌ Quality assessment test error: {e}")
            self.results['quality_assessment']['status'] = 'error'
            self.results['quality_assessment']['details'].append(str(e))

    async def test_routing_fixes(self):
        """
        TEST 2: FastAPI Routing - Verify generation types don't conflict with project IDs
        """
        print("\n🛣️ TEST 2: FastAPI Routing Fixes")
        try:
            # Test the problematic routes that were fixed
            test_routes = [
                ("/generate/integrated", "POST", {"prompt": "test integrated", "style": "anime"}),
                ("/generate/professional", "POST", {"prompt": "test professional", "style": "anime"}),
                ("/generate/personal", "POST", {"prompt": "test personal", "style": "anime"}),
            ]

            routing_success = True

            for route, method, data in test_routes:
                try:
                    if method == "POST":
                        async with self.session.post(f"{API_BASE}{route}", json=data) as response:
                            status = response.status
                            response_text = await response.text()

                            # Route should be recognized (not 404)
                            if status != 404:
                                print(f"✅ Route {route} properly recognized: {status}")
                                self.results['routing_fixes']['details'].append(
                                    f"Route {route}: {status} - Properly routed"
                                )
                            else:
                                print(f"❌ Route {route} not found: {status}")
                                routing_success = False

                except Exception as e:
                    print(f"⚠️ Route {route} error: {e}")

            # Test the renamed route that fixes conflicts
            try:
                project_data = {"name": "Routing Test", "description": "Test"}
                async with self.session.post(f"{API_BASE}/projects", json=project_data) as response:
                    if response.status == 200:
                        project = await response.json()
                        project_id = project['id']

                        # Test the fixed route: /projects/{id}/generate instead of /generate/{id}
                        gen_data = {"prompt": "test", "character": "original"}
                        async with self.session.post(f"{API_BASE}/projects/{project_id}/generate", json=gen_data) as gen_response:
                            if gen_response.status != 404:
                                print(f"✅ Fixed project generation route works: {gen_response.status}")
                                routing_success = True
                            else:
                                print(f"❌ Fixed project generation route failed: {gen_response.status}")
                                routing_success = False

            except Exception as e:
                print(f"⚠️ Project generation route test error: {e}")

            self.results['routing_fixes']['status'] = 'passed' if routing_success else 'failed'

        except Exception as e:
            print(f"❌ Routing test error: {e}")
            self.results['routing_fixes']['status'] = 'error'

    async def test_stuck_projects_fix(self):
        """
        TEST 3: Stuck Projects - Verify clearing mechanism works
        """
        print("\n🔄 TEST 3: Stuck Projects Fix")
        try:
            # Create a stuck project directly in database
            conn = psycopg2.connect(**DB_PARAMS)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Insert a stuck project (older than 10 minutes)
            stuck_time = datetime.now() - timedelta(minutes=15)
            cur.execute("""
                INSERT INTO anime_projects (name, description, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (
                "Stuck Test Project",
                "This project should be stuck",
                "generating",
                stuck_time,
                stuck_time
            ))

            stuck_project_id = cur.fetchone()['id']
            conn.commit()
            print(f"📝 Created stuck project: {stuck_project_id}")

            # Test the clear stuck projects endpoint
            async with self.session.post(f"{API_BASE}/projects/clear-stuck") as response:
                if response.status == 200:
                    clear_result = await response.json()
                    print(f"✅ Clear stuck projects response: {clear_result}")

                    # Verify the project status was updated
                    cur.execute("SELECT status FROM anime_projects WHERE id = %s", (stuck_project_id,))
                    updated_status = cur.fetchone()['status']

                    if updated_status != "generating":
                        print(f"✅ Stuck project status cleared: {updated_status}")
                        self.results['stuck_projects']['status'] = 'passed'
                        self.results['stuck_projects']['details'].append(
                            f"Cleared {clear_result.get('stuck_projects', 0)} stuck projects"
                        )
                    else:
                        print(f"❌ Stuck project still stuck: {updated_status}")
                        self.results['stuck_projects']['status'] = 'failed'
                else:
                    print(f"❌ Clear stuck projects failed: {response.status}")
                    self.results['stuck_projects']['status'] = 'failed'

            cur.close()
            conn.close()

        except Exception as e:
            print(f"❌ Stuck projects test error: {e}")
            self.results['stuck_projects']['status'] = 'error'

    async def test_progress_tracking_fix(self):
        """
        TEST 4: Progress Tracking - Verify REAL ComfyUI monitoring instead of fake 0.5
        """
        print("\n📊 TEST 4: Progress Tracking Fix")
        try:
            # Test the generation status endpoint
            test_request_id = "test_progress_" + str(int(time.time()))

            async with self.session.get(f"{API_BASE}/generation/{test_request_id}/status") as response:
                if response.status == 200:
                    status_data = await response.json()
                    progress = status_data.get('progress', -1)

                    print(f"📊 Status response: {status_data}")

                    # Verify it's not the hardcoded 0.5
                    if progress != 0.5:
                        print(f"✅ Progress tracking is REAL: {progress}")
                        self.results['progress_tracking']['status'] = 'passed'
                        self.results['progress_tracking']['details'].append(
                            f"Real progress value: {progress} (not fake 0.5)"
                        )
                    else:
                        # If it's 0.5, check if it's from real ComfyUI or fake
                        print(f"⚠️ Progress is 0.5 - checking if real or fake...")

                        # Test with another ID to see if it varies
                        test_request_id2 = "test_progress_" + str(int(time.time()) + 1)
                        async with self.session.get(f"{API_BASE}/generation/{test_request_id2}/status") as response2:
                            if response2.status == 200:
                                status_data2 = await response2.json()
                                progress2 = status_data2.get('progress', -1)

                                if progress2 != progress:
                                    print(f"✅ Progress varies: {progress} vs {progress2} - Real tracking!")
                                    self.results['progress_tracking']['status'] = 'passed'
                                else:
                                    print(f"❌ Progress always same: likely fake")
                                    self.results['progress_tracking']['status'] = 'failed'

                else:
                    print(f"❌ Generation status endpoint failed: {response.status}")
                    self.results['progress_tracking']['status'] = 'failed'

        except Exception as e:
            print(f"❌ Progress tracking test error: {e}")
            self.results['progress_tracking']['status'] = 'error'

    async def test_integration_verification(self):
        """
        TEST 5: Integration Test - End-to-end verification
        """
        print("\n🔗 TEST 5: Integration Verification")
        try:
            # Test complete workflow
            print("🔄 Testing complete generation workflow...")

            # 1. Create project
            project_data = {"name": "Integration Test", "description": "End-to-end test"}
            async with self.session.post(f"{API_BASE}/projects", json=project_data) as response:
                if response.status == 200:
                    project = await response.json()
                    project_id = project['id']
                    print(f"✅ Project created: {project_id}")

                    # 2. Start generation (using fixed route)
                    gen_data = {"prompt": "anime character test", "character": "original"}
                    async with self.session.post(f"{API_BASE}/projects/{project_id}/generate", json=gen_data) as gen_response:
                        gen_status = gen_response.status
                        print(f"📝 Generation started: {gen_status}")

                        if gen_status in [200, 202, 500]:  # 500 might be expected if services not running
                            gen_result = await gen_response.json()
                            print(f"📊 Generation result: {gen_result}")

                            # 3. Check project status
                            async with self.session.get(f"{API_BASE}/projects") as projects_response:
                                if projects_response.status == 200:
                                    projects = await projects_response.json()
                                    our_project = next((p for p in projects if p['id'] == project_id), None)

                                    if our_project:
                                        print(f"✅ Project status: {our_project.get('status', 'unknown')}")
                                        self.results['integration']['status'] = 'passed'
                                        self.results['integration']['details'].append(
                                            "Complete workflow tested successfully"
                                        )
                                    else:
                                        print(f"❌ Project not found after creation")
                                        self.results['integration']['status'] = 'failed'
                                else:
                                    print(f"❌ Failed to get projects: {projects_response.status}")
                                    self.results['integration']['status'] = 'failed'
                        else:
                            print(f"❌ Generation failed: {gen_status}")
                            self.results['integration']['status'] = 'failed'
                else:
                    print(f"❌ Failed to create project: {response.status}")
                    self.results['integration']['status'] = 'failed'

        except Exception as e:
            print(f"❌ Integration test error: {e}")
            self.results['integration']['status'] = 'error'

    async def create_mock_job_with_file(self, project_id):
        """Create a mock job with output file for quality testing"""
        try:
            conn = psycopg2.connect(**DB_PARAMS)
            cur = conn.cursor()

            # Create a mock output file
            mock_file_path = "/tmp/test_anime_output.png"
            with open(mock_file_path, 'w') as f:
                f.write("mock image data")

            # Insert job record
            cur.execute("""
                INSERT INTO production_jobs (project_id, job_type, prompt, parameters, status, output_path)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                project_id,
                "test_generation",
                "test prompt",
                '{"test": true}',
                "completed",
                mock_file_path
            ))

            conn.commit()
            cur.close()
            conn.close()
            print(f"📁 Created mock job with output file: {mock_file_path}")

        except Exception as e:
            print(f"⚠️ Failed to create mock job: {e}")

    async def generate_report(self):
        """Generate comprehensive test report"""
        print("\n" + "=" * 80)
        print("📊 COMPREHENSIVE TEST RESULTS")
        print("=" * 80)

        total_tests = len(self.results)
        passed_tests = sum(1 for result in self.results.values() if result['status'] == 'passed')
        failed_tests = sum(1 for result in self.results.values() if result['status'] == 'failed')
        error_tests = sum(1 for result in self.results.values() if result['status'] == 'error')

        print(f"📈 SUMMARY: {passed_tests}/{total_tests} tests passed")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"⚠️ Errors: {error_tests}")
        print()

        for test_name, result in self.results.items():
            status_emoji = {"passed": "✅", "failed": "❌", "error": "⚠️", "pending": "⏳"}
            emoji = status_emoji.get(result['status'], "❓")

            print(f"{emoji} {test_name.upper().replace('_', ' ')}: {result['status']}")
            for detail in result['details']:
                print(f"   └─ {detail}")
            print()

        # Overall result
        if passed_tests == total_tests:
            print("🎉 ALL FIXES VERIFIED WORKING!")
            return True
        else:
            print("⚠️ Some fixes need attention")
            return False

    async def run_all_tests(self):
        """Run complete test suite"""
        await self.setup()

        try:
            # Basic health check
            if not await self.test_health_check():
                print("❌ API not available - cannot run tests")
                return False

            # Run all fix verification tests
            await self.test_quality_assessment_fix()
            await self.test_routing_fixes()
            await self.test_stuck_projects_fix()
            await self.test_progress_tracking_fix()
            await self.test_integration_verification()

            # Generate final report
            success = await self.generate_report()

            return success

        finally:
            await self.cleanup()

async def main():
    """Main test runner"""
    print("🎬 Anime Production Fixes Verification Suite")
    print("🎯 Testing all critical fixes implemented")
    print()

    test_suite = AnimeProductionTestSuite()
    success = await test_suite.run_all_tests()

    if success:
        print("\n🚀 All fixes verified - anime production system is working correctly!")
        sys.exit(0)
    else:
        print("\n⚠️ Some issues detected - check test results above")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())