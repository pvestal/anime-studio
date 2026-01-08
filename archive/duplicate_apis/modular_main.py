#!/usr/bin/env python3
"""
Modular anime production API.
Replaces the 4286-line main.py with clean, organized code.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import redis
import requests
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
# Import modular components
from models import AnimeProject, Base, ProductionJob
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from workflows import get_simple_image_workflow, get_video_workflow

# Configuration
DATABASE_URL = (
    "postgresql://patrick:tower_echo_brain_secret_key_2025@localhost/anime_production"
)
REDIS_URL = "redis://localhost:6379"
COMFYUI_URL = "http://localhost:8188"
OUTPUT_DIR = Path("/mnt/1TB-storage/ComfyUI/output")

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

# Redis setup
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# FastAPI app
app = FastAPI(title="Modular Anime Production API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class GenerationRequest(BaseModel):
    prompt: str
    project_name: Optional[str] = None
    negative_prompt: Optional[str] = None
    type: str = "image"  # image or video


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# API Endpoints
@app.get("/api/anime/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "modular-anime-production"}


@app.get("/api/anime/projects")
async def list_projects(db: Session = Depends(get_db)):
    """List all projects."""
    projects = db.query(AnimeProject).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "created_at": p.created_at.isoformat(),
        }
        for p in projects
    ]


@app.post("/api/anime/projects")
async def create_project(project: ProjectCreate, db: Session = Depends(get_db)):
    """Create a new project."""

    # Check if project exists
    existing = db.query(AnimeProject).filter_by(name=project.name).first()
    if existing:
        raise HTTPException(400, f"Project '{project.name}' already exists")

    # Create project
    db_project = AnimeProject(name=project.name, description=project.description)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)

    return {
        "id": db_project.id,
        "name": db_project.name,
        "message": "Project created successfully",
    }


@app.post("/api/anime/generate")
async def generate_anime(
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Generate anime image or video."""

    # Create or get project
    project = db.query(AnimeProject).filter_by(name=request.project_name).first()
    if not project and request.project_name:
        project = AnimeProject(name=request.project_name)
        db.add(project)
        db.commit()
        db.refresh(project)

    # Create job
    job = ProductionJob(
        project_id=project.id if project else None,
        job_type=request.type,
        status="pending",
        prompt=request.prompt,
        metadata_={"negative_prompt": request.negative_prompt},
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Queue job for processing
    job_data = {
        "job_id": job.id,
        "type": request.type,
        "prompt": request.prompt,
        "negative_prompt": request.negative_prompt,
    }

    redis_client.rpush("anime_job_queue", json.dumps(job_data))
    logger.info(f"Queued job {job.id} for processing")

    # Start processing in background
    background_tasks.add_task(process_job, job.id)

    return {"job_id": job.id, "status": "queued", "message": "Generation job queued"}


async def process_job(job_id: int):
    """Process a generation job."""

    db = SessionLocal()
    try:
        # Get job
        job = db.query(ProductionJob).filter_by(id=job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        # Update status
        job.status = "processing"
        db.commit()

        # Generate based on type
        if job.job_type == "image":
            workflow = get_simple_image_workflow(
                job.prompt, job.metadata_.get("negative_prompt")
            )
        else:
            workflow = get_video_workflow(job.prompt)

        # Submit to ComfyUI
        response = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})

        if response.status_code != 200:
            raise Exception(f"ComfyUI error: {response.status_code}")

        result = response.json()
        comfyui_job_id = result.get("prompt_id")

        # Update job with ComfyUI ID
        job.comfyui_job_id = comfyui_job_id
        job.status = "generating"
        db.commit()

        # Wait for completion (simplified)
        time.sleep(10)  # In production, would poll for status

        # Check for output
        history = requests.get(f"{COMFYUI_URL}/history/{comfyui_job_id}").json()

        if comfyui_job_id in history:
            outputs = history[comfyui_job_id].get("outputs", {})
            for node_output in outputs.values():
                if "images" in node_output:
                    for img in node_output["images"]:
                        job.output_path = str(OUTPUT_DIR / img["filename"])
                        break
                    if job.output_path:
                        break

        # Update job status
        if job.output_path:
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            logger.info(f"Job {job_id} completed: {job.output_path}")
        else:
            job.status = "failed"
            job.error = "No output generated"
            logger.error(f"Job {job_id} failed: no output")

        db.commit()

    except Exception as e:
        logger.error(f"Job {job_id} processing error: {e}")
        if job:
            job.status = "failed"
            job.error = str(e)
            db.commit()
    finally:
        db.close()


@app.get("/api/anime/jobs/{job_id}")
async def get_job_status(job_id: int, db: Session = Depends(get_db)):
    """Get job status."""

    job = db.query(ProductionJob).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    return {
        "id": job.id,
        "status": job.status,
        "output_path": job.output_path,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@app.get("/api/anime/jobs/{job_id}/output")
async def get_job_output(job_id: int, db: Session = Depends(get_db)):
    """Get job output file path."""

    job = db.query(ProductionJob).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    if not job.output_path:
        raise HTTPException(404, "No output available yet")

    if not Path(job.output_path).exists():
        raise HTTPException(404, "Output file not found")

    return {
        "job_id": job_id,
        "output_path": job.output_path,
        "filename": Path(job.output_path).name,
    }


if __name__ == "__main__":
    import uvicorn

    print("🚀 Starting Modular Anime Production API")
    print("📍 Port: 49797")
    print("📦 285 lines vs 4286 lines (93% reduction!)")

    uvicorn.run(app, host="0.0.0.0", port=49797)
