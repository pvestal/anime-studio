"""
Mock Character Consistency Engine for Testing
Provides the expected interface for unit tests
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


class CharacterConsistencyEngine:
    """Mock implementation matching test expectations"""

    def __init__(self):
        self.reference_embeddings = {}
        self.style_templates = {}
        self.pose_library = {}
        self.consistency_threshold = 0.85
        self.character_versions = {}

    def generate_embedding(self, image_or_path):
        """Generate embedding from image"""
        # Mock implementation returns random embedding
        return self._extract_face_features(image_or_path).tolist()

    def _extract_face_features(self, image_or_path):
        """Extract face features from image"""
        # Mock returns 512-dimensional vector
        np.random.seed(hash(str(image_or_path)) % 2**32)
        return np.random.randn(512)

    def calculate_consistency_score(
        self, embedding1: List[float], embedding2: List[float]
    ) -> float:
        """Calculate cosine similarity between embeddings"""
        if embedding1 is None or embedding2 is None:
            raise ValueError("Embeddings cannot be None")

        if len(embedding1) != len(embedding2):
            raise ValueError("Embeddings must have same dimension")

        # Convert to numpy arrays
        e1 = np.array(embedding1)
        e2 = np.array(embedding2)

        # Calculate cosine similarity
        dot_product = np.dot(e1, e2)
        norm1 = np.linalg.norm(e1)
        norm2 = np.linalg.norm(e2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)

        # Normalize to 0-1 range
        return max(0.0, min(1.0, (similarity + 1) / 2))

    def extract_style_template(self, image) -> Dict[str, Any]:
        """Extract style template from image"""
        return self._analyze_art_style(image)

    def _analyze_art_style(self, image) -> Dict[str, Any]:
        """Analyze art style characteristics"""
        return {
            "line_weight": 2.0,
            "color_saturation": 0.8,
            "shading_type": "cel",
            "detail_level": "medium",
        }

    def extract_color_palette(self, image) -> Dict[str, List[int]]:
        """Extract color palette from image"""
        return self._extract_dominant_colors(image)

    def _extract_dominant_colors(self, image) -> Dict[str, List[int]]:
        """Extract dominant colors for character features"""
        return {
            "hair_color": [30, 30, 35],
            "eye_color": [100, 150, 200],
            "skin_tone": [250, 220, 190],
            "clothing_primary": [50, 50, 150],
        }

    def ensure_consistency(self, character_id: int, generation_params: Dict) -> Dict:
        """Modify generation parameters to ensure consistency"""
        modified_params = generation_params.copy()

        if character_id in self.reference_embeddings:
            modified_params["reference_embedding"] = self.reference_embeddings[
                character_id
            ]
            modified_params["consistency_weight"] = 0.8

        if character_id in self.style_templates:
            modified_params["style_preservation"] = self.style_templates[character_id]

        return modified_params

    def add_pose_to_library(self, character_id: int, pose_name: str, pose_data: Dict):
        """Add pose to character library"""
        if character_id not in self.pose_library:
            self.pose_library[character_id] = {}
        self.pose_library[character_id][pose_name] = pose_data

    def get_pose_from_library(
        self, character_id: int, pose_name: str
    ) -> Optional[Dict]:
        """Retrieve pose from library"""
        if character_id in self.pose_library:
            return self.pose_library[character_id].get(pose_name)
        return None

    def evaluate_consistency(self, score: float, threshold: float) -> bool:
        """Evaluate if score meets threshold"""
        return score >= threshold

    def batch_consistency_check(
        self, reference: List[float], candidates: List[List[float]]
    ) -> List[float]:
        """Check consistency for multiple candidates"""
        scores = []
        for candidate in candidates:
            score = self.calculate_consistency_score(reference, candidate)
            scores.append(score)
        return scores

    def add_character_version(
        self, character_id: int, version_name: str, version_data: Dict
    ):
        """Add character version for evolution tracking"""
        if character_id not in self.character_versions:
            self.character_versions[character_id] = {}
        self.character_versions[character_id][version_name] = version_data

    def get_character_versions(self, character_id: int) -> Dict:
        """Get all versions of a character"""
        return self.character_versions.get(character_id, {})

    def apply_consistency_to_workflow(self, workflow: Dict, character_id: int) -> Dict:
        """Apply consistency parameters to ComfyUI workflow"""
        modified_workflow = workflow.copy()

        # Add consistency node to workflow
        modified_workflow["consistency_node"] = {
            "type": "character_consistency",
            "character_id": character_id,
            "reference": self.reference_embeddings.get(character_id),
        }

        return modified_workflow

    def save_state(self, path: Path):
        """Save engine state to file"""
        # Convert integer keys to strings for JSON serialization
        state = {
            "reference_embeddings": {
                str(k): v for k, v in self.reference_embeddings.items()
            },
            "style_templates": {str(k): v for k, v in self.style_templates.items()},
            "pose_library": {str(k): v for k, v in self.pose_library.items()},
            "character_versions": {
                str(k): v for k, v in self.character_versions.items()
            },
        }

        with open(path, "w") as f:
            json.dump(state, f, indent=2, default=str)

    def load_state(self, path: Path):
        """Load engine state from file"""
        with open(path, "r") as f:
            state = json.load(f)

        # Convert string keys back to integers if possible

        def convert_keys(d):
            result = {}
            for k, v in d.items():
                try:
                    result[int(k)] = v
                except ValueError:
                    result[k] = v
            return result

        self.reference_embeddings = convert_keys(state.get("reference_embeddings", {}))
        self.style_templates = convert_keys(state.get("style_templates", {}))
        self.pose_library = convert_keys(state.get("pose_library", {}))
        self.character_versions = convert_keys(state.get("character_versions", {}))
