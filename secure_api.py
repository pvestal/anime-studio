#!/usr/bin/env python3
"""
Secure Anime Production API - with practical security measures
Not theater, just sensible protections
"""

import os
import re
import asyncio
import json
import time
import uuid
import requests
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
import uvicorn
from dotenv import load_dotenv

from database import db_manager, initialize_database, close_database

# Load environment variables
load_dotenv()

# Configuration from environment
COMFYUI_URL = os.getenv('COMFYUI_URL', 'http://localhost:8188')
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', '/mnt/1TB-storage/ComfyUI/output'))
ORGANIZED_DIR = Path(os.getenv('ORGANIZED_DIR', '/mnt/1TB-storage/anime/projects'))
PORT = int(os.getenv('API_PORT', '8328'))

# Ensure organized directory exists
ORGANIZED_DIR.mkdir(parents=True, exist_ok=True)

# FastAPI app
app = FastAPI(
    title="Anime Production API - Secure",
    description="Production anime generation with practical security",
    version="4.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
jobs_cache: Dict[str, Dict[str, Any]] = {}
projects: Dict[str, Dict[str, Any]] = {}
characters: Dict[str, Dict[str, Any]] = {}
websocket_connections: Dict[str, WebSocket] = {}
generation_queue = Queue()
MODEL_PRELOADED = False

# Input validation helpers
def sanitize_text(text: str, max_length: int = 1000) -> str:
    """Sanitize text input to prevent injection"""
    if not text:
        return ""

    # Remove null bytes
    text = text.replace('\x00', '')

    # Limit length
    text = text[:max_length]

    # Remove control characters except newlines and tabs
    text = ''.join(char for char in text if char == '\n' or char == '\t' or ord(char) >= 32)

    return text.strip()

def validate_id(id_string: str) -> bool:
    """Validate ID format to prevent injection"""
    # IDs should be alphanumeric with hyphens only
    return bool(re.match(r'^[a-zA-Z0-9\-]+$', id_string)) and len(id_string) <= 50

# Pydantic models with validation
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field("", max_length=500)
    style: Optional[str] = Field("anime", max_length=50)
    metadata: Optional[Dict[str, Any]] = {}

    @validator('name', 'description', 'style')
    def sanitize_fields(cls, v):
        if v:
            return sanitize_text(v)
        return v

class CharacterCreate(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field("", max_length=500)
    personality: Optional[str] = Field("", max_length=500)
    appearance: str = Field(..., min_length=1, max_length=500)
    backstory: Optional[str] = Field("", max_length=1000)
    reference_prompts: Optional[List[str]] = []

    @validator('project_id')
    def validate_project_id(cls, v):
        if not validate_id(v):
            raise ValueError('Invalid project ID format')
        return v

    @validator('name', 'description', 'personality', 'appearance', 'backstory')
    def sanitize_fields(cls, v):
        if v:
            return sanitize_text(v)
        return v

class GenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)
    negative_prompt: Optional[str] = Field("bad quality, deformed, blurry", max_length=500)
    width: int = Field(512, ge=64, le=2048)
    height: int = Field(768, ge=64, le=2048)
    project_id: Optional[str] = Field(None, max_length=50)
    character_id: Optional[str] = Field(None, max_length=50)
    style_preset: Optional[str] = Field(None, max_length=50)

    @validator('prompt', 'negative_prompt')
    def sanitize_prompts(cls, v):
        if v:
            return sanitize_text(v)
        return v

    @validator('project_id', 'character_id')
    def validate_ids(cls, v):
        if v and not validate_id(v):
            raise ValueError('Invalid ID format')
        return v

    @validator('width', 'height')
    def validate_dimensions(cls, v):
        # Round to nearest 64 for better generation
        return (v // 64) * 64

def preload_models():
    """Preload ComfyUI models at startup"""
    global MODEL_PRELOADED
    print("🚀 Preloading models...")

    try:
        dummy_workflow = create_workflow("preload test", "bad", 512, 512)
        response = requests.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": dummy_workflow},
            timeout=60
        )

        if response.status_code == 200:
            MODEL_PRELOADED = True
            print("✅ Models preloaded successfully")
        else:
            print(f"⚠️ Model preload returned {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to preload models: {e}")

def create_workflow(prompt: str, negative_prompt: str, width: int, height: int,
                   style_preset: Optional[str] = None) -> Dict[str, Any]:
    """Create optimized workflow"""

    # Sanitize inputs for workflow
    prompt = sanitize_text(prompt, 1000)
    negative_prompt = sanitize_text(negative_prompt, 500)

    seed = int(time.time() * 1000) % 2147483647
    filename_prefix = f"anime_{int(time.time())}"

    if style_preset and style_preset in ["cyberpunk", "fantasy", "steampunk", "studio_ghibli", "manga"]:
        prompt = apply_style_preset(prompt, style_preset)

    return {
        "3": {
            "inputs": {
                "seed": seed,
                "steps": 15,
                "cfg": 7,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler"
        },
        "4": {
            "inputs": {
                "ckpt_name": "Counterfeit-V2.5.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "5": {
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1
            },
            "class_type": "EmptyLatentImage"
        },
        "6": {
            "inputs": {
                "text": prompt,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "7": {
            "inputs": {
                "text": negative_prompt,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "8": {
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            },
            "class_type": "VAEDecode"
        },
        "9": {
            "inputs": {
                "filename_prefix": filename_prefix,
                "images": ["8", 0]
            },
            "class_type": "SaveImage"
        }
    }

def apply_style_preset(prompt: str, style: str) -> str:
    """Apply validated style presets"""
    styles = {
        "cyberpunk": f"{prompt}, cyberpunk style, neon lights, futuristic city, high tech",
        "fantasy": f"{prompt}, fantasy art style, magical, ethereal lighting, detailed",
        "steampunk": f"{prompt}, steampunk style, brass and copper, victorian era, mechanical",
        "studio_ghibli": f"{prompt}, studio ghibli style, soft colors, whimsical, detailed background",
        "manga": f"{prompt}, manga style, black and white, detailed linework, expressive"
    }
    return styles.get(style, prompt)

def organize_file(source_path: Path, project_id: str, character_id: Optional[str] = None) -> Path:
    """Organize generated files with validation"""

    # Validate IDs
    if not validate_id(project_id):
        raise ValueError("Invalid project ID")

    if character_id and not validate_id(character_id):
        raise ValueError("Invalid character ID")

    # Create safe paths
    project_dir = ORGANIZED_DIR / project_id
    project_dir.mkdir(exist_ok=True)

    if character_id:
        char_dir = project_dir / "characters" / character_id
        char_dir.mkdir(parents=True, exist_ok=True)
        dest_dir = char_dir
    else:
        dest_dir = project_dir / "general"
        dest_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_path = dest_dir / f"{timestamp}_{source_path.name}"
    shutil.copy2(source_path, dest_path)

    return dest_path

async def process_generation_worker():
    """Worker to process generation queue"""
    executor = ThreadPoolExecutor(max_workers=3)

    while True:
        if not generation_queue.empty():
            job_data = generation_queue.get()
            executor.submit(process_single_generation, job_data)
        await asyncio.sleep(0.1)

def process_single_generation(job_data: Dict[str, Any]):
    """Process a single generation job"""
    job_id = job_data["id"]

    try:
        workflow = create_workflow(
            job_data["prompt"],
            job_data["negative_prompt"],
            job_data["width"],
            job_data["height"],
            job_data.get("style_preset")
        )

        response = requests.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            comfyui_id = result.get("prompt_id")
            job_data["comfyui_id"] = comfyui_id
            job_data["status"] = "processing"
            monitor_and_complete(job_id, comfyui_id, job_data)
        else:
            job_data["status"] = "failed"
            job_data["error"] = f"ComfyUI error: {response.status_code}"

    except Exception as e:
        job_data["status"] = "failed"
        job_data["error"] = str(e)

def monitor_and_complete(job_id: str, comfyui_id: str, job_data: Dict[str, Any]):
    """Monitor job completion"""
    max_wait = 60

    while max_wait > 0:
        try:
            response = requests.get(f"{COMFYUI_URL}/history/{comfyui_id}")

            if response.status_code == 200:
                history = response.json()

                if comfyui_id in history:
                    job_result = history[comfyui_id]
                    outputs = job_result.get("outputs", {})

                    for node_output in outputs.values():
                        if "images" in node_output:
                            for img in node_output["images"]:
                                source_path = OUTPUT_DIR / img["filename"]
                                if source_path.exists():
                                    if job_data.get("project_id"):
                                        try:
                                            organized_path = organize_file(
                                                source_path,
                                                job_data["project_id"],
                                                job_data.get("character_id")
                                            )
                                            job_data["organized_path"] = str(organized_path)
                                        except ValueError as e:
                                            print(f"Organization error: {e}")

                                    job_data["output_path"] = str(source_path)
                                    job_data["status"] = "completed"
                                    job_data["completed_at"] = datetime.utcnow().isoformat()
                                    job_data["total_time"] = time.time() - job_data["start_time"]

                                    asyncio.run(send_progress_update(job_id, 100, "completed"))
                                    return

                    job_data["status"] = "failed"
                    job_data["error"] = "No output file generated"
                    return

        except Exception as e:
            print(f"Monitor error: {e}")

        time.sleep(1)
        max_wait -= 1

        progress = int((60 - max_wait) / 60 * 100)
        asyncio.run(send_progress_update(job_id, progress, "processing"))

    job_data["status"] = "failed"
    job_data["error"] = "Generation timeout"

async def send_progress_update(job_id: str, progress: int, status: str):
    """Send progress updates via WebSocket"""
    if job_id in websocket_connections:
        try:
            await websocket_connections[job_id].send_json({
                "job_id": job_id,
                "progress": progress,
                "status": status,
                "timestamp": datetime.utcnow().isoformat()
            })
        except:
            pass

@app.on_event("startup")
async def startup_event():
    """Initialize system on startup"""
    print("Starting secure anime production API...")
    await initialize_database()
    preload_models()
    asyncio.create_task(process_generation_worker())
    print("System ready!")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    await close_database()

# API Endpoints

@app.post("/api/anime/projects")
async def create_project(project: ProjectCreate):
    """Create a new anime project with validation"""
    project_id = str(uuid.uuid4())[:8]

    project_data = {
        "id": project_id,
        "name": project.name,
        "description": project.description,
        "style": project.style,
        "metadata": project.metadata,
        "created_at": datetime.utcnow().isoformat(),
        "file_count": 0,
        "characters": []
    }

    projects[project_id] = project_data

    # Save to database with parameterized query
    try:
        await db_manager.create_job({
            "id": project_id,
            "prompt": f"Project: {project.name}",
            "status": "project_created"
        })
    except:
        pass  # Project tracking in memory is sufficient

    project_dir = ORGANIZED_DIR / project_id
    project_dir.mkdir(exist_ok=True)

    return project_data

@app.get("/api/anime/projects")
async def list_projects():
    """List all projects"""
    return {"projects": list(projects.values())}

@app.get("/api/anime/projects/{project_id}")
async def get_project(project_id: str):
    """Get project details with ID validation"""
    if not validate_id(project_id):
        raise HTTPException(400, "Invalid project ID format")

    if project_id not in projects:
        raise HTTPException(404, "Project not found")

    return projects[project_id]

@app.post("/api/anime/characters")
async def create_character(character: CharacterCreate):
    """Create a character with validation"""
    character_id = str(uuid.uuid4())[:8]

    character_data = {
        "id": character_id,
        "project_id": character.project_id,
        "name": character.name,
        "description": character.description,
        "personality": character.personality,
        "appearance": character.appearance,
        "backstory": character.backstory,
        "reference_prompts": character.reference_prompts,
        "created_at": datetime.utcnow().isoformat(),
        "generation_count": 0
    }

    characters[character_id] = character_data

    if character.project_id in projects:
        projects[character.project_id]["characters"].append(character_id)

    return character_data

@app.get("/api/anime/characters/{character_id}")
async def get_character(character_id: str):
    """Get character details with validation"""
    if not validate_id(character_id):
        raise HTTPException(400, "Invalid character ID format")

    if character_id not in characters:
        raise HTTPException(404, "Character not found")

    return characters[character_id]

@app.get("/api/anime/characters/{character_id}/bible")
async def get_character_bible(character_id: str):
    """Get character bible with validation"""
    if not validate_id(character_id):
        raise HTTPException(400, "Invalid character ID format")

    if character_id not in characters:
        raise HTTPException(404, "Character not found")

    char = characters[character_id]
    return {
        "character_id": character_id,
        "bible": {
            "name": char["name"],
            "appearance": char["appearance"],
            "personality": char["personality"],
            "backstory": char["backstory"],
            "reference_prompts": char["reference_prompts"],
            "generation_count": char["generation_count"]
        }
    }

@app.post("/generate")
async def generate_image(request: GenerationRequest, background_tasks: BackgroundTasks):
    """Generate image with full validation"""
    job_id = str(uuid.uuid4())[:8]

    job_data = {
        "id": job_id,
        "status": "queued",
        "prompt": request.prompt,
        "negative_prompt": request.negative_prompt,
        "width": request.width,
        "height": request.height,
        "project_id": request.project_id,
        "character_id": request.character_id,
        "style_preset": request.style_preset,
        "created_at": datetime.utcnow().isoformat(),
        "start_time": time.time()
    }

    jobs_cache[job_id] = job_data
    generation_queue.put(job_data)

    # Save to database with parameterized query
    try:
        await db_manager.create_job(job_data)
    except Exception as e:
        print(f"DB save error (non-critical): {e}")

    return {
        "job_id": job_id,
        "status": "queued",
        "queue_position": generation_queue.qsize(),
        "estimated_time": f"{generation_queue.qsize() * 4} seconds",
        "websocket_url": f"ws://localhost:{PORT}/ws/{job_id}"
    }

@app.websocket("/ws/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    """WebSocket with ID validation"""
    if not validate_id(job_id):
        await websocket.close()
        return

    await websocket.accept()
    websocket_connections[job_id] = websocket

    try:
        while True:
            await asyncio.sleep(1)

            if job_id in jobs_cache:
                job = jobs_cache[job_id]
                await websocket.send_json({
                    "job_id": job_id,
                    "status": job["status"],
                    "progress": 100 if job["status"] == "completed" else 50
                })

                if job["status"] in ["completed", "failed"]:
                    break

    except WebSocketDisconnect:
        pass
    finally:
        if job_id in websocket_connections:
            del websocket_connections[job_id]

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status with validation"""
    if not validate_id(job_id):
        raise HTTPException(400, "Invalid job ID format")

    if job_id not in jobs_cache:
        job = await db_manager.get_job(job_id)
        if not job:
            raise HTTPException(404, f"Job {job_id} not found")
        return job

    return jobs_cache[job_id]

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "model_preloaded": MODEL_PRELOADED,
        "queue_size": generation_queue.qsize(),
        "active_websockets": len(websocket_connections),
        "projects": len(projects),
        "characters": len(characters),
        "jobs_in_memory": len(jobs_cache),
        "security": "enabled"
    }

if __name__ == "__main__":
    # Install python-dotenv if needed
    import subprocess
    import sys

    try:
        from dotenv import load_dotenv
    except ImportError:
        print("Installing python-dotenv...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "python-dotenv"])
        from dotenv import load_dotenv

    uvicorn.run(
        "secure_api:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info"
    )