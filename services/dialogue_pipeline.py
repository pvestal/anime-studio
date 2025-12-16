#!/usr/bin/env python3
"""
Dialogue Processing Pipeline for Anime Production
Handles multi-character dialogue generation, timing, and scene composition
Integrates voice generation with video production workflow
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
from fastapi import HTTPException
from pydantic import BaseModel, Field
import aiofiles

from lip_sync_processor import LipSyncProcessor, process_voice_for_lip_sync

logger = logging.getLogger(__name__)

class DialogueLine(BaseModel):
    """Single line of dialogue in a scene"""
    line_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    character_name: str = Field(..., min_length=1, max_length=255)
    dialogue_text: str = Field(..., min_length=1, max_length=1000)
    emotion: str = Field(default="neutral", description="Emotional tone")
    timing_start: Optional[float] = Field(None, description="Start time in seconds")
    timing_end: Optional[float] = Field(None, description="End time in seconds")
    priority: int = Field(default=1, ge=1, le=10, description="Speaking priority (1=highest)")
    voice_settings: Optional[Dict] = Field(default_factory=dict)

class SceneDialogue(BaseModel):
    """Complete dialogue for a scene"""
    scene_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: Optional[str] = Field(None)
    scene_name: str = Field(..., min_length=1, max_length=255)
    dialogue_lines: List[DialogueLine] = Field(..., min_items=1)
    background_music_path: Optional[str] = Field(None)
    background_music_volume: float = Field(default=0.3, ge=0.0, le=1.0)
    scene_duration: Optional[float] = Field(None, description="Total scene duration in seconds")
    auto_timing: bool = Field(default=True, description="Automatically calculate timing")
    output_format: str = Field(default="wav", pattern="^(wav|mp3)$")

class TimingCalculator:
    """Calculate optimal timing for dialogue lines"""

    def __init__(self):
        self.words_per_minute_base = 150  # Average speaking rate
        self.pause_between_speakers = 0.5  # Seconds
        self.min_line_duration = 0.5  # Minimum line duration
        self.max_line_duration = 10.0  # Maximum line duration

    def estimate_line_duration(self, text: str, emotion: str = "neutral") -> float:
        """Estimate duration for a single line of dialogue"""
        word_count = len(text.split())

        # Base duration calculation
        base_wpm = self.words_per_minute_base

        # Adjust WPM based on emotion
        emotion_adjustments = {
            "excited": 1.2,
            "angry": 1.1,
            "sad": 0.8,
            "whisper": 0.7,
            "shout": 1.3,
            "confused": 0.9,
            "neutral": 1.0
        }

        adjusted_wpm = base_wpm * emotion_adjustments.get(emotion, 1.0)
        duration = (word_count / adjusted_wpm) * 60

        # Apply constraints
        duration = max(self.min_line_duration, min(self.max_line_duration, duration))

        # Add padding for natural speech rhythm
        duration += len(text) * 0.01  # Small padding per character

        return duration

    def calculate_scene_timing(self, dialogue_lines: List[DialogueLine]) -> List[DialogueLine]:
        """Calculate timing for all dialogue lines in a scene"""
        current_time = 0.0
        previous_speaker = None
        timed_lines = []

        for line in dialogue_lines:
            # Add pause if speaker changes
            if previous_speaker and previous_speaker != line.character_name:
                current_time += self.pause_between_speakers

            # Estimate line duration if not provided
            if line.timing_start is None:
                line.timing_start = current_time

            line_duration = self.estimate_line_duration(line.dialogue_text, line.emotion)

            if line.timing_end is None:
                line.timing_end = line.timing_start + line_duration

            current_time = line.timing_end
            previous_speaker = line.character_name
            timed_lines.append(line)

        return timed_lines

class DialogueProcessor:
    """Main dialogue processing engine"""

    def __init__(self, db_pool: asyncpg.Pool, voice_service_url: str = "http://localhost:8319"):
        self.db_pool = db_pool
        self.voice_service_url = voice_service_url
        self.timing_calculator = TimingCalculator()
        self.lip_sync_processor = LipSyncProcessor()
        self.audio_storage_path = Path("/mnt/1TB-storage/ComfyUI/output/dialogue")
        self.audio_storage_path.mkdir(parents=True, exist_ok=True)

    async def process_scene_dialogue(self, scene: SceneDialogue) -> Dict:
        """Process complete scene dialogue with voice generation and timing"""
        try:
            logger.info(f"Processing scene dialogue: {scene.scene_name}")

            # Step 1: Calculate timing if auto_timing is enabled
            if scene.auto_timing:
                scene.dialogue_lines = self.timing_calculator.calculate_scene_timing(scene.dialogue_lines)

            # Step 2: Generate voice for each dialogue line
            voice_generation_results = []
            total_errors = 0

            for line in scene.dialogue_lines:
                voice_result = await self.generate_voice_for_line(line, scene.scene_id)
                voice_generation_results.append(voice_result)

                if not voice_result.get("success", False):
                    total_errors += 1

            # Step 3: Generate lip sync data for each line
            lip_sync_results = []
            for i, line in enumerate(scene.dialogue_lines):
                voice_result = voice_generation_results[i]
                if voice_result.get("success") and voice_result.get("audio_file_path"):
                    lip_sync_result = await process_voice_for_lip_sync(
                        voice_file_path=voice_result["audio_file_path"],
                        character_name=line.character_name,
                        output_dir=str(self.audio_storage_path),
                        frame_rate=24.0
                    )
                    lip_sync_results.append(lip_sync_result)
                else:
                    lip_sync_results.append({"success": False, "error": "Voice generation failed"})

            # Step 4: Compose scene audio track
            scene_audio_result = await self.compose_scene_audio(
                scene, voice_generation_results, lip_sync_results
            )

            # Step 5: Store scene data in database
            await self.store_scene_in_database(scene, voice_generation_results, lip_sync_results)

            # Calculate final scene duration
            final_duration = max(
                [line.timing_end for line in scene.dialogue_lines if line.timing_end],
                default=0.0
            )

            return {
                "success": True,
                "scene_id": scene.scene_id,
                "scene_name": scene.scene_name,
                "dialogue_lines_processed": len(scene.dialogue_lines),
                "voice_generation_errors": total_errors,
                "scene_duration": final_duration,
                "scene_audio_path": scene_audio_result.get("scene_audio_path"),
                "lip_sync_data_paths": [result.get("lip_sync_data_path") for result in lip_sync_results if result.get("success")],
                "dialogue_timing": [
                    {
                        "line_id": line.line_id,
                        "character_name": line.character_name,
                        "start_time": line.timing_start,
                        "end_time": line.timing_end,
                        "duration": line.timing_end - line.timing_start if line.timing_end and line.timing_start else None
                    }
                    for line in scene.dialogue_lines
                ]
            }

        except Exception as e:
            logger.error(f"Scene dialogue processing error: {e}")
            return {
                "success": False,
                "error": str(e),
                "scene_id": scene.scene_id
            }

    async def generate_voice_for_line(self, line: DialogueLine, scene_id: str) -> Dict:
        """Generate voice for a single dialogue line"""
        try:
            import httpx

            # Prepare voice generation request
            voice_request = {
                "text": line.dialogue_text,
                "character_name": line.character_name,
                "emotion": line.emotion,
                **line.voice_settings
            }

            # Call voice generation service
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.voice_service_url}/api/voice/generate",
                    json=voice_request
                )

                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Voice generated for {line.character_name}: {line.line_id}")
                    return {
                        "success": True,
                        "line_id": line.line_id,
                        "character_name": line.character_name,
                        "audio_file_path": result.get("audio_file_path"),
                        "job_id": result.get("job_id"),
                        "generation_time_ms": result.get("generation_time_ms"),
                        "voice_id": result.get("voice_id")
                    }
                else:
                    logger.error(f"Voice generation failed for line {line.line_id}: {response.status_code}")
                    return {
                        "success": False,
                        "line_id": line.line_id,
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }

        except Exception as e:
            logger.error(f"Voice generation error for line {line.line_id}: {e}")
            return {
                "success": False,
                "line_id": line.line_id,
                "error": str(e)
            }

    async def compose_scene_audio(
        self,
        scene: SceneDialogue,
        voice_results: List[Dict],
        lip_sync_results: List[Dict]
    ) -> Dict:
        """Compose all dialogue lines into a single scene audio track"""
        try:
            # For now, return success with mock data
            # In production, this would use audio mixing libraries like pydub or ffmpeg

            scene_audio_filename = f"scene_{scene.scene_id}_{int(time.time())}.wav"
            scene_audio_path = self.audio_storage_path / scene_audio_filename

            # Calculate total scene duration
            max_end_time = max(
                [line.timing_end for line in scene.dialogue_lines if line.timing_end],
                default=5.0
            )

            # Mock audio composition (replace with actual audio mixing)
            logger.info(f"Composing scene audio: {len(voice_results)} voice tracks")

            # Create empty audio file placeholder
            async with aiofiles.open(scene_audio_path, "w") as f:
                await f.write(f"# Scene audio composition placeholder for {scene.scene_name}\n")
                await f.write(f"# Duration: {max_end_time} seconds\n")
                await f.write(f"# Dialogue lines: {len(scene.dialogue_lines)}\n")

            return {
                "success": True,
                "scene_audio_path": str(scene_audio_path),
                "duration": max_end_time,
                "voice_tracks_composed": len([r for r in voice_results if r.get("success")]),
                "background_music_applied": scene.background_music_path is not None
            }

        except Exception as e:
            logger.error(f"Scene audio composition error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def store_scene_in_database(
        self,
        scene: SceneDialogue,
        voice_results: List[Dict],
        lip_sync_results: List[Dict]
    ):
        """Store scene dialogue data in database"""
        try:
            async with self.db_pool.acquire() as conn:
                # Store scene metadata
                await conn.execute("""
                    INSERT INTO dialogue_scenes (
                        scene_id, project_id, scene_name, background_music_path,
                        background_music_volume, scene_duration, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (scene_id) DO UPDATE SET
                        scene_name = EXCLUDED.scene_name,
                        background_music_path = EXCLUDED.background_music_path,
                        background_music_volume = EXCLUDED.background_music_volume,
                        scene_duration = EXCLUDED.scene_duration,
                        updated_at = CURRENT_TIMESTAMP
                """,
                scene.scene_id, scene.project_id, scene.scene_name,
                scene.background_music_path, scene.background_music_volume,
                max([line.timing_end for line in scene.dialogue_lines if line.timing_end], default=0.0),
                datetime.now()
                )

                # Store dialogue lines
                for i, line in enumerate(scene.dialogue_lines):
                    voice_result = voice_results[i] if i < len(voice_results) else {}
                    lip_sync_result = lip_sync_results[i] if i < len(lip_sync_results) else {}

                    await conn.execute("""
                        INSERT INTO dialogue_lines (
                            line_id, scene_id, character_name, dialogue_text, emotion,
                            timing_start, timing_end, priority, voice_settings,
                            audio_file_path, lip_sync_data_path, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (line_id) DO UPDATE SET
                            dialogue_text = EXCLUDED.dialogue_text,
                            emotion = EXCLUDED.emotion,
                            timing_start = EXCLUDED.timing_start,
                            timing_end = EXCLUDED.timing_end,
                            audio_file_path = EXCLUDED.audio_file_path,
                            lip_sync_data_path = EXCLUDED.lip_sync_data_path,
                            updated_at = CURRENT_TIMESTAMP
                    """,
                    line.line_id, scene.scene_id, line.character_name, line.dialogue_text, line.emotion,
                    line.timing_start, line.timing_end, line.priority, json.dumps(line.voice_settings),
                    voice_result.get("audio_file_path"), lip_sync_result.get("lip_sync_data_path"),
                    datetime.now()
                    )

                logger.info(f"Stored scene {scene.scene_id} with {len(scene.dialogue_lines)} lines in database")

        except Exception as e:
            logger.error(f"Database storage error: {e}")
            raise

    async def get_scene_dialogue(self, scene_id: str) -> Optional[Dict]:
        """Retrieve scene dialogue from database"""
        try:
            async with self.db_pool.acquire() as conn:
                # Get scene metadata
                scene_data = await conn.fetchrow(
                    "SELECT * FROM dialogue_scenes WHERE scene_id = $1",
                    scene_id
                )

                if not scene_data:
                    return None

                # Get dialogue lines
                lines_data = await conn.fetch(
                    "SELECT * FROM dialogue_lines WHERE scene_id = $1 ORDER BY timing_start",
                    scene_id
                )

                return {
                    "scene_id": scene_data["scene_id"],
                    "project_id": scene_data["project_id"],
                    "scene_name": scene_data["scene_name"],
                    "background_music_path": scene_data["background_music_path"],
                    "background_music_volume": scene_data["background_music_volume"],
                    "scene_duration": scene_data["scene_duration"],
                    "dialogue_lines": [
                        {
                            "line_id": line["line_id"],
                            "character_name": line["character_name"],
                            "dialogue_text": line["dialogue_text"],
                            "emotion": line["emotion"],
                            "timing_start": line["timing_start"],
                            "timing_end": line["timing_end"],
                            "priority": line["priority"],
                            "voice_settings": line["voice_settings"],
                            "audio_file_path": line["audio_file_path"],
                            "lip_sync_data_path": line["lip_sync_data_path"]
                        }
                        for line in lines_data
                    ],
                    "created_at": scene_data["created_at"].isoformat() if scene_data["created_at"] else None
                }

        except Exception as e:
            logger.error(f"Error retrieving scene dialogue: {e}")
            return None

    async def update_dialogue_timing(self, scene_id: str, timing_adjustments: List[Dict]) -> bool:
        """Update dialogue timing after manual adjustments"""
        try:
            async with self.db_pool.acquire() as conn:
                async with conn.transaction():
                    for adjustment in timing_adjustments:
                        await conn.execute("""
                            UPDATE dialogue_lines
                            SET timing_start = $1, timing_end = $2, updated_at = CURRENT_TIMESTAMP
                            WHERE line_id = $3 AND scene_id = $4
                        """,
                        adjustment["timing_start"], adjustment["timing_end"],
                        adjustment["line_id"], scene_id
                        )

                    # Update scene duration
                    max_end_time = max([adj["timing_end"] for adj in timing_adjustments])
                    await conn.execute("""
                        UPDATE dialogue_scenes
                        SET scene_duration = $1, updated_at = CURRENT_TIMESTAMP
                        WHERE scene_id = $2
                    """, max_end_time, scene_id)

                logger.info(f"Updated timing for {len(timing_adjustments)} lines in scene {scene_id}")
                return True

        except Exception as e:
            logger.error(f"Error updating dialogue timing: {e}")
            return False

    async def export_scene_for_video_pipeline(self, scene_id: str) -> Dict:
        """Export scene data for integration with video generation pipeline"""
        try:
            scene_data = await self.get_scene_dialogue(scene_id)

            if not scene_data:
                return {"success": False, "error": "Scene not found"}

            # Format data for video pipeline integration
            export_data = {
                "scene_id": scene_id,
                "scene_name": scene_data["scene_name"],
                "total_duration": scene_data["scene_duration"],
                "voice_tracks": [],
                "lip_sync_data": [],
                "character_list": list(set([line["character_name"] for line in scene_data["dialogue_lines"]])),
                "background_music": {
                    "path": scene_data["background_music_path"],
                    "volume": scene_data["background_music_volume"]
                } if scene_data["background_music_path"] else None
            }

            for line in scene_data["dialogue_lines"]:
                if line["audio_file_path"]:
                    export_data["voice_tracks"].append({
                        "character_name": line["character_name"],
                        "audio_path": line["audio_file_path"],
                        "start_time": line["timing_start"],
                        "end_time": line["timing_end"],
                        "emotion": line["emotion"]
                    })

                if line["lip_sync_data_path"]:
                    export_data["lip_sync_data"].append({
                        "character_name": line["character_name"],
                        "lip_sync_path": line["lip_sync_data_path"],
                        "start_time": line["timing_start"],
                        "end_time": line["timing_end"]
                    })

            # Save export data to file
            export_filename = f"scene_export_{scene_id}_{int(time.time())}.json"
            export_path = self.audio_storage_path / export_filename

            async with aiofiles.open(export_path, "w") as f:
                await f.write(json.dumps(export_data, indent=2))

            return {
                "success": True,
                "export_path": str(export_path),
                "scene_data": export_data
            }

        except Exception as e:
            logger.error(f"Scene export error: {e}")
            return {
                "success": False,
                "error": str(e)
            }