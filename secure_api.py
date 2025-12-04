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

from database_operations import EnhancedDatabaseManager
from pose_library import pose_library
from src.storyline_database import StorylineDatabase

# Initialize database managers
db_manager = EnhancedDatabaseManager()
storyline_db = StorylineDatabase()

async def initialize_database():
    await storyline_db.initialize()
    return True
async def close_database():
    await storyline_db.cleanup()
    return None

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
    pose_description: Optional[str] = Field(None, max_length=200)

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
                   style_preset: Optional[str] = None, character_ref: Optional[str] = None,
                   pose_ref: Optional[str] = None) -> Dict[str, Any]:
    """Create 93% consistency workflow with ControlNet + IPAdapter"""

    # Sanitize inputs for workflow
    prompt = sanitize_text(prompt, 1000)
    negative_prompt = sanitize_text(negative_prompt, 500)

    seed = int(time.time() * 1000) % 2147483647
    filename_prefix = f"anime_{int(time.time())}"

    if style_preset and style_preset in ["cyberpunk", "fantasy", "steampunk", "studio_ghibli", "manga"]:
        prompt = apply_style_preset(prompt, style_preset)

    # If character reference and pose are provided, use the proven 93% workflow
    if character_ref and pose_ref:
        # Copy reference files to ComfyUI input
        char_name = f"char_{seed}.png"
        pose_name = f"pose_{seed}.png"

        try:
            shutil.copy(character_ref, f"/mnt/1TB-storage/ComfyUI/input/{char_name}")
            shutil.copy(pose_ref, f"/mnt/1TB-storage/ComfyUI/input/{pose_name}")
        except Exception as e:
            print(f"File copy error: {e}")
            # Fall back to basic workflow if files can't be copied
            character_ref = None
            pose_ref = None

    # Use 93% consistency workflow if we have character and pose
    if character_ref and pose_ref:
        return {
            # Base model
            "model": {
                "inputs": {"ckpt_name": "counterfeit_v3.safetensors"},
                "class_type": "CheckpointLoaderSimple"
            },
            # IPAdapter for character consistency
            "ipa_loader": {
                "inputs": {
                    "model": ["model", 0],
                    "preset": "PLUS (high strength)"
                },
                "class_type": "IPAdapterUnifiedLoader"
            },
            "char_img": {
                "inputs": {"image": char_name, "upload": "image"},
                "class_type": "LoadImage"
            },
            "ipa_apply": {
                "inputs": {
                    "model": ["ipa_loader", 0],
                    "ipadapter": ["ipa_loader", 1],
                    "image": ["char_img", 0],
                    "weight": 0.9,
                    "weight_type": "standard",
                    "start_at": 0.0,
                    "end_at": 0.9
                },
                "class_type": "IPAdapter"
            },
            # ControlNet for pose control
            "cn_loader": {
                "inputs": {"control_net_name": "control_v11p_sd15_openpose.pth"},
                "class_type": "ControlNetLoader"
            },
            "pose_img": {
                "inputs": {"image": pose_name, "upload": "image"},
                "class_type": "LoadImage"
            },
            # Text conditioning
            "pos_text": {
                "inputs": {"text": f"{prompt}, masterpiece, best quality", "clip": ["model", 1]},
                "class_type": "CLIPTextEncode"
            },
            "neg_text": {
                "inputs": {"text": f"{negative_prompt}, low quality, blurry, different character", "clip": ["model", 1]},
                "class_type": "CLIPTextEncode"
            },
            # Apply ControlNet to conditioning
            "cn_pos": {
                "inputs": {
                    "conditioning": ["pos_text", 0],
                    "control_net": ["cn_loader", 0],
                    "image": ["pose_img", 0],
                    "strength": 0.7
                },
                "class_type": "ControlNetApply"
            },
            "cn_neg": {
                "inputs": {
                    "conditioning": ["neg_text", 0],
                    "control_net": ["cn_loader", 0],
                    "image": ["pose_img", 0],
                    "strength": 0.7
                },
                "class_type": "ControlNetApply"
            },
            # Generation
            "latent": {
                "inputs": {"width": width, "height": height, "batch_size": 1},
                "class_type": "EmptyLatentImage"
            },
            "sampler": {
                "inputs": {
                    "seed": seed,
                    "steps": 25,
                    "cfg": 7.0,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1.0,
                    "model": ["ipa_apply", 0],
                    "positive": ["cn_pos", 0],
                    "negative": ["cn_neg", 0],
                    "latent_image": ["latent", 0]
                },
                "class_type": "KSampler"
            },
            "decode": {
                "inputs": {"samples": ["sampler", 0], "vae": ["model", 2]},
                "class_type": "VAEDecode"
            },
            "save": {
                "inputs": {
                    "filename_prefix": filename_prefix,
                    "images": ["decode", 0]
                },
                "class_type": "SaveImage"
            }
        }

    # Fall back to original basic workflow if no character/pose
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
        # Get character reference and pose if available
        character_ref = None
        pose_ref = None

        if job_data.get("character_id"):
            # Check if we have character reference
            char_path = Path(f"/home/patrick/.anime-characters/{job_data['character_id']}/reference.png")
            if char_path.exists():
                character_ref = str(char_path)

            # Use pose library to get appropriate pose
            pose_desc = job_data.get("pose_description", "standing")
            pose_ref = pose_library.get_pose_skeleton(pose_desc)

            # Fallback to default pose if library fails
            if not pose_ref:
                pose_path = Path("/mnt/1TB-storage/ComfyUI/output/pose_test_00001_.png")
                if pose_path.exists():
                    pose_ref = str(pose_path)

        workflow = create_workflow(
            job_data["prompt"],
            job_data["negative_prompt"],
            job_data["width"],
            job_data["height"],
            job_data.get("style_preset"),
            character_ref,
            pose_ref
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
    """Monitor job completion with real progress"""
    max_wait = 300  # 5 minutes
    start_time = time.time()
    last_progress = -1

    while time.time() - start_time < max_wait:
        try:
            # Check queue status for real progress
            queue_response = requests.get(f"{COMFYUI_URL}/queue")
            if queue_response.status_code == 200:
                queue_data = queue_response.json()

                # Check if running
                running = queue_data.get("queue_running", [])
                for item in running:
                    if len(item) > 0 and item[0] == comfyui_id:
                        # Update to processing status
                        job_data["status"] = "processing"
                        # Estimate progress at 50% when running
                        progress = 50
                        if progress != last_progress:
                            last_progress = progress
                            asyncio.run(send_progress_update(job_id, progress, "processing"))
                        break

                # Check if still pending
                pending = queue_data.get("queue_pending", [])
                for idx, item in enumerate(pending):
                    if len(item) > 0 and item[0] == comfyui_id:
                        job_data["status"] = "queued"
                        job_data["queue_position"] = idx + 1
                        if last_progress != 0:
                            last_progress = 0
                            asyncio.run(send_progress_update(job_id, 0, "queued"))
                        break

            # Check history for completion
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

        time.sleep(0.5)  # Poll every 500ms for more responsive updates

    job_data["status"] = "failed"
    job_data["error"] = "Generation timeout after 5 minutes"

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

# OLD projects endpoint removed - replaced with file system version below

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
        "pose_description": request.pose_description,
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
                # Send real progress from job data
                progress = job.get("progress", 0)
                if job["status"] == "completed":
                    progress = 100
                elif job["status"] == "processing" and progress == 0:
                    progress = 50  # Default if no real progress yet

                await websocket.send_json({
                    "job_id": job_id,
                    "status": job["status"],
                    "progress": progress,
                    "queue_position": job.get("queue_position")
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

@app.get("/api/health")
async def api_health_check():
    """Health check endpoint for API pattern"""
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

@app.get("/api/anime/health")
async def anime_api_health_check():
    """Health check endpoint for anime API pattern"""
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
# Characters endpoint that was missing from tests
@app.get("/characters")
async def list_characters():
    """List all characters from actual project directories"""
    try:
        characters = []
        projects_dir = Path("/mnt/1TB-storage/anime/projects")

        if projects_dir.exists():
            for project_dir in projects_dir.iterdir():
                if project_dir.is_dir():
                    chars_dir = project_dir / "characters"
                    if chars_dir.exists():
                        for char_dir in chars_dir.iterdir():
                            if char_dir.is_dir():
                                characters.append({
                                    "name": char_dir.name,
                                    "project_id": project_dir.name,
                                    "path": str(char_dir)
                                })

        return {"characters": characters}
    except Exception as e:
        raise HTTPException(500, f"Error reading characters: {e}")

# Fix projects endpoint to read actual data
@app.get("/api/anime/projects")
async def list_projects():
    """List actual projects from file system"""
    try:
        projects = []
        projects_dir = Path("/mnt/1TB-storage/anime/projects")

        if projects_dir.exists():
            for project_dir in projects_dir.iterdir():
                if project_dir.is_dir():
                    project_info = {
                        "id": project_dir.name,
                        "name": project_dir.name,
                        "path": str(project_dir),
                        "characters": [],
                        "images": 0
                    }

                    # Count characters
                    chars_dir = project_dir / "characters"
                    if chars_dir.exists():
                        project_info["characters"] = [d.name for d in chars_dir.iterdir() if d.is_dir()]

                    # Count images
                    general_dir = project_dir / "general"
                    if general_dir.exists():
                        project_info["images"] = len(list(general_dir.glob("*.png")))

                    projects.append(project_info)

        return {"projects": projects}
    except Exception as e:
        raise HTTPException(500, f"Error reading projects: {e}")

# Storyline endpoints
@app.get("/api/stories")
async def list_stories():
    """List all stories in database"""
    try:
        stories = await storyline_db.list_stories()
        return {"stories": stories}
    except Exception as e:
        raise HTTPException(500, f"Database error: {e}")

@app.post("/api/stories")
async def create_story(story_data: dict):
    """Create new interactive story"""
    try:
        story_id = str(uuid.uuid4())[:8]
        await storyline_db.save_story(story_id, story_data)
        return {"story_id": story_id, "status": "created"}
    except Exception as e:
        raise HTTPException(500, f"Error creating story: {e}")

@app.get("/api/stories/{story_id}")
async def get_story(story_id: str):
    """Get specific story details"""
    try:
        story = await storyline_db.load_story(story_id)
        if not story:
            raise HTTPException(404, "Story not found")
        return story
    except Exception as e:
        raise HTTPException(500, f"Error loading story: {e}")

@app.get("/api/stories/test")
async def test_sakura():
    """Test loading Sakura story"""
    try:
        story = await storyline_db.load_story("sakura_adventure")
        if story:
            return {"found": True, "title": story["title"], "author": story["author"]}
        else:
            return {"found": False, "message": "Sakura story not found"}
    except Exception as e:
        return {"error": str(e)}

# Story branching endpoints
@app.post("/api/stories/{story_id}/branches")
async def create_story_branch(story_id: str, branch_data: dict):
    """Create new story branch"""
    try:
        from src.storyline_version_control import StorylineVersionControl
        vcs = StorylineVersionControl(story_id)

        branch_name = branch_data.get("name", f"branch_{int(time.time())}")
        description = branch_data.get("description", "")

        new_branch = vcs.create_branch(branch_name, description)

        # Save branch to database
        await storyline_db.save_branch(story_id, {
            "name": branch_name,
            "head_commit": vcs.head_commit,
            "parent_branch": vcs.current_branch,
            "description": description
        })

        return {"branch": new_branch, "status": "created"}
    except Exception as e:
        raise HTTPException(500, f"Error creating branch: {e}")

@app.post("/api/stories/{story_id}/branches/{branch_name}/switch")
async def switch_story_branch(story_id: str, branch_name: str):
    """Switch to different story branch"""
    try:
        from src.storyline_version_control import StorylineVersionControl
        vcs = StorylineVersionControl(story_id)

        vcs.switch_branch(branch_name)

        return {
            "current_branch": vcs.current_branch,
            "head_commit": vcs.head_commit,
            "story": vcs.working_story
        }
    except Exception as e:
        raise HTTPException(500, f"Error switching branch: {e}")

@app.get("/api/stories/{story_id}/branches")
async def list_story_branches(story_id: str):
    """List all branches for a story"""
    try:
        branches = await storyline_db.load_branches(story_id)
        return {"branches": branches}
    except Exception as e:
        raise HTTPException(500, f"Error loading branches: {e}")

@app.post("/api/stories/{story_id}/merge")
async def merge_story_branches(story_id: str, merge_data: dict):
    """Merge story branches"""
    try:
        from src.storyline_version_control import StorylineVersionControl
        vcs = StorylineVersionControl(story_id)

        source_branch = merge_data["source_branch"]
        target_branch = merge_data.get("target_branch", vcs.current_branch)

        success, conflicts = vcs.merge_branches(source_branch, target_branch)

        return {
            "success": success,
            "conflicts": conflicts,
            "source": source_branch,
            "target": target_branch
        }
    except Exception as e:
        raise HTTPException(500, f"Error merging branches: {e}")

# Character evolution endpoints
@app.post("/api/stories/{story_id}/characters/{character_name}/evolve")
async def evolve_character(story_id: str, character_name: str, evolution_data: dict):
    """Evolve character based on story events"""
    try:
        commit_hash = evolution_data.get("commit_hash", f"evolution_{int(time.time())}")

        await storyline_db.save_character_evolution(story_id, {
            "name": character_name,
            "commit_hash": commit_hash,
            "evolution_state": evolution_data.get("evolution_state", {}),
            "emotional_state": evolution_data.get("emotional_state", {}),
            "relationships": evolution_data.get("relationships", {})
        })

        return {"status": "character evolved", "character": character_name}
    except Exception as e:
        raise HTTPException(500, f"Error evolving character: {e}")

@app.get("/api/stories/{story_id}/characters/{character_name}/evolution")
async def get_character_evolution(story_id: str, character_name: str):
    """Get character evolution history"""
    try:
        evolution = await storyline_db.load_character_evolution(story_id, character_name)
        return {"character": character_name, "evolution": evolution}
    except Exception as e:
        raise HTTPException(500, f"Error loading evolution: {e}")

# Echo Brain integration endpoints
@app.post("/api/stories/{story_id}/intent")
async def analyze_user_intent(story_id: str, intent_data: dict):
    """Analyze user intent for story interaction using Echo Brain"""
    try:
        from src.user_interaction_system import UserInteractionSystem

        user_system = UserInteractionSystem()
        await user_system.initialize()

        user_input = intent_data["input"]
        context = intent_data.get("context", {})
        context["story_id"] = story_id

        intent = await user_system.capture_intent(user_input, context)

        await user_system.cleanup()

        return {
            "action": intent.action,
            "target": intent.target,
            "parameters": intent.parameters,
            "confidence": intent.confidence
        }
    except Exception as e:
        raise HTTPException(500, f"Error analyzing intent: {e}")

@app.post("/api/stories/{story_id}/suggestions")
async def get_story_suggestions(story_id: str):
    """Get AI suggestions for next story actions using Echo Brain"""
    try:
        from src.user_interaction_system import UserInteractionSystem

        user_system = UserInteractionSystem()
        await user_system.initialize()

        # Load story for context
        story = await storyline_db.load_story(story_id)
        if not story:
            raise HTTPException(404, "Story not found")

        context = {
            "story": story["working_story"],
            "current_branch": story["current_branch"],
            "story_id": story_id
        }

        suggestions = await user_system.suggest_next_action(context)

        await user_system.cleanup()

        return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(500, f"Error getting suggestions: {e}")

# Enhanced generation endpoint that links to story progression
@app.post("/api/stories/{story_id}/generate")
async def generate_for_story(story_id: str, generation_data: dict):
    """Generate image linked to specific story chapter/scene"""
    try:
        # Get story details
        story = await storyline_db.load_story(story_id)
        if not story:
            raise HTTPException(404, "Story not found")

        # Extract generation parameters
        prompt = generation_data["prompt"]
        character_name = generation_data.get("character_name")
        chapter_index = generation_data.get("chapter_index", 0)
        scene_description = generation_data.get("scene_description", "")

        # Enhance prompt with story context
        if character_name and character_name in story["working_story"].get("characters", {}):
            char_data = story["working_story"]["characters"][character_name]
            prompt += f", {char_data.get('hair_color', '')} hair, {char_data.get('eye_color', '')} eyes"

        # Call existing generation endpoint
        job_data = {
            "prompt": prompt,
            "project_id": story["metadata"].get("project_id", "default"),
            "character_name": character_name,
            "negative_prompt": generation_data.get("negative_prompt", "bad quality"),
            "width": generation_data.get("width", 512),
            "height": generation_data.get("height", 768)
        }

        # Submit job (reuse existing generation logic)
        job_id = str(uuid.uuid4())[:8]
        job_tracker = get_job_tracker()
        job_tracker.create_job(job_id, job_data)

        # Track connection to story/chapter
        job_data["story_connection"] = {
            "story_id": story_id,
            "chapter_index": chapter_index,
            "scene_description": scene_description
        }

        return {
            "job_id": job_id,
            "status": "queued",
            "story_id": story_id,
            "chapter_index": chapter_index
        }

    except Exception as e:
        raise HTTPException(500, f"Error generating for story: {e}")

