#!/usr/bin/env python3
"""
Performance Metrics Tracker for Anime Production System
Real-time monitoring and analytics for generation performance, quality trends, and system efficiency
Provides insights for optimization and learning
"""

import asyncio
import json
import logging
import time
import psutil
import aiohttp
import nvidia_ml_py3 as nvml
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
import statistics
from collections import deque, defaultdict
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PerformanceMetricsTracker:
    def __init__(self):
        self.comfyui_url = "http://127.0.0.1:8188"
        self.echo_brain_url = "http://127.0.0.1:8309"

        # Database connection
        self.db_params = {
            'host': 'localhost',
            'database': 'tower_consolidated',
            'user': 'patrick',
            'password': '***REMOVED***'
        }

        # Real-time metrics storage
        self.active_generations = {}
        self.recent_generations = deque(maxlen=100)
        self.quality_trends = deque(maxlen=50)
        self.performance_history = deque(maxlen=1000)

        # System monitoring
        self.system_metrics = {
            'cpu_usage': deque(maxlen=60),  # 1 minute of data
            'memory_usage': deque(maxlen=60),
            'gpu_usage': deque(maxlen=60),
            'gpu_memory': deque(maxlen=60),
            'disk_io': deque(maxlen=60)
        }

        # Performance thresholds
        self.performance_thresholds = {
            'max_generation_time': 300,  # 5 minutes
            'min_quality_score': 0.7,
            'max_cpu_usage': 90,
            'max_memory_usage': 90,
            'max_gpu_usage': 95,
            'max_gpu_memory': 95
        }

        # Initialize NVIDIA ML for GPU monitoring
        try:
            nvml.nvmlInit()
            self.gpu_available = True
            self.gpu_count = nvml.nvmlDeviceGetCount()
            logger.info(f"GPU monitoring initialized: {self.gpu_count} GPUs detected")
        except:
            self.gpu_available = False
            logger.warning("GPU monitoring not available")

        # Start background monitoring
        asyncio.create_task(self.start_system_monitoring())

    async def start_system_monitoring(self):
        """Start continuous system monitoring"""
        logger.info("Starting system performance monitoring...")

        while True:
            try:
                await self.collect_system_metrics()
                await asyncio.sleep(1)  # Collect every second
            except Exception as e:
                logger.error(f"Error in system monitoring: {e}")
                await asyncio.sleep(5)

    async def collect_system_metrics(self):
        """Collect current system metrics"""
        try:
            # CPU and Memory
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            self.system_metrics['cpu_usage'].append({
                'timestamp': datetime.now(),
                'value': cpu_percent
            })

            self.system_metrics['memory_usage'].append({
                'timestamp': datetime.now(),
                'value': memory_percent
            })

            # Disk I/O
            disk_io = psutil.disk_io_counters()
            if disk_io:
                self.system_metrics['disk_io'].append({
                    'timestamp': datetime.now(),
                    'read_bytes': disk_io.read_bytes,
                    'write_bytes': disk_io.write_bytes
                })

            # GPU metrics if available
            if self.gpu_available:
                try:
                    for gpu_id in range(self.gpu_count):
                        handle = nvml.nvmlDeviceGetHandleByIndex(gpu_id)
                        gpu_util = nvml.nvmlDeviceGetUtilizationRates(handle)
                        gpu_mem = nvml.nvmlDeviceGetMemoryInfo(handle)

                        gpu_usage = gpu_util.gpu
                        gpu_memory_percent = (gpu_mem.used / gpu_mem.total) * 100

                        self.system_metrics['gpu_usage'].append({
                            'timestamp': datetime.now(),
                            'gpu_id': gpu_id,
                            'value': gpu_usage
                        })

                        self.system_metrics['gpu_memory'].append({
                            'timestamp': datetime.now(),
                            'gpu_id': gpu_id,
                            'value': gpu_memory_percent,
                            'used_mb': gpu_mem.used // (1024 * 1024),
                            'total_mb': gpu_mem.total // (1024 * 1024)
                        })

                except Exception as e:
                    logger.error(f"Error collecting GPU metrics: {e}")

            # Check for performance alerts
            await self.check_performance_alerts(cpu_percent, memory_percent)

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")

    async def check_performance_alerts(self, cpu_percent: float, memory_percent: float):
        """Check for performance threshold violations"""
        alerts = []

        if cpu_percent > self.performance_thresholds['max_cpu_usage']:
            alerts.append(f"High CPU usage: {cpu_percent:.1f}%")

        if memory_percent > self.performance_thresholds['max_memory_usage']:
            alerts.append(f"High memory usage: {memory_percent:.1f}%")

        if self.gpu_available and self.system_metrics['gpu_usage']:
            latest_gpu = self.system_metrics['gpu_usage'][-1]
            if latest_gpu['value'] > self.performance_thresholds['max_gpu_usage']:
                alerts.append(f"High GPU usage: {latest_gpu['value']:.1f}%")

        if self.gpu_available and self.system_metrics['gpu_memory']:
            latest_gpu_mem = self.system_metrics['gpu_memory'][-1]
            if latest_gpu_mem['value'] > self.performance_thresholds['max_gpu_memory']:
                alerts.append(f"High GPU memory: {latest_gpu_mem['value']:.1f}%")

        if alerts:
            await self.log_performance_alert(alerts)

    async def log_performance_alert(self, alerts: List[str]):
        """Log performance alerts to database"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO performance_alerts (alert_type, message, system_state, created_at)
                VALUES (%s, %s, %s, %s)
            """, (
                'system_performance',
                '; '.join(alerts),
                json.dumps(self.get_current_system_state()),
                datetime.now()
            ))

            conn.commit()
            cur.close()
            conn.close()

            logger.warning(f"⚠️ Performance alert: {'; '.join(alerts)}")

        except Exception as e:
            logger.error(f"Error logging performance alert: {e}")

    def get_current_system_state(self) -> Dict:
        """Get current system state snapshot"""
        state = {
            'timestamp': datetime.now().isoformat(),
            'cpu_usage': self.system_metrics['cpu_usage'][-1]['value'] if self.system_metrics['cpu_usage'] else 0,
            'memory_usage': self.system_metrics['memory_usage'][-1]['value'] if self.system_metrics['memory_usage'] else 0,
            'active_generations': len(self.active_generations),
            'recent_generation_count': len(self.recent_generations)
        }

        if self.gpu_available and self.system_metrics['gpu_usage']:
            state['gpu_usage'] = self.system_metrics['gpu_usage'][-1]['value']

        if self.gpu_available and self.system_metrics['gpu_memory']:
            state['gpu_memory_usage'] = self.system_metrics['gpu_memory'][-1]['value']

        return state

    async def track_generation_start(self, prompt_id: str, prompt: str, workflow_params: Dict):
        """Track start of new generation"""
        generation_data = {
            'prompt_id': prompt_id,
            'prompt': prompt,
            'workflow_params': workflow_params,
            'start_time': datetime.now(),
            'start_system_state': self.get_current_system_state()
        }

        self.active_generations[prompt_id] = generation_data

        # Log to database
        await self.log_generation_event(prompt_id, 'started', generation_data)

        logger.info(f"📊 Tracking generation start: {prompt_id}")

    async def track_generation_progress(self, prompt_id: str, progress: float, node_info: Optional[Dict] = None):
        """Track generation progress"""
        if prompt_id in self.active_generations:
            self.active_generations[prompt_id]['last_progress'] = progress
            self.active_generations[prompt_id]['last_progress_time'] = datetime.now()

            if node_info:
                self.active_generations[prompt_id]['current_node'] = node_info

            # Calculate estimated completion time
            start_time = self.active_generations[prompt_id]['start_time']
            elapsed = (datetime.now() - start_time).total_seconds()

            if progress > 0:
                estimated_total = elapsed / progress
                estimated_remaining = estimated_total - elapsed
                self.active_generations[prompt_id]['estimated_completion'] = datetime.now() + timedelta(seconds=estimated_remaining)

    async def track_generation_complete(self, prompt_id: str, success: bool, output_files: List[str] = None, quality_result: Dict = None):
        """Track completion of generation"""
        if prompt_id not in self.active_generations:
            logger.warning(f"Completion tracked for unknown generation: {prompt_id}")
            return

        generation_data = self.active_generations[prompt_id]
        end_time = datetime.now()
        total_duration = (end_time - generation_data['start_time']).total_seconds()

        completion_data = {
            'end_time': end_time,
            'total_duration': total_duration,
            'success': success,
            'output_files': output_files or [],
            'quality_result': quality_result,
            'end_system_state': self.get_current_system_state()
        }

        generation_data.update(completion_data)

        # Move to recent generations
        self.recent_generations.append(generation_data.copy())
        del self.active_generations[prompt_id]

        # Update quality trends
        if quality_result and 'quality_score' in quality_result:
            self.quality_trends.append({
                'timestamp': end_time,
                'quality_score': quality_result['quality_score'],
                'prompt_id': prompt_id
            })

        # Update performance history
        self.performance_history.append({
            'timestamp': end_time,
            'duration': total_duration,
            'success': success,
            'quality_score': quality_result.get('quality_score', 0) if quality_result else 0
        })

        # Log to database
        await self.log_generation_event(prompt_id, 'completed', completion_data)

        # Check for performance issues
        if total_duration > self.performance_thresholds['max_generation_time']:
            await self.log_performance_alert([f"Generation took too long: {total_duration:.1f}s > {self.performance_thresholds['max_generation_time']}s"])

        logger.info(f"📊 Generation completed: {prompt_id} in {total_duration:.1f}s (success: {success})")

    async def log_generation_event(self, prompt_id: str, event_type: str, data: Dict):
        """Log generation event to database"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO generation_metrics (prompt_id, event_type, event_data, created_at)
                VALUES (%s, %s, %s, %s)
            """, (
                prompt_id,
                event_type,
                json.dumps(data, default=str),
                datetime.now()
            ))

            conn.commit()
            cur.close()
            conn.close()

        except Exception as e:
            logger.error(f"Error logging generation event: {e}")

    async def get_performance_analytics(self, time_range: timedelta = timedelta(hours=24)) -> Dict:
        """Get comprehensive performance analytics"""
        try:
            cutoff_time = datetime.now() - time_range

            # Filter recent data
            recent_completions = [
                gen for gen in self.performance_history
                if gen['timestamp'] > cutoff_time
            ]

            if not recent_completions:
                return self.get_empty_analytics()

            # Calculate statistics
            durations = [gen['duration'] for gen in recent_completions]
            quality_scores = [gen['quality_score'] for gen in recent_completions if gen['quality_score'] > 0]
            success_count = sum(1 for gen in recent_completions if gen['success'])

            analytics = {
                'time_range_hours': time_range.total_seconds() / 3600,
                'total_generations': len(recent_completions),
                'successful_generations': success_count,
                'success_rate': success_count / len(recent_completions) if recent_completions else 0,

                'duration_stats': {
                    'average': statistics.mean(durations),
                    'median': statistics.median(durations),
                    'min': min(durations),
                    'max': max(durations),
                    'std_dev': statistics.stdev(durations) if len(durations) > 1 else 0
                },

                'quality_stats': {
                    'average': statistics.mean(quality_scores) if quality_scores else 0,
                    'median': statistics.median(quality_scores) if quality_scores else 0,
                    'min': min(quality_scores) if quality_scores else 0,
                    'max': max(quality_scores) if quality_scores else 0,
                    'trend': self.calculate_quality_trend()
                },

                'system_performance': self.get_system_performance_summary(),
                'active_generations': len(self.active_generations),
                'recent_alerts': await self.get_recent_alerts(),

                'efficiency_metrics': {
                    'generations_per_hour': len(recent_completions) / max(time_range.total_seconds() / 3600, 1),
                    'average_quality_per_time': (statistics.mean(quality_scores) / statistics.mean(durations)) if quality_scores and durations else 0,
                    'resource_efficiency': self.calculate_resource_efficiency()
                }
            }

            return analytics

        except Exception as e:
            logger.error(f"Error generating performance analytics: {e}")
            return self.get_empty_analytics()

    def get_empty_analytics(self) -> Dict:
        """Return empty analytics structure"""
        return {
            'total_generations': 0,
            'successful_generations': 0,
            'success_rate': 0,
            'duration_stats': {'average': 0, 'median': 0, 'min': 0, 'max': 0, 'std_dev': 0},
            'quality_stats': {'average': 0, 'median': 0, 'min': 0, 'max': 0, 'trend': 'stable'},
            'system_performance': {},
            'active_generations': 0,
            'recent_alerts': [],
            'efficiency_metrics': {}
        }

    def calculate_quality_trend(self) -> str:
        """Calculate quality trend over recent generations"""
        if len(self.quality_trends) < 3:
            return 'insufficient_data'

        recent_scores = [item['quality_score'] for item in list(self.quality_trends)[-10:]]
        older_scores = [item['quality_score'] for item in list(self.quality_trends)[-20:-10]]

        if not older_scores:
            return 'insufficient_data'

        recent_avg = statistics.mean(recent_scores)
        older_avg = statistics.mean(older_scores)

        difference = recent_avg - older_avg

        if abs(difference) < 0.05:
            return 'stable'
        elif difference > 0:
            return 'improving'
        else:
            return 'declining'

    def get_system_performance_summary(self) -> Dict:
        """Get summary of system performance"""
        summary = {}

        # CPU
        if self.system_metrics['cpu_usage']:
            cpu_values = [item['value'] for item in list(self.system_metrics['cpu_usage'])[-30:]]
            summary['cpu'] = {
                'current': cpu_values[-1] if cpu_values else 0,
                'average': statistics.mean(cpu_values),
                'max': max(cpu_values)
            }

        # Memory
        if self.system_metrics['memory_usage']:
            mem_values = [item['value'] for item in list(self.system_metrics['memory_usage'])[-30:]]
            summary['memory'] = {
                'current': mem_values[-1] if mem_values else 0,
                'average': statistics.mean(mem_values),
                'max': max(mem_values)
            }

        # GPU
        if self.gpu_available and self.system_metrics['gpu_usage']:
            gpu_values = [item['value'] for item in list(self.system_metrics['gpu_usage'])[-30:]]
            gpu_mem_values = [item['value'] for item in list(self.system_metrics['gpu_memory'])[-30:]]

            summary['gpu'] = {
                'usage_current': gpu_values[-1] if gpu_values else 0,
                'usage_average': statistics.mean(gpu_values) if gpu_values else 0,
                'memory_current': gpu_mem_values[-1] if gpu_mem_values else 0,
                'memory_average': statistics.mean(gpu_mem_values) if gpu_mem_values else 0
            }

        return summary

    def calculate_resource_efficiency(self) -> float:
        """Calculate overall resource efficiency score"""
        try:
            # Simple efficiency calculation based on system usage vs output
            if not self.recent_generations or not self.system_metrics['cpu_usage']:
                return 0.0

            recent_completions = len([gen for gen in self.recent_generations if gen['success']])
            avg_cpu = statistics.mean([item['value'] for item in list(self.system_metrics['cpu_usage'])[-60:]])

            # Higher completions with lower CPU usage = higher efficiency
            efficiency = recent_completions / max(avg_cpu / 100, 0.1)

            return min(efficiency, 10.0)  # Cap at 10.0

        except Exception as e:
            logger.error(f"Error calculating resource efficiency: {e}")
            return 0.0

    async def get_recent_alerts(self, limit: int = 10) -> List[Dict]:
        """Get recent performance alerts"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT alert_type, message, created_at
                FROM performance_alerts
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))

            alerts = cur.fetchall()
            cur.close()
            conn.close()

            return [dict(alert) for alert in alerts]

        except Exception as e:
            logger.error(f"Error getting recent alerts: {e}")
            return []

    async def get_generation_queue_status(self) -> Dict:
        """Get current generation queue status"""
        return {
            'active_generations': len(self.active_generations),
            'active_details': [
                {
                    'prompt_id': pid,
                    'elapsed_time': (datetime.now() - data['start_time']).total_seconds(),
                    'progress': data.get('last_progress', 0),
                    'estimated_completion': data.get('estimated_completion').isoformat() if data.get('estimated_completion') else None
                }
                for pid, data in self.active_generations.items()
            ],
            'recent_completions': len(self.recent_generations),
            'quality_trend': self.calculate_quality_trend()
        }

    async def export_metrics_report(self, format: str = 'json') -> str:
        """Export comprehensive metrics report"""
        try:
            analytics = await self.get_performance_analytics()
            queue_status = await self.get_generation_queue_status()
            system_state = self.get_current_system_state()

            report = {
                'report_timestamp': datetime.now().isoformat(),
                'analytics': analytics,
                'queue_status': queue_status,
                'system_state': system_state,
                'configuration': {
                    'thresholds': self.performance_thresholds,
                    'monitoring_enabled': True,
                    'gpu_available': self.gpu_available
                }
            }

            if format == 'json':
                return json.dumps(report, indent=2, default=str)
            else:
                # Could add other formats like CSV, XML, etc.
                return json.dumps(report, default=str)

        except Exception as e:
            logger.error(f"Error exporting metrics report: {e}")
            return json.dumps({'error': str(e)})

# Database table creation
async def create_metrics_tables():
    """Create tables for metrics tracking"""
    try:
        conn = psycopg2.connect(
            host='localhost',
            database='tower_consolidated',
            user='patrick',
            password=''
        )
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS generation_metrics (
                id SERIAL PRIMARY KEY,
                prompt_id VARCHAR(255),
                event_type VARCHAR(50),
                event_data JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS performance_alerts (
                id SERIAL PRIMARY KEY,
                alert_type VARCHAR(50),
                message TEXT,
                system_state JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS system_metrics_snapshots (
                id SERIAL PRIMARY KEY,
                cpu_usage FLOAT,
                memory_usage FLOAT,
                gpu_usage FLOAT,
                gpu_memory_usage FLOAT,
                disk_io_read BIGINT,
                disk_io_write BIGINT,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_generation_metrics_prompt ON generation_metrics(prompt_id);
            CREATE INDEX IF NOT EXISTS idx_generation_metrics_type ON generation_metrics(event_type);
            CREATE INDEX IF NOT EXISTS idx_generation_metrics_time ON generation_metrics(created_at);
            CREATE INDEX IF NOT EXISTS idx_performance_alerts_time ON performance_alerts(created_at);
            CREATE INDEX IF NOT EXISTS idx_system_metrics_time ON system_metrics_snapshots(created_at);
        """)

        conn.commit()
        cur.close()
        conn.close()
        logger.info("Performance metrics tables created/verified")

    except Exception as e:
        logger.error(f"Error creating metrics tables: {e}")

async def main():
    """Main entry point for testing"""
    await create_metrics_tables()

    # Start metrics tracker
    tracker = PerformanceMetricsTracker()

    # Simulate some generation tracking
    await tracker.track_generation_start("test_123", "anime girl", {"steps": 30, "cfg": 7.5})
    await asyncio.sleep(2)
    await tracker.track_generation_progress("test_123", 0.5)
    await asyncio.sleep(2)
    await tracker.track_generation_complete("test_123", True, ["output.mp4"], {"quality_score": 0.85})

    # Get analytics
    analytics = await tracker.get_performance_analytics()
    print("Analytics:", json.dumps(analytics, indent=2, default=str))

    # Keep monitoring for a while
    await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())