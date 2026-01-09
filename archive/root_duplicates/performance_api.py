#!/usr/bin/env python3
"""
Performance Tracking and Prediction API
RESTful endpoints for anime generation performance analytics and ML predictions.
"""

import asyncio
import logging
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor
from performance_predictor import PerformancePredictor
import numpy as np

logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': '192.168.50.135',
    'port': 5432,
    'database': 'anime_production',
    'user': 'patrick',
    'password': 'tower_echo_brain_secret_key_2025'
}

# Initialize performance predictor
predictor = PerformancePredictor(DB_CONFIG)

# FastAPI router
router = APIRouter(prefix="/api/anime/performance", tags=["performance"])

# Pydantic models
class TimeEstimateRequest(BaseModel):
    """Request model for time estimation"""
    pipeline_type: str = Field(..., description="Type of generation pipeline", pattern="^(image|video)$")
    job_type: Optional[str] = Field(None, description="Type of job (e.g., 'character', 'scene', 'trailer')")
    resolution: str = Field("512x512", description="Output resolution")
    frame_count: Optional[int] = Field(1, description="Number of frames for video")
    steps: Optional[int] = Field(20, description="Number of generation steps")
    guidance_scale: Optional[float] = Field(7.5, description="CFG guidance scale")
    model_version: Optional[str] = Field(None, description="Model version to use")
    complexity_score: Optional[float] = Field(None, description="Estimated complexity (0-10)")

class TimeEstimateResponse(BaseModel):
    """Response model for time estimation"""
    predicted_time_seconds: float
    confidence: float
    prediction_method: str
    model_used: str
    uncertainty_range: List[float]
    recommendations: List[str] = []

class PerformanceMetrics(BaseModel):
    """Performance metrics for a completed job"""
    job_id: str
    pipeline_type: str
    total_time_seconds: float
    success: bool = True
    error_details: Optional[Dict] = None
    gpu_utilization_avg: Optional[float] = None
    gpu_utilization_peak: Optional[float] = None
    vram_used_mb: Optional[int] = None
    cpu_utilization_avg: Optional[float] = None
    memory_used_mb: Optional[int] = None
    queue_time_seconds: Optional[float] = None
    processing_time_seconds: Optional[float] = None

class PerformanceTrend(BaseModel):
    """Performance trend data"""
    date: str
    pipeline_type: str
    avg_generation_time: float
    median_generation_time: float
    success_rate: float
    total_jobs: int
    bottlenecks: List[str]
    recommendations: List[str]

class WeeklyReport(BaseModel):
    """Weekly performance report"""
    week_start: str
    week_end: str
    total_jobs: int
    total_generation_time: float
    avg_generation_time: float
    success_rate: float
    top_bottlenecks: List[str]
    performance_trends: List[PerformanceTrend]
    predictions_accuracy: Dict[str, float]

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        database=DB_CONFIG['database'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password']
    )

@router.post("/estimate-time", response_model=TimeEstimateResponse)
async def estimate_generation_time(request: TimeEstimateRequest):
    """
    Estimate generation time for given job parameters.
    Uses machine learning models trained on historical performance data.
    """
    try:
        # Load models if not already loaded
        for pipeline in ['image', 'video']:
            for model_type in ['random_forest', 'gradient_boosting']:
                try:
                    predictor.load_model_from_db(pipeline, model_type)
                except Exception as e:
                    logger.warning(f"Could not load {model_type} model for {pipeline}: {e}")

        # Convert request to dictionary
        job_params = request.dict()

        # Make prediction
        prediction = predictor.predict_generation_time(job_params)

        # Generate recommendations based on parameters
        recommendations = []
        if request.frame_count and request.frame_count > 120:
            recommendations.append("Consider breaking long videos into shorter segments for better performance")

        if request.resolution and 'x' in request.resolution:
            try:
                w, h = map(int, request.resolution.split('x'))
                if w * h > 1024 * 1024:
                    recommendations.append("High resolution may significantly increase generation time")
            except:
                pass

        if request.steps and request.steps > 50:
            recommendations.append("High step count will increase generation time. Consider reducing for faster results")

        prediction['recommendations'] = recommendations

        return TimeEstimateResponse(**prediction)

    except Exception as e:
        logger.error(f"Error estimating generation time: {e}")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")

@router.post("/record-metrics")
async def record_performance_metrics(metrics: PerformanceMetrics):
    """
    Record actual performance metrics for a completed job.
    This data is used to train and improve prediction models.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Insert performance metrics
                cursor.execute("""
                    INSERT INTO anime_api.generation_performance
                    (job_id, pipeline_type, total_time_seconds, queue_time_seconds,
                     processing_time_seconds, gpu_utilization_avg, gpu_utilization_peak,
                     vram_used_mb, cpu_utilization_avg, memory_used_mb, error_details,
                     success_rate, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (job_id) DO UPDATE SET
                    total_time_seconds = EXCLUDED.total_time_seconds,
                    processing_time_seconds = EXCLUDED.processing_time_seconds,
                    gpu_utilization_avg = EXCLUDED.gpu_utilization_avg,
                    error_details = EXCLUDED.error_details,
                    success_rate = EXCLUDED.success_rate
                """, (
                    metrics.job_id,
                    metrics.pipeline_type,
                    metrics.total_time_seconds,
                    metrics.queue_time_seconds,
                    metrics.processing_time_seconds,
                    metrics.gpu_utilization_avg,
                    metrics.gpu_utilization_peak,
                    metrics.vram_used_mb,
                    metrics.cpu_utilization_avg,
                    metrics.memory_used_mb,
                    json.dumps(metrics.error_details or {}),
                    1.0 if metrics.success else 0.0,
                    datetime.now()
                ))

                # Check for performance alerts
                if not metrics.success or (metrics.total_time_seconds and metrics.total_time_seconds > 300):
                    await _create_performance_alert(cursor, metrics)

                conn.commit()

        return {"message": "Performance metrics recorded successfully", "job_id": metrics.job_id}

    except Exception as e:
        logger.error(f"Error recording performance metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record metrics: {str(e)}")

@router.get("/trends", response_model=Dict[str, Any])
async def get_performance_trends(
    days_back: int = 7,
    pipeline_type: Optional[str] = None
):
    """
    Get performance trends and bottleneck analysis.
    Analyzes recent performance data to identify patterns and issues.
    """
    try:
        analysis = predictor.analyze_performance_trends(days_back)

        # If specific pipeline requested, filter results
        if pipeline_type and pipeline_type in analysis:
            analysis = {pipeline_type: analysis[pipeline_type]}

        return {
            "period_days": days_back,
            "analysis_date": datetime.now().isoformat(),
            "trends": analysis
        }

    except Exception as e:
        logger.error(f"Error analyzing performance trends: {e}")
        raise HTTPException(status_code=500, detail=f"Trend analysis failed: {str(e)}")

@router.get("/alerts")
async def get_performance_alerts(
    severity: Optional[str] = None,
    resolved: bool = False,
    limit: int = 50
):
    """
    Get recent performance alerts.
    Returns alerts for slow performance, failures, or resource bottlenecks.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                query = """
                    SELECT id, alert_type, severity, message, details,
                           threshold_value, actual_value, is_resolved,
                           created_at, resolved_at
                    FROM anime_api.performance_alerts
                    WHERE 1=1
                """
                params = []

                if severity:
                    query += " AND severity = %s"
                    params.append(severity)

                if not resolved:
                    query += " AND NOT is_resolved"

                query += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)

                cursor.execute(query, params)
                alerts = cursor.fetchall()

                return {
                    "alerts": [dict(alert) for alert in alerts],
                    "total_count": len(alerts)
                }

    except Exception as e:
        logger.error(f"Error fetching performance alerts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch alerts: {str(e)}")

@router.get("/weekly-report", response_model=WeeklyReport)
async def get_weekly_performance_report(weeks_back: int = 1):
    """
    Generate comprehensive weekly performance report.
    Includes statistics, trends, bottlenecks, and prediction accuracy.
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(weeks=weeks_back)

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get weekly statistics
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_jobs,
                        SUM(total_time_seconds) as total_time,
                        AVG(total_time_seconds) as avg_time,
                        AVG(CASE WHEN error_details::text = '{}' THEN 1.0 ELSE 0.0 END) as success_rate
                    FROM anime_api.generation_performance
                    WHERE created_at >= %s AND created_at <= %s
                """, (start_date, end_date))

                stats = cursor.fetchone()

                # Get daily trends
                cursor.execute("""
                    SELECT
                        DATE(created_at) as date,
                        pipeline_type,
                        AVG(total_time_seconds) as avg_time,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_time_seconds) as median_time,
                        AVG(CASE WHEN error_details::text = '{}' THEN 1.0 ELSE 0.0 END) as success_rate,
                        COUNT(*) as job_count
                    FROM anime_api.generation_performance
                    WHERE created_at >= %s AND created_at <= %s
                    GROUP BY DATE(created_at), pipeline_type
                    ORDER BY date, pipeline_type
                """, (start_date, end_date))

                daily_trends = cursor.fetchall()

                # Get prediction accuracy (if predictions were stored)
                cursor.execute("""
                    SELECT
                        pipeline_type,
                        AVG(ABS(predicted_time_seconds - total_time_seconds) / total_time_seconds) as avg_error
                    FROM anime_api.generation_performance
                    WHERE created_at >= %s AND created_at <= %s
                    AND predicted_time_seconds IS NOT NULL
                    GROUP BY pipeline_type
                """, (start_date, end_date))

                accuracy_data = cursor.fetchall()

        # Process trends
        trends = []
        bottlenecks_counter = {}

        for trend in daily_trends:
            # Identify bottlenecks (simplified logic)
            bottlenecks = []
            if trend['success_rate'] < 0.9:
                bottlenecks.append('high_failure_rate')
                bottlenecks_counter['high_failure_rate'] = bottlenecks_counter.get('high_failure_rate', 0) + 1

            if trend['avg_time'] > 180:  # > 3 minutes
                bottlenecks.append('slow_generation')
                bottlenecks_counter['slow_generation'] = bottlenecks_counter.get('slow_generation', 0) + 1

            trends.append(PerformanceTrend(
                date=str(trend['date']),
                pipeline_type=trend['pipeline_type'],
                avg_generation_time=float(trend['avg_time']),
                median_generation_time=float(trend['median_time']),
                success_rate=float(trend['success_rate']),
                total_jobs=int(trend['job_count']),
                bottlenecks=bottlenecks,
                recommendations=_get_trend_recommendations(bottlenecks)
            ))

        # Top bottlenecks
        top_bottlenecks = sorted(bottlenecks_counter.items(), key=lambda x: x[1], reverse=True)[:5]

        # Prediction accuracy
        predictions_accuracy = {}
        for acc in accuracy_data:
            predictions_accuracy[acc['pipeline_type']] = float(1 - acc['avg_error'])

        return WeeklyReport(
            week_start=start_date.strftime('%Y-%m-%d'),
            week_end=end_date.strftime('%Y-%m-%d'),
            total_jobs=stats['total_jobs'] or 0,
            total_generation_time=float(stats['total_time'] or 0),
            avg_generation_time=float(stats['avg_time'] or 0),
            success_rate=float(stats['success_rate'] or 0),
            top_bottlenecks=[item[0] for item in top_bottlenecks],
            performance_trends=trends,
            predictions_accuracy=predictions_accuracy
        )

    except Exception as e:
        logger.error(f"Error generating weekly report: {e}")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")

@router.post("/train-models")
async def train_prediction_models(background_tasks: BackgroundTasks):
    """
    Train machine learning models on recent performance data.
    This is typically run as a background task on a schedule.
    """
    background_tasks.add_task(_train_models_task)
    return {"message": "Model training started in background"}

@router.get("/model-status")
async def get_model_status():
    """
    Get status of trained prediction models.
    Returns information about available models and their performance.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT model_name, model_type, pipeline_type, accuracy_score,
                           mean_absolute_error, training_data_count, last_trained_at, is_active
                    FROM anime_api.performance_prediction_models
                    ORDER BY pipeline_type, model_type, last_trained_at DESC
                """)

                models = cursor.fetchall()

                return {
                    "models": [dict(model) for model in models],
                    "total_models": len(models)
                }

    except Exception as e:
        logger.error(f"Error fetching model status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch model status: {str(e)}")

# Helper functions
async def _create_performance_alert(cursor, metrics: PerformanceMetrics):
    """Create performance alert for slow or failed jobs"""
    if not metrics.success:
        cursor.execute("""
            INSERT INTO anime_api.performance_alerts
            (alert_type, severity, message, details, job_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            'job_failure',
            'high',
            f'Job {metrics.job_id} failed during {metrics.pipeline_type} generation',
            json.dumps(metrics.error_details or {}),
            metrics.job_id
        ))
    elif metrics.total_time_seconds and metrics.total_time_seconds > 300:
        cursor.execute("""
            INSERT INTO anime_api.performance_alerts
            (alert_type, severity, message, details, job_id, threshold_value, actual_value)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            'slow_generation',
            'medium',
            f'Slow {metrics.pipeline_type} generation detected',
            json.dumps({'job_id': metrics.job_id, 'pipeline_type': metrics.pipeline_type}),
            metrics.job_id,
            300.0,
            metrics.total_time_seconds
        ))

def _get_trend_recommendations(bottlenecks: List[str]) -> List[str]:
    """Get recommendations based on identified bottlenecks"""
    recommendations = []

    if 'high_failure_rate' in bottlenecks:
        recommendations.append("High failure rate detected. Review error logs and consider parameter adjustments.")

    if 'slow_generation' in bottlenecks:
        recommendations.append("Generation times are above average. Consider optimizing parameters or upgrading hardware.")

    if not bottlenecks:
        recommendations.append("Performance is within normal parameters.")

    return recommendations

async def _train_models_task():
    """Background task to train prediction models"""
    try:
        logger.info("Starting model training task")

        for pipeline_type in ['image', 'video']:
            for model_type in ['random_forest', 'gradient_boosting', 'linear_regression']:
                try:
                    metrics = predictor.train_model(pipeline_type, model_type)
                    predictor.save_model_to_db(pipeline_type, model_type)
                    logger.info(f"Trained and saved {model_type} model for {pipeline_type}")
                except Exception as e:
                    logger.error(f"Failed to train {model_type} for {pipeline_type}: {e}")

        logger.info("Model training task completed")

    except Exception as e:
        logger.error(f"Model training task failed: {e}")

# Export router for inclusion in main app
__all__ = ['router']