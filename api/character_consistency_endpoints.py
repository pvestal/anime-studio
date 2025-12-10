#!/usr/bin/env python3
"""
Character Consistency API Endpoints
New endpoints for enhanced seed storage and character consistency management
"""

import json
# Import the main app dependencies
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.append("/opt/tower-anime-production/api")

# Import from the patch
from character_consistency_patch import (CharacterVersionCreate, CharacterVersionResponse,
                                         EnhancedGenerationRequest, consistency_engine,
                                         create_character_version, seed_manager, update_production_job_with_consistency_data)

# Create router for new endpoints
router = APIRouter(prefix="/api/anime", tags=["character-consistency"])

# Import database session dependency from main
try:
    from main import get_db
except ImportError:
    # Fallback dependency definition


    def get_db():
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        DATABASE_URL = (
            "postgresql://patrick:tower_echo_brain_secret_key_2025@localhost/anime_production"
        )
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()


@router.post("/generate/consistent", response_model=dict)


async def generate_with_consistency(
    request: EnhancedGenerationRequest, db: Session = Depends(get_db)
):
    """
    Enhanced generation endpoint with character consistency tracking
    Supports fixed seeds, character linking, and workflow snapshots
    """
    try:
        # Import or define the Production Job model
        try:
            from main import ProductionJob
        except ImportError:
            # Fallback ProductionJob definition
            from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text
            from sqlalchemy.dialects.postgresql import JSONB
            from sqlalchemy.ext.declarative import declarative_base

            Base = declarative_base()


            class ProductionJob(Base):
                __tablename__ = "production_jobs"
                __table_args__ = {"schema": "anime_api"}
                id = Column(Integer, primary_key=True, index=True)
                job_type = Column(String)
                prompt = Column(Text)
                parameters = Column(Text)
                status = Column(String, default="pending")
                seed = Column(BigInteger)
                character_id = Column(Integer)
                workflow_snapshot = Column(JSONB)
                generation_start_time = Column(DateTime)

        # Determine seed to use
        final_seed = request.seed

        if not final_seed and request.use_character_seed and request.character_id:
            # Get canonical seed from character versions
            final_seed = seed_manager.get_character_canonical_seed(db, request.character_id)

        if not final_seed:
            # Generate deterministic or timestamp-based seed
            if request.character != "original":
                final_seed = seed_manager.generate_deterministic_seed(
                    request.character, request.prompt
                )
            else:
                final_seed = int(time.time())

        # Prepare workflow parameters
        workflow_params = {
            "prompt": request.prompt,
            "character": request.character,
            "scene_type": request.scene_type,
            "duration": request.duration,
            "style": request.style,
            "seed": final_seed,
        }

        # Add generation parameters if provided
        if request.generation_parameters:
            workflow_params.update(request.generation_parameters)

        # Create production job with consistency data
        job = ProductionJob(
            job_type="consistent_generation",
            prompt=request.prompt,
            parameters=json.dumps(workflow_params),
            status="processing",
            seed=final_seed,
            character_id=request.character_id,
            generation_start_time=datetime.utcnow(),
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        # Analyze consistency if character_id provided
        consistency_analysis = None
        if request.character_id:
            consistency_analysis = consistency_engine.analyze_consistency(
                request.character_id, {"seed": final_seed, "workflow": workflow_params}, db
            )

        # Here would be the actual ComfyUI integration
        # For now, simulate the workflow snapshot
        workflow_snapshot = {
            "workflow_id": f"workflow_{job.id}",
            "parameters": workflow_params,
            "timestamp": datetime.utcnow().isoformat(),
            "comfyui_version": "1.0",
            "nodes": {
                "seed_node": {"seed": final_seed},
                "prompt_node": {"text": request.prompt},
                "character_node": {"character": request.character},
            },
        }

        # Update job with workflow snapshot
        update_production_job_with_consistency_data(
            db,
            job.id,
            seed=final_seed,
            character_id=request.character_id,
            workflow_snapshot=workflow_snapshot,
        )

        # Save workflow template if requested
        template_path = None
        if request.workflow_template and request.character != "original":
            template_path = seed_manager.save_workflow_template(
                request.character, workflow_snapshot
            )

        return {
            "job_id": job.id,
            "status": "processing",
            "seed": final_seed,
            "character_id": request.character_id,
            "workflow_template_path": template_path,
            "consistency_analysis": consistency_analysis.dict() if consistency_analysis else None,
            "estimated_completion": "2-3 minutes",
            "message": "Consistent generation started with seed tracking",
        }

    except Exception as e:
        # Create failed job record
        job = ProductionJob(
            job_type="consistent_generation",
            prompt=request.prompt,
            parameters=json.dumps(request.dict()),
            status="failed",
        )
        db.add(job)
        db.commit()

        raise HTTPException(status_code=500, detail=f"Consistent generation failed: {str(e)}")


@router.post("/characters/{character_id}/versions", response_model=CharacterVersionResponse)


async def create_character_version_endpoint(
    character_id: int, version_data: CharacterVersionCreate, db: Session = Depends(get_db)
):
    """Create a new version for an existing character"""
    try:
        # Verify character exists
        character_check = db.execute(
            text("SELECT id FROM anime_api.characters WHERE id = :id"), {"id": character_id}
        ).fetchone()

        if not character_check:
            raise HTTPException(status_code=404, detail="Character not found")

        # Ensure character_id matches
        version_data.character_id = character_id

        # Create the version
        version_id = create_character_version(db, version_data)

        # Fetch the created version
        version = db.execute(
            text(
                """
                SELECT * FROM anime_api.character_versions
                WHERE id = :version_id
            """
            ),
            {"version_id": version_id},
        ).fetchone()

        return CharacterVersionResponse(
            id=version.id,
            character_id=version.character_id,
            version_number=version.version_number,
            seed=version.seed,
            appearance_changes=version.appearance_changes,
            lora_path=version.lora_path,
            embedding_path=version.embedding_path,
            comfyui_workflow=version.comfyui_workflow,
            workflow_template_path=version.workflow_template_path,
            generation_parameters=version.generation_parameters,
            quality_score=version.quality_score,
            consistency_score=version.consistency_score,
            created_at=version.created_at,
            updated_at=version.updated_at,
            notes=version.notes,
            is_canonical=version.is_canonical,
            parent_version_id=version.parent_version_id,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create character version: {str(e)}")


@router.get("/characters/{character_id}/versions", response_model=List[CharacterVersionResponse])


async def get_character_versions(
    character_id: int, db: Session = Depends(get_db), include_non_canonical: bool = False
):
    """Get all versions for a character"""
    try:
        query = """
            SELECT * FROM anime_api.character_versions
            WHERE character_id = :character_id
        """

        if not include_non_canonical:
            query += " AND is_canonical = TRUE"

        query += " ORDER BY version_number DESC"

        versions = db.execute(text(query), {"character_id": character_id}).fetchall()

        return [
            CharacterVersionResponse(
                id=v.id,
                character_id=v.character_id,
                version_number=v.version_number,
                seed=v.seed,
                appearance_changes=v.appearance_changes,
                lora_path=v.lora_path,
                embedding_path=v.embedding_path,
                comfyui_workflow=v.comfyui_workflow,
                workflow_template_path=v.workflow_template_path,
                generation_parameters=v.generation_parameters,
                quality_score=v.quality_score,
                consistency_score=v.consistency_score,
                created_at=v.created_at,
                updated_at=v.updated_at,
                notes=v.notes,
                is_canonical=v.is_canonical,
                parent_version_id=v.parent_version_id,
            )
            for v in versions
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get character versions: {str(e)}")


@router.get("/characters/{character_id}/canonical-seed")


async def get_canonical_seed(character_id: int, db: Session = Depends(get_db)):
    """Get the canonical seed for a character"""
    try:
        canonical_seed = seed_manager.get_character_canonical_seed(db, character_id)

        if canonical_seed is None:
            # Return deterministic seed based on character name
            character = db.execute(
                text("SELECT name FROM anime_api.characters WHERE id = :id"), {"id": character_id}
            ).fetchone()

            if not character:
                raise HTTPException(status_code=404, detail="Character not found")

            canonical_seed = seed_manager.generate_deterministic_seed(character.name, "default")

        return {
            "character_id": character_id,
            "canonical_seed": canonical_seed,
            "seed_type": "canonical" if canonical_seed else "deterministic",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get canonical seed: {str(e)}")


@router.post("/characters/{character_id}/analyze-consistency")


async def analyze_character_consistency(
    character_id: int, generation_data: Dict[str, Any], db: Session = Depends(get_db)
):
    """Analyze consistency for a potential generation"""
    try:
        analysis = consistency_engine.analyze_consistency(character_id, generation_data, db)

        return {
            "character_id": character_id,
            "analysis": analysis.dict(),
            "recommendations": analysis.recommendations,
            "issues_detected": analysis.issues_detected,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze consistency: {str(e)}")


@router.get("/jobs/{job_id}/consistency-info")


async def get_job_consistency_info(job_id: int, db: Session = Depends(get_db)):
    """Get consistency information for a production job"""
    try:
        job_info = db.execute(
            text(
                """
                SELECT id, seed, character_id, workflow_snapshot, status, created_at
                FROM anime_api.production_jobs
                WHERE id = :job_id
            """
            ),
            {"job_id": job_id},
        ).fetchone()

        if not job_info:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get character info if linked
        character_info = None
        if job_info.character_id:
            character = db.execute(
                text("SELECT id, name FROM anime_api.characters WHERE id = :id"),
                {"id": job_info.character_id},
            ).fetchone()
            if character:
                character_info = {"id": character.id, "name": character.name}

        return {
            "job_id": job_info.id,
            "seed": job_info.seed,
            "character": character_info,
            "workflow_snapshot": job_info.workflow_snapshot,
            "status": job_info.status,
            "created_at": job_info.created_at.isoformat() if job_info.created_at else None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get job consistency info: {str(e)}")


@router.get("/workflow-templates")


async def list_workflow_templates():
    """List available workflow templates"""

    try:
        template_dir = "/mnt/1TB-storage/ComfyUI/workflows/patrick_characters"
        templates = []

        if os.path.exists(template_dir):
            for filename in os.listdir(template_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(template_dir, filename)
                    stat = os.stat(filepath)
                    templates.append(
                        {
                            "filename": filename,
                            "path": filepath,
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "character": filename.split("_")[0] if "_" in filename else "unknown",
                        }
                    )

        return {
            "template_directory": template_dir,
            "total_templates": len(templates),
            "templates": sorted(templates, key=lambda x: x["modified"], reverse=True),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list workflow templates: {str(e)}")
