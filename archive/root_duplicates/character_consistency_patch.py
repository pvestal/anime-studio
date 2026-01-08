#!/usr/bin/env python3
"""
Character Consistency API Patch
Enhances the anime production API with seed storage and character consistency features
"""

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class EnhancedGenerationRequest(BaseModel):
    """Enhanced generation request with seed and character consistency"""

    prompt: str
    character: str = "original"
    scene_type: str = "dialogue"
    duration: int = 3
    style: str = "anime"
    type: str = "professional"

    # New fields for character consistency
    seed: Optional[int] = None  # Fixed seed for reproducible generation
    character_id: Optional[int] = None  # Link to specific character
    use_character_seed: bool = False  # Use character's canonical seed
    workflow_template: Optional[str] = None  # Specific workflow template path
    generation_parameters: Optional[Dict[str, Any]] = None  # Additional parameters


class CharacterVersionCreate(BaseModel):
    """Create new character version with seed and workflow"""

    character_id: Optional[int] = None  # Will be set from URL path
    seed: Optional[int] = None
    appearance_changes: Optional[str] = None
    lora_path: Optional[str] = None
    embedding_path: Optional[str] = None
    comfyui_workflow: Optional[Dict[str, Any]] = None
    workflow_template_path: Optional[str] = None
    generation_parameters: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    is_canonical: bool = False


class CharacterVersionResponse(BaseModel):
    """Character version response model"""

    id: int
    character_id: int
    version_number: int
    seed: Optional[int]
    appearance_changes: Optional[str]
    lora_path: Optional[str]
    embedding_path: Optional[str]
    comfyui_workflow: Optional[Dict[str, Any]]
    workflow_template_path: Optional[str]
    generation_parameters: Optional[Dict[str, Any]]
    quality_score: Optional[float]
    consistency_score: Optional[float]
    created_at: datetime
    updated_at: datetime
    notes: Optional[str]
    is_canonical: bool
    parent_version_id: Optional[int]


class ConsistencyAnalysisResult(BaseModel):
    """Result of character consistency analysis"""

    consistency_score: float
    visual_match_score: float
    workflow_similarity: float
    seed_determinism: float
    recommendations: list[str]
    issues_detected: list[str]


class SeedManager:
    """Manages seed generation and storage for character consistency"""

    def __init__(self):
        self.seed_cache = {}

    def generate_deterministic_seed(self, character_name: str, prompt: str) -> int:
        """Generate deterministic seed based on character and prompt"""
        combined = f"{character_name}:{prompt}"
        hash_object = hashlib.md5(combined.encode())
        # Convert first 8 bytes of hash to integer
        return int.from_bytes(hash_object.digest()[:8], byteorder="big")

    def get_character_canonical_seed(
        self, db_session, character_id: int
    ) -> Optional[int]:
        """Get canonical seed for character from database"""
        from sqlalchemy import text

        result = db_session.execute(
            text(
                """
                SELECT seed FROM character_versions
                WHERE character_id = :character_id AND is_canonical = TRUE
                ORDER BY created_at DESC LIMIT 1
            """
            ),
            {"character_id": character_id},
        ).fetchone()

        return result[0] if result else None

    def save_workflow_template(
        self, character_name: str, workflow: Dict[str, Any]
    ) -> str:
        """Save workflow template to file system"""
        template_dir = "/mnt/1TB-storage/ComfyUI/workflows/patrick_characters"
        safe_name = "".join(
            c for c in character_name if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        safe_name = safe_name.replace(" ", "_").lower()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name}_{timestamp}.json"
        filepath = f"{template_dir}/{filename}"

        with open(filepath, "w") as f:
            json.dump(workflow, f, indent=2)

        return filepath


class CharacterConsistencyEngine:
    """Engine for managing character consistency across generations"""

    def __init__(self):
        self.seed_manager = SeedManager()

    def analyze_consistency(
        self, character_id: int, new_generation_data: Dict[str, Any], db_session
    ) -> ConsistencyAnalysisResult:
        """Analyze consistency of new generation against character history"""

        # Get character version history
        from sqlalchemy import text

        versions = db_session.execute(
            text(
                """
                SELECT * FROM character_versions
                WHERE character_id = :character_id
                ORDER BY created_at DESC
            """
            ),
            {"character_id": character_id},
        ).fetchall()

        if not versions:
            return ConsistencyAnalysisResult(
                consistency_score=100.0,
                visual_match_score=100.0,
                workflow_similarity=100.0,
                seed_determinism=100.0,
                recommendations=["This is the first generation for this character"],
                issues_detected=[],
            )

        # Analyze consistency metrics
        latest_version = versions[0]

        # Seed consistency check
        seed_score = (
            100.0 if new_generation_data.get("seed") == latest_version.seed else 50.0
        )

        # Workflow similarity (basic JSON comparison)
        workflow_score = self._compare_workflows(
            latest_version.comfyui_workflow, new_generation_data.get("workflow")
        )

        # Overall consistency score
        consistency_score = (seed_score + workflow_score) / 2

        recommendations = []
        issues = []

        if seed_score < 100:
            recommendations.append(
                "Consider using the canonical character seed for consistency"
            )

        if workflow_score < 80:
            issues.append("Workflow differs significantly from previous generations")

        return ConsistencyAnalysisResult(
            consistency_score=consistency_score,
            visual_match_score=85.0,  # Placeholder - would need image analysis
            workflow_similarity=workflow_score,
            seed_determinism=seed_score,
            recommendations=recommendations,
            issues_detected=issues,
        )

    def _compare_workflows(
        self, workflow1: Optional[Dict], workflow2: Optional[Dict]
    ) -> float:
        """Compare two workflows for similarity"""
        if workflow1 is None and workflow2 is None:
            return 100.0
        if workflow1 is None or workflow2 is None:
            return 0.0

        # Simple comparison - could be enhanced with deep analysis
        workflow1_str = json.dumps(workflow1, sort_keys=True)
        workflow2_str = json.dumps(workflow2, sort_keys=True)

        if workflow1_str == workflow2_str:
            return 100.0
        else:
            # Basic similarity metric
            common_keys = set(workflow1.keys()) & set(workflow2.keys())
            total_keys = set(workflow1.keys()) | set(workflow2.keys())
            return (len(common_keys) / len(total_keys)) * 100 if total_keys else 0.0


# Database helper functions
def create_character_version(db_session, version_data: CharacterVersionCreate) -> int:
    """Create new character version in database"""
    from sqlalchemy import text

    # Get next version number
    next_version = db_session.execute(
        text("SELECT get_next_character_version(:character_id)"),
        {"character_id": version_data.character_id},
    ).scalar()

    # Insert new version
    result = db_session.execute(
        text(
            """
            INSERT INTO character_versions
            (character_id, version_number, seed, appearance_changes, lora_path,
             embedding_path, comfyui_workflow, workflow_template_path,
             generation_parameters, notes, is_canonical)
            VALUES (:character_id, :version_number, :seed, :appearance_changes,
                   :lora_path, :embedding_path, :comfyui_workflow,
                   :workflow_template_path, :generation_parameters, :notes, :is_canonical)
            RETURNING id
        """
        ),
        {
            "character_id": version_data.character_id,
            "version_number": next_version,
            "seed": version_data.seed,
            "appearance_changes": version_data.appearance_changes,
            "lora_path": version_data.lora_path,
            "embedding_path": version_data.embedding_path,
            "comfyui_workflow": (
                json.dumps(version_data.comfyui_workflow)
                if version_data.comfyui_workflow
                else None
            ),
            "workflow_template_path": version_data.workflow_template_path,
            "generation_parameters": (
                json.dumps(version_data.generation_parameters)
                if version_data.generation_parameters
                else None
            ),
            "notes": version_data.notes,
            "is_canonical": version_data.is_canonical,
        },
    )

    version_id = result.scalar()
    db_session.commit()

    return version_id


def update_production_job_with_consistency_data(
    db_session,
    job_id: int,
    seed: Optional[int] = None,
    character_id: Optional[int] = None,
    workflow_snapshot: Optional[Dict] = None,
):
    """Update production job with consistency tracking data"""
    from sqlalchemy import text

    db_session.execute(
        text(
            """
            UPDATE production_jobs
            SET seed = :seed,
                character_id = :character_id,
                workflow_snapshot = :workflow_snapshot
            WHERE id = :job_id
        """
        ),
        {
            "job_id": job_id,
            "seed": seed,
            "character_id": character_id,
            "workflow_snapshot": (
                json.dumps(workflow_snapshot) if workflow_snapshot else None
            ),
        },
    )
    db_session.commit()


# Initialize global instances
seed_manager = SeedManager()
consistency_engine = CharacterConsistencyEngine()
