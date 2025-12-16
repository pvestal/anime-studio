#!/usr/bin/env python3
"""
CLIP-based Character Consistency System
Production-grade anime character similarity using OpenAI CLIP embeddings
"""

import os
import sqlite3
import asyncio
import hashlib
import pickle
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from PIL import Image
import numpy as np
import torch
import clip
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class CLIPCharacterConsistency:
    """Advanced character consistency using CLIP embeddings"""

    def __init__(self,
                 db_path: str = "/opt/tower-anime-production/database/anime_production.db",
                 clip_model: str = "ViT-B/32",
                 device: str = None):
        """
        Initialize CLIP-based character consistency system

        Args:
            db_path: Path to SQLite database
            clip_model: CLIP model to use ('ViT-B/32', 'ViT-B/16', 'ViT-L/14')
            device: Device to use ('cuda', 'cpu', or None for auto)
        """
        self.db_path = db_path
        self.clip_model_name = clip_model

        # Set device
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        logger.info(f"Using device: {self.device}")

        # Load CLIP model
        self._load_clip_model()

        # Initialize database
        self._init_database()

    def _load_clip_model(self):
        """Load CLIP model and preprocessing function"""
        try:
            self.clip_model, self.clip_preprocess = clip.load(
                self.clip_model_name,
                device=self.device
            )
            self.embedding_dim = self.clip_model.visual.output_dim
            logger.info(f"Loaded CLIP model {self.clip_model_name} with {self.embedding_dim}D embeddings")

        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")
            raise

    def _init_database(self):
        """Initialize database with asset metadata schema"""
        try:
            # Read and execute schema if database doesn't exist
            if not os.path.exists(self.db_path):
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

                schema_path = "/opt/tower-anime-production/database/asset_metadata_schema.sql"
                if os.path.exists(schema_path):
                    with open(schema_path, 'r') as f:
                        schema_sql = f.read()

                    with sqlite3.connect(self.db_path) as conn:
                        conn.executescript(schema_sql)
                    logger.info("Initialized database with asset metadata schema")

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")

    def _get_db_connection(self):
        """Get database connection with proper configuration"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def encode_image(self, image_path: str) -> np.ndarray:
        """
        Encode image to CLIP embedding

        Args:
            image_path: Path to image file

        Returns:
            CLIP embedding as numpy array
        """
        try:
            # Load and preprocess image
            image = Image.open(image_path).convert('RGB')
            image_tensor = self.clip_preprocess(image).unsqueeze(0).to(self.device)

            # Generate embedding
            with torch.no_grad():
                embedding = self.clip_model.encode_image(image_tensor)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)  # Normalize

            return embedding.cpu().numpy().flatten()

        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
            return np.zeros(self.embedding_dim)

    def cosine_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Calculate cosine similarity between two embeddings"""
        try:
            # Ensure embeddings are normalized
            embedding1 = embedding1 / np.linalg.norm(embedding1)
            embedding2 = embedding2 / np.linalg.norm(embedding2)

            similarity = np.dot(embedding1, embedding2)
            return float(similarity)

        except Exception as e:
            logger.error(f"Cosine similarity calculation failed: {e}")
            return 0.0

    def store_asset_metadata(self, image_path: str, character_name: str,
                           project_id: Optional[int] = None,
                           scene_id: Optional[int] = None,
                           generation_prompt: Optional[str] = None) -> int:
        """
        Store asset metadata in database

        Returns:
            Asset ID
        """
        try:
            # Calculate file hash
            with open(image_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()

            # Get file stats
            file_size = os.path.getsize(image_path)

            # Get image dimensions
            with Image.open(image_path) as img:
                dimensions = json.dumps({"width": img.width, "height": img.height})

            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                # Check if asset already exists
                cursor.execute("""
                    SELECT id FROM asset_metadata
                    WHERE asset_path = ? OR asset_hash = ?
                """, (image_path, file_hash))

                existing = cursor.fetchone()
                if existing:
                    logger.info(f"Asset already exists with ID {existing['id']}")
                    return existing['id']

                # Insert new asset
                cursor.execute("""
                    INSERT INTO asset_metadata (
                        asset_path, asset_hash, asset_type, file_size, dimensions,
                        project_id, scene_id, character_name, generation_prompt
                    ) VALUES (?, ?, 'image', ?, ?, ?, ?, ?, ?)
                """, (image_path, file_hash, file_size, dimensions,
                      project_id, scene_id, character_name, generation_prompt))

                asset_id = cursor.lastrowid
                logger.info(f"Stored asset metadata for {image_path} with ID {asset_id}")
                return asset_id

        except Exception as e:
            logger.error(f"Failed to store asset metadata: {e}")
            return -1

    def store_clip_embedding(self, asset_id: int, character_name: str,
                           embedding: np.ndarray, confidence: float = 1.0) -> bool:
        """Store CLIP embedding in database"""
        try:
            # Serialize embedding
            embedding_blob = pickle.dumps(embedding)

            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                # Insert or replace embedding
                cursor.execute("""
                    INSERT OR REPLACE INTO clip_embeddings (
                        asset_id, character_name, model_name, embedding_vector,
                        embedding_dimension, confidence_score
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (asset_id, character_name, self.clip_model_name,
                      embedding_blob, self.embedding_dim, confidence))

                logger.info(f"Stored CLIP embedding for asset {asset_id}, character {character_name}")
                return True

        except Exception as e:
            logger.error(f"Failed to store CLIP embedding: {e}")
            return False

    def get_character_embeddings(self, character_name: str) -> List[Tuple[int, np.ndarray, float]]:
        """
        Get all stored embeddings for a character

        Returns:
            List of (asset_id, embedding, confidence) tuples
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                # Get active references for character
                cursor.execute("""
                    SELECT ce.asset_id, ce.embedding_vector, ce.confidence_score
                    FROM clip_embeddings ce
                    JOIN character_references cr ON cr.asset_id = ce.asset_id
                    WHERE ce.character_name = ? AND cr.character_name = ?
                    AND cr.is_active = 1
                    ORDER BY cr.reference_weight DESC, cr.created_at DESC
                """, (character_name, character_name))

                embeddings = []
                for row in cursor.fetchall():
                    try:
                        embedding = pickle.loads(row['embedding_vector'])
                        embeddings.append((row['asset_id'], embedding, row['confidence_score']))
                    except Exception as e:
                        logger.warning(f"Failed to deserialize embedding for asset {row['asset_id']}: {e}")

                logger.info(f"Retrieved {len(embeddings)} embeddings for character {character_name}")
                return embeddings

        except Exception as e:
            logger.error(f"Failed to get character embeddings: {e}")
            return []

    def calculate_character_consistency(self, image_path: str, character_name: str,
                                      method: str = "best_match") -> Dict:
        """
        Calculate character consistency using CLIP embeddings

        Args:
            image_path: Path to image to analyze
            character_name: Name of character to check consistency against
            method: 'best_match', 'average', 'weighted_average'

        Returns:
            Dictionary with consistency analysis results
        """
        try:
            # Encode new image
            new_embedding = self.encode_image(image_path)
            if np.allclose(new_embedding, 0):
                return {"error": "Failed to encode image"}

            # Get reference embeddings
            reference_embeddings = self.get_character_embeddings(character_name)

            if not reference_embeddings:
                logger.info(f"No references found for character {character_name}")
                return {
                    "character_name": character_name,
                    "consistency_score": 1.0,  # First image is perfectly consistent
                    "reference_count": 0,
                    "method": method,
                    "is_first_reference": True,
                    "similarities": []
                }

            # Calculate similarities
            similarities = []
            for asset_id, ref_embedding, confidence in reference_embeddings:
                similarity = self.cosine_similarity(new_embedding, ref_embedding)
                weighted_similarity = similarity * confidence
                similarities.append({
                    "asset_id": asset_id,
                    "similarity": similarity,
                    "weighted_similarity": weighted_similarity,
                    "confidence": confidence
                })

            # Calculate final consistency score based on method
            if method == "best_match":
                consistency_score = max(sim["similarity"] for sim in similarities)

            elif method == "weighted_average":
                total_weight = sum(sim["confidence"] for sim in similarities)
                if total_weight > 0:
                    consistency_score = sum(sim["weighted_similarity"] for sim in similarities) / total_weight
                else:
                    consistency_score = 0.0

            else:  # average
                consistency_score = np.mean([sim["similarity"] for sim in similarities])

            return {
                "character_name": character_name,
                "consistency_score": float(consistency_score),
                "reference_count": len(reference_embeddings),
                "method": method,
                "is_first_reference": False,
                "similarities": similarities,
                "best_match": max(similarities, key=lambda x: x["similarity"]) if similarities else None
            }

        except Exception as e:
            logger.error(f"Character consistency calculation failed: {e}")
            return {"error": str(e)}

    def add_character_reference(self, image_path: str, character_name: str,
                               reference_type: str = "auto",
                               weight: float = 1.0,
                               created_by: Optional[str] = None) -> bool:
        """Add image as character reference"""
        try:
            # Store asset metadata
            asset_id = self.store_asset_metadata(image_path, character_name)
            if asset_id == -1:
                return False

            # Generate and store CLIP embedding
            embedding = self.encode_image(image_path)
            if not self.store_clip_embedding(asset_id, character_name, embedding):
                return False

            # Add to character references
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT OR REPLACE INTO character_references (
                        character_name, asset_id, reference_type,
                        reference_weight, created_by
                    ) VALUES (?, ?, ?, ?, ?)
                """, (character_name, asset_id, reference_type, weight, created_by))

                logger.info(f"Added {reference_type} reference for character {character_name}")

                # Clean up old auto references if we have too many
                if reference_type == "auto":
                    self._cleanup_old_references(character_name)

                return True

        except Exception as e:
            logger.error(f"Failed to add character reference: {e}")
            return False

    def _cleanup_old_references(self, character_name: str, max_auto_refs: int = 10):
        """Remove old auto references to keep reference count manageable"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                # Count auto references
                cursor.execute("""
                    SELECT COUNT(*) as count FROM character_references
                    WHERE character_name = ? AND reference_type = 'auto' AND is_active = 1
                """, (character_name,))

                count = cursor.fetchone()['count']

                if count > max_auto_refs:
                    # Deactivate oldest auto references
                    excess = count - max_auto_refs
                    cursor.execute("""
                        UPDATE character_references
                        SET is_active = 0
                        WHERE id IN (
                            SELECT id FROM character_references
                            WHERE character_name = ? AND reference_type = 'auto' AND is_active = 1
                            ORDER BY created_at ASC
                            LIMIT ?
                        )
                    """, (character_name, excess))

                    logger.info(f"Deactivated {excess} old auto references for {character_name}")

        except Exception as e:
            logger.error(f"Failed to cleanup old references: {e}")

    def log_consistency_history(self, asset_id: int, character_name: str,
                              consistency_result: Dict) -> bool:
        """Log character consistency analysis to history table"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                best_match = consistency_result.get("best_match")

                cursor.execute("""
                    INSERT INTO character_consistency_history (
                        character_name, asset_id, clip_similarity_score,
                        reference_count, best_match_asset_id, best_match_score,
                        embedding_model, comparison_method, analysis_metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    character_name,
                    asset_id,
                    consistency_result.get("consistency_score", 0.0),
                    consistency_result.get("reference_count", 0),
                    best_match.get("asset_id") if best_match else None,
                    best_match.get("similarity") if best_match else None,
                    self.clip_model_name,
                    consistency_result.get("method", "best_match"),
                    json.dumps(consistency_result)
                ))

                return True

        except Exception as e:
            logger.error(f"Failed to log consistency history: {e}")
            return False

    def get_character_stats(self, character_name: str) -> Dict:
        """Get comprehensive statistics for a character"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                # Get reference count and types
                cursor.execute("""
                    SELECT reference_type, COUNT(*) as count, AVG(reference_weight) as avg_weight
                    FROM character_references
                    WHERE character_name = ? AND is_active = 1
                    GROUP BY reference_type
                """, (character_name,))

                reference_stats = {row['reference_type']: {
                    'count': row['count'],
                    'avg_weight': row['avg_weight']
                } for row in cursor.fetchall()}

                # Get consistency history stats
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_analyses,
                        AVG(clip_similarity_score) as avg_consistency,
                        MIN(clip_similarity_score) as min_consistency,
                        MAX(clip_similarity_score) as max_consistency,
                        AVG(reference_count) as avg_ref_count
                    FROM character_consistency_history
                    WHERE character_name = ?
                """, (character_name,))

                history_stats = cursor.fetchone()

                return {
                    "character_name": character_name,
                    "reference_stats": reference_stats,
                    "total_references": sum(stats['count'] for stats in reference_stats.values()),
                    "history": dict(history_stats) if history_stats else {},
                    "clip_model": self.clip_model_name
                }

        except Exception as e:
            logger.error(f"Failed to get character stats: {e}")
            return {"error": str(e)}


# Integration functions for anime production system
async def analyze_character_consistency_clip(
    image_path: str,
    character_name: str,
    clip_model: str = "ViT-B/32",
    consistency_threshold: float = 0.8,
    auto_add_reference: bool = True
) -> Dict:
    """
    Analyze character consistency using CLIP embeddings

    Args:
        image_path: Path to image to analyze
        character_name: Character name to check consistency against
        clip_model: CLIP model to use
        consistency_threshold: Minimum threshold for automatic reference addition
        auto_add_reference: Whether to automatically add good matches as references

    Returns:
        Comprehensive analysis results
    """
    try:
        # Initialize CLIP consistency checker
        clip_checker = CLIPCharacterConsistency(clip_model=clip_model)

        # Store asset metadata first
        asset_id = clip_checker.store_asset_metadata(image_path, character_name)

        # Calculate consistency
        consistency_result = clip_checker.calculate_character_consistency(
            image_path, character_name, method="weighted_average"
        )

        # Log to history
        if asset_id != -1:
            clip_checker.log_consistency_history(asset_id, character_name, consistency_result)

        # Auto-add as reference if it meets threshold and not first reference
        if (auto_add_reference and
            not consistency_result.get("is_first_reference", False) and
            consistency_result.get("consistency_score", 0) >= consistency_threshold):

            clip_checker.add_character_reference(
                image_path, character_name, reference_type="auto"
            )
            consistency_result["added_as_reference"] = True
        elif consistency_result.get("is_first_reference", False):
            # Always add first reference
            clip_checker.add_character_reference(
                image_path, character_name, reference_type="auto"
            )
            consistency_result["added_as_reference"] = True
        else:
            consistency_result["added_as_reference"] = False

        # Add metadata for integration
        consistency_result.update({
            "asset_id": asset_id,
            "clip_model": clip_model,
            "threshold_used": consistency_threshold,
            "analysis_timestamp": datetime.now().isoformat()
        })

        return consistency_result

    except Exception as e:
        logger.error(f"CLIP character consistency analysis failed: {e}")
        return {"error": str(e)}


# Test function for development
async def test_clip_consistency():
    """Test CLIP character consistency with existing images"""
    import glob

    # Find test images
    test_images = glob.glob("/mnt/1TB-storage/ComfyUI/output/anime_*.png")[:5]

    if not test_images:
        print("No test images found")
        return

    print(f"Testing CLIP consistency with {len(test_images)} images")

    for i, image_path in enumerate(test_images):
        print(f"\n--- Testing image {i+1}: {Path(image_path).name} ---")

        result = await analyze_character_consistency_clip(
            image_path,
            "test_character",
            consistency_threshold=0.75
        )

        print(f"Consistency Score: {result.get('consistency_score', 'N/A'):.3f}")
        print(f"Reference Count: {result.get('reference_count', 'N/A')}")
        print(f"Added as Reference: {result.get('added_as_reference', False)}")
        print(f"Method: {result.get('method', 'N/A')}")

        if result.get('best_match'):
            print(f"Best Match Score: {result['best_match']['similarity']:.3f}")


if __name__ == "__main__":
    asyncio.run(test_clip_consistency())