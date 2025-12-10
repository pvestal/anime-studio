#!/usr/bin/env python3
"""
PERFORMANCE VALIDATION AUDIT
Testing claimed 4-second performance vs reality

PERFORMANCE CLAIMS TO VALIDATE:
- 4 seconds average generation time (vs claimed 60-200 seconds improvement)
- Concurrent request handling without blocking
- Database persistence without performance impact
- Memory efficiency during generation

This audit will provide HONEST assessment of actual performance
"""

import requests
import time
import json
import asyncio
import psutil
import statistics
import concurrent.futures
from typing import List, Dict, Any
import threading


class PerformanceAudit:
    def __init__(self):
        self.api_base = "http://localhost:8328"
        self.test_results = []
        self.memory_measurements = []

    def measure_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage"""
        process_info = []

        # Find anime-related processes
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info']):
            try:
                if any('anime' in str(item).lower() for item in proc.info['cmdline'] or []):
                    memory_mb = proc.info['memory_info'].rss / 1024 / 1024
                    process_info.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'memory_mb': memory_mb
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        total_memory = sum(p['memory_mb'] for p in process_info)

        return {
            'total_anime_memory_mb': total_memory,
            'process_count': len(process_info),
            'individual_processes': process_info
        }

    def wait_for_job_completion(self, job_id: str, max_wait: int = 180) -> Dict[str, Any]:
        """Wait for job to complete and measure actual time"""
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                response = requests.get(f"{self.api_base}/jobs/{job_id}", timeout=5)

                if response.status_code == 200:
                    job_data = response.json()
                    status = job_data.get('status', 'unknown')

                    if status == 'completed':
                        actual_time = time.time() - start_time
                        reported_time = job_data.get('total_time', 0)

                        return {
                            'success': True,
                            'job_id': job_id,
                            'status': status,
                            'actual_wall_time': actual_time,
                            'reported_generation_time': reported_time,
                            'output_path': job_data.get('output_path'),
                            'prompt': job_data.get('prompt', '')[:50]
                        }

                    elif status == 'failed':
                        return {
                            'success': False,
                            'job_id': job_id,
                            'status': status,
                            'error': job_data.get('error', 'Unknown error'),
                            'actual_wall_time': time.time() - start_time
                        }

                    # Still running, continue waiting
                    time.sleep(1)

            except Exception as e:
                print(f"Error checking job {job_id}: {e}")
                time.sleep(1)

        # Timeout
        return {
            'success': False,
            'job_id': job_id,
            'status': 'timeout',
            'error': f'Job timed out after {max_wait} seconds',
            'actual_wall_time': max_wait
        }

    def test_single_generation_performance(self) -> Dict[str, Any]:
        """Test single generation with detailed timing"""
        print("\n⏱️  SINGLE GENERATION PERFORMANCE TEST")
        print("-" * 50)

        # Measure memory before
        memory_before = self.measure_memory_usage()

        test_prompt = "high quality anime girl with blue hair in cherry blossom garden"

        print(f"Testing prompt: {test_prompt}")
        print(f"Memory before: {memory_before['total_anime_memory_mb']:.1f}MB")

        # Start generation
        start_request = time.time()

        try:
            response = requests.post(f"{self.api_base}/generate", json={
                "prompt": test_prompt,
                "negative_prompt": "bad quality, deformed",
                "width": 512,
                "height": 768
            }, timeout=15)

            request_time = time.time() - start_request

            if response.status_code != 200:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}: {response.text}',
                    'request_time': request_time
                }

            job_data = response.json()
            job_id = job_data.get('job_id')

            print(f"✅ Request submitted in {request_time:.3f}s, job ID: {job_id}")

            # Wait for completion with detailed monitoring
            result = self.wait_for_job_completion(job_id, max_wait=300)  # 5 minutes max

            # Measure memory after
            memory_after = self.measure_memory_usage()
            memory_delta = memory_after['total_anime_memory_mb'] - memory_before['total_anime_memory_mb']

            result.update({
                'request_time': request_time,
                'memory_before_mb': memory_before['total_anime_memory_mb'],
                'memory_after_mb': memory_after['total_anime_memory_mb'],
                'memory_delta_mb': memory_delta
            })

            if result['success']:
                print(f"✅ Generation completed!")
                print(f"   Actual wall time: {result['actual_wall_time']:.2f}s")
                print(f"   Reported time: {result['reported_generation_time']:.2f}s")
                print(f"   Memory delta: {memory_delta:+.1f}MB")

                # Verify output file exists
                output_path = result.get('output_path')
                if output_path:
                    import os
                    if os.path.exists(output_path):
                        file_size = os.path.getsize(output_path) / 1024
                        print(f"   Output file: {file_size:.1f}KB")
                        result['output_file_size_kb'] = file_size
                    else:
                        print(f"   ⚠️  Output file missing: {output_path}")
                        result['output_file_missing'] = True
            else:
                print(f"❌ Generation failed: {result.get('error', 'Unknown error')}")
                print(f"   Time until failure: {result['actual_wall_time']:.2f}s")

            return result

        except Exception as e:
            return {
                'success': False,
                'error': f'Exception during generation: {str(e)}',
                'request_time': time.time() - start_request
            }

    def test_performance_under_load(self, num_concurrent: int = 5) -> List[Dict[str, Any]]:
        """Test performance with multiple concurrent requests"""
        print(f"\n🚀 CONCURRENT PERFORMANCE TEST ({num_concurrent} requests)")
        print("-" * 50)

        def single_concurrent_test(worker_id: int) -> Dict[str, Any]:
            """Single worker for concurrent test"""
            try:
                start_time = time.time()

                response = requests.post(f"{self.api_base}/generate", json={
                    "prompt": f"anime character test worker {worker_id}",
                    "width": 512,
                    "height": 768
                }, timeout=10)

                if response.status_code != 200:
                    return {
                        'worker_id': worker_id,
                        'success': False,
                        'error': f'HTTP {response.status_code}',
                        'submission_time': time.time() - start_time
                    }

                job_data = response.json()
                job_id = job_data.get('job_id')
                submission_time = time.time() - start_time

                # Wait for completion
                result = self.wait_for_job_completion(job_id, max_wait=180)
                result.update({
                    'worker_id': worker_id,
                    'submission_time': submission_time
                })

                return result

            except Exception as e:
                return {
                    'worker_id': worker_id,
                    'success': False,
                    'error': str(e),
                    'submission_time': time.time() - start_time
                }

        # Launch concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as executor:
            futures = [executor.submit(single_concurrent_test, i) for i in range(num_concurrent)]
            results = []

            for future in concurrent.futures.as_completed(futures, timeout=300):  # 5 min total
                try:
                    result = future.result()
                    results.append(result)

                    if result['success']:
                        print(f"✅ Worker {result['worker_id']}: {result['actual_wall_time']:.2f}s total")
                    else:
                        print(f"❌ Worker {result['worker_id']}: {result['error']}")

                except Exception as e:
                    print(f"💥 Worker future failed: {e}")

        return results

    def analyze_performance_results(self, results: List[Dict[str, Any]]):
        """Analyze and report performance results"""
        successful = [r for r in results if r.get('success')]
        failed = [r for r in results if not r.get('success')]

        print(f"\n📊 PERFORMANCE ANALYSIS")
        print("-" * 50)

        print(f"Success Rate: {len(successful)}/{len(results)} ({(len(successful)/len(results)*100):.1f}%)")

        if successful:
            wall_times = [r['actual_wall_time'] for r in successful]
            reported_times = [r.get('reported_generation_time', 0) for r in successful if r.get('reported_generation_time')]

            print(f"\nWall Clock Times (actual user experience):")
            print(f"  Average: {statistics.mean(wall_times):.2f}s")
            print(f"  Median: {statistics.median(wall_times):.2f}s")
            print(f"  Min: {min(wall_times):.2f}s")
            print(f"  Max: {max(wall_times):.2f}s")
            print(f"  Std Dev: {statistics.stdev(wall_times) if len(wall_times) > 1 else 0:.2f}s")

            if reported_times:
                print(f"\nReported Generation Times (ComfyUI only):")
                print(f"  Average: {statistics.mean(reported_times):.2f}s")
                print(f"  Median: {statistics.median(reported_times):.2f}s")

            # Check claimed performance
            avg_wall_time = statistics.mean(wall_times)
            if avg_wall_time > 10:
                print(f"\n⚠️  PERFORMANCE CONCERN: Average {avg_wall_time:.2f}s > 10s target")
            elif avg_wall_time <= 5:
                print(f"\n✅ PERFORMANCE GOOD: Average {avg_wall_time:.2f}s ≤ 5s")
            else:
                print(f"\n⚡ PERFORMANCE ACCEPTABLE: Average {avg_wall_time:.2f}s")

        if failed:
            print(f"\nFailure Analysis:")
            error_types = {}
            for r in failed:
                error = r.get('error', 'Unknown')
                error_types[error] = error_types.get(error, 0) + 1

            for error, count in error_types.items():
                print(f"  {error}: {count} times")

    def run_comprehensive_performance_audit(self):
        """Run complete performance audit"""
        print("⚡ COMPREHENSIVE PERFORMANCE AUDIT - Tower Anime Production")
        print("=" * 70)

        # Test 1: Single generation baseline
        single_result = self.test_single_generation_performance()
        self.test_results.append(single_result)

        # Test 2: Small concurrent load (3 requests)
        concurrent_3 = self.test_performance_under_load(3)
        self.test_results.extend(concurrent_3)

        # Test 3: Medium concurrent load (5 requests)
        concurrent_5 = self.test_performance_under_load(5)
        self.test_results.extend(concurrent_5)

        # Analysis
        self.analyze_performance_results(self.test_results)

        # Memory analysis
        print(f"\n💾 MEMORY USAGE SUMMARY")
        print("-" * 50)
        current_memory = self.measure_memory_usage()
        print(f"Current anime processes: {current_memory['process_count']}")
        print(f"Total memory usage: {current_memory['total_anime_memory_mb']:.1f}MB")

        for proc in current_memory['individual_processes']:
            print(f"  PID {proc['pid']}: {proc['name']} - {proc['memory_mb']:.1f}MB")

        # Final verdict
        print(f"\n" + "=" * 70)
        print("🎯 PERFORMANCE VERDICT")
        print("=" * 70)

        successful_results = [r for r in self.test_results if r.get('success')]

        if successful_results:
            avg_time = statistics.mean([r['actual_wall_time'] for r in successful_results])

            print(f"Average Generation Time: {avg_time:.2f} seconds")

            if avg_time <= 4:
                print("✅ CLAIM VALIDATED: Sub-4-second performance achieved")
            elif avg_time <= 10:
                print("⚡ CLAIM PARTIALLY VALIDATED: Good performance but >4s")
            else:
                print("❌ CLAIM DISPUTED: Performance significantly slower than claimed")

            success_rate = len(successful_results) / len(self.test_results)
            if success_rate >= 0.95:
                print("✅ RELIABILITY: High success rate (≥95%)")
            elif success_rate >= 0.8:
                print("⚡ RELIABILITY: Acceptable success rate (≥80%)")
            else:
                print("❌ RELIABILITY: Poor success rate (<80%)")

        else:
            print("❌ CRITICAL: No successful generations completed")

        return self.test_results


if __name__ == "__main__":
    audit = PerformanceAudit()
    results = audit.run_comprehensive_performance_audit()