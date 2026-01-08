#!/usr/bin/env python3
"""
Character Bible Database Operations
Handles all database operations for character consistency and management in Phase 1
"""

import asyncio
import json
import logging
import numpy as np
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import psycopg2
from psycopg2.extras import RealDictCursor, Json

# Import our database manager
import sys
sys.path.append('..')
from database_operations import EnhancedDatabaseManager, DatabaseConfig, create_database_manager

logger = logging.getLogger(__name__)

class CharacterBibleDB:
    """Database operations for character consistency and bible management"""

    def __init__(self, db_manager: EnhancedDatabaseManager = None):
        self.db_manager = db_manager or create_database_manager()
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensure character consistency schema exists"""
        schema_path = Path(__file__).parent.parent / "database" / "character_consistency_schema.sql"
        if schema_path.exists():
            logger.info(f"Character consistency schema found at {schema_path}")
        else:
            logger.warning("Character consistency schema not found")

    async def create_character(self, character_data: Dict[str, Any]) -> int:
        """Create a new character entry"""
        try:
            query = """
            INSERT INTO characters (name, project_id, description, visual_traits, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """

            params = (
                character_data['name'],
                character_data.get('project_id'),
                character_data.get('description'),
                Json(character_data.get('visual_traits', {})),
                character_data.get('status', 'draft'),
                Json(character_data.get('metadata', {}))
            )

            result = await self.db_manager.execute_query_robust(
                query, params, fetch_result=True, operation_type="create_character"
            )

            character_id = result[0]['id']
            logger.info(f"✅ Created character '{character_data['name']}' with ID {character_id}")
            return character_id

        except Exception as e:
            logger.error(f"❌ Failed to create character: {e}")
            raise

    async def get_character(self, character_id: int = None, character_name: str = None) -> Optional[Dict[str, Any]]:
        """Get character by ID or name"""
        try:
            if character_id:
                query = "SELECT * FROM characters WHERE id = %s"
                params = (character_id,)
            elif character_name:
                query = "SELECT * FROM characters WHERE name = %s"
                params = (character_name,)
            else:
                raise ValueError("Must provide either character_id or character_name")

            result = await self.db_manager.execute_query_robust(
                query, params, fetch_result=True, operation_type="get_character"
            )

            return dict(result[0]) if result else None

        except Exception as e:
            logger.error(f"❌ Failed to get character: {e}")
            return None

    async def create_character_anchor(self, anchor_data: Dict[str, Any]) -> int:
        """Create a character anchor (reference pose/expression)"""
        try:
            query = """
            INSERT INTO character_anchors
            (character_id, anchor_type, anchor_name, description, image_path,
             face_embedding, clip_embedding, generation_params, quality_score, aesthetic_score, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """

            params = (
                anchor_data['character_id'],
                anchor_data['anchor_type'],
                anchor_data['anchor_name'],
                anchor_data.get('description'),
                anchor_data['image_path'],
                anchor_data.get('face_embedding'),  # BYTEA
                anchor_data.get('clip_embedding'),  # BYTEA
                Json(anchor_data.get('generation_params', {})),
                anchor_data.get('quality_score'),
                anchor_data.get('aesthetic_score'),
                Json(anchor_data.get('metadata', {}))
            )

            result = await self.db_manager.execute_query_robust(
                query, params, fetch_result=True, operation_type="create_anchor"
            )

            anchor_id = result[0]['id']
            logger.info(f"✅ Created character anchor ID {anchor_id}")
            return anchor_id

        except Exception as e:
            logger.error(f"❌ Failed to create character anchor: {e}")
            raise

    async def store_face_embedding(self, embedding_data: Dict[str, Any]) -> int:
        """Store face embedding for character consistency"""
        try:
            query = """
            INSERT INTO face_embeddings
            (character_id, anchor_id, embedding_type, embedding_vector,
             face_bbox, face_landmarks, confidence_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """

            # Serialize numpy embedding to bytes
            embedding_vector = None
            if 'embedding_vector' in embedding_data:
                embedding_vector = pickle.dumps(embedding_data['embedding_vector'])

            params = (
                embedding_data['character_id'],
                embedding_data.get('anchor_id'),
                embedding_data['embedding_type'],
                embedding_vector,
                Json(embedding_data.get('face_bbox', {})),
                Json(embedding_data.get('face_landmarks', {})),
                embedding_data.get('confidence_score')
            )

            result = await self.db_manager.execute_query_robust(
                query, params, fetch_result=True, operation_type="store_embedding"
            )

            embedding_id = result[0]['id']
            logger.info(f"✅ Stored face embedding ID {embedding_id}")
            return embedding_id

        except Exception as e:
            logger.error(f"❌ Failed to store face embedding: {e}")
            raise

    async def get_character_embeddings(self, character_id: int, embedding_type: str = 'arcface') -> List[Dict[str, Any]]:
        """Get all face embeddings for a character"""
        try:
            query = """
            SELECT * FROM face_embeddings
            WHERE character_id = %s AND embedding_type = %s
            ORDER BY confidence_score DESC
            """

            result = await self.db_manager.execute_query_robust(
                query, (character_id, embedding_type), fetch_result=True, operation_type="get_embeddings"
            )

            embeddings = []
            for row in result or []:
                embedding_dict = dict(row)
                # Deserialize numpy embedding
                if embedding_dict['embedding_vector']:
                    embedding_dict['embedding_vector'] = pickle.loads(embedding_dict['embedding_vector'])
                embeddings.append(embedding_dict)

            return embeddings

        except Exception as e:
            logger.error(f"❌ Failed to get character embeddings: {e}")
            return []

    async def record_generation_consistency(self, consistency_data: Dict[str, Any]) -> int:
        """Record consistency scores for a generation"""
        try:
            query = """
            INSERT INTO generation_consistency
            (character_id, generation_request_id, output_image_path, face_similarity_score,
             style_similarity_score, aesthetic_score, overall_consistency_score,
             quality_gates_passed, validation_status, improvement_suggestions, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """

            params = (
                consistency_data['character_id'],
                consistency_data.get('generation_request_id'),
                consistency_data['output_image_path'],
                consistency_data.get('face_similarity_score'),
                consistency_data.get('style_similarity_score'),
                consistency_data.get('aesthetic_score'),
                consistency_data.get('overall_consistency_score'),
                consistency_data.get('quality_gates_passed', False),
                consistency_data.get('validation_status', 'pending'),
                consistency_data.get('improvement_suggestions', []),
                Json(consistency_data.get('metadata', {}))
            )

            result = await self.db_manager.execute_query_robust(
                query, params, fetch_result=True, operation_type="record_consistency"
            )

            consistency_id = result[0]['id']
            logger.info(f"✅ Recorded generation consistency ID {consistency_id}")
            return consistency_id

        except Exception as e:
            logger.error(f"❌ Failed to record generation consistency: {e}")
            raise

    async def get_quality_gates(self) -> List[Dict[str, Any]]:
        """Get active quality gate configurations"""
        try:
            query = """
            SELECT * FROM quality_gates
            WHERE is_active = TRUE
            ORDER BY gate_name
            """

            result = await self.db_manager.execute_query_robust(
                query, fetch_result=True, operation_type="get_quality_gates"
            )

            return [dict(row) for row in result or []]

        except Exception as e:
            logger.error(f"❌ Failed to get quality gates: {e}")
            return []

    async def check_quality_gates(self, scores: Dict[str, float]) -> Tuple[bool, List[str]]:
        """Check if scores pass all quality gates"""
        try:
            gates = await self.get_quality_gates()
            passed = True
            failures = []

            for gate in gates:
                gate_type = gate['gate_type']
                threshold = gate['threshold_value']

                # Map gate types to score keys
                score_key_map = {
                    'face_similarity': 'face_similarity_score',
                    'aesthetic_score': 'aesthetic_score',
                    'style_consistency': 'style_similarity_score',
                    'overall_consistency': 'overall_consistency_score'
                }

                score_key = score_key_map.get(gate_type)
                if score_key and score_key in scores:
                    if scores[score_key] < threshold:
                        passed = False
                        failures.append(f"{gate['gate_name']}: {scores[score_key]:.3f} < {threshold}")

            return passed, failures

        except Exception as e:
            logger.error(f"❌ Failed to check quality gates: {e}")
            return False, [f"Quality gate check failed: {e}"]

    async def get_character_anchors(self, character_id: int, anchor_type: str = None) -> List[Dict[str, Any]]:
        """Get character anchors by type"""
        try:
            if anchor_type:
                query = """
                SELECT * FROM character_anchors
                WHERE character_id = %s AND anchor_type = %s
                ORDER BY created_at
                """
                params = (character_id, anchor_type)
            else:
                query = """
                SELECT * FROM character_anchors
                WHERE character_id = %s
                ORDER BY anchor_type, created_at
                """
                params = (character_id,)

            result = await self.db_manager.execute_query_robust(
                query, params, fetch_result=True, operation_type="get_anchors"
            )

            return [dict(row) for row in result or []]

        except Exception as e:
            logger.error(f"❌ Failed to get character anchors: {e}")
            return []

    async def update_character_canonical_hash(self, character_id: int, canonical_hash: str) -> bool:
        """Update character canonical hash"""
        try:
            query = """
            UPDATE characters
            SET canonical_hash = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """

            result = await self.db_manager.execute_query_robust(
                query, (canonical_hash, character_id),
                fetch_result=False, operation_type="update_canonical_hash"
            )

            return result > 0

        except Exception as e:
            logger.error(f"❌ Failed to update canonical hash: {e}")
            return False

    async def get_character_consistency_stats(self, character_id: int) -> Dict[str, Any]:
        """Get consistency statistics for a character"""
        try:
            query = """
            SELECT
                COUNT(*) as total_generations,
                AVG(face_similarity_score) as avg_face_similarity,
                AVG(style_similarity_score) as avg_style_similarity,
                AVG(aesthetic_score) as avg_aesthetic_score,
                AVG(overall_consistency_score) as avg_overall_consistency,
                SUM(CASE WHEN quality_gates_passed THEN 1 ELSE 0 END) as passed_gates,
                MAX(overall_consistency_score) as best_consistency_score,
                MIN(overall_consistency_score) as worst_consistency_score
            FROM generation_consistency
            WHERE character_id = %s
            """

            result = await self.db_manager.execute_query_robust(
                query, (character_id,), fetch_result=True, operation_type="get_consistency_stats"
            )

            if result:
                stats = dict(result[0])
                # Calculate pass rate
                if stats['total_generations'] and stats['total_generations'] > 0:
                    stats['quality_gate_pass_rate'] = stats['passed_gates'] / stats['total_generations']
                else:
                    stats['quality_gate_pass_rate'] = 0.0
                return stats

            return {}

        except Exception as e:
            logger.error(f"❌ Failed to get consistency stats: {e}")
            return {}

    async def create_ipadapter_config(self, config_data: Dict[str, Any]) -> int:
        """Create IPAdapter configuration for character"""
        try:
            query = """
            INSERT INTO ipadapter_configs
            (config_name, character_id, model_path, weight, start_at, end_at,
             faceid_v2, weight_v2, combine_embeds, embeds_scaling, config_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """

            params = (
                config_data['config_name'],
                config_data.get('character_id'),
                config_data['model_path'],
                config_data.get('weight', 1.0),
                config_data.get('start_at', 0.0),
                config_data.get('end_at', 1.0),
                config_data.get('faceid_v2', False),
                config_data.get('weight_v2', 1.0),
                config_data.get('combine_embeds', 'concat'),
                config_data.get('embeds_scaling', 'V only'),
                Json(config_data.get('config_data', {}))
            )

            result = await self.db_manager.execute_query_robust(
                query, params, fetch_result=True, operation_type="create_ipadapter_config"
            )

            config_id = result[0]['id']
            logger.info(f"✅ Created IPAdapter config ID {config_id}")
            return config_id

        except Exception as e:
            logger.error(f"❌ Failed to create IPAdapter config: {e}")
            raise

    async def get_ipadapter_config(self, character_id: int = None, config_name: str = None) -> Optional[Dict[str, Any]]:
        """Get IPAdapter configuration"""
        try:
            if character_id:
                query = """
                SELECT * FROM ipadapter_configs
                WHERE character_id = %s AND is_active = TRUE
                ORDER BY created_at DESC LIMIT 1
                """
                params = (character_id,)
            elif config_name:
                query = """
                SELECT * FROM ipadapter_configs
                WHERE config_name = %s AND is_active = TRUE
                """
                params = (config_name,)
            else:
                raise ValueError("Must provide either character_id or config_name")

            result = await self.db_manager.execute_query_robust(
                query, params, fetch_result=True, operation_type="get_ipadapter_config"
            )

            return dict(result[0]) if result else None

        except Exception as e:
            logger.error(f"❌ Failed to get IPAdapter config: {e}")
            return None

# Example usage and testing
async def test_character_bible_db():
    """Test character bible database operations"""
    try:
        db = CharacterBibleDB()

        # Test character creation
        character_data = {
            'name': 'test_character_kai',
            'project_id': 1,
            'description': 'Test character for Phase 1 implementation',
            'visual_traits': {
                'hair_color': 'silver',
                'eye_color': 'blue',
                'age_range': 'young_adult',
                'style': 'anime'
            },
            'status': 'draft'
        }

        character_id = await db.create_character(character_data)
        print(f"✅ Created test character with ID: {character_id}")

        # Test retrieval
        character = await db.get_character(character_id=character_id)
        print(f"✅ Retrieved character: {character['name'] if character else 'Not found'}")

        # Test quality gates
        quality_gates = await db.get_quality_gates()
        print(f"✅ Found {len(quality_gates)} quality gates")

        # Test quality gate check
        test_scores = {
            'face_similarity_score': 0.75,
            'aesthetic_score': 6.0,
            'style_similarity_score': 0.88,
            'overall_consistency_score': 0.80
        }

        passed, failures = await db.check_quality_gates(test_scores)
        print(f"✅ Quality gate check - Passed: {passed}, Failures: {failures}")

        return True

    except Exception as e:
        print(f"❌ Character bible DB test failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_character_bible_db())