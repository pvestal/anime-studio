#!/usr/bin/env python3
"""
Database Manager for Anime Production System
Clean, modular database operations using psycopg2 and threading
Inspired by Echo Brain's architecture with separation of concerns
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
from contextlib import contextmanager
import json
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor, Json
from psycopg2 import OperationalError, DatabaseError as Psycopg2DatabaseError
from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class DatabaseConfig:
    """Database configuration class"""
    def __init__(self):
        self.host = "192.168.50.135"
        self.port = 5432
        self.database = "anime_production"
        self.user = "patrick"
        self.password = "tower_echo_brain_secret_key_2025"
        self.pool_size = 5
        self.max_overflow = 10
        self.pool_timeout = 30

    @property
    def connection_params(self) -> Dict[str, Any]:
        """Get psycopg2 connection parameters"""
        return {
            'host': self.host,
            'port': self.port,
            'database': self.database,
            'user': self.user,
            'password': self.password,
            'cursor_factory': RealDictCursor
        }

class DatabaseError(Exception):
    """Custom database error class"""
    def __init__(self, message: str, original_error: Exception = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)

class DatabaseManager:
    """
    Clean database manager for anime production system
    Handles all database operations with connection pooling and error handling
    """

    def __init__(self, config: DatabaseConfig = None):
        self.config = config or DatabaseConfig()
        self.pool = None
        self.pool_lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize database connections and create tables"""
        try:
            # Create connection pool
            self.pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=self.config.pool_size,
                **self.config.connection_params
            )

            self._initialized = True  # Set this before creating tables

            # Create tables if they don't exist
            self._create_tables()

            # Test connection
            self._test_connection()

            logger.info("✅ Database manager initialized successfully")
            return True

        except Exception as e:
            self._initialized = False
            logger.error(f"❌ Failed to initialize database manager: {e}")
            raise DatabaseError(f"Database initialization failed: {e}", e)

    def _create_tables(self):
        """Create database tables if they don't exist"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Create generation_jobs table
                    cur.execute("""
                    CREATE TABLE IF NOT EXISTS generation_jobs (
                        id TEXT PRIMARY KEY,
                        prompt TEXT NOT NULL,
                        character_name TEXT,
                        duration REAL,
                        style TEXT,
                        status TEXT DEFAULT 'pending',
                        progress INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        output_path TEXT,
                        error_message TEXT,
                        metadata JSONB
                    )
                    """)

                    # Create index for better performance
                    cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_generation_jobs_status
                    ON generation_jobs(status)
                    """)

                    cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_generation_jobs_created
                    ON generation_jobs(created_at DESC)
                    """)

                conn.commit()
            logger.info("✅ Database tables created/verified")
        except Exception as e:
            logger.error(f"❌ Failed to create tables: {e}")
            raise DatabaseError(f"Table creation failed: {e}", e)

    def _test_connection(self):
        """Test database connection"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            logger.info("✅ Database connection test passed")
        except Exception as e:
            logger.error(f"❌ Database connection test failed: {e}")
            raise DatabaseError(f"Connection test failed: {e}", e)

    @contextmanager
    def get_connection(self):
        """Get database connection with automatic cleanup"""
        if not self._initialized:
            raise DatabaseError("Database manager not initialized")

        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise DatabaseError(f"Database connection error: {e}", e)
        finally:
            if conn:
                self.pool.putconn(conn)

    # Job Management Methods

    def save_job(self, job_data: Dict[str, Any]) -> str:
        """Save a new generation job to database"""
        try:
            job_id = job_data.get('id') or f"job_{uuid.uuid4().hex[:8]}"

            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                    INSERT INTO generation_jobs
                    (id, prompt, character_name, duration, style, status, progress, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        job_id,
                        job_data.get('prompt'),
                        job_data.get('character_name'),
                        job_data.get('duration'),
                        job_data.get('style'),
                        job_data.get('status', 'pending'),
                        job_data.get('progress', 0),
                        Json(job_data.get('metadata', {}))
                    ))
                conn.commit()

            logger.info(f"✅ Saved job {job_id} to database")
            return job_id

        except psycopg2.IntegrityError as e:
            logger.error(f"❌ Job {job_data.get('id')} already exists")
            raise DatabaseError(f"Job already exists: {e}", e)
        except Exception as e:
            logger.error(f"❌ Failed to save job: {e}")
            raise DatabaseError(f"Failed to save job: {e}", e)

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing job's status and progress"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Check if job exists
                    cur.execute("SELECT id FROM generation_jobs WHERE id = %s", (job_id,))
                    if not cur.fetchone():
                        logger.warning(f"Job {job_id} not found for update")
                        return False

                    # Build update query dynamically
                    update_fields = []
                    params = []

                    for key, value in updates.items():
                        if key in ['status', 'progress', 'output_path', 'error_message', 'metadata']:
                            if key == 'metadata':
                                update_fields.append(f"{key} = %s")
                                params.append(Json(value))
                            else:
                                update_fields.append(f"{key} = %s")
                                params.append(value)

                    # Always update the timestamp
                    update_fields.append("updated_at = %s")
                    params.append(datetime.utcnow())

                    # Set completed_at if status is completed
                    if updates.get('status') == 'completed':
                        update_fields.append("completed_at = %s")
                        params.append(datetime.utcnow())

                    # Set started_at if status changes to processing
                    if updates.get('status') == 'processing':
                        update_fields.append("started_at = %s")
                        params.append(datetime.utcnow())

                    if update_fields:
                        query = f"""
                        UPDATE generation_jobs
                        SET {', '.join(update_fields)}
                        WHERE id = %s
                        """
                        params.append(job_id)

                        cur.execute(query, params)
                        conn.commit()
                        logger.info(f"✅ Updated job {job_id}")
                        return True

                    return False

        except Exception as e:
            logger.error(f"❌ Failed to update job {job_id}: {e}")
            raise DatabaseError(f"Failed to update job: {e}", e)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a job by ID"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                    SELECT id, prompt, character_name, duration, style, status, progress,
                           created_at, updated_at, started_at, completed_at,
                           output_path, error_message, metadata
                    FROM generation_jobs
                    WHERE id = %s
                    """, (job_id,))

                    row = cur.fetchone()
                    if row:
                        job_data = {
                            'id': row['id'],
                            'prompt': row['prompt'],
                            'character_name': row['character_name'],
                            'duration': row['duration'],
                            'style': row['style'],
                            'status': row['status'],
                            'progress': row['progress'],
                            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                            'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
                            'started_at': row['started_at'].isoformat() if row['started_at'] else None,
                            'completed_at': row['completed_at'].isoformat() if row['completed_at'] else None,
                            'output_path': row['output_path'],
                            'error_message': row['error_message'],
                            'metadata': row['metadata'] or {}
                        }
                        logger.info(f"✅ Retrieved job {job_id}")
                        return job_data

                    logger.info(f"Job {job_id} not found")
                    return None

        except Exception as e:
            logger.error(f"❌ Failed to get job {job_id}: {e}")
            raise DatabaseError(f"Failed to get job: {e}", e)

    def list_jobs(self, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """List jobs with optional status filter"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    base_query = """
                    SELECT id, prompt, character_name, duration, style, status, progress,
                           created_at, updated_at, started_at, completed_at,
                           output_path, error_message, metadata
                    FROM generation_jobs
                    """

                    if status:
                        query = f"{base_query} WHERE status = %s ORDER BY created_at DESC LIMIT %s OFFSET %s"
                        cur.execute(query, (status, limit, offset))
                    else:
                        query = f"{base_query} ORDER BY created_at DESC LIMIT %s OFFSET %s"
                        cur.execute(query, (limit, offset))

                    jobs = []
                    for row in cur.fetchall():
                        job_data = {
                            'id': row['id'],
                            'prompt': row['prompt'],
                            'character_name': row['character_name'],
                            'duration': row['duration'],
                            'style': row['style'],
                            'status': row['status'],
                            'progress': row['progress'],
                            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                            'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
                            'started_at': row['started_at'].isoformat() if row['started_at'] else None,
                            'completed_at': row['completed_at'].isoformat() if row['completed_at'] else None,
                            'output_path': row['output_path'],
                            'error_message': row['error_message'],
                            'metadata': row['metadata'] or {}
                        }
                        jobs.append(job_data)

                    logger.info(f"✅ Retrieved {len(jobs)} jobs")
                    return jobs

        except Exception as e:
            logger.error(f"❌ Failed to list jobs: {e}")
            raise DatabaseError(f"Failed to list jobs: {e}", e)

    def get_active_jobs(self) -> List[Dict[str, Any]]:
        """Get all active (pending/processing) jobs"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                    SELECT id, prompt, character_name, duration, style, status, progress,
                           created_at, updated_at, started_at, completed_at,
                           output_path, error_message, metadata
                    FROM generation_jobs
                    WHERE status IN ('pending', 'processing')
                    ORDER BY created_at
                    """)

                    jobs = []
                    for row in cur.fetchall():
                        job_data = {
                            'id': row['id'],
                            'prompt': row['prompt'],
                            'character_name': row['character_name'],
                            'duration': row['duration'],
                            'style': row['style'],
                            'status': row['status'],
                            'progress': row['progress'],
                            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                            'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
                            'started_at': row['started_at'].isoformat() if row['started_at'] else None,
                            'completed_at': row['completed_at'].isoformat() if row['completed_at'] else None,
                            'output_path': row['output_path'],
                            'error_message': row['error_message'],
                            'metadata': row['metadata'] or {}
                        }
                        jobs.append(job_data)

                    logger.info(f"✅ Retrieved {len(jobs)} active jobs")
                    return jobs

        except Exception as e:
            logger.error(f"❌ Failed to get active jobs: {e}")
            raise DatabaseError(f"Failed to get active jobs: {e}", e)

    def delete_job(self, job_id: str) -> bool:
        """Delete a job from database"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM generation_jobs WHERE id = %s", (job_id,))

                    if cur.rowcount > 0:
                        conn.commit()
                        logger.info(f"✅ Deleted job {job_id}")
                        return True
                    else:
                        logger.warning(f"Job {job_id} not found for deletion")
                        return False

        except Exception as e:
            logger.error(f"❌ Failed to delete job {job_id}: {e}")
            raise DatabaseError(f"Failed to delete job: {e}", e)

    # Character Management Methods

    def save_character(self, character_data: Dict[str, Any]) -> bool:
        """Save character data to database using existing table structure"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # First check if we need to ensure a project exists
                    project_id = character_data.get('project_id', 1)

                    # Insert character using existing table structure
                    cur.execute("""
                    INSERT INTO characters (project_id, name, description, version)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                    """, (
                        project_id,
                        character_data.get('name'),
                        character_data.get('design_prompt', ''),  # Use design_prompt as description
                        character_data.get('version', 1)
                    ))

                    result = cur.fetchone()
                    character_id = result['id'] if result else None

                conn.commit()
                logger.info(f"✅ Saved character {character_data.get('name')} with ID {character_id}")
                return True

        except Exception as e:
            logger.error(f"❌ Failed to save character: {e}")
            raise DatabaseError(f"Failed to save character: {e}", e)

    # Health and Statistics Methods

    def get_health_status(self) -> Dict[str, Any]:
        """Get database health status"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Test connection
                    cur.execute("SELECT 1")
                    cur.fetchone()  # Consume the result

                    # Get job counts
                    cur.execute("""
                    SELECT
                        status,
                        COUNT(*) as count
                    FROM generation_jobs
                    GROUP BY status
                    """)

                    job_rows = cur.fetchall()
                    job_counts = {row['status']: row['count'] for row in job_rows} if job_rows else {}

                    # Get recent activity
                    cur.execute("""
                    SELECT COUNT(*)
                    FROM generation_jobs
                    WHERE created_at > NOW() - INTERVAL '24 hours'
                    """)

                    recent_result = cur.fetchone()
                    recent_jobs = recent_result[0] if recent_result else 0

                    return {
                        'status': 'healthy',
                        'connection': 'active',
                        'job_counts': job_counts,
                        'recent_jobs_24h': recent_jobs,
                        'timestamp': datetime.utcnow().isoformat()
                    }

        except Exception as e:
            logger.error(f"❌ Database health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    def close(self):
        """Close database connections"""
        if self.pool:
            self.pool.closeall()
            self.pool = None
        logger.info("✅ Database connections closed")

# Factory function for easy instantiation
def create_database_manager(config: DatabaseConfig = None) -> DatabaseManager:
    """Create and initialize a database manager"""
    manager = DatabaseManager(config)
    manager.initialize()
    return manager

# Example usage
def test_database_manager():
    """Test the database manager functionality"""
    try:
        # Create database manager
        db = create_database_manager()

        # Test job operations
        job_data = {
            'id': f'test_job_{int(time.time())}',
            'prompt': 'Test anime generation',
            'character_name': 'Test Character',
            'duration': 5.0,
            'style': 'anime'
        }

        # Save job
        job_id = db.save_job(job_data)
        print(f"Created job: {job_id}")

        # Update job
        db.update_job(job_id, {'status': 'processing', 'progress': 50})
        print(f"Updated job: {job_id}")

        # Get job
        retrieved_job = db.get_job(job_id)
        print(f"Retrieved job: {retrieved_job['status'] if retrieved_job else 'Not found'}")

        # List jobs
        jobs = db.list_jobs(limit=5)
        print(f"Total jobs found: {len(jobs)}")

        # Test active jobs
        active_jobs = db.get_active_jobs()
        print(f"Active jobs: {len(active_jobs)}")

        # Health check
        health = db.get_health_status()
        print(f"Database health: {health['status']}")
        print(f"Job counts: {health.get('job_counts', {})}")

        # Test deletion
        db.delete_job(job_id)
        print(f"Deleted test job: {job_id}")

        # Cleanup
        db.close()
        print("✅ Database manager test completed successfully")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise

if __name__ == "__main__":
    test_database_manager()