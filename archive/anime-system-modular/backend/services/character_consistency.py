"""
Tower Anime Production System - Character Consistency Service
Handles face embeddings, consistency checking, and character attribute management
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import numpy as np

logger = logging.getLogger(__name__)

# Conditional imports for optional dependencies
try:
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False
    logger.warning("InsightFace not available - face consistency checking disabled")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class CharacterConsistencyService:
    """
    Service for maintaining character visual consistency across generations.
    
    Uses ArcFace embeddings for face similarity and provides tools for
    managing character visual attributes.
    """
    
    def __init__(
        self,
        db_pool,
        model_path: str = "buffalo_l",
        similarity_threshold: float = 0.70,
        device: str = "cuda"
    ):
        self.db = db_pool
        self.similarity_threshold = similarity_threshold
        self.device = device
        self.face_analyzer: Optional[FaceAnalysis] = None
        self._model_path = model_path
        
    async def initialize(self):
        """Initialize face analysis model (call once at startup)"""
        if not INSIGHTFACE_AVAILABLE:
            logger.warning("InsightFace not installed - face features disabled")
            return
            
        try:
            self.face_analyzer = FaceAnalysis(
                name=self._model_path,
                providers=[f'{self.device.upper()}ExecutionProvider', 'CPUExecutionProvider']
            )
            self.face_analyzer.prepare(ctx_id=0 if self.device == "cuda" else -1)
            logger.info("Face analyzer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize face analyzer: {e}")
            self.face_analyzer = None
    
    # === Face Embedding Operations ===
    
    async def compute_embedding(self, image_path: str) -> Optional[np.ndarray]:
        """
        Compute face embedding from image.
        
        Returns 512-dimensional ArcFace embedding or None if no face detected.
        """
        if not self.face_analyzer or not CV2_AVAILABLE:
            return None
            
        try:
            img = cv2.imread(image_path)
            if img is None:
                logger.error(f"Could not read image: {image_path}")
                return None
                
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            faces = self.face_analyzer.get(img_rgb)
            
            if not faces:
                logger.warning(f"No face detected in: {image_path}")
                return None
                
            # Return embedding of largest face (by bbox area)
            largest_face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
            return largest_face.embedding
            
        except Exception as e:
            logger.error(f"Error computing embedding: {e}")
            return None
    
    async def store_character_embedding(
        self,
        character_id: UUID,
        image_path: str,
        force_recompute: bool = False
    ) -> Tuple[bool, Optional[float]]:
        """
        Compute and store face embedding for a character.
        
        Returns (success, similarity_baseline) where similarity_baseline
        is the self-similarity score for validation.
        """
        # Check if embedding exists
        if not force_recompute:
            existing = await self._get_stored_embedding(character_id)
            if existing is not None:
                logger.info(f"Character {character_id} already has embedding")
                return True, 1.0
        
        embedding = await self.compute_embedding(image_path)
        if embedding is None:
            return False, None
            
        # Store in database
        embedding_bytes = embedding.tobytes()
        
        async with self.db.acquire() as conn:
            await conn.execute("""
                UPDATE characters 
                SET reference_embedding = $1
                WHERE id = $2
            """, embedding_bytes, character_id)
        
        logger.info(f"Stored embedding for character {character_id}")
        return True, 1.0  # Self-similarity is always 1.0
    
    async def _get_stored_embedding(self, character_id: UUID) -> Optional[np.ndarray]:
        """Retrieve stored embedding for character"""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT reference_embedding FROM characters WHERE id = $1
            """, character_id)
            
        if row and row['reference_embedding']:
            return np.frombuffer(row['reference_embedding'], dtype=np.float32)
        return None
    
    # === Consistency Checking ===
    
    async def check_consistency(
        self,
        character_id: UUID,
        image_path: str,
        threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Check if generated image matches character reference.
        
        Returns dict with similarity_score, passes_threshold, etc.
        """
        threshold = threshold or self.similarity_threshold
        
        # Get reference embedding
        ref_embedding = await self._get_stored_embedding(character_id)
        if ref_embedding is None:
            return {
                "character_id": str(character_id),
                "similarity_score": 0.0,
                "passes_threshold": False,
                "threshold_used": threshold,
                "error": "No reference embedding stored for character"
            }
        
        # Compute embedding for test image
        test_embedding = await self.compute_embedding(image_path)
        if test_embedding is None:
            return {
                "character_id": str(character_id),
                "similarity_score": 0.0,
                "passes_threshold": False,
                "threshold_used": threshold,
                "error": "No face detected in test image"
            }
        
        # Cosine similarity
        similarity = self._cosine_similarity(ref_embedding, test_embedding)
        
        return {
            "character_id": str(character_id),
            "similarity_score": float(similarity),
            "passes_threshold": similarity >= threshold,
            "threshold_used": threshold,
            "error": None
        }
    
    async def check_multi_character_consistency(
        self,
        character_ids: List[UUID],
        image_path: str,
        threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Check consistency for multiple characters in a single image.
        
        Attempts to match detected faces to character references.
        """
        if not self.face_analyzer or not CV2_AVAILABLE:
            return {"error": "Face analysis not available", "results": []}
            
        threshold = threshold or self.similarity_threshold
        
        # Detect all faces in image
        img = cv2.imread(image_path)
        if img is None:
            return {"error": f"Could not read image: {image_path}", "results": []}
            
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        detected_faces = self.face_analyzer.get(img_rgb)
        
        if not detected_faces:
            return {"error": "No faces detected", "results": []}
        
        # Get reference embeddings
        ref_embeddings = {}
        for char_id in character_ids:
            emb = await self._get_stored_embedding(char_id)
            if emb is not None:
                ref_embeddings[char_id] = emb
        
        # Match faces to characters (greedy assignment)
        results = []
        used_faces = set()
        
        for char_id, ref_emb in ref_embeddings.items():
            best_match = None
            best_similarity = -1
            best_face_idx = -1
            
            for idx, face in enumerate(detected_faces):
                if idx in used_faces:
                    continue
                    
                sim = self._cosine_similarity(ref_emb, face.embedding)
                if sim > best_similarity:
                    best_similarity = sim
                    best_match = face
                    best_face_idx = idx
            
            if best_match is not None and best_similarity >= threshold:
                used_faces.add(best_face_idx)
                results.append({
                    "character_id": str(char_id),
                    "similarity_score": float(best_similarity),
                    "passes_threshold": True,
                    "bbox": best_match.bbox.tolist()
                })
            else:
                results.append({
                    "character_id": str(char_id),
                    "similarity_score": float(best_similarity) if best_similarity > 0 else 0.0,
                    "passes_threshold": False,
                    "bbox": None
                })
        
        all_passed = all(r["passes_threshold"] for r in results)
        avg_similarity = np.mean([r["similarity_score"] for r in results])
        
        return {
            "all_passed": all_passed,
            "average_similarity": float(avg_similarity),
            "threshold_used": threshold,
            "results": results
        }
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings"""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    
    # === Character Attribute Management ===
    
    async def add_attribute(
        self,
        character_id: UUID,
        attribute_type: str,
        attribute_value: str,
        prompt_tokens: List[str] = None,
        priority: int = 0
    ) -> UUID:
        """Add a visual attribute to a character"""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO character_attributes 
                (character_id, attribute_type, attribute_value, prompt_tokens, priority)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """, character_id, attribute_type, attribute_value, prompt_tokens or [], priority)
            return row['id']
    
    async def get_attributes(self, character_id: UUID) -> List[Dict[str, Any]]:
        """Get all attributes for a character, ordered by priority"""
        async with self.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM character_attributes 
                WHERE character_id = $1 
                ORDER BY priority DESC, attribute_type
            """, character_id)
            return [dict(r) for r in rows]
    
    async def build_character_prompt(self, character_id: UUID) -> str:
        """
        Build a prompt string from character attributes.
        
        Combines base_prompt with attribute tokens in priority order.
        """
        async with self.db.acquire() as conn:
            # Get base character data
            char = await conn.fetchrow("""
                SELECT name, base_prompt FROM characters WHERE id = $1
            """, character_id)
            
            if not char:
                return ""
            
            # Get attributes
            attrs = await conn.fetch("""
                SELECT attribute_type, attribute_value, prompt_tokens 
                FROM character_attributes 
                WHERE character_id = $1 
                ORDER BY priority DESC
            """, character_id)
        
        prompt_parts = []
        
        # Start with base prompt if exists
        if char['base_prompt']:
            prompt_parts.append(char['base_prompt'])
        else:
            prompt_parts.append(char['name'])
        
        # Add attribute tokens
        for attr in attrs:
            if attr['prompt_tokens']:
                prompt_parts.extend(attr['prompt_tokens'])
            else:
                prompt_parts.append(attr['attribute_value'])
        
        return ", ".join(prompt_parts)
    
    async def get_negative_tokens(self, character_id: UUID) -> List[str]:
        """Get negative prompt tokens for character"""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT negative_tokens FROM characters WHERE id = $1
            """, character_id)
            return row['negative_tokens'] if row else []
    
    # === Variation Management ===
    
    async def create_variation(
        self,
        character_id: UUID,
        variation_name: str,
        variation_type: str,
        prompt_modifiers: Dict[str, Any] = None,
        reference_image_path: str = None
    ) -> UUID:
        """Create a character variation (outfit, expression, etc.)"""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO character_variations 
                (character_id, variation_name, variation_type, prompt_modifiers, reference_image_path)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """, character_id, variation_name, variation_type, 
                prompt_modifiers or {}, reference_image_path)
            return row['id']
    
    async def get_variations(
        self, 
        character_id: UUID, 
        variation_type: str = None
    ) -> List[Dict[str, Any]]:
        """Get variations for a character, optionally filtered by type"""
        async with self.db.acquire() as conn:
            if variation_type:
                rows = await conn.fetch("""
                    SELECT * FROM character_variations 
                    WHERE character_id = $1 AND variation_type = $2
                    ORDER BY variation_name
                """, character_id, variation_type)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM character_variations 
                    WHERE character_id = $1
                    ORDER BY variation_type, variation_name
                """, character_id)
            return [dict(r) for r in rows]
    
    async def apply_variation(
        self,
        character_id: UUID,
        variation_id: UUID,
        base_prompt: str
    ) -> str:
        """Apply variation modifiers to a prompt"""
        async with self.db.acquire() as conn:
            var = await conn.fetchrow("""
                SELECT prompt_modifiers FROM character_variations 
                WHERE id = $1 AND character_id = $2
            """, variation_id, character_id)
            
        if not var or not var['prompt_modifiers']:
            return base_prompt
            
        modifiers = var['prompt_modifiers']
        
        # Handle different modifier types
        if 'prepend' in modifiers:
            base_prompt = f"{modifiers['prepend']}, {base_prompt}"
        if 'append' in modifiers:
            base_prompt = f"{base_prompt}, {modifiers['append']}"
        if 'replace' in modifiers:
            for old, new in modifiers['replace'].items():
                base_prompt = base_prompt.replace(old, new)
                
        return base_prompt
