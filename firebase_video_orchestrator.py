#!/usr/bin/env python3
"""
Firebase Video Orchestrator
Hybrid local/Firebase system for scalable video generation
"""

import asyncio
import aiohttp
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import os
from pathlib import Path
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FirebaseVideoOrchestrator:
    """Orchestrates video generation between local Tower and Firebase Cloud"""

    def __init__(self):
        self.firebase_project_id = "tower-echo-brain"
        self.firebase_base_url = f"https://us-central1-{self.firebase_project_id}.cloudfunctions.net"
        self.local_comfyui_url = "http://127.0.0.1:8188"
        self.echo_brain_url = "http://127.0.0.1:8309"
        self.apple_music_url = "http://127.0.0.1:8315"

        # Budget controls
        self.daily_budget = 5.00  # $5 per day
        self.monthly_budget = 50.00  # $50 per month

        # Duration thresholds
        self.local_max_duration = 10  # seconds
        self.firebase_min_duration = 11  # seconds

    async def generate_video(self,
                           prompt: str,
                           duration_seconds: int,
                           style: str = "anime",
                           quality: str = "standard",
                           use_apple_music: bool = True) -> Dict[str, Any]:
        """
        Main video generation entry point
        Routes to local or Firebase based on duration and constraints
        """

        logger.info(f"🎬 Video generation request: {duration_seconds}s - {prompt}")

        # Step 1: Get BPM analysis from Echo Brain
        bpm_analysis = await self.get_bpm_analysis(prompt, duration_seconds)

        # Step 2: Get Apple Music recommendations if requested
        apple_music_track = None
        if use_apple_music and bpm_analysis:
            apple_music_track = await self.get_apple_music_recommendation(bpm_analysis)

        # Step 3: Route to appropriate generation method
        if duration_seconds <= self.local_max_duration:
            return await self.generate_local(prompt, duration_seconds, style, bpm_analysis, apple_music_track)
        else:
            # Check budget first for Firebase generation
            budget_ok = await self.check_budget_constraint(duration_seconds, quality)
            if not budget_ok:
                return {
                    "success": False,
                    "error": "Budget constraint exceeded",
                    "suggestion": "Use local generation or increase budget"
                }

            return await self.generate_firebase(prompt, duration_seconds, style, quality, bpm_analysis, apple_music_track)

    async def get_bpm_analysis(self, prompt: str, duration: int) -> Optional[Dict]:
        """Get BPM analysis from Echo Brain"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "video_prompt": prompt,
                    "duration_seconds": duration
                }

                async with session.post(
                    f"{self.echo_brain_url}/api/echo/soundtrack/analyze-video-bpm",
                    json=payload,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"🧠 Echo BPM analysis: {data.get('recommended_bpm', 'unknown')} BPM")
                        return data
                    else:
                        logger.warning(f"Echo BPM analysis failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"BPM analysis error: {e}")
            return None

    async def get_apple_music_recommendation(self, bpm_analysis: Dict) -> Optional[Dict]:
        """Get Apple Music track recommendation based on BPM analysis"""
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "q": f"anime soundtrack {bpm_analysis.get('emotional_tone', 'cinematic')}",
                    "mood": bpm_analysis.get('emotional_tone', 'cinematic'),
                    "limit": 5
                }

                async with session.get(
                    f"{self.apple_music_url}/api/search",
                    params=params,
                    timeout=15
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        tracks = data.get('results', [])
                        if tracks:
                            selected_track = tracks[0]  # Use first result for now
                            logger.info(f"🎵 Selected Apple Music track: {selected_track.get('name', 'Unknown')}")
                            return selected_track
                    return None
        except Exception as e:
            logger.error(f"Apple Music recommendation error: {e}")
            return None

    async def generate_local(self, prompt: str, duration: int, style: str,
                           bpm_analysis: Dict, apple_music_track: Dict) -> Dict[str, Any]:
        """Generate video locally using existing ComfyUI system"""
        logger.info(f"🏠 Using local generation for {duration}s video")

        start_time = time.time()

        try:
            # Use existing local generation system
            async with aiohttp.ClientSession() as session:
                payload = {
                    "prompt": prompt,
                    "duration": duration,
                    "frames": duration * 24,  # 24fps
                    "use_apple_music": apple_music_track is not None
                }

                async with session.post(
                    f"{self.local_comfyui_url.replace('8188', '8328')}/api/generate",
                    json=payload,
                    timeout=7200  # 2 hours max for local
                ) as response:
                    if response.status == 200:
                        data = await response.json()

                        processing_time = time.time() - start_time

                        return {
                            "success": True,
                            "generation_id": data.get("generation_id"),
                            "compute_location": "local",
                            "processing_time_seconds": round(processing_time, 2),
                            "estimated_cost_usd": 0.0,  # Local is free
                            "video_specs": {
                                "duration_seconds": duration,
                                "style": style,
                                "frames": duration * 24
                            },
                            "bpm_analysis": bpm_analysis,
                            "apple_music_track": apple_music_track,
                            "check_status_url": f"/api/status/{data.get('generation_id')}"
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"Local generation failed: {response.status}",
                            "compute_location": "local"
                        }

        except Exception as e:
            logger.error(f"Local generation error: {e}")
            return {
                "success": False,
                "error": str(e),
                "compute_location": "local"
            }

    async def check_budget_constraint(self, duration: int, quality: str) -> bool:
        """Check if Firebase generation is within budget"""
        try:
            async with aiohttp.ClientSession() as session:
                # Get cost estimate
                async with session.post(
                    f"{self.firebase_base_url}/getCostEstimate",
                    json={
                        "data": {
                            "duration_seconds": duration,
                            "quality": quality
                        }
                    },
                    timeout=10
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        estimated_cost = data.get("result", {}).get("estimated_cost_usd", 0)

                        # Check current budget status
                        async with session.post(
                            f"{self.firebase_base_url}/checkBudget",
                            json={
                                "data": {
                                    "daily_budget": self.daily_budget,
                                    "monthly_budget": self.monthly_budget
                                }
                            },
                            timeout=10
                        ) as budget_response:
                            if budget_response.status == 200:
                                budget_data = await budget_response.json()
                                budget_status = budget_data.get("result", {})

                                daily_remaining = budget_status.get("daily", {}).get("remaining", 0)
                                monthly_remaining = budget_status.get("monthly", {}).get("remaining", 0)

                                if estimated_cost <= daily_remaining and estimated_cost <= monthly_remaining:
                                    logger.info(f"💰 Budget OK: ${estimated_cost:.4f} (Daily: ${daily_remaining:.2f}, Monthly: ${monthly_remaining:.2f})")
                                    return True
                                else:
                                    logger.warning(f"💸 Budget exceeded: ${estimated_cost:.4f} > ${min(daily_remaining, monthly_remaining):.4f}")
                                    return False

            return False  # Default to reject if checks fail
        except Exception as e:
            logger.error(f"Budget check error: {e}")
            return False

    async def generate_firebase(self, prompt: str, duration: int, style: str, quality: str,
                              bpm_analysis: Dict, apple_music_track: Dict) -> Dict[str, Any]:
        """Generate video using Firebase Cloud Functions"""
        logger.info(f"☁️ Using Firebase generation for {duration}s video")

        start_time = time.time()

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "data": {
                        "video_prompt": prompt,
                        "duration_seconds": duration,
                        "style": style,
                        "resolution": "1024x576",
                        "bpm_analysis": bpm_analysis,
                        "apple_music_track": apple_music_track
                    }
                }

                async with session.post(
                    f"{self.firebase_base_url}/generateLongVideo",
                    json=payload,
                    timeout=600  # 10 minutes for orchestration
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data.get("result", {})

                        processing_time = time.time() - start_time

                        # Firebase returns segment-based results
                        if result.get("success"):
                            return {
                                "success": True,
                                "generation_id": result.get("generation_id"),
                                "compute_location": "firebase",
                                "processing_time_seconds": round(processing_time, 2),
                                "estimated_cost_usd": result.get("estimated_cost_usd", 0),
                                "segments": result.get("segments", []),
                                "total_segments": result.get("total_segments", 0),
                                "success_rate": result.get("success_rate", 0),
                                "video_specs": result.get("video_specs", {}),
                                "bpm_analysis": bpm_analysis,
                                "apple_music_track": apple_music_track,
                                "next_steps": result.get("next_steps", ""),
                                "message": result.get("message", "")
                            }
                        else:
                            return {
                                "success": False,
                                "error": result.get("message", "Firebase generation failed"),
                                "compute_location": "firebase",
                                "segments": result.get("segments", []),
                                "failed_segments": result.get("failed_segment_details", [])
                            }
                    else:
                        return {
                            "success": False,
                            "error": f"Firebase API error: {response.status}",
                            "compute_location": "firebase"
                        }

        except Exception as e:
            logger.error(f"Firebase generation error: {e}")
            return {
                "success": False,
                "error": str(e),
                "compute_location": "firebase"
            }

    async def get_budget_status(self) -> Dict[str, Any]:
        """Get current budget status"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.firebase_base_url}/checkBudget",
                    json={
                        "data": {
                            "daily_budget": self.daily_budget,
                            "monthly_budget": self.monthly_budget
                        }
                    },
                    timeout=10
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("result", {})
                    else:
                        return {"error": f"Budget check failed: {response.status}"}
        except Exception as e:
            return {"error": str(e)}

    async def get_cost_estimate(self, duration: int, quality: str = "standard") -> Dict[str, Any]:
        """Get cost estimate for video generation"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.firebase_base_url}/getCostEstimate",
                    json={
                        "data": {
                            "duration_seconds": duration,
                            "quality": quality
                        }
                    },
                    timeout=10
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("result", {})
                    else:
                        return {"error": f"Cost estimate failed: {response.status}"}
        except Exception as e:
            return {"error": str(e)}

# Example usage
async def main():
    orchestrator = FirebaseVideoOrchestrator()

    # Test short video (local)
    print("🎬 Testing 5-second video (local generation)...")
    result1 = await orchestrator.generate_video(
        prompt="Cyberpunk warrior in neon city",
        duration_seconds=5,
        style="anime"
    )
    print(f"Result: {json.dumps(result1, indent=2)}")

    # Test budget status
    print("\n💰 Checking budget status...")
    budget = await orchestrator.get_budget_status()
    print(f"Budget: {json.dumps(budget, indent=2)}")

    # Test cost estimate for long video
    print("\n💸 Getting cost estimate for 60s video...")
    estimate = await orchestrator.get_cost_estimate(60, "standard")
    print(f"Estimate: {json.dumps(estimate, indent=2)}")

if __name__ == "__main__":
    asyncio.run(main())