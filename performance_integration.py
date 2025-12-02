#!/usr/bin/env python3
"""
Performance Integration Module
Integrates performance tracking into the main anime production API.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from performance_api import router as performance_router
from performance_analyzer import PerformanceAnalyzer
from performance_middleware import performance_tracker, initialize_performance_monitoring
import psycopg2

logger = logging.getLogger(__name__)

# Database configuration for performance tracking
PERFORMANCE_DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'anime_production',
    'user': 'patrick',
    'password': 'tower_echo_brain_secret_key_2025'
}

# Initialize performance analyzer
analyzer = PerformanceAnalyzer(PERFORMANCE_DB_CONFIG)

# Create additional performance endpoints
performance_ext_router = APIRouter(prefix="/api/anime", tags=["performance-extended"])

@performance_ext_router.get("/performance/dashboard")
async def get_performance_dashboard():
    """
    Get comprehensive performance dashboard data.
    Returns real-time metrics, trends, and recommendations.
    """
    try:
        # Get recent bottlenecks
        bottlenecks = analyzer.analyze_bottlenecks(days_back=7)

        # Get performance trends
        trends = analyzer.analyze_trends(days_back=14)

        # Get optimization opportunities
        opportunities = analyzer.identify_optimization_opportunities(bottlenecks, trends)

        # Get current system status
        with psycopg2.connect(**PERFORMANCE_DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                # Recent job statistics
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_jobs_24h,
                        AVG(total_time_seconds) as avg_time_24h,
                        AVG(gpu_utilization_avg) as avg_gpu_util_24h,
                        COUNT(CASE WHEN error_details::text != '{}' THEN 1 END) as failed_jobs_24h
                    FROM anime_api.generation_performance
                    WHERE created_at >= NOW() - INTERVAL '24 hours'
                """)
                recent_stats = cursor.fetchone()

                # Queue status
                cursor.execute("""
                    SELECT COUNT(*) as queued_jobs
                    FROM anime_api.generation_jobs
                    WHERE status IN ('pending', 'queued')
                """)
                queue_status = cursor.fetchone()

        return {
            "timestamp": datetime.now().isoformat(),
            "system_status": {
                "jobs_24h": recent_stats[0] if recent_stats else 0,
                "avg_generation_time": float(recent_stats[1] or 0),
                "avg_gpu_utilization": float(recent_stats[2] or 0),
                "failed_jobs_24h": recent_stats[3] if recent_stats else 0,
                "queued_jobs": queue_status[0] if queue_status else 0,
                "success_rate_24h": 1 - (recent_stats[3] / max(1, recent_stats[0])) if recent_stats else 1
            },
            "bottlenecks": [
                {
                    "type": b.type.value,
                    "severity": b.severity,
                    "description": b.description,
                    "recommendations": b.recommendations[:3]  # Top 3 recommendations
                }
                for b in bottlenecks[:5]  # Top 5 bottlenecks
            ],
            "trends": [
                {
                    "metric": t.metric,
                    "direction": t.direction.value,
                    "change_rate": t.change_rate,
                    "confidence": t.confidence,
                    "current_value": t.current_value
                }
                for t in trends[:8]  # Top 8 trends
            ],
            "optimization_opportunities": [
                {
                    "area": o.area,
                    "potential_improvement": o.potential_improvement,
                    "effort_required": o.effort_required,
                    "description": o.description
                }
                for o in opportunities[:3]  # Top 3 opportunities
            ]
        }

    except Exception as e:
        logger.error(f"Error generating performance dashboard: {e}")
        raise HTTPException(status_code=500, detail=f"Dashboard generation failed: {str(e)}")

@performance_ext_router.get("/performance/report/comprehensive")
async def get_comprehensive_report(days_back: int = 7):
    """
    Generate comprehensive performance analysis report.
    Includes detailed bottleneck analysis, trends, and optimization recommendations.
    """
    try:
        report = analyzer.generate_performance_report(days_back)
        return report

    except Exception as e:
        logger.error(f"Error generating comprehensive report: {e}")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")

@performance_ext_router.post("/performance/train-models-comprehensive")
async def train_comprehensive_models(background_tasks: BackgroundTasks):
    """
    Train comprehensive ML models for performance prediction.
    Trains multiple model types and saves the best performing ones.
    """
    async def train_models_task():
        """Background task to train all model types"""
        try:
            logger.info("Starting comprehensive model training")

            from performance_predictor import PerformancePredictor
            predictor = PerformancePredictor(PERFORMANCE_DB_CONFIG)

            training_results = {}

            for pipeline_type in ['image', 'video']:
                training_results[pipeline_type] = {}

                for model_type in ['random_forest', 'gradient_boosting', 'linear_regression', 'neural_network']:
                    try:
                        logger.info(f"Training {model_type} for {pipeline_type}")

                        # Train model
                        metrics = predictor.train_model(pipeline_type, model_type)

                        # Save if accuracy is good enough
                        if metrics.get('accuracy_within_20_percent', 0) > 0.6:  # 60% accuracy threshold
                            predictor.save_model_to_db(pipeline_type, model_type)
                            training_results[pipeline_type][model_type] = {
                                'status': 'saved',
                                'accuracy': metrics['accuracy_within_20_percent'],
                                'mae': metrics['mean_absolute_error']
                            }
                            logger.info(f"Saved {model_type} model for {pipeline_type}")
                        else:
                            training_results[pipeline_type][model_type] = {
                                'status': 'not_saved',
                                'reason': 'accuracy_too_low',
                                'accuracy': metrics['accuracy_within_20_percent']
                            }

                    except Exception as e:
                        logger.error(f"Failed to train {model_type} for {pipeline_type}: {e}")
                        training_results[pipeline_type][model_type] = {
                            'status': 'failed',
                            'error': str(e)
                        }

            # Store training results in database for reference
            with psycopg2.connect(**PERFORMANCE_DB_CONFIG) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO anime_api.performance_alerts
                        (alert_type, severity, message, details)
                        VALUES ('model_training', 'low', %s, %s)
                    """, (
                        "Model training completed",
                        json.dumps(training_results)
                    ))
                    conn.commit()

            logger.info("Comprehensive model training completed")

        except Exception as e:
            logger.error(f"Model training task failed: {e}")

    background_tasks.add_task(train_models_task)
    return {"message": "Comprehensive model training started in background"}

@performance_ext_router.get("/performance/predictions/bulk")
async def bulk_time_predictions(job_requests: list):
    """
    Get time predictions for multiple job configurations.
    Useful for batch planning and resource allocation.
    """
    try:
        from performance_predictor import PerformancePredictor
        predictor = PerformancePredictor(PERFORMANCE_DB_CONFIG)

        # Load available models
        for pipeline in ['image', 'video']:
            for model_type in ['random_forest', 'gradient_boosting']:
                try:
                    predictor.load_model_from_db(pipeline, model_type)
                except:
                    pass  # Model not available

        predictions = []
        total_estimated_time = 0

        for i, job_params in enumerate(job_requests):
            try:
                prediction = predictor.predict_generation_time(job_params)
                predictions.append({
                    "job_index": i,
                    "job_params": job_params,
                    "prediction": prediction
                })
                total_estimated_time += prediction['predicted_time_seconds']

            except Exception as e:
                predictions.append({
                    "job_index": i,
                    "job_params": job_params,
                    "error": str(e)
                })

        return {
            "total_jobs": len(job_requests),
            "total_estimated_time_seconds": total_estimated_time,
            "total_estimated_time_formatted": f"{int(total_estimated_time // 3600)}h {int((total_estimated_time % 3600) // 60)}m {int(total_estimated_time % 60)}s",
            "predictions": predictions
        }

    except Exception as e:
        logger.error(f"Error in bulk predictions: {e}")
        raise HTTPException(status_code=500, detail=f"Bulk prediction failed: {str(e)}")

# Performance monitoring startup/shutdown handlers
async def startup_performance_monitoring():
    """Initialize performance monitoring on startup"""
    try:
        initialize_performance_monitoring()
        logger.info("Performance monitoring initialized")
    except Exception as e:
        logger.error(f"Failed to initialize performance monitoring: {e}")

async def shutdown_performance_monitoring():
    """Shutdown performance monitoring"""
    try:
        from performance_middleware import shutdown_performance_monitoring
        shutdown_performance_monitoring()
        logger.info("Performance monitoring shutdown complete")
    except Exception as e:
        logger.error(f"Error shutting down performance monitoring: {e}")

# Export routers for inclusion in main app
performance_routers = [performance_router, performance_ext_router]

# Export startup/shutdown handlers
performance_handlers = {
    'startup': startup_performance_monitoring,
    'shutdown': shutdown_performance_monitoring
}

__all__ = ['performance_routers', 'performance_handlers', 'analyzer', 'performance_tracker']