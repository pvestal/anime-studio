#!/usr/bin/env python3
"""
Unified Anime Generation FastAPI - Using 93% Consistency Core
Complementary web interface to CLI tool
"""

import json
import uuid
from typing import List, Optional
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn

# Import the unified core system
from anime_generation_core import anime_core

# Configuration
PORT = 8330  # New port to avoid conflicts
OUTPUT_DIR = Path("/home/patrick/anime-output")

# FastAPI app
app = FastAPI(
    title="Unified Anime Generation API",
    description="Web interface for the proven 93% consistency anime generation system",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class GenerationRequest(BaseModel):
    character_name: str
    pose_description: str
    prompt_extra: Optional[str] = ""
    variations: Optional[int] = 1

class CharacterRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    reference_image_path: str

class GenerationResponse(BaseModel):
    success: bool
    job_id: str
    message: str
    output_files: List[str] = []
    errors: List[str] = []

class CharacterInfo(BaseModel):
    name: str
    description: str
    reference_path: str
    created: str

# In-memory job tracking
active_jobs = {}

def background_generation(job_id: str, character_name: str, pose: str,
                         prompt_extra: str = "", variations: int = 1):
    """Background task for generation"""
    try:
        active_jobs[job_id] = {
            "status": "running",
            "progress": "Starting generation...",
            "started_at": datetime.now().isoformat(),
            "character": character_name,
            "pose": pose,
            "variations": variations
        }

        # Use the unified core
        results = anime_core.generate_character_variations(
            character_name, pose, prompt_extra, variations
        )

        output_files = []
        errors = []

        for result in results:
            if result["success"]:
                output_files.append(result["organized_output"])
            else:
                errors.append(result["error"])

        active_jobs[job_id] = {
            "status": "completed" if output_files else "failed",
            "progress": f"Generated {len(output_files)}/{variations} images",
            "started_at": active_jobs[job_id]["started_at"],
            "completed_at": datetime.now().isoformat(),
            "output_files": output_files,
            "errors": errors,
            "character": character_name,
            "pose": pose,
            "variations": variations
        }

    except Exception as e:
        active_jobs[job_id] = {
            "status": "failed",
            "progress": f"Error: {str(e)}",
            "started_at": active_jobs[job_id]["started_at"],
            "completed_at": datetime.now().isoformat(),
            "errors": [str(e)],
            "character": character_name,
            "pose": pose,
            "variations": variations
        }

# API Endpoints
@app.get("/")
async def home():
    """Simple web interface"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Unified Anime Generation</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 800px; }
            .character {
                border: 1px solid #ddd;
                padding: 15px;
                margin: 10px 0;
                border-radius: 5px;
            }
            input, select, textarea {
                width: 300px;
                padding: 5px;
                margin: 5px 0;
            }
            button {
                background: #007bff;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 3px;
                cursor: pointer;
            }
            .output {
                background: #f8f9fa;
                padding: 15px;
                margin: 10px 0;
                border-radius: 5px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎨 Unified Anime Generation</h1>
            <p>Web interface for the 93% consistency anime generation system</p>

            <h2>Generate Images</h2>
            <form onsubmit="generateImage(event)">
                <div>
                    <label>Character:</label><br>
                    <select id="character_name" required>
                        <option value="">Loading...</option>
                    </select>
                </div>
                <div>
                    <label>Pose Description:</label><br>
                    <input type="text" id="pose_description" placeholder="sitting, standing, dancing..." required>
                </div>
                <div>
                    <label>Extra Prompt:</label><br>
                    <input type="text" id="prompt_extra" placeholder="in garden, at school...">
                </div>
                <div>
                    <label>Variations:</label><br>
                    <input type="number" id="variations" value="1" min="1" max="10">
                </div>
                <button type="submit">Generate</button>
            </form>

            <div id="output" class="output" style="display:none;">
                <h3>Generation Status</h3>
                <div id="status"></div>
            </div>
        </div>

        <script>
            // Load characters
            fetch('/api/characters')
                .then(r => r.json())
                .then(chars => {
                    const select = document.getElementById('character_name');
                    select.innerHTML = '<option value="">Select character...</option>';
                    chars.forEach(char => {
                        select.innerHTML += `<option value="${char}">${char}</option>`;
                    });
                });

            function generateImage(event) {
                event.preventDefault();

                const data = {
                    character_name: document.getElementById('character_name').value,
                    pose_description: document.getElementById('pose_description').value,
                    prompt_extra: document.getElementById('prompt_extra').value,
                    variations: parseInt(document.getElementById('variations').value)
                };

                document.getElementById('output').style.display = 'block';
                document.getElementById('status').innerHTML = 'Starting generation...';

                fetch('/api/generate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                })
                .then(r => r.json())
                .then(result => {
                    if (result.success) {
                        checkStatus(result.job_id);
                    } else {
                        document.getElementById('status').innerHTML = `Error: ${result.message}`;
                    }
                })
                .catch(e => {
                    document.getElementById('status').innerHTML = `Error: ${e.message}`;
                });
            }

            function checkStatus(jobId) {
                fetch(`/api/jobs/${jobId}`)
                    .then(r => r.json())
                    .then(job => {
                        document.getElementById('status').innerHTML = `
                            <strong>Status:</strong> ${job.status}<br>
                            <strong>Progress:</strong> ${job.progress}<br>
                            ${job.output_files ? `<strong>Files:</strong> ${job.output_files.length} generated` : ''}
                        `;

                        if (job.status === 'running') {
                            setTimeout(() => checkStatus(jobId), 2000);
                        }
                    });
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.get("/api/health")
async def health():
    """Health check"""
    return {"status": "healthy", "core_available": True, "timestamp": datetime.now().isoformat()}

@app.get("/api/characters")
async def list_characters():
    """List available characters"""
    try:
        characters = anime_core.list_characters()
        return characters
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/characters/{character_name}")
async def get_character_info(character_name: str):
    """Get character information"""
    try:
        char_info = anime_core.get_character_info(character_name)
        if not char_info:
            raise HTTPException(status_code=404, detail="Character not found")
        return CharacterInfo(
            name=char_info["name"],
            description=char_info["metadata"].get("description", ""),
            reference_path=char_info["reference"],
            created=char_info["metadata"].get("created", "")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/characters")
async def add_character(character: CharacterRequest):
    """Add a new character"""
    try:
        result = anime_core.add_character(character.name, character.reference_image_path, character.description)
        return {"success": True, "message": f"Character '{character.name}' added successfully", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/generate")
async def generate_anime(request: GenerationRequest, background_tasks: BackgroundTasks):
    """Start anime generation (background task)"""
    try:
        # Validate character exists
        if request.character_name not in anime_core.list_characters():
            raise HTTPException(status_code=400, detail=f"Character '{request.character_name}' not found")

        # Validate pose skeleton exists
        pose_ref = anime_core.get_pose_skeleton(request.pose_description)
        if not pose_ref:
            raise HTTPException(status_code=400, detail="Could not generate pose skeleton")

        # Create job
        job_id = str(uuid.uuid4())

        # Start background task
        background_tasks.add_task(
            background_generation,
            job_id, request.character_name, request.pose_description,
            request.prompt_extra, request.variations
        )

        return GenerationResponse(
            success=True,
            job_id=job_id,
            message=f"Generation started for {request.character_name}",
            output_files=[]
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get generation job status"""
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    return active_jobs[job_id]

@app.get("/api/jobs")
async def list_jobs():
    """List all jobs"""
    return active_jobs

@app.get("/api/output/{file_path:path}")
async def get_output_file(file_path: str):
    """Serve generated images"""
    full_path = OUTPUT_DIR / file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path)

@app.get("/api/gallery")
async def get_gallery():
    """Get recent generated images"""
    try:
        # Get today's folder
        today = datetime.now().strftime("%Y-%m-%d")
        today_dir = OUTPUT_DIR / today

        if not today_dir.exists():
            return {"images": []}

        images = []
        for img_file in today_dir.glob("*.png"):
            images.append({
                "filename": img_file.name,
                "path": f"/api/output/{today}/{img_file.name}",
                "created": datetime.fromtimestamp(img_file.stat().st_mtime).isoformat()
            })

        # Sort by creation time (newest first)
        images.sort(key=lambda x: x["created"], reverse=True)

        return {"images": images[:20]}  # Return last 20 images

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    print(f"🚀 Starting Unified Anime Generation API on port {PORT}")
    print(f"   CLI available at: /opt/tower-anime-production/anime-gen")
    print(f"   Web interface: http://localhost:{PORT}/")
    print(f"   API docs: http://localhost:{PORT}/docs")
    uvicorn.run(app, host="0.0.0.0", port=PORT)