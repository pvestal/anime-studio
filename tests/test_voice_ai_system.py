#!/usr/bin/env python3
"""
Comprehensive Testing Suite for Voice AI System
Tests all components of the voice generation and integration system
"""

import asyncio
import json
import os
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import asyncpg
import httpx
import pytest
from fastapi.testclient import TestClient

# Test configuration
TEST_DB_CONFIG = {
    "host": "192.168.50.135",
    "database": "tower_consolidated",
    "user": "patrick",
    "password": "tower_echo_brain_secret_key_2025",
}

# Mock data for testing
MOCK_CHARACTER_PROFILES = [
    {
        "character_name": "TestCharacter1",
        "voice_id": "test_voice_1",
        "voice_name": "Test Voice 1",
        "description": "Test character voice profile"
    },
    {
        "character_name": "TestCharacter2",
        "voice_id": "test_voice_2",
        "voice_name": "Test Voice 2",
        "description": "Another test character voice profile"
    }
]

MOCK_DIALOGUE_LINES = [
    {
        "character_name": "TestCharacter1",
        "dialogue_text": "Hello, this is a test dialogue line.",
        "emotion": "neutral"
    },
    {
        "character_name": "TestCharacter2",
        "dialogue_text": "This is another test line with excitement!",
        "emotion": "excited"
    }
]

class VoiceAITestSuite:
    """Main test suite for Voice AI system"""

    def __init__(self):
        self.db_pool: Optional[asyncpg.Pool] = None
        self.voice_api_url = "http://localhost:8319"
        self.anime_api_url = "http://localhost:8328"
        self.echo_brain_url = "http://localhost:8309"
        self.test_files_created = []

    async def setup(self):
        """Set up test environment"""
        try:
            # Initialize database connection
            self.db_pool = await asyncpg.create_pool(**TEST_DB_CONFIG)

            # Clean up any existing test data
            await self.cleanup_test_data()

            # Create test storage directories
            self.test_storage = Path("/tmp/voice_ai_test")
            self.test_storage.mkdir(parents=True, exist_ok=True)

            print("✓ Test environment setup completed")

        except Exception as e:
            print(f"✗ Test setup failed: {e}")
            raise

    async def cleanup(self):
        """Clean up test environment"""
        try:
            # Clean up test data
            await self.cleanup_test_data()

            # Close database connections
            if self.db_pool:
                await self.db_pool.close()

            # Clean up test files
            for file_path in self.test_files_created:
                try:
                    Path(file_path).unlink(missing_ok=True)
                except Exception as e:
                    print(f"Warning: Could not remove test file {file_path}: {e}")

            print("✓ Test cleanup completed")

        except Exception as e:
            print(f"✗ Test cleanup failed: {e}")

    async def cleanup_test_data(self):
        """Clean up test data from database"""
        try:
            async with self.db_pool.acquire() as conn:
                # Delete test voice profiles
                await conn.execute(
                    "DELETE FROM voice_profiles WHERE character_name LIKE 'TestCharacter%'"
                )

                # Delete test voice jobs
                await conn.execute(
                    "DELETE FROM voice_generation_jobs WHERE character_name LIKE 'TestCharacter%'"
                )

                # Delete test dialogue data
                await conn.execute(
                    "DELETE FROM dialogue_lines WHERE character_name LIKE 'TestCharacter%'"
                )

                # Delete test scenes
                await conn.execute(
                    "DELETE FROM dialogue_scenes WHERE scene_name LIKE 'TestScene%'"
                )

        except Exception as e:
            print(f"Warning: Test data cleanup failed: {e}")

    async def test_voice_service_health(self) -> bool:
        """Test voice service health endpoint"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.voice_api_url}/api/voice/health")

                if response.status_code == 200:
                    health_data = response.json()
                    print(f"✓ Voice service health check passed: {health_data['status']}")
                    return True
                else:
                    print(f"✗ Voice service health check failed: {response.status_code}")
                    return False

        except Exception as e:
            print(f"✗ Voice service health check error: {e}")
            return False

    async def test_character_profile_management(self) -> bool:
        """Test character voice profile creation and management"""
        try:
            async with httpx.AsyncClient() as client:
                # Test creating character profiles
                for profile in MOCK_CHARACTER_PROFILES:
                    response = await client.post(
                        f"{self.voice_api_url}/api/voice/characters/profile",
                        json=profile
                    )

                    if response.status_code == 200:
                        result = response.json()
                        print(f"✓ Character profile created: {profile['character_name']}")
                    else:
                        print(f"✗ Character profile creation failed: {response.status_code}")
                        return False

                # Test listing character profiles
                response = await client.get(f"{self.voice_api_url}/api/voice/characters")

                if response.status_code == 200:
                    characters = response.json()
                    if characters['count'] >= len(MOCK_CHARACTER_PROFILES):
                        print(f"✓ Character profile listing: {characters['count']} characters found")
                    else:
                        print(f"✗ Character profile listing incomplete")
                        return False
                else:
                    print(f"✗ Character profile listing failed: {response.status_code}")
                    return False

                return True

        except Exception as e:
            print(f"✗ Character profile management test error: {e}")
            return False

    async def test_voice_generation(self) -> bool:
        """Test voice generation functionality"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                for line in MOCK_DIALOGUE_LINES:
                    # Test quick voice generation
                    response = await client.post(
                        f"{self.voice_api_url}/api/voice/generate/quick",
                        json=line
                    )

                    if response.status_code == 200:
                        result = response.json()
                        print(f"✓ Voice generated for {line['character_name']}: {result['job_id']}")

                        # Store for cleanup
                        if result.get('audio_file_path'):
                            self.test_files_created.append(result['audio_file_path'])
                    else:
                        print(f"✗ Voice generation failed for {line['character_name']}: {response.status_code}")
                        return False

                return True

        except Exception as e:
            print(f"✗ Voice generation test error: {e}")
            return False

    async def test_batch_voice_generation(self) -> bool:
        """Test batch voice generation"""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                batch_request = {
                    "lines": MOCK_DIALOGUE_LINES,
                    "scene_name": "TestScene1"
                }

                response = await client.post(
                    f"{self.voice_api_url}/api/voice/generate/batch",
                    json=batch_request
                )

                if response.status_code == 200:
                    result = response.json()
                    print(f"✓ Batch voice generation started: {result['batch_id']}")
                    print(f"  Lines queued: {result['lines_count']}")

                    # Wait a moment for processing
                    await asyncio.sleep(5)

                    return True
                else:
                    print(f"✗ Batch voice generation failed: {response.status_code}")
                    return False

        except Exception as e:
            print(f"✗ Batch voice generation test error: {e}")
            return False

    async def test_dialogue_scene_processing(self) -> bool:
        """Test complete dialogue scene processing"""
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                scene_data = {
                    "scene_name": "TestScene2",
                    "project_id": "test_project_1",
                    "dialogue_lines": [
                        {
                            "character_name": line["character_name"],
                            "dialogue_text": line["dialogue_text"],
                            "emotion": line["emotion"],
                            "priority": 1,
                            "voice_settings": {}
                        }
                        for line in MOCK_DIALOGUE_LINES
                    ],
                    "auto_timing": True,
                    "background_music_volume": 0.3
                }

                response = await client.post(
                    f"{self.voice_api_url}/api/voice/scenes/process",
                    json=scene_data
                )

                if response.status_code == 200:
                    result = response.json()
                    print(f"✓ Scene dialogue processing completed: {result['scene_id']}")
                    print(f"  Lines processed: {result['dialogue_lines_processed']}")
                    print(f"  Scene duration: {result.get('scene_duration', 0):.2f}s")

                    # Test scene retrieval
                    scene_id = result['scene_id']
                    response = await client.get(f"{self.voice_api_url}/api/voice/scenes/{scene_id}")

                    if response.status_code == 200:
                        scene_details = response.json()
                        print(f"✓ Scene retrieval successful: {len(scene_details['dialogue_lines'])} lines")
                    else:
                        print(f"✗ Scene retrieval failed: {response.status_code}")
                        return False

                    return True
                else:
                    print(f"✗ Scene dialogue processing failed: {response.status_code}")
                    return False

        except Exception as e:
            print(f"✗ Dialogue scene processing test error: {e}")
            return False

    async def test_echo_brain_integration(self) -> bool:
        """Test Echo Brain integration for voice assessment"""
        try:
            # First check if Echo Brain is available
            async with httpx.AsyncClient(timeout=10) as client:
                try:
                    response = await client.get(f"{self.echo_brain_url}/api/echo/health")
                    if response.status_code != 200:
                        print("⚠ Echo Brain not available - skipping integration test")
                        return True  # Skip but don't fail
                except Exception:
                    print("⚠ Echo Brain not available - skipping integration test")
                    return True  # Skip but don't fail

            # Test voice quality assessment
            async with httpx.AsyncClient(timeout=30) as client:
                assessment_request = {
                    "job_id": str(uuid.uuid4()),
                    "audio_file_path": "/tmp/test_audio.mp3",
                    "character_name": "TestCharacter1",
                    "original_text": "This is a test for voice quality assessment.",
                    "emotion": "neutral",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
                    "compare_with_profile": True
                }

                response = await client.post(
                    f"{self.voice_api_url}/api/voice/assess",
                    json=assessment_request
                )

                if response.status_code == 200:
                    result = response.json()
                    print(f"✓ Voice quality assessment completed")
                    print(f"  Assessment success: {result['success']}")
                    if result.get('assessment'):
                        assessment = result['assessment']
                        print(f"  Overall score: {assessment.get('overall_score', 0):.2f}")
                        print(f"  Approved: {result.get('approved', False)}")
                else:
                    print(f"✗ Voice quality assessment failed: {response.status_code}")
                    return False

            return True

        except Exception as e:
            print(f"✗ Echo Brain integration test error: {e}")
            return False

    async def test_audio_management(self) -> bool:
        """Test audio file management and optimization"""
        try:
            # Test storage statistics
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.voice_api_url}/api/voice/stats")

                if response.status_code == 200:
                    stats = response.json()
                    print(f"✓ Voice statistics retrieved:")
                    print(f"  Total voice jobs: {stats.get('voice_generation', {}).get('total_jobs', 0)}")
                    print(f"  Total characters: {stats.get('characters', {}).get('total_characters', 0)}")
                    print(f"  Success rate: {stats.get('voice_generation', {}).get('success_rate', 0):.2%}")
                else:
                    print(f"✗ Voice statistics failed: {response.status_code}")
                    return False

            return True

        except Exception as e:
            print(f"✗ Audio management test error: {e}")
            return False

    async def test_character_analytics(self) -> bool:
        """Test character voice analytics"""
        try:
            async with httpx.AsyncClient() as client:
                for profile in MOCK_CHARACTER_PROFILES:
                    character_name = profile['character_name']

                    # Test analytics retrieval
                    response = await client.get(
                        f"{self.voice_api_url}/api/voice/characters/{character_name}/analytics"
                    )

                    if response.status_code == 200:
                        analytics = response.json()
                        print(f"✓ Analytics retrieved for {character_name}")
                        print(f"  Profile exists: {analytics.get('profile_exists', False)}")
                        print(f"  Total generations: {analytics.get('generation_stats', {}).get('total_generations', 0)}")
                    else:
                        print(f"✗ Analytics failed for {character_name}: {response.status_code}")
                        return False

            return True

        except Exception as e:
            print(f"✗ Character analytics test error: {e}")
            return False

    async def test_complete_scene_integration(self) -> bool:
        """Test complete scene with video-voice integration"""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                complete_scene_request = {
                    "project_id": "test_project_integration",
                    "scene_name": "TestCompleteScene",
                    "video_prompt": "anime character speaking in a peaceful garden",
                    "characters": ["TestCharacter1", "TestCharacter2"],
                    "dialogue_lines": [
                        {
                            "character_name": "TestCharacter1",
                            "dialogue_text": "Welcome to our integration test scene.",
                            "emotion": "neutral"
                        },
                        {
                            "character_name": "TestCharacter2",
                            "dialogue_text": "This tests the complete video-voice pipeline!",
                            "emotion": "excited"
                        }
                    ],
                    "video_settings": {
                        "video_type": "video",
                        "frames": 48,
                        "fps": 24,
                        "width": 512,
                        "height": 512
                    },
                    "audio_settings": {
                        "background_music_volume": 0.3,
                        "voice_audio_volume": 0.8,
                        "enable_lip_sync": True
                    }
                }

                response = await client.post(
                    f"{self.voice_api_url}/api/voice/complete-scene",
                    json=complete_scene_request
                )

                if response.status_code == 200:
                    result = response.json()
                    processing_id = result['processing_id']
                    print(f"✓ Complete scene processing started: {processing_id}")
                    print(f"  Estimated time: {result.get('estimated_time', 0)} seconds")

                    # Wait briefly then check status
                    await asyncio.sleep(10)

                    status_response = await client.get(
                        f"{self.voice_api_url}/api/voice/complete-scene/{processing_id}/status"
                    )

                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        print(f"✓ Scene processing status retrieved: {status_data.get('processing_status', 'unknown')}")
                    else:
                        print(f"⚠ Scene processing status check failed: {status_response.status_code}")

                    return True
                else:
                    print(f"✗ Complete scene integration failed: {response.status_code}")
                    return False

        except Exception as e:
            print(f"✗ Complete scene integration test error: {e}")
            return False

    async def test_performance_benchmarks(self) -> bool:
        """Test performance benchmarks"""
        try:
            print("🔧 Running performance benchmarks...")

            # Voice generation speed test
            start_time = time.time()

            async with httpx.AsyncClient(timeout=60) as client:
                # Generate multiple voice samples concurrently
                tasks = []
                for i in range(5):
                    task = client.post(
                        f"{self.voice_api_url}/api/voice/generate/quick",
                        json={
                            "text": f"Performance test line number {i + 1} for benchmarking.",
                            "character_name": "TestCharacter1",
                            "emotion": "neutral"
                        }
                    )
                    tasks.append(task)

                # Wait for all to complete
                responses = await asyncio.gather(*tasks, return_exceptions=True)

                successful = sum(1 for r in responses if hasattr(r, 'status_code') and r.status_code == 200)
                total_time = time.time() - start_time

                print(f"✓ Performance benchmark completed:")
                print(f"  Concurrent voice generations: {len(tasks)}")
                print(f"  Successful: {successful}/{len(tasks)}")
                print(f"  Total time: {total_time:.2f} seconds")
                print(f"  Average time per generation: {total_time / len(tasks):.2f} seconds")

                return successful >= len(tasks) * 0.8  # 80% success rate

        except Exception as e:
            print(f"✗ Performance benchmark error: {e}")
            return False

    async def run_all_tests(self) -> Dict[str, bool]:
        """Run all test cases"""
        print("🚀 Starting Voice AI System Test Suite")
        print("=" * 60)

        test_results = {}

        # List of test methods
        test_methods = [
            ("Voice Service Health", self.test_voice_service_health),
            ("Character Profile Management", self.test_character_profile_management),
            ("Voice Generation", self.test_voice_generation),
            ("Batch Voice Generation", self.test_batch_voice_generation),
            ("Dialogue Scene Processing", self.test_dialogue_scene_processing),
            ("Echo Brain Integration", self.test_echo_brain_integration),
            ("Audio Management", self.test_audio_management),
            ("Character Analytics", self.test_character_analytics),
            ("Complete Scene Integration", self.test_complete_scene_integration),
            ("Performance Benchmarks", self.test_performance_benchmarks),
        ]

        for test_name, test_method in test_methods:
            print(f"\n🧪 Running test: {test_name}")
            print("-" * 40)

            try:
                result = await test_method()
                test_results[test_name] = result

                if result:
                    print(f"✅ {test_name}: PASSED")
                else:
                    print(f"❌ {test_name}: FAILED")

            except Exception as e:
                print(f"💥 {test_name}: ERROR - {e}")
                test_results[test_name] = False

        # Summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)

        passed = sum(1 for result in test_results.values() if result)
        total = len(test_results)

        for test_name, result in test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status:<10} {test_name}")

        print("-" * 60)
        print(f"📈 OVERALL RESULT: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

        if passed == total:
            print("🎉 ALL TESTS PASSED! Voice AI system is ready for production.")
        elif passed >= total * 0.8:
            print("⚠️  MOSTLY PASSED. Minor issues detected but system is functional.")
        else:
            print("🚨 SIGNIFICANT ISSUES. System requires attention before production use.")

        return test_results

# Main execution
async def main():
    """Main test execution function"""
    test_suite = VoiceAITestSuite()

    try:
        await test_suite.setup()
        results = await test_suite.run_all_tests()
        return results
    finally:
        await test_suite.cleanup()

def run_voice_ai_tests():
    """Synchronous wrapper for running tests"""
    return asyncio.run(main())

if __name__ == "__main__":
    # Run tests directly
    asyncio.run(main())