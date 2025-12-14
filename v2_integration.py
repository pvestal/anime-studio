#!/usr/bin/env python3
"""
v2.0 Integration Layer for Tower Anime Production System
Bridges current anime_api.py with v2.0 database tables and services
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'anime_production',
    'user': 'patrick',
    'password': 'tower_echo_brain_secret_key_2025',
    'port': 5432
}

class V2DatabaseManager:
    """
    Database manager for v2.0 tables with integer compatibility
    """

    def __init__(self):
        self.pool = None

    def connect(self):
        """Initialize database connection pool"""
        try:
            self.pool = pool.SimpleConnectionPool(
                1, 10, **DB_CONFIG
            )
            logger.info("Database pool initialized")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def get_connection(self):
        """Get connection from pool"""
        if not self.pool:
            self.connect()
        return self.pool.getconn()

    def return_connection(self, conn):
        """Return connection to pool"""
        self.pool.putconn(conn)

    # === Project Operations ===

    def create_project(self, name: str, description: str = "", project_type: str = "anime") -> int:
        """Create new project and return ID"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO projects (name, description, type, status, created_at)
                    VALUES (%s, %s, %s, 'active', NOW())
                    RETURNING id
                """, (name, description, project_type))
                result = cur.fetchone()
                conn.commit()
                logger.info(f"Created project: {name} (ID: {result['id']})")
                return result['id']
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create project: {e}")
            raise
        finally:
            self.return_connection(conn)

    def get_projects(self) -> List[Dict]:
        """Get all projects"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM projects ORDER BY created_at DESC")
                return [dict(row) for row in cur.fetchall()]
        finally:
            self.return_connection(conn)

    # === Job Operations ===

    def create_job(
        self,
        project_id: int,
        character_id: Optional[int],
        job_type: str,
        prompt: str,
        negative_prompt: str = "",
        **metadata
    ) -> int:
        """Create new job and return ID"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO jobs (project_id, character_id, job_type, prompt, negative_prompt,
                                    status, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, 'pending', %s, NOW())
                    RETURNING id
                """, (project_id, character_id, job_type, prompt, negative_prompt, json.dumps(metadata)))
                result = cur.fetchone()
                conn.commit()
                logger.info(f"Created job: {job_type} (ID: {result['id']})")
                return result['id']
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create job: {e}")
            raise
        finally:
            self.return_connection(conn)

    def update_job_status(self, job_id: int, status: str, output_path: str = None, error_message: str = None):
        """Update job status and completion info"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                if status == 'completed':
                    cur.execute("""
                        UPDATE jobs
                        SET status = %s, output_path = %s, completed_at = NOW()
                        WHERE id = %s
                    """, (status, output_path, job_id))
                elif status == 'failed':
                    cur.execute("""
                        UPDATE jobs
                        SET status = %s, error_message = %s
                        WHERE id = %s
                    """, (status, error_message, job_id))
                else:
                    cur.execute("""
                        UPDATE jobs
                        SET status = %s
                        WHERE id = %s
                    """, (status, job_id))
                conn.commit()
                logger.info(f"Updated job {job_id} status to: {status}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update job status: {e}")
            raise
        finally:
            self.return_connection(conn)

    def get_job(self, job_id: int) -> Optional[Dict]:
        """Get job by ID"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
                result = cur.fetchone()
                return dict(result) if result else None
        finally:
            self.return_connection(conn)

    # === Generation Parameters (Reproducibility) ===

    def store_generation_params(
        self,
        job_id: int,
        positive_prompt: str,
        negative_prompt: str = "",
        generation_seed: int = -1,
        model_name: str = "",
        **params
    ):
        """Store complete generation parameters for reproducibility"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO generation_params
                    (job_id, positive_prompt, negative_prompt, seed, model_name,
                     sampler_name, scheduler, steps, cfg_scale, width, height,
                     lora_models, controlnet_configs, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    job_id, positive_prompt, negative_prompt, generation_seed, model_name,
                    params.get('sampler', 'euler'), params.get('scheduler', 'normal'),
                    params.get('steps', 20), params.get('cfg_scale', 7.0),
                    params.get('width', 512), params.get('height', 512),
                    json.dumps(params.get('lora_models', [])),
                    json.dumps(params.get('controlnet_configs', []))
                ))
                conn.commit()
                logger.info(f"Stored generation params for job {job_id}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to store generation params: {e}")
            raise
        finally:
            self.return_connection(conn)

    # === Quality Metrics ===

    def store_quality_score(
        self,
        job_id: int,
        metric_name: str,
        score_value: float,
        threshold_min: float = None,
        threshold_max: float = None,
        details: Dict = None
    ):
        """Store quality metric score"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                passed = True
                if threshold_min is not None and score_value < threshold_min:
                    passed = False
                if threshold_max is not None and score_value > threshold_max:
                    passed = False

                cur.execute("""
                    INSERT INTO quality_scores
                    (job_id, metric_name, score_value, threshold_min, threshold_max,
                     passed, details, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """, (job_id, metric_name, score_value, threshold_min, threshold_max,
                     passed, json.dumps(details or {})))
                conn.commit()
                logger.info(f"Stored quality score: {metric_name}={score_value} for job {job_id}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to store quality score: {e}")
            raise
        finally:
            self.return_connection(conn)

    def get_job_quality_scores(self, job_id: int) -> List[Dict]:
        """Get all quality scores for a job"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM quality_scores
                    WHERE job_id = %s
                    ORDER BY created_at DESC
                """, (job_id,))
                return [dict(row) for row in cur.fetchall()]
        finally:
            self.return_connection(conn)

    # === Character Management ===

    def add_character_attribute(
        self,
        character_id: int,
        attribute_type: str,
        attribute_value: str,
        prompt_tokens: List[str] = None,
        priority: int = 0
    ):
        """Add character attribute"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO character_attributes
                    (character_id, attribute_type, attribute_value, prompt_tokens, priority, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, (character_id, attribute_type, attribute_value, prompt_tokens or [], priority))
                conn.commit()
                logger.info(f"Added attribute {attribute_type}={attribute_value} for character {character_id}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to add character attribute: {e}")
            raise
        finally:
            self.return_connection(conn)

    def get_character_attributes(self, character_id: int) -> List[Dict]:
        """Get character attributes"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM character_attributes
                    WHERE character_id = %s
                    ORDER BY priority DESC, created_at
                """, (character_id,))
                return [dict(row) for row in cur.fetchall()]
        finally:
            self.return_connection(conn)


class V2IntegrationAPI:
    """
    Integration API that extends existing anime_api.py with v2.0 capabilities
    """

    def __init__(self):
        self.db = V2DatabaseManager()
        self.db.connect()

    async def create_anime_job_with_v2(
        self,
        character_name: str,
        prompt: str,
        negative_prompt: str = "",
        project_name: str = "Default Anime Project",
        **generation_params
    ) -> Dict:
        """
        Create anime generation job with full v2.0 tracking

        Returns job info with tracking ID for progress monitoring
        """
        try:
            # Get or create project
            projects = self.db.get_projects()
            project = next((p for p in projects if p['name'] == project_name), None)
            if not project:
                project_id = self.db.create_project(project_name, f"Auto-created for {character_name}")
            else:
                project_id = project['id']

            # Get character (assuming it exists in main characters table)
            # This would integrate with existing character lookup
            character_id = None  # Would lookup from existing API

            # Create job with v2.0 tracking
            job_id = self.db.create_job(
                project_id=project_id,
                character_id=character_id,
                job_type="anime_generation",
                prompt=prompt,
                negative_prompt=negative_prompt,
                generation_type="image",  # or "video"
                quality_gate="phase1"
            )

            # Store generation parameters for reproducibility
            # Extract seed first to avoid conflict
            gen_seed = generation_params.pop('seed', -1)
            gen_model = generation_params.pop('model', 'default')

            self.db.store_generation_params(
                job_id=job_id,
                positive_prompt=prompt,
                negative_prompt=negative_prompt,
                generation_seed=gen_seed,
                model_name=gen_model,
                **generation_params
            )

            return {
                "job_id": job_id,
                "project_id": project_id,
                "status": "pending",
                "tracking_enabled": True,
                "reproducible": True,
                "quality_gates": ["face_similarity", "aesthetic_score"],
                "created_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to create v2.0 job: {e}")
            raise

    async def update_job_with_quality_metrics(
        self,
        job_id: int,
        output_path: str,
        face_similarity: float = None,
        aesthetic_score: float = None
    ):
        """
        Complete job and calculate quality metrics
        """
        try:
            # Update job completion
            self.db.update_job_status(job_id, "completed", output_path)

            # Store quality metrics
            if face_similarity is not None:
                self.db.store_quality_score(
                    job_id=job_id,
                    metric_name="face_similarity",
                    score_value=face_similarity,
                    threshold_min=0.70,  # v2.0 phase gate requirement
                    details={"model": "arcface", "threshold": 0.70}
                )

            if aesthetic_score is not None:
                self.db.store_quality_score(
                    job_id=job_id,
                    metric_name="aesthetic_score",
                    score_value=aesthetic_score,
                    threshold_min=5.5,  # v2.0 phase gate requirement
                    details={"model": "aesthetic_predictor", "scale": "1-10"}
                )

            # Check phase gate compliance
            scores = self.db.get_job_quality_scores(job_id)
            passed_count = sum(1 for score in scores if score['passed'])
            total_count = len(scores)

            gate_status = {
                "phase": "phase1",
                "passed_metrics": passed_count,
                "total_metrics": total_count,
                "pass_rate": passed_count / total_count if total_count > 0 else 0,
                "gate_passed": (passed_count / total_count) >= 0.8 if total_count > 0 else False
            }

            logger.info(f"Job {job_id} quality gate: {gate_status}")
            return gate_status

        except Exception as e:
            logger.error(f"Failed to update job with quality metrics: {e}")
            raise

    async def reproduce_generation(self, job_id: int) -> Dict:
        """
        Reproduce exact generation using stored parameters
        """
        try:
            job = self.db.get_job(job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found")

            # Get stored parameters
            conn = self.db.get_connection()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM generation_params WHERE job_id = %s
                    """, (job_id,))
                    params = cur.fetchone()

                    if not params:
                        raise ValueError(f"No generation parameters found for job {job_id}")

                    reproduction_data = {
                        "original_job_id": job_id,
                        "prompt": params['positive_prompt'],
                        "negative_prompt": params['negative_prompt'],
                        "seed": params['seed'],
                        "model": params['model_name'],
                        "sampler": params['sampler_name'],
                        "scheduler": params['scheduler'],
                        "steps": params['steps'],
                        "cfg_scale": params['cfg_scale'],
                        "width": params['width'],
                        "height": params['height'],
                        "lora_models": params['lora_models'],
                        "controlnet_configs": params['controlnet_configs'],
                        "reproducible": True
                    }

                    logger.info(f"Retrieved reproduction parameters for job {job_id}")
                    return reproduction_data

            finally:
                self.db.return_connection(conn)

        except Exception as e:
            logger.error(f"Failed to get reproduction parameters: {e}")
            raise


# Global instance for integration
v2_integration = V2IntegrationAPI()

# Export key functions for use in anime_api.py
async def create_tracked_job(character_name: str, prompt: str, **kwargs):
    """Create job with v2.0 tracking - use this in anime_api.py"""
    return await v2_integration.create_anime_job_with_v2(character_name, prompt, **kwargs)

async def complete_job_with_quality(job_id: int, output_path: str, **quality_metrics):
    """Complete job with quality metrics - use this in anime_api.py"""
    return await v2_integration.update_job_with_quality_metrics(job_id, output_path, **quality_metrics)

async def reproduce_job(job_id: int):
    """Reproduce job exactly - new API endpoint"""
    return await v2_integration.reproduce_generation(job_id)


if __name__ == "__main__":
    # Test the integration
    async def test_integration():
        try:
            # Test project creation
            projects = v2_integration.db.get_projects()
            print(f"Found {len(projects)} projects")

            # Test job creation
            job_data = await v2_integration.create_anime_job_with_v2(
                character_name="Test Character",
                prompt="a beautiful anime girl with blue hair",
                negative_prompt="blurry, ugly",
                seed=12345,
                model="anime_model_v1"
            )
            print(f"Created job: {job_data}")

            # Test quality metrics
            gate_status = await v2_integration.update_job_with_quality_metrics(
                job_id=job_data['job_id'],
                output_path="/test/output.png",
                face_similarity=0.85,
                aesthetic_score=7.2
            )
            print(f"Quality gate status: {gate_status}")

        except Exception as e:
            print(f"Integration test failed: {e}")

    asyncio.run(test_integration())