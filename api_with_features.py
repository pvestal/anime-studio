#!/usr/bin/env python3
"""
Optimized Anime Production API with all missing features
- Model preloading for instant generation
- True concurrent processing
- Project management
- Character tracking
- File organization
"""

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
import threading
from queue import Queue

from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from database import db_manager, initialize_database, close_database

# Configuration
COMFYUI_URL = "http://localhost:8188"
OUTPUT_DIR = Path("/mnt/1TB-storage/ComfyUI/output")
ORGANIZED_DIR = Path("/mnt/1TB-storage/anime/projects")
PORT = 8328

# Ensure organized directory exists
ORGANIZED_DIR.mkdir(parents=True, exist_ok=True)

# FastAPI app
app = FastAPI(
    title="Anime Production API - Optimized",
    description="Full-featured anime generation with project management",
    version="3.0.0"
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

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    style: Optional[str] = "anime"
    metadata: Optional[Dict[str, Any]] = {}

class CharacterCreate(BaseModel):
    project_id: str
    name: str
    description: str
    personality: Optional[str] = ""
    appearance: str
    backstory: Optional[str] = ""
    reference_prompts: Optional[List[str]] = []

class GenerationRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = "bad quality, deformed, blurry"
    width: int = 512
    height: int = 768
    project_id: Optional[str] = None
    character_id: Optional[str] = None
    style_preset: Optional[str] = None

def preload_models():
    """Preload ComfyUI models at startup to avoid cold start"""
    global MODEL_PRELOADED
    print("🚀 Preloading models...")

    try:
        # Trigger model loading with a dummy request
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
    """Create optimized workflow with style presets"""

    seed = int(time.time() * 1000) % 2147483647
    filename_prefix = f"anime_{int(time.time())}"

    # Apply style preset if provided
    if style_preset:
        prompt = apply_style_preset(prompt, style_preset)

    # Optimized workflow with reduced steps for speed
    return {
        "3": {
            "inputs": {
                "seed": seed,
                "steps": 15,  # Reduced from 20 for speed
                "cfg": 7,
                "sampler_name": "dpmpp_2m",  # Faster sampler
                "scheduler": "karras",  # Better quality/speed ratio
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
    """Apply style presets to prompts"""
    styles = {
        "cyberpunk": f"{prompt}, cyberpunk style, neon lights, futuristic city, high tech",
        "fantasy": f"{prompt}, fantasy art style, magical, ethereal lighting, detailed",
        "steampunk": f"{prompt}, steampunk style, brass and copper, victorian era, mechanical",
        "studio_ghibli": f"{prompt}, studio ghibli style, soft colors, whimsical, detailed background",
        "manga": f"{prompt}, manga style, black and white, detailed linework, expressive"
    }
    return styles.get(style, prompt)

def organize_file(source_path: Path, project_id: str, character_id: Optional[str] = None) -> Path:
    """Organize generated files by project and character"""

    # Create project directory
    project_dir = ORGANIZED_DIR / project_id
    project_dir.mkdir(exist_ok=True)

    if character_id:
        # Create character subdirectory
        char_dir = project_dir / "characters" / character_id
        char_dir.mkdir(parents=True, exist_ok=True)
        dest_dir = char_dir
    else:
        # General project images
        dest_dir = project_dir / "general"
        dest_dir.mkdir(exist_ok=True)

    # Copy file to organized location
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_path = dest_dir / f"{timestamp}_{source_path.name}"
    shutil.copy2(source_path, dest_path)

    return dest_path

async def process_generation_worker():
    """Worker to process generation queue concurrently"""
    executor = ThreadPoolExecutor(max_workers=3)  # True concurrent processing

    while True:
        if not generation_queue.empty():
            job_data = generation_queue.get()
            executor.submit(process_single_generation, job_data)
        await asyncio.sleep(0.1)

def process_single_generation(job_data: Dict[str, Any]):
    """Process a single generation job"""
    job_id = job_data["id"]

    try:
        # Create workflow
        workflow = create_workflow(
            job_data["prompt"],
            job_data["negative_prompt"],
            job_data["width"],
            job_data["height"],
            job_data.get("style_preset")
        )

        # Submit to ComfyUI
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

            # Monitor completion
            monitor_and_complete(job_id, comfyui_id, job_data)
        else:
            job_data["status"] = "failed"
            job_data["error"] = f"ComfyUI error: {response.status_code}"

    except Exception as e:
        job_data["status"] = "failed"
        job_data["error"] = str(e)

def monitor_and_complete(job_id: str, comfyui_id: str, job_data: Dict[str, Any]):
    """Monitor job completion and organize output"""
    max_wait = 60

    while max_wait > 0:
        try:
            # Check ComfyUI history
            response = requests.get(f"{COMFYUI_URL}/history/{comfyui_id}")

            if response.status_code == 200:
                history = response.json()

                if comfyui_id in history:
                    # Find output file
                    job_result = history[comfyui_id]
                    outputs = job_result.get("outputs", {})

                    for node_output in outputs.values():
                        if "images" in node_output:
                            for img in node_output["images"]:
                                source_path = OUTPUT_DIR / img["filename"]
                                if source_path.exists():
                                    # Organize file if project specified
                                    if job_data.get("project_id"):
                                        organized_path = organize_file(
                                            source_path,
                                            job_data["project_id"],
                                            job_data.get("character_id")
                                        )
                                        job_data["organized_path"] = str(organized_path)

                                    job_data["output_path"] = str(source_path)
                                    job_data["status"] = "completed"
                                    job_data["completed_at"] = datetime.utcnow().isoformat()
                                    job_data["total_time"] = time.time() - job_data["start_time"]

                                    # Send WebSocket update
                                    asyncio.run(send_progress_update(job_id, 100, "completed"))

                                    return

                    # No output found
                    job_data["status"] = "failed"
                    job_data["error"] = "No output file generated"
                    return

        except Exception as e:
            print(f"Monitor error: {e}")

        time.sleep(1)
        max_wait -= 1

        # Send progress updates
        progress = int((60 - max_wait) / 60 * 100)
        asyncio.run(send_progress_update(job_id, progress, "processing"))

    # Timeout
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
    print("Starting optimized anime production API...")

    # Initialize database
    await initialize_database()

    # Preload models to avoid cold start
    preload_models()

    # Start generation worker
    asyncio.create_task(process_generation_worker())

    print("System ready!")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    await close_database()

# Project Management Endpoints

@app.post("/api/anime/projects")
async def create_project(project: ProjectCreate):
    """Create a new anime project"""
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

    # Create project directory
    project_dir = ORGANIZED_DIR / project_id
    project_dir.mkdir(exist_ok=True)

    return project_data

@app.get("/api/anime/projects")
async def list_projects():
    """List all projects"""
    return {"projects": list(projects.values())}

@app.get("/api/anime/projects/{project_id}")
async def get_project(project_id: str):
    """Get project details"""
    if project_id not in projects:
        raise HTTPException(404, "Project not found")
    return projects[project_id]

# Character Management Endpoints

@app.post("/api/anime/characters")
async def create_character(character: CharacterCreate):
    """Create a character with bible"""
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

    # Update project
    if character.project_id in projects:
        projects[character.project_id]["characters"].append(character_id)

    return character_data

@app.get("/api/anime/characters/{character_id}")
async def get_character(character_id: str):
    """Get character details including bible"""
    if character_id not in characters:
        raise HTTPException(404, "Character not found")
    return characters[character_id]

@app.get("/api/anime/characters/{character_id}/bible")
async def get_character_bible(character_id: str):
    """Get complete character bible"""
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

# Enhanced Generation Endpoint

@app.post("/generate")
async def generate_image(request: GenerationRequest, background_tasks: BackgroundTasks):
    """Generate image with project/character tracking"""

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

    # Add to cache
    jobs_cache[job_id] = job_data

    # Add to processing queue
    generation_queue.put(job_data)

    return {
        "job_id": job_id,
        "status": "queued",
        "queue_position": generation_queue.qsize(),
        "estimated_time": f"{generation_queue.qsize() * 4} seconds",
        "websocket_url": f"ws://localhost:{PORT}/ws/{job_id}"
    }

# WebSocket for real-time updates

@app.websocket("/ws/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time progress updates"""
    await websocket.accept()
    websocket_connections[job_id] = websocket

    try:
        while True:
            # Keep connection alive
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
    """Get job status with all details"""
    if job_id not in jobs_cache:
        # Try database
        job = await db_manager.get_job(job_id)
        if not job:
            raise HTTPException(404, f"Job {job_id} not found")
        return job

    return jobs_cache[job_id]

@app.get("/health")
async def health_check():
    """Health check with system status"""
    return {
        "status": "healthy",
        "model_preloaded": MODEL_PRELOADED,
        "queue_size": generation_queue.qsize(),
        "active_websockets": len(websocket_connections),
        "projects": len(projects),
        "characters": len(characters),
        "jobs_in_memory": len(jobs_cache)
    }

if __name__ == "__main__":
    uvicorn.run(
        "optimized_api:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info"
    )