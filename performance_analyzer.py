#!/usr/bin/env python3
"""
Performance Analysis and Trend Detection System
Advanced analytics for identifying performance patterns, bottlenecks, and optimization opportunities.
"""

import logging
import json
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import psycopg2
from psycopg2.extras import RealDictCursor
import numpy as np
import pandas as pd
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class BottleneckType(Enum):
    """Types of performance bottlenecks"""
    GPU_UNDERUTILIZATION = "gpu_underutilization"
    HIGH_QUEUE_TIME = "high_queue_time"
    MEMORY_CONSTRAINT = "memory_constraint"
    CPU_BOTTLENECK = "cpu_bottleneck"
    HIGH_FAILURE_RATE = "high_failure_rate"
    SLOW_INITIALIZATION = "slow_initialization"
    RESOURCE_CONTENTION = "resource_contention"
    SUBOPTIMAL_PARAMETERS = "suboptimal_parameters"

class TrendDirection(Enum):
    """Performance trend directions"""
    IMPROVING = "improving"
    DEGRADING = "degrading"
    STABLE = "stable"
    VOLATILE = "volatile"

@dataclass
class PerformanceBottleneck:
    """Represents a performance bottleneck"""
    type: BottleneckType
    severity: float  # 0-1 scale
    affected_jobs: int
    description: str
    recommendations: List[str]
    metric_values: Dict[str, float]

@dataclass
class PerformanceTrend:
    """Represents a performance trend"""
    metric: str
    direction: TrendDirection
    change_rate: float  # Change per day
    confidence: float   # 0-1 scale
    period_days: int
    current_value: float
    predicted_value_7d: float

@dataclass
class OptimizationOpportunity:
    """Represents an optimization opportunity"""
    area: str
    potential_improvement: float  # Percentage improvement
    effort_required: str  # low, medium, high
    description: str
    implementation_steps: List[str]
    expected_impact: str

class PerformanceAnalyzer:
    """Advanced performance analysis and trend detection"""

    def __init__(self, db_config: Dict[str, str]):
        self.db_config = db_config
        self.thresholds = {
            'slow_generation_image': 120.0,  # seconds
            'slow_generation_video': 300.0,  # seconds
            'low_gpu_utilization': 60.0,     # percentage
            'high_cpu_usage': 80.0,          # percentage
            'high_failure_rate': 0.1,        # 10% failure rate
            'high_queue_time': 30.0,         # seconds
            'memory_efficiency_threshold': 0.8  # 80% memory usage
        }

    def connect_db(self):
        """Create database connection"""
        return psycopg2.connect(
            host=self.db_config['host'],
            port=self.db_config['port'],
            database=self.db_config['database'],
            user=self.db_config['user'],
            password=self.db_config['password']
        )

    def analyze_bottlenecks(self, days_back: int = 7) -> List[PerformanceBottleneck]:
        """Identify performance bottlenecks in recent data"""
        with self.connect_db() as conn:
            query = """
            SELECT
                pipeline_type,
                total_time_seconds,
                gpu_utilization_avg,
                cpu_utilization_avg,
                vram_used_mb,
                vram_total_mb,
                queue_time_seconds,
                initialization_time_seconds,
                processing_time_seconds,
                error_details,
                frame_count,
                resolution,
                created_at
            FROM anime_api.generation_performance
            WHERE created_at >= %s
            AND total_time_seconds IS NOT NULL
            ORDER BY created_at DESC
            """

            df = pd.read_sql(query, conn, params=[datetime.now() - timedelta(days=days_back)])

            if df.empty:
                return []

            bottlenecks = []

            # Analyze GPU utilization
            gpu_bottleneck = self._analyze_gpu_utilization(df)
            if gpu_bottleneck:
                bottlenecks.append(gpu_bottleneck)

            # Analyze generation times
            time_bottlenecks = self._analyze_generation_times(df)
            bottlenecks.extend(time_bottlenecks)

            # Analyze failure rates
            failure_bottleneck = self._analyze_failure_rates(df)
            if failure_bottleneck:
                bottlenecks.append(failure_bottleneck)

            # Analyze queue times
            queue_bottleneck = self._analyze_queue_times(df)
            if queue_bottleneck:
                bottlenecks.append(queue_bottleneck)

            # Analyze memory usage
            memory_bottleneck = self._analyze_memory_usage(df)
            if memory_bottleneck:
                bottlenecks.append(memory_bottleneck)

            # Analyze resource contention
            contention_bottleneck = self._analyze_resource_contention(df)
            if contention_bottleneck:
                bottlenecks.append(contention_bottleneck)

            return sorted(bottlenecks, key=lambda x: x.severity, reverse=True)

    def _analyze_gpu_utilization(self, df: pd.DataFrame) -> Optional[PerformanceBottleneck]:
        """Analyze GPU utilization patterns"""
        gpu_data = df[df['gpu_utilization_avg'].notna()]
        if gpu_data.empty:
            return None

        avg_gpu_util = gpu_data['gpu_utilization_avg'].mean()
        low_util_jobs = len(gpu_data[gpu_data['gpu_utilization_avg'] < self.thresholds['low_gpu_utilization']])

        if avg_gpu_util < self.thresholds['low_gpu_utilization']:
            severity = 1.0 - (avg_gpu_util / 100.0)

            recommendations = [
                "Increase batch size if memory allows",
                "Use more complex models or higher quality settings",
                "Check for CPU bottlenecks limiting GPU utilization",
                "Consider running multiple concurrent jobs"
            ]

            return PerformanceBottleneck(
                type=BottleneckType.GPU_UNDERUTILIZATION,
                severity=severity,
                affected_jobs=low_util_jobs,
                description=f"GPU utilization averaging {avg_gpu_util:.1f}% (below {self.thresholds['low_gpu_utilization']:.1f}% threshold)",
                recommendations=recommendations,
                metric_values={'avg_gpu_utilization': avg_gpu_util, 'threshold': self.thresholds['low_gpu_utilization']}
            )

        return None

    def _analyze_generation_times(self, df: pd.DataFrame) -> List[PerformanceBottleneck]:
        """Analyze generation time patterns"""
        bottlenecks = []

        for pipeline_type in df['pipeline_type'].unique():
            pipeline_data = df[df['pipeline_type'] == pipeline_type]
            threshold = self.thresholds[f'slow_generation_{pipeline_type}']

            avg_time = pipeline_data['total_time_seconds'].mean()
            slow_jobs = len(pipeline_data[pipeline_data['total_time_seconds'] > threshold])

            if avg_time > threshold:
                severity = min(1.0, (avg_time - threshold) / threshold)

                recommendations = self._get_time_optimization_recommendations(pipeline_type, pipeline_data)

                bottlenecks.append(PerformanceBottleneck(
                    type=BottleneckType.SUBOPTIMAL_PARAMETERS,
                    severity=severity,
                    affected_jobs=slow_jobs,
                    description=f"{pipeline_type.title()} generation averaging {avg_time:.1f}s (above {threshold:.1f}s threshold)",
                    recommendations=recommendations,
                    metric_values={'avg_time': avg_time, 'threshold': threshold, 'pipeline_type': pipeline_type}
                ))

        return bottlenecks

    def _get_time_optimization_recommendations(self, pipeline_type: str, data: pd.DataFrame) -> List[str]:
        """Get time optimization recommendations based on data analysis"""
        recommendations = []

        # Analyze step counts
        if 'steps' in data.columns and data['steps'].notna().any():
            avg_steps = data['steps'].mean()
            if avg_steps > 30:
                recommendations.append(f"Consider reducing step count (currently averaging {avg_steps:.1f})")

        # Analyze resolution
        if 'resolution' in data.columns:
            high_res_jobs = data[data['resolution'].str.contains('1024|2048|4096', na=False)]
            if len(high_res_jobs) > len(data) * 0.3:
                recommendations.append("High resolution jobs detected. Consider generating at lower resolution and upscaling")

        # Pipeline-specific recommendations
        if pipeline_type == 'video':
            if 'frame_count' in data.columns and data['frame_count'].notna().any():
                avg_frames = data['frame_count'].mean()
                if avg_frames > 60:
                    recommendations.append("Consider breaking long videos into shorter segments")
        else:
            recommendations.append("Optimize image generation parameters for faster processing")

        if not recommendations:
            recommendations.append("Review generation parameters and consider hardware upgrades")

        return recommendations

    def _analyze_failure_rates(self, df: pd.DataFrame) -> Optional[PerformanceBottleneck]:
        """Analyze job failure patterns"""
        total_jobs = len(df)
        if total_jobs == 0:
            return None

        # Count jobs with errors
        error_jobs = len(df[df['error_details'].notna() & (df['error_details'].astype(str) != '{}')])
        failure_rate = error_jobs / total_jobs

        if failure_rate > self.thresholds['high_failure_rate']:
            severity = min(1.0, failure_rate / 0.5)  # Cap at 50% failure rate for severity calculation

            recommendations = [
                "Review error logs to identify common failure patterns",
                "Validate input parameters and reduce complexity if needed",
                "Check system resources and GPU memory availability",
                "Implement more robust error handling and retries"
            ]

            return PerformanceBottleneck(
                type=BottleneckType.HIGH_FAILURE_RATE,
                severity=severity,
                affected_jobs=error_jobs,
                description=f"High failure rate: {failure_rate:.1%} of jobs failing",
                recommendations=recommendations,
                metric_values={'failure_rate': failure_rate, 'threshold': self.thresholds['high_failure_rate']}
            )

        return None

    def _analyze_queue_times(self, df: pd.DataFrame) -> Optional[PerformanceBottleneck]:
        """Analyze job queue time patterns"""
        queue_data = df[df['queue_time_seconds'].notna()]
        if queue_data.empty:
            return None

        avg_queue_time = queue_data['queue_time_seconds'].mean()
        high_queue_jobs = len(queue_data[queue_data['queue_time_seconds'] > self.thresholds['high_queue_time']])

        if avg_queue_time > self.thresholds['high_queue_time']:
            severity = min(1.0, avg_queue_time / 120.0)  # Cap at 2 minutes for severity

            recommendations = [
                "Increase processing capacity or optimize job scheduling",
                "Implement job priority queuing for urgent tasks",
                "Consider distributing load across multiple GPUs",
                "Optimize job batching and resource allocation"
            ]

            return PerformanceBottleneck(
                type=BottleneckType.HIGH_QUEUE_TIME,
                severity=severity,
                affected_jobs=high_queue_jobs,
                description=f"High queue times: averaging {avg_queue_time:.1f}s",
                recommendations=recommendations,
                metric_values={'avg_queue_time': avg_queue_time, 'threshold': self.thresholds['high_queue_time']}
            )

        return None

    def _analyze_memory_usage(self, df: pd.DataFrame) -> Optional[PerformanceBottleneck]:
        """Analyze memory usage patterns"""
        memory_data = df[(df['vram_used_mb'].notna()) & (df['vram_total_mb'].notna())]
        if memory_data.empty:
            return None

        memory_data = memory_data.copy()
        memory_data['memory_utilization'] = memory_data['vram_used_mb'] / memory_data['vram_total_mb']

        avg_memory_util = memory_data['memory_utilization'].mean()
        high_memory_jobs = len(memory_data[memory_data['memory_utilization'] > 0.9])

        if avg_memory_util > self.thresholds['memory_efficiency_threshold']:
            severity = min(1.0, (avg_memory_util - self.thresholds['memory_efficiency_threshold']) * 5)

            recommendations = [
                "Memory usage is high. Consider reducing batch size or resolution",
                "Monitor for out-of-memory errors",
                "Consider upgrading to GPU with more VRAM",
                "Implement memory-efficient generation techniques"
            ]

            return PerformanceBottleneck(
                type=BottleneckType.MEMORY_CONSTRAINT,
                severity=severity,
                affected_jobs=high_memory_jobs,
                description=f"High memory utilization: {avg_memory_util:.1%} average",
                recommendations=recommendations,
                metric_values={'avg_memory_utilization': avg_memory_util, 'threshold': self.thresholds['memory_efficiency_threshold']}
            )

        return None

    def _analyze_resource_contention(self, df: pd.DataFrame) -> Optional[PerformanceBottleneck]:
        """Analyze resource contention patterns"""
        cpu_data = df[df['cpu_utilization_avg'].notna()]
        if cpu_data.empty:
            return None

        avg_cpu_util = cpu_data['cpu_utilization_avg'].mean()
        high_cpu_jobs = len(cpu_data[cpu_data['cpu_utilization_avg'] > self.thresholds['high_cpu_usage']])

        if avg_cpu_util > self.thresholds['high_cpu_usage']:
            severity = min(1.0, (avg_cpu_util - self.thresholds['high_cpu_usage']) / 20.0)

            recommendations = [
                "High CPU usage detected. Check for CPU-intensive preprocessing",
                "Consider optimizing data loading and preprocessing pipelines",
                "Monitor for resource contention with other processes",
                "Implement asynchronous processing where possible"
            ]

            return PerformanceBottleneck(
                type=BottleneckType.CPU_BOTTLENECK,
                severity=severity,
                affected_jobs=high_cpu_jobs,
                description=f"High CPU utilization: {avg_cpu_util:.1f}% average",
                recommendations=recommendations,
                metric_values={'avg_cpu_utilization': avg_cpu_util, 'threshold': self.thresholds['high_cpu_usage']}
            )

        return None

    def analyze_trends(self, days_back: int = 30) -> List[PerformanceTrend]:
        """Analyze performance trends over time"""
        with self.connect_db() as conn:
            query = """
            SELECT
                DATE(created_at) as date,
                pipeline_type,
                AVG(total_time_seconds) as avg_time,
                AVG(gpu_utilization_avg) as avg_gpu_util,
                AVG(cpu_utilization_avg) as avg_cpu_util,
                COUNT(*) as job_count,
                COUNT(CASE WHEN error_details::text != '{}' THEN 1 END) as error_count
            FROM anime_api.generation_performance
            WHERE created_at >= %s
            AND total_time_seconds IS NOT NULL
            GROUP BY DATE(created_at), pipeline_type
            ORDER BY date, pipeline_type
            """

            df = pd.read_sql(query, conn, params=[datetime.now() - timedelta(days=days_back)])

            if df.empty:
                return []

            trends = []

            # Analyze trends for each pipeline type
            for pipeline_type in df['pipeline_type'].unique():
                pipeline_data = df[df['pipeline_type'] == pipeline_type].copy()
                pipeline_data['date'] = pd.to_datetime(pipeline_data['date'])
                pipeline_data = pipeline_data.sort_values('date')

                # Generation time trend
                time_trend = self._calculate_trend(
                    pipeline_data['avg_time'].values,
                    f"{pipeline_type}_generation_time",
                    len(pipeline_data),
                    pipeline_data['avg_time'].iloc[-1] if len(pipeline_data) > 0 else 0
                )
                if time_trend:
                    trends.append(time_trend)

                # GPU utilization trend
                gpu_data = pipeline_data.dropna(subset=['avg_gpu_util'])
                if not gpu_data.empty:
                    gpu_trend = self._calculate_trend(
                        gpu_data['avg_gpu_util'].values,
                        f"{pipeline_type}_gpu_utilization",
                        len(gpu_data),
                        gpu_data['avg_gpu_util'].iloc[-1]
                    )
                    if gpu_trend:
                        trends.append(gpu_trend)

                # Success rate trend
                pipeline_data['success_rate'] = 1 - (pipeline_data['error_count'] / pipeline_data['job_count'])
                success_trend = self._calculate_trend(
                    pipeline_data['success_rate'].values,
                    f"{pipeline_type}_success_rate",
                    len(pipeline_data),
                    pipeline_data['success_rate'].iloc[-1] if len(pipeline_data) > 0 else 0
                )
                if success_trend:
                    trends.append(success_trend)

            return trends

    def _calculate_trend(self, values: np.ndarray, metric_name: str,
                        period_days: int, current_value: float) -> Optional[PerformanceTrend]:
        """Calculate trend statistics for a metric"""
        if len(values) < 3:
            return None

        # Calculate linear regression
        x = np.arange(len(values))
        slope, intercept = np.polyfit(x, values, 1)

        # Determine trend direction
        if abs(slope) < 0.01:  # Very small change
            direction = TrendDirection.STABLE
        elif slope > 0:
            if 'time' in metric_name.lower():
                direction = TrendDirection.DEGRADING  # Increasing time is bad
            else:
                direction = TrendDirection.IMPROVING  # Increasing utilization/success is good
        else:
            if 'time' in metric_name.lower():
                direction = TrendDirection.IMPROVING  # Decreasing time is good
            else:
                direction = TrendDirection.DEGRADING  # Decreasing utilization/success is bad

        # Calculate volatility
        volatility = np.std(values) / np.mean(values) if np.mean(values) > 0 else 0
        if volatility > 0.3:
            direction = TrendDirection.VOLATILE

        # Calculate confidence based on R-squared
        y_pred = slope * x + intercept
        ss_res = np.sum((values - y_pred) ** 2)
        ss_tot = np.sum((values - np.mean(values)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        confidence = max(0, min(1, r_squared))

        # Predict value in 7 days
        predicted_value_7d = slope * (len(values) + 7) + intercept

        return PerformanceTrend(
            metric=metric_name,
            direction=direction,
            change_rate=slope,
            confidence=confidence,
            period_days=period_days,
            current_value=current_value,
            predicted_value_7d=predicted_value_7d
        )

    def identify_optimization_opportunities(self, bottlenecks: List[PerformanceBottleneck],
                                          trends: List[PerformanceTrend]) -> List[OptimizationOpportunity]:
        """Identify optimization opportunities based on bottlenecks and trends"""
        opportunities = []

        # GPU optimization opportunities
        gpu_bottlenecks = [b for b in bottlenecks if b.type == BottleneckType.GPU_UNDERUTILIZATION]
        if gpu_bottlenecks:
            gpu_bottleneck = gpu_bottlenecks[0]
            potential_improvement = (100 - gpu_bottleneck.metric_values['avg_gpu_utilization']) / 2
            opportunities.append(OptimizationOpportunity(
                area="GPU Utilization",
                potential_improvement=potential_improvement,
                effort_required="medium",
                description="Increase GPU utilization through parameter optimization",
                implementation_steps=[
                    "Analyze current generation parameters",
                    "Increase batch size or complexity",
                    "Implement concurrent job processing",
                    "Monitor GPU memory usage"
                ],
                expected_impact="Significant reduction in generation times"
            ))

        # Time optimization opportunities
        time_bottlenecks = [b for b in bottlenecks if 'time' in str(b.type).lower()]
        if time_bottlenecks:
            time_bottleneck = time_bottlenecks[0]
            potential_improvement = min(50, time_bottleneck.severity * 30)
            opportunities.append(OptimizationOpportunity(
                area="Generation Speed",
                potential_improvement=potential_improvement,
                effort_required="low",
                description="Optimize generation parameters and preprocessing",
                implementation_steps=[
                    "Review and optimize generation parameters",
                    "Implement caching for repeated operations",
                    "Optimize preprocessing pipelines",
                    "Consider model optimization techniques"
                ],
                expected_impact="Faster generation times and better resource utilization"
            ))

        # Memory optimization opportunities
        memory_bottlenecks = [b for b in bottlenecks if b.type == BottleneckType.MEMORY_CONSTRAINT]
        if memory_bottlenecks:
            opportunities.append(OptimizationOpportunity(
                area="Memory Management",
                potential_improvement=20.0,
                effort_required="medium",
                description="Optimize memory usage and prevent out-of-memory errors",
                implementation_steps=[
                    "Implement gradient checkpointing",
                    "Optimize batch sizes",
                    "Add memory monitoring and alerts",
                    "Consider model pruning techniques"
                ],
                expected_impact="More stable generation and ability to handle larger jobs"
            ))

        # Infrastructure opportunities
        if len(bottlenecks) > 3:
            opportunities.append(OptimizationOpportunity(
                area="Infrastructure Scaling",
                potential_improvement=40.0,
                effort_required="high",
                description="Scale infrastructure to handle increased workload",
                implementation_steps=[
                    "Assess current hardware limitations",
                    "Plan GPU/CPU upgrade path",
                    "Implement distributed processing",
                    "Add load balancing and auto-scaling"
                ],
                expected_impact="Significant improvement in overall system capacity and performance"
            ))

        return opportunities

    def generate_performance_report(self, days_back: int = 7) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        try:
            # Analyze bottlenecks
            bottlenecks = self.analyze_bottlenecks(days_back)

            # Analyze trends
            trends = self.analyze_trends(min(days_back * 2, 30))

            # Identify optimization opportunities
            opportunities = self.identify_optimization_opportunities(bottlenecks, trends)

            # Get overall statistics
            with self.connect_db() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_jobs,
                        AVG(total_time_seconds) as avg_generation_time,
                        AVG(gpu_utilization_avg) as avg_gpu_utilization,
                        AVG(CASE WHEN error_details::text = '{}' THEN 1.0 ELSE 0.0 END) as success_rate,
                        MIN(created_at) as period_start,
                        MAX(created_at) as period_end
                    FROM anime_api.generation_performance
                    WHERE created_at >= %s
                """, [datetime.now() - timedelta(days=days_back)])

                stats = cursor.fetchone()

            return {
                "report_generated": datetime.now().isoformat(),
                "analysis_period_days": days_back,
                "overall_statistics": dict(stats) if stats else {},
                "bottlenecks": [
                    {
                        "type": b.type.value,
                        "severity": b.severity,
                        "affected_jobs": b.affected_jobs,
                        "description": b.description,
                        "recommendations": b.recommendations,
                        "metrics": b.metric_values
                    }
                    for b in bottlenecks
                ],
                "trends": [
                    {
                        "metric": t.metric,
                        "direction": t.direction.value,
                        "change_rate": t.change_rate,
                        "confidence": t.confidence,
                        "current_value": t.current_value,
                        "predicted_value_7d": t.predicted_value_7d
                    }
                    for t in trends
                ],
                "optimization_opportunities": [
                    {
                        "area": o.area,
                        "potential_improvement": o.potential_improvement,
                        "effort_required": o.effort_required,
                        "description": o.description,
                        "implementation_steps": o.implementation_steps,
                        "expected_impact": o.expected_impact
                    }
                    for o in opportunities
                ],
                "summary": {
                    "critical_bottlenecks": len([b for b in bottlenecks if b.severity > 0.7]),
                    "improving_trends": len([t for t in trends if t.direction == TrendDirection.IMPROVING]),
                    "degrading_trends": len([t for t in trends if t.direction == TrendDirection.DEGRADING]),
                    "optimization_potential": sum([o.potential_improvement for o in opportunities])
                }
            }

        except Exception as e:
            logger.error(f"Error generating performance report: {e}")
            return {
                "error": str(e),
                "report_generated": datetime.now().isoformat()
            }


# Export the analyzer class
__all__ = ['PerformanceAnalyzer', 'BottleneckType', 'TrendDirection', 'PerformanceBottleneck', 'PerformanceTrend', 'OptimizationOpportunity']