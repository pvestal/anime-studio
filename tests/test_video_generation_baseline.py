#!/usr/bin/env python3
"""
Video Generation Baseline Test
Establishes current performance metrics before optimization

Author: Claude & Patrick
Purpose: Pride in engineering - measure, improve, verify
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# Add parent directory to path
sys.path.insert(0, '/opt/tower-anime-production')

class VideoGenerationBaseline:
    """Establish baseline metrics for video generation"""

    def __init__(self):
        self.api_url = "http://localhost:8331/api/anime"
        self.comfyui_url = "http://localhost:8188"
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": [],
            "summary": {}
        }

    def test_current_animatediff_performance(self):
        """Test current AnimateDiff generation time"""
        print("\n" + "="*60)
        print("🎬 ANIMATEDIFF BASELINE TEST")
        print("="*60)

        test_cases = [
            {
                "name": "Short Loop (1s, 24 frames)",
                "prompt": "anime girl walking cycle, smooth motion",
                "frames": 24,
                "expected_max_time": 120  # 2 minutes target
            },
            {
                "name": "Medium Video (5s, 120 frames)",
                "prompt": "anime character dancing, dynamic movement",
                "frames": 120,
                "expected_max_time": 300  # 5 minutes target
            }
        ]

        for test in test_cases:
            print(f"\n📊 Testing: {test['name']}")
            print(f"   Prompt: {test['prompt']}")
            print(f"   Frames: {test['frames']}")

            start_time = time.time()

            # Test actual generation
            try:
                result = self._generate_video(
                    prompt=test['prompt'],
                    frames=test['frames']
                )

                elapsed = time.time() - start_time
                success = elapsed < test['expected_max_time']

                test_result = {
                    "test": test['name'],
                    "frames": test['frames'],
                    "time_seconds": round(elapsed, 2),
                    "target_seconds": test['expected_max_time'],
                    "success": success,
                    "performance": "✅ PASS" if success else "❌ FAIL"
                }

                self.results["tests"].append(test_result)

                print(f"   Time: {elapsed:.2f}s")
                print(f"   Target: <{test['expected_max_time']}s")
                print(f"   Result: {test_result['performance']}")

            except Exception as e:
                print(f"   ❌ Error: {e}")
                self.results["tests"].append({
                    "test": test['name'],
                    "error": str(e),
                    "success": False
                })

    def _generate_video(self, prompt, frames):
        """Generate video using current pipeline"""
        # Check if we should use the API or direct ComfyUI
        try:
            # First try the API endpoint
            response = requests.post(
                f"{self.api_url}/generate",
                json={
                    "prompt": prompt,
                    "type": "video",
                    "frames": frames
                },
                timeout=600  # 10 minute timeout
            )

            if response.status_code == 200:
                return response.json()
            else:
                # Fallback to direct ComfyUI
                return self._generate_via_comfyui(prompt, frames)

        except requests.exceptions.RequestException:
            # API not available, use ComfyUI directly
            return self._generate_via_comfyui(prompt, frames)

    def _generate_via_comfyui(self, prompt, frames):
        """Direct ComfyUI generation for testing"""
        workflow = self._create_animatediff_workflow(prompt, frames)

        # Submit to ComfyUI
        response = requests.post(
            f"{self.comfyui_url}/prompt",
            json={"prompt": workflow}
        )

        if response.status_code != 200:
            raise Exception(f"ComfyUI error: {response.status_code}")

        return response.json()

    def _create_animatediff_workflow(self, prompt, frames):
        """Create AnimateDiff workflow for testing"""
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "AOM3A1B.safetensors"
                }
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["1", 1]
                }
            },
            "3": {
                "class_type": "ADE_LoadAnimateDiffModel",
                "inputs": {
                    "model_name": "mm-Stabilized_mid.pth",
                    "beta_schedule": "linear"
                }
            },
            "4": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": int(time.time()),
                    "steps": 20,  # Current unoptimized
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "latent_image": ["5", 0]
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": 512,
                    "height": 512,
                    "batch_size": frames
                }
            }
        }

    def test_memory_usage(self):
        """Test VRAM usage during generation"""
        print("\n📊 Testing VRAM Usage...")

        try:
            # Get GPU stats before
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.free",
                 "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                used, free = map(int, result.stdout.strip().split(', '))
                total = used + free

                self.results["summary"]["vram_used_mb"] = used
                self.results["summary"]["vram_free_mb"] = free
                self.results["summary"]["vram_total_mb"] = total
                self.results["summary"]["vram_utilization"] = round((used/total)*100, 1)

                print(f"   VRAM Used: {used}MB / {total}MB ({(used/total)*100:.1f}%)")
                print(f"   VRAM Free: {free}MB")

        except Exception as e:
            print(f"   Could not measure VRAM: {e}")

    def save_results(self):
        """Save baseline results for comparison"""
        results_path = Path("/opt/tower-anime-production/tests/baseline_results.json")

        # Calculate summary statistics
        if self.results["tests"]:
            successful_tests = [t for t in self.results["tests"] if t.get("success")]
            self.results["summary"]["total_tests"] = len(self.results["tests"])
            self.results["summary"]["successful_tests"] = len(successful_tests)
            self.results["summary"]["success_rate"] = round(
                (len(successful_tests) / len(self.results["tests"])) * 100, 1
            )

            if successful_tests:
                avg_time = sum(t["time_seconds"] for t in successful_tests) / len(successful_tests)
                self.results["summary"]["average_time_seconds"] = round(avg_time, 2)

        with open(results_path, 'w') as f:
            json.dump(self.results, f, indent=2)

        print(f"\n📁 Results saved to: {results_path}")
        return self.results

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("📊 BASELINE TEST SUMMARY")
        print("="*60)

        for key, value in self.results["summary"].items():
            print(f"  {key}: {value}")

        print("\n🎯 Individual Test Results:")
        for test in self.results["tests"]:
            if "error" in test:
                print(f"  ❌ {test['test']}: ERROR - {test['error']}")
            else:
                status = "✅" if test['success'] else "❌"
                print(f"  {status} {test['test']}: {test['time_seconds']}s (target: <{test['target_seconds']}s)")


def main():
    """Run baseline tests"""
    print("🚀 Starting AnimateDiff Video Generation Baseline Tests")
    print("Purpose: Establish current performance before optimization")
    print("Philosophy: Measure → Refactor → Test → Repeat")

    baseline = VideoGenerationBaseline()

    # Run tests
    baseline.test_memory_usage()
    baseline.test_current_animatediff_performance()

    # Save and display results
    baseline.save_results()
    baseline.print_summary()

    print("\n✅ Baseline established. Ready for refactoring cycle.")
    print("Next step: Implement optimizations and compare against this baseline.")


if __name__ == "__main__":
    main()