#!/usr/bin/env python3
"""
Secured Anime Production API with SQLAlchemy Database Integration
Refactored to use proper database models instead of in-memory storage.
"""

import logging
import os
import sys
from datetime import datetime
from typing import Dict, Optional

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from models import Character, ProductionJob, Project
from pydantic import BaseModel, Field, validator
from sqlalchemy import desc
from sqlalchemy.orm import Session

# Database imports
from database import DatabaseHealth, close_database, get_db, init_database

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth_middleware import optional_auth, require_auth

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI with security
app = FastAPI(
    title="Secured Anime Production API",
    description="Production-ready anime generation API with SQLAlchemy database integration",
    version="3.0.0",
    docs_url="/api/anime/docs",
    redoc_url="/api/anime/redoc",
)

# Configure CORS properly (not wide open)
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://192.168.50.135",
    "https://tower.local",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# GPU resource management (keeping existing logic)
gpu_queue = []
active_generation = None


# Pydantic models for API requests


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    type: str = Field(default="anime")
    metadata: Optional[dict] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict] = None


class CharacterCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    project_id: int
    description: Optional[str] = None
    visual_traits: Optional[dict] = Field(default_factory=dict)
    base_prompt: Optional[str] = None


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=500)
    type: str = Field(default="image", pattern="^(image|video)$")
    project_id: Optional[int] = None
    character_id: Optional[int] = None

    @validator("prompt")
    def validate_prompt(cls, v):
        """Sanitize and validate prompt"""
        # Remove any SQL-like patterns
        dangerous_patterns = ["DROP", "DELETE", "INSERT", "UPDATE", "--", ";"]
        for pattern in dangerous_patterns:
            if pattern in v.upper():
                raise ValueError("Invalid characters in prompt")
        return v.strip()


# Application startup and shutdown
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    try:
        init_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Close database connections on shutdown"""
    try:
        close_database()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# Existing GPU and ComfyUI functions (unchanged)


async def check_gpu_availability() -> bool:
    """Check if GPU is available for new generation"""
    global active_generation

    if active_generation is None:
        return True

    # Check if active job is still running in ComfyUI
    try:
        async with httpx.AsyncClient() as client:
            queue_response = await client.get("http://localhost:8188/queue")
            queue_data = queue_response.json()

            # If queue is empty, GPU is available
            if not queue_data.get("queue_running", []):
                active_generation = None
                return True

            return False
    except:
        # If can't check, assume available to avoid blocking
        active_generation = None
        return True


async def get_comfyui_job_status(prompt_id: str) -> Dict:
    """Get real-time job status from ComfyUI"""
    try:
        # Check if job is still in queue
        async with httpx.AsyncClient() as client:
            queue_response = await client.get("http://localhost:8188/queue")
            queue_data = queue_response.json()

            # Check running queue
            for item in queue_data.get("queue_running", []):
                if len(item) > 1 and item[1] == prompt_id:
                    return {
                        "status": "processing",
                        "progress": 50,
                        "estimated_remaining": 30,
                    }

            # Check pending queue
            for item in queue_data.get("queue_pending", []):
                if len(item) > 1 and item[1] == prompt_id:
                    return {
                        "status": "queued",
                        "progress": 0,
                        "estimated_remaining": 60,
                    }

            # Check history for completion
            history_response = await client.get(
                f"http://localhost:8188/history/{prompt_id}"
            )

            if history_response.status_code == 200:
                history = history_response.json()

                if prompt_id in history:
                    prompt_history = history[prompt_id]

                    if "outputs" in prompt_history:
                        # Find output files
                        for node_id, output in prompt_history["outputs"].items():
                            if "images" in output:
                                filename = output["images"][0]["filename"]
                                output_path = (
                                    f"/mnt/1TB-storage/ComfyUI/output/{filename}"
                                )

                                return {
                                    "status": "completed",
                                    "progress": 100,
                                    "output_path": output_path,
                                    "estimated_remaining": 0,
                                }
                            elif "videos" in output:
                                filename = output["videos"][0]["filename"]
                                output_path = (
                                    f"/mnt/1TB-storage/ComfyUI/output/{filename}"
                                )

                                return {
                                    "status": "completed",
                                    "progress": 100,
                                    "output_path": output_path,
                                    "estimated_remaining": 0,
                                }

            # If not found anywhere, assume failed after timeout
            return {
                "status": "failed",
                "progress": 0,
                "error": "Job not found in ComfyUI queue or history",
                "estimated_remaining": 0,
            }

    except Exception as e:
        logger.error(f"Failed to get ComfyUI status for {prompt_id}: {e}")
        return None


# Database-driven API endpoints
@app.get("/api/anime/health")
async def health(db: Session = Depends(get_db)):
    """Comprehensive health check including database status"""
    try:
        # Check ComfyUI connectivity
        async with httpx.AsyncClient(timeout=5) as client:
            comfyui_response = await client.get("http://localhost:8188/queue")
            comfyui_status = (
                "healthy" if comfyui_response.status_code == 200 else "unhealthy"
            )
            queue_data = (
                comfyui_response.json() if comfyui_response.status_code == 200 else {}
            )
    except:
        comfyui_status = "unavailable"
        queue_data = {}

    # Check GPU availability
    gpu_available = await check_gpu_availability()

    # Get database statistics
    db_info = DatabaseHealth.get_connection_info()

    # Count active jobs from database
    active_jobs_count = (
        db.query(ProductionJob).filter(ProductionJob.status == "processing").count()
    )
    total_jobs_count = db.query(ProductionJob).count()
    total_projects_count = db.query(Project).count()
    total_characters_count = db.query(Character).count()

    return {
        "status": "healthy",
        "service": "secured-anime-production-db",
        "version": "3.0.0-database-integrated",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "database": db_info,
            "comfyui": {
                "status": comfyui_status,
                "queue_running": len(queue_data.get("queue_running", [])),
                "queue_pending": len(queue_data.get("queue_pending", [])),
            },
            "gpu": {
                "available": gpu_available,
                "active_generation": active_generation is not None,
            },
            "stats": {
                "projects": total_projects_count,
                "characters": total_characters_count,
                "jobs": {"total": total_jobs_count, "active": active_jobs_count},
            },
        },
    }


# Project CRUD endpoints
@app.get("/api/anime/projects")
async def list_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user_data: dict = Depends(optional_auth),
):
    """List all projects with pagination"""
    projects = (
        db.query(Project)
        .order_by(desc(Project.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    total = db.query(Project).count()

    return {
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "type": p.type,
                "status": p.status,
                "metadata": p.metadata_,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in projects
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@app.post("/api/anime/projects")
async def create_project(
    request: ProjectCreateRequest,
    db: Session = Depends(get_db),
    user_data: dict = Depends(require_auth),
):
    """Create a new project"""

    # Check if project with same name exists
    existing = db.query(Project).filter(Project.name == request.name).first()
    if existing:
        raise HTTPException(
            status_code=400, detail="Project with this name already exists"
        )

    project = Project(
        name=request.name,
        description=request.description,
        type=request.type,
        metadata_=request.metadata,
        status="active",
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    logger.info(f"Created project {project.id}: {project.name}")

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "type": project.type,
        "status": project.status,
        "metadata": project.metadata_,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "message": "Project created successfully",
    }


@app.get("/api/anime/projects/{project_id}")
async def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user_data: dict = Depends(optional_auth),
):
    """Get project details with related characters and jobs"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get related data
    characters = db.query(Character).filter(Character.project_id == project_id).all()
    jobs = (
        db.query(ProductionJob)
        .filter(ProductionJob.project_id == project_id)
        .order_by(desc(ProductionJob.created_at))
        .limit(10)
        .all()
    )

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "type": project.type,
        "status": project.status,
        "metadata": project.metadata_,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        "characters": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "status": c.status,
            }
            for c in characters
        ],
        "recent_jobs": [
            {
                "id": j.id,
                "job_type": j.job_type,
                "status": j.status,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs
        ],
    }


# Character CRUD endpoints
@app.get("/api/anime/characters")
async def list_characters(
    project_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user_data: dict = Depends(optional_auth),
):
    """List characters, optionally filtered by project"""
    query = db.query(Character)

    if project_id:
        query = query.filter(Character.project_id == project_id)

    characters = (
        query.order_by(desc(Character.created_at)).offset(skip).limit(limit).all()
    )
    total = query.count()

    return {
        "characters": [
            {
                "id": c.id,
                "name": c.name,
                "project_id": c.project_id,
                "description": c.description,
                "visual_traits": c.visual_traits,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in characters
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@app.post("/api/anime/characters")
async def create_character(
    request: CharacterCreateRequest,
    db: Session = Depends(get_db),
    user_data: dict = Depends(require_auth),
):
    """Create a new character"""

    # Verify project exists
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=400, detail="Project not found")

    # Check if character name is unique
    existing = db.query(Character).filter(Character.name == request.name).first()
    if existing:
        raise HTTPException(
            status_code=400, detail="Character with this name already exists"
        )

    character = Character(
        name=request.name,
        project_id=request.project_id,
        description=request.description,
        visual_traits=request.visual_traits,
        base_prompt=request.base_prompt,
        status="draft",
    )

    db.add(character)
    db.commit()
    db.refresh(character)

    logger.info(
        f"Created character {character.id}: {character.name} for project {project.name}"
    )

    return {
        "id": character.id,
        "name": character.name,
        "project_id": character.project_id,
        "description": character.description,
        "visual_traits": character.visual_traits,
        "status": character.status,
        "created_at": (
            character.created_at.isoformat() if character.created_at else None
        ),
        "message": "Character created successfully",
    }


# Job status and progress endpoints
@app.get("/api/anime/jobs/{job_id}/progress")
async def get_job_progress(
    job_id: int, db: Session = Depends(get_db), user_data: dict = Depends(optional_auth)
):
    """Get real-time job progress from database and ComfyUI"""

    job = db.query(ProductionJob).filter(ProductionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # If job has a ComfyUI ID, get real-time status
    comfyui_status = None
    if job.metadata_ and job.metadata_.get("comfyui_id"):
        comfyui_id = job.metadata_["comfyui_id"]
        comfyui_status = await get_comfyui_job_status(comfyui_id)

        # Update job status in database if ComfyUI shows completion
        if comfyui_status and comfyui_status["status"] in ["completed", "failed"]:
            job.status = comfyui_status["status"]
            if comfyui_status.get("output_path"):
                job.output_path = comfyui_status["output_path"]
            if comfyui_status["status"] == "completed":
                job.completed_at = datetime.utcnow()
            db.commit()

    return {
        "job_id": job.id,
        "status": job.status,
        "job_type": job.job_type,
        "prompt": job.prompt,
        "progress": comfyui_status.get("progress", 0) if comfyui_status else 0,
        "output_path": job.output_path,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "estimated_remaining": (
            comfyui_status.get("estimated_remaining", 0) if comfyui_status else 0
        ),
        "metadata": job.metadata_,
    }


if __name__ == "__main__":
    logger.info("Starting Secured Anime Production API with Database Integration")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8331,  # Using different port to not conflict with existing API
        log_level="info",
    )
