#!/usr/bin/env python3
"""
LoRA Training API Service
RESTful API for managing character LoRA training operations
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.append('/opt/anime-studio')
from lora_training_pipeline import LoRATrainingPipeline

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="LoRA Training API",
    description="API for managing character LoRA training operations",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'anime_production',
    'user': 'patrick',
    'password': 'RP78eIrW7cI2jYvL5akt1yurE',
    'port': 5432
}

# Global training pipeline instance
training_pipeline = LoRATrainingPipeline()

# Pydantic models
class TrainingJobResponse(BaseModel):
    id: int
    character_id: int
    character_name: str
    target_asset_type: str
    status: str
    required_approvals: Optional[int] = None
    approved_images: Optional[int] = None
    generated_images: Optional[List[str]] = None
    training_script_path: Optional[str] = None
    trained_model_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class CharacterResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    design_prompt: Optional[str] = None
    has_lora: bool = False
    lora_path: Optional[str] = None
    training_status: Optional[str] = None

class TrainingRequest(BaseModel):
    character_id: int
    image_count: int = Field(default=20, ge=10, le=50)
    training_config: Optional[Dict[str, Any]] = None

class TrainingStatusResponse(BaseModel):
    character_id: int
    character_name: str
    status: str
    progress: Optional[str] = None
    error_message: Optional[str] = None
    estimated_completion: Optional[datetime] = None

# Database helper functions
def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(**DB_CONFIG)

async def get_character_info(character_id: int) -> Optional[Dict]:
    """Get character information from database"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT id, name, description, design_prompt
            FROM characters
            WHERE id = %s
        """, (character_id,))

        character = cursor.fetchone()
        return dict(character) if character else None
    finally:
        conn.close()

# API Endpoints

@app.get("/", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "LoRA Training API",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/characters", response_model=List[CharacterResponse], tags=["Characters"])
async def get_characters():
    """Get list of all characters with their LoRA training status"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT
                c.id,
                c.name,
                c.description,
                c.design_prompt,
                ctj.status as training_status,
                ctj.trained_model_path
            FROM characters c
            LEFT JOIN character_training_jobs ctj ON c.id = ctj.character_id
                AND ctj.target_asset_type = 'lora_v1'
            ORDER BY c.id
        """

        cursor.execute(query)
        characters = cursor.fetchall()

        result = []
        for char in characters:
            result.append(CharacterResponse(
                id=char['id'],
                name=char['name'] or f"Character {char['id']}",
                description=char['description'],
                design_prompt=char['design_prompt'],
                has_lora=bool(char['trained_model_path']),
                lora_path=char['trained_model_path'],
                training_status=char['training_status']
            ))

        return result

    finally:
        conn.close()

@app.get("/characters/untrained", response_model=List[CharacterResponse], tags=["Characters"])
async def get_untrained_characters():
    """Get characters that need LoRA training"""
    characters = await training_pipeline.get_characters_needing_training()

    result = []
    for char in characters:
        result.append(CharacterResponse(
            id=char['id'],
            name=char['name'],
            description=char['description'],
            design_prompt=char['design_prompt'],
            has_lora=False,
            training_status='needs_training'
        ))

    return result

@app.get("/training-jobs", response_model=List[TrainingJobResponse], tags=["Training Jobs"])
async def get_training_jobs():
    """Get all training jobs"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT
                ctj.*,
                c.name as character_name
            FROM character_training_jobs ctj
            JOIN characters c ON ctj.character_id = c.id
            ORDER BY ctj.created_at DESC
        """

        cursor.execute(query)
        jobs = cursor.fetchall()

        result = []
        for job in jobs:
            result.append(TrainingJobResponse(
                id=job['id'],
                character_id=job['character_id'],
                character_name=job['character_name'],
                target_asset_type=job['target_asset_type'],
                status=job['status'],
                required_approvals=job['required_approvals'],
                approved_images=job['approved_images'],
                generated_images=job['generated_images'],
                training_script_path=job['training_script_path'],
                trained_model_path=job['trained_model_path'],
                created_at=job['created_at'],
                updated_at=job['updated_at']
            ))

        return result

    finally:
        conn.close()

@app.get("/training-jobs/{character_id}", response_model=TrainingJobResponse, tags=["Training Jobs"])
async def get_training_job(character_id: int):
    """Get training job for specific character"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT
                ctj.*,
                c.name as character_name
            FROM character_training_jobs ctj
            JOIN characters c ON ctj.character_id = c.id
            WHERE ctj.character_id = %s
            ORDER BY ctj.created_at DESC
            LIMIT 1
        """

        cursor.execute(query, (character_id,))
        job = cursor.fetchone()

        if not job:
            raise HTTPException(status_code=404, detail="Training job not found")

        return TrainingJobResponse(
            id=job['id'],
            character_id=job['character_id'],
            character_name=job['character_name'],
            target_asset_type=job['target_asset_type'],
            status=job['status'],
            required_approvals=job['required_approvals'],
            approved_images=job['approved_images'],
            generated_images=job['generated_images'],
            training_script_path=job['training_script_path'],
            trained_model_path=job['trained_model_path'],
            created_at=job['created_at'],
            updated_at=job['updated_at']
        )

    finally:
        conn.close()

@app.post("/training/start/{character_id}", tags=["Training Operations"])
async def start_character_training(
    character_id: int,
    background_tasks: BackgroundTasks,
    request: Optional[TrainingRequest] = None
):
    """Start LoRA training for a specific character"""

    # Verify character exists
    character = await get_character_info(character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    # Check if training already in progress
    conn = get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT status FROM character_training_jobs
            WHERE character_id = %s AND status IN ('in_progress', 'completed')
            ORDER BY created_at DESC
            LIMIT 1
        """, (character_id,))

        existing_job = cursor.fetchone()
        if existing_job:
            if existing_job['status'] == 'in_progress':
                raise HTTPException(
                    status_code=400,
                    detail="Training already in progress for this character"
                )
            elif existing_job['status'] == 'completed':
                raise HTTPException(
                    status_code=400,
                    detail="Character already has completed training"
                )

    finally:
        conn.close()

    # Configure training parameters
    image_count = request.image_count if request else 20

    # Start training in background
    background_tasks.add_task(
        run_character_training,
        character_id,
        character['name'],
        character.get('design_prompt') or character.get('description', ''),
        image_count
    )

    return {
        "message": f"Training started for {character['name']}",
        "character_id": character_id,
        "character_name": character['name'],
        "image_count": image_count,
        "status": "started"
    }

@app.post("/training/start-all", tags=["Training Operations"])
async def start_training_all_characters(background_tasks: BackgroundTasks):
    """Start LoRA training for all characters that need it"""

    characters = await training_pipeline.get_characters_needing_training()

    if not characters:
        return {
            "message": "No characters need training",
            "characters_queued": 0
        }

    # Start batch training in background
    background_tasks.add_task(run_batch_training)

    return {
        "message": f"Batch training started for {len(characters)} characters",
        "characters_queued": len(characters),
        "characters": [char['name'] for char in characters]
    }

@app.get("/training/status/{character_id}", response_model=TrainingStatusResponse, tags=["Training Operations"])
async def get_training_status(character_id: int):
    """Get training status for specific character"""

    character = await get_character_info(character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    conn = get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT status, created_at, updated_at
            FROM character_training_jobs
            WHERE character_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (character_id,))

        job = cursor.fetchone()

        if not job:
            status = "not_started"
            progress = None
        else:
            status = job['status']
            if status == 'in_progress':
                # Calculate estimated progress based on time elapsed
                elapsed = datetime.now() - job['updated_at']
                progress = f"Training in progress ({elapsed.seconds // 60} minutes elapsed)"
            else:
                progress = f"Status: {status}"

        return TrainingStatusResponse(
            character_id=character_id,
            character_name=character['name'],
            status=status,
            progress=progress
        )

    finally:
        conn.close()

@app.delete("/training/cancel/{character_id}", tags=["Training Operations"])
async def cancel_training(character_id: int):
    """Cancel ongoing training for character"""

    character = await get_character_info(character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    # Update status to cancelled
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE character_training_jobs
            SET status = 'cancelled', updated_at = %s
            WHERE character_id = %s AND status = 'in_progress'
        """, (datetime.now(), character_id))

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=400,
                detail="No active training found to cancel"
            )

        conn.commit()

        return {
            "message": f"Training cancelled for {character['name']}",
            "character_id": character_id
        }

    finally:
        conn.close()

# Background task functions
async def run_character_training(character_id: int, character_name: str,
                               design_prompt: str, image_count: int):
    """Background task to run character training"""
    try:
        logger.info(f"Starting background training for {character_name}")

        # Generate training images
        training_images = await training_pipeline.generate_training_images(
            character_id, character_name, design_prompt, image_count
        )

        if training_images:
            # Start LoRA training
            success = await training_pipeline.start_lora_training(
                character_id, character_name, training_images
            )

            if success:
                logger.info(f"Training completed successfully for {character_name}")
            else:
                logger.error(f"Training failed for {character_name}")
        else:
            logger.error(f"No training images generated for {character_name}")

    except Exception as e:
        logger.error(f"Error in background training for {character_name}: {e}")

async def run_batch_training():
    """Background task to run batch training"""
    try:
        logger.info("Starting batch LoRA training")
        await training_pipeline.process_character_queue()
        logger.info("Batch training completed")

    except Exception as e:
        logger.error(f"Error in batch training: {e}")

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize service on startup"""
    logger.info("LoRA Training API starting up...")

    # Test database connection
    try:
        conn = get_db_connection()
        conn.close()
        logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")

    # Test ComfyUI connection
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8188") as response:
                if response.status == 200:
                    logger.info("ComfyUI connection successful")
                else:
                    logger.warning(f"ComfyUI connection returned status {response.status}")
    except Exception as e:
        logger.error(f"ComfyUI connection failed: {e}")

    logger.info("LoRA Training API ready")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8329)