#!/usr/bin/env python3
"""
Performance monitoring system for Tower Anime Production.

Features:
- Generation time tracking
- VRAM usage monitoring
- Bottleneck identification
- Performance metrics logging
- Real-time performance dashboard
- Optimization recommendations
"""

import json
import time
import asyncio
import logging
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import sqlite3
import psutil
import subprocess

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetric:
    """Individual performance measurement"""
    timestamp: float
    generation_id: str
    generation_type: str  # "image", "animation"
    prompt_length: int

    # Generation parameters
    model_name: str
    width: int
    height: int
    steps: int
    cfg_scale: float
    sampler: str
    batch_size: int

    # Performance metrics
    total_time_seconds: float
    queue_time_seconds: float
    generation_time_seconds: float
    vae_decode_time_seconds: float

    # Resource usage
    vram_used_mb: int
    vram_peak_mb: int
    gpu_utilization_percent: float
    cpu_usage_percent: float
    temperature_celsius: int

    # Quality metrics
    output_file_size_mb: float
    quality_score: float = 0.0

    # Optimization flags
    used_cache: bool = False
    optimization_level: str = "standard"  # "draft", "standard", "high_quality"

@dataclass
class BottleneckAnalysis:
    """Analysis of performance bottlenecks"""
    bottleneck_type: str  # "vram", "compute", "io", "queue"
    severity: str  # "low", "medium", "high", "critical"
    description: str
    recommendation: str
    estimated_improvement: str

@dataclass
class PerformanceReport:
    """Comprehensive performance report"""
    period_start: float
    period_end: float
    total_generations: int

    # Time statistics
    avg_generation_time: float
    min_generation_time: float
    max_generation_time: float
    p95_generation_time: float

    # Resource statistics
    avg_vram_usage: float
    peak_vram_usage: float
    avg_gpu_utilization: float
    avg_temperature: float

    # Efficiency metrics
    generations_per_hour: float
    cache_hit_rate: float
    failure_rate: float

    # Bottlenecks and recommendations
    bottlenecks: List[BottleneckAnalysis]
    recommendations: List[str]

class PerformanceMonitor:
    """Performance monitoring and analysis system"""

    def __init__(self, db_path: str = "/opt/tower-anime-production/logs/performance.db"):
        """
        Initialize performance monitor

        Args:
            db_path: SQLite database path for metrics storage
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create database and tables
        self._init_database()

        # Current monitoring session
        self.current_metrics: Dict[str, PerformanceMetric] = {}
        self.monitoring_active = False

        # Performance thresholds
        self.thresholds = {
            "target_generation_time": {
                "draft": 30,      # seconds
                "standard": 60,
                "high_quality": 120
            },
            "vram_warning_mb": 10000,     # 10GB warning threshold
            "temperature_warning": 80,    # Celsius
            "gpu_utilization_low": 70,    # Below 70% indicates underutilization
            "queue_time_warning": 30      # seconds
        }

    def _init_database(self):
        """Initialize SQLite database for metrics storage"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    generation_id TEXT,
                    generation_type TEXT,
                    prompt_length INTEGER,
                    model_name TEXT,
                    width INTEGER,
                    height INTEGER,
                    steps INTEGER,
                    cfg_scale REAL,
                    sampler TEXT,
                    batch_size INTEGER,
                    total_time_seconds REAL,
                    queue_time_seconds REAL,
                    generation_time_seconds REAL,
                    vae_decode_time_seconds REAL,
                    vram_used_mb INTEGER,
                    vram_peak_mb INTEGER,
                    gpu_utilization_percent REAL,
                    cpu_usage_percent REAL,
                    temperature_celsius INTEGER,
                    output_file_size_mb REAL,
                    quality_score REAL,
                    used_cache INTEGER,
                    optimization_level TEXT
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS bottleneck_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    generation_id TEXT,
                    bottleneck_type TEXT,
                    severity TEXT,
                    description TEXT,
                    recommendation TEXT
                )
            ''')

            # Create indexes for performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON performance_metrics(timestamp)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_generation_type ON performance_metrics(generation_type)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_model_name ON performance_metrics(model_name)')

    def start_monitoring(self, generation_id: str, generation_type: str,
                        generation_params: Dict[str, Any]):
        """Start monitoring a generation process"""

        current_time = time.time()

        # Get initial system stats
        gpu_stats = self._get_gpu_stats()
        cpu_usage = psutil.cpu_percent(interval=None)

        metric = PerformanceMetric(
            timestamp=current_time,
            generation_id=generation_id,
            generation_type=generation_type,
            prompt_length=len(generation_params.get("prompt", "")),
            model_name=generation_params.get("model", "unknown"),
            width=generation_params.get("width", 512),
            height=generation_params.get("height", 512),
            steps=generation_params.get("steps", 20),
            cfg_scale=generation_params.get("cfg", 7.0),
            sampler=generation_params.get("sampler", "unknown"),
            batch_size=generation_params.get("batch_size", 1),
            total_time_seconds=0,
            queue_time_seconds=0,
            generation_time_seconds=0,
            vae_decode_time_seconds=0,
            vram_used_mb=gpu_stats["used_mb"],
            vram_peak_mb=gpu_stats["used_mb"],
            gpu_utilization_percent=gpu_stats["utilization"],
            cpu_usage_percent=cpu_usage,
            temperature_celsius=gpu_stats["temperature"],
            output_file_size_mb=0,
            quality_score=0,
            used_cache=generation_params.get("used_cache", False),
            optimization_level=generation_params.get("optimization_level", "standard")
        )

        self.current_metrics[generation_id] = metric
        self.monitoring_active = True

        logger.info(f"Started monitoring generation {generation_id}")

    def update_monitoring(self, generation_id: str, phase: str,
                         additional_data: Optional[Dict] = None):
        """Update monitoring for a specific generation phase"""

        if generation_id not in self.current_metrics:
            logger.warning(f"Generation {generation_id} not found in current metrics")
            return

        metric = self.current_metrics[generation_id]
        current_time = time.time()

        # Update based on phase
        if phase == "queue_complete":
            metric.queue_time_seconds = current_time - metric.timestamp

        elif phase == "generation_complete":
            metric.generation_time_seconds = current_time - metric.timestamp - metric.queue_time_seconds

        elif phase == "vae_decode_complete":
            metric.vae_decode_time_seconds = current_time - (
                metric.timestamp + metric.queue_time_seconds + metric.generation_time_seconds
            )

        # Update resource usage
        gpu_stats = self._get_gpu_stats()
        metric.vram_peak_mb = max(metric.vram_peak_mb, gpu_stats["used_mb"])
        metric.gpu_utilization_percent = max(
            metric.gpu_utilization_percent, gpu_stats["utilization"]
        )
        metric.temperature_celsius = max(
            metric.temperature_celsius, gpu_stats["temperature"]
        )

        # Add any additional data
        if additional_data:
            if "output_file_size_mb" in additional_data:
                metric.output_file_size_mb = additional_data["output_file_size_mb"]
            if "quality_score" in additional_data:
                metric.quality_score = additional_data["quality_score"]

    def complete_monitoring(self, generation_id: str, success: bool = True,
                           output_path: Optional[str] = None) -> PerformanceMetric:
        """Complete monitoring and save results"""

        if generation_id not in self.current_metrics:
            logger.warning(f"Generation {generation_id} not found in current metrics")
            return None

        metric = self.current_metrics[generation_id]
        current_time = time.time()

        # Calculate total time
        metric.total_time_seconds = current_time - metric.timestamp

        # Calculate output file size if path provided
        if output_path and Path(output_path).exists():
            file_size_bytes = Path(output_path).stat().st_size
            metric.output_file_size_mb = file_size_bytes / (1024 * 1024)

        # Save to database
        if success:
            self._save_metric_to_db(metric)

        # Analyze for bottlenecks
        bottlenecks = self._analyze_bottlenecks(metric)
        for bottleneck in bottlenecks:
            self._save_bottleneck_to_db(generation_id, bottleneck)

        # Clean up
        del self.current_metrics[generation_id]

        # Log performance summary
        self._log_performance_summary(metric, bottlenecks)

        return metric

    def _get_gpu_stats(self) -> Dict[str, Any]:
        """Get current GPU statistics"""
        try:
            result = subprocess.run([
                'nvidia-smi',
                '--query-gpu=memory.used,utilization.gpu,temperature.gpu',
                '--format=csv,nounits,noheader'
            ], capture_output=True, text=True, check=True)

            values = result.stdout.strip().split(',')
            return {
                "used_mb": int(values[0]),
                "utilization": float(values[1]),
                "temperature": int(values[2])
            }
        except Exception as e:
            logger.error(f"Failed to get GPU stats: {e}")
            return {"used_mb": 0, "utilization": 0, "temperature": 0}

    def _save_metric_to_db(self, metric: PerformanceMetric):
        """Save performance metric to database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO performance_metrics (
                    timestamp, generation_id, generation_type, prompt_length,
                    model_name, width, height, steps, cfg_scale, sampler, batch_size,
                    total_time_seconds, queue_time_seconds, generation_time_seconds,
                    vae_decode_time_seconds, vram_used_mb, vram_peak_mb,
                    gpu_utilization_percent, cpu_usage_percent, temperature_celsius,
                    output_file_size_mb, quality_score, used_cache, optimization_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                metric.timestamp, metric.generation_id, metric.generation_type,
                metric.prompt_length, metric.model_name, metric.width, metric.height,
                metric.steps, metric.cfg_scale, metric.sampler, metric.batch_size,
                metric.total_time_seconds, metric.queue_time_seconds,
                metric.generation_time_seconds, metric.vae_decode_time_seconds,
                metric.vram_used_mb, metric.vram_peak_mb,
                metric.gpu_utilization_percent, metric.cpu_usage_percent,
                metric.temperature_celsius, metric.output_file_size_mb,
                metric.quality_score, 1 if metric.used_cache else 0,
                metric.optimization_level
            ))

    def _save_bottleneck_to_db(self, generation_id: str, bottleneck: BottleneckAnalysis):
        """Save bottleneck analysis to database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO bottleneck_events (
                    timestamp, generation_id, bottleneck_type, severity,
                    description, recommendation
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                time.time(), generation_id, bottleneck.bottleneck_type,
                bottleneck.severity, bottleneck.description, bottleneck.recommendation
            ))

    def _analyze_bottlenecks(self, metric: PerformanceMetric) -> List[BottleneckAnalysis]:
        """Analyze performance metric for bottlenecks"""
        bottlenecks = []

        # Check generation time vs target
        target_time = self.thresholds["target_generation_time"][metric.optimization_level]
        if metric.total_time_seconds > target_time * 1.5:  # 50% over target
            severity = "high" if metric.total_time_seconds > target_time * 2 else "medium"
            bottlenecks.append(BottleneckAnalysis(
                bottleneck_type="generation_time",
                severity=severity,
                description=f"Generation took {metric.total_time_seconds:.1f}s vs target {target_time}s",
                recommendation="Consider using draft mode or optimizing workflow parameters",
                estimated_improvement="30-60% faster generation"
            ))

        # Check VRAM usage
        if metric.vram_peak_mb > self.thresholds["vram_warning_mb"]:
            severity = "critical" if metric.vram_peak_mb > 11500 else "high"
            bottlenecks.append(BottleneckAnalysis(
                bottleneck_type="vram",
                severity=severity,
                description=f"Peak VRAM usage: {metric.vram_peak_mb}MB",
                recommendation="Reduce resolution, enable VAE tiling, or use smaller batch size",
                estimated_improvement="20-40% VRAM reduction"
            ))

        # Check GPU utilization
        if metric.gpu_utilization_percent < self.thresholds["gpu_utilization_low"]:
            bottlenecks.append(BottleneckAnalysis(
                bottleneck_type="gpu_underutilization",
                severity="medium",
                description=f"Low GPU utilization: {metric.gpu_utilization_percent}%",
                recommendation="Increase batch size or resolution to better utilize GPU",
                estimated_improvement="Better hardware utilization"
            ))

        # Check temperature
        if metric.temperature_celsius > self.thresholds["temperature_warning"]:
            severity = "critical" if metric.temperature_celsius > 85 else "high"
            bottlenecks.append(BottleneckAnalysis(
                bottleneck_type="temperature",
                severity=severity,
                description=f"High GPU temperature: {metric.temperature_celsius}°C",
                recommendation="Improve cooling or reduce workload intensity",
                estimated_improvement="Prevent thermal throttling"
            ))

        # Check queue time
        if metric.queue_time_seconds > self.thresholds["queue_time_warning"]:
            bottlenecks.append(BottleneckAnalysis(
                bottleneck_type="queue",
                severity="medium",
                description=f"Long queue time: {metric.queue_time_seconds:.1f}s",
                recommendation="Implement better queue management or add more workers",
                estimated_improvement="Reduced waiting time"
            ))

        return bottlenecks

    def _log_performance_summary(self, metric: PerformanceMetric,
                                bottlenecks: List[BottleneckAnalysis]):
        """Log performance summary"""

        logger.info(
            f"Generation {metric.generation_id} completed: "
            f"{metric.total_time_seconds:.1f}s total, "
            f"VRAM peak: {metric.vram_peak_mb}MB, "
            f"GPU: {metric.gpu_utilization_percent:.1f}%, "
            f"Quality: {metric.quality_score:.1f}"
        )

        if bottlenecks:
            for bottleneck in bottlenecks:
                logger.warning(
                    f"Bottleneck detected [{bottleneck.severity}]: "
                    f"{bottleneck.description} - {bottleneck.recommendation}"
                )

    def get_performance_report(self, hours: int = 24) -> PerformanceReport:
        """Generate comprehensive performance report"""

        cutoff_time = time.time() - (hours * 3600)

        with sqlite3.connect(self.db_path) as conn:
            # Get metrics from specified time period
            cursor = conn.execute('''
                SELECT * FROM performance_metrics
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
            ''', (cutoff_time,))

            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            if not rows:
                return PerformanceReport(
                    period_start=cutoff_time,
                    period_end=time.time(),
                    total_generations=0,
                    avg_generation_time=0,
                    min_generation_time=0,
                    max_generation_time=0,
                    p95_generation_time=0,
                    avg_vram_usage=0,
                    peak_vram_usage=0,
                    avg_gpu_utilization=0,
                    avg_temperature=0,
                    generations_per_hour=0,
                    cache_hit_rate=0,
                    failure_rate=0,
                    bottlenecks=[],
                    recommendations=[]
                )

            # Convert to list of dicts
            metrics = [dict(zip(columns, row)) for row in rows]

            # Calculate statistics
            generation_times = [m["total_time_seconds"] for m in metrics]
            vram_usage = [m["vram_peak_mb"] for m in metrics]
            gpu_utilization = [m["gpu_utilization_percent"] for m in metrics]
            temperatures = [m["temperature_celsius"] for m in metrics]
            cache_usage = [m["used_cache"] for m in metrics]

            # Get bottlenecks from the period
            bottleneck_cursor = conn.execute('''
                SELECT bottleneck_type, severity, description, recommendation
                FROM bottleneck_events
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
            ''', (cutoff_time,))

            bottleneck_rows = bottleneck_cursor.fetchall()
            bottlenecks = [
                BottleneckAnalysis(
                    bottleneck_type=row[0],
                    severity=row[1],
                    description=row[2],
                    recommendation=row[3],
                    estimated_improvement="See recommendation"
                )
                for row in bottleneck_rows
            ]

            # Generate recommendations
            recommendations = self._generate_recommendations(metrics, bottlenecks)

            return PerformanceReport(
                period_start=cutoff_time,
                period_end=time.time(),
                total_generations=len(metrics),
                avg_generation_time=statistics.mean(generation_times),
                min_generation_time=min(generation_times) if generation_times else 0,
                max_generation_time=max(generation_times) if generation_times else 0,
                p95_generation_time=self._percentile(generation_times, 95),
                avg_vram_usage=statistics.mean(vram_usage) if vram_usage else 0,
                peak_vram_usage=max(vram_usage) if vram_usage else 0,
                avg_gpu_utilization=statistics.mean(gpu_utilization) if gpu_utilization else 0,
                avg_temperature=statistics.mean(temperatures) if temperatures else 0,
                generations_per_hour=len(metrics) / hours,
                cache_hit_rate=sum(cache_usage) / len(cache_usage) * 100 if cache_usage else 0,
                failure_rate=0,  # Would need failure tracking
                bottlenecks=bottlenecks[-10:],  # Last 10 bottlenecks
                recommendations=recommendations
            )

    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of data"""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(percentile / 100 * len(sorted_data))
        return sorted_data[min(index, len(sorted_data) - 1)]

    def _generate_recommendations(self, metrics: List[Dict],
                                bottlenecks: List[BottleneckAnalysis]) -> List[str]:
        """Generate optimization recommendations based on analysis"""
        recommendations = []

        if not metrics:
            return recommendations

        # Analyze common patterns
        avg_generation_time = statistics.mean([m["total_time_seconds"] for m in metrics])
        avg_vram = statistics.mean([m["vram_peak_mb"] for m in metrics])

        # Time-based recommendations
        if avg_generation_time > 60:
            recommendations.append(
                "Consider using draft mode (8 steps) for faster iterations, "
                "then high-quality mode only for final outputs"
            )

        # VRAM-based recommendations
        if avg_vram > 8000:
            recommendations.append(
                "High VRAM usage detected. Enable VAE tiling for large images "
                "or reduce batch sizes"
            )

        # Model-based recommendations
        model_usage = {}
        for metric in metrics:
            model = metric["model_name"]
            model_usage[model] = model_usage.get(model, 0) + 1

        if model_usage:
            most_used_model = max(model_usage, key=model_usage.get)
            if "xl" not in most_used_model.lower() and avg_generation_time > 45:
                recommendations.append(
                    f"Consider switching to faster models like AOM3A1B.safetensors "
                    f"instead of {most_used_model} for routine work"
                )

        # Bottleneck-based recommendations
        bottleneck_types = [b.bottleneck_type for b in bottlenecks]
        if bottleneck_types.count("vram") > 3:
            recommendations.append(
                "Frequent VRAM bottlenecks detected. Consider implementing "
                "model caching or reducing concurrent generations"
            )

        return recommendations[:5]  # Return top 5 recommendations

    def export_metrics(self, output_path: str, hours: int = 24) -> str:
        """Export metrics to JSON file"""

        cutoff_time = time.time() - (hours * 3600)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM performance_metrics
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
            ''', (cutoff_time,))

            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            metrics = [dict(zip(columns, row)) for row in rows]

        # Generate report
        report = self.get_performance_report(hours)

        export_data = {
            "export_timestamp": time.time(),
            "period_hours": hours,
            "summary": asdict(report),
            "detailed_metrics": metrics
        }

        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Exported {len(metrics)} metrics to {output_path}")
        return output_path


# Factory function
def get_performance_monitor() -> PerformanceMonitor:
    """Get configured performance monitor instance"""
    return PerformanceMonitor()


# Example usage
if __name__ == "__main__":
    async def test_monitor():
        monitor = get_performance_monitor()

        # Simulate monitoring a generation
        generation_id = "test_001"
        params = {
            "prompt": "anime girl with blue hair",
            "model": "counterfeit_v3.safetensors",
            "width": 768,
            "height": 768,
            "steps": 15,
            "cfg": 6.5,
            "sampler": "dpmpp_2m",
            "optimization_level": "standard"
        }

        monitor.start_monitoring(generation_id, "image", params)

        # Simulate generation phases
        await asyncio.sleep(1)
        monitor.update_monitoring(generation_id, "queue_complete")

        await asyncio.sleep(2)
        monitor.update_monitoring(generation_id, "generation_complete")

        await asyncio.sleep(0.5)
        monitor.update_monitoring(generation_id, "vae_decode_complete")

        # Complete monitoring
        metric = monitor.complete_monitoring(generation_id, success=True)

        print(f"Monitored generation: {metric.total_time_seconds:.1f}s total")

        # Generate report
        report = monitor.get_performance_report(hours=1)
        print(f"Performance report: {report.total_generations} generations")

    asyncio.run(test_monitor())