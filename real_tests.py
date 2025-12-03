#!/usr/bin/env python3
"""
Real comprehensive tests - verify everything ACTUALLY works
"""

import time
import requests
import json
import asyncio
import websocket
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime

BASE_URL = "http://localhost:8328"

def test_generation_speed():
    """Test actual generation speed with preloaded models"""
    print("\n⚡ TESTING GENERATION SPEED (with preloaded models)...")

    times = []
    for i in range(3):
        start = time.time()

        # Create generation request
        response = requests.post(f"{BASE_URL}/generate",
            json={"prompt": f"speed test {i} - anime girl"})
        job = response.json()
        job_id = job.get("job_id")

        # Wait for completion
        max_wait = 60
        completed = False
        while max_wait > 0 and not completed:
            status_response = requests.get(f"{BASE_URL}/jobs/{job_id}")
            if status_response.status_code == 200:
                status = status_response.json()
                if status.get("status") == "completed":
                    elapsed = time.time() - start
                    times.append(elapsed)
                    print(f"  Generation {i+1}: {elapsed:.2f}s")
                    completed = True
                    break
            time.sleep(0.5)
            max_wait -= 0.5

        if not completed:
            print(f"  Generation {i+1}: TIMEOUT")

    if times:
        avg = sum(times) / len(times)
        print(f"  Average: {avg:.2f}s")
        print(f"  ✅ SPEED TEST: {'PASS' if avg < 10 else 'FAIL'}")
        return avg < 10
    return False

def test_true_concurrency():
    """Test if concurrent processing actually works"""
    print("\n🔄 TESTING TRUE CONCURRENT PROCESSING...")

    def make_request(index):
        start = time.time()
        response = requests.post(f"{BASE_URL}/generate",
            json={"prompt": f"concurrent test {index}"})
        job = response.json()
        job_id = job.get("job_id")

        # Wait for completion
        max_wait = 60
        while max_wait > 0:
            status = requests.get(f"{BASE_URL}/jobs/{job_id}").json()
            if status.get("status") == "completed":
                return {
                    "index": index,
                    "time": time.time() - start,
                    "job_id": job_id
                }
            time.sleep(0.5)
            max_wait -= 0.5

        return {"index": index, "time": 60, "failed": True}

    # Submit 5 concurrent requests
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(make_request, i) for i in range(5)]
        results = [f.result() for f in as_completed(futures)]

    results.sort(key=lambda x: x["index"])
    times = [r["time"] for r in results if "failed" not in r]

    # Check if processing is truly concurrent
    # If sequential, times would be 4s, 8s, 12s, 16s, 20s
    # If concurrent, all should be around 4-8s
    max_time = max(times) if times else 0
    avg_time = sum(times) / len(times) if times else 0

    print(f"  Times: {[f'{t:.1f}s' for t in times]}")
    print(f"  Max time: {max_time:.1f}s")
    print(f"  Average: {avg_time:.1f}s")

    is_concurrent = max_time < 20  # Should be much less than 20s if concurrent
    print(f"  ✅ CONCURRENCY: {'TRUE' if is_concurrent else 'FALSE (Sequential)'}")
    return is_concurrent

def test_project_and_character():
    """Test project and character management"""
    print("\n📁 TESTING PROJECT & CHARACTER MANAGEMENT...")

    # Create project
    project_response = requests.post(f"{BASE_URL}/api/anime/projects",
        json={
            "name": f"Test Project {int(time.time())}",
            "description": "Testing project features",
            "style": "fantasy"
        })

    if project_response.status_code != 200:
        print("  ❌ Failed to create project")
        return False

    project = project_response.json()
    project_id = project["id"]
    print(f"  ✅ Created project: {project_id}")

    # Create character
    char_response = requests.post(f"{BASE_URL}/api/anime/characters",
        json={
            "project_id": project_id,
            "name": "Test Character",
            "description": "A test character",
            "appearance": "blue hair, red eyes",
            "personality": "brave and kind",
            "backstory": "A hero from another world"
        })

    if char_response.status_code != 200:
        print("  ❌ Failed to create character")
        return False

    character = char_response.json()
    char_id = character["id"]
    print(f"  ✅ Created character: {char_id}")

    # Get character bible
    bible_response = requests.get(f"{BASE_URL}/api/anime/characters/{char_id}/bible")

    if bible_response.status_code != 200:
        print("  ❌ Failed to get character bible")
        return False

    bible = bible_response.json()
    print(f"  ✅ Retrieved character bible: {bible['bible']['name']}")

    # Generate with project/character
    gen_response = requests.post(f"{BASE_URL}/generate",
        json={
            "prompt": "test character in scene",
            "project_id": project_id,
            "character_id": char_id
        })

    if gen_response.status_code != 200:
        print("  ❌ Failed to generate with project/character")
        return False

    job = gen_response.json()
    print(f"  ✅ Generation queued with project/character: {job['job_id']}")

    # Check file organization
    time.sleep(10)  # Wait for generation

    project_dir = Path(f"/mnt/1TB-storage/anime/projects/{project_id}")
    if project_dir.exists():
        char_dir = project_dir / "characters" / char_id
        if char_dir.exists():
            files = list(char_dir.glob("*.png"))
            if files:
                print(f"  ✅ Files organized: {len(files)} files in {char_dir}")
                return True
            else:
                print(f"  ⚠️ Character directory exists but no files yet")
        else:
            print(f"  ❌ Character directory not created")
    else:
        print(f"  ❌ Project directory not created")

    return False

def test_websocket_progress():
    """Test WebSocket progress updates"""
    print("\n📡 TESTING WEBSOCKET PROGRESS...")

    # Create a generation
    response = requests.post(f"{BASE_URL}/generate",
        json={"prompt": "websocket test"})
    job = response.json()
    job_id = job.get("job_id")
    ws_url = job.get("websocket_url", "").replace("http://", "ws://")

    if not ws_url:
        print("  ❌ No WebSocket URL provided")
        return False

    print(f"  WebSocket URL: {ws_url}")

    try:
        # Connect to WebSocket
        ws = websocket.WebSocket()
        ws.settimeout(5)
        ws.connect(ws_url)
        print("  ✅ WebSocket connected")

        # Wait for updates
        updates_received = 0
        max_updates = 10

        while updates_received < max_updates:
            try:
                message = ws.recv()
                data = json.loads(message)
                print(f"  Update: status={data.get('status')}, progress={data.get('progress')}%")
                updates_received += 1

                if data.get("status") in ["completed", "failed"]:
                    break
            except websocket.WebSocketTimeoutException:
                break
            except Exception as e:
                print(f"  Error: {e}")
                break

        ws.close()

        if updates_received > 0:
            print(f"  ✅ Received {updates_received} progress updates")
            return True
        else:
            print("  ❌ No updates received")
            return False

    except Exception as e:
        print(f"  ❌ WebSocket error: {e}")
        return False

def test_style_presets():
    """Test style preset application"""
    print("\n🎨 TESTING STYLE PRESETS...")

    styles = ["cyberpunk", "fantasy", "manga", "studio_ghibli"]

    for style in styles:
        response = requests.post(f"{BASE_URL}/generate",
            json={
                "prompt": "anime character",
                "style_preset": style
            })

        if response.status_code == 200:
            job = response.json()
            print(f"  ✅ Style '{style}' accepted: job {job['job_id']}")
        else:
            print(f"  ❌ Style '{style}' failed")
            return False

    return True

def stress_test():
    """Stress test with many concurrent requests"""
    print("\n🔥 STRESS TESTING (10 concurrent)...")

    def make_request(i):
        try:
            start = time.time()
            response = requests.post(f"{BASE_URL}/generate",
                json={"prompt": f"stress test {i}"}, timeout=5)
            if response.status_code == 200:
                return {"success": True, "time": time.time() - start}
            else:
                return {"success": False, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # Submit 10 concurrent requests
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request, i) for i in range(10)]
        results = [f.result() for f in as_completed(futures)]

    successful = sum(1 for r in results if r.get("success"))
    avg_time = sum(r.get("time", 0) for r in results if r.get("success")) / max(successful, 1)

    print(f"  Successful: {successful}/10")
    print(f"  Average response time: {avg_time:.3f}s")
    print(f"  ✅ STRESS TEST: {'PASS' if successful >= 8 else 'FAIL'}")

    return successful >= 8

def run_all_tests():
    """Run all real tests"""
    print("=" * 60)
    print("🧪 REAL COMPREHENSIVE TESTING")
    print("=" * 60)

    results = {
        "Speed": test_generation_speed(),
        "Concurrency": test_true_concurrency(),
        "Project/Character": test_project_and_character(),
        "WebSocket": test_websocket_progress(),
        "Style Presets": test_style_presets(),
        "Stress Test": stress_test()
    }

    print("\n" + "=" * 60)
    print("📊 FINAL RESULTS")
    print("=" * 60)

    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test}: {status}")

    passed_count = sum(1 for p in results.values() if p)
    total_count = len(results)

    print(f"\nOverall: {passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED! System is working correctly.")
    else:
        print("\n⚠️ Some tests failed. Review and fix issues.")

    return results

if __name__ == "__main__":
    run_all_tests()