"""
SQLAlchemy database configuration for anime production system.
Provides session management and FastAPI dependency injection.
"""

import logging
import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine.events import event
from sqlalchemy.orm import Session, sessionmaker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration from environment variables (matching secured_api.py)
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "anime_production"),
    "user": os.getenv("DB_USER", "patrick"),
    "password": os.getenv(
        "DB_PASSWORD", "tower_echo_brain_secret_key_2025"
    ),  # Fallback from secured_api.py
}

# Construct PostgreSQL connection URL
DATABASE_URL = (
    f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
    f"{DB_CONFIG['host']}/{DB_CONFIG['database']}"
)

# Create SQLAlchemy engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL debugging
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=300,  # Recycle connections every 5 minutes
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models (imported from models.py)
from models import Base


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency to get database session.

    Usage in FastAPI routes:
    @app.get("/api/anime/projects")


    async def get_projects(db: Session = Depends(get_db)):
        return db.query(Project).all()
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def init_database():
    """
    Initialize database connection and create tables if needed.
    Call this at application startup.
    """
    try:
        # Test database connection
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")

        # Create all tables (will only create missing ones)
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


def close_database():
    """
    Close database connections.
    Call this at application shutdown.
    """
    try:
        engine.dispose()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")


# Event listeners for connection monitoring
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set connection parameters if needed"""


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    """Log when connections are checked out (for debugging)"""
    logger.debug("Connection checked out from pool")


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_connection, connection_record):
    """Log when connections are returned to pool (for debugging)"""
    logger.debug("Connection returned to pool")


# Database utilities


class DatabaseHealth:
    """Database health check utilities"""

    @staticmethod
    def check_connection() -> bool:
        """Check if database is accessible"""
        try:
            from sqlalchemy import text

            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    @staticmethod
    def get_connection_info() -> dict:
        """Get database connection information"""
        try:
            pool = engine.pool
            return {
                "status": (
                    "healthy" if DatabaseHealth.check_connection() else "unhealthy"
                ),
                "database": DB_CONFIG["database"],
                "host": DB_CONFIG["host"],
                "pool_size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "invalid": pool.invalid(),
            }
        except Exception as e:
            logger.error(f"Error getting connection info: {e}")
            return {"status": "error", "error": str(e)}


# Async database utilities (for future async support)
# from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
# async_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
# AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession)

# async def get_async_db() -> AsyncSession:
#     """Async database session dependency"""
#     async with AsyncSessionLocal() as session:
#         try:
#             yield session
#         except Exception as e:
#             logger.error(f"Async database session error: {e}")
#             await session.rollback()
#             raise
#         finally:
#             await session.close()
