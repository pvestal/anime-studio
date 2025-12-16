"""Authentication middleware for Anime Production API"""

import os
import time
from functools import lru_cache
from typing import Optional

import httpx
import jwt
from fastapi import Header, HTTPException

# Configuration
AUTH_SERVICE_URL = "http://localhost:8088"
JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY", "tower_jwt_secret_2025"
)  # Should match auth service


@lru_cache()
def get_jwt_secret():
    """Get JWT secret, preferably from Vault"""
    try:
        import hvac

        vault = hvac.Client(url="http://127.0.0.1:8200")
        vault.token = os.getenv("VAULT_ROOT_TOKEN")

        # Try to read JWT secret from Vault
        secret = vault.secrets.kv.v2.read_secret_version(path="auth/jwt")
        return secret["data"]["data"]["secret_key"]
    except Exception:
        # Fallback to environment variable or default
        return JWT_SECRET_KEY


async def verify_token_with_auth_service(token: str) -> dict:
    """Verify token with the Tower auth service"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{AUTH_SERVICE_URL}/api/auth/verify",
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code == 200:
                return response.json()
            return None
    except Exception as e:
        print(f"Auth service verification failed: {e}")
        return None


def verify_jwt_locally(token: str) -> dict:
    """Verify JWT token locally as fallback"""
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])

        # Check expiration
        if payload.get("exp", 0) < time.time():
            raise HTTPException(status_code=401, detail="Token expired")

        return {
            "valid": True,
            "user": payload.get("user", "anonymous"),
            "email": payload.get("email"),
            "expires": payload.get("exp"),
        }
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def require_auth(authorization: Optional[str] = Header(None)) -> dict:
    """Require valid authentication for protected endpoints"""

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Invalid authorization format. Use: Bearer <token>"
        )

    token = authorization.replace("Bearer ", "")

    # Try auth service first
    user_data = await verify_token_with_auth_service(token)

    # Fallback to local verification
    if not user_data:
        user_data = verify_jwt_locally(token)

    if not user_data or not user_data.get("valid"):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return user_data


async def optional_auth(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Optional authentication - returns None if no token provided"""
    if not authorization:
        return None

    try:
        return await require_auth(authorization)
    except HTTPException:
        return None


from collections import defaultdict
from datetime import datetime, timedelta
# Rate limiting decorator
from functools import wraps


class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Check if request is allowed within rate limit"""
        now = datetime.now()
        cutoff = now - timedelta(seconds=window_seconds)

        # Clean old requests
        self.requests[key] = [
            req_time for req_time in self.requests[key] if req_time > cutoff
        ]

        # Check limit
        if len(self.requests[key]) >= max_requests:
            return False

        # Add this request
        self.requests[key].append(now)
        return True


rate_limiter = RateLimiter()


def rate_limit(max_requests: int = 10, window_seconds: int = 60):
    """Rate limiting decorator"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get user from auth if available
            user_data = kwargs.get("user_data", {})
            user_key = user_data.get("email", "anonymous")

            # Check rate limit
            if not rate_limiter.is_allowed(user_key, max_requests, window_seconds):
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds} seconds",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# Example usage in FastAPI:
"""
from auth_middleware import require_auth, optional_auth, rate_limit

@app.post("/api/anime/generate")
@rate_limit(max_requests=10, window_seconds=60)
async def generate_anime(
    request: GenerateRequest,
    user_data: dict = Depends(require_auth)
):
    # User is authenticated
    print(f"Generating for user: {user_data['email']}")
    # ... generation logic ...

@app.get("/api/anime/gallery")
async def get_gallery(
    user_data: Optional[dict] = Depends(optional_auth)
):
    # Authentication optional
    if user_data:
        print(f"Authenticated user: {user_data['email']}")
    else:
        print("Anonymous user")
    # ... gallery logic ...
"""
