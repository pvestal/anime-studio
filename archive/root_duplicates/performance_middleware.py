#!/usr/bin/env python3
"""
Performance Tracking Middleware
Automatically captures performance metrics during anime generation processes.
"""

import asyncio
import logging
import psutil
import time
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from contextlib import contextmanager, asynccontextmanager
import threading
import queue
import subprocess
import os
import nvidia_ml_py3 as nvml
from performance_api import record_performance_metrics

logger = logging.getLogger(__name__)

class PerformanceTracker:
    """Tracks performance metrics during generation jobs"""

    def __init__(self):
        self.active_jobs = {}
        self.metrics_queue = queue.Queue()
        self.monitoring_active = False
        self.monitor_thread = None
        self._init_gpu_monitoring()

    def _init_gpu_monitoring(self):
        """Initialize GPU monitoring"""
        try:
            nvml.nvmlInit()
            self.gpu_available = True
            self.gpu_count = nvml.nvmlDeviceGetCount()
            logger.info(f"GPU monitoring initialized. Found {self.gpu_count} GPUs")
        except Exception as e:
            logger.warning(f"GPU monitoring not available: {e}")
            self.gpu_available = False
            self.gpu_count = 0

    def start_monitoring(self):
        """Start background monitoring thread"""
        if not self.monitoring_active:
            self.monitoring_active = True
            self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("Performance monitoring started")

    def stop_monitoring(self):
        """Stop background monitoring"""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Performance monitoring stopped")

    def _monitoring_loop(self):
        """Background monitoring loop"""
        while self.monitoring_active:
            try:
                # Update metrics for all active jobs
                current_time = time.time()
                for job_id, job_data in self.active_jobs.items():
                    self._update_job_metrics(job_id, job_data, current_time)

                time.sleep(2)  # Update every 2 seconds
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(5)

    def _update_job_metrics(self, job_id: str, job_data: Dict, current_time: float):
        """Update real-time metrics for a job"""
        try:
            # CPU and memory metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()

            # GPU metrics
            gpu_metrics = self._get_gpu_metrics()

            # Update job data
            job_data['cpu_samples'].append(cpu_percent)
            job_data['memory_samples'].append(memory.used)

            if gpu_metrics:
                job_data['gpu_utilization_samples'].extend([gpu['utilization'] for gpu in gpu_metrics])
                job_data['vram_samples'].extend([gpu['memory_used'] for gpu in gpu_metrics])
                job_data['gpu_temp_samples'].extend([gpu['temperature'] for gpu in gpu_metrics])

            # Keep only recent samples (last 5 minutes)
            max_samples = 150  # 5 minutes * 30 samples per minute
            for key in ['cpu_samples', 'memory_samples', 'gpu_utilization_samples', 'vram_samples']:
                if key in job_data and len(job_data[key]) > max_samples:
                    job_data[key] = job_data[key][-max_samples:]

        except Exception as e:
            logger.warning(f"Error updating metrics for job {job_id}: {e}")

    def _get_gpu_metrics(self) -> Optional[List[Dict]]:
        """Get current GPU metrics"""
        if not self.gpu_available:
            return None

        gpu_metrics = []
        try:
            for i in range(self.gpu_count):
                handle = nvml.nvmlDeviceGetHandleByIndex(i)

                # GPU utilization
                util = nvml.nvmlDeviceGetUtilizationRates(handle)

                # Memory info
                mem_info = nvml.nvmlDeviceGetMemoryInfo(handle)

                # Temperature
                try:
                    temp = nvml.nvmlDeviceGetTemperature(handle, nvml.NVML_TEMPERATURE_GPU)
                except:
                    temp = None

                # GPU name
                try:
                    name = nvml.nvmlDeviceGetName(handle).decode('utf-8')
                except:
                    name = f"GPU_{i}"

                gpu_metrics.append({
                    'gpu_id': i,
                    'name': name,
                    'utilization': util.gpu,
                    'memory_utilization': util.memory,
                    'memory_total': mem_info.total // (1024 * 1024),  # MB
                    'memory_used': mem_info.used // (1024 * 1024),   # MB
                    'memory_free': mem_info.free // (1024 * 1024),   # MB
                    'temperature': temp
                })

            return gpu_metrics

        except Exception as e:
            logger.warning(f"Error getting GPU metrics: {e}")
            return None

    @contextmanager
    def track_job(self, job_id: str, pipeline_type: str, job_params: Dict):
        """Context manager to track a generation job"""
        start_time = time.time()

        # Initialize job tracking
        job_data = {
            'job_id': job_id,
            'pipeline_type': pipeline_type,
            'job_params': job_params,
            'start_time': start_time,
            'queue_start_time': None,
            'processing_start_time': None,
            'end_time': None,
            'cpu_samples': [],
            'memory_samples': [],
            'gpu_utilization_samples': [],
            'vram_samples': [],
            'gpu_temp_samples': [],
            'error_details': None,
            'success': False,
            'phases': {}  # Track different phases of generation
        }

        self.active_jobs[job_id] = job_data

        # Start monitoring if not already active
        if not self.monitoring_active:
            self.start_monitoring()

        try:
            logger.info(f"Started tracking job {job_id} ({pipeline_type})")
            yield JobTracker(job_id, job_data, self)

        except Exception as e:
            job_data['error_details'] = {
                'error_type': type(e).__name__,
                'error_message': str(e),
                'error_time': time.time()
            }
            logger.error(f"Job {job_id} failed: {e}")
            raise

        finally:
            job_data['end_time'] = time.time()
            self._finalize_job(job_id, job_data)
            if job_id in self.active_jobs:
                del self.active_jobs[job_id]

    def _finalize_job(self, job_id: str, job_data: Dict):
        """Finalize job metrics and save to database"""
        try:
            # Calculate final metrics
            total_time = job_data['end_time'] - job_data['start_time']

            # Queue time calculation
            queue_time = None
            if job_data.get('processing_start_time') and job_data.get('queue_start_time'):
                queue_time = job_data['processing_start_time'] - job_data['queue_start_time']

            # Processing time calculation
            processing_time = None
            if job_data.get('processing_start_time'):
                processing_time = job_data['end_time'] - job_data['processing_start_time']

            # Calculate averages from samples
            cpu_avg = np.mean(job_data['cpu_samples']) if job_data['cpu_samples'] else None
            memory_avg = np.mean(job_data['memory_samples']) if job_data['memory_samples'] else None

            gpu_util_avg = None
            gpu_util_peak = None
            vram_used = None
            vram_peak = None
            gpu_model = None

            if job_data['gpu_utilization_samples']:
                gpu_util_avg = np.mean(job_data['gpu_utilization_samples'])
                gpu_util_peak = np.max(job_data['gpu_utilization_samples'])

            if job_data['vram_samples']:
                vram_used = np.mean(job_data['vram_samples'])
                vram_peak = np.max(job_data['vram_samples'])

            # Get GPU model info
            if self.gpu_available and self.gpu_count > 0:
                try:
                    handle = nvml.nvmlDeviceGetHandleByIndex(0)  # Use first GPU
                    gpu_model = nvml.nvmlDeviceGetName(handle).decode('utf-8')
                except:
                    gpu_model = "Unknown GPU"

            # Calculate complexity score based on job parameters
            complexity_score = self._calculate_complexity_score(job_data['job_params'])

            # Create performance metrics object
            metrics_data = {
                'job_id': job_id,
                'pipeline_type': job_data['pipeline_type'],
                'total_time_seconds': total_time,
                'queue_time_seconds': queue_time,
                'processing_time_seconds': processing_time,
                'gpu_utilization_avg': gpu_util_avg,
                'gpu_utilization_peak': gpu_util_peak,
                'vram_used_mb': int(vram_used) if vram_used else None,
                'cpu_utilization_avg': cpu_avg,
                'memory_used_mb': int(memory_avg / (1024 * 1024)) if memory_avg else None,
                'success': job_data.get('success', True),
                'error_details': job_data.get('error_details')
            }

            # Store additional metadata
            extended_metadata = {
                'complexity_score': complexity_score,
                'gpu_model': gpu_model,
                'job_params': job_data['job_params'],
                'phases': job_data['phases'],
                'sample_counts': {
                    'cpu_samples': len(job_data['cpu_samples']),
                    'gpu_samples': len(job_data['gpu_utilization_samples']),
                    'memory_samples': len(job_data['memory_samples'])
                }
            }

            # Save to database (async call)
            asyncio.create_task(self._save_metrics_async(metrics_data, extended_metadata))

            logger.info(f"Job {job_id} completed. Total time: {total_time:.2f}s, "
                       f"GPU avg: {gpu_util_avg:.1f}%" if gpu_util_avg else "")

        except Exception as e:
            logger.error(f"Error finalizing job {job_id}: {e}")

    async def _save_metrics_async(self, metrics_data: Dict, extended_metadata: Dict):
        """Save metrics to database asynchronously"""
        try:
            # Add extended metadata to the main metrics
            metrics_data.update({
                'complexity_score': extended_metadata.get('complexity_score'),
                'gpu_model': extended_metadata.get('gpu_model'),
                'metadata': json.dumps(extended_metadata)
            })

            # Save to database using the performance API
            await record_performance_metrics(metrics_data)

        except Exception as e:
            logger.error(f"Error saving metrics to database: {e}")

    def _calculate_complexity_score(self, job_params: Dict) -> float:
        """Calculate complexity score (0-10) based on job parameters"""
        try:
            score = 1.0  # Base score

            # Resolution complexity
            resolution = job_params.get('resolution', '512x512')
            if 'x' in str(resolution):
                try:
                    w, h = map(int, str(resolution).split('x'))
                    pixels = w * h
                    # Normalize to 512x512 baseline
                    resolution_factor = pixels / (512 * 512)
                    score += min(3.0, resolution_factor)
                except:
                    score += 1.0

            # Frame count complexity
            frame_count = job_params.get('frame_count', 1)
            if frame_count > 1:
                frame_factor = min(3.0, frame_count / 30.0)  # 30 frames baseline
                score += frame_factor

            # Steps complexity
            steps = job_params.get('steps', 20)
            step_factor = min(2.0, steps / 50.0)  # 50 steps max complexity
            score += step_factor

            # Guidance scale complexity
            guidance = job_params.get('guidance_scale', 7.5)
            if guidance > 10.0:
                score += 1.0

            return min(10.0, score)

        except Exception as e:
            logger.warning(f"Error calculating complexity score: {e}")
            return 5.0  # Default medium complexity


class JobTracker:
    """Individual job tracker with phase tracking"""

    def __init__(self, job_id: str, job_data: Dict, tracker: PerformanceTracker):
        self.job_id = job_id
        self.job_data = job_data
        self.tracker = tracker

    def mark_queued(self):
        """Mark job as queued"""
        self.job_data['queue_start_time'] = time.time()
        logger.debug(f"Job {self.job_id} queued")

    def mark_processing_start(self):
        """Mark job processing start"""
        self.job_data['processing_start_time'] = time.time()
        logger.debug(f"Job {self.job_id} processing started")

    def mark_phase(self, phase_name: str, description: str = ""):
        """Mark the start of a processing phase"""
        phase_time = time.time()
        self.job_data['phases'][phase_name] = {
            'start_time': phase_time,
            'description': description
        }
        logger.debug(f"Job {self.job_id} phase: {phase_name}")

    def mark_phase_end(self, phase_name: str):
        """Mark the end of a processing phase"""
        if phase_name in self.job_data['phases']:
            end_time = time.time()
            self.job_data['phases'][phase_name]['end_time'] = end_time
            duration = end_time - self.job_data['phases'][phase_name]['start_time']
            self.job_data['phases'][phase_name]['duration'] = duration
            logger.debug(f"Job {self.job_id} phase {phase_name} completed in {duration:.2f}s")

    def mark_success(self):
        """Mark job as successful"""
        self.job_data['success'] = True

    def mark_failure(self, error: Exception):
        """Mark job as failed"""
        self.job_data['success'] = False
        self.job_data['error_details'] = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'error_time': time.time()
        }

    def update_progress(self, progress: float, stage: str = ""):
        """Update job progress (0.0 to 1.0)"""
        self.job_data['progress'] = progress
        if stage:
            self.job_data['current_stage'] = stage


# Global performance tracker instance
performance_tracker = PerformanceTracker()

# Decorator for automatic performance tracking
def track_performance(pipeline_type: str):
    """Decorator to automatically track performance of generation functions"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Generate job ID
            job_id = hashlib.md5(f"{func.__name__}_{time.time()}_{id(func)}".encode()).hexdigest()[:16]

            # Extract job parameters from function arguments
            job_params = {
                'function': func.__name__,
                'args_count': len(args),
                'kwargs': {k: str(v)[:100] for k, v in kwargs.items()}  # Truncate long values
            }

            with performance_tracker.track_job(job_id, pipeline_type, job_params) as tracker:
                tracker.mark_processing_start()

                try:
                    result = func(*args, **kwargs)
                    tracker.mark_success()
                    return result
                except Exception as e:
                    tracker.mark_failure(e)
                    raise

        return wrapper
    return decorator


# Context manager for manual performance tracking
@contextmanager
def track_generation_job(job_id: str, pipeline_type: str, job_params: Dict):
    """Context manager for manual performance tracking"""
    with performance_tracker.track_job(job_id, pipeline_type, job_params) as tracker:
        yield tracker


# Initialize monitoring on import
def initialize_performance_monitoring():
    """Initialize performance monitoring system"""
    try:
        import numpy as np
        global np
    except ImportError:
        logger.error("NumPy not available. Performance tracking may be limited.")

    performance_tracker.start_monitoring()
    logger.info("Performance tracking system initialized")


# Clean shutdown function
def shutdown_performance_monitoring():
    """Clean shutdown of performance monitoring"""
    performance_tracker.stop_monitoring()
    logger.info("Performance monitoring shutdown complete")


# Export public interface
__all__ = [
    'performance_tracker',
    'track_performance',
    'track_generation_job',
    'initialize_performance_monitoring',
    'shutdown_performance_monitoring',
    'PerformanceTracker',
    'JobTracker'
]