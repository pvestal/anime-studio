#!/usr/bin/env python3
"""
Advanced test suite for working anime API
Tests project-specific styles, regeneration consistency, edge cases
"""

import requests
import json
import time
import hashlib
from pathlib import Path
from PIL import Image
import io

API_BASE = "http://localhost:49999"

def test_project_specific_styles():
    """Test different anime styles for project consistency"""

    print("🎨 TESTING PROJECT-SPECIFIC STYLES")
    print("-" * 50)

    styles = [
        {
            "name": "Studio Ghibli Style",
            "prompt": "anime girl, studio ghibli style, soft colors, nature background",
            "expected_characteristics": ["soft", "nature", "ghibli"]
        },
        {
            "name": "Dark Anime Style",
            "prompt": "anime warrior, dark fantasy style, dramatic lighting, gothic",
            "expected_characteristics": ["dark", "dramatic", "gothic"]
        },
        {
            "name": "Cute Chibi Style",
            "prompt": "anime chibi cat girl, cute kawaii style, pastel colors",
            "expected_characteristics": ["chibi", "cute", "pastel"]
        }
    ]

    results = []

    for style in styles:
        print(f"\n📝 Testing {style['name']}...")

        # Submit generation
        response = requests.post(f"{API_BASE}/generate", json={
            "prompt": style["prompt"],
            "negative_prompt": "bad quality, deformed, blurry",
            "width": 512,
            "height": 768
        })

        if response.status_code != 200:
            print(f"❌ Failed to submit: {response.status_code}")
            continue

        job_data = response.json()
        job_id = job_data["job_id"]

        # Wait for completion
        start_time = time.time()
        while time.time() - start_time < 30:  # 30 second timeout
            job_response = requests.get(f"{API_BASE}/jobs/{job_id}")
            job = job_response.json()

            if job["status"] == "completed":
                print(f"✅ {style['name']}: {job['total_time']:.1f}s")

                # Check output file
                if job["output_path"] and Path(job["output_path"]).exists():
                    file_size = Path(job["output_path"]).stat().st_size
                    print(f"   📁 File: {file_size:,} bytes")

                    results.append({
                        "style": style["name"],
                        "time": job["total_time"],
                        "file_size": file_size,
                        "path": job["output_path"],
                        "success": True
                    })
                else:
                    print(f"❌ No output file found")
                    results.append({"style": style["name"], "success": False})
                break
            elif job["status"] == "failed":
                print(f"❌ {style['name']}: Generation failed - {job.get('error', 'unknown')}")
                results.append({"style": style["name"], "success": False, "error": job.get("error")})
                break

            time.sleep(2)
        else:
            print(f"⏰ {style['name']}: Timeout after 30 seconds")
            results.append({"style": style["name"], "success": False, "error": "timeout"})

    return results

def test_regeneration_consistency():
    """Test regenerating same prompt multiple times"""

    print("\n🔄 TESTING REGENERATION CONSISTENCY")
    print("-" * 50)

    base_prompt = "anime girl with blue hair, detailed face, school uniform"
    regenerations = []

    for i in range(3):
        print(f"\n🔄 Regeneration {i+1}/3...")

        response = requests.post(f"{API_BASE}/generate", json={
            "prompt": base_prompt,
            "negative_prompt": "bad quality, deformed",
            "width": 512,
            "height": 768
        })

        if response.status_code != 200:
            print(f"❌ Failed to submit regeneration {i+1}")
            continue

        job_data = response.json()
        job_id = job_data["job_id"]

        # Wait for completion
        start_time = time.time()
        while time.time() - start_time < 30:
            job_response = requests.get(f"{API_BASE}/jobs/{job_id}")
            job = job_response.json()

            if job["status"] == "completed":
                print(f"✅ Regeneration {i+1}: {job['total_time']:.1f}s")

                if job["output_path"] and Path(job["output_path"]).exists():
                    file_path = Path(job["output_path"])
                    file_size = file_path.stat().st_size

                    # Calculate file hash for uniqueness check
                    with open(file_path, 'rb') as f:
                        file_hash = hashlib.md5(f.read()).hexdigest()[:8]

                    regenerations.append({
                        "id": i+1,
                        "time": job["total_time"],
                        "file_size": file_size,
                        "file_hash": file_hash,
                        "path": str(file_path)
                    })

                    print(f"   📁 Size: {file_size:,} bytes, Hash: {file_hash}")
                break
            elif job["status"] == "failed":
                print(f"❌ Regeneration {i+1} failed: {job.get('error', 'unknown')}")
                break

            time.sleep(2)
        else:
            print(f"⏰ Regeneration {i+1}: Timeout")

    # Analyze consistency
    if len(regenerations) >= 2:
        times = [r["time"] for r in regenerations]
        sizes = [r["file_size"] for r in regenerations]
        hashes = [r["file_hash"] for r in regenerations]

        avg_time = sum(times) / len(times)
        time_variance = max(times) - min(times)
        size_variance = max(sizes) - min(sizes)
        unique_images = len(set(hashes))

        print(f"\n📊 CONSISTENCY ANALYSIS:")
        print(f"   ⏱️  Average time: {avg_time:.1f}s (variance: {time_variance:.1f}s)")
        print(f"   📁 Size variance: {size_variance:,} bytes")
        print(f"   🎲 Unique images: {unique_images}/{len(regenerations)}")

        if unique_images == len(regenerations):
            print("   ✅ All generations are unique (good randomization)")
        else:
            print("   ⚠️  Some duplicates found (check seed randomization)")

    return regenerations

def test_dimension_variations():
    """Test different image dimensions"""

    print("\n📐 TESTING DIMENSION VARIATIONS")
    print("-" * 50)

    dimensions = [
        {"width": 512, "height": 512, "name": "Square"},
        {"width": 768, "height": 512, "name": "Landscape"},
        {"width": 512, "height": 768, "name": "Portrait"},
        {"width": 1024, "height": 768, "name": "Large"},
    ]

    results = []

    for dim in dimensions:
        print(f"\n📏 Testing {dim['name']} ({dim['width']}x{dim['height']})...")

        response = requests.post(f"{API_BASE}/generate", json={
            "prompt": "anime landscape, detailed background",
            "width": dim["width"],
            "height": dim["height"]
        })

        if response.status_code != 200:
            print(f"❌ Failed to submit {dim['name']}")
            continue

        job_data = response.json()
        job_id = job_data["job_id"]

        # Wait for completion
        start_time = time.time()
        while time.time() - start_time < 45:  # Larger images may take longer
            job_response = requests.get(f"{API_BASE}/jobs/{job_id}")
            job = job_response.json()

            if job["status"] == "completed":
                if job["output_path"] and Path(job["output_path"]).exists():
                    # Verify actual image dimensions
                    try:
                        with Image.open(job["output_path"]) as img:
                            actual_width, actual_height = img.size

                        dimension_correct = (actual_width == dim["width"] and
                                           actual_height == dim["height"])

                        print(f"✅ {dim['name']}: {job['total_time']:.1f}s")
                        print(f"   📐 Expected: {dim['width']}x{dim['height']}")
                        print(f"   📐 Actual: {actual_width}x{actual_height}")
                        print(f"   {'✅' if dimension_correct else '❌'} Dimensions {'correct' if dimension_correct else 'incorrect'}")

                        results.append({
                            "name": dim["name"],
                            "expected": f"{dim['width']}x{dim['height']}",
                            "actual": f"{actual_width}x{actual_height}",
                            "correct": dimension_correct,
                            "time": job["total_time"],
                            "success": True
                        })

                    except Exception as e:
                        print(f"❌ Error checking image: {e}")
                        results.append({"name": dim["name"], "success": False, "error": str(e)})
                else:
                    print(f"❌ No output file")
                    results.append({"name": dim["name"], "success": False, "error": "no_file"})
                break
            elif job["status"] == "failed":
                print(f"❌ {dim['name']} failed: {job.get('error', 'unknown')}")
                results.append({"name": dim["name"], "success": False, "error": job.get("error")})
                break

            time.sleep(3)
        else:
            print(f"⏰ {dim['name']}: Timeout")
            results.append({"name": dim["name"], "success": False, "error": "timeout"})

    return results

def test_error_conditions():
    """Test various error conditions and edge cases"""

    print("\n🚨 TESTING ERROR CONDITIONS")
    print("-" * 50)

    error_tests = [
        {
            "name": "Empty prompt",
            "data": {"prompt": "", "negative_prompt": "bad quality"},
            "expected_error": True
        },
        {
            "name": "Extremely large dimensions",
            "data": {"prompt": "test", "width": 4096, "height": 4096},
            "expected_error": True
        },
        {
            "name": "Invalid dimensions",
            "data": {"prompt": "test", "width": 0, "height": 512},
            "expected_error": True
        },
        {
            "name": "Very long prompt",
            "data": {"prompt": "anime " * 200, "negative_prompt": "bad"},
            "expected_error": False  # Should handle long prompts
        }
    ]

    results = []

    for test in error_tests:
        print(f"\n🧪 Testing {test['name']}...")

        response = requests.post(f"{API_BASE}/generate", json=test["data"])

        if test["expected_error"]:
            if response.status_code != 200:
                print(f"✅ Correctly rejected with status {response.status_code}")
                results.append({"test": test["name"], "result": "correctly_rejected"})
            else:
                print(f"⚠️  Unexpectedly accepted - monitoring for failure...")
                job_data = response.json()
                job_id = job_data["job_id"]

                # Check if it fails during processing
                time.sleep(10)
                job_response = requests.get(f"{API_BASE}/jobs/{job_id}")
                job = job_response.json()

                if job["status"] == "failed":
                    print(f"✅ Failed during processing as expected")
                    results.append({"test": test["name"], "result": "failed_during_processing"})
                else:
                    print(f"❌ Unexpectedly succeeded")
                    results.append({"test": test["name"], "result": "unexpectedly_succeeded"})
        else:
            if response.status_code == 200:
                print(f"✅ Accepted as expected")
                results.append({"test": test["name"], "result": "correctly_accepted"})
            else:
                print(f"❌ Unexpectedly rejected with status {response.status_code}")
                results.append({"test": test["name"], "result": "unexpectedly_rejected"})

    return results

def main():
    """Run complete advanced test suite"""

    print("🧪 ADVANCED ANIME API TEST SUITE")
    print("=" * 70)

    # Check API is running
    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        if response.status_code != 200:
            print("❌ API not responding - start working_api.py first")
            return
        print("✅ API is running")
    except Exception as e:
        print(f"❌ Cannot connect to API: {e}")
        return

    # Run test suites
    style_results = test_project_specific_styles()
    regen_results = test_regeneration_consistency()
    dimension_results = test_dimension_variations()
    error_results = test_error_conditions()

    # Summary
    print("\n" + "=" * 70)
    print("📊 ADVANCED TEST SUITE SUMMARY")
    print("=" * 70)

    style_success = sum(1 for r in style_results if r.get("success", False))
    print(f"🎨 Style variations: {style_success}/{len(style_results)} successful")

    regen_success = len(regen_results)
    print(f"🔄 Regenerations: {regen_success}/3 successful")

    dim_success = sum(1 for r in dimension_results if r.get("success", False) and r.get("correct", False))
    print(f"📐 Dimension tests: {dim_success}/{len(dimension_results)} correct")

    error_correct = sum(1 for r in error_results if "correctly" in r.get("result", ""))
    print(f"🚨 Error handling: {error_correct}/{len(error_results)} handled correctly")

    total_tests = len(style_results) + 3 + len(dimension_results) + len(error_results)
    total_success = style_success + regen_success + dim_success + error_correct

    print(f"\n🎯 OVERALL: {total_success}/{total_tests} tests passed ({total_success/total_tests*100:.1f}%)")

    if total_success == total_tests:
        print("🏆 ALL ADVANCED TESTS PASSED - API is robust")
    elif total_success >= total_tests * 0.8:
        print("✅ GOOD performance - minor issues to address")
    else:
        print("⚠️  NEEDS IMPROVEMENT - significant issues found")

if __name__ == "__main__":
    main()