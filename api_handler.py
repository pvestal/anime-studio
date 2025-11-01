#!/usr/bin/env python3
"""
Enhanced API Handler with Comprehensive Error Handling, Validation, and Rate Limiting
Provides robust API endpoint management with request validation, rate limiting,
circuit breakers, and comprehensive error handling for the anime production system.
"""

import asyncio
import time
import json
import hashlib
import ipaddress
from typing import Dict, Optional, Any, List, Union, Callable, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import logging
from collections import defaultdict, deque
import redis
from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GzipMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ValidationError, validator
import uvicorn

# Import our error handling framework
from shared.error_handling import (
    AnimeGenerationError, ErrorSeverity, ErrorCategory,
    MetricsCollector, OperationMetrics, CircuitBreaker
)

logger = logging.getLogger(__name__)

class RequestPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

class RateLimitType(Enum):
    PER_IP = "per_ip"
    PER_USER = "per_user"
    PER_ENDPOINT = "per_endpoint"
    GLOBAL = "global"

@dataclass
class APIConfig:
    """Configuration for API handling"""
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8328
    debug: bool = False

    # Rate limiting
    redis_url: str = "redis://localhost:6379"
    rate_limit_enabled: bool = True
    default_rate_limit: int = 100  # requests per minute
    burst_rate_limit: int = 200   # burst allowance

    # Rate limits by endpoint
    endpoint_rate_limits: Dict[str, int] = None

    # Security
    require_auth: bool = False
    allowed_origins: List[str] = None
    max_request_size_mb: int = 100

    # Request validation
    validate_requests: bool = True
    max_prompt_length: int = 5000
    max_duration_seconds: int = 300  # 5 minutes max

    # Circuit breaker settings
    circuit_breaker_enabled: bool = True
    failure_threshold: int = 10
    recovery_timeout: int = 60

    # Monitoring
    enable_metrics: bool = True
    log_all_requests: bool = True

    def __post_init__(self):
        if self.endpoint_rate_limits is None:
            self.endpoint_rate_limits = {
                "/api/generate": 10,      # 10 per minute for generation
                "/api/status": 60,        # 60 per minute for status
                "/api/health": 120,       # 120 per minute for health
                "/api/characters": 30     # 30 per minute for characters
            }

        if self.allowed_origins is None:
            self.allowed_origins = [
                "https://192.168.50.135",
                "http://localhost:3000",
                "http://localhost:8080"
            ]

@dataclass
class RateLimitInfo:
    """Rate limit information"""
    limit: int
    remaining: int
    reset_time: datetime
    retry_after: Optional[int] = None

class APIError(AnimeGenerationError):
    """API-specific errors"""

    def __init__(self, message: str, status_code: int = 500,
                 error_code: str = None, **kwargs):
        super().__init__(message, ErrorCategory.SYSTEM, ErrorSeverity.MEDIUM, **kwargs)
        self.status_code = status_code
        self.error_code = error_code or "INTERNAL_ERROR"
        self.context.update({
            "status_code": status_code,
            "error_code": error_code,
            "service": "api"
        })

class RequestValidator:
    """Validates API requests with comprehensive checking"""

    def __init__(self, config: APIConfig):
        self.config = config

    def validate_generation_request(self, request_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate generation request"""
        errors = []

        # Check required fields
        required_fields = ['prompt']
        for field in required_fields:
            if field not in request_data:
                errors.append(f"Missing required field: {field}")

        # Validate prompt
        prompt = request_data.get('prompt', '')
        if isinstance(prompt, str):
            if len(prompt.strip()) == 0:
                errors.append("Prompt cannot be empty")
            elif len(prompt) > self.config.max_prompt_length:
                errors.append(f"Prompt too long: {len(prompt)} > {self.config.max_prompt_length}")
        else:
            errors.append("Prompt must be a string")

        # Validate duration
        duration = request_data.get('duration', 5)
        if isinstance(duration, (int, float)):
            if duration <= 0:
                errors.append("Duration must be positive")
            elif duration > self.config.max_duration_seconds:
                errors.append(f"Duration too long: {duration} > {self.config.max_duration_seconds}")
        else:
            errors.append("Duration must be a number")

        # Validate character name if provided
        character_name = request_data.get('character_name', '')
        if character_name and not isinstance(character_name, str):
            errors.append("Character name must be a string")

        # Validate style
        style = request_data.get('style', 'anime')
        if style and not isinstance(style, str):
            errors.append("Style must be a string")

        # Validate priority
        priority = request_data.get('priority', 2)
        if isinstance(priority, int):
            if priority < 1 or priority > 4:
                errors.append("Priority must be between 1 and 4")
        else:
            errors.append("Priority must be an integer")

        return len(errors) == 0, errors

class RateLimiter:
    """Redis-based rate limiter with multiple strategies"""

    def __init__(self, config: APIConfig):
        self.config = config
        self.redis_client = None
        self.memory_store = defaultdict(lambda: deque())  # Fallback for when Redis unavailable

        if config.rate_limit_enabled:
            try:
                self.redis_client = redis.from_url(config.redis_url, decode_responses=True)
                # Test connection
                self.redis_client.ping()
                logger.info("✅ Redis connection established for rate limiting")
            except Exception as e:
                logger.warning(f"Redis connection failed, using memory store: {e}")
                self.redis_client = None

    async def check_rate_limit(self, key: str, limit: int, window_seconds: int = 60) -> RateLimitInfo:
        """Check if request is within rate limit"""
        current_time = time.time()
        window_start = current_time - window_seconds

        if self.redis_client:
            return await self._check_redis_rate_limit(key, limit, window_seconds, current_time)
        else:
            return await self._check_memory_rate_limit(key, limit, window_start, current_time)

    async def _check_redis_rate_limit(self, key: str, limit: int, window_seconds: int,
                                     current_time: float) -> RateLimitInfo:
        """Check rate limit using Redis"""
        try:
            pipe = self.redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, current_time - window_seconds)
            pipe.zcard(key)
            pipe.zadd(key, {str(current_time): current_time})
            pipe.expire(key, window_seconds)
            results = pipe.execute()

            current_count = results[1] + 1  # +1 for current request
            remaining = max(0, limit - current_count)
            reset_time = datetime.fromtimestamp(current_time + window_seconds)

            if current_count > limit:
                retry_after = window_seconds
                # Remove the request we just added since it's over limit
                self.redis_client.zrem(key, str(current_time))
                return RateLimitInfo(
                    limit=limit,
                    remaining=0,
                    reset_time=reset_time,
                    retry_after=retry_after
                )

            return RateLimitInfo(
                limit=limit,
                remaining=remaining,
                reset_time=reset_time
            )

        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}")
            # Fallback to allowing request
            return RateLimitInfo(
                limit=limit,
                remaining=limit - 1,
                reset_time=datetime.fromtimestamp(current_time + window_seconds)
            )

    async def _check_memory_rate_limit(self, key: str, limit: int, window_start: float,
                                      current_time: float) -> RateLimitInfo:
        """Check rate limit using memory store"""
        requests = self.memory_store[key]

        # Remove old requests
        while requests and requests[0] < window_start:
            requests.popleft()

        # Add current request
        requests.append(current_time)

        current_count = len(requests)
        remaining = max(0, limit - current_count)
        reset_time = datetime.fromtimestamp(current_time + 60)  # 1 minute window

        if current_count > limit:
            # Remove the request we just added
            requests.pop()
            return RateLimitInfo(
                limit=limit,
                remaining=0,
                reset_time=reset_time,
                retry_after=60
            )

        return RateLimitInfo(
            limit=limit,
            remaining=remaining,
            reset_time=reset_time
        )

    def get_rate_limit_key(self, request_type: RateLimitType, identifier: str,
                          endpoint: str = None) -> str:
        """Generate rate limit key"""
        if request_type == RateLimitType.PER_IP:
            return f"rate_limit:ip:{identifier}"
        elif request_type == RateLimitType.PER_USER:
            return f"rate_limit:user:{identifier}"
        elif request_type == RateLimitType.PER_ENDPOINT:
            return f"rate_limit:endpoint:{endpoint}:{identifier}"
        elif request_type == RateLimitType.GLOBAL:
            return f"rate_limit:global"
        else:
            return f"rate_limit:unknown:{identifier}"

class RequestLogger:
    """Logs API requests for monitoring and debugging"""

    def __init__(self, config: APIConfig):
        self.config = config
        self.request_history = deque(maxlen=1000)  # Keep last 1000 requests

    def log_request(self, request: Request, response_status: int,
                   processing_time: float, error: str = None):
        """Log API request"""
        client_ip = self._get_client_ip(request)

        request_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "method": request.method,
            "path": str(request.url.path),
            "client_ip": client_ip,
            "user_agent": request.headers.get("user-agent", ""),
            "response_status": response_status,
            "processing_time_ms": round(processing_time * 1000, 2),
            "error": error
        }

        if self.config.log_all_requests:
            logger.info(f"API Request: {request.method} {request.url.path} - {response_status} ({processing_time:.3f}s)")

        self.request_history.append(request_log)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request"""
        # Check X-Forwarded-For header first
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Use client IP from connection
        return request.client.host if request.client else "unknown"

    def get_request_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get request statistics"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        recent_requests = [
            req for req in self.request_history
            if datetime.fromisoformat(req["timestamp"]) > cutoff_time
        ]

        if not recent_requests:
            return {"total_requests": 0, "period_hours": hours}

        # Calculate statistics
        total_requests = len(recent_requests)
        successful_requests = len([r for r in recent_requests if r["response_status"] < 400])
        error_requests = total_requests - successful_requests

        avg_processing_time = sum(r["processing_time_ms"] for r in recent_requests) / total_requests

        # Top client IPs
        ip_counts = defaultdict(int)
        for req in recent_requests:
            ip_counts[req["client_ip"]] += 1

        top_ips = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        # Top endpoints
        endpoint_counts = defaultdict(int)
        for req in recent_requests:
            endpoint_counts[req["path"]] += 1

        top_endpoints = sorted(endpoint_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "error_requests": error_requests,
            "success_rate_percent": round((successful_requests / total_requests) * 100, 2),
            "average_processing_time_ms": round(avg_processing_time, 2),
            "top_client_ips": top_ips,
            "top_endpoints": top_endpoints,
            "period_hours": hours
        }

class SecurityManager:
    """Manages API security including authentication and IP filtering"""

    def __init__(self, config: APIConfig):
        self.config = config
        self.blocked_ips = set()
        self.suspicious_activity = defaultdict(list)

    def validate_request_origin(self, request: Request) -> bool:
        """Validate request origin"""
        origin = request.headers.get("origin")
        if not origin:
            return True  # Allow requests without origin header

        return origin in self.config.allowed_origins

    def check_ip_blocked(self, ip: str) -> bool:
        """Check if IP is blocked"""
        return ip in self.blocked_ips

    def block_ip(self, ip: str, reason: str):
        """Block an IP address"""
        self.blocked_ips.add(ip)
        logger.warning(f"Blocked IP {ip}: {reason}")

    def detect_suspicious_activity(self, ip: str, endpoint: str) -> bool:
        """Detect suspicious activity patterns"""
        now = datetime.utcnow()
        activity_key = f"{ip}:{endpoint}"

        # Clean old activity records
        self.suspicious_activity[activity_key] = [
            timestamp for timestamp in self.suspicious_activity[activity_key]
            if now - timestamp < timedelta(minutes=5)
        ]

        # Add current activity
        self.suspicious_activity[activity_key].append(now)

        # Check for suspicious patterns
        recent_activity = len(self.suspicious_activity[activity_key])

        if recent_activity > 50:  # More than 50 requests in 5 minutes
            return True

        return False

class EnhancedAPIHandler:
    """Enhanced API handler with comprehensive error handling and features"""

    def __init__(self, config: APIConfig = None, metrics_collector: MetricsCollector = None):
        self.config = config or APIConfig()
        self.metrics_collector = metrics_collector
        self.validator = RequestValidator(self.config)
        self.rate_limiter = RateLimiter(self.config)
        self.request_logger = RequestLogger(self.config)
        self.security_manager = SecurityManager(self.config)
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.failure_threshold,
            recovery_timeout=self.config.recovery_timeout
        ) if self.config.circuit_breaker_enabled else None

        # Initialize FastAPI app
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        """Create and configure FastAPI application"""
        app = FastAPI(
            title="Enhanced Anime Production API",
            description="Comprehensive anime generation API with error handling",
            version="2.0.0",
            debug=self.config.debug
        )

        # Add middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.config.allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        app.add_middleware(GzipMiddleware, minimum_size=1000)

        # Add custom middleware
        app.middleware("http")(self._request_middleware)

        # Add exception handlers
        app.add_exception_handler(ValidationError, self._validation_error_handler)
        app.add_exception_handler(APIError, self._api_error_handler)
        app.add_exception_handler(Exception, self._general_error_handler)

        return app

    async def _request_middleware(self, request: Request, call_next):
        """Custom request middleware for logging and security"""
        start_time = time.time()
        client_ip = self.request_logger._get_client_ip(request)

        # Security checks
        if self.security_manager.check_ip_blocked(client_ip):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "IP address blocked"}
            )

        if not self.security_manager.validate_request_origin(request):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "Invalid origin"}
            )

        # Rate limiting
        if self.config.rate_limit_enabled:
            endpoint = str(request.url.path)
            rate_limit = self.config.endpoint_rate_limits.get(
                endpoint, self.config.default_rate_limit
            )

            rate_limit_key = self.rate_limiter.get_rate_limit_key(
                RateLimitType.PER_IP, client_ip, endpoint
            )

            rate_limit_info = await self.rate_limiter.check_rate_limit(
                rate_limit_key, rate_limit
            )

            if rate_limit_info.retry_after:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "Rate limit exceeded",
                        "retry_after": rate_limit_info.retry_after,
                        "limit": rate_limit_info.limit,
                        "reset_time": rate_limit_info.reset_time.isoformat()
                    },
                    headers={
                        "X-RateLimit-Limit": str(rate_limit_info.limit),
                        "X-RateLimit-Remaining": str(rate_limit_info.remaining),
                        "X-RateLimit-Reset": str(int(rate_limit_info.reset_time.timestamp())),
                        "Retry-After": str(rate_limit_info.retry_after)
                    }
                )

        # Detect suspicious activity
        if self.security_manager.detect_suspicious_activity(client_ip, str(request.url.path)):
            logger.warning(f"Suspicious activity detected from {client_ip}")

        try:
            response = await call_next(request)
            processing_time = time.time() - start_time

            # Log request
            self.request_logger.log_request(
                request, response.status_code, processing_time
            )

            # Add rate limit headers
            if self.config.rate_limit_enabled and 'rate_limit_info' in locals():
                response.headers["X-RateLimit-Limit"] = str(rate_limit_info.limit)
                response.headers["X-RateLimit-Remaining"] = str(rate_limit_info.remaining)
                response.headers["X-RateLimit-Reset"] = str(int(rate_limit_info.reset_time.timestamp()))

            return response

        except Exception as e:
            processing_time = time.time() - start_time
            self.request_logger.log_request(
                request, 500, processing_time, str(e)
            )
            raise

    async def _validation_error_handler(self, request: Request, exc: ValidationError):
        """Handle Pydantic validation errors"""
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Validation failed",
                "details": exc.errors(),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    async def _api_error_handler(self, request: Request, exc: APIError):
        """Handle API-specific errors"""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.message,
                "error_code": exc.error_code,
                "correlation_id": exc.correlation_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    async def _general_error_handler(self, request: Request, exc: Exception):
        """Handle general exceptions"""
        error_id = hashlib.md5(f"{time.time()}{str(exc)}".encode()).hexdigest()[:8]

        logger.error(f"Unhandled exception [{error_id}]: {exc}", exc_info=True)

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "error_id": error_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    # API endpoint decorators and helpers

    def validate_request(self, validation_func: Callable):
        """Decorator for request validation"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                # Extract request data from kwargs
                request_data = kwargs.get('request_data', {})

                if self.config.validate_requests:
                    is_valid, errors = validation_func(request_data)
                    if not is_valid:
                        raise APIError(
                            f"Request validation failed: {'; '.join(errors)}",
                            status_code=status.HTTP_400_BAD_REQUEST,
                            error_code="VALIDATION_FAILED"
                        )

                return await func(*args, **kwargs)
            return wrapper
        return decorator

    def circuit_breaker_protection(self, func):
        """Decorator for circuit breaker protection"""
        if not self.circuit_breaker:
            return func

        async def wrapper(*args, **kwargs):
            try:
                return await self.circuit_breaker.call(func, *args, **kwargs)
            except Exception as e:
                if self.circuit_breaker.state == 'OPEN':
                    raise APIError(
                        "Service temporarily unavailable",
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        error_code="SERVICE_UNAVAILABLE"
                    )
                raise
        return wrapper

    def monitor_performance(self, operation_type: str):
        """Decorator for performance monitoring"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                if not self.metrics_collector:
                    return await func(*args, **kwargs)

                operation_id = f"api_{operation_type}_{int(time.time())}"
                metrics = OperationMetrics(
                    operation_id=operation_id,
                    operation_type=f"api_{operation_type}",
                    start_time=datetime.utcnow()
                )

                try:
                    result = await func(*args, **kwargs)
                    metrics.complete(True)
                    await self.metrics_collector.log_operation(metrics)
                    return result
                except Exception as e:
                    error_dict = {"error": str(e), "type": type(e).__name__}
                    metrics.complete(False, error_dict)
                    await self.metrics_collector.log_operation(metrics)
                    raise
            return wrapper
        return decorator

    async def get_api_health(self) -> Dict[str, Any]:
        """Get comprehensive API health status"""
        request_stats = self.request_logger.get_request_stats(24)

        # Check circuit breaker status
        circuit_status = "disabled"
        if self.circuit_breaker:
            circuit_status = self.circuit_breaker.state.lower()

        # Check rate limiter status
        rate_limiter_status = "enabled" if self.config.rate_limit_enabled else "disabled"
        redis_status = "connected" if self.rate_limiter.redis_client else "disconnected"

        return {
            "api_status": "healthy",
            "version": "2.0.0",
            "uptime_hours": 0,  # Would need to track this
            "request_stats": request_stats,
            "rate_limiting": {
                "status": rate_limiter_status,
                "redis_status": redis_status,
                "default_limit": self.config.default_rate_limit
            },
            "circuit_breaker": {
                "status": circuit_status,
                "failure_threshold": self.config.failure_threshold if self.circuit_breaker else None
            },
            "security": {
                "blocked_ips": len(self.security_manager.blocked_ips),
                "auth_required": self.config.require_auth
            },
            "config": {
                "debug_mode": self.config.debug,
                "max_request_size_mb": self.config.max_request_size_mb,
                "validation_enabled": self.config.validate_requests
            },
            "last_check": datetime.utcnow().isoformat()
        }

    def run_server(self):
        """Run the API server"""
        logger.info(f"Starting Enhanced Anime Production API on {self.config.host}:{self.config.port}")

        uvicorn.run(
            self.app,
            host=self.config.host,
            port=self.config.port,
            debug=self.config.debug,
            access_log=self.config.log_all_requests
        )

# Factory function
def create_api_handler(config: APIConfig = None, metrics_collector: MetricsCollector = None) -> EnhancedAPIHandler:
    """Create configured API handler instance"""
    return EnhancedAPIHandler(config, metrics_collector)

# Example usage with actual endpoints
def setup_anime_api_routes(api_handler: EnhancedAPIHandler):
    """Set up anime production API routes"""
    app = api_handler.app

    # Request models
    class GenerationRequest(BaseModel):
        prompt: str
        character_name: Optional[str] = None
        duration: int = 5
        style: str = "anime"
        priority: int = 2

        @validator('prompt')
        def validate_prompt(cls, v):
            if len(v.strip()) == 0:
                raise ValueError('Prompt cannot be empty')
            return v

        @validator('duration')
        def validate_duration(cls, v):
            if v <= 0 or v > 300:
                raise ValueError('Duration must be between 1 and 300 seconds')
            return v

    @app.post("/api/generate")
    @api_handler.validate_request(api_handler.validator.validate_generation_request)
    @api_handler.circuit_breaker_protection
    @api_handler.monitor_performance("generation")
    async def generate_video(request: GenerationRequest):
        """Generate anime video with comprehensive error handling"""
        try:
            # This would integrate with the actual generation system
            result = {
                "success": True,
                "job_id": f"job_{int(time.time())}",
                "estimated_time": request.duration * 60,  # seconds
                "status": "queued",
                "request_data": request.dict()
            }

            return JSONResponse(content=result)

        except Exception as e:
            raise APIError(
                f"Generation request failed: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error_code="GENERATION_FAILED"
            )

    @app.get("/api/health")
    async def health_check():
        """API health check endpoint"""
        health_data = await api_handler.get_api_health()
        return JSONResponse(content=health_data)

    @app.get("/api/status/{job_id}")
    async def get_job_status(job_id: str):
        """Get generation job status"""
        # This would check actual job status
        status_data = {
            "job_id": job_id,
            "status": "processing",
            "progress_percent": 45,
            "estimated_completion": datetime.utcnow().isoformat(),
            "message": "Generating video frames..."
        }

        return JSONResponse(content=status_data)

# Example usage and testing
async def test_api_handler():
    """Test the enhanced API handler"""
    config = APIConfig(port=8329, debug=True)  # Use different port for testing
    api_handler = create_api_handler(config)

    # Set up routes
    setup_anime_api_routes(api_handler)

    # Get health status
    health = await api_handler.get_api_health()
    print("API Health:", json.dumps(health, indent=2, default=str))

    print(f"API configured on port {config.port}")
    print("Routes configured:")
    for route in api_handler.app.routes:
        if hasattr(route, 'path'):
            print(f"  {route.methods} {route.path}")

if __name__ == "__main__":
    # Run the test
    asyncio.run(test_api_handler())