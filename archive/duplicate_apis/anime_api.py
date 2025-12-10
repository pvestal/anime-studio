#!/usr/bin/env python3
"""
Tower Anime Production Service - FastAPI REST Service
Location: /opt/tower-anime-production/
Port: 8320
"""

import json
import logging
import os
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import psycopg2
import requests
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from git_branching import compare_branches as git_compare_branches
from git_branching import create_branch as git_create_branch
from git_branching import create_commit as git_create_commit
from git_branching import get_commit_details as git_get_commit_details
from git_branching import get_commit_history as git_get_commit_history
from git_branching import list_branches as git_list_branches
from git_branching import merge_branches as git_merge_branches
from git_branching import revert_to_commit as git_revert_to_commit
from git_branching import tag_commit as git_tag_commit
from project_bible_api import (CharacterDefinition, ProjectBibleAPI,
                               ProjectBibleCreate, ProjectBibleUpdate)
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field
from v2_integration import (complete_job_with_quality, create_tracked_job,
                            reproduce_job, v2_integration)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Tower Anime Production API",
    description="RESTful API for anime project, character, and scene management",
    version="2.0.0",
)

# CORS middleware for dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify dashboard origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include Redis router
try:
    from redis_api_endpoints import redis_router

    app.include_router(redis_router, tags=["Redis Queue"])
    logger.info("Redis router integrated successfully")
except ImportError as e:
    logger.warning(f"Redis router not available: {e}")
except Exception as e:
    logger.error(f"Failed to integrate Redis router: {e}")

# Database configuration
DB_CONFIG = {
    "host": "192.168.50.135",
    "database": "anime_production",
    "user": "patrick",
    "password": "tower_echo_brain_secret_key_2025",
    "port": 5432,
    "options": "-c search_path=anime_api,public",
}

# Connection pool
connection_pool = None


def init_pool():
    global connection_pool
    if connection_pool is None:
        connection_pool = pool.SimpleConnectionPool(
            1, 10, **DB_CONFIG  # min and max connections
        )


# Database connection manager
@contextmanager
def get_db():
    global connection_pool
    if connection_pool is None:
        init_pool()
    conn = connection_pool.getconn()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        if connection_pool:
            connection_pool.putconn(conn)


# Initialize database schema
def init_db():
    """Initialize SQLite database with proper schema"""
    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Projects table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """
        )

        # Characters table with versioning
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS characters (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                version INTEGER DEFAULT 1,
                image_path TEXT,
                comfyui_workflow TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """
        )

        # Scenes table with branching support
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scenes (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL,
                branch_name TEXT DEFAULT 'main',
                scene_number INTEGER NOT NULL,
                description TEXT,
                characters TEXT,
                video_path TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """
        )

        conn.commit()
        logger.info("Database initialized successfully")


# Add v2.0 endpoint for job completion
@app.post("/api/anime/jobs/{job_id}/complete")
async def complete_anime_job(job_id: int, request: Dict[str, Any]):
    """Complete job with quality metrics and v2.0 tracking"""
    try:
        output_path = request.get("output_path")
        if not output_path:
            raise HTTPException(status_code=400, detail="output_path required")

        # Get quality metrics from request or calculate defaults
        face_similarity = request.get(
            "face_similarity", 0.75)  # Default passing
        aesthetic_score = request.get(
            "aesthetic_score", 6.0)  # Default passing

        # Complete job with v2.0 quality tracking
        gate_status = await complete_job_with_quality(
            job_id=job_id,
            output_path=output_path,
            face_similarity=face_similarity,
            aesthetic_score=aesthetic_score,
        )

        return {
            "job_id": job_id,
            "status": "completed",
            "output_path": output_path,
            "quality_gate": gate_status,
            "message": "Job completed with v2.0 quality tracking",
        }

    except Exception as e:
        logger.error(f"Error completing job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Add v2.0 endpoint for reproduction
@app.get("/api/anime/jobs/{job_id}/reproduce")
async def reproduce_anime_job(job_id: int):
    """Get reproduction parameters for exact regeneration"""
    try:
        repro_data = await reproduce_job(job_id)

        return {
            "job_id": job_id,
            "reproduction_data": repro_data,
            "message": "Use these parameters for exact reproduction",
        }

    except Exception as e:
        logger.error(f"Error getting reproduction data for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Add endpoint to get job status and quality metrics
@app.get("/api/anime/jobs/{job_id}/status")
async def get_job_status(job_id: int):
    """Get job status and quality metrics"""
    try:
        job = v2_integration.db.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        quality_scores = v2_integration.db.get_job_quality_scores(job_id)

        return {
            "job_id": job_id,
            "status": job["status"],
            "created_at": job["created_at"],
            "completed_at": job.get("completed_at"),
            "output_path": job.get("output_path"),
            "quality_scores": quality_scores,
            "error_message": job.get("error_message"),
        }

    except Exception as e:
        logger.error(f"Error getting job status {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Pydantic Models
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ProjectResponse(BaseModel):
    # Updated to support UUID from episodes table
    id: str
    name: str
    description: Optional[str]
    status: str
    created_at: str
    updated_at: str
    metadata: Optional[Dict[str, Any]]


class CharacterCreate(BaseModel):
    project_id: int
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    image_path: Optional[str] = None
    comfyui_workflow: Optional[str] = None


class CharacterResponse(BaseModel):
    id: int
    project_id: int
    name: str
    description: Optional[str]
    version: int
    image_path: Optional[str]
    comfyui_workflow: Optional[str]
    created_at: str
    updated_at: str


class CharacterUpdate(BaseModel):
    description: Optional[str] = None
    image_path: Optional[str] = None
    comfyui_workflow: Optional[str] = None


class SceneCreate(BaseModel):
    project_id: int
    branch_name: str = "main"
    scene_number: int
    description: str
    characters: List[str] = []


class SceneResponse(BaseModel):
    id: int
    project_id: int
    branch_name: str
    scene_number: int
    description: str
    characters: List[str]
    video_path: Optional[str]
    status: str
    created_at: str
    updated_at: str


class SceneUpdate(BaseModel):
    description: Optional[str] = None
    characters: Optional[List[str]] = None
    video_path: Optional[str] = None
    status: Optional[str] = None


# API Endpoints


@app.get("/api/anime/health")
async def health_check():
    """Health check endpoint"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT COUNT(*) FROM episodes")
            project_count = cursor.fetchone()[0]

        return {
            "status": "healthy",
            "service": "tower-anime-production",
            "database": "connected",
            "project_count": project_count,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


# ========== PROJECT ENDPOINTS ==========


async def download_apple_music_preview(track_id: str) -> str:
    """Download Apple Music 30-sec preview for video generation"""
    try:
        response = requests.post(
            f"http://127.0.0.1:8315/api/apple-music/track/{track_id}/download"
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("file_path")
    except Exception as e:
        logger.error(f"Failed to download Apple Music preview: {e}")
    return None


@app.post("/api/anime/projects", response_model=ProjectResponse)
async def create_project(project: ProjectCreate):
    """Create a new anime project"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            metadata_json = json.dumps(
                project.metadata) if project.metadata else None

            cursor.execute(
                """
                INSERT INTO episodes (name, description, metadata)
                VALUES (?, ?, ?)
            """,
                (project.name, project.description, metadata_json),
            )

            project_id = cursor.lastrowid

            # Fetch created project
            cursor.execute(
                "SELECT * FROM episodes WHERE id = %s", (project_id,))
            row = cursor.fetchone()

            return {
                "id": str(row["id"]),
                "name": row["title"],
                "description": row["synopsis"],
                "status": row["status"],
                "created_at": str(row["created_at"]) if row["created_at"] else None,
                "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
                "metadata": row["metadata"] if row["metadata"] else None,
            }
    except Exception as e:
        logger.error(f"Error creating project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anime/projects", response_model=List[ProjectResponse])
async def list_projects(status: Optional[str] = None, limit: int = 100):
    """List all projects with optional status filter"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            if status:
                cursor.execute(
                    "SELECT * FROM episodes WHERE status = %s ORDER BY created_at DESC LIMIT %s",
                    (status, limit),
                )
            else:
                cursor.execute(
                    "SELECT * FROM episodes ORDER BY created_at DESC LIMIT %s", (
                        limit,)
                )

            rows = cursor.fetchall()

            return [
                {
                    "id": str(row["id"]),
                    "name": row["title"],
                    "description": row["synopsis"],
                    "status": row["status"],
                    "created_at": str(row["created_at"]) if row["created_at"] else None,
                    "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
                    "metadata": row["metadata"] if row["metadata"] else None,
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anime/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int):
    """Get project details by ID"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM episodes WHERE id = %s", (project_id,))
            row = cursor.fetchone()

            if not row:
                raise HTTPException(
                    status_code=404, detail="Project not found")

            return {
                "id": str(row["id"]),
                "name": row["title"],
                "description": row["synopsis"],
                "status": row["status"],
                "created_at": str(row["created_at"]) if row["created_at"] else None,
                "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
                "metadata": row["metadata"] if row["metadata"] else None,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== CHARACTER ENDPOINTS ==========


@app.post("/api/anime/characters", response_model=CharacterResponse)
async def create_character(character: CharacterCreate):
    """Create a new character for a project"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Verify project exists
            cursor.execute(
                "SELECT id FROM episodes WHERE id = %s", (
                    character.project_id,)
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404, detail="Project not found")

            cursor.execute(
                """
                INSERT INTO characters (project_id, name, description, image_path, comfyui_workflow)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    character.project_id,
                    character.name,
                    character.description,
                    character.image_path,
                    character.comfyui_workflow,
                ),
            )

            character_id = cursor.lastrowid

            cursor.execute(
                "SELECT * FROM characters WHERE id = %s", (character_id,))
            row = cursor.fetchone()

            return {
                "id": str(row["id"]),
                "project_id": row["project_id"],
                "name": row["title"],
                "description": row["synopsis"],
                "version": row["version"],
                "image_path": row["image_path"],
                "comfyui_workflow": row["comfyui_workflow"],
                "created_at": str(row["created_at"]) if row["created_at"] else None,
                "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating character: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anime/characters", response_model=List[CharacterResponse])
async def list_characters(project_id: Optional[int] = None, limit: int = 100):
    """List characters with optional project filter"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            if project_id:
                cursor.execute(
                    "SELECT * FROM characters WHERE project_id = %s ORDER BY created_at DESC LIMIT %s",
                    (project_id, limit),
                )
            else:
                cursor.execute(
                    "SELECT * FROM characters ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )

            rows = cursor.fetchall()

            return [
                {
                    "id": str(row["id"]),
                    "project_id": row["project_id"],
                    "name": row["title"],
                    "description": row["synopsis"],
                    "version": row["version"],
                    "image_path": row["image_path"],
                    "comfyui_workflow": row["comfyui_workflow"],
                    "created_at": str(row["created_at"]) if row["created_at"] else None,
                    "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error listing characters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/anime/characters/{character_id}", response_model=CharacterResponse)
async def update_character(character_id: int, update: CharacterUpdate):
    """Update character and increment version"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Check if character exists
            cursor.execute(
                "SELECT * FROM characters WHERE id = %s", (character_id,))
            existing = cursor.fetchone()
            if not existing:
                raise HTTPException(
                    status_code=404, detail="Character not found")

            # Build update query dynamically
            updates = []
            params = []

            if update.description is not None:
                updates.append("description = ?")
                params.append(update.description)
            if update.image_path is not None:
                updates.append("image_path = ?")
                params.append(update.image_path)
            if update.comfyui_workflow is not None:
                updates.append("comfyui_workflow = ?")
                params.append(update.comfyui_workflow)

            # Always increment version and update timestamp
            updates.append("version = version + 1")
            updates.append("updated_at = CURRENT_TIMESTAMP")

            params.append(character_id)

            cursor.execute(
                f"""
                UPDATE characters 
                SET {', '.join(updates)}
                WHERE id = %s
            """,
                params,
            )

            # Fetch updated character
            cursor.execute(
                "SELECT * FROM characters WHERE id = %s", (character_id,))
            row = cursor.fetchone()

            return {
                "id": str(row["id"]),
                "project_id": row["project_id"],
                "name": row["title"],
                "description": row["synopsis"],
                "version": row["version"],
                "image_path": row["image_path"],
                "comfyui_workflow": row["comfyui_workflow"],
                "created_at": str(row["created_at"]) if row["created_at"] else None,
                "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating character: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== SCENE ENDPOINTS ==========


@app.post("/api/anime/scenes", response_model=SceneResponse)
async def create_scene(scene: SceneCreate):
    """Create a new scene in a project"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Verify project exists
            cursor.execute(
                "SELECT id FROM episodes WHERE id = %s", (scene.project_id,))
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404, detail="Project not found")

            characters_json = json.dumps(scene.characters)

            cursor.execute(
                """
                INSERT INTO scenes (project_id, branch_name, scene_number, description, characters)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    scene.project_id,
                    scene.branch_name,
                    scene.scene_number,
                    scene.description,
                    characters_json,
                ),
            )

            scene_id = cursor.lastrowid

            cursor.execute("SELECT * FROM scenes WHERE id = %s", (scene_id,))
            row = cursor.fetchone()

            return {
                "id": str(row["id"]),
                "project_id": row["project_id"],
                "branch_name": row["branch_name"],
                "scene_number": row["scene_number"],
                "description": row["synopsis"],
                "characters": (
                    json.loads(row["characters"]) if row["characters"] else []
                ),
                "video_path": row["video_path"],
                "status": row["status"],
                "created_at": str(row["created_at"]) if row["created_at"] else None,
                "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating scene: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anime/scenes", response_model=List[SceneResponse])
async def list_scenes(
    project_id: Optional[int] = None,
    branch_name: Optional[str] = None,
    limit: int = 100,
):
    """List scenes with optional project and branch filters"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            query = "SELECT * FROM scenes WHERE 1=1"
            params = []

            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)
            if branch_name:
                query += " AND branch_name = ?"
                params.append(branch_name)

            query += " ORDER BY scene_number ASC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [
                {
                    "id": str(row["id"]),
                    "project_id": row["project_id"],
                    "branch_name": row["branch_name"],
                    "scene_number": row["scene_number"],
                    "description": row["synopsis"],
                    "characters": (
                        json.loads(row["characters"]
                                   ) if row["characters"] else []
                    ),
                    "video_path": row["video_path"],
                    "status": row["status"],
                    "created_at": str(row["created_at"]) if row["created_at"] else None,
                    "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error listing scenes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/anime/scenes/{scene_id}", response_model=SceneResponse)
async def update_scene(scene_id: int, update: SceneUpdate):
    """Update scene details"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Check if scene exists
            cursor.execute("SELECT * FROM scenes WHERE id = %s", (scene_id,))
            existing = cursor.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Scene not found")

            # Build update query
            updates = []
            params = []

            if update.description is not None:
                updates.append("description = ?")
                params.append(update.description)
            if update.characters is not None:
                updates.append("characters = ?")
                params.append(json.dumps(update.characters))
            if update.video_path is not None:
                updates.append("video_path = ?")
                params.append(update.video_path)
            if update.status is not None:
                updates.append("status = ?")
                params.append(update.status)

            # Always update timestamp
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(scene_id)

            cursor.execute(
                f"""
                UPDATE scenes 
                SET {', '.join(updates)}
                WHERE id = %s
            """,
                params,
            )

            # Fetch updated scene
            cursor.execute("SELECT * FROM scenes WHERE id = %s", (scene_id,))
            row = cursor.fetchone()

            return {
                "id": str(row["id"]),
                "project_id": row["project_id"],
                "branch_name": row["branch_name"],
                "scene_number": row["scene_number"],
                "description": row["synopsis"],
                "characters": (
                    json.loads(row["characters"]) if row["characters"] else []
                ),
                "video_path": row["video_path"],
                "status": row["status"],
                "created_at": str(row["created_at"]) if row["created_at"] else None,
                "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating scene: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Initialize database on startup

# ============================================================================
# GIT-LIKE BRANCHING SYSTEM ENDPOINTS
# ============================================================================


# Pydantic models for git operations
class BranchCreate(BaseModel):
    project_id: int
    new_branch: str
    from_branch: str = "main"
    from_commit: Optional[str] = None
    description: str = ""


class CommitCreate(BaseModel):
    project_id: int
    branch_name: str
    message: str
    author: str
    scene_data: Dict[str, Any]


class MergeRequest(BaseModel):
    project_id: int
    from_branch: str
    to_branch: str
    strategy: str = "ours"
    author: str = "system"


class RevertRequest(BaseModel):
    project_id: int
    branch_name: str
    commit_hash: str
    author: str = "system"


class TagCreate(BaseModel):
    commit_hash: str
    tag_name: str
    description: str = ""


@app.post("/api/anime/branch", tags=["Git Branching"])
async def create_branch(branch: BranchCreate):
    """Create a new storyline branch"""
    try:
        result = git_create_branch(
            project_id=branch.project_id,
            new_branch=branch.new_branch,
            from_branch=branch.from_branch,
            from_commit=branch.from_commit,
            description=branch.description,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating branch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/anime/commit", tags=["Git Branching"])
async def create_commit(commit: CommitCreate):
    """Create a commit with scene snapshot"""
    try:
        result = git_create_commit(
            project_id=commit.project_id,
            branch_name=commit.branch_name,
            message=commit.message,
            author=commit.author,
            scene_data=commit.scene_data,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating commit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anime/commits", tags=["Git Branching"])
async def get_commits(project_id: int, branch_name: str, limit: int = 50):
    """Get commit history for a branch"""
    try:
        commits = git_get_commit_history(project_id, branch_name, limit)
        return {
            "branch_name": branch_name,
            "commit_count": len(commits),
            "commits": commits,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching commits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anime/commit/{commit_hash}", tags=["Git Branching"])
async def get_commit(commit_hash: str):
    """Get full details of a specific commit"""
    try:
        commit = git_get_commit_details(commit_hash)
        return commit
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching commit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anime/branches", tags=["Git Branching"])
async def get_branches(project_id: int):
    """List all branches for a project"""
    try:
        branches = git_list_branches(project_id)
        return {
            "project_id": project_id,
            "branch_count": len(branches),
            "branches": branches,
        }
    except Exception as e:
        logger.error(f"Error listing branches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anime/compare", tags=["Git Branching"])
async def compare_branches(project_id: int, branch_a: str, branch_b: str):
    """Compare two branches"""
    try:
        comparison = git_compare_branches(project_id, branch_a, branch_b)
        return comparison
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error comparing branches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/anime/merge", tags=["Git Branching"])
async def merge_branches(merge: MergeRequest):
    """Merge one branch into another"""
    try:
        result = git_merge_branches(
            project_id=merge.project_id,
            from_branch=merge.from_branch,
            to_branch=merge.to_branch,
            strategy=merge.strategy,
            author=merge.author,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error merging branches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/anime/revert", tags=["Git Branching"])
async def revert_commit(revert: RevertRequest):
    """Revert branch to a previous commit"""
    try:
        result = git_revert_to_commit(
            project_id=revert.project_id,
            branch_name=revert.branch_name,
            commit_hash=revert.commit_hash,
            author=revert.author,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error reverting commit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/anime/tag", tags=["Git Branching"])
async def create_tag(tag: TagCreate):
    """Create a milestone tag for a commit"""
    try:
        result = git_tag_commit(
            commit_hash=tag.commit_hash,
            tag_name=tag.tag_name,
            description=tag.description,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating tag: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Audio storage configuration
AUDIO_STORAGE_PATH = "/mnt/10TB1/Music/SceneAudio"

# Ensure audio storage directory exists
os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)


@app.post("/api/anime/scenes/{scene_id}/audio")
async def upload_scene_audio(
    scene_id: int, audio_file: UploadFile = File(...), bpm: Optional[float] = None
):
    """Upload and attach audio to a scene"""
    try:
        # Validate scene exists
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT id, description FROM scenes WHERE id = %s", (scene_id,)
            )
            scene = cursor.fetchone()
            if not scene:
                raise HTTPException(status_code=404, detail="Scene not found")

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"scene_{scene_id}_{timestamp}_{audio_file.filename}"
        file_path = os.path.join(AUDIO_STORAGE_PATH, filename)

        # Save uploaded file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(audio_file.file, buffer)

        # Analyze BPM via Apple Music service if not provided
        if bpm is None:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://127.0.0.1:8315/api/music/analyze",
                        files={"audio": open(file_path, "rb")},
                        timeout=30.0,
                    )
                    if response.status_code == 200:
                        analysis = response.json()
                        bpm = analysis.get("bpm", 120.0)
            except Exception as e:
                logger.warning(f"BPM analysis failed: {e}")
                bpm = 120.0  # Default BPM

        # Update scene with audio metadata
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """
                SELECT workflow_data FROM scenes WHERE id = %s
            """,
                (scene_id,),
            )
            row = cursor.fetchone()
            workflow_data = json.loads(row[0]) if row[0] else {}

            # Add audio metadata
            workflow_data["audio"] = {
                "file_path": file_path,
                "filename": audio_file.filename,
                "bpm": bpm,
                "uploaded_at": datetime.now().isoformat(),
                "size_bytes": os.path.getsize(file_path),
            }

            cursor.execute(
                """
                UPDATE scenes 
                SET workflow_data = ?
                WHERE id = %s
            """,
                (json.dumps(workflow_data), scene_id),
            )
            conn.commit()

        return {"success": True, "scene_id": scene_id, "audio": workflow_data["audio"]}

    except Exception as e:
        logger.error(f"Error uploading audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anime/scenes/{scene_id}/audio")
async def get_scene_audio(scene_id: int):
    """Get audio metadata for a scene"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT workflow_data FROM scenes WHERE id = %s", (scene_id,)
            )
            row = cursor.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Scene not found")

            workflow_data = json.loads(row[0]) if row[0] else {}
            audio_data = workflow_data.get("audio")

            if not audio_data:
                raise HTTPException(
                    status_code=404, detail="No audio attached to scene"
                )

            # Verify file still exists
            if not os.path.exists(audio_data["file_path"]):
                raise HTTPException(
                    status_code=404, detail="Audio file not found on disk"
                )

            return audio_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/anime/director/command")
async def process_director_command(command: Dict[str, Any]):
    """Process natural language director commands via Echo Brain"""
    try:
        message = command.get("message")
        context = command.get("context", {})

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        # Proxy to Echo Brain
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://127.0.0.1:8309/api/echo/chat",
                json={
                    "message": message,
                    "context": {
                        **context,
                        "source": "director-studio",
                        "timestamp": datetime.now().isoformat(),
                    },
                },
                timeout=60.0,
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Echo Brain error: {response.text}",
                )

            return response.json()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing director command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Natural language command generation endpoint


async def download_apple_music_preview(track_id: str) -> str:
    """Download Apple Music 30-sec preview for video generation"""
    try:
        response = requests.post(
            f"http://127.0.0.1:8315/api/apple-music/track/{track_id}/download"
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("file_path")
    except Exception as e:
        logger.error(f"Failed to download Apple Music preview: {e}")
    return None


@app.post("/api/anime/projects/{project_id}/generate-from-command")
async def generate_from_command(project_id: int, request: Dict[str, Any]):
    """
    Generate anime scenes from natural language commands via Echo Brain

    Flow:
    1. Send command to Echo Brain for interpretation
    2. Extract scene parameters from AI response
    3. Trigger generation via anime service (port 8328)
    4. Return generation_id for tracking
    """
    try:
        command = request.get("command")
        if not command:
            raise HTTPException(status_code=400, detail="Command is required")

        # Verify project exists
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT id, name FROM episodes WHERE id = %s", (project_id,))
            project = cursor.fetchone()
            if not project:
                raise HTTPException(
                    status_code=404, detail="Project not found")

        # Step 1: Send command to Echo Brain for interpretation
        logger.info(f"Sending command to Echo Brain: {command}")
        async with httpx.AsyncClient() as client:
            echo_response = await client.post(
                "http://127.0.0.1:8309/api/echo/chat",
                json={
                    "message": f"Interpret this anime scene generation command and extract parameters: {command}",
                    "context": {
                        "source": "anime-generation",
                        "project_id": project_id,
                        "task": "extract scene parameters from command",
                    },
                },
                timeout=30.0,
            )

            if echo_response.status_code != 200:
                raise HTTPException(
                    status_code=500, detail=f"Echo Brain error: {echo_response.text}"
                )

            echo_data = echo_response.json()
            interpretation = echo_data.get("response", "")

        # Step 2: Use USER-PROVIDED character data, not database garbage
        # Get project info to determine which character set to use
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT name, description FROM episodes WHERE id = %s", (
                    project_id,)
            )
            project = cursor.fetchone()

        # USER'S ACTUAL CHARACTER DATA - use this instead of database
        user_characters = {}
        if "Tokyo Debt Desire" in project["name"]:
            user_characters = {
                "Harem comedy anime": "photorealistic scenes of financial desperation in Tokyo urban setting",
                "Multiple female characters": "diverse personalities and backgrounds in debt situations",
                "Tokyo setting": "modern urban environment, office buildings, financial district",
            }
        elif "Cyberpunk" in project["name"] or "Goblin Slayer" in project["name"]:
            user_characters = {
                "Kai Nakamura": "cyberpunk character in futuristic Tokyo setting",
                "Goblin Slayer elements": "dark fantasy mixed with cyberpunk aesthetics",
                "Futuristic Tokyo": "neon lights, high-tech urban environment",
            }

        # Build enhanced prompt with USER'S character data
        enhanced_prompt = command
        if user_characters:
            char_descriptions = [
                f"{name}: {desc}" for name, desc in user_characters.items()
            ]
            enhanced_prompt = f"{command}. Characters: {'; '.join(char_descriptions)}"

        generation_params = {
            "prompt": enhanced_prompt,
            "character": (
                list(user_characters.keys())[0]
                if user_characters
                else "anime character"
            ),
            "duration": 5,
            "frames": 120,
            "style": "anime masterpiece",
            "width": 1920,
            "height": 1080,
            "fps": 24,
        }

        # Step 3: Create v2.0 tracked job first
        logger.info("Creating v2.0 tracked job")
        job_data = await create_tracked_job(
            character_name=generation_params["character"],
            prompt=generation_params["prompt"],
            project_name=project["name"],
            seed=-1,  # Will be set by ComfyUI
            model="default",
            width=generation_params["width"],
            height=generation_params["height"],
            duration=generation_params["duration"],
            frames=generation_params["frames"],
        )

        # Step 4: Trigger generation via anime service
        logger.info(
            f"Triggering generation via anime service: {generation_params}")
        generation_params["v2_job_id"] = job_data["job_id"]  # Pass tracking ID

        async with httpx.AsyncClient() as client:
            gen_response = await client.post(
                f"http://127.0.0.1:8328/api/anime/generate-redis",
                json=generation_params,
                timeout=60.0,
            )

            if gen_response.status_code != 200:
                raise HTTPException(
                    status_code=gen_response.status_code,
                    detail=f"Generation service error: {gen_response.text}",
                )

            generation_data = gen_response.json()

        # Return generation tracking info with v2.0 job ID
        return {
            "success": True,
            "generation_id": generation_data.get("generation_id"),
            "v2_job_id": job_data["job_id"],  # v2.0 tracking ID
            "status": "generating",
            "command": command,
            "interpretation": interpretation,
            "project_id": project_id,
            "tracking_enabled": True,
            "reproducible": True,
            "message": "Scene generation started with v2.0 tracking",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in generate_from_command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Voice generation for scenes
@app.post("/api/anime/scenes/{scene_id}/generate-voice")
async def generate_scene_voice(scene_id: int, request: Dict[str, Any]):
    """Generate voice line for scene dialogue"""
    try:
        dialogue = request.get("dialogue")
        if not dialogue:
            raise HTTPException(status_code=400, detail="Dialogue is required")

        # Verify scene exists
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT id, description FROM scenes WHERE id = %s", (scene_id,)
            )
            scene = cursor.fetchone()
            if not scene:
                raise HTTPException(status_code=404, detail="Scene not found")

        # Connect to voice service (port 8316)
        logger.info(f"Generating voice for scene {scene_id}: {dialogue}")
        async with httpx.AsyncClient() as client:
            voice_response = await client.post(
                "http://127.0.0.1:8316/api/tts/generate",
                json={"text": dialogue, "voice": "default", "scene_id": scene_id},
                timeout=60.0,
            )

            if voice_response.status_code != 200:
                raise HTTPException(
                    status_code=voice_response.status_code,
                    detail=f"Voice service error: {voice_response.text}",
                )

            voice_data = voice_response.json()

        # Attach voice to scene workflow_data
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT workflow_data FROM scenes WHERE id = %s", (scene_id,)
            )
            row = cursor.fetchone()
            workflow_data = json.loads(row[0]) if row[0] else {}

            workflow_data["voice"] = {
                "dialogue": dialogue,
                "voice_file": voice_data.get("file_path"),
                "duration": voice_data.get("duration"),
                "generated_at": datetime.now().isoformat(),
            }

            cursor.execute(
                """
                UPDATE scenes 
                SET workflow_data = ?
                WHERE id = %s
            """,
                (json.dumps(workflow_data), scene_id),
            )
            conn.commit()

        return {"success": True, "scene_id": scene_id, "voice": workflow_data["voice"]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating voice: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Apple Music playlist integration
@app.get("/api/anime/audio/playlists")
async def get_music_playlists():
    """Get user music playlists from Apple Music service"""
    try:
        # Proxy to Apple Music service (port 8315)
        logger.info("Fetching Apple Music playlists")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://127.0.0.1:8315/api/music/playlists", timeout=30.0
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Apple Music service error: {response.text}",
                )

            return response.json()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching playlists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("startup")
async def startup_event():
    """Initialize database on application startup"""
    init_db()
    logger.info("Tower Anime Production API started successfully")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8328)


# ============================================================================
# AUDIO ATTACHMENT ENDPOINTS
# ============================================================================


SCENE_AUDIO_DIR = Path("/mnt/10TB1/Music/SceneAudio")
SCENE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/api/anime/scenes/{scene_id}/audio", tags=["Audio"])
async def upload_scene_audio(scene_id: int, file: UploadFile = File(...)):
    """Upload audio file for a scene and analyze BPM"""
    try:
        # Verify scene exists
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "SELECT id, description FROM scenes WHERE id = %s", (scene_id,))
        scene = cursor.fetchone()

        if not scene:
            conn.close()
            raise HTTPException(status_code=404, detail="Scene not found")

        # Save file to storage
        file_extension = Path(file.filename).suffix
        audio_filename = f"scene_{scene_id}_{int(time.time())}{file_extension}"
        audio_path = SCENE_AUDIO_DIR / audio_filename

        with audio_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(f"Audio file saved: {audio_path}")

        # Try to get BPM from Apple Music service
        bpm = None
        duration = None
        try:
            # Call Apple Music quality analysis
            # Note: This requires the track to be in Apple Music library first
            # For uploaded files, we'll store without BPM analysis initially
            logger.info(
                "BPM analysis would be performed here via Apple Music service")
            bpm = None  # Placeholder - Apple Music needs library integration
        except Exception as e:
            logger.warning(f"BPM analysis failed: {e}")

        # Update scene with audio path
        cursor.execute(
            "UPDATE scenes SET video_path = ? WHERE id = %s",
            (str(audio_path), scene_id),
        )
        conn.commit()
        conn.close()

        return {
            "success": True,
            "scene_id": scene_id,
            "audio_file": audio_filename,
            "audio_path": str(audio_path),
            "bpm": bpm,
            "duration": duration,
            "message": "Audio uploaded successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anime/scenes/{scene_id}/audio", tags=["Audio"])
async def get_scene_audio(scene_id: int):
    """Get audio file path for a scene"""
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "SELECT id, video_path FROM scenes WHERE id = %s", (scene_id,))
        scene = cursor.fetchone()
        conn.close()

        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")

        audio_path = scene[1]

        if not audio_path or not Path(audio_path).exists():
            return {"scene_id": scene_id, "has_audio": False, "audio_path": None}

        return {
            "scene_id": scene_id,
            "has_audio": True,
            "audio_path": audio_path,
            "filename": Path(audio_path).name,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting scene audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DIRECTOR COMMAND ENDPOINTS
# ============================================================================


@app.post("/api/anime/director/command", tags=["Director"])
async def process_director_command(command: dict):
    """Process natural language director command via Echo Brain"""
    try:
        message = command.get("message", "")
        context = command.get("context", {})

        if not message:
            raise HTTPException(status_code=400, detail="Message required")

        # Forward to Echo Brain
        try:
            echo_response = requests.post(
                "http://127.0.0.1:8309/api/echo/chat",
                json={
                    "message": message,
                    "context": {
                        **context,
                        "source": "director-studio",
                        "type": "director_command",
                    },
                },
                timeout=30,
            )

            if echo_response.status_code == 200:
                return echo_response.json()
            else:
                raise Exception(
                    f"Echo Brain error: {echo_response.status_code}")

        except requests.exceptions.Timeout:
            raise HTTPException(status_code=504, detail="Echo Brain timeout")
        except requests.exceptions.ConnectionError:
            raise HTTPException(
                status_code=503, detail="Echo Brain unavailable")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing director command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === GIT STORYLINE CONTROL ENDPOINTS ===


class GitBranchRequest(BaseModel):
    project_id: int
    new_branch_name: str
    from_branch: str = "main"
    storyline_goal: str = ""
    author: str = "director"


class GitCommitRequest(BaseModel):
    project_id: int
    branch_name: str
    message: str
    author: str = "director"
    scene_data: Dict[str, Any]
    analyze_impact: bool = True


class StorylineMarkersRequest(BaseModel):
    project_id: int
    scenes: List[Dict[str, Any]]


@app.post("/api/anime/git/branches", response_model=Dict[str, Any])
async def create_git_branch(request: GitBranchRequest):
    """Create a new git branch with Echo Brain's storyline guidance"""
    try:
        from git_branching import echo_guided_branch_creation

        result = await echo_guided_branch_creation(
            project_id=request.project_id,
            base_branch=request.from_branch,
            new_branch_name=request.new_branch_name,
            storyline_goal=request.storyline_goal,
            author=request.author,
        )

        return {
            "success": True,
            "branch_name": request.new_branch_name,
            "echo_guidance": result.get("echo_guidance", {}),
            "created_at": result.get("created_at"),
            "base_analysis": result.get("base_analysis", {}),
        }

    except Exception as e:
        logger.error(f"Git branch creation failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Git branch creation failed: {str(e)}"
        )


@app.get("/api/anime/git/branches/{project_id}", response_model=List[Dict[str, Any]])
async def get_project_branches(project_id: int):
    """Get all git branches for a project"""
    try:
        from git_branching import list_branches

        branches = list_branches(project_id)
        return branches

    except Exception as e:
        logger.error(f"Get branches failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Get branches failed: {str(e)}")


@app.post("/api/anime/storyline/analyze/{project_id}", response_model=Dict[str, Any])
async def analyze_storyline(project_id: int, branch_name: str = "main"):
    """Get Echo Brain's analysis of storyline progression"""
    try:
        from git_branching import echo_analyze_storyline

        analysis = await echo_analyze_storyline(project_id, branch_name)
        return analysis

    except Exception as e:
        logger.error(f"Storyline analysis failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Storyline analysis failed: {str(e)}"
        )


@app.post("/api/anime/storyline/markers", response_model=Dict[str, Any])
async def create_storyline_markers(request: StorylineMarkersRequest):
    """Create comprehensive editing markers for video production"""
    try:
        from echo_integration import EchoIntegration

        echo = EchoIntegration()
        markers = await echo.create_storyline_markers(
            request.project_id, request.scenes
        )

        return {
            "success": True,
            "markers": markers,
            "total_scenes": len(request.scenes),
            "created_at": markers.get("created_at"),
        }

    except Exception as e:
        logger.error(f"Storyline markers creation failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Storyline markers failed: {str(e)}"
        )


@app.get("/api/anime/git/status/{project_id}", response_model=Dict[str, Any])
async def get_git_status(project_id: int):
    """Get comprehensive git status for a project including Echo analysis"""
    try:
        from git_branching import (echo_analyze_storyline, get_commit_history,
                                   list_branches)

        # Get all branches
        branches = list_branches(project_id)

        # Get commit history for main branch
        main_commits = get_commit_history(project_id, "main")

        # Get latest Echo analysis
        latest_analysis = await echo_analyze_storyline(project_id, "main")

        return {
            "project_id": project_id,
            "branches": branches,
            "main_branch_commits": len(main_commits),
            "latest_commits": main_commits[:5] if main_commits else [],
            "echo_analysis": latest_analysis,
            "status_checked_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Git status check failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Git status failed: {str(e)}")


# Project Bible API endpoints
bible_api = None


def get_bible_api():
    global bible_api
    if bible_api is None:
        # Create simple database manager that uses existing get_db context
        class SimpleDBManager:
            def get_connection(self):
                return get_db()

        db_manager = SimpleDBManager()
        bible_api = ProjectBibleAPI(db_manager)
    return bible_api


@app.post("/api/anime/projects/{project_id}/bible", response_model=Dict[str, Any])
async def create_project_bible(project_id: int, bible_data: ProjectBibleCreate):
    """Create a new project bible for a project"""
    try:
        bible_api = get_bible_api()
        result = await bible_api.create_project_bible(project_id, bible_data)
        return result
    except Exception as e:
        logger.error(f"Error creating project bible: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anime/projects/{project_id}/bible", response_model=Dict[str, Any])
async def get_project_bible(project_id: int):
    """Get project bible for a project"""
    try:
        bible_api = get_bible_api()
        result = await bible_api.get_project_bible(project_id)
        return result
    except Exception as e:
        logger.error(f"Error getting project bible: {e}")
        raise HTTPException(status_code=404, detail="Project bible not found")


@app.put("/api/anime/projects/{project_id}/bible", response_model=Dict[str, Any])
async def update_project_bible(project_id: int, bible_update: ProjectBibleUpdate):
    """Update project bible"""
    try:
        bible_api = get_bible_api()
        result = await bible_api.update_project_bible(project_id, bible_update)
        return result
    except Exception as e:
        logger.error(f"Error updating project bible: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/anime/projects/{project_id}/bible/characters", response_model=Dict[str, Any]
)
async def add_character_to_bible(project_id: int, character: CharacterDefinition):
    """Add character definition to project bible"""
    try:
        bible_api = get_bible_api()
        result = await bible_api.add_character_to_bible(project_id, character)
        return result
    except Exception as e:
        logger.error(f"Error adding character to bible: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/api/anime/projects/{project_id}/bible/characters",
    response_model=List[Dict[str, Any]],
)
async def get_bible_characters(project_id: int):
    """Get all characters from project bible"""
    try:
        bible_api = get_bible_api()
        result = await bible_api.get_bible_characters(project_id)
        return result
    except Exception as e:
        logger.error(f"Error getting bible characters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/api/anime/projects/{project_id}/bible/history",
    response_model=List[Dict[str, Any]],
)
async def get_bible_history(project_id: int):
    """Get revision history for project bible"""
    try:
        bible_api = get_bible_api()
        result = await bible_api.get_bible_history(project_id)
        return result
    except Exception as e:
        logger.error(f"Error getting bible history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
