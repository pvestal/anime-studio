#!/usr/bin/env python3
"""
Quality Gates Module for Phase 1 Character Consistency
Implements quality assessment metrics including face similarity, aesthetic scoring,
and style consistency validation with configurable thresholds.
"""

import asyncio
import logging
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import time
import json

# Image processing
from PIL import Image
import cv2

# Face recognition and embeddings
try:
    import insightface
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False
    logging.warning("InsightFace not available - face similarity will use mock data")

# ML models for aesthetic scoring
try:
    import torch
    import clip
    CLIP_AVAILABLE = True
except ImportError:
    CLIP_AVAILABLE = False
    logging.warning("CLIP not available - style consistency will use mock data")

try:
    import transformers
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

# Database operations
from character_bible_db import CharacterBibleDB

logger = logging.getLogger(__name__)

class QualityGateEngine:
    """
    Quality assessment engine for character consistency validation.
    Implements the target metrics:
    - Face cosine similarity: >0.70
    - LAION Aesthetic score: >5.5
    - Style adherence: CLIP similarity >0.85
    - Generation reproducibility: Same seed = identical output
    """

    def __init__(self, db: CharacterBibleDB = None):
        self.db = db or CharacterBibleDB()
        self.face_analyzer = None
        self.clip_model = None
        self.aesthetic_model = None
        self._initialize_models()

        # Target thresholds
        self.target_thresholds = {
            'face_similarity_min': 0.70,
            'aesthetic_score_min': 5.5,
            'style_clip_min': 0.85,
            'overall_consistency_min': 0.75
        }

    def _initialize_models(self):
        """Initialize AI models for quality assessment"""
        try:
            # Initialize InsightFace for face embeddings
            if INSIGHTFACE_AVAILABLE:
                self.face_analyzer = FaceAnalysis(providers=['CPUExecutionProvider'])
                self.face_analyzer.prepare(ctx_id=0, det_size=(640, 640))
                logger.info("✅ InsightFace initialized")

            # Initialize CLIP for style consistency
            if CLIP_AVAILABLE:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                self.clip_model, self.clip_preprocess = clip.load("ViT-B/32", device=device)
                logger.info(f"✅ CLIP initialized on {device}")

            # TODO: Initialize LAION aesthetic predictor
            # For now, we'll use a mock implementation
            logger.info("⚠️  LAION aesthetic predictor: using mock implementation")

        except Exception as e:
            logger.error(f"❌ Error initializing quality models: {e}")

    async def extract_face_embedding(self, image_path: str) -> Optional[np.ndarray]:
        """Extract face embedding using InsightFace ArcFace"""
        try:
            if not INSIGHTFACE_AVAILABLE or not self.face_analyzer:
                # Return mock embedding for testing
                return np.random.random(512).astype(np.float32)

            # Load and process image
            image = cv2.imread(str(image_path))
            if image is None:
                logger.error(f"Could not load image: {image_path}")
                return None

            # Detect faces
            faces = self.face_analyzer.get(image)
            if not faces:
                logger.warning(f"No faces detected in {image_path}")
                return None

            # Get embedding from the first (largest) face
            face = max(faces, key=lambda x: x.bbox[2] * x.bbox[3])  # Largest face by area
            embedding = face.embedding

            logger.info(f"✅ Extracted face embedding shape: {embedding.shape}")
            return embedding

        except Exception as e:
            logger.error(f"❌ Error extracting face embedding: {e}")
            return None

    async def calculate_face_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Calculate cosine similarity between face embeddings"""
        try:
            if embedding1 is None or embedding2 is None:
                return 0.0

            # Normalize embeddings
            norm1 = np.linalg.norm(embedding1)
            norm2 = np.linalg.norm(embedding2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            embedding1_norm = embedding1 / norm1
            embedding2_norm = embedding2 / norm2

            # Calculate cosine similarity
            similarity = np.dot(embedding1_norm, embedding2_norm)

            # Ensure similarity is in valid range
            similarity = max(0.0, min(1.0, float(similarity)))

            logger.debug(f"Face similarity calculated: {similarity:.4f}")
            return similarity

        except Exception as e:
            logger.error(f"❌ Error calculating face similarity: {e}")
            return 0.0

    async def calculate_aesthetic_score(self, image_path: str) -> float:
        """Calculate LAION aesthetic predictor score"""
        try:
            # TODO: Implement actual LAION aesthetic predictor
            # For Phase 1, using mock implementation based on image properties

            image = Image.open(image_path)
            width, height = image.size

            # Mock scoring based on resolution and aspect ratio
            resolution_score = min(10.0, (width * height) / 100000)  # Higher res = better
            aspect_ratio = width / height
            aspect_score = 10.0 - abs(aspect_ratio - 1.0) * 2  # Closer to 1:1 = better

            # Add some randomness to simulate real aesthetic scoring
            aesthetic_score = (resolution_score + aspect_score) / 2 + np.random.uniform(-1.0, 1.0)
            aesthetic_score = max(0.0, min(10.0, aesthetic_score))

            logger.info(f"✅ Aesthetic score calculated: {aesthetic_score:.2f}")
            return aesthetic_score

        except Exception as e:
            logger.error(f"❌ Error calculating aesthetic score: {e}")
            return 0.0

    async def calculate_clip_similarity(self, image_path: str, text_prompt: str) -> float:
        """Calculate CLIP similarity between image and style description"""
        try:
            if not CLIP_AVAILABLE or not self.clip_model:
                # Return mock similarity for testing
                return np.random.uniform(0.7, 0.95)

            # Load and preprocess image
            image = Image.open(image_path)
            image_input = self.clip_preprocess(image).unsqueeze(0)

            # Tokenize text
            text_input = clip.tokenize([text_prompt])

            # Calculate features
            with torch.no_grad():
                image_features = self.clip_model.encode_image(image_input)
                text_features = self.clip_model.encode_text(text_input)

                # Normalize features
                image_features /= image_features.norm(dim=-1, keepdim=True)
                text_features /= text_features.norm(dim=-1, keepdim=True)

                # Calculate similarity
                similarity = torch.cosine_similarity(image_features, text_features).item()

            logger.info(f"✅ CLIP similarity calculated: {similarity:.4f}")
            return max(0.0, min(1.0, similarity))

        except Exception as e:
            logger.error(f"❌ Error calculating CLIP similarity: {e}")
            return 0.0

    async def assess_generation_quality(self, image_path: str, character_id: int,
                                      style_prompt: str = None) -> Dict[str, Any]:
        """Comprehensive quality assessment for a generated image"""
        start_time = time.time()

        try:
            logger.info(f"🔍 Starting quality assessment for {image_path}")

            # 1. Extract face embedding from new generation
            new_embedding = await self.extract_face_embedding(image_path)

            # 2. Get reference embeddings for character
            reference_embeddings = await self.db.get_character_embeddings(character_id)

            # 3. Calculate face similarity scores
            face_similarities = []
            if reference_embeddings and new_embedding is not None:
                for ref_emb_data in reference_embeddings:
                    ref_embedding = ref_emb_data['embedding_vector']
                    if ref_embedding is not None:
                        similarity = await self.calculate_face_similarity(new_embedding, ref_embedding)
                        face_similarities.append(similarity)

            # Take the best similarity score
            best_face_similarity = max(face_similarities) if face_similarities else 0.0

            # 4. Calculate aesthetic score
            aesthetic_score = await self.calculate_aesthetic_score(image_path)

            # 5. Calculate style consistency (CLIP similarity)
            style_similarity = 0.0
            if style_prompt:
                style_similarity = await self.calculate_clip_similarity(image_path, style_prompt)

            # 6. Calculate overall consistency score
            overall_consistency = self._calculate_overall_score(
                best_face_similarity, aesthetic_score, style_similarity
            )

            # 7. Check quality gates
            scores = {
                'face_similarity_score': best_face_similarity,
                'aesthetic_score': aesthetic_score,
                'style_similarity_score': style_similarity,
                'overall_consistency_score': overall_consistency
            }

            quality_gates_passed, gate_failures = await self.db.check_quality_gates(scores)

            # 8. Generate improvement suggestions
            improvement_suggestions = self._generate_improvement_suggestions(scores, gate_failures)

            assessment_time = time.time() - start_time

            assessment_result = {
                'character_id': character_id,
                'image_path': image_path,
                'face_similarity_score': best_face_similarity,
                'aesthetic_score': aesthetic_score,
                'style_similarity_score': style_similarity,
                'overall_consistency_score': overall_consistency,
                'quality_gates_passed': quality_gates_passed,
                'gate_failures': gate_failures,
                'improvement_suggestions': improvement_suggestions,
                'reference_embeddings_count': len(reference_embeddings),
                'assessment_time_seconds': assessment_time,
                'target_metrics_met': {
                    'face_similarity': best_face_similarity >= self.target_thresholds['face_similarity_min'],
                    'aesthetic_score': aesthetic_score >= self.target_thresholds['aesthetic_score_min'],
                    'style_consistency': style_similarity >= self.target_thresholds['style_clip_min'],
                    'overall_consistency': overall_consistency >= self.target_thresholds['overall_consistency_min']
                }
            }

            logger.info(f"✅ Quality assessment completed in {assessment_time:.2f}s")
            logger.info(f"   Face similarity: {best_face_similarity:.3f} (target: >0.70)")
            logger.info(f"   Aesthetic score: {aesthetic_score:.2f} (target: >5.5)")
            logger.info(f"   Style consistency: {style_similarity:.3f} (target: >0.85)")
            logger.info(f"   Overall consistency: {overall_consistency:.3f} (target: >0.75)")
            logger.info(f"   Quality gates passed: {quality_gates_passed}")

            return assessment_result

        except Exception as e:
            logger.error(f"❌ Quality assessment failed: {e}")
            return {
                'error': str(e),
                'quality_gates_passed': False,
                'assessment_time_seconds': time.time() - start_time
            }

    def _calculate_overall_score(self, face_sim: float, aesthetic: float, style_sim: float) -> float:
        """Calculate weighted overall consistency score"""
        # Normalize aesthetic score to 0-1 range
        aesthetic_normalized = min(1.0, aesthetic / 10.0)

        # Weighted combination (face similarity is most important for character consistency)
        weights = {'face': 0.5, 'aesthetic': 0.2, 'style': 0.3}

        overall_score = (
            weights['face'] * face_sim +
            weights['aesthetic'] * aesthetic_normalized +
            weights['style'] * style_sim
        )

        return max(0.0, min(1.0, overall_score))

    def _generate_improvement_suggestions(self, scores: Dict[str, float],
                                        gate_failures: List[str]) -> List[str]:
        """Generate specific improvement suggestions based on scores"""
        suggestions = []

        if scores['face_similarity_score'] < self.target_thresholds['face_similarity_min']:
            suggestions.append(
                f"Face similarity too low ({scores['face_similarity_score']:.3f}). "
                "Consider using IPAdapter FaceID with higher weight or better reference images."
            )

        if scores['aesthetic_score'] < self.target_thresholds['aesthetic_score_min']:
            suggestions.append(
                f"Aesthetic quality too low ({scores['aesthetic_score']:.2f}). "
                "Try increasing resolution, improving lighting, or adjusting composition."
            )

        if scores['style_similarity_score'] < self.target_thresholds['style_clip_min']:
            suggestions.append(
                f"Style consistency too low ({scores['style_similarity_score']:.3f}). "
                "Refine style prompts or adjust CLIP guidance strength."
            )

        # Add specific gate failure messages
        for failure in gate_failures:
            suggestions.append(f"Quality gate failure: {failure}")

        return suggestions

    async def create_character_reference_set(self, character_id: int,
                                           reference_images: List[str]) -> Dict[str, Any]:
        """Create canonical reference set for character consistency"""
        try:
            logger.info(f"🎯 Creating reference set for character {character_id}")

            embeddings_created = 0
            total_quality_score = 0.0

            for i, image_path in enumerate(reference_images):
                # Extract face embedding
                embedding = await self.extract_face_embedding(image_path)
                if embedding is None:
                    logger.warning(f"⚠️  No face found in reference image: {image_path}")
                    continue

                # Assess image quality
                aesthetic_score = await self.calculate_aesthetic_score(image_path)

                # Store embedding in database
                embedding_data = {
                    'character_id': character_id,
                    'embedding_type': 'arcface',
                    'embedding_vector': embedding,
                    'confidence_score': 0.95  # High confidence for reference images
                }

                await self.db.store_face_embedding(embedding_data)
                embeddings_created += 1
                total_quality_score += aesthetic_score

                logger.info(f"✅ Processed reference image {i+1}/{len(reference_images)}: {image_path}")

            # Calculate average quality
            avg_quality = total_quality_score / max(1, embeddings_created)

            # Generate canonical hash
            import hashlib
            hash_data = json.dumps({
                'character_id': character_id,
                'reference_count': embeddings_created,
                'avg_quality': avg_quality,
                'timestamp': time.time()
            }, sort_keys=True)
            canonical_hash = hashlib.sha256(hash_data.encode()).hexdigest()

            # Update character with canonical hash
            await self.db.update_character_canonical_hash(character_id, canonical_hash)

            result = {
                'character_id': character_id,
                'embeddings_created': embeddings_created,
                'total_references': len(reference_images),
                'average_quality_score': avg_quality,
                'canonical_hash': canonical_hash,
                'status': 'completed'
            }

            logger.info(f"✅ Reference set created: {embeddings_created}/{len(reference_images)} successful")
            return result

        except Exception as e:
            logger.error(f"❌ Failed to create reference set: {e}")
            return {'status': 'error', 'error': str(e)}

    async def batch_quality_assessment(self, image_paths: List[str],
                                     character_id: int, style_prompt: str = None) -> List[Dict[str, Any]]:
        """Perform quality assessment on multiple images"""
        results = []

        logger.info(f"🔍 Starting batch quality assessment for {len(image_paths)} images")

        for i, image_path in enumerate(image_paths):
            logger.info(f"Processing image {i+1}/{len(image_paths)}: {image_path}")
            result = await self.assess_generation_quality(image_path, character_id, style_prompt)
            result['batch_index'] = i
            results.append(result)

        # Calculate batch statistics
        valid_results = [r for r in results if 'error' not in r]
        if valid_results:
            avg_face_sim = np.mean([r['face_similarity_score'] for r in valid_results])
            avg_aesthetic = np.mean([r['aesthetic_score'] for r in valid_results])
            avg_style_sim = np.mean([r['style_similarity_score'] for r in valid_results])
            pass_rate = np.mean([r['quality_gates_passed'] for r in valid_results])

            logger.info(f"✅ Batch assessment complete:")
            logger.info(f"   Average face similarity: {avg_face_sim:.3f}")
            logger.info(f"   Average aesthetic score: {avg_aesthetic:.2f}")
            logger.info(f"   Average style consistency: {avg_style_sim:.3f}")
            logger.info(f"   Quality gate pass rate: {pass_rate:.2%}")

        return results

# Testing and validation functions
async def test_quality_gates():
    """Test quality gates with mock data"""
    try:
        quality_engine = QualityGateEngine()

        # Test with mock image (you would replace with real image path)
        test_image = "/tmp/test_character.png"

        # Create a simple test image if it doesn't exist
        if not Path(test_image).exists():
            # Create a simple colored image for testing
            import numpy as np
            from PIL import Image
            test_img = Image.fromarray(np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8))
            test_img.save(test_image)

        # Run quality assessment
        assessment = await quality_engine.assess_generation_quality(
            image_path=test_image,
            character_id=1,
            style_prompt="anime character, high quality, detailed"
        )

        print("✅ Quality Assessment Test Results:")
        print(json.dumps(assessment, indent=2, default=str))

        return assessment['quality_gates_passed'] if 'quality_gates_passed' in assessment else False

    except Exception as e:
        logger.error(f"❌ Quality gates test failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_quality_gates())