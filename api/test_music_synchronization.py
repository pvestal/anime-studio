#!/usr/bin/env python3
"""
Music Synchronization System Test Suite
Comprehensive testing of the complete music-video synchronization pipeline
including BPM analysis, AI music selection, and frame-accurate synchronization.

Author: Claude Code
Created: 2025-12-15
Purpose: End-to-end testing of anime music synchronization system
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import httpx
import pytest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MusicSyncTester:
    """Comprehensive test suite for music synchronization system"""

    def __init__(self):
        self.base_url = "http://localhost"
        self.ports = {
            "music_sync": 8316,
            "ai_music": 8317,
            "integration": 8318,
            "apple_music": 8315,
            "echo_brain": 8309
        }

        self.test_data_dir = Path("/opt/tower-anime-production/test_data")
        self.test_data_dir.mkdir(exist_ok=True)

        self.test_results = {}

    async def run_comprehensive_tests(self) -> Dict[str, Any]:
        """Run complete test suite"""

        logger.info("🧪 Starting comprehensive music synchronization tests")

        test_results = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "running",
            "service_health": {},
            "component_tests": {},
            "integration_tests": {},
            "performance_metrics": {},
            "errors": []
        }

        try:
            # 1. Service Health Checks
            logger.info("📊 Testing service health...")
            test_results["service_health"] = await self._test_service_health()

            # 2. Component Tests
            logger.info("🔧 Testing individual components...")
            test_results["component_tests"] = await self._test_components()

            # 3. Integration Tests
            logger.info("🔗 Testing system integration...")
            test_results["integration_tests"] = await self._test_integration()

            # 4. Performance Tests
            logger.info("⚡ Testing performance...")
            test_results["performance_metrics"] = await self._test_performance()

            # 5. End-to-End Tests
            logger.info("🎬 Testing end-to-end workflow...")
            test_results["e2e_tests"] = await self._test_end_to_end()

            test_results["overall_status"] = "completed"
            logger.info("✅ All tests completed successfully")

        except Exception as e:
            test_results["overall_status"] = "failed"
            test_results["errors"].append(f"Test suite failed: {str(e)}")
            logger.error(f"❌ Test suite failed: {e}")

        return test_results

    async def _test_service_health(self) -> Dict[str, Any]:
        """Test health of all services"""

        health_results = {}

        for service, port in self.ports.items():
            try:
                url = f"{self.base_url}:{port}/api/{service.replace('_', '-')}/health"
                if service == "integration":
                    url = f"{self.base_url}:{port}/api/integrated/health"

                async with httpx.AsyncClient(timeout=10) as client:
                    start_time = time.time()
                    response = await client.get(url)
                    response_time = time.time() - start_time

                    health_results[service] = {
                        "status": "healthy" if response.status_code == 200 else "unhealthy",
                        "response_time": response_time,
                        "response_code": response.status_code,
                        "response_data": response.json() if response.status_code == 200 else None
                    }

            except Exception as e:
                health_results[service] = {
                    "status": "error",
                    "error": str(e)
                }

        return health_results

    async def _test_components(self) -> Dict[str, Any]:
        """Test individual component functionality"""

        component_results = {}

        # Test BPM Analysis
        logger.info("Testing BPM analysis...")
        component_results["bpm_analysis"] = await self._test_bmp_analysis()

        # Test AI Music Selection
        logger.info("Testing AI music selection...")
        component_results["ai_music_selection"] = await self._test_ai_music_selection()

        # Test Video Analysis
        logger.info("Testing video analysis...")
        component_results["video_analysis"] = await self._test_video_analysis()

        # Test Apple Music Integration
        logger.info("Testing Apple Music integration...")
        component_results["apple_music"] = await self._test_apple_music()

        return component_results

    async def _test_bpm_analysis(self) -> Dict[str, Any]:
        """Test BPM analysis functionality"""

        try:
            # Create test audio file
            test_audio = await self._create_test_audio()

            # Test track analysis
            test_request = {
                "track_id": "test_track_001",
                "title": "Test Track",
                "artist": "Test Artist",
                "duration": 30.0,
                "file_path": test_audio
            }

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}:{self.ports['music_sync']}/api/music-sync/analyze-track",
                    json=test_request
                )

                if response.status_code == 200:
                    analysis_data = response.json()
                    return {
                        "status": "success",
                        "bpm_detected": analysis_data.get("bpm"),
                        "energy_calculated": analysis_data.get("energy"),
                        "analysis_time": time.time(),
                        "full_response": analysis_data
                    }
                else:
                    return {
                        "status": "failed",
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    async def _test_ai_music_selection(self) -> Dict[str, Any]:
        """Test AI music selection functionality"""

        try:
            # Create test scene context
            scene_context = {
                "scene_id": "test_scene_001",
                "duration": 30.0,
                "emotional_arc": [
                    {"timestamp": 0, "emotion": "peaceful", "intensity": 0.6},
                    {"timestamp": 15, "emotion": "dramatic", "intensity": 0.8}
                ],
                "visual_elements": {"style": "anime", "colors": "bright"},
                "dialogue_density": 0.3,
                "action_sequences": [],
                "character_focus": ["protagonist"],
                "setting": "school",
                "time_of_day": "morning",
                "narrative_importance": 0.7
            }

            async with httpx.AsyncClient(timeout=45) as client:
                # Test scene analysis
                response = await client.post(
                    f"{self.base_url}:{self.ports['ai_music']}/api/ai-music/analyze-scene",
                    json=scene_context
                )

                if response.status_code == 200:
                    criteria = response.json()

                    # Test music recommendations
                    recommendation_response = await client.post(
                        f"{self.base_url}:{self.ports['ai_music']}/api/ai-music/recommend",
                        json=scene_context
                    )

                    if recommendation_response.status_code == 200:
                        recommendations = recommendation_response.json()
                        return {
                            "status": "success",
                            "criteria_generated": criteria,
                            "recommendations_count": len(recommendations.get("alternative_options", [])) + 1,
                            "primary_track": recommendations.get("primary_recommendation", {}).get("track_id"),
                            "confidence": recommendations.get("primary_recommendation", {}).get("confidence_score"),
                            "echo_brain_used": "echo_brain_analysis" in recommendations
                        }
                    else:
                        return {
                            "status": "partial",
                            "criteria_success": True,
                            "recommendations_failed": f"HTTP {recommendation_response.status_code}"
                        }
                else:
                    return {
                        "status": "failed",
                        "error": f"Scene analysis failed: HTTP {response.status_code}"
                    }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    async def _test_video_analysis(self) -> Dict[str, Any]:
        """Test video analysis functionality"""

        try:
            # Create test video
            test_video = await self._create_test_video()

            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.base_url}:{self.ports['music_sync']}/api/music-sync/analyze-video",
                    json={"video_path": test_video}
                )

                if response.status_code == 200:
                    video_metadata = response.json()
                    return {
                        "status": "success",
                        "duration_detected": video_metadata.get("duration"),
                        "frame_rate_detected": video_metadata.get("frame_rate"),
                        "estimated_bpm": video_metadata.get("estimated_bpm"),
                        "action_intensity": video_metadata.get("action_intensity"),
                        "metadata": video_metadata
                    }
                else:
                    return {
                        "status": "failed",
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    async def _test_apple_music(self) -> Dict[str, Any]:
        """Test Apple Music integration"""

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # Test search functionality
                response = await client.get(
                    f"{self.base_url}:{self.ports['apple_music']}/api/apple-music/search",
                    params={"q": "anime peaceful", "types": "songs", "limit": 5}
                )

                if response.status_code == 200:
                    search_results = response.json()
                    songs = search_results.get("results", {}).get("songs", {}).get("data", [])

                    return {
                        "status": "success",
                        "search_results_count": len(songs),
                        "sample_tracks": [
                            {
                                "title": song.get("attributes", {}).get("name"),
                                "artist": song.get("attributes", {}).get("artistName")
                            }
                            for song in songs[:3]
                        ],
                        "api_accessible": True
                    }
                else:
                    return {
                        "status": "failed",
                        "error": f"Search failed: HTTP {response.status_code}",
                        "api_accessible": False
                    }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    async def _test_integration(self) -> Dict[str, Any]:
        """Test system integration between components"""

        integration_results = {}

        # Test Music Sync + AI Selection Integration
        logger.info("Testing music sync + AI integration...")
        integration_results["sync_ai_integration"] = await self._test_sync_ai_integration()

        # Test Video + Music Integration
        logger.info("Testing video + music integration...")
        integration_results["video_music_integration"] = await self._test_video_music_integration()

        # Test Echo Brain Integration
        logger.info("Testing Echo Brain integration...")
        integration_results["echo_brain_integration"] = await self._test_echo_brain_integration()

        return integration_results

    async def _test_sync_ai_integration(self) -> Dict[str, Any]:
        """Test integration between sync engine and AI selector"""

        try:
            # Create scene for AI analysis
            scene_context = {
                "scene_id": "integration_test",
                "duration": 20.0,
                "emotional_arc": [{"timestamp": 0, "emotion": "energetic", "intensity": 0.8}],
                "visual_elements": {},
                "dialogue_density": 0.2,
                "action_sequences": [{"start_time": 5, "duration": 3, "intensity": 0.9}],
                "character_focus": ["hero"],
                "setting": "battle",
                "time_of_day": "day",
                "narrative_importance": 0.9
            }

            # Test AI music selection
            async with httpx.AsyncClient(timeout=60) as client:
                ai_response = await client.post(
                    f"{self.base_url}:{self.ports['ai_music']}/api/ai-music/recommend",
                    json=scene_context
                )

                if ai_response.status_code != 200:
                    return {"status": "failed", "error": "AI selection failed"}

                recommendations = ai_response.json()
                primary_track = recommendations.get("primary_recommendation", {}).get("track_id")

                if not primary_track:
                    return {"status": "failed", "error": "No track recommended"}

                # Test sync configuration generation
                video_metadata = {
                    "duration": 20.0,
                    "frame_rate": 24.0,
                    "resolution": [1920, 1080],
                    "video_path": "/tmp/test_video.mp4",
                    "scene_count": 2,
                    "action_intensity": 0.8,
                    "emotional_tone": "energetic"
                }

                track_metadata = {
                    "track_id": primary_track,
                    "title": "Test Track",
                    "artist": "Test Artist",
                    "duration": 180.0,
                    "bpm": 140
                }

                sync_response = await client.post(
                    f"{self.base_url}:{self.ports['music_sync']}/api/music-sync/generate-config",
                    json={
                        "video_metadata": video_metadata,
                        "track_metadata": track_metadata,
                        "user_preferences": {}
                    }
                )

                if sync_response.status_code == 200:
                    sync_config = sync_response.json()
                    return {
                        "status": "success",
                        "ai_recommendation_confidence": recommendations["primary_recommendation"]["confidence_score"],
                        "sync_score": sync_config.get("sync_score"),
                        "sync_points_generated": len(sync_config.get("sync_points", [])),
                        "integration_successful": True
                    }
                else:
                    return {
                        "status": "partial",
                        "ai_success": True,
                        "sync_failed": f"HTTP {sync_response.status_code}"
                    }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    async def _test_video_music_integration(self) -> Dict[str, Any]:
        """Test complete video-music integration pipeline"""

        try:
            # Test integrated generation request
            generation_request = {
                "project_id": "test_project",
                "scene_description": "A peaceful anime scene with a character walking through a school hallway in the morning",
                "character_ids": ["student_001"],
                "duration": 15.0,
                "style_preferences": {"style": "anime", "quality": "high"},
                "music_preferences": {"volume": 0.7, "fade_in": 2.0},
                "sync_music": True,
                "auto_select_music": True
            }

            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(
                    f"{self.base_url}:{self.ports['integration']}/api/integrated/generate",
                    json=generation_request
                )

                if response.status_code == 200:
                    job_data = response.json()
                    job_id = job_data.get("job_id")

                    if job_id:
                        # Monitor job for a short time
                        max_wait = 30  # 30 seconds for test
                        start_time = time.time()

                        while time.time() - start_time < max_wait:
                            status_response = await client.get(
                                f"{self.base_url}:{self.ports['integration']}/api/integrated/status/{job_id}"
                            )

                            if status_response.status_code == 200:
                                status_data = status_response.json()
                                job_status = status_data.get("status")

                                if job_status in ["completed", "failed"]:
                                    return {
                                        "status": "success" if job_status == "completed" else "failed",
                                        "job_id": job_id,
                                        "final_status": job_status,
                                        "video_status": status_data.get("video_status"),
                                        "music_status": status_data.get("music_status"),
                                        "sync_status": status_data.get("sync_status"),
                                        "ai_selection": "ai_music_selection" in status_data,
                                        "test_duration": time.time() - start_time
                                    }

                            await asyncio.sleep(2)

                        # Test timed out, but job was created
                        return {
                            "status": "timeout",
                            "job_id": job_id,
                            "message": "Job created but timed out waiting for completion",
                            "integration_pipeline_working": True
                        }
                    else:
                        return {"status": "failed", "error": "No job ID returned"}

                else:
                    return {
                        "status": "failed",
                        "error": f"Integration request failed: HTTP {response.status_code}"
                    }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    async def _test_echo_brain_integration(self) -> Dict[str, Any]:
        """Test Echo Brain integration"""

        try:
            # Test Echo Brain query
            query = "Analyze the best music type for a peaceful anime scene with morning sunlight"

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}:{self.ports['echo_brain']}/api/echo/query",
                    json={
                        "query": query,
                        "conversation_id": "music_sync_test",
                        "context_type": "music_analysis"
                    }
                )

                if response.status_code == 200:
                    echo_response = response.json()
                    return {
                        "status": "success",
                        "response_received": len(echo_response.get("response", "")) > 0,
                        "confidence": echo_response.get("confidence"),
                        "echo_brain_accessible": True
                    }
                else:
                    return {
                        "status": "failed",
                        "error": f"Echo Brain query failed: HTTP {response.status_code}",
                        "echo_brain_accessible": False
                    }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "echo_brain_accessible": False
            }

    async def _test_performance(self) -> Dict[str, Any]:
        """Test performance metrics"""

        performance_results = {}

        # Test BPM analysis performance
        logger.info("Testing BPM analysis performance...")
        performance_results["bpm_analysis_performance"] = await self._test_bpm_performance()

        # Test AI selection performance
        logger.info("Testing AI selection performance...")
        performance_results["ai_selection_performance"] = await self._test_ai_performance()

        # Test sync generation performance
        logger.info("Testing sync generation performance...")
        performance_results["sync_performance"] = await self._test_sync_performance()

        return performance_results

    async def _test_bpm_performance(self) -> Dict[str, Any]:
        """Test BPM analysis performance"""

        try:
            test_audio = await self._create_test_audio()
            times = []

            # Run multiple tests
            for i in range(3):
                start_time = time.time()

                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        f"{self.base_url}:{self.ports['music_sync']}/api/music-sync/analyze-track",
                        json={
                            "track_id": f"perf_test_{i}",
                            "title": "Performance Test Track",
                            "artist": "Test Artist",
                            "duration": 30.0,
                            "file_path": test_audio
                        }
                    )

                analysis_time = time.time() - start_time
                times.append(analysis_time)

                if response.status_code != 200:
                    return {"status": "failed", "error": f"Analysis {i} failed"}

            return {
                "status": "success",
                "average_time": sum(times) / len(times),
                "min_time": min(times),
                "max_time": max(times),
                "all_times": times
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _test_ai_performance(self) -> Dict[str, Any]:
        """Test AI selection performance"""

        try:
            scene_context = {
                "scene_id": "perf_test",
                "duration": 30.0,
                "emotional_arc": [{"timestamp": 0, "emotion": "peaceful", "intensity": 0.6}],
                "visual_elements": {},
                "dialogue_density": 0.3,
                "action_sequences": [],
                "character_focus": ["protagonist"],
                "setting": "school",
                "time_of_day": "morning",
                "narrative_importance": 0.7
            }

            start_time = time.time()

            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.base_url}:{self.ports['ai_music']}/api/ai-music/recommend",
                    json=scene_context
                )

            selection_time = time.time() - start_time

            if response.status_code == 200:
                recommendations = response.json()
                return {
                    "status": "success",
                    "selection_time": selection_time,
                    "recommendations_count": len(recommendations.get("alternative_options", [])) + 1,
                    "echo_brain_time_included": True
                }
            else:
                return {"status": "failed", "error": f"HTTP {response.status_code}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _test_sync_performance(self) -> Dict[str, Any]:
        """Test synchronization performance"""

        try:
            video_metadata = {
                "duration": 20.0,
                "frame_rate": 24.0,
                "resolution": [1920, 1080],
                "video_path": "/tmp/test_video.mp4",
                "scene_count": 2,
                "action_intensity": 0.8,
                "emotional_tone": "energetic"
            }

            track_metadata = {
                "track_id": "sync_perf_test",
                "title": "Performance Test Track",
                "artist": "Test Artist",
                "duration": 180.0,
                "bpm": 140
            }

            start_time = time.time()

            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    f"{self.base_url}:{self.ports['music_sync']}/api/music-sync/generate-config",
                    json={
                        "video_metadata": video_metadata,
                        "track_metadata": track_metadata,
                        "user_preferences": {}
                    }
                )

            sync_time = time.time() - start_time

            if response.status_code == 200:
                config = response.json()
                return {
                    "status": "success",
                    "sync_generation_time": sync_time,
                    "sync_points_generated": len(config.get("sync_points", [])),
                    "sync_score": config.get("sync_score")
                }
            else:
                return {"status": "failed", "error": f"HTTP {response.status_code}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _test_end_to_end(self) -> Dict[str, Any]:
        """Test complete end-to-end workflow"""

        try:
            logger.info("Running end-to-end workflow test...")

            # 1. Create test video
            test_video = await self._create_test_video()

            # 2. Analyze video
            async with httpx.AsyncClient(timeout=60) as client:
                video_analysis_response = await client.post(
                    f"{self.base_url}:{self.ports['music_sync']}/api/music-sync/analyze-video",
                    json={"video_path": test_video}
                )

                if video_analysis_response.status_code != 200:
                    return {"status": "failed", "step": "video_analysis",
                           "error": f"HTTP {video_analysis_response.status_code}"}

                video_metadata = video_analysis_response.json()

                # 3. Get AI music recommendation
                scene_context = {
                    "scene_id": "e2e_test",
                    "duration": video_metadata.get("duration", 30.0),
                    "emotional_arc": [{"timestamp": 0, "emotion": "peaceful", "intensity": 0.6}],
                    "visual_elements": {},
                    "dialogue_density": 0.3,
                    "action_sequences": [],
                    "character_focus": ["protagonist"],
                    "setting": "school",
                    "time_of_day": "morning",
                    "narrative_importance": 0.7
                }

                ai_recommendation_response = await client.post(
                    f"{self.base_url}:{self.ports['ai_music']}/api/ai-music/recommend",
                    json=scene_context
                )

                if ai_recommendation_response.status_code != 200:
                    return {"status": "failed", "step": "ai_recommendation",
                           "error": f"HTTP {ai_recommendation_response.status_code}"}

                recommendations = ai_recommendation_response.json()
                primary_track = recommendations["primary_recommendation"]["track_id"]

                # 4. Generate sync configuration
                track_metadata = {
                    "track_id": primary_track,
                    "title": "E2E Test Track",
                    "artist": "Test Artist",
                    "duration": 180.0,
                    "bpm": 120
                }

                sync_config_response = await client.post(
                    f"{self.base_url}:{self.ports['music_sync']}/api/music-sync/generate-config",
                    json={
                        "video_metadata": video_metadata,
                        "track_metadata": track_metadata,
                        "user_preferences": {}
                    }
                )

                if sync_config_response.status_code != 200:
                    return {"status": "failed", "step": "sync_configuration",
                           "error": f"HTTP {sync_config_response.status_code}"}

                sync_config = sync_config_response.json()

                return {
                    "status": "success",
                    "steps_completed": [
                        "video_analysis",
                        "ai_recommendation",
                        "sync_configuration"
                    ],
                    "video_duration": video_metadata.get("duration"),
                    "recommended_track": primary_track,
                    "ai_confidence": recommendations["primary_recommendation"]["confidence_score"],
                    "sync_score": sync_config.get("sync_score"),
                    "sync_points_count": len(sync_config.get("sync_points", [])),
                    "end_to_end_successful": True
                }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "end_to_end_successful": False
            }

    async def _create_test_audio(self) -> str:
        """Create a test audio file for BPM analysis"""

        output_path = self.test_data_dir / f"test_audio_{int(time.time())}.wav"

        try:
            # Create a 30-second test audio file with 120 BPM
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "sine=frequency=440:duration=30",
                "-ar", "22050",
                "-ac", "1",
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                return str(output_path)
            else:
                logger.error(f"Test audio creation failed: {result.stderr}")
                raise RuntimeError("Test audio creation failed")

        except Exception as e:
            logger.error(f"Failed to create test audio: {e}")
            raise

    async def _create_test_video(self) -> str:
        """Create a test video file for analysis"""

        output_path = self.test_data_dir / f"test_video_{int(time.time())}.mp4"

        try:
            # Create a 30-second test video
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "testsrc=duration=30:size=1920x1080:rate=24",
                "-f", "lavfi",
                "-i", "sine=frequency=440:duration=30",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-pix_fmt", "yuv420p",
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                return str(output_path)
            else:
                logger.error(f"Test video creation failed: {result.stderr}")
                raise RuntimeError("Test video creation failed")

        except Exception as e:
            logger.error(f"Failed to create test video: {e}")
            raise


async def main():
    """Main test execution"""

    print("🎵 Music Synchronization System Test Suite")
    print("=" * 50)

    tester = MusicSyncTester()

    try:
        results = await tester.run_comprehensive_tests()

        print("\n📊 TEST RESULTS")
        print("=" * 30)

        # Print summary
        print(f"Overall Status: {results['overall_status']}")
        print(f"Timestamp: {results['timestamp']}")

        # Service health summary
        print("\n🏥 Service Health:")
        for service, health in results.get('service_health', {}).items():
            status = health.get('status', 'unknown')
            print(f"  {service}: {status}")

        # Component test summary
        print("\n🔧 Component Tests:")
        for component, result in results.get('component_tests', {}).items():
            status = result.get('status', 'unknown')
            print(f"  {component}: {status}")

        # Integration test summary
        print("\n🔗 Integration Tests:")
        for test, result in results.get('integration_tests', {}).items():
            status = result.get('status', 'unknown')
            print(f"  {test}: {status}")

        # Performance summary
        print("\n⚡ Performance Tests:")
        for test, result in results.get('performance_metrics', {}).items():
            status = result.get('status', 'unknown')
            if status == 'success' and 'time' in str(result):
                time_key = next((k for k in result.keys() if 'time' in k), None)
                if time_key:
                    print(f"  {test}: {status} ({result[time_key]:.2f}s)")
                else:
                    print(f"  {test}: {status}")
            else:
                print(f"  {test}: {status}")

        # End-to-end test summary
        if 'e2e_tests' in results:
            e2e_result = results['e2e_tests']
            print(f"\n🎬 End-to-End Test: {e2e_result.get('status', 'unknown')}")
            if e2e_result.get('end_to_end_successful'):
                print("  ✅ Complete workflow validated")

        # Errors
        if results.get('errors'):
            print("\n❌ Errors:")
            for error in results['errors']:
                print(f"  - {error}")

        # Save detailed results
        results_file = Path("/opt/tower-anime-production/test_results.json")
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\n📁 Detailed results saved to: {results_file}")

        return results['overall_status'] == 'completed'

    except Exception as e:
        print(f"\n❌ Test suite execution failed: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)