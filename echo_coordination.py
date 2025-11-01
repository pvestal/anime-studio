#!/usr/bin/env python3
"""
Enhanced Echo Brain Integration with Error Recovery and Fallback Modes
Provides robust Echo Brain communication with automatic failover, model selection,
and comprehensive error handling for the anime production system.
"""

import asyncio
import aiohttp
import json
import logging
import time
import hashlib
from typing import Dict, Optional, Any, List, Union, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import requests

# Import our error handling framework
from shared.error_handling import (
    AnimeGenerationError, EchoBrainError, ErrorSeverity, ErrorCategory,
    CircuitBreaker, RetryManager, MetricsCollector, OperationMetrics
)

logger = logging.getLogger(__name__)

class EchoModelTier(Enum):
    FAST = "fast"           # Small models for quick responses (1B-7B)
    STANDARD = "standard"   # Medium models for balanced performance (8B-32B)
    ADVANCED = "advanced"   # Large models for complex tasks (70B+)

class EchoIntelligenceLevel(Enum):
    BASIC = "basic"         # Simple queries, fast response
    MODERATE = "moderate"   # Standard analysis
    ADVANCED = "advanced"   # Complex reasoning
    EXPERT = "expert"       # Deep analysis, creative tasks

class EchoServiceStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OVERLOADED = "overloaded"
    UNAVAILABLE = "unavailable"

@dataclass
class EchoConfig:
    """Configuration for Echo Brain integration"""
    base_url: str = "http://192.168.50.135:8309"
    timeout_seconds: int = 300  # 5 minutes default
    max_retries: int = 3
    retry_delay: float = 2.0
    max_retry_delay: float = 60.0

    # Model selection preferences
    preferred_models: Dict[str, List[str]] = None
    fallback_models: List[str] = None
    model_timeout_override: Dict[str, int] = None

    # Circuit breaker settings
    circuit_breaker_threshold: int = 5
    circuit_breaker_recovery_time: int = 120

    # Fallback settings
    enable_local_fallback: bool = True
    local_fallback_model: str = "llama3.2:latest"
    fallback_cache_ttl: int = 3600  # 1 hour

    def __post_init__(self):
        if self.preferred_models is None:
            self.preferred_models = {
                "fast": ["llama3.2:latest", "tinyllama:latest"],
                "standard": ["llama3.1:8b", "qwen2.5:7b", "mistral:7b"],
                "advanced": ["qwen2.5-coder:32b", "mixtral:8x7b", "llama3.1:70b"]
            }

        if self.fallback_models is None:
            self.fallback_models = ["llama3.2:latest", "tinyllama:latest"]

        if self.model_timeout_override is None:
            self.model_timeout_override = {
                "llama3.1:70b": 600,    # 10 minutes for 70B model
                "qwen2.5-coder:32b": 300,  # 5 minutes for 32B model
                "mixtral:8x7b": 180     # 3 minutes for 8x7B model
            }

@dataclass
class EchoRequest:
    """Structure for Echo Brain requests"""
    request_id: str
    query: str
    context: str
    intelligence_level: EchoIntelligenceLevel
    model_tier: EchoModelTier
    specific_model: Optional[str] = None
    timeout_override: Optional[int] = None
    priority: int = 5  # 1-10, 1 is highest
    retry_count: int = 0
    metadata: Dict[str, Any] = None
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}

@dataclass
class EchoResponse:
    """Structure for Echo Brain responses"""
    request_id: str
    response: str
    model_used: str
    intelligence_level: str
    processing_time_seconds: float
    success: bool
    confidence_score: Optional[float] = None
    fallback_used: bool = False
    cached_response: bool = False
    metadata: Dict[str, Any] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}

class EchoHealthMonitor:
    """Monitors Echo Brain service health and performance"""

    def __init__(self, config: EchoConfig):
        self.config = config
        self.last_health_check = None
        self.current_status = EchoServiceStatus.HEALTHY
        self.model_performance = {}
        self.response_times = []
        self.error_count = 0
        self.success_count = 0

    async def check_health(self) -> EchoServiceStatus:
        """Check Echo Brain service health"""
        try:
            async with aiohttp.ClientSession() as session:
                # Check basic connectivity
                async with session.get(
                    f"{self.config.base_url}/api/echo/health",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        health_data = await response.json()

                        # Check system metrics
                        system_metrics = health_data.get('system_metrics', {})
                        cpu_percent = system_metrics.get('cpu_percent', 0)
                        memory_percent = system_metrics.get('memory_percent', 0)

                        # Determine status based on metrics
                        if cpu_percent > 90 or memory_percent > 90:
                            self.current_status = EchoServiceStatus.OVERLOADED
                        elif cpu_percent > 70 or memory_percent > 70:
                            self.current_status = EchoServiceStatus.DEGRADED
                        else:
                            self.current_status = EchoServiceStatus.HEALTHY

                        return self.current_status

                    elif response.status == 503:
                        self.current_status = EchoServiceStatus.OVERLOADED
                    else:
                        self.current_status = EchoServiceStatus.DEGRADED

        except Exception as e:
            logger.error(f"Echo health check failed: {e}")
            self.current_status = EchoServiceStatus.UNAVAILABLE

        self.last_health_check = datetime.utcnow()
        return self.current_status

    def record_response(self, response_time: float, success: bool, model_used: str = None):
        """Record response metrics"""
        self.response_times.append(response_time)
        if len(self.response_times) > 100:  # Keep last 100 responses
            self.response_times.pop(0)

        if success:
            self.success_count += 1
        else:
            self.error_count += 1

        if model_used:
            if model_used not in self.model_performance:
                self.model_performance[model_used] = {"total_requests": 0, "success_count": 0, "avg_response_time": 0}

            perf = self.model_performance[model_used]
            perf["total_requests"] += 1
            if success:
                perf["success_count"] += 1

            # Update average response time
            current_avg = perf["avg_response_time"]
            total_requests = perf["total_requests"]
            perf["avg_response_time"] = ((current_avg * (total_requests - 1)) + response_time) / total_requests

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics"""
        total_requests = self.success_count + self.error_count
        success_rate = (self.success_count / total_requests * 100) if total_requests > 0 else 0

        avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0

        return {
            "current_status": self.current_status.value,
            "total_requests": total_requests,
            "success_rate_percent": round(success_rate, 2),
            "average_response_time_seconds": round(avg_response_time, 2),
            "model_performance": self.model_performance,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None
        }

class ModelSelector:
    """Selects optimal models based on request requirements and performance"""

    def __init__(self, config: EchoConfig, health_monitor: EchoHealthMonitor):
        self.config = config
        self.health_monitor = health_monitor

    def select_model(self, request: EchoRequest) -> str:
        """Select optimal model for request"""
        # Use specific model if requested
        if request.specific_model:
            return request.specific_model

        # Get preferred models for tier
        tier_models = self.config.preferred_models.get(request.model_tier.value, [])

        # Filter based on performance data
        available_models = self._filter_available_models(tier_models)

        if not available_models:
            # Fall back to any available model
            available_models = self._filter_available_models(self.config.fallback_models)

        if not available_models:
            # Last resort: use first preferred model
            return tier_models[0] if tier_models else "llama3.2:latest"

        # Select best performing model
        return self._select_best_model(available_models)

    def _filter_available_models(self, models: List[str]) -> List[str]:
        """Filter models based on availability and performance"""
        available = []

        for model in models:
            perf = self.health_monitor.model_performance.get(model, {})
            success_rate = 0

            if perf.get("total_requests", 0) > 0:
                success_rate = (perf["success_count"] / perf["total_requests"]) * 100

            # Only include models with >70% success rate or no data yet
            if perf.get("total_requests", 0) == 0 or success_rate > 70:
                available.append(model)

        return available

    def _select_best_model(self, models: List[str]) -> str:
        """Select best model based on performance metrics"""
        if len(models) == 1:
            return models[0]

        best_model = models[0]
        best_score = 0

        for model in models:
            perf = self.health_monitor.model_performance.get(model, {})

            if perf.get("total_requests", 0) == 0:
                # No data, give moderate score
                score = 0.5
            else:
                success_rate = perf["success_count"] / perf["total_requests"]
                avg_time = perf["avg_response_time"]

                # Score based on success rate and response time
                # Prefer higher success rate and lower response time
                score = success_rate * 0.7 + (1 / (avg_time + 1)) * 0.3

            if score > best_score:
                best_score = score
                best_model = model

        return best_model

class ResponseCache:
    """Caches Echo responses to reduce load and improve performance"""

    def __init__(self, cache_dir: str, ttl_seconds: int = 3600):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self.memory_cache = {}

    def _get_cache_key(self, request: EchoRequest) -> str:
        """Generate cache key for request"""
        cache_content = f"{request.query}|{request.context}|{request.intelligence_level.value}"
        return hashlib.md5(cache_content.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get cache file path"""
        return self.cache_dir / f"{cache_key}.cache.json"

    async def get(self, request: EchoRequest) -> Optional[EchoResponse]:
        """Get cached response if available and valid"""
        cache_key = self._get_cache_key(request)

        # Check memory cache first
        if cache_key in self.memory_cache:
            cached_entry = self.memory_cache[cache_key]
            if datetime.utcnow() - cached_entry["cached_at"] < timedelta(seconds=self.ttl_seconds):
                response = cached_entry["response"]
                response.cached_response = True
                return response

        # Check file cache
        cache_file = self._get_cache_path(cache_key)
        if cache_file.exists():
            try:
                file_stat = cache_file.stat()
                cache_age = datetime.utcnow() - datetime.fromtimestamp(file_stat.st_mtime)

                if cache_age < timedelta(seconds=self.ttl_seconds):
                    with open(cache_file, 'r') as f:
                        cache_data = json.load(f)

                    response = EchoResponse(**cache_data)
                    response.cached_response = True

                    # Store in memory cache
                    self.memory_cache[cache_key] = {
                        "response": response,
                        "cached_at": datetime.utcnow()
                    }

                    return response

            except Exception as e:
                logger.warning(f"Failed to read cache file {cache_file}: {e}")

        return None

    async def set(self, request: EchoRequest, response: EchoResponse):
        """Cache response"""
        cache_key = self._get_cache_key(request)

        # Store in memory cache
        self.memory_cache[cache_key] = {
            "response": response,
            "cached_at": datetime.utcnow()
        }

        # Store in file cache
        cache_file = self._get_cache_path(cache_key)
        try:
            with open(cache_file, 'w') as f:
                json.dump(asdict(response), f, default=str, indent=2)
        except Exception as e:
            logger.error(f"Failed to write cache file {cache_file}: {e}")

class EnhancedEchoIntegration:
    """Enhanced Echo Brain integration with comprehensive error handling"""

    def __init__(self, config: EchoConfig = None, metrics_collector: MetricsCollector = None):
        self.config = config or EchoConfig()
        self.metrics_collector = metrics_collector
        self.health_monitor = EchoHealthMonitor(self.config)
        self.model_selector = ModelSelector(self.config, self.health_monitor)
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.circuit_breaker_threshold,
            recovery_timeout=self.config.circuit_breaker_recovery_time
        )
        self.retry_manager = RetryManager()
        self.response_cache = ResponseCache(
            "/opt/tower-anime-production/cache/echo",
            self.config.fallback_cache_ttl
        )

    async def query_echo_robust(self, request: EchoRequest) -> EchoResponse:
        """Query Echo Brain with comprehensive error handling and fallback"""
        operation_id = f"echo_query_{request.request_id}"
        metrics = OperationMetrics(
            operation_id=operation_id,
            operation_type="echo_brain_query",
            start_time=datetime.utcnow(),
            context={
                "request_id": request.request_id,
                "intelligence_level": request.intelligence_level.value,
                "model_tier": request.model_tier.value,
                "query_length": len(request.query)
            }
        )

        try:
            # Check cache first
            cached_response = await self.response_cache.get(request)
            if cached_response:
                logger.debug(f"Echo query {request.request_id} served from cache")
                metrics.complete(True, {"source": "cache"})
                if self.metrics_collector:
                    await self.metrics_collector.log_operation(metrics)
                return cached_response

            # Check service health
            health_status = await self.health_monitor.check_health()
            if health_status == EchoServiceStatus.UNAVAILABLE:
                return await self._attempt_local_fallback(request)

            # Query with circuit breaker protection
            start_time = time.time()
            response = await self.circuit_breaker.call(
                self._query_echo_internal, request
            )
            processing_time = time.time() - start_time

            # Record performance metrics
            self.health_monitor.record_response(
                processing_time, True, response.model_used
            )

            # Cache successful response
            await self.response_cache.set(request, response)

            metrics.complete(True, {
                "model_used": response.model_used,
                "processing_time": processing_time,
                "fallback_used": response.fallback_used
            })
            if self.metrics_collector:
                await self.metrics_collector.log_operation(metrics)

            return response

        except Exception as e:
            # Record failure
            processing_time = (datetime.utcnow() - metrics.start_time).total_seconds()
            self.health_monitor.record_response(processing_time, False)

            # Determine if retry is appropriate
            should_retry = (
                request.retry_count < self.config.max_retries and
                self._is_retryable_error(e)
            )

            if should_retry:
                logger.warning(f"Retrying Echo query {request.request_id} (attempt {request.retry_count + 1})")
                request.retry_count += 1
                await asyncio.sleep(self.config.retry_delay * (2 ** request.retry_count))
                return await self.query_echo_robust(request)

            # Try fallback if available
            if self.config.enable_local_fallback:
                logger.warning(f"Echo query failed, attempting local fallback: {e}")
                fallback_response = await self._attempt_local_fallback(request)
                if fallback_response:
                    metrics.complete(True, {"source": "local_fallback", "original_error": str(e)})
                    if self.metrics_collector:
                        await self.metrics_collector.log_operation(metrics)
                    return fallback_response

            # Create appropriate error
            error = self._create_echo_error(e, request)
            metrics.complete(False, error.to_dict())
            if self.metrics_collector:
                await self.metrics_collector.log_operation(metrics)
                await self.metrics_collector.log_error(error)

            raise error

    async def _query_echo_internal(self, request: EchoRequest) -> EchoResponse:
        """Internal Echo query with model selection and timeout handling"""
        # Select optimal model
        selected_model = self.model_selector.select_model(request)
        timeout = request.timeout_override or self.config.model_timeout_override.get(
            selected_model, self.config.timeout_seconds
        )

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "query": request.query,
                    "context": request.context,
                    "model": selected_model,
                    "intelligence_level": request.intelligence_level.value,
                    "metadata": request.metadata
                }

                async with session.post(
                    f"{self.config.base_url}/api/echo/query",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()

                        return EchoResponse(
                            request_id=request.request_id,
                            response=data.get('response', ''),
                            model_used=data.get('model_used', selected_model),
                            intelligence_level=data.get('intelligence_level', request.intelligence_level.value),
                            processing_time_seconds=data.get('processing_time_seconds', 0),
                            success=True,
                            confidence_score=data.get('confidence_score'),
                            metadata=data.get('metadata', {})
                        )
                    else:
                        response_text = await response.text()
                        raise EchoBrainError(
                            f"Echo query failed: {response.status} - {response_text}",
                            model_used=selected_model,
                            intelligence_level=request.intelligence_level.value
                        )

        except asyncio.TimeoutError:
            raise EchoBrainError(
                f"Echo query timeout after {timeout} seconds",
                model_used=selected_model,
                intelligence_level=request.intelligence_level.value
            )
        except aiohttp.ClientError as e:
            raise EchoBrainError(
                f"Network error communicating with Echo: {str(e)}",
                model_used=selected_model,
                intelligence_level=request.intelligence_level.value
            )

    async def _attempt_local_fallback(self, request: EchoRequest) -> Optional[EchoResponse]:
        """Attempt local model fallback when Echo is unavailable"""
        if not self.config.enable_local_fallback:
            return None

        try:
            logger.info(f"Attempting local fallback for request {request.request_id}")

            # Try local Ollama instance
            local_payload = {
                "model": self.config.local_fallback_model,
                "prompt": f"Context: {request.context}\n\nQuery: {request.query}",
                "stream": False
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://localhost:11434/api/generate",
                    json=local_payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status == 200:
                        data = await response.json()

                        return EchoResponse(
                            request_id=request.request_id,
                            response=data.get('response', ''),
                            model_used=self.config.local_fallback_model,
                            intelligence_level="fallback",
                            processing_time_seconds=0,
                            success=True,
                            fallback_used=True,
                            metadata={"fallback_reason": "echo_unavailable"}
                        )

        except Exception as e:
            logger.error(f"Local fallback also failed: {e}")

        return None

    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if error is retryable"""
        if isinstance(error, EchoBrainError):
            return error.severity in [ErrorSeverity.MEDIUM, ErrorSeverity.HIGH]
        elif isinstance(error, (asyncio.TimeoutError, aiohttp.ClientError)):
            return True
        else:
            return False

    def _create_echo_error(self, original_error: Exception, request: EchoRequest) -> EchoBrainError:
        """Create appropriate Echo error from original error"""
        if isinstance(original_error, EchoBrainError):
            return original_error
        else:
            return EchoBrainError(
                f"Echo Brain query failed: {str(original_error)}",
                model_used=request.specific_model,
                intelligence_level=request.intelligence_level.value,
                correlation_id=request.request_id
            )

    # High-level convenience methods for anime production

    async def generate_story_scene(self, character_name: str, scene_description: str,
                                 style_context: str = "") -> EchoResponse:
        """Generate story scene using Echo Brain"""
        request = EchoRequest(
            request_id=f"story_{int(time.time())}",
            query=f"Create a detailed anime scene description for character '{character_name}' in this scenario: {scene_description}",
            context=f"anime_story_generation|style:{style_context}",
            intelligence_level=EchoIntelligenceLevel.ADVANCED,
            model_tier=EchoModelTier.ADVANCED,
            metadata={"character_name": character_name, "scene_type": "story"}
        )

        return await self.query_echo_robust(request)

    async def analyze_character_consistency(self, character_name: str,
                                          generated_content: str) -> EchoResponse:
        """Analyze character consistency in generated content"""
        request = EchoRequest(
            request_id=f"consistency_{int(time.time())}",
            query=f"Analyze this generated content for consistency with character '{character_name}': {generated_content}",
            context="character_consistency_analysis",
            intelligence_level=EchoIntelligenceLevel.EXPERT,
            model_tier=EchoModelTier.ADVANCED,
            metadata={"character_name": character_name, "analysis_type": "consistency"}
        )

        return await self.query_echo_robust(request)

    async def optimize_generation_prompt(self, base_prompt: str,
                                       target_style: str = "anime") -> EchoResponse:
        """Optimize generation prompt using Echo Brain"""
        request = EchoRequest(
            request_id=f"optimize_{int(time.time())}",
            query=f"Optimize this prompt for {target_style} image generation: {base_prompt}",
            context="prompt_optimization",
            intelligence_level=EchoIntelligenceLevel.MODERATE,
            model_tier=EchoModelTier.STANDARD,
            metadata={"target_style": target_style, "optimization_type": "prompt"}
        )

        return await self.query_echo_robust(request)

    async def get_service_status(self) -> Dict[str, Any]:
        """Get comprehensive Echo integration status"""
        health_status = await self.health_monitor.check_health()
        performance_metrics = self.health_monitor.get_performance_metrics()

        return {
            "service_status": health_status.value,
            "circuit_breaker_state": self.circuit_breaker.state,
            "performance_metrics": performance_metrics,
            "config": {
                "base_url": self.config.base_url,
                "timeout_seconds": self.config.timeout_seconds,
                "max_retries": self.config.max_retries,
                "local_fallback_enabled": self.config.enable_local_fallback,
                "preferred_models": self.config.preferred_models
            },
            "cache_stats": {
                "memory_cache_size": len(self.response_cache.memory_cache),
                "cache_dir": str(self.response_cache.cache_dir)
            },
            "last_check": datetime.utcnow().isoformat()
        }

# Factory function
def create_echo_integration(config: EchoConfig = None, metrics_collector: MetricsCollector = None) -> EnhancedEchoIntegration:
    """Create configured Echo integration instance"""
    return EnhancedEchoIntegration(config, metrics_collector)

# Example usage and testing
async def test_echo_integration():
    """Test the enhanced Echo integration"""
    echo_integration = create_echo_integration()

    try:
        # Test service status
        print("Getting Echo service status...")
        status = await echo_integration.get_service_status()
        print("Service Status:", json.dumps(status, indent=2, default=str))

        # Test story generation
        print("\nTesting story generation...")
        story_response = await echo_integration.generate_story_scene(
            "Kai Nakamura",
            "standing confidently in a neon-lit cyberpunk alley",
            "cyberpunk anime"
        )
        print(f"Story generated: {story_response.success}")
        print(f"Model used: {story_response.model_used}")
        print(f"Response length: {len(story_response.response)}")

        # Test prompt optimization
        print("\nTesting prompt optimization...")
        optimize_response = await echo_integration.optimize_generation_prompt(
            "anime girl with blue hair",
            "high quality anime"
        )
        print(f"Prompt optimized: {optimize_response.success}")
        print(f"Fallback used: {optimize_response.fallback_used}")

    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_echo_integration())