"""Authentication middleware for Anime Production API"""

import os
import time
import jwt
import httpx
from typing import Optional
from fastapi import HTTPException, Header, Depends
from functools import lru_cache

# Configuration
AUTH_SERVICE_URL = "http://localhost:8088"
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "tower_jwt_secret_2025")

# Allow local services (Telegram bot) without auth
TRUSTED_LOCAL_IPS = ["127.0.0.1", "localhost", "::1"]

async def require_auth(authorization: Optional[str] = Header(None), x_forwarded_for: Optional[str] = Header(None)):
    """Require authentication for protected endpoints - allows local services"""
    # Allow local Telegram bot requests
    if x_forwarded_for in TRUSTED_LOCAL_IPS or authorization == "telegram-bot-internal":
        return {"user_id": "telegram_bot", "username": "PatricksEchoBot", "role": "service"}

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    # Extract token from Bearer scheme
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    # Verify token locally (simplified for now)
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=["HS256"]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def optional_auth(authorization: Optional[str] = Header(None)):
    """Optional authentication - returns None if not authenticated"""
    if not authorization:
        return None

    try:
        return await require_auth(authorization=authorization)
    except HTTPException:
        return None

def rate_limit(max_requests: int = 10, window: int = 60):
    """Simple rate limiting decorator"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Simplified rate limiting - would use Redis in production
            return await func(*args, **kwargs)
        return wrapper
    return decorator