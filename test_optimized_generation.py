#!/usr/bin/env python3
"""
Test optimized generation speed
Compares draft mode vs standard generation
"""

import time
import requests
import json
from pathlib import Path

def test_draft_generation():
    """Test draft mode generation (target: <30 seconds)"""

    url = "http://localhost:8328/api/anime/orchestrate"

    # Use draft mode settings from optimized_workflows.py
    draft_request = {
        "prompt": "anime girl with blue hair, simple portrait",
        "type": "image",
        "mode": "draft",  # Would need to be implemented in API
        "width": 512,     # Smaller resolution for speed
        "height": 512,
        "steps": 8,       # Minimal steps
        "cfg_scale": 5.0, # Lower CFG for speed
        "sampler": "euler",  # Fast sampler
        "project_id": 1,
        "character_name": "test_character"
    }

    print("🚀 Starting DRAFT mode generation test...")
    print(f"Settings: {draft_request['width']}x{draft_request['height']}, {draft_request.get('steps', 20)} steps")

    start_time = time.time()

    try:
        response = requests.post(url, json=draft_request, timeout=120)
        response.raise_for_status()

        result = response.json()
        generation_time = time.time() - start_time

        print(f"✅ Draft generation completed in {generation_time:.2f} seconds")

        if result.get("success"):
            print(f"📁 Output: {result.get('output_path')}")

        # Check if we met the target
        if generation_time < 30:
            print("🎉 TARGET MET: Under 30 seconds!")
        elif generation_time < 60:
            print("⚡ Good: Under 1 minute")
        else:
            print(f"⚠️  Still slow: {generation_time:.2f} seconds")

        return generation_time, result

    except requests.exceptions.Timeout:
        print("❌ Request timed out after 120 seconds")
        return None, None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None

def test_standard_generation():
    """Test standard generation for comparison"""

    url = "http://localhost:8328/api/anime/orchestrate"

    # Current standard settings
    standard_request = {
        "prompt": "anime girl with blue hair, detailed portrait",
        "type": "image",
        "width": 1024,    # Current default
        "height": 1024,
        "project_id": 1,
        "character_name": "test_character"
    }

    print("\n📊 Starting STANDARD generation test...")
    print(f"Settings: {standard_request['width']}x{standard_request['height']}, default steps")

    start_time = time.time()

    try:
        response = requests.post(url, json=standard_request, timeout=600)
        response.raise_for_status()

        result = response.json()
        generation_time = time.time() - start_time

        print(f"✅ Standard generation completed in {generation_time:.2f} seconds")

        if result.get("success"):
            print(f"📁 Output: {result.get('output_path')}")

        return generation_time, result

    except requests.exceptions.Timeout:
        print("❌ Request timed out after 600 seconds")
        return None, None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None

def check_api_health():
    """Check if API is running"""
    try:
        response = requests.get("http://localhost:8328/api/anime/health", timeout=5)
        response.raise_for_status()
        health = response.json()

        print("🏥 API Health Check:")
        print(f"  Status: {health['status']}")
        print(f"  ComfyUI: {health['components']['comfyui']['status']}")
        print(f"  GPU Available: {health['components']['gpu']['available']}")
        print(f"  Active Jobs: {health['components']['jobs']['active_count']}")

        return health['components']['comfyui']['status'] == 'healthy'

    except Exception as e:
        print(f"❌ API health check failed: {e}")
        return False

def main():
    """Run performance tests"""

    print("=" * 60)
    print("🎯 ANIME GENERATION PERFORMANCE TEST")
    print("=" * 60)

    # Check API health first
    if not check_api_health():
        print("\n⚠️  API or ComfyUI not healthy. Please check services.")
        return

    print("\n" + "=" * 60)

    # Test draft mode
    draft_time, draft_result = test_draft_generation()

    # Only test standard if draft worked
    if draft_time is not None:
        standard_time, standard_result = test_standard_generation()

        # Compare results
        if standard_time:
            print("\n" + "=" * 60)
            print("📈 PERFORMANCE COMPARISON:")
            print(f"  Draft Mode:    {draft_time:.2f} seconds")
            print(f"  Standard Mode: {standard_time:.2f} seconds")

            speedup = standard_time / draft_time
            print(f"  Speedup:       {speedup:.1f}x faster")

            improvement = ((standard_time - draft_time) / standard_time) * 100
            print(f"  Improvement:   {improvement:.1f}% reduction in time")

    print("\n" + "=" * 60)
    print("✨ Test complete!")

if __name__ == "__main__":
    main()