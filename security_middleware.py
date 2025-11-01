#!/usr/bin/env python3
"""
Security middleware for Anime Production API
Provides rate limiting, input validation, and request monitoring
"""

import time
import json
import logging
import hashlib
from collections import defaultdict, deque
from typing import Dict, Any, Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import re

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware to prevent abuse of generation endpoints"""

    def __init__(self, app, calls_per_minute: int = 60, calls_per_hour: int = 1000):
        super().__init__(app)
        self.calls_per_minute = calls_per_minute
        self.calls_per_hour = calls_per_hour
        self.minute_buckets: Dict[str, deque] = defaultdict(deque)
        self.hour_buckets: Dict[str, deque] = defaultdict(deque)

        # Stricter limits for generation endpoints
        self.generation_endpoints = {
            '/api/anime/generate': {'per_minute': 5, 'per_hour': 50},
            '/api/anime/projects': {'per_minute': 20, 'per_hour': 200}
        }

    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)
        current_time = time.time()

        # Clean old entries
        self._cleanup_buckets(current_time)

        # Check rate limits
        if self._is_rate_limited(client_ip, request.url.path, current_time):
            logger.warning(f"Rate limit exceeded for IP {client_ip} on path {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "Rate limit exceeded. Please try again later."}
            )

        # Record this request
        self._record_request(client_ip, current_time)

        response = await call_next(request)
        return response

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP from request headers"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup_buckets(self, current_time: float):
        """Remove old entries from rate limit buckets"""
        minute_cutoff = current_time - 60
        hour_cutoff = current_time - 3600

        for ip in list(self.minute_buckets.keys()):
            bucket = self.minute_buckets[ip]
            while bucket and bucket[0] < minute_cutoff:
                bucket.popleft()
            if not bucket:
                del self.minute_buckets[ip]

        for ip in list(self.hour_buckets.keys()):
            bucket = self.hour_buckets[ip]
            while bucket and bucket[0] < hour_cutoff:
                bucket.popleft()
            if not bucket:
                del self.hour_buckets[ip]

    def _is_rate_limited(self, client_ip: str, path: str, current_time: float) -> bool:
        """Check if request should be rate limited"""
        # Get limits for this endpoint
        limits = self.generation_endpoints.get(path, {
            'per_minute': self.calls_per_minute,
            'per_hour': self.calls_per_hour
        })

        minute_count = len(self.minute_buckets[client_ip])
        hour_count = len(self.hour_buckets[client_ip])

        return (minute_count >= limits['per_minute'] or
                hour_count >= limits['per_hour'])

    def _record_request(self, client_ip: str, current_time: float):
        """Record a request for rate limiting"""
        self.minute_buckets[client_ip].append(current_time)
        self.hour_buckets[client_ip].append(current_time)


class SecurityValidationMiddleware(BaseHTTPMiddleware):
    """Security validation middleware for request inspection"""

    def __init__(self, app):
        super().__init__(app)
        self.dangerous_patterns = [
            r'<script[^>]*>.*?</script>',  # Script tags
            r'javascript:',  # JavaScript protocols
            r'onload\s*=',  # Event handlers
            r'onerror\s*=',
            r'onclick\s*=',
            r'eval\s*\(',  # Code execution
            r'exec\s*\(',
            r'import\s+os',  # Python imports
            r'subprocess\.',
            r'__import__',
            r'\.\.\/.*\.\./',  # Path traversal
            r'\/etc\/passwd',  # System files
            r'\/proc\/',
            r'cmd\.exe',  # Windows commands
            r'powershell',
            r'SELECT.*FROM.*WHERE',  # SQL injection patterns
            r'INSERT.*INTO',
            r'UPDATE.*SET',
            r'DELETE.*FROM',
            r'DROP.*TABLE',
            r'UNION.*SELECT',
            r'LOAD_FILE\(',
            r'INTO.*OUTFILE',
        ]

        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.dangerous_patterns]

    async def dispatch(self, request: Request, call_next):
        # Skip security checks for GET requests to static files
        if request.method == "GET" and any(request.url.path.endswith(ext) for ext in ['.js', '.css', '.png', '.jpg', '.svg']):
            return await call_next(request)

        # Validate request
        try:
            await self._validate_request(request)
        except HTTPException as e:
            logger.error(f"Security validation failed for {request.url.path}: {e.detail}")
            return JSONResponse(
                status_code=e.status_code,
                content={"error": e.detail}
            )

        response = await call_next(request)
        return response

    async def _validate_request(self, request: Request):
        """Validate request for security threats"""
        # Check URL for malicious patterns
        self._check_for_malicious_content(request.url.path, "URL path")

        # Check query parameters
        for key, value in request.query_params.items():
            self._check_for_malicious_content(str(value), f"Query parameter '{key}'")

        # Check headers for injection attempts
        suspicious_headers = ['User-Agent', 'Referer', 'X-Forwarded-For']
        for header in suspicious_headers:
            value = request.headers.get(header)
            if value:
                self._check_for_malicious_content(value, f"Header '{header}'")

        # Check request body if present
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    # Check JSON content
                    try:
                        json_data = json.loads(body)
                        self._validate_json_data(json_data)
                    except json.JSONDecodeError:
                        # Check raw body content
                        body_str = body.decode('utf-8', errors='ignore')
                        self._check_for_malicious_content(body_str, "Request body")
            except Exception as e:
                logger.warning(f"Could not validate request body: {e}")

    def _check_for_malicious_content(self, content: str, context: str):
        """Check content for malicious patterns"""
        if not content:
            return

        for pattern in self.compiled_patterns:
            if pattern.search(content):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Malicious content detected in {context}"
                )

        # Check for excessively long content (potential DoS)
        if len(content) > 10000:  # 10KB limit
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Content too large in {context}"
            )

    def _validate_json_data(self, data: Any, depth: int = 0):
        """Recursively validate JSON data"""
        if depth > 10:  # Prevent deep nesting attacks
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON nesting too deep"
            )

        if isinstance(data, dict):
            for key, value in data.items():
                self._check_for_malicious_content(str(key), f"JSON key")
                if isinstance(value, str):
                    self._check_for_malicious_content(value, f"JSON value for key '{key}'")
                else:
                    self._validate_json_data(value, depth + 1)
        elif isinstance(data, list):
            if len(data) > 1000:  # Prevent large array attacks
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="JSON array too large"
                )
            for item in data:
                self._validate_json_data(item, depth + 1)
        elif isinstance(data, str):
            self._check_for_malicious_content(data, "JSON string value")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log security-relevant requests"""

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")

        # Log security-sensitive operations
        if self._is_sensitive_operation(request):
            logger.info(f"Security-sensitive request: {request.method} {request.url.path} from {client_ip}")

        response = await call_next(request)

        process_time = time.time() - start_time

        # Log slow requests (potential DoS attempts)
        if process_time > 10.0:
            logger.warning(f"Slow request detected: {request.method} {request.url.path} took {process_time:.2f}s from {client_ip}")

        # Log failed requests
        if response.status_code >= 400:
            logger.warning(f"Failed request: {response.status_code} {request.method} {request.url.path} from {client_ip}")

        return response

    def _is_sensitive_operation(self, request: Request) -> bool:
        """Check if this is a security-sensitive operation"""
        sensitive_paths = [
            '/api/anime/generate',
            '/api/anime/projects',
            '/api/admin',
            '/api/upload'
        ]

        return (request.method in ["POST", "PUT", "PATCH", "DELETE"] and
                any(request.url.path.startswith(path) for path in sensitive_paths))


def create_security_middleware(app):
    """Create and configure all security middleware"""
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(SecurityValidationMiddleware)
    app.add_middleware(RateLimitMiddleware, calls_per_minute=60, calls_per_hour=1000)
    return app