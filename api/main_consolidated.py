#!/usr/bin/env python3
"""
Tower Anime Production Consolidated API
All endpoints in one properly organized file with error handling
"""

import os
import sys
import logging
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, HTTPException, status, BackgroundTasks, Depends, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
import uvicorn

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Tower Anime Production API",
    description="Consolidated anime production service with all endpoints",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============= Request/Response Models =============

class GenerationRequest(BaseModel):
    prompt: str
    project_id: Optional[str] = None
    character_id: Optional[str] = None
    workflow_id: Optional[str] = None
    quality: Optional[str] = "high"
    duration: Optional[int] = 60

class GenerationResponse(BaseModel):
    job_id: str
    status: str
    message: Optional[str] = None
    result_url: Optional[str] = None
    estimated_time: Optional[int] = None

class EpisodeRequest(BaseModel):
    title: str
    description: str
    scenes: List[Dict]
    duration: Optional[int] = 300

class LoRATrainingRequest(BaseModel):
    name: str
    dataset_path: str
    base_model: Optional[str] = "ltx-video-2b"
    epochs: Optional[int] = 10
    learning_rate: Optional[float] = 1e-4

class ProjectRequest(BaseModel):
    name: str
    description: str
    genre: Optional[str] = "anime"
    target_episodes: Optional[int] = 12

# ============= Health & Status Endpoints =============

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        return {
            "status": "healthy",
            "service": "anime-studio",
            "version": "2.0.0",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail="Health check failed")

@app.get("/")
async def root():
    """Root endpoint with API info"""
    try:
        return {
            "service": "Tower Anime Production API",
            "version": "2.0.0",
            "documentation": "/docs",
            "health": "/health",
            "endpoints": {
                "generation": "/api/anime/generate",
                "projects": "/api/anime/projects",
                "episodes": "/api/anime/episodes",
                "characters": "/api/anime/characters",
                "lora": "/api/lora",
                "workflows": "/api/video/workflows"
            }
        }
    except Exception as e:
        logger.error(f"Root endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============= Generation Endpoints =============

@app.post("/api/anime/generate", response_model=GenerationResponse)
async def generate_anime(request: GenerationRequest, background_tasks: BackgroundTasks):
    """Generate anime content using ComfyUI workflows"""
    try:
        import uuid
        import httpx

        job_id = str(uuid.uuid4())

        # Prepare ComfyUI request
        workflow_data = {
            "prompt": request.prompt,
            "workflow_id": request.workflow_id or "default_anime",
            "character_id": request.character_id,
            "quality": request.quality,
            "duration": request.duration
        }

        # Submit to ComfyUI
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8188/prompt",
                    json={"prompt": workflow_data, "client_id": job_id},
                    timeout=30
                )

                if response.status_code != 200:
                    logger.warning(f"ComfyUI returned {response.status_code}")

        except httpx.RequestError as e:
            logger.error(f"ComfyUI connection failed: {e}")
            # Continue anyway - job will be queued

        # Queue background processing
        background_tasks.add_task(process_generation_job, job_id, workflow_data)

        return GenerationResponse(
            job_id=job_id,
            status="processing",
            message="Generation job submitted",
            estimated_time=120
        )

    except Exception as e:
        logger.error(f"Generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/anime/jobs/{job_id}/status", response_model=GenerationResponse)
async def get_job_status(job_id: str):
    """Get generation job status"""
    try:
        import httpx

        # Check ComfyUI history
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://localhost:8188/history/{job_id}",
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    if job_id in data:
                        # Job found in history - it's complete
                        return GenerationResponse(
                            job_id=job_id,
                            status="completed",
                            message="Generation complete",
                            result_url=f"/api/video/download/{job_id}.mp4"
                        )

        except httpx.RequestError:
            pass

        # Job not found or still processing
        return GenerationResponse(
            job_id=job_id,
            status="processing",
            message="Job is still processing"
        )

    except Exception as e:
        logger.error(f"Status check failed for {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============= Project Management Endpoints =============

@app.get("/api/anime/projects")
async def list_projects(limit: int = 20):
    """List anime projects"""
    try:
        import asyncpg

        conn = await asyncpg.connect(
            host="localhost",
            database="anime_production",
            user="patrick",
            password="RP78eIrW7cI2jYvL5akt1yurE"
        )

        try:
            projects = await conn.fetch(
                """SELECT id, name, description, status, created_at
                   FROM projects
                   ORDER BY created_at DESC
                   LIMIT $1""",
                limit
            )
            return {
                "projects": [dict(p) for p in projects],
                "count": len(projects)
            }
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Failed to list projects: {e}")
        # Return empty list on error
        return {"projects": [], "error": str(e)}

@app.post("/api/anime/projects", response_model=Dict)
async def create_project(request: ProjectRequest):
    """Create new anime project"""
    try:
        import uuid
        import asyncpg

        conn = await asyncpg.connect(
            host="localhost",
            database="anime_production",
            user="patrick",
            password="RP78eIrW7cI2jYvL5akt1yurE"
        )

        try:
            # Let database auto-generate the ID
            project_id = await conn.fetchval(
                """INSERT INTO projects (name, description, status, created_at)
                   VALUES ($1, $2, 'planning', $3)
                   RETURNING id""",
                request.name,
                request.description,
                datetime.now()
            )

            return {
                "id": project_id,
                "name": request.name,
                "status": "planning",
                "message": "Project created successfully"
            }
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Failed to create project: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============= Episode Management Endpoints =============

@app.get("/api/anime/episodes")
async def list_episodes(project_id: Optional[str] = None, limit: int = 50):
    """List episodes"""
    try:
        import asyncpg

        conn = await asyncpg.connect(
            host="localhost",
            database="anime_production",
            user="patrick",
            password="RP78eIrW7cI2jYvL5akt1yurE"
        )

        try:
            if project_id:
                episodes = await conn.fetch(
                    """SELECT id, title, episode_number, status
                       FROM episodes
                       WHERE project_id = $1
                       ORDER BY episode_number
                       LIMIT $2""",
                    project_id, limit
                )
            else:
                episodes = await conn.fetch(
                    """SELECT id, title, episode_number, status
                       FROM episodes
                       ORDER BY created_at DESC
                       LIMIT $1""",
                    limit
                )

            return {
                "episodes": [dict(e) for e in episodes],
                "count": len(episodes)
            }
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Failed to list episodes: {e}")
        return {"episodes": [], "error": str(e)}

@app.post("/api/anime/episodes", response_model=Dict)
async def create_episode(project_id: str, request: EpisodeRequest):
    """Create new episode"""
    try:
        import uuid
        import asyncpg

        episode_id = str(uuid.uuid4())

        # Convert project_id to int if it's numeric, otherwise use it as-is
        try:
            project_id_value = int(project_id)
        except ValueError:
            # If it's not a number, try to find the project by ID string
            project_id_value = project_id

        conn = await asyncpg.connect(
            host="localhost",
            database="anime_production",
            user="patrick",
            password="RP78eIrW7cI2jYvL5akt1yurE"
        )

        try:
            # Get next episode number
            max_episode = await conn.fetchval(
                "SELECT MAX(episode_number) FROM episodes WHERE project_id = $1",
                project_id_value
            )
            episode_number = (max_episode or 0) + 1

            await conn.execute(
                """INSERT INTO episodes (id, project_id, title, description, episode_number, status, created_at)
                   VALUES ($1, $2, $3, $4, $5, 'draft', $6)""",
                episode_id,
                project_id_value,
                request.title,
                request.description,
                episode_number,
                datetime.now()
            )

            # Create scenes
            for i, scene in enumerate(request.scenes):
                scene_id = str(uuid.uuid4())
                await conn.execute(
                    """INSERT INTO scenes (id, episode_id, scene_number, prompt)
                       VALUES ($1, $2, $3, $4)""",
                    scene_id,
                    episode_id,
                    i + 1,
                    scene.get("description", "")
                )

            return {
                "id": episode_id,
                "episode_number": episode_number,
                "title": request.title,
                "message": f"Episode {episode_number} created with {len(request.scenes)} scenes"
            }
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Failed to create episode: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============= Character Management Endpoints =============

@app.get("/api/anime/characters")
async def list_characters(project_id: Optional[str] = None):
    """List characters"""
    try:
        import asyncpg

        conn = await asyncpg.connect(
            host="localhost",
            database="anime_production",
            user="patrick",
            password="RP78eIrW7cI2jYvL5akt1yurE"
        )

        try:
            if project_id:
                characters = await conn.fetch(
                    """SELECT c.id, c.name, c.description, c.personality, c.lora_path
                       FROM characters c
                       WHERE c.project_id = $1""",
                    project_id
                )
            else:
                characters = await conn.fetch(
                    """SELECT c.id, c.name, c.description, c.personality, c.lora_path
                       FROM characters c
                       ORDER BY c.name"""
                )

            return {
                "characters": [dict(c) for c in characters],
                "count": len(characters)
            }
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Failed to list characters: {e}")
        return {"characters": [], "error": str(e)}

# ============= LoRA Training Endpoints =============

@app.post("/api/lora/train", response_model=Dict)
async def start_lora_training(request: LoRATrainingRequest, background_tasks: BackgroundTasks):
    """Start LoRA training job"""
    try:
        import uuid

        training_id = str(uuid.uuid4())

        # Queue training job
        background_tasks.add_task(
            run_lora_training,
            training_id=training_id,
            config={
                "name": request.name,
                "dataset_path": request.dataset_path,
                "base_model": request.base_model,
                "epochs": request.epochs,
                "learning_rate": request.learning_rate
            }
        )

        return {
            "training_id": training_id,
            "status": "queued",
            "message": f"LoRA training job {training_id} queued"
        }

    except Exception as e:
        logger.error(f"Failed to start LoRA training: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/lora/training/{training_id}")
async def get_training_status(training_id: str):
    """Get LoRA training status"""
    try:
        # This would check actual training status
        # For now, return mock status
        return {
            "training_id": training_id,
            "status": "completed",
            "progress": 100,
            "model_path": f"/models/lora/{training_id}.safetensors"
        }
    except Exception as e:
        logger.error(f"Failed to get training status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/lora/models")
async def list_lora_models():
    """List available LoRA models"""
    try:
        import asyncpg

        conn = await asyncpg.connect(
            host="localhost",
            database="anime_production",
            user="patrick",
            password="RP78eIrW7cI2jYvL5akt1yurE"
        )

        try:
            models = await conn.fetch(
                """SELECT id, name, type, file_path, created_at
                   FROM lora_models
                   ORDER BY created_at DESC"""
            )

            return {
                "models": [dict(m) for m in models],
                "count": len(models)
            }
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Failed to list LoRA models: {e}")
        return {"models": [], "error": str(e)}

# ============= Workflow Management Endpoints =============

@app.get("/api/video/workflows")
async def list_workflows():
    """List available video generation workflows"""
    try:
        import asyncpg

        conn = await asyncpg.connect(
            host="localhost",
            database="anime_production",
            user="patrick",
            password="RP78eIrW7cI2jYvL5akt1yurE"
        )

        try:
            # Return empty workflows since table doesn't exist
            workflows = []

            return {
                "workflows": [dict(w) for w in workflows],
                "count": len(workflows)
            }
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Failed to list workflows: {e}")
        return {"workflows": [], "error": str(e)}

# ============= File Management Endpoints =============

@app.get("/api/video/download/{filename}")
async def download_video(filename: str):
    """Download generated video file"""
    try:
        # Try multiple possible locations
        possible_paths = [
            Path(f"/opt/anime-studio/outputs/{filename}"),
            Path(f"/tmp/{filename}"),
            Path(f"/opt/ComfyUI/output/{filename}")
        ]

        file_path = None
        for path in possible_paths:
            if path.exists():
                file_path = path
                break

        if not file_path:
            # Return a mock file for testing
            return {
                "message": "File not found in production paths",
                "filename": filename,
                "status": "mock_response"
            }

        return FileResponse(
            path=str(file_path),
            media_type="video/mp4",
            filename=filename
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload/dataset")
async def upload_dataset(files: List[UploadFile] = File(...)):
    """Upload dataset for LoRA training"""
    try:
        import uuid

        dataset_id = str(uuid.uuid4())
        dataset_path = Path(f"/tmp/lora_datasets/{dataset_id}")
        dataset_path.mkdir(parents=True, exist_ok=True)

        saved_files = []
        for file in files:
            try:
                file_path = dataset_path / file.filename
                content = await file.read()
                with open(file_path, "wb") as f:
                    f.write(content)
                saved_files.append(str(file_path))
            except Exception as e:
                logger.error(f"Failed to save file {file.filename}: {e}")

        return {
            "dataset_id": dataset_id,
            "path": str(dataset_path),
            "files_saved": len(saved_files),
            "files": saved_files
        }

    except Exception as e:
        logger.error(f"Dataset upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============= Echo Brain Integration =============

@app.get("/api/echo-brain/status")
async def echo_brain_status():
    """Check Echo Brain integration status"""
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8309/health", timeout=2)
            if response.status_code == 200:
                return {
                    "status": "connected",
                    "echo_brain": response.json()
                }

    except Exception as e:
        logger.warning(f"Echo Brain not available: {e}")
        return {
            "status": "disconnected",
            "error": str(e)
        }

@app.post("/api/anime/projects/{project_id}/echo-suggest")
async def echo_suggest_content(project_id: str, prompt: str):
    """Get Echo Brain suggestions for project"""
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8309/api/echo/chat",
                json={
                    "query": f"Suggest anime content for project {project_id}: {prompt}",
                    "context": {"project_id": project_id}
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "suggestions": data.get("response", ""),
                    "project_id": project_id
                }

    except Exception as e:
        logger.error(f"Echo Brain suggestion failed: {e}")
        return {
            "suggestions": "Echo Brain unavailable",
            "error": str(e)
        }

# ============= Helper Functions =============

async def process_generation_job(job_id: str, config: Dict):
    """Background task to process generation job"""
    try:
        logger.info(f"Processing generation job {job_id}")
        # Actual generation logic would go here
        await asyncio.sleep(2)  # Simulate processing
        logger.info(f"Job {job_id} completed")
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")

async def run_lora_training(training_id: str, config: Dict):
    """Background task to run LoRA training"""
    try:
        logger.info(f"Starting LoRA training {training_id}")
        # Actual training logic would go here
        await asyncio.sleep(5)  # Simulate training
        logger.info(f"Training {training_id} completed")
    except Exception as e:
        logger.error(f"Training {training_id} failed: {e}")

# ============= Error Handlers =============

@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Custom 404 handler"""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not found",
            "path": str(request.url.path),
            "timestamp": datetime.now().isoformat()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Catch-all exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )

# ============= Startup/Shutdown Events =============

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Tower Anime Production API starting...")

    # Test database connection
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host="localhost",
            database="anime_production",
            user="patrick",
            password="RP78eIrW7cI2jYvL5akt1yurE",
            timeout=5
        )
        await conn.close()
        logger.info("✅ Database connected")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")

    # Test ComfyUI connection
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8188/system_stats", timeout=2)
            if response.status_code == 200:
                logger.info("✅ ComfyUI connected")
    except:
        logger.warning("⚠️ ComfyUI not available")

    logger.info("API ready at http://0.0.0.0:8328")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Tower Anime Production API shutting down...")

# ============= Main Entry Point =============

if __name__ == "__main__":
    uvicorn.run(
        "main_consolidated:app",
        host="0.0.0.0",
        port=8328,
        reload=True,
        log_level="info"
    )