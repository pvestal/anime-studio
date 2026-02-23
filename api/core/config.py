"""
Configuration management for Tower Anime Production API
Domain-aware configuration system for network accessibility
"""

import os
import secrets
import psycopg2
from typing import Any, Optional


def get_environment() -> str:
    """Get current environment (development, production, etc.)"""
    return os.getenv('TOWER_ENVIRONMENT', 'development')


def get_domain() -> str:
    """Get base domain for services"""
    env = get_environment()
    if env == 'production':
        return os.getenv('TOWER_DOMAIN', 'tower.local')
    else:
        # Development: use IP for local network access
        return os.getenv('TOWER_DOMAIN', '192.168.50.135')


def get_service_url(service_name: str, port: int, protocol: str = 'http') -> str:
    """Generate service URL based on environment and domain"""
    domain = get_domain()
    return f"{protocol}://{domain}:{port}"


def get_database_host() -> str:
    """Get database host based on environment and local availability"""
    # Check if explicitly set via environment
    db_host = os.getenv('DATABASE_HOST')
    if db_host:
        return db_host

    # For development, check if we're running on the same machine as the database
    # If PostgreSQL is available locally, use localhost for better performance and security
    import socket
    try:
        # Try to connect to PostgreSQL locally first
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 5432))
        sock.close()
        if result == 0:
            return 'localhost'  # Use localhost if PostgreSQL is available locally
    except:
        pass

    # Fall back to domain-aware configuration for remote PostgreSQL
    return get_domain()


def get_database_password() -> str:
    """Get database password from environment"""
    password = os.getenv('DATABASE_PASSWORD')
    if not password:
        # Use default for development - should be overridden in production
        password = 'RP78eIrW7cI2jYvL5akt1yurE'
    return password


class SystemConfig:
    """Single source of truth for system configuration"""
    _cache = {}

    @classmethod
    def get(cls, key: str, default=None):
        """Get config value from database with caching"""
        if key not in cls._cache:
            try:
                conn = psycopg2.connect(
                    host=get_database_host(),
                    database='tower_consolidated',
                    user='patrick',
                    password=get_database_password()
                )
                with conn.cursor() as cur:
                    cur.execute("SELECT value FROM system_config WHERE key = %s", (key,))
                    result = cur.fetchone()
                    cls._cache[key] = result[0] if result else default
                conn.close()
            except Exception:
                # Fallback to default if database unavailable
                cls._cache[key] = default
        return cls._cache[key]

    @classmethod
    def refresh(cls):
        """Clear cache to reload from database"""
        cls._cache = {}


# Service URLs Configuration
COMFYUI_URL = get_service_url('comfyui', 8188)
ECHO_BRAIN_URL = get_service_url('echo-brain', 8309)
DASHBOARD_URL = get_service_url('dashboard', 8080)
KNOWLEDGE_BASE_URL = get_service_url('knowledge-base', 8307)
AUTH_SERVICE_URL = get_service_url('auth', 8088)

# Database Configuration
DATABASE_HOST = get_database_host()
DATABASE_URL = f"postgresql://patrick:{get_database_password()}@{DATABASE_HOST}/anime_production"

# Authentication Configuration
JWT_SECRET = os.getenv('JWT_SECRET_KEY', secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

# CORS Configuration - Domain-aware origins
def get_cors_origins() -> list:
    """Generate CORS origins based on domain configuration"""
    domain = get_domain()
    base_origins = [
        f"http://{domain}:3000",
        f"http://{domain}:8080",
        f"http://{domain}:8088",
        f"http://{domain}:8307",
        f"http://{domain}:8309",
        f"http://{domain}:8328",
        f"https://{domain}:3000",
        f"https://{domain}:8080",
    ]

    # Add localhost for development
    if get_environment() == 'development':
        base_origins.extend([
            "http://localhost:3000",
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8080",
        ])

    return base_origins

CORS_ORIGINS = get_cors_origins()

# Static Files Configuration
STATIC_DIR = "/opt/anime-studio/static"
MEDIA_DIR = "/opt/anime-studio/media"

# Network Configuration
BIND_HOST = os.getenv('BIND_HOST', '0.0.0.0')  # Bind to all interfaces by default
SERVICE_PORT = int(os.getenv('SERVICE_PORT', '8328'))