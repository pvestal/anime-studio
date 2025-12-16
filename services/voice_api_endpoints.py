#!/usr/bin/env python3
"""
Voice AI API Endpoints
Main API endpoints for voice generation and integration
Combines all voice services into a unified interface
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import asyncpg
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

# Import voice service modules
from voice_ai_service import VoiceGenerationRequest, CharacterVoiceProfile, MultiCharacterDialogue
from dialogue_pipeline import DialogueProcessor, SceneDialogue, DialogueLine
from video_voice_integration import VideoVoiceProcessor, VideoVoiceRequest
from echo_voice_integration import EchoBrainVoiceIntegration, VoiceAssessmentRequest
from lip_sync_processor import LipSyncProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Anime Voice AI API",
    description="Complete voice generation and integration system for anime production",
    version="1.0.0",
    docs_url="/api/voice/docs",
    redoc_url="/api/voice/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://192.168.50.135",
        "https://tower.local",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Database configuration
DB_CONFIG = {
    "host": "192.168.50.135",
    "database": "tower_consolidated",
    "user": "patrick",
    "password": "tower_echo_brain_secret_key_2025",
}

# Global services
db_pool: Optional[asyncpg.Pool] = None
dialogue_processor: Optional[DialogueProcessor] = None
video_voice_processor: Optional[VideoVoiceProcessor] = None
echo_brain_integration: Optional[EchoBrainVoiceIntegration] = None
lip_sync_processor: Optional[LipSyncProcessor] = None

# Request/Response models
class QuickVoiceRequest(BaseModel):
    """Quick voice generation request"""
    text: str = Field(..., min_length=1, max_length=1000)
    character_name: Optional[str] = Field(None, description="Character name for voice mapping")
    emotion: str = Field(default="neutral", description="Emotion for voice generation")

class BatchVoiceRequest(BaseModel):
    """Batch voice generation for multiple lines"""
    lines: List[QuickVoiceRequest] = Field(..., min_items=1, max_items=20)
    scene_name: Optional[str] = Field(None, description="Scene name for organization")

class CompleteSceneRequest(BaseModel):
    """Complete scene with video and voice integration"""
    project_id: str = Field(..., description="Project identifier")
    scene_name: str = Field(..., description="Scene name")
    video_prompt: str = Field(..., description="Video generation prompt")
    characters: List[str] = Field(..., description="Character names")
    dialogue_lines: List[Dict] = Field(..., description="Dialogue lines")
    video_settings: Dict = Field(default_factory=dict, description="Video generation settings")
    audio_settings: Dict = Field(default_factory=dict, description="Audio settings")

class VoiceOptimizationRequest(BaseModel):
    """Request for voice setting optimization"""
    character_name: str = Field(..., description="Character name to optimize")
    target_quality: float = Field(default=0.8, ge=0.5, le=1.0, description="Target quality score")

# Startup and initialization
@app.on_event("startup")
async def startup_event():
    """Initialize all services"""
    global db_pool, dialogue_processor, video_voice_processor, echo_brain_integration, lip_sync_processor

    try:
        # Initialize database connection
        db_pool = await asyncpg.create_pool(
            host=DB_CONFIG["host"],
            database=DB_CONFIG["database"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            min_size=5,
            max_size=20,
        )

        # Initialize all voice services
        dialogue_processor = DialogueProcessor(db_pool)
        video_voice_processor = VideoVoiceProcessor(db_pool)
        echo_brain_integration = EchoBrainVoiceIntegration(db_pool)
        lip_sync_processor = LipSyncProcessor()

        # Create database tables
        await initialize_voice_database()

        logger.info("Voice AI API services initialized successfully")

    except Exception as e:
        logger.error(f"Startup initialization failed: {e}")
        raise

async def initialize_voice_database():
    """Initialize voice database tables"""
    try:
        async with db_pool.acquire() as conn:
            # Read and execute voice AI schema
            schema_path = Path(__file__).parent.parent / "database" / "voice_ai_schema.sql"
            if schema_path.exists():
                with open(schema_path, 'r') as f:
                    schema_sql = f.read()
                await conn.execute(schema_sql)
                logger.info("Voice AI database schema initialized")
            else:
                logger.warning("Voice AI schema file not found")

    except Exception as e:
        logger.error(f"Database initialization error: {e}")

# Basic voice generation endpoints
@app.get("/api/voice/health")
async def health_check():
    """Comprehensive health check"""
    return {
        "service": "voice-ai-api",
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "database": db_pool is not None,
            "dialogue_processor": dialogue_processor is not None,
            "video_voice_processor": video_voice_processor is not None,
            "echo_brain_integration": echo_brain_integration is not None,
            "lip_sync_processor": lip_sync_processor is not None
        }
    }

@app.post("/api/voice/generate/quick")
async def quick_voice_generation(request: QuickVoiceRequest):
    """Quick voice generation for single line"""
    try:
        # Convert to full voice request
        voice_request = VoiceGenerationRequest(
            text=request.text,
            character_name=request.character_name,
            emotion=request.emotion
        )

        # Use voice AI service logic (simplified)
        job_id = str(uuid.uuid4())

        # Mock voice generation (replace with actual service call)
        return {
            "success": True,
            "job_id": job_id,
            "status": "completed",
            "text": request.text,
            "character_name": request.character_name,
            "emotion": request.emotion,
            "audio_file_path": f"/mnt/1TB-storage/ComfyUI/output/voice/quick_{job_id}.mp3",
            "estimated_duration": len(request.text) * 0.1
        }

    except Exception as e:
        logger.error(f"Quick voice generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/voice/generate/batch")
async def batch_voice_generation(request: BatchVoiceRequest, background_tasks: BackgroundTasks):
    """Batch voice generation for multiple lines"""
    try:
        batch_id = str(uuid.uuid4())
        results = []

        for i, line in enumerate(request.lines):
            # Generate voice for each line
            job_id = str(uuid.uuid4())

            # Add to background processing
            background_tasks.add_task(
                process_voice_line_background,
                job_id, line, batch_id
            )

            results.append({
                "line_index": i,
                "job_id": job_id,
                "text": line.text,
                "character_name": line.character_name,
                "status": "processing"
            })

        return {
            "success": True,
            "batch_id": batch_id,
            "scene_name": request.scene_name,
            "lines_count": len(request.lines),
            "results": results
        }

    except Exception as e:
        logger.error(f"Batch voice generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_voice_line_background(job_id: str, line: QuickVoiceRequest, batch_id: str):
    """Background processing for voice line"""
    try:
        # Simulate voice processing
        await asyncio.sleep(2)  # Mock processing time

        # Store result in database
        async with db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO voice_generation_jobs (job_id, text, character_name, status, audio_file_path)
                VALUES ($1, $2, $3, 'completed', $4)
            """, job_id, line.text, line.character_name, f"/mock/path/{job_id}.mp3")

        logger.info(f"Background voice processing completed: {job_id}")

    except Exception as e:
        logger.error(f"Background voice processing error: {e}")

# Character voice management endpoints
@app.post("/api/voice/characters/profile")
async def create_character_voice_profile(profile: CharacterVoiceProfile):
    """Create or update character voice profile"""
    try:
        async with db_pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO voice_profiles (character_name, voice_id, voice_name, voice_settings, description, sample_text)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (character_name)
                DO UPDATE SET
                    voice_id = EXCLUDED.voice_id,
                    voice_name = EXCLUDED.voice_name,
                    voice_settings = EXCLUDED.voice_settings,
                    description = EXCLUDED.description,
                    sample_text = EXCLUDED.sample_text,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """,
            profile.character_name, profile.voice_id, profile.voice_name,
            json.dumps(profile.voice_settings), profile.description, profile.sample_text
            )

        return {
            "success": True,
            "character_name": profile.character_name,
            "profile_id": result["id"],
            "message": "Character voice profile created/updated successfully"
        }

    except Exception as e:
        logger.error(f"Error creating character profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/voice/characters")
async def list_character_profiles():
    """List all character voice profiles"""
    try:
        async with db_pool.acquire() as conn:
            profiles = await conn.fetch("SELECT * FROM voice_profiles ORDER BY character_name")

            return {
                "characters": [
                    {
                        "id": profile["id"],
                        "character_name": profile["character_name"],
                        "voice_id": profile["voice_id"],
                        "voice_name": profile["voice_name"],
                        "description": profile["description"],
                        "usage_count": profile["usage_count"],
                        "created_at": profile["created_at"].isoformat() if profile["created_at"] else None
                    }
                    for profile in profiles
                ],
                "count": len(profiles)
            }

    except Exception as e:
        logger.error(f"Error listing character profiles: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/voice/characters/{character_name}/analytics")
async def get_character_analytics(character_name: str):
    """Get voice analytics for a character"""
    try:
        analytics = await echo_brain_integration.get_character_voice_analytics(character_name)
        return analytics

    except Exception as e:
        logger.error(f"Error getting character analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/voice/characters/{character_name}/optimize")
async def optimize_character_voice(character_name: str, request: VoiceOptimizationRequest):
    """Optimize voice settings for a character using Echo Brain"""
    try:
        optimization_result = await echo_brain_integration.optimize_voice_settings_for_character(character_name)

        if optimization_result.get("success"):
            # Update character profile with optimized settings
            async with db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE voice_profiles
                    SET voice_settings = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE character_name = $2
                """, json.dumps(optimization_result["optimized_settings"]), character_name)

        return optimization_result

    except Exception as e:
        logger.error(f"Voice optimization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Scene dialogue processing endpoints
@app.post("/api/voice/scenes/process")
async def process_scene_dialogue(scene: SceneDialogue):
    """Process complete scene dialogue with voice generation"""
    try:
        result = await dialogue_processor.process_scene_dialogue(scene)
        return result

    except Exception as e:
        logger.error(f"Scene dialogue processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/voice/scenes/{scene_id}")
async def get_scene_dialogue(scene_id: str):
    """Get scene dialogue data"""
    try:
        scene_data = await dialogue_processor.get_scene_dialogue(scene_id)

        if not scene_data:
            raise HTTPException(status_code=404, detail="Scene not found")

        return scene_data

    except Exception as e:
        logger.error(f"Error getting scene dialogue: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/voice/scenes/{scene_id}/timing")
async def update_dialogue_timing(scene_id: str, timing_adjustments: List[Dict]):
    """Update dialogue timing"""
    try:
        success = await dialogue_processor.update_dialogue_timing(scene_id, timing_adjustments)

        if success:
            return {"success": True, "scene_id": scene_id, "updated_lines": len(timing_adjustments)}
        else:
            raise HTTPException(status_code=500, detail="Failed to update timing")

    except Exception as e:
        logger.error(f"Timing update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/voice/scenes/{scene_id}/export")
async def export_scene_for_video(scene_id: str):
    """Export scene data for video pipeline integration"""
    try:
        export_result = await dialogue_processor.export_scene_for_video_pipeline(scene_id)
        return export_result

    except Exception as e:
        logger.error(f"Scene export error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Complete video-voice integration
@app.post("/api/voice/complete-scene")
async def create_complete_scene(request: CompleteSceneRequest, background_tasks: BackgroundTasks):
    """Create complete scene with integrated video and voice"""
    try:
        # Convert to video-voice request
        video_voice_request = VideoVoiceRequest(
            project_id=request.project_id,
            scene_name=request.scene_name,
            video_prompt=request.video_prompt,
            dialogue_lines=request.dialogue_lines,
            characters=request.characters,
            **request.video_settings,
            **request.audio_settings
        )

        # Process in background for long operations
        processing_id = str(uuid.uuid4())
        background_tasks.add_task(
            process_complete_scene_background,
            video_voice_request, processing_id
        )

        return {
            "success": True,
            "processing_id": processing_id,
            "project_id": request.project_id,
            "scene_name": request.scene_name,
            "status": "processing",
            "estimated_time": 300,  # 5 minutes estimate
            "message": "Complete scene processing started"
        }

    except Exception as e:
        logger.error(f"Complete scene creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_complete_scene_background(request: VideoVoiceRequest, processing_id: str):
    """Background processing for complete scene"""
    try:
        result = await video_voice_processor.process_integrated_video(request)

        # Store processing result
        async with db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE video_voice_processing
                SET processing_status = $1, completed_at = CURRENT_TIMESTAMP
                WHERE processing_id = $2
            """, "completed" if result.get("success") else "failed", processing_id)

        logger.info(f"Complete scene processing finished: {processing_id}")

    except Exception as e:
        logger.error(f"Background scene processing error: {e}")

@app.get("/api/voice/complete-scene/{processing_id}/status")
async def get_complete_scene_status(processing_id: str):
    """Get complete scene processing status"""
    try:
        status_data = await video_voice_processor.get_processing_status(processing_id)

        if not status_data:
            raise HTTPException(status_code=404, detail="Processing ID not found")

        return status_data

    except Exception as e:
        logger.error(f"Error getting processing status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Voice quality assessment endpoints
@app.post("/api/voice/assess")
async def assess_voice_quality(request: VoiceAssessmentRequest):
    """Assess voice quality using Echo Brain"""
    try:
        assessment = await echo_brain_integration.assess_voice_quality(request)
        return assessment

    except Exception as e:
        logger.error(f"Voice assessment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/voice/assessments/{character_name}")
async def get_character_assessments(character_name: str, limit: int = 10):
    """Get recent voice assessments for a character"""
    try:
        async with db_pool.acquire() as conn:
            assessments = await conn.fetch("""
                SELECT * FROM voice_quality_assessments
                WHERE character_name = $1
                ORDER BY assessed_at DESC
                LIMIT $2
            """, character_name, limit)

            return {
                "character_name": character_name,
                "assessments": [
                    {
                        "assessment_id": assessment["assessment_id"],
                        "quality_score": assessment["quality_score"],
                        "consistency_score": assessment["consistency_score"],
                        "emotion_accuracy": assessment["emotion_accuracy"],
                        "approved": assessment["approved"],
                        "recommendations": assessment["recommendations"],
                        "assessed_at": assessment["assessed_at"].isoformat() if assessment["assessed_at"] else None
                    }
                    for assessment in assessments
                ],
                "count": len(assessments)
            }

    except Exception as e:
        logger.error(f"Error getting character assessments: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# File serving endpoints
@app.get("/api/voice/audio/{job_id}")
async def serve_voice_audio(job_id: str):
    """Serve generated voice audio file"""
    try:
        async with db_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT audio_file_path FROM voice_generation_jobs WHERE job_id = $1",
                job_id
            )

            if not result or not result["audio_file_path"]:
                raise HTTPException(status_code=404, detail="Audio file not found")

            file_path = Path(result["audio_file_path"])
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="Audio file not found on disk")

            return FileResponse(
                path=file_path,
                media_type="audio/mpeg",
                filename=f"voice_{job_id}.mp3"
            )

    except Exception as e:
        logger.error(f"Error serving audio file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/voice/video/{processing_id}")
async def serve_integrated_video(processing_id: str):
    """Serve complete integrated video"""
    try:
        async with db_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT output_video_path FROM video_voice_processing WHERE processing_id = $1",
                processing_id
            )

            if not result or not result["output_video_path"]:
                raise HTTPException(status_code=404, detail="Video not found")

            file_path = Path(result["output_video_path"])
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="Video file not found on disk")

            return FileResponse(
                path=file_path,
                media_type="video/mp4",
                filename=f"scene_{processing_id}.mp4"
            )

    except Exception as e:
        logger.error(f"Error serving video file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Statistics and monitoring endpoints
@app.get("/api/voice/stats")
async def get_voice_statistics():
    """Get comprehensive voice generation statistics"""
    try:
        async with db_pool.acquire() as conn:
            # Voice generation stats
            voice_stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_jobs,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                    COUNT(CASE WHEN status = 'processing' THEN 1 END) as processing,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                    AVG(generation_time_ms) as avg_generation_time
                FROM voice_generation_jobs
            """)

            # Character stats
            character_stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_characters,
                    AVG(usage_count) as avg_usage_per_character
                FROM voice_profiles
            """)

            # Quality stats
            quality_stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_assessments,
                    AVG(quality_score) as avg_quality_score,
                    COUNT(CASE WHEN approved THEN 1 END) as approved_count
                FROM voice_quality_assessments
            """)

            return {
                "voice_generation": {
                    "total_jobs": voice_stats["total_jobs"] or 0,
                    "completed": voice_stats["completed"] or 0,
                    "processing": voice_stats["processing"] or 0,
                    "failed": voice_stats["failed"] or 0,
                    "success_rate": (voice_stats["completed"] or 0) / max(1, voice_stats["total_jobs"] or 1),
                    "avg_generation_time_ms": voice_stats["avg_generation_time"] or 0
                },
                "characters": {
                    "total_characters": character_stats["total_characters"] or 0,
                    "avg_usage_per_character": character_stats["avg_usage_per_character"] or 0
                },
                "quality": {
                    "total_assessments": quality_stats["total_assessments"] or 0,
                    "avg_quality_score": quality_stats["avg_quality_score"] or 0,
                    "approval_rate": (quality_stats["approved_count"] or 0) / max(1, quality_stats["total_assessments"] or 1)
                },
                "timestamp": datetime.now().isoformat()
            }

    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    logger.info("Starting Voice AI API")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8319,
        log_level="info",
    )