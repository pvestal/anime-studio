#!/usr/bin/env python3
"""
Voice AI Service for Anime Production
Integrates with Eleven Labs API for high-quality text-to-speech
Supports character voice profiles and multi-character dialogue
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import asyncpg
import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import aiofiles

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Voice AI Service",
    description="Text-to-speech and voice generation for anime production",
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

# Configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_STORAGE_PATH = Path("/mnt/1TB-storage/ComfyUI/output/voice")
VOICE_STORAGE_PATH.mkdir(parents=True, exist_ok=True)

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "192.168.50.135"),
    "database": os.getenv("DB_NAME", "tower_consolidated"),
    "user": os.getenv("DB_USER", "patrick"),
    "password": os.getenv("DB_PASSWORD", "tower_echo_brain_secret_key_2025"),
}

# Request/Response models
class VoiceGenerationRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="Text to convert to speech")
    character_id: Optional[int] = Field(None, description="Character ID for voice mapping")
    character_name: Optional[str] = Field(None, description="Character name for voice assignment")
    voice_id: Optional[str] = Field(None, description="Specific Eleven Labs voice ID")
    emotion: str = Field(default="neutral", description="Emotion for voice generation")
    stability: float = Field(default=0.5, ge=0.0, le=1.0, description="Voice stability (0-1)")
    similarity_boost: float = Field(default=0.8, ge=0.0, le=1.0, description="Voice similarity boost")
    style: float = Field(default=0.0, ge=0.0, le=1.0, description="Style exaggeration")
    use_speaker_boost: bool = Field(default=True, description="Use speaker boost for clarity")

class CharacterVoiceProfile(BaseModel):
    character_name: str = Field(..., min_length=1, max_length=255)
    voice_id: str = Field(..., description="Eleven Labs voice ID")
    voice_name: str = Field(..., description="Human-readable voice name")
    voice_settings: Dict = Field(default_factory=dict, description="Default voice settings")
    description: Optional[str] = Field(None, description="Voice profile description")
    sample_text: str = Field(default="Hello, this is a sample of my voice.", description="Sample text for testing")

class MultiCharacterDialogue(BaseModel):
    scene_id: Optional[int] = Field(None, description="Scene ID for organization")
    dialogue_lines: List[Dict] = Field(..., description="List of dialogue lines with character assignments")
    # Example: [{"character_name": "Akira", "text": "Hello there!", "timing_start": 0.0, "emotion": "happy"}]
    background_music_volume: float = Field(default=0.3, ge=0.0, le=1.0, description="Background music volume")
    export_format: str = Field(default="wav", pattern="^(wav|mp3)$", description="Audio export format")

class VoiceAssignmentDB(BaseModel):
    scene_id: Optional[int] = None
    character_id: int
    voice_id: str
    dialogue_text: str
    audio_file_path: str
    timing_start: float
    duration: float
    emotion: str
    created_at: datetime

# Global variables
db_pool: Optional[asyncpg.Pool] = None
available_voices: Dict[str, Dict] = {}

async def init_database():
    """Initialize database connection pool and create tables"""
    global db_pool

    try:
        db_pool = await asyncpg.create_pool(
            host=DB_CONFIG["host"],
            database=DB_CONFIG["database"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            min_size=5,
            max_size=20,
        )

        # Create voice-related tables if they don't exist
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS voice_profiles (
                    id SERIAL PRIMARY KEY,
                    character_name VARCHAR(255) UNIQUE NOT NULL,
                    voice_id VARCHAR(255) NOT NULL,
                    voice_name VARCHAR(255) NOT NULL,
                    voice_settings JSONB DEFAULT '{}',
                    description TEXT,
                    sample_text TEXT DEFAULT 'Hello, this is a sample of my voice.',
                    usage_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS voice_assignments (
                    id SERIAL PRIMARY KEY,
                    scene_id INTEGER,
                    character_id INTEGER,
                    voice_id VARCHAR(255) NOT NULL,
                    dialogue_text TEXT NOT NULL,
                    audio_file_path TEXT NOT NULL,
                    timing_start FLOAT DEFAULT 0.0,
                    duration FLOAT,
                    emotion VARCHAR(100) DEFAULT 'neutral',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS voice_generation_jobs (
                    id SERIAL PRIMARY KEY,
                    job_id UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
                    text TEXT NOT NULL,
                    character_name VARCHAR(255),
                    voice_id VARCHAR(255) NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    audio_file_path TEXT,
                    error_message TEXT,
                    generation_time_ms INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                );
            """)

            # Create indexes
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_voice_profiles_character ON voice_profiles(character_name);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_voice_assignments_scene ON voice_assignments(scene_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_voice_jobs_status ON voice_generation_jobs(status);")

        logger.info("Voice AI database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

async def load_available_voices():
    """Load available voices from Eleven Labs API"""
    global available_voices

    if not ELEVENLABS_API_KEY:
        logger.warning("Eleven Labs API key not configured, using fallback voices")
        available_voices = {
            "fallback_female": {"name": "Fallback Female", "category": "premade"},
            "fallback_male": {"name": "Fallback Male", "category": "premade"},
        }
        return

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": ELEVENLABS_API_KEY}
            )

            if response.status_code == 200:
                voices_data = response.json()
                available_voices = {
                    voice["voice_id"]: {
                        "name": voice["name"],
                        "category": voice.get("category", "premade"),
                        "description": voice.get("description", ""),
                        "preview_url": voice.get("preview_url"),
                        "settings": voice.get("settings", {})
                    }
                    for voice in voices_data.get("voices", [])
                }
                logger.info(f"Loaded {len(available_voices)} voices from Eleven Labs")
            else:
                logger.error(f"Failed to load voices: {response.status_code}")
                available_voices = {}
    except Exception as e:
        logger.error(f"Error loading voices: {e}")
        available_voices = {}

async def generate_speech_elevenlabs(
    text: str,
    voice_id: str,
    stability: float = 0.5,
    similarity_boost: float = 0.8,
    style: float = 0.0,
    use_speaker_boost: bool = True
) -> Optional[bytes]:
    """Generate speech using Eleven Labs API"""

    if not ELEVENLABS_API_KEY:
        logger.warning("Eleven Labs API key not available, using TTS fallback")
        return await generate_speech_fallback(text, voice_id)

    try:
        voice_settings = {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": use_speaker_boost
        }

        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": voice_settings
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                json=payload,
                headers={
                    "xi-api-key": ELEVENLABS_API_KEY,
                    "Content-Type": "application/json"
                }
            )

            if response.status_code == 200:
                return response.content
            else:
                logger.error(f"Eleven Labs API error {response.status_code}: {response.text}")
                return None

    except Exception as e:
        logger.error(f"Speech generation error: {e}")
        return None

async def generate_speech_fallback(text: str, voice_id: str) -> Optional[bytes]:
    """Fallback TTS using system TTS (espeak/festival)"""
    try:
        import subprocess

        # Use espeak as fallback TTS
        process = await asyncio.create_subprocess_exec(
            "espeak",
            "-s", "150",  # Speed
            "-v", "en",   # Voice
            "-w", "/dev/stdout",  # Output to stdout
            text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0 and stdout:
            return stdout
        else:
            logger.error(f"Fallback TTS failed: {stderr.decode()}")
            return None

    except Exception as e:
        logger.error(f"Fallback TTS error: {e}")
        return None

async def save_audio_file(audio_data: bytes, filename: str, format: str = "mp3") -> str:
    """Save audio data to file and return path"""
    try:
        file_path = VOICE_STORAGE_PATH / f"{filename}.{format}"

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(audio_data)

        return str(file_path)
    except Exception as e:
        logger.error(f"Error saving audio file: {e}")
        raise

async def get_character_voice_profile(character_name: str) -> Optional[Dict]:
    """Get voice profile for a character"""
    try:
        async with db_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM voice_profiles WHERE character_name = $1",
                character_name
            )

            if result:
                return {
                    "id": result["id"],
                    "character_name": result["character_name"],
                    "voice_id": result["voice_id"],
                    "voice_name": result["voice_name"],
                    "voice_settings": result["voice_settings"],
                    "description": result["description"],
                    "sample_text": result["sample_text"],
                    "usage_count": result["usage_count"],
                }
            return None
    except Exception as e:
        logger.error(f"Error getting character voice profile: {e}")
        return None

# API Endpoints

@app.on_event("startup")
async def startup_event():
    """Initialize service on startup"""
    await init_database()
    await load_available_voices()
    logger.info("Voice AI Service started successfully")

@app.get("/api/voice/health")
async def health_check():
    """Health check endpoint"""
    return {
        "service": "voice-ai",
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "elevenlabs_available": ELEVENLABS_API_KEY is not None,
        "available_voices": len(available_voices),
        "storage_path": str(VOICE_STORAGE_PATH),
    }

@app.get("/api/voice/voices")
async def list_available_voices():
    """List all available voices"""
    return {
        "voices": available_voices,
        "count": len(available_voices)
    }

@app.post("/api/voice/generate")
async def generate_voice(request: VoiceGenerationRequest):
    """Generate speech from text with character voice mapping"""
    start_time = time.time()

    try:
        # Determine voice ID
        voice_id = request.voice_id
        if not voice_id and request.character_name:
            # Look up character voice profile
            profile = await get_character_voice_profile(request.character_name)
            if profile:
                voice_id = profile["voice_id"]
                # Use profile settings if not overridden
                if not request.voice_id:
                    settings = profile.get("voice_settings", {})
                    request.stability = settings.get("stability", request.stability)
                    request.similarity_boost = settings.get("similarity_boost", request.similarity_boost)

        if not voice_id:
            voice_id = list(available_voices.keys())[0] if available_voices else "fallback_female"

        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Store job in database
        async with db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO voice_generation_jobs (job_id, text, character_name, voice_id, status)
                VALUES ($1, $2, $3, $4, 'processing')
            """, job_id, request.text, request.character_name, voice_id)

        # Generate speech
        audio_data = await generate_speech_elevenlabs(
            text=request.text,
            voice_id=voice_id,
            stability=request.stability,
            similarity_boost=request.similarity_boost,
            style=request.style,
            use_speaker_boost=request.use_speaker_boost
        )

        if not audio_data:
            # Update job status to failed
            async with db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE voice_generation_jobs
                    SET status = 'failed', error_message = 'Speech generation failed'
                    WHERE job_id = $1
                """, job_id)
            raise HTTPException(status_code=500, detail="Speech generation failed")

        # Save audio file
        filename = f"voice_{job_id}_{int(time.time())}"
        audio_path = await save_audio_file(audio_data, filename, "mp3")

        generation_time = int((time.time() - start_time) * 1000)

        # Update job status
        async with db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE voice_generation_jobs
                SET status = 'completed', audio_file_path = $1, generation_time_ms = $2, completed_at = CURRENT_TIMESTAMP
                WHERE job_id = $3
            """, audio_path, generation_time, job_id)

            # Update character usage count if applicable
            if request.character_name:
                await conn.execute("""
                    UPDATE voice_profiles
                    SET usage_count = usage_count + 1
                    WHERE character_name = $1
                """, request.character_name)

        return {
            "job_id": job_id,
            "status": "completed",
            "audio_file_path": audio_path,
            "duration_estimate": len(request.text) * 0.1,  # Rough estimate
            "generation_time_ms": generation_time,
            "voice_id": voice_id,
            "character_name": request.character_name,
        }

    except Exception as e:
        logger.error(f"Voice generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
            profile.character_name,
            profile.voice_id,
            profile.voice_name,
            json.dumps(profile.voice_settings),
            profile.description,
            profile.sample_text
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

@app.get("/api/voice/characters/{character_name}/profile")
async def get_character_profile(character_name: str):
    """Get character voice profile"""
    profile = await get_character_voice_profile(character_name)
    if not profile:
        raise HTTPException(status_code=404, detail="Character profile not found")
    return profile

@app.post("/api/voice/dialogue/multi-character")
async def generate_multi_character_dialogue(dialogue: MultiCharacterDialogue):
    """Generate dialogue for multiple characters in a scene"""
    try:
        generated_files = []
        total_duration = 0.0

        for i, line in enumerate(dialogue.dialogue_lines):
            character_name = line.get("character_name")
            text = line.get("text", "")
            emotion = line.get("emotion", "neutral")
            timing_start = line.get("timing_start", total_duration)

            if not character_name or not text:
                continue

            # Generate voice for this line
            voice_request = VoiceGenerationRequest(
                text=text,
                character_name=character_name,
                emotion=emotion
            )

            # Generate the speech
            result = await generate_voice(voice_request)

            if result["status"] == "completed":
                # Estimate duration (rough calculation)
                estimated_duration = len(text) * 0.1

                # Store in voice_assignments table
                async with db_pool.acquire() as conn:
                    if dialogue.scene_id:
                        character_id = await conn.fetchval(
                            "SELECT id FROM anime_characters WHERE character_name = $1",
                            character_name
                        )

                        await conn.execute("""
                            INSERT INTO voice_assignments
                            (scene_id, character_id, voice_id, dialogue_text, audio_file_path, timing_start, duration, emotion)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """,
                        dialogue.scene_id, character_id, result["voice_id"],
                        text, result["audio_file_path"], timing_start,
                        estimated_duration, emotion)

                generated_files.append({
                    "line_index": i,
                    "character_name": character_name,
                    "text": text,
                    "audio_file_path": result["audio_file_path"],
                    "timing_start": timing_start,
                    "duration": estimated_duration,
                    "emotion": emotion
                })

                total_duration = max(total_duration, timing_start + estimated_duration)

        return {
            "success": True,
            "scene_id": dialogue.scene_id,
            "generated_files": generated_files,
            "total_duration": total_duration,
            "file_count": len(generated_files)
        }

    except Exception as e:
        logger.error(f"Multi-character dialogue generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/voice/audio/{job_id}")
async def serve_audio_file(job_id: str):
    """Serve generated audio file"""
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

@app.post("/api/voice/echo-brain/assess")
async def echo_brain_voice_assessment(assessment_data: Dict):
    """Integration endpoint for Echo Brain to assess voice quality"""
    try:
        # This would integrate with Echo Brain for quality assessment
        # For now, return a mock assessment

        job_id = assessment_data.get("job_id")
        text = assessment_data.get("text", "")
        character_name = assessment_data.get("character_name")

        # Mock quality metrics (replace with actual Echo Brain integration)
        quality_score = 0.85  # Mock score
        consistency_score = 0.92
        emotion_accuracy = 0.78

        return {
            "job_id": job_id,
            "quality_assessment": {
                "overall_score": quality_score,
                "consistency_score": consistency_score,
                "emotion_accuracy": emotion_accuracy,
                "recommendations": [
                    "Voice matches character profile well",
                    "Emotion expression could be enhanced"
                ]
            },
            "approved": quality_score > 0.8
        }

    except Exception as e:
        logger.error(f"Echo Brain assessment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/voice/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    """Get voice generation job status"""
    try:
        async with db_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM voice_generation_jobs WHERE job_id = $1",
                job_id
            )

            if not result:
                raise HTTPException(status_code=404, detail="Job not found")

            return {
                "job_id": job_id,
                "status": result["status"],
                "text": result["text"],
                "character_name": result["character_name"],
                "voice_id": result["voice_id"],
                "audio_file_path": result["audio_file_path"],
                "error_message": result["error_message"],
                "generation_time_ms": result["generation_time_ms"],
                "created_at": result["created_at"].isoformat() if result["created_at"] else None,
                "completed_at": result["completed_at"].isoformat() if result["completed_at"] else None,
            }

    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    logger.info("Starting Voice AI Service")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8319,  # Voice AI service port
        log_level="info",
    )