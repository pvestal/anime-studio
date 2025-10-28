#!/usr/bin/env python3
"""
Tower Anime Production - Enhanced Error Handling Framework
Provides structured error handling, retry logic, and quality assessment
"""

import time
import json
import logging
import asyncio
import traceback
import hashlib
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime
import aiohttp
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ErrorCategory(Enum):
    NETWORK = "network"
    GENERATION = "generation"
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    RESOURCE = "resource"
    SYSTEM = "system"

# Structured Exception Hierarchy
class AnimeGenerationError(Exception):
    """Base exception for anime generation system"""

    def __init__(self, message: str, category: ErrorCategory, severity: ErrorSeverity,
                 context: Dict[str, Any] = None, correlation_id: str = None):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.context = context or {}
        self.correlation_id = correlation_id or self._generate_correlation_id()
        self.timestamp = datetime.utcnow()
        self.stack_trace = traceback.format_exc()

    def _generate_correlation_id(self) -> str:
        """Generate unique correlation ID for error tracking"""
        timestamp = str(time.time())
        return hashlib.md5(f"{timestamp}-{self.message}".encode()).hexdigest()[:8]

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to structured dictionary for logging"""
        return {
            "error_id": self.correlation_id,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "stack_trace": self.stack_trace
        }

class ComfyUIError(AnimeGenerationError):
    """Errors related to ComfyUI integration"""

    def __init__(self, message: str, status_code: int = None, response_data: Dict = None, **kwargs):
        super().__init__(message, ErrorCategory.NETWORK, ErrorSeverity.HIGH, **kwargs)
        self.status_code = status_code
        self.response_data = response_data or {}
        self.context.update({
            "status_code": status_code,
            "response_data": response_data,
            "service": "ComfyUI"
        })

class EchoBrainError(AnimeGenerationError):
    """Errors related to Echo Brain integration"""

    def __init__(self, message: str, model_used: str = None, intelligence_level: str = None, **kwargs):
        super().__init__(message, ErrorCategory.NETWORK, ErrorSeverity.MEDIUM, **kwargs)
        self.model_used = model_used
        self.intelligence_level = intelligence_level
        self.context.update({
            "model_used": model_used,
            "intelligence_level": intelligence_level,
            "service": "Echo Brain"
        })

class QualityValidationError(AnimeGenerationError):
    """Errors related to output quality validation"""

    def __init__(self, message: str, validation_type: str, quality_score: float = None, **kwargs):
        super().__init__(message, ErrorCategory.VALIDATION, ErrorSeverity.MEDIUM, **kwargs)
        self.validation_type = validation_type
        self.quality_score = quality_score
        self.context.update({
            "validation_type": validation_type,
            "quality_score": quality_score
        })

class ResourceExhaustionError(AnimeGenerationError):
    """Errors related to resource exhaustion (GPU, memory, disk)"""

    def __init__(self, message: str, resource_type: str, current_usage: float = None, **kwargs):
        super().__init__(message, ErrorCategory.RESOURCE, ErrorSeverity.HIGH, **kwargs)
        self.resource_type = resource_type
        self.current_usage = current_usage
        self.context.update({
            "resource_type": resource_type,
            "current_usage": current_usage
        })

@dataclass
class OperationMetrics:
    """Metrics for tracking operation performance"""
    operation_id: str
    operation_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    success: Optional[bool] = None
    duration_seconds: Optional[float] = None
    error_details: Optional[Dict[str, Any]] = None
    context: Dict[str, Any] = None

    def complete(self, success: bool, error_details: Dict[str, Any] = None):
        """Mark operation as complete"""
        self.end_time = datetime.utcnow()
        self.success = success
        self.duration_seconds = (self.end_time - self.start_time).total_seconds()
        self.error_details = error_details

class MetricsCollector:
    """Collects and stores performance metrics"""

    def __init__(self, db_config: Dict[str, str]):
        self.db_config = db_config
        self._setup_database()

    def _setup_database(self):
        """Setup database tables for metrics storage"""
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                # Create metrics table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS anime_operation_metrics (
                        id SERIAL PRIMARY KEY,
                        operation_id VARCHAR(50) UNIQUE NOT NULL,
                        operation_type VARCHAR(50) NOT NULL,
                        start_time TIMESTAMP NOT NULL,
                        end_time TIMESTAMP,
                        duration_seconds FLOAT,
                        success BOOLEAN,
                        error_details JSONB,
                        context JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE INDEX IF NOT EXISTS idx_operation_type_time
                    ON anime_operation_metrics(operation_type, start_time);

                    CREATE INDEX IF NOT EXISTS idx_success_time
                    ON anime_operation_metrics(success, start_time);
                """)

                # Create error logs table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS anime_error_logs (
                        id SERIAL PRIMARY KEY,
                        error_id VARCHAR(50) UNIQUE NOT NULL,
                        message TEXT NOT NULL,
                        category VARCHAR(50) NOT NULL,
                        severity VARCHAR(20) NOT NULL,
                        context JSONB,
                        stack_trace TEXT,
                        timestamp TIMESTAMP NOT NULL,
                        resolved BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE INDEX IF NOT EXISTS idx_category_timestamp
                    ON anime_error_logs(category, timestamp);

                    CREATE INDEX IF NOT EXISTS idx_severity_resolved
                    ON anime_error_logs(severity, resolved);
                """)

            conn.commit()
            conn.close()
            logger.info("✅ Database tables created successfully")
        except Exception as e:
            logger.error(f"❌ Database setup failed: {e}")

    async def log_operation(self, metrics: OperationMetrics):
        """Log operation metrics to database"""
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO anime_operation_metrics
                    (operation_id, operation_type, start_time, end_time, duration_seconds,
                     success, error_details, context)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (operation_id) DO UPDATE SET
                        end_time = EXCLUDED.end_time,
                        duration_seconds = EXCLUDED.duration_seconds,
                        success = EXCLUDED.success,
                        error_details = EXCLUDED.error_details
                """, (
                    metrics.operation_id,
                    metrics.operation_type,
                    metrics.start_time,
                    metrics.end_time,
                    metrics.duration_seconds,
                    metrics.success,
                    json.dumps(metrics.error_details) if metrics.error_details else None,
                    json.dumps(metrics.context) if metrics.context else None
                ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to log metrics: {e}")

    async def log_error(self, error: AnimeGenerationError):
        """Log structured error to database"""
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                error_data = error.to_dict()
                cur.execute("""
                    INSERT INTO anime_error_logs
                    (error_id, message, category, severity, context, stack_trace, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (error_id) DO NOTHING
                """, (
                    error_data["error_id"],
                    error_data["message"],
                    error_data["category"],
                    error_data["severity"],
                    json.dumps(error_data["context"]),
                    error_data["stack_trace"],
                    error_data["timestamp"]
                ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to log error: {e}")

    async def get_success_rate(self, operation_type: str, hours: int = 24) -> float:
        """Get success rate for operation type in last N hours"""
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE success = TRUE) as successful
                    FROM anime_operation_metrics
                    WHERE operation_type = %s
                    AND start_time > NOW() - INTERVAL '%s hours'
                """, (operation_type, hours))

                result = cur.fetchone()
                if result and result['total'] > 0:
                    return float(result['successful']) / float(result['total'])
                return 0.0
        except Exception as e:
            logger.error(f"Failed to get success rate: {e}")
            return 0.0

class CircuitBreaker:
    """Circuit breaker pattern for external service calls"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60,
                 expected_exception: type = Exception):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN

    async def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == 'OPEN':
            if time.time() - self.last_failure_time < self.recovery_timeout:
                raise ComfyUIError("Circuit breaker is OPEN - service unavailable")
            else:
                self.state = 'HALF_OPEN'

        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e

    def _on_success(self):
        """Reset circuit breaker on successful call"""
        self.failure_count = 0
        self.state = 'CLOSED'

    def _on_failure(self):
        """Handle failure - increment count and potentially open circuit"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            logger.warning(f"🔴 Circuit breaker OPENED after {self.failure_count} failures")

class RetryManager:
    """Manages retry logic with exponential backoff"""

    @staticmethod
    async def retry_with_backoff(func: Callable, max_retries: int = 3,
                               base_delay: float = 1.0, max_delay: float = 60.0,
                               exceptions: tuple = (Exception,)):
        """Retry function with exponential backoff"""
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func()
                else:
                    return func()
            except exceptions as e:
                last_exception = e
                if attempt == max_retries:
                    break

                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(f"🔄 Attempt {attempt + 1} failed, retrying in {delay}s: {str(e)}")
                await asyncio.sleep(delay)

        raise last_exception

# Quality Assessment Framework
class QualityAssessor:
    """Assesses quality of generated anime content"""

    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector

    async def assess_image_quality(self, image_path: str, expected_prompt: str) -> Dict[str, Any]:
        """Assess quality of generated image"""
        operation_id = f"quality_assessment_{int(time.time())}"
        metrics = OperationMetrics(
            operation_id=operation_id,
            operation_type="image_quality_assessment",
            start_time=datetime.utcnow(),
            context={"image_path": image_path, "prompt": expected_prompt}
        )

        try:
            # Basic quality checks
            quality_score = await self._calculate_quality_score(image_path)

            # Prompt adherence check (placeholder - would use vision model)
            prompt_adherence = await self._check_prompt_adherence(image_path, expected_prompt)

            assessment = {
                "quality_score": quality_score,
                "prompt_adherence": prompt_adherence,
                "overall_rating": (quality_score + prompt_adherence) / 2,
                "issues": self._identify_issues(quality_score, prompt_adherence),
                "recommendations": self._generate_recommendations(quality_score, prompt_adherence)
            }

            metrics.complete(True)
            await self.metrics_collector.log_operation(metrics)

            return assessment

        except Exception as e:
            error = QualityValidationError(
                f"Quality assessment failed: {str(e)}",
                validation_type="image_quality",
                correlation_id=operation_id
            )

            metrics.complete(False, error.to_dict())
            await self.metrics_collector.log_operation(metrics)
            await self.metrics_collector.log_error(error)

            raise error

    async def _calculate_quality_score(self, image_path: str) -> float:
        """Calculate technical quality score (0.0 - 1.0)"""
        # Placeholder implementation - would use image analysis
        # Check file size, resolution, format validity
        import os
        if os.path.exists(image_path) and os.path.getsize(image_path) > 10000:
            return 0.8  # Good quality
        return 0.3  # Poor quality

    async def _check_prompt_adherence(self, image_path: str, prompt: str) -> float:
        """Check how well image matches prompt (0.0 - 1.0)"""
        # Placeholder - would use vision-language model
        return 0.75

    def _identify_issues(self, quality_score: float, prompt_adherence: float) -> List[str]:
        """Identify specific quality issues"""
        issues = []
        if quality_score < 0.5:
            issues.append("Low technical quality")
        if prompt_adherence < 0.6:
            issues.append("Poor prompt adherence")
        if quality_score < 0.3:
            issues.append("Potential generation failure")
        return issues

    def _generate_recommendations(self, quality_score: float, prompt_adherence: float) -> List[str]:
        """Generate improvement recommendations"""
        recommendations = []
        if quality_score < 0.5:
            recommendations.append("Increase generation steps or adjust sampler settings")
        if prompt_adherence < 0.6:
            recommendations.append("Enhance prompt with more specific details")
        if quality_score < 0.3:
            recommendations.append("Check ComfyUI workflow configuration")
        return recommendations

# Learning System for Continuous Improvement
class LearningSystem:
    """System for learning from failures and improving future generations"""

    def __init__(self, metrics_collector: MetricsCollector, kb_url: str):
        self.metrics_collector = metrics_collector
        self.kb_url = kb_url

    async def analyze_failure_patterns(self, operation_type: str, days: int = 7) -> Dict[str, Any]:
        """Analyze failure patterns to identify improvement opportunities"""
        try:
            conn = psycopg2.connect(**self.metrics_collector.db_config)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get failed operations
                cur.execute("""
                    SELECT error_details, context, COUNT(*) as frequency
                    FROM anime_operation_metrics
                    WHERE operation_type = %s
                    AND success = FALSE
                    AND start_time > NOW() - INTERVAL '%s days'
                    GROUP BY error_details, context
                    ORDER BY frequency DESC
                    LIMIT 10
                """, (operation_type, days))

                failure_patterns = cur.fetchall()

                # Get common error categories
                cur.execute("""
                    SELECT category, COUNT(*) as frequency
                    FROM anime_error_logs
                    WHERE timestamp > NOW() - INTERVAL '%s days'
                    GROUP BY category
                    ORDER BY frequency DESC
                """, (days,))

                error_categories = cur.fetchall()

            conn.close()

            analysis = {
                "operation_type": operation_type,
                "analysis_period_days": days,
                "failure_patterns": [dict(row) for row in failure_patterns],
                "error_categories": [dict(row) for row in error_categories],
                "recommendations": self._generate_learning_recommendations(failure_patterns, error_categories)
            }

            # Save analysis to Knowledge Base
            await self._save_to_kb(f"Failure Analysis - {operation_type}", analysis)

            return analysis

        except Exception as e:
            logger.error(f"Failed to analyze patterns: {e}")
            return {"error": str(e)}

    def _generate_learning_recommendations(self, failure_patterns: List, error_categories: List) -> List[str]:
        """Generate recommendations based on failure analysis"""
        recommendations = []

        # Analyze most common failures
        if failure_patterns:
            top_failure = failure_patterns[0]
            if top_failure['frequency'] > 5:
                recommendations.append(f"Address top failure pattern (occurs {top_failure['frequency']} times)")

        # Analyze error categories
        for category in error_categories:
            if category['frequency'] > 10:
                recommendations.append(f"Focus on {category['category']} errors ({category['frequency']} occurrences)")

        return recommendations

    async def _save_to_kb(self, title: str, content: Dict[str, Any]):
        """Save learning analysis to Knowledge Base"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "title": title,
                    "content": f"# Learning Analysis\n\n```json\n{json.dumps(content, indent=2, default=str)}\n```",
                    "category": "learning-analysis",
                    "tags": ["anime-production", "failure-analysis", "learning"]
                }

                async with session.post(f"{self.kb_url}/api/articles", json=payload) as response:
                    if response.status == 200:
                        logger.info(f"✅ Saved learning analysis to KB: {title}")
                    else:
                        logger.error(f"❌ Failed to save to KB: {response.status}")
        except Exception as e:
            logger.error(f"KB save error: {e}")

# Example usage configuration
TOWER_DB_CONFIG = {
    "host": "localhost",
    "database": "tower_consolidated",
    "user": "patrick",
    "password": "your_password"  # Configure appropriately
}

# Initialize global instances
metrics_collector = MetricsCollector(TOWER_DB_CONFIG)
quality_assessor = QualityAssessor(metrics_collector)
learning_system = LearningSystem(metrics_collector, "https://localhost/kb")

# Circuit breakers for external services
comfyui_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
echo_brain_circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)