#!/usr/bin/env python3
import shutil

"""Tower Anime Production Service - Main API"""

import asyncio
import json
import os
import sqlite3
import time
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Tower Anime Production", version="2.0")

DATABASE_PATH = "/opt/tower-anime-production/database/anime.db"
FRAMES_DIR = "/opt/tower-anime-production/frames"
VIDEOS_DIR = "/opt/tower-anime-production/videos"
COMFYUI_URL = "http://localhost:8188"


class CharacterModel(BaseModel):
    name: str
    description: str
    design_prompt: str
    voice_id: Optional[str] = None


class SceneModel(BaseModel):
    description: str
    duration_seconds: float = 3.0
    characters: List[str] = []


class ProjectCreateModel(BaseModel):
    name: str
    description: str
    characters: List[CharacterModel]
    scenes: List[SceneModel]
    style: str = "anime"


class ProjectResponse(BaseModel):
    id: int
    name: str
    status: str
    created_at: str
    frames_dir: Optional[str]
    video_path: Optional[str]


def get_db():
    """Get database connection"""
    return sqlite3.connect(DATABASE_PATH)


@app.post("/api/projects", response_model=ProjectResponse)
async def create_project(project: ProjectCreateModel):
    """Create a new anime project with persistence"""

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Create project
        timestamp = int(time.time())
        frames_dir = f"{FRAMES_DIR}/project_{timestamp}"
        os.makedirs(frames_dir, exist_ok=True)

        cursor.execute(
            """
            INSERT INTO projects (name, description, style, frames_dir, status)
            VALUES (?, ?, ?, ?, 'created')
        """,
            (project.name, project.description, project.style, frames_dir),
        )

        project_id = cursor.lastrowid

        # Add characters
        for char in project.characters:
            cursor.execute(
                """
                INSERT INTO characters (project_id, name, description, design_prompt, voice_id)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    project_id,
                    char.name,
                    char.description,
                    char.design_prompt,
                    char.voice_id,
                ),
            )

        # Add scenes
        for i, scene in enumerate(project.scenes):
            workflow = generate_comfyui_workflow(
                scene.description, project.style)
            cursor.execute(
                """
                INSERT INTO scenes (project_id, scene_number, description, duration_seconds, workflow_json)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    project_id,
                    i + 1,
                    scene.description,
                    scene.duration_seconds,
                    json.dumps(workflow),
                ),
            )

        conn.commit()

        # Get created project
        cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        proj = cursor.fetchone()

        return ProjectResponse(
            id=proj[0],
            name=proj[1],
            status=proj[4],
            created_at=proj[7],
            frames_dir=proj[5],
            video_path=proj[6],
        )

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/projects")
async def list_projects():
    """List all anime projects"""

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, status, created_at, video_path 
        FROM projects 
        ORDER BY created_at DESC
    """
    )

    projects = []
    for row in cursor.fetchall():
        projects.append(
            {
                "id": row[0],
                "name": row[1],
                "status": row[2],
                "created_at": row[3],
                "video_path": row[4],
            }
        )

    conn.close()
    return projects


@app.post("/api/projects/{project_id}/generate")
async def generate_anime(project_id: int, background_tasks: BackgroundTasks):
    """Generate anime for a project"""

    conn = get_db()
    cursor = conn.cursor()

    # Check project exists
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    project = cursor.fetchone()

    if not project:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")

    # Create generation job
    cursor.execute(
        """
        INSERT INTO generation_jobs (project_id, job_type, status)
        VALUES (?, 'full_video', 'queued')
    """,
        (project_id,),
    )

    job_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Start generation in background
    background_tasks.add_task(generate_anime_task, project_id, job_id)

    return {"job_id": job_id, "status": "started"}


async def generate_anime_task(project_id: int, job_id: int):
    """Background task to generate anime"""

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Update job status
        cursor.execute(
            "UPDATE generation_jobs SET status = 'running', started_at = ? WHERE id = ?",
            (datetime.now(), job_id),
        )
        conn.commit()

        # Get scenes
        cursor.execute(
            "SELECT * FROM scenes WHERE project_id = ? ORDER BY scene_number",
            (project_id,),
        )
        scenes = cursor.fetchall()

        # Generate frames for each scene
        all_frames = []
        for scene in scenes:
            scene_id = scene[0]
            workflow = json.loads(scene[6])

            # Call ComfyUI
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{COMFYUI_URL}/prompt", json={"prompt": workflow}
                )

                if response.status_code == 200:
                    # Simulate frame generation (in reality, poll for completion)
                    frame_path = (
                        f"{FRAMES_DIR}/project_{project_id}/scene_{scene_id}_frame.png"
                    )

                    # Save frame record
                    cursor.execute(
                        """
                        INSERT INTO frames (scene_id, frame_number, file_path, prompt_used)
                        VALUES (?, 1, ?, ?)
                    """,
                        (scene_id, frame_path, scene[3]),
                    )

                    all_frames.append(frame_path)

        # Create video from frames
        video_path = f"{VIDEOS_DIR}/project_{project_id}.mp4"
        # In reality, use FFmpeg here

        # Update project
        cursor.execute(
            "UPDATE projects SET status = 'completed', video_path = ? WHERE id = ?",
            (video_path, project_id),
        )

        # Update job
        cursor.execute(
            "UPDATE generation_jobs SET status = 'completed', completed_at = ?, result_path = ? WHERE id = ?",
            (datetime.now(), video_path, job_id),
        )

        conn.commit()

    except Exception as e:
        cursor.execute(
            "UPDATE generation_jobs SET status = 'failed', error_message = ? WHERE id = ?",
            (str(e), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def generate_comfyui_workflow(description: str, style: str):
    """Generate ComfyUI workflow for a scene"""

    return {
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": f"{style} style, {description}, high quality, detailed",
                "clip": ["4", 1],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "anything-v5.safetensors"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 768, "height": 512, "batch_size": 1},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(time.time()),
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["3", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "bad quality, blurry, ugly", "clip": ["4", 1]},
        },
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "tower-anime-production",
        "database": os.path.exists(DATABASE_PATH),
        "comfyui": await check_comfyui(),
    }


async def check_comfyui():
    """Check if ComfyUI is accessible"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{COMFYUI_URL}/", timeout=2)
            return response.status_code == 200
    except:
        return False


if __name__ == "__main__":
    import uvicorn

    print("🎌 Starting Tower Anime Production Service on port 8328")
    uvicorn.run(app, host="0.0.0.0", port=8328)


async def wait_for_comfyui_completion(
    client, prompt_id: str, project_id: int, scene_id: int, max_wait: int = 300
):
    """Wait for ComfyUI to complete generation and return frame path"""

    start_time = time.time()
    frame_path = f"{FRAMES_DIR}/project_{project_id}/scene_{scene_id}_frame.png"

    while time.time() - start_time < max_wait:
        try:
            # Check queue status
            response = await client.get(f"{COMFYUI_URL}/api/queue")
            if response.status_code == 200:
                queue_data = response.json()

                # Check if our prompt is still in queue
                running = queue_data.get("queue_running", [])
                pending = queue_data.get("queue_pending", [])

                # Look for our prompt_id
                still_processing = False
                for item in running + pending:
                    if len(item) >= 2 and item[1] == prompt_id:
                        still_processing = True
                        break

                if not still_processing:
                    # Check if output file exists
                    output_response = await client.get(
                        f"{COMFYUI_URL}/api/history/{prompt_id}"
                    )
                    if output_response.status_code == 200:
                        history = output_response.json()
                        if prompt_id in history:
                            # Extract output file path from history
                            outputs = history[prompt_id].get("outputs", {})
                            for node_id, node_outputs in outputs.items():
                                if "images" in node_outputs:
                                    for img_info in node_outputs["images"]:
                                        # Copy from ComfyUI output to our frames directory
                                        src_path = f"/home/patrick/Projects/ComfyUI-Working/output/{img_info['filename']}"
                                        if os.path.exists(src_path):
                                            os.makedirs(
                                                os.path.dirname(frame_path),
                                                exist_ok=True,
                                            )
                                            shutil.copy2(src_path, frame_path)
                                            return frame_path

                            # If no images found, still return path for placeholder
                            return frame_path

            # Wait before next check
            await asyncio.sleep(2)

        except Exception as e:
            print(f"Error checking ComfyUI status: {e}")
            await asyncio.sleep(2)

    # Timeout reached
    return None


async def create_video_from_frames(frame_paths: list, output_path: str):
    """Create video from frame images using FFmpeg"""

    if not frame_paths:
        return False

    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Create temporary file list for ffmpeg
        temp_list = f"/tmp/frames_{int(time.time())}.txt"
        with open(temp_list, "w") as f:
            for frame_path in frame_paths:
                if os.path.exists(frame_path):
                    # FFmpeg expects duration per frame
                    f.write(f"file '{frame_path}'\n")
                    f.write("duration 3.0\n")

        # Use FFmpeg to create video
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            temp_list,
            "-vf",
            "scale=768:512",
            "-c:v",
            "libx264",
            "-r",
            "1",  # 1 FPS since each frame should show for 3 seconds
            "-pix_fmt",
            "yuv420p",
            output_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        # Clean up temp file
        if os.path.exists(temp_list):
            os.remove(temp_list)

        return process.returncode == 0

    except Exception as e:
        print(f"Error creating video: {e}")
        return False
