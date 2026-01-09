#!/usr/bin/env python3
"""
Enhanced Database Manager with Connection Pooling and Error Recovery
Provides robust database operations with automatic failover, connection pooling,
and comprehensive error handling for the anime production system.
"""

import asyncio
import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor, Json
from psycopg2 import OperationalError, DatabaseError, InterfaceError
import logging
import time
import json
import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union, Callable, AsyncGenerator
from contextlib import contextmanager, asynccontextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
import threading
import queue
import sqlite3

# Import our error handling framework
from shared.error_handling import (
    AnimeGenerationError, ErrorSeverity, ErrorCategory,
    RetryManager, MetricsCollector, OperationMetrics
)

logger = logging.getLogger(__name__)

def get_vault_secret() -> str:
    """Get database password from HashiCorp Vault"""
    try:
        import hvac
        client = hvac.Client(url='http://127.0.0.1:8200')

        # Try to get vault token from environment or file
        vault_token = os.environ.get('VAULT_TOKEN')
        if not vault_token:
            try:
                with open('/opt/vault/.vault-token', 'r') as f:
                    vault_token = f.read().strip()
            except FileNotFoundError:
                pass

        if vault_token:
            client.token = vault_token
            secret = client.secrets.kv.v2.read_secret_version(path='anime/database')
            return secret['data']['data']['password']
    except Exception as e:
        logger.warning(f"Could not get password from Vault: {e}")

    # Fallback to environment variable
    return os.environ.get('ANIME_DB_PASSWORD', 'tower_echo_brain_secret_key_2025')

@dataclass
class DatabaseConfig:
    """Database configuration with fallback options"""
    # Primary database (PostgreSQL)
    primary_host: str = "localhost"
    primary_port: int = 5433
    primary_database: str = "anime_production"
    primary_user: str = "patrick"
    primary_password: str = field(default_factory=lambda: get_vault_secret())

    # Connection pool settings
    min_connections: int = 2
    max_connections: int = 10
    connection_timeout: int = 30
    idle_timeout: int = 300  # 5 minutes

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0
    max_retry_delay: float = 30.0

    # Fallback database (SQLite)
    fallback_enabled: bool = True
    fallback_path: str = "/opt/tower-anime-production/database/fallback.db"

    # Health check settings
    health_check_interval: int = 60  # seconds
    connection_test_query: str = "SELECT 1"

class DatabaseError(AnimeGenerationError):
    """Database-specific errors"""

    def __init__(self, message: str, query: str = None, params: Any = None,
                 original_error: Exception = None, **kwargs):
        super().__init__(message, ErrorCategory.SYSTEM, ErrorSeverity.HIGH, **kwargs)
        self.query = query
        self.params = params
        self.original_error = original_error
        self.context.update({
            "query": query,
            "params": str(params) if params else None,
            "original_error": str(original_error) if original_error else None,
            "service": "database"
        })

class ConnectionPoolManager:
    """Manages PostgreSQL connection pool with health monitoring"""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.pool = None
        self.pool_lock = threading.Lock()
        self.last_health_check = None
        self.is_healthy = False
        self.connection_count = 0
        self.failed_connections = 0

    def initialize_pool(self) -> bool:
        """Initialize the connection pool"""
        try:
            with self.pool_lock:
                if self.pool:
                    self.pool.closeall()

                # Build connection string
                conn_string = (
                    f"host={self.config.primary_host} "
                    f"port={self.config.primary_port} "
                    f"dbname={self.config.primary_database} "
                    f"user={self.config.primary_user} "
                    f"password={self.config.primary_password} "
                    f"connect_timeout={self.config.connection_timeout}"
                )

                self.pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=self.config.min_connections,
                    maxconn=self.config.max_connections,
                    dsn=conn_string,
                    cursor_factory=RealDictCursor
                )

                # Test the pool
                test_conn = self.pool.getconn()
                try:
                    with test_conn.cursor() as cur:
                        cur.execute(self.config.connection_test_query)
                        cur.fetchone()
                    self.is_healthy = True
                    logger.info(f"✅ Database pool initialized: {self.config.min_connections}-{self.config.max_connections} connections")
                finally:
                    self.pool.putconn(test_conn)

                return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize database pool: {e}")
            self.is_healthy = False
            return False

    @contextmanager
    def get_connection(self):
        """Get connection from pool with automatic cleanup"""
        if not self.pool or not self.is_healthy:
            if not self.initialize_pool():
                raise DatabaseError("Database pool unavailable and initialization failed")

        conn = None
        try:
            conn = self.pool.getconn()
            if conn is None:
                raise DatabaseError("No connections available in pool")

            self.connection_count += 1
            yield conn

        except Exception as e:
            self.failed_connections += 1
            if conn:
                conn.rollback()
            raise DatabaseError(
                f"Database connection error: {str(e)}",
                original_error=e
            )
        finally:
            if conn:
                try:
                    self.pool.putconn(conn)
                except Exception as e:
                    logger.error(f"Error returning connection to pool: {e}")

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        if not self.pool:
            return {"status": "not_initialized"}

        return {
            "status": "healthy" if self.is_healthy else "unhealthy",
            "min_connections": self.config.min_connections,
            "max_connections": self.config.max_connections,
            "total_connections_used": self.connection_count,
            "failed_connections": self.failed_connections,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None
        }

    def close_pool(self):
        """Close all connections in the pool"""
        with self.pool_lock:
            if self.pool:
                self.pool.closeall()
                self.pool = None
                self.is_healthy = False
                logger.info("Database pool closed")

class FallbackDatabase:
    """SQLite fallback database for when PostgreSQL is unavailable"""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection_lock = threading.Lock()
        self._initialize_schema()

    def _initialize_schema(self):
        """Initialize SQLite schema for fallback operations"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS fallback_operations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        operation_type TEXT NOT NULL,
                        data JSON NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        synced_to_primary BOOLEAN DEFAULT FALSE
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS generation_requests (
                        id TEXT PRIMARY KEY,
                        prompt TEXT NOT NULL,
                        character_name TEXT,
                        duration INTEGER,
                        style TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS error_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        error_id TEXT UNIQUE,
                        message TEXT NOT NULL,
                        category TEXT,
                        severity TEXT,
                        context JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                conn.commit()
                logger.info("✅ Fallback database schema initialized")

        except Exception as e:
            logger.error(f"❌ Failed to initialize fallback database: {e}")

    @contextmanager
    def get_connection(self):
        """Get SQLite connection with thread safety"""
        with self.connection_lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Dict-like access
            try:
                yield conn
            finally:
                conn.close()

    def log_operation(self, operation_type: str, data: Dict[str, Any]) -> bool:
        """Log operation to fallback database"""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "INSERT INTO fallback_operations (operation_type, data) VALUES (?, ?)",
                    (operation_type, json.dumps(data, default=str))
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to log fallback operation: {e}")
            return False

    def get_pending_operations(self) -> List[Dict[str, Any]]:
        """Get operations pending sync to primary database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT id, operation_type, data, created_at
                    FROM fallback_operations
                    WHERE synced_to_primary = FALSE
                    ORDER BY created_at
                """)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get pending operations: {e}")
            return []

class EnhancedDatabaseManager:
    """Enhanced database manager with pooling, fallback, and error recovery"""

    def __init__(self, config: DatabaseConfig = None, metrics_collector: MetricsCollector = None):
        self.config = config or DatabaseConfig()
        self.metrics_collector = metrics_collector
        self.pool_manager = ConnectionPoolManager(self.config)
        self.fallback_db = FallbackDatabase(self.config.fallback_path) if self.config.fallback_enabled else None
        self.retry_manager = RetryManager()

        # Initialize connection pool
        self.pool_manager.initialize_pool()

    @contextmanager
    def get_db_connection(self, use_fallback_on_failure: bool = True):
        """Get database connection with automatic fallback"""
        try:
            with self.pool_manager.get_connection() as conn:
                yield conn, False  # (connection, is_fallback)
        except Exception as e:
            if use_fallback_on_failure and self.fallback_db:
                logger.warning(f"Primary database unavailable, using fallback: {e}")
                with self.fallback_db.get_connection() as fallback_conn:
                    yield fallback_conn, True  # (connection, is_fallback)
            else:
                raise DatabaseError(
                    f"Database connection failed: {str(e)}",
                    original_error=e
                )

    async def execute_query_robust(self, query: str, params: Any = None,
                                 fetch_result: bool = True, operation_type: str = "query") -> Any:
        """Execute query with comprehensive error handling and retry logic"""
        operation_id = f"db_{operation_type}_{int(time.time())}"
        metrics = OperationMetrics(
            operation_id=operation_id,
            operation_type=f"database_{operation_type}",
            start_time=datetime.utcnow(),
            context={"query": query[:100], "has_params": params is not None}
        )

        async def _execute_with_retry():
            with self.get_db_connection() as (conn, is_fallback):
                try:
                    with conn.cursor() as cur:
                        if params:
                            cur.execute(query, params)
                        else:
                            cur.execute(query)

                        result = None
                        if fetch_result:
                            if query.strip().upper().startswith('SELECT'):
                                result = cur.fetchall()
                            else:
                                result = cur.rowcount

                        if not is_fallback:
                            conn.commit()

                        return result, is_fallback

                except Exception as e:
                    if not is_fallback:
                        conn.rollback()
                    raise e

        try:
            result, is_fallback = await self.retry_manager.retry_with_backoff(
                _execute_with_retry,
                max_retries=self.config.max_retries,
                base_delay=self.config.retry_delay,
                max_delay=self.config.max_retry_delay,
                exceptions=(psycopg2.Error, sqlite3.Error, DatabaseError)
            )

            metrics.complete(True, {"is_fallback": is_fallback})
            if self.metrics_collector:
                await self.metrics_collector.log_operation(metrics)

            if is_fallback:
                # Log to fallback database for later sync
                self.fallback_db.log_operation(operation_type, {
                    "query": query,
                    "params": params,
                    "result_type": type(result).__name__,
                    "timestamp": datetime.utcnow().isoformat()
                })

            return result

        except Exception as e:
            error = DatabaseError(
                f"Database operation failed: {str(e)}",
                query=query,
                params=params,
                original_error=e,
                correlation_id=operation_id
            )

            metrics.complete(False, error.to_dict())
            if self.metrics_collector:
                await self.metrics_collector.log_operation(metrics)
                await self.metrics_collector.log_error(error)

            raise error

    async def execute_transaction_robust(self, operations: List[Dict[str, Any]]) -> List[Any]:
        """Execute multiple operations in a transaction with rollback support"""
        operation_id = f"db_transaction_{int(time.time())}"
        metrics = OperationMetrics(
            operation_id=operation_id,
            operation_type="database_transaction",
            start_time=datetime.utcnow(),
            context={"operation_count": len(operations)}
        )

        results = []

        try:
            with self.get_db_connection() as (conn, is_fallback):
                if is_fallback:
                    # SQLite autocommit mode - execute operations individually
                    for op in operations:
                        with conn:
                            cur = conn.cursor()
                            cur.execute(op['query'], op.get('params'))
                            if op.get('fetch_result', False):
                                results.append(cur.fetchall())
                            else:
                                results.append(cur.rowcount)
                else:
                    # PostgreSQL transaction
                    try:
                        with conn:
                            with conn.cursor() as cur:
                                for op in operations:
                                    cur.execute(op['query'], op.get('params'))
                                    if op.get('fetch_result', False):
                                        results.append(cur.fetchall())
                                    else:
                                        results.append(cur.rowcount)
                    except Exception as e:
                        conn.rollback()
                        raise e

            metrics.complete(True, {"is_fallback": is_fallback, "results_count": len(results)})
            if self.metrics_collector:
                await self.metrics_collector.log_operation(metrics)

            return results

        except Exception as e:
            error = DatabaseError(
                f"Transaction failed: {str(e)}",
                original_error=e,
                correlation_id=operation_id
            )

            metrics.complete(False, error.to_dict())
            if self.metrics_collector:
                await self.metrics_collector.log_operation(metrics)
                await self.metrics_collector.log_error(error)

            raise error

    # High-level convenience methods for anime production

    async def save_generation_request(self, request_data: Dict[str, Any]) -> str:
        """Save generation request to database"""
        query = """
        INSERT INTO generation_requests (id, prompt, character_name, duration, style, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """

        request_id = request_data.get('id', f"gen_{int(time.time())}")
        params = (
            request_id,
            request_data.get('prompt'),
            request_data.get('character_name'),
            request_data.get('duration'),
            request_data.get('style'),
            request_data.get('status', 'pending'),
            datetime.utcnow()
        )

        result = await self.execute_query_robust(query, params, fetch_result=True, operation_type="insert_generation")
        return request_id

    async def update_generation_status(self, request_id: str, status: str, result_data: Dict[str, Any] = None) -> bool:
        """Update generation request status"""
        query = """
        UPDATE generation_requests
        SET status = %s, result_data = %s, updated_at = %s
        WHERE id = %s
        """

        params = (status, Json(result_data) if result_data else None, datetime.utcnow(), request_id)

        result = await self.execute_query_robust(query, params, fetch_result=False, operation_type="update_generation")
        return result > 0

    async def get_generation_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get generation request by ID"""
        query = "SELECT * FROM generation_requests WHERE id = %s"

        result = await self.execute_query_robust(query, (request_id,), fetch_result=True, operation_type="select_generation")
        return dict(result[0]) if result else None

    async def get_active_generations(self) -> List[Dict[str, Any]]:
        """Get all active generation requests"""
        query = """
        SELECT * FROM generation_requests
        WHERE status IN ('pending', 'processing', 'generating')
        ORDER BY created_at
        """

        result = await self.execute_query_robust(query, fetch_result=True, operation_type="select_active_generations")
        return [dict(row) for row in result] if result else []

    async def save_character_data(self, character_name: str, character_data: Dict[str, Any]) -> bool:
        """Save or update character data"""
        query = """
        INSERT INTO characters (name, data, updated_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (name) DO UPDATE SET
            data = EXCLUDED.data,
            updated_at = EXCLUDED.updated_at
        """

        params = (character_name, Json(character_data), datetime.utcnow())
        result = await self.execute_query_robust(query, params, fetch_result=False, operation_type="upsert_character")
        return result > 0

    async def get_character_data(self, character_name: str) -> Optional[Dict[str, Any]]:
        """Get character data by name"""
        query = "SELECT data FROM characters WHERE name = %s"

        result = await self.execute_query_robust(query, (character_name,), fetch_result=True, operation_type="select_character")
        return result[0]['data'] if result else None

    async def log_error_to_db(self, error: AnimeGenerationError) -> bool:
        """Log error to database"""
        query = """
        INSERT INTO error_logs (error_id, message, category, severity, context, stack_trace, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (error_id) DO NOTHING
        """

        error_data = error.to_dict()
        params = (
            error_data["error_id"],
            error_data["message"],
            error_data["category"],
            error_data["severity"],
            Json(error_data["context"]),
            error_data["stack_trace"],
            error_data["timestamp"]
        )

        try:
            result = await self.execute_query_robust(query, params, fetch_result=False, operation_type="insert_error_log")
            return result > 0
        except Exception as e:
            logger.error(f"Failed to log error to database: {e}")
            return False

    async def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive database system health"""
        pool_stats = self.pool_manager.get_pool_stats()

        # Test database connectivity
        try:
            await self.execute_query_robust("SELECT 1", fetch_result=True, operation_type="health_check")
            db_status = "healthy"
        except Exception as e:
            db_status = f"unhealthy: {str(e)}"

        # Check recent error rates
        error_count_query = """
        SELECT COUNT(*) as error_count
        FROM error_logs
        WHERE timestamp > NOW() - INTERVAL '1 hour'
        """

        try:
            error_result = await self.execute_query_robust(error_count_query, fetch_result=True, operation_type="error_count")
            recent_errors = error_result[0]['error_count'] if error_result else 0
        except Exception:
            recent_errors = 0

        # Check pending operations in fallback
        pending_operations = 0
        if self.fallback_db:
            try:
                pending_ops = self.fallback_db.get_pending_operations()
                pending_operations = len(pending_ops)
            except Exception:
                pass

        return {
            "database_status": db_status,
            "connection_pool": pool_stats,
            "recent_errors_1h": recent_errors,
            "fallback_enabled": self.config.fallback_enabled,
            "pending_fallback_operations": pending_operations,
            "last_check": datetime.utcnow().isoformat()
        }

    async def sync_fallback_operations(self) -> int:
        """Sync pending fallback operations to primary database"""
        if not self.fallback_db:
            return 0

        pending_ops = self.fallback_db.get_pending_operations()
        synced_count = 0

        for op in pending_ops:
            try:
                # Attempt to replay operation on primary database
                data = json.loads(op['data'])
                query = data.get('query')
                params = data.get('params')

                if query:
                    await self.execute_query_robust(query, params, fetch_result=False, operation_type="sync_fallback")

                    # Mark as synced in fallback database
                    with self.fallback_db.get_connection() as conn:
                        conn.execute(
                            "UPDATE fallback_operations SET synced_to_primary = TRUE WHERE id = ?",
                            (op['id'],)
                        )
                        conn.commit()

                    synced_count += 1

            except Exception as e:
                logger.error(f"Failed to sync fallback operation {op['id']}: {e}")

        if synced_count > 0:
            logger.info(f"✅ Synced {synced_count} fallback operations to primary database")

        return synced_count

    def close(self):
        """Close all database connections"""
        self.pool_manager.close_pool()

# Factory function
def create_database_manager(config: DatabaseConfig = None, metrics_collector: MetricsCollector = None) -> EnhancedDatabaseManager:
    """Create configured database manager instance"""
    return EnhancedDatabaseManager(config, metrics_collector)

# Example usage and testing
async def test_database_manager():
    """Test the enhanced database manager"""
    db_manager = create_database_manager()

    try:
        # Test basic connectivity
        print("Testing database connectivity...")
        result = await db_manager.execute_query_robust("SELECT 1 as test", fetch_result=True)
        print("✅ Database connectivity test passed")

        # Test health check
        print("\nGetting system health...")
        health = await db_manager.get_system_health()
        print("System Health:", json.dumps(health, indent=2, default=str))

        # Test generation request operations
        print("\nTesting generation request operations...")

        request_data = {
            'id': f'test_{int(time.time())}',
            'prompt': 'test anime character',
            'character_name': 'Test Character',
            'duration': 5,
            'style': 'anime'
        }

        # Save request
        request_id = await db_manager.save_generation_request(request_data)
        print(f"✅ Saved generation request: {request_id}")

        # Update status
        await db_manager.update_generation_status(request_id, 'completed', {'output_path': '/test/path'})
        print(f"✅ Updated generation status: {request_id}")

        # Retrieve request
        retrieved = await db_manager.get_generation_request(request_id)
        print(f"✅ Retrieved generation request: {retrieved['id'] if retrieved else 'Not found'}")

    except Exception as e:
        print(f"❌ Test failed: {e}")
    finally:
        db_manager.close()

if __name__ == "__main__":
    asyncio.run(test_database_manager())