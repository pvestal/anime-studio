#!/usr/bin/env python3
"""
Test Complete Anime Production Workflow
Tests the orchestrator with ComfyUI integration, BPM analysis, and Apple Music
"""

import asyncio
import json
from firebase_video_orchestrator import FirebaseVideoOrchestrator

async def test_complete_workflow():
    """Test the complete video generation workflow"""
    print("🎬 Testing Complete Anime Production Workflow")
    print("=" * 60)

    # Initialize orchestrator
    orchestrator = FirebaseVideoOrchestrator()

    # Test cases
    test_cases = [
        {
            "prompt": "magical girl transformation with sparkles and rainbow colors",
            "duration_seconds": 5,
            "style": "anime",
            "quality": "standard"
        },
        {
            "prompt": "peaceful cherry blossom garden in spring",
            "duration_seconds": 3,
            "style": "anime",
            "quality": "standard"
        }
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🧪 Test Case {i}: {test_case['prompt'][:50]}...")
        print("-" * 40)

        try:
            # Call the orchestrator
            result = await orchestrator.generate_video(**test_case)

            print(f"✅ Generation Result:")
            print(f"   Success: {result.get('success', False)}")
            print(f"   Compute Location: {result.get('compute_location', 'unknown')}")
            print(f"   Processing Time: {result.get('processing_time_seconds', 0)}s")

            if result.get('bpm_analysis'):
                bpm_data = result['bpm_analysis']
                print(f"   BPM Analysis: {bpm_data.get('recommended_bpm', 'N/A')} BPM")
                print(f"   Emotional Tone: {bpm_data.get('emotional_tone', 'N/A')}")
                print(f"   Analysis Method: {bpm_data.get('analysis_method', 'N/A')}")

            if result.get('apple_music_track'):
                print(f"   Apple Music: Track recommended")
            else:
                print(f"   Apple Music: No recommendation")

            if result.get('output_path'):
                print(f"   Output: {result['output_path']}")

            if not result.get('success'):
                print(f"   Error: {result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"❌ Test failed: {e}")

    print(f"\n🏁 Workflow testing complete!")

if __name__ == "__main__":
    asyncio.run(test_complete_workflow())