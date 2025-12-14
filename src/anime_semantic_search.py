#!/usr/bin/env python3
"""
Anime Generation Semantic Search System
Integrates with Qdrant for intelligent generation parameter learning
"""

import json
import logging
import asyncio
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import hashlib

import psycopg2
from psycopg2.extras import RealDictCursor
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import httpx

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

class AnimeSemanticSearch:
    """Semantic search system for anime generation learning"""

    def __init__(self):
        # Qdrant client
        self.qdrant = QdrantClient(host="localhost", port=6333)
        self.collection_name = "anime_generations"
        self.vector_size = 768  # Standard embedding size

        # Ensure collection exists
        self._ensure_collection()

    def _ensure_collection(self):
        """Create Qdrant collection if it doesn't exist"""
        try:
            collections = self.qdrant.get_collections().collections
            if not any(c.name == self.collection_name for c in collections):
                self.qdrant.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection: {self.collection_name}")
            else:
                logger.info(f"Collection exists: {self.collection_name}")
        except Exception as e:
            logger.error(f"Collection setup failed: {e}")

    def _get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**DB_CONFIG)

    def _text_to_embedding(self, text: str) -> List[float]:
        """Convert text to embedding vector"""
        # Simple hash-based embedding for now (replace with CLIP/Sentence-BERT later)
        hash_obj = hashlib.sha256(text.encode())
        hash_bytes = hash_obj.digest()

        # Expand to desired vector size
        np.random.seed(int.from_bytes(hash_bytes[:4], 'big'))
        embedding = np.random.randn(self.vector_size)

        # Normalize
        embedding = embedding / np.linalg.norm(embedding)
        return embedding.tolist()

    def _params_to_vector(self, params: Dict) -> List[float]:
        """Convert generation parameters to normalized vector"""
        # Normalize common parameters
        vector = []

        # Steps (0-100 range)
        steps = params.get('steps', 20)
        vector.append(steps / 100.0)

        # CFG (0-20 range)
        cfg = params.get('cfg_scale', 7.0)
        vector.append(cfg / 20.0)

        # Sampler (categorical)
        samplers = ['euler', 'euler_a', 'dpm++_2m', 'dpm++_sde', 'heun', 'dpmpp_2m']
        sampler = params.get('sampler_name', 'euler')
        sampler_idx = samplers.index(sampler) if sampler in samplers else 0
        vector.append(sampler_idx / len(samplers))

        # Width/Height
        width = params.get('width', 1024)
        height = params.get('height', 1024)
        vector.append(width / 2048.0)
        vector.append(height / 2048.0)

        # Pad to consistent size
        while len(vector) < 10:
            vector.append(0.0)

        return vector[:10]

    def _quality_to_vector(self, scores: List[Dict]) -> List[float]:
        """Convert quality scores to vector"""
        vector = []

        # Extract known metrics
        metrics = {
            'face_similarity': 0.0,
            'aesthetic_score': 0.0,
            'consistency_score': 0.0,
            'technical_quality': 0.0
        }

        for score in scores:
            metric_name = score.get('metric_name', '')
            if metric_name in metrics:
                metrics[metric_name] = score.get('score_value', 0.0)

        # Normalize to 0-1 range
        vector = [
            metrics['face_similarity'],
            metrics['aesthetic_score'] / 10.0 if metrics['aesthetic_score'] > 0 else 0.5,
            metrics['consistency_score'],
            metrics['technical_quality'] / 10.0 if metrics['technical_quality'] > 0 else 0.5
        ]

        return vector

    async def index_generation(self, job_id: int) -> bool:
        """Index a generation in Qdrant"""
        try:
            conn = self._get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Fetch job details
                cur.execute("""
                    SELECT j.*, p.name as project_name, c.name as character_name
                    FROM jobs j
                    LEFT JOIN projects p ON j.project_id = p.id
                    LEFT JOIN characters c ON j.character_id = c.id
                    WHERE j.id = %s
                """, (job_id,))
                job = cur.fetchone()

                if not job:
                    logger.error(f"Job {job_id} not found")
                    return False

                # Fetch generation parameters
                cur.execute("""
                    SELECT * FROM generation_params WHERE job_id = %s
                """, (job_id,))
                params = cur.fetchone()

                # Fetch quality scores
                cur.execute("""
                    SELECT * FROM quality_scores WHERE job_id = %s
                """, (job_id,))
                scores = cur.fetchall()

            conn.close()

            # Generate embeddings
            text_embedding = self._text_to_embedding(job['prompt'])
            param_vector = self._params_to_vector(params if params else {})
            quality_vector = self._quality_to_vector(scores if scores else [])

            # Combine embeddings with weights
            combined = np.array(text_embedding) * 0.7  # 70% weight on prompt

            # Add parameter influence
            param_influence = np.zeros(self.vector_size)
            param_influence[:10] = param_vector
            combined += param_influence * 0.2  # 20% weight on params

            # Add quality influence
            quality_influence = np.zeros(self.vector_size)
            quality_influence[:4] = quality_vector
            combined += quality_influence * 0.1  # 10% weight on quality

            # Normalize
            combined = combined / np.linalg.norm(combined)

            # Prepare payload
            payload = {
                'job_id': job_id,
                'prompt': job['prompt'],
                'character_name': job.get('character_name', 'unknown'),
                'project_name': job.get('project_name', 'unknown'),
                'status': job['status'],
                'output_path': job.get('output_path', ''),
                'created_at': job['created_at'].isoformat() if job['created_at'] else '',
                'quality_scores': {s['metric_name']: s['score_value'] for s in (scores or [])},
                'generation_params': dict(params) if params else {}
            }

            # Store in Qdrant
            self.qdrant.upsert(
                collection_name=self.collection_name,
                points=[PointStruct(
                    id=job_id,
                    vector=combined.tolist(),
                    payload=payload
                )]
            )

            logger.info(f"Indexed job {job_id} in Qdrant")
            return True

        except Exception as e:
            logger.error(f"Failed to index job {job_id}: {e}")
            return False

    async def search_similar(self, query: str, limit: int = 5, min_quality: float = 0.0) -> List[Dict]:
        """Search for similar generations"""
        try:
            # Generate query embedding
            text_embedding = self._text_to_embedding(query)

            # Create combined vector to match indexing format
            combined = np.array(text_embedding) * 0.7

            # Add neutral parameter influence
            param_influence = np.zeros(self.vector_size)
            param_influence[:10] = [0.5] * 10  # Neutral param values
            combined += param_influence * 0.2

            # Add neutral quality influence
            quality_influence = np.zeros(self.vector_size)
            quality_influence[:4] = [0.5] * 4  # Neutral quality values
            combined += quality_influence * 0.1

            # Normalize
            combined = combined / np.linalg.norm(combined)

            # Search Qdrant
            results = self.qdrant.query_points(
                collection_name=self.collection_name,
                query=combined.tolist(),
                limit=limit * 2,  # Get extra to filter by quality
                with_payload=True
            ).points

            # Filter and enhance results
            enhanced_results = []
            for result in results:
                # Check quality threshold
                quality_scores = result.payload.get('quality_scores', {})
                avg_quality = np.mean(list(quality_scores.values())) if quality_scores else 0

                if avg_quality >= min_quality:
                    enhanced_results.append({
                        'job_id': result.payload.get('job_id'),
                        'similarity': result.score,
                        'prompt': result.payload.get('prompt'),
                        'character_name': result.payload.get('character_name'),
                        'quality_scores': quality_scores,
                        'generation_params': result.payload.get('generation_params', {}),
                        'output_path': result.payload.get('output_path'),
                        'created_at': result.payload.get('created_at')
                    })

                if len(enhanced_results) >= limit:
                    break

            return enhanced_results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    async def get_optimal_params(self, query: str, min_quality: float = 7.0) -> Dict:
        """Extract optimal parameters from similar successful generations"""
        try:
            # Find similar successful generations
            similar = await self.search_similar(query, limit=10, min_quality=min_quality)

            if not similar:
                return {'success': False, 'message': 'No similar generations found'}

            # Extract parameters
            all_params = [s['generation_params'] for s in similar if s['generation_params']]

            if not all_params:
                return {'success': False, 'message': 'No parameters found'}

            # Calculate optimal values
            optimal = {}

            # Numeric parameters - use median
            numeric_params = ['steps', 'cfg_scale', 'width', 'height']
            for param in numeric_params:
                values = [p.get(param) for p in all_params if p.get(param) is not None]
                if values:
                    optimal[param] = float(np.median(values))

            # Categorical parameters - use mode
            categorical_params = ['sampler_name', 'scheduler', 'model_name']
            for param in categorical_params:
                values = [p.get(param) for p in all_params if p.get(param)]
                if values:
                    optimal[param] = max(set(values), key=values.count)

            # Calculate confidence based on sample size and quality
            avg_quality = np.mean([
                np.mean(list(s['quality_scores'].values()))
                for s in similar if s['quality_scores']
            ])
            confidence = min(len(similar) / 10.0, 1.0) * (avg_quality / 10.0)

            return {
                'success': True,
                'optimal_params': optimal,
                'confidence': float(round(confidence, 2)),
                'sample_size': len(similar),
                'average_quality': float(round(avg_quality, 2))
            }

        except Exception as e:
            logger.error(f"Failed to get optimal params: {e}")
            return {'success': False, 'error': str(e)}

    async def batch_index_existing(self) -> Dict:
        """Index all existing completed jobs"""
        try:
            conn = self._get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM jobs
                    WHERE status = 'completed'
                    ORDER BY created_at DESC
                """)
                job_ids = [row[0] for row in cur.fetchall()]
            conn.close()

            indexed = 0
            failed = 0

            for job_id in job_ids:
                success = await self.index_generation(job_id)
                if success:
                    indexed += 1
                else:
                    failed += 1

                # Small delay to avoid overwhelming the system
                await asyncio.sleep(0.1)

            return {
                'success': True,
                'total': len(job_ids),
                'indexed': indexed,
                'failed': failed
            }

        except Exception as e:
            logger.error(f"Batch indexing failed: {e}")
            return {'success': False, 'error': str(e)}

# Singleton instance
search_engine = AnimeSemanticSearch()

async def search_similar_generations(query: str, limit: int = 5) -> List[Dict]:
    """Public API for searching similar generations"""
    return await search_engine.search_similar(query, limit)

async def get_optimal_generation_params(query: str) -> Dict:
    """Public API for getting optimal parameters"""
    return await search_engine.get_optimal_params(query)

async def index_new_generation(job_id: int) -> bool:
    """Public API for indexing a new generation"""
    return await search_engine.index_generation(job_id)

async def batch_index_all() -> Dict:
    """Public API for batch indexing"""
    return await search_engine.batch_index_existing()