#!/usr/bin/env python3
"""
Database connection and operations for anime production system
Using asyncpg for async PostgreSQL operations
"""

import asyncpg
import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration from environment
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': os.getenv('DB_NAME', 'anime_production'),
    'user': os.getenv('DB_USER', 'patrick'),
    'password': os.getenv('DB_PASSWORD', '')
}

class DatabaseManager:
    """Manages database connections and operations"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def initialize(self):
        """Create connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                **DB_CONFIG,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.info("Database pool created successfully")

            # Ensure tables have required columns
            await self.ensure_schema()

        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise

    async def ensure_schema(self):
        """Ensure database schema has all required columns"""
        async with self.pool.acquire() as conn:
            # Add missing columns if they don't exist
            await conn.execute("""
                ALTER TABLE anime_api.production_jobs
                ADD COLUMN IF NOT EXISTS total_time_seconds FLOAT,
                ADD COLUMN IF NOT EXISTS file_path TEXT,
                ADD COLUMN IF NOT EXISTS generation_params JSONB,
                ADD COLUMN IF NOT EXISTS job_id VARCHAR(50),
                ADD COLUMN IF NOT EXISTS negative_prompt TEXT,
                ADD COLUMN IF NOT EXISTS width INTEGER,
                ADD COLUMN IF NOT EXISTS height INTEGER,
                ADD COLUMN IF NOT EXISTS start_time FLOAT;
            """)

            # Create index on job_id for faster lookups
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_production_jobs_job_id
                ON anime_api.production_jobs(job_id);
            """)

            logger.info("Database schema updated successfully")

    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database pool closed")

    async def create_job(self, job_data: Dict[str, Any]) -> int:
        """Create a new job in the database"""
        async with self.pool.acquire() as conn:
            query = """
                INSERT INTO anime_api.production_jobs (
                    job_id, comfyui_job_id, job_type, prompt, negative_prompt,
                    width, height, status, start_time, generation_params,
                    created_at, parameters
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
                ) RETURNING id
            """

            # Prepare parameters
            params = {
                'width': job_data.get('width', 512),
                'height': job_data.get('height', 768),
                'negative_prompt': job_data.get('negative_prompt', '')
            }

            row = await conn.fetchrow(
                query,
                job_data['id'],  # job_id
                job_data.get('comfyui_id'),  # comfyui_job_id
                'image_generation',  # job_type
                job_data['prompt'],  # prompt
                job_data.get('negative_prompt', ''),  # negative_prompt
                job_data.get('width', 512),  # width
                job_data.get('height', 768),  # height
                job_data['status'],  # status
                job_data.get('start_time'),  # start_time
                json.dumps(params),  # generation_params (JSONB)
                datetime.utcnow(),  # created_at
                json.dumps(params)  # parameters (TEXT)
            )

            db_id = row['id']
            logger.info(f"Created job {job_data['id']} with database ID {db_id}")
            return db_id

    async def update_job_status(self, job_id: str, status: str,
                               comfyui_id: Optional[str] = None,
                               error: Optional[str] = None,
                               output_path: Optional[str] = None,
                               total_time: Optional[float] = None):
        """Update job status in the database"""
        async with self.pool.acquire() as conn:
            query = """
                UPDATE anime_api.production_jobs
                SET status = $2::varchar(50),
                    comfyui_job_id = COALESCE($3, comfyui_job_id),
                    error = $4,
                    file_path = COALESCE($5, file_path),
                    total_time_seconds = COALESCE($6, total_time_seconds),
                    updated_at = $7,
                    completed_at = CASE WHEN $2 IN ('completed', 'failed') THEN $7 ELSE completed_at END
                WHERE job_id = $1
            """

            await conn.execute(
                query,
                job_id,
                status,
                comfyui_id,
                error,
                output_path,
                total_time,
                datetime.utcnow()
            )

            logger.info(f"Updated job {job_id} status to {status}")

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details from database"""
        async with self.pool.acquire() as conn:
            query = """
                SELECT id, job_id, comfyui_job_id, job_type, prompt, negative_prompt,
                       width, height, status, file_path, error, start_time,
                       total_time_seconds, created_at, updated_at, completed_at,
                       generation_params
                FROM anime_api.production_jobs
                WHERE job_id = $1
            """

            row = await conn.fetchrow(query, job_id)

            if row:
                return {
                    'db_id': row['id'],
                    'id': row['job_id'],
                    'comfyui_id': row['comfyui_job_id'],
                    'job_type': row['job_type'],
                    'prompt': row['prompt'],
                    'negative_prompt': row['negative_prompt'],
                    'width': row['width'],
                    'height': row['height'],
                    'status': row['status'],
                    'output_path': row['file_path'],
                    'error': row['error'],
                    'start_time': row['start_time'],
                    'total_time': row['total_time_seconds'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
                    'completed_at': row['completed_at'].isoformat() if row['completed_at'] else None,
                    'generation_params': row['generation_params']
                }
            return None

    async def list_jobs(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List jobs from database"""
        async with self.pool.acquire() as conn:
            query = """
                SELECT id, job_id, comfyui_job_id, job_type, prompt, status,
                       file_path, total_time_seconds, created_at, completed_at
                FROM anime_api.production_jobs
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
            """

            rows = await conn.fetch(query, limit, offset)

            return [{
                'db_id': row['id'],
                'id': row['job_id'],
                'comfyui_id': row['comfyui_job_id'],
                'job_type': row['job_type'],
                'prompt': row['prompt'],
                'status': row['status'],
                'output_path': row['file_path'],
                'total_time': row['total_time_seconds'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'completed_at': row['completed_at'].isoformat() if row['completed_at'] else None
            } for row in rows]

    async def get_stats(self) -> Dict[str, int]:
        """Get job statistics from database"""
        async with self.pool.acquire() as conn:
            query = """
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed,
                    COUNT(*) FILTER (WHERE status = 'running') as running,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE status = 'queued') as queued
                FROM anime_api.production_jobs
            """

            row = await conn.fetchrow(query)

            return {
                'total': row['total'],
                'completed': row['completed'],
                'running': row['running'],
                'failed': row['failed'],
                'queued': row['queued']
            }

# Global database manager instance
db_manager = DatabaseManager()

async def initialize_database():
    """Initialize the database connection"""
    await db_manager.initialize()

async def close_database():
    """Close the database connection"""
    await db_manager.close()