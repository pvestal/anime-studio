#!/usr/bin/env python3
"""
Upload API Endpoints for Media Ingestion
Connects frontend to the ingestion system
"""

import os
import time
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import json
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor

# Import our ingestion systems
import sys
sys.path.append('/mnt/1TB-storage')
from media_ingestion_point import MediaIngestionPoint
from mario_galaxy_pipeline import MarioGalaxyPipeline
from echo_brain_integration import EchoBrainIntegration

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Media Upload API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize systems
ingestion = MediaIngestionPoint()
mario_pipeline = MarioGalaxyPipeline()
echo_integration = EchoBrainIntegration()

# Database configuration
DB_CONFIG = {
    'host': '192.168.50.135',
    'database': 'anime_production',
    'user': 'patrick',
    'password': 'RP78eIrW7cI2jYvL5akt1yurE'
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

@app.post("/api/upload/media")
async def upload_media(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    auto_process: bool = Form(True),
    settings: str = Form("{}")
):
    """Upload media file to ingestion point"""

    try:
        settings_dict = json.loads(settings)
    except:
        settings_dict = {}

    logger.info(f"📤 Uploading: {file.filename} (auto_process: {auto_process})")

    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in {'.mp4', '.avi', '.mov', '.mkv', '.jpg', '.jpeg', '.png', '.webp'}:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    # Save file to ingestion uploads
    upload_path = ingestion.ingestion_dir / file.filename

    # Handle filename conflicts
    counter = 1
    original_path = upload_path
    while upload_path.exists():
        stem = original_path.stem
        suffix = original_path.suffix
        upload_path = upload_path.parent / f"{stem}_{counter}{suffix}"
        counter += 1

    # Save uploaded file
    with open(upload_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)

    logger.info(f"✅ Saved to: {upload_path}")

    # Analyze immediately
    analysis = ingestion.analyze_media_file(upload_path)

    # Store upload record in database
    upload_record = await store_upload_record({
        "filename": upload_path.name,
        "original_filename": file.filename,
        "file_path": str(upload_path),
        "file_size": len(content),
        "file_type": analysis.get("type"),
        "analysis": analysis,
        "settings": settings_dict,
        "auto_process": auto_process
    })

    # Trigger background processing if enabled
    if auto_process:
        background_tasks.add_task(
            process_upload_background,
            str(upload_path),
            upload_record["id"],
            settings_dict
        )

    return {
        "success": True,
        "upload_id": upload_record["id"],
        "filename": upload_path.name,
        "analysis": analysis,
        "auto_processing": auto_process
    }

async def store_upload_record(upload_data: Dict[str, Any]) -> Dict[str, Any]:
    """Store upload record in database"""

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO uploaded_media (
            filename, original_filename, file_path, file_size,
            file_type, analysis, settings, auto_process,
            upload_timestamp, status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        upload_data["filename"],
        upload_data["original_filename"],
        upload_data["file_path"],
        upload_data["file_size"],
        upload_data["file_type"],
        json.dumps(upload_data["analysis"]),
        json.dumps(upload_data["settings"]),
        upload_data["auto_process"],
        time.time(),
        "uploaded"
    ))

    upload_id = cursor.fetchone()["id"]
    conn.commit()
    conn.close()

    return {"id": upload_id, **upload_data}

async def process_upload_background(file_path: str, upload_id: int, settings: Dict[str, Any]):
    """Background processing of uploaded file"""

    try:
        logger.info(f"🔄 Processing upload {upload_id}: {file_path}")

        # Update status
        await update_upload_status(upload_id, "processing", "Analyzing content...")

        # Process with Echo Brain integration
        await echo_integration.process_upload(file_path)

        # Character-specific processing
        file_path_obj = Path(file_path)
        analysis = ingestion.analyze_media_file(file_path_obj)

        characters_detected = []
        images_generated = 0

        # Enhanced character detection
        if analysis.get("type") == "video":
            characters_detected = await detect_characters_enhanced(analysis)

            # Auto-generate if characters found and enabled
            if characters_detected and settings.get("enabled", True):
                images_generated = await auto_generate_characters(characters_detected, settings)

        # Update final status
        await update_upload_status(upload_id, "completed", f"Generated {images_generated} images", {
            "characters_detected": characters_detected,
            "images_generated": images_generated,
            "processing_complete": True
        })

        logger.info(f"✅ Processing complete: {upload_id}")

    except Exception as e:
        logger.error(f"❌ Processing failed {upload_id}: {e}")
        await update_upload_status(upload_id, "error", str(e))

async def detect_characters_enhanced(analysis: Dict[str, Any]) -> List[str]:
    """Enhanced character detection using color analysis"""

    characters = []
    sample_frames = analysis.get("metadata", {}).get("sample_frames", [])

    for frame_data in sample_frames:
        brightness = frame_data.get("brightness", 0)
        mean_bgr = frame_data.get("mean_bgr", [0, 0, 0])

        b, g, r = mean_bgr

        # Mario detection (red hat, blue overalls)
        if r > 100 and b > 80 and 70 < brightness < 160:
            characters.append("mario")

        # Bowser detection (dark scenes with fire colors)
        elif brightness < 70 and r > 80:
            characters.append("bowser")

        # Luigi detection (green dominant)
        elif g > r and g > b and b > 80:
            characters.append("luigi")

    return list(set(characters))  # Remove duplicates

async def auto_generate_characters(characters: List[str], settings: Dict[str, Any]) -> int:
    """Auto-generate images for detected characters"""

    images_generated = 0
    style = settings.get("style", "movie_realistic")

    scenes = [
        "space adventure with star power",
        "heroic action scene",
        "dramatic battle scene",
        "peaceful exploration scene",
        "power-up transformation"
    ]

    for character in characters:
        for scene in scenes[:2]:  # Generate 2 images per character
            try:
                image_path = await mario_pipeline.generate_character_image(
                    character.title(), scene, style
                )

                if image_path:
                    images_generated += 1
                    logger.info(f"✅ Generated: {character} - {scene}")

            except Exception as e:
                logger.error(f"❌ Generation failed {character}: {e}")

    return images_generated

async def update_upload_status(upload_id: int, status: str, message: str = "", metadata: Dict = None):
    """Update upload processing status"""

    conn = get_db_connection()
    cursor = conn.cursor()

    update_data = {
        "status": status,
        "status_message": message,
        "updated_timestamp": time.time()
    }

    if metadata:
        update_data["processing_metadata"] = json.dumps(metadata)

    cursor.execute("""
        UPDATE uploaded_media
        SET status = %s, status_message = %s, updated_timestamp = %s,
            processing_metadata = COALESCE(%s, processing_metadata)
        WHERE id = %s
    """, (status, message, update_data["updated_timestamp"],
          update_data.get("processing_metadata"), upload_id))

    conn.commit()
    conn.close()

@app.get("/api/uploads/recent")
async def get_recent_uploads(limit: int = 12):
    """Get recent uploads with processing status"""

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, filename, original_filename, file_size, file_type,
               analysis, status, status_message, processing_metadata,
               upload_timestamp, updated_timestamp
        FROM uploaded_media
        ORDER BY upload_timestamp DESC
        LIMIT %s
    """, (limit,))

    uploads = []
    for row in cursor.fetchall():
        upload = dict(row)

        # Parse JSON fields
        upload["analysis"] = json.loads(upload["analysis"]) if upload["analysis"] else {}
        upload["processing_metadata"] = json.loads(upload["processing_metadata"]) if upload["processing_metadata"] else {}

        # Add convenience fields
        upload["characters"] = upload["processing_metadata"].get("characters_detected", [])
        upload["auto_generated"] = upload["processing_metadata"].get("images_generated", 0) > 0
        upload["loras_trained"] = False  # TODO: Check LoRA status

        # Metadata shortcuts
        metadata = upload["analysis"].get("metadata", {})
        upload["metadata"] = {
            "duration": metadata.get("duration"),
            "resolution": metadata.get("resolution", "unknown"),
            "fps": metadata.get("fps")
        }

        uploads.append(upload)

    conn.close()

    return {"uploads": uploads}

@app.get("/api/uploads/thumbnail/{upload_id}")
async def get_upload_thumbnail(upload_id: int):
    """Get thumbnail for uploaded media"""

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT file_path, file_type FROM uploaded_media WHERE id = %s
    """, (upload_id,))

    result = cursor.fetchone()
    conn.close()

    if not result:
        raise HTTPException(status_code=404, detail="Upload not found")

    file_path = Path(result["file_path"])

    if result["file_type"] == "image" and file_path.exists():
        return FileResponse(str(file_path))
    else:
        # Return placeholder or generate video thumbnail
        placeholder_path = "/opt/anime-studio/frontend/src/assets/video-placeholder.png"
        if Path(placeholder_path).exists():
            return FileResponse(placeholder_path)
        else:
            raise HTTPException(status_code=404, detail="Thumbnail not available")

@app.post("/api/process/auto-generate")
async def trigger_auto_generate(request: Dict[str, Any]):
    """Manually trigger auto-generation for uploaded file"""

    filename = request.get("filename")
    settings = request.get("settings", {})

    if not filename:
        raise HTTPException(status_code=400, detail="Filename required")

    # Find upload record
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, file_path, analysis FROM uploaded_media
        WHERE filename = %s OR original_filename = %s
        ORDER BY upload_timestamp DESC LIMIT 1
    """, (filename, filename))

    result = cursor.fetchone()
    conn.close()

    if not result:
        raise HTTPException(status_code=404, detail="Upload not found")

    # Trigger processing
    analysis = json.loads(result["analysis"]) if result["analysis"] else {}
    characters = await detect_characters_enhanced(analysis)
    images_generated = 0

    if characters:
        images_generated = await auto_generate_characters(characters, settings)

    return {
        "success": True,
        "upload_id": result["id"],
        "characters_detected": characters,
        "images_created": images_generated
    }

@app.get("/api/ingestion/status")
async def get_ingestion_status():
    """Get current ingestion system status"""

    # Count pending uploads
    pending_uploads = len(list(ingestion.ingestion_dir.glob("*")))

    # Count recent processed files
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
               SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
               SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors
        FROM uploaded_media
        WHERE upload_timestamp > %s
    """, (time.time() - 86400,))  # Last 24 hours

    stats = cursor.fetchone()
    conn.close()

    return {
        "status": "operational",
        "pending_uploads": pending_uploads,
        "stats_24h": dict(stats) if stats else {},
        "ingestion_dir": str(ingestion.ingestion_dir),
        "echo_brain_connected": True,  # TODO: Check actual connection
        "mario_pipeline_ready": len(mario_pipeline.character_loras) > 0
    }

if __name__ == "__main__":
    import uvicorn

    # Create database table if not exists
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS uploaded_media (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(255) NOT NULL,
            original_filename VARCHAR(255),
            file_path TEXT NOT NULL,
            file_size BIGINT,
            file_type VARCHAR(50),
            analysis JSONB,
            settings JSONB,
            auto_process BOOLEAN DEFAULT TRUE,
            upload_timestamp DOUBLE PRECISION,
            updated_timestamp DOUBLE PRECISION,
            status VARCHAR(50) DEFAULT 'uploaded',
            status_message TEXT,
            processing_metadata JSONB
        )
    """)

    conn.commit()
    conn.close()

    logger.info("🚀 Starting Media Upload API on port 8090")
    uvicorn.run(app, host="0.0.0.0", port=8090)