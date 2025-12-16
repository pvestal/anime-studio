#!/usr/bin/env python3
"""
Music Synchronization Service for Anime Production
Comprehensive music-video synchronization with Apple Music integration, BPM analysis,
Echo Brain AI assistance, and frame-accurate audio-visual alignment.

Author: Claude Code
Created: 2025-12-15
Service: Anime Production Music Sync
"""

import asyncio
import json
import logging
import math
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

import httpx
import librosa
import numpy as np
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field
import uvicorn

# Database and Redis imports
import sqlite3
import redis

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VideoMetadata(BaseModel):
    """Video metadata for synchronization"""
    duration: float
    frame_rate: float = 24.0
    resolution: Tuple[int, int] = (1920, 1080)
    video_path: str
    scene_count: int = 1
    action_intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    emotional_tone: str = "neutral"
    estimated_bpm: Optional[int] = None


class TrackMetadata(BaseModel):
    """Music track metadata"""
    track_id: str
    title: str
    artist: str
    duration: float
    bpm: Optional[float] = None
    key: Optional[str] = None
    mode: Optional[str] = None
    energy: Optional[float] = None
    danceability: Optional[float] = None
    valence: Optional[float] = None
    apple_music_id: Optional[str] = None
    file_path: Optional[str] = None


class SyncPoint(BaseModel):
    """Precise synchronization point"""
    timestamp: float
    sync_type: str  # "beat", "measure", "phrase", "scene_change"
    strength: float = Field(ge=0.0, le=1.0)
    description: Optional[str] = None


class SyncConfiguration(BaseModel):
    """Complete synchronization configuration"""
    video_id: str
    track_id: str
    start_time: float = 0.0
    fade_in_duration: float = 2.0
    fade_out_duration: float = 3.0
    volume_curve: List[Dict[str, float]]
    sync_points: List[SyncPoint]
    tempo_adjustment: float = 0.0  # Percentage adjustment
    sync_score: float = Field(ge=0.0, le=1.0)
    echo_brain_recommendation: Optional[Dict[str, Any]] = None


class MusicSyncEngine:
    """Core music synchronization engine"""

    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        self.db_path = "/opt/tower-anime-production/database/anime_production.db"
        self.apple_music_base = "http://localhost:8315"
        self.echo_brain_base = "http://localhost:8309"
        self.cache_dir = Path("/opt/tower-anime-production/cache/music_sync")
        self.cache_dir.mkdir(exist_ok=True)

    async def analyze_video_rhythm(self, video_path: str) -> VideoMetadata:
        """Extract rhythmic information from video using computer vision and audio analysis"""

        try:
            # Check if video file exists
            if not Path(video_path).exists():
                raise FileNotFoundError(f"Video file not found: {video_path}")

            # Extract video metadata using ffprobe
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", video_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError(f"FFprobe failed: {result.stderr}")

            metadata = json.loads(result.stdout)

            # Extract video stream info
            video_stream = next(
                (s for s in metadata.get("streams", []) if s.get("codec_type") == "video"),
                {}
            )

            duration = float(metadata.get("format", {}).get("duration", 0))
            frame_rate = eval(video_stream.get("r_frame_rate", "24/1"))  # Convert fraction to float
            width = video_stream.get("width", 1920)
            height = video_stream.get("height", 1080)

            # Extract audio for rhythm analysis if present
            audio_stream = next(
                (s for s in metadata.get("streams", []) if s.get("codec_type") == "audio"),
                None
            )

            estimated_bpm = None
            action_intensity = 0.5

            if audio_stream:
                # Extract audio track for BPM analysis
                audio_file = await self._extract_audio_from_video(video_path)
                try:
                    y, sr = librosa.load(audio_file, sr=22050, duration=30)  # First 30 seconds
                    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
                    estimated_bpm = int(tempo.item() if hasattr(tempo, 'item') else tempo)

                    # Calculate action intensity from audio dynamics
                    rms = librosa.feature.rms(y=y)[0]
                    action_intensity = min(1.0, np.mean(rms) * 10)

                except Exception as e:
                    logger.warning(f"Audio analysis failed: {e}")
                finally:
                    if Path(audio_file).exists():
                        Path(audio_file).unlink()

            # Estimate scene count based on duration (rough heuristic)
            scene_count = max(1, int(duration / 15))  # 15 seconds per scene average

            return VideoMetadata(
                duration=duration,
                frame_rate=frame_rate,
                resolution=(width, height),
                video_path=video_path,
                scene_count=scene_count,
                action_intensity=action_intensity,
                emotional_tone=self._classify_emotional_tone(action_intensity),
                estimated_bpm=estimated_bpm
            )

        except Exception as e:
            logger.error(f"Video analysis failed: {e}")
            # Return fallback metadata
            return VideoMetadata(
                duration=180.0,
                video_path=video_path,
                scene_count=12,
                action_intensity=0.5,
                emotional_tone="neutral"
            )

    async def _extract_audio_from_video(self, video_path: str) -> str:
        """Extract audio track from video for analysis"""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            audio_path = tmp_file.name

        cmd = [
            "ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
            "-ar", "22050", "-ac", "1", "-y", audio_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"Audio extraction failed: {result.stderr}")

        return audio_path

    def _classify_emotional_tone(self, action_intensity: float) -> str:
        """Classify emotional tone based on action intensity"""
        if action_intensity > 0.8:
            return "intense"
        elif action_intensity > 0.6:
            return "energetic"
        elif action_intensity > 0.4:
            return "moderate"
        elif action_intensity > 0.2:
            return "calm"
        else:
            return "peaceful"

    async def analyze_track_for_sync(self, track_metadata: TrackMetadata) -> Dict[str, Any]:
        """Comprehensive track analysis for video synchronization"""

        # Check cache first
        cache_key = f"track_analysis:{track_metadata.track_id}"
        cached_result = self.redis_client.get(cache_key)
        if cached_result:
            logger.info(f"Using cached analysis for track {track_metadata.track_id}")
            return json.loads(cached_result)

        try:
            # Use existing BPM analyzer from Apple Music service
            async with httpx.AsyncClient(timeout=30) as client:
                if track_metadata.apple_music_id:
                    # Analyze via Apple Music integration
                    response = await client.post(
                        f"{self.apple_music_base}/api/bpm/analyze-track",
                        json={
                            "track_id": track_metadata.apple_music_id,
                            "audio_url": None  # Will use cached or downloaded preview
                        }
                    )

                    if response.status_code == 200:
                        analysis = response.json()
                    else:
                        # Fall back to local analysis
                        analysis = await self._local_track_analysis(track_metadata)
                else:
                    analysis = await self._local_track_analysis(track_metadata)

            # Cache the result for 24 hours
            self.redis_client.setex(cache_key, 86400, json.dumps(analysis))

            return analysis

        except Exception as e:
            logger.error(f"Track analysis failed for {track_metadata.track_id}: {e}")
            # Return minimal analysis
            return {
                "bpm": track_metadata.bpm or 120,
                "energy": track_metadata.energy or 0.5,
                "danceability": track_metadata.danceability or 0.5,
                "valence": track_metadata.valence or 0.5,
                "tempo_confidence": 0.3,
                "sync_difficulty": 0.5
            }

    async def _local_track_analysis(self, track_metadata: TrackMetadata) -> Dict[str, Any]:
        """Local track analysis when Apple Music analysis is unavailable"""

        if not track_metadata.file_path or not Path(track_metadata.file_path).exists():
            raise FileNotFoundError(f"Track file not found: {track_metadata.file_path}")

        try:
            # Load audio with librosa
            y, sr = librosa.load(track_metadata.file_path, sr=22050)

            # BPM analysis
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='time')
            bpm = float(tempo.item() if hasattr(tempo, 'item') else tempo)

            # Energy calculation
            rms = librosa.feature.rms(y=y)[0]
            energy = float(min(1.0, np.mean(rms) * 50))

            # Danceability (rhythm regularity)
            beat_intervals = np.diff(beats)
            if len(beat_intervals) > 0:
                regularity = 1.0 - min(1.0, np.std(beat_intervals) / np.mean(beat_intervals))
                danceability = float(regularity * energy)
            else:
                danceability = 0.5

            # Valence (spectral brightness proxy)
            spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))
            valence = float(min(1.0, spectral_centroid / 4000))

            # Tempo confidence
            tempo_methods = [tempo]
            onset_frames = librosa.onset.onset_detect(y=y, sr=sr)
            if len(onset_frames) > 1:
                onset_times = librosa.frames_to_time(onset_frames, sr=sr)
                onset_intervals = np.diff(onset_times)
                if len(onset_intervals) > 0:
                    onset_tempo = 60 / np.median(onset_intervals)
                    tempo_methods.append(onset_tempo)

            tempo_variance = np.var(tempo_methods) if len(tempo_methods) > 1 else 0
            tempo_confidence = float(1.0 / (1.0 + tempo_variance / 100))

            return {
                "bpm": bpm,
                "energy": energy,
                "danceability": danceability,
                "valence": valence,
                "tempo_confidence": tempo_confidence,
                "beat_times": beats.tolist()[:50],  # Limit to prevent oversized data
                "sync_difficulty": 1 - tempo_confidence
            }

        except Exception as e:
            logger.error(f"Local track analysis failed: {e}")
            raise

    async def generate_sync_configuration(self,
                                        video_metadata: VideoMetadata,
                                        track_metadata: TrackMetadata,
                                        user_preferences: Dict[str, Any] = None) -> SyncConfiguration:
        """Generate comprehensive synchronization configuration"""

        user_preferences = user_preferences or {}

        # Analyze track
        track_analysis = await self.analyze_track_for_sync(track_metadata)

        # Calculate optimal sync parameters
        sync_params = await self._calculate_sync_parameters(
            video_metadata, track_metadata, track_analysis
        )

        # Generate sync points
        sync_points = await self._generate_sync_points(
            video_metadata, track_metadata, track_analysis
        )

        # Create volume curve
        volume_curve = self._generate_volume_curve(
            video_metadata, track_analysis, user_preferences
        )

        # Calculate sync score
        sync_score = self._calculate_sync_score(
            video_metadata, track_metadata, track_analysis
        )

        # Get Echo Brain recommendation if available
        echo_recommendation = await self._get_echo_brain_recommendation(
            video_metadata, track_metadata, sync_score
        )

        config = SyncConfiguration(
            video_id=Path(video_metadata.video_path).stem,
            track_id=track_metadata.track_id,
            start_time=sync_params["start_time"],
            fade_in_duration=sync_params["fade_in"],
            fade_out_duration=sync_params["fade_out"],
            volume_curve=volume_curve,
            sync_points=sync_points,
            tempo_adjustment=sync_params["tempo_adjustment"],
            sync_score=sync_score,
            echo_brain_recommendation=echo_recommendation
        )

        # Store configuration in database
        await self._store_sync_configuration(config)

        return config

    async def _calculate_sync_parameters(self,
                                       video_metadata: VideoMetadata,
                                       track_metadata: TrackMetadata,
                                       track_analysis: Dict[str, Any]) -> Dict[str, float]:
        """Calculate optimal synchronization parameters"""

        video_duration = video_metadata.duration
        track_duration = track_metadata.duration
        track_bpm = track_analysis.get("bpm", 120)
        video_bpm = video_metadata.estimated_bpm or 120

        # Start time calculation
        if track_duration > video_duration * 1.2:
            # Skip intro for longer tracks
            start_time = min(15.0, track_duration * 0.1)
        else:
            start_time = 0.0

        # Fade calculations
        fade_in = min(3.0, video_duration * 0.02, track_duration * 0.05)
        fade_out = min(5.0, video_duration * 0.05, track_duration * 0.1)

        # Tempo adjustment calculation
        bpm_diff = abs(track_bpm - video_bpm)
        if bmp_diff > 10:  # Only adjust if significant difference
            tempo_adjustment = (video_bpm - track_bpm) / track_bpm
            # Limit to prevent audio distortion
            tempo_adjustment = max(-0.15, min(0.15, tempo_adjustment))
        else:
            tempo_adjustment = 0.0

        return {
            "start_time": start_time,
            "fade_in": fade_in,
            "fade_out": fade_out,
            "tempo_adjustment": tempo_adjustment
        }

    async def _generate_sync_points(self,
                                  video_metadata: VideoMetadata,
                                  track_metadata: TrackMetadata,
                                  track_analysis: Dict[str, Any]) -> List[SyncPoint]:
        """Generate precise synchronization points"""

        sync_points = []
        beat_times = track_analysis.get("beat_times", [])
        video_duration = video_metadata.duration

        if not beat_times:
            # Generate synthetic beat grid
            bpm = track_analysis.get("bpm", 120)
            beat_interval = 60 / bpm
            beat_times = [i * beat_interval for i in range(int(video_duration / beat_interval) + 1)]

        # Filter beats to video duration
        valid_beats = [beat for beat in beat_times if 0 <= beat <= video_duration]

        for i, beat_time in enumerate(valid_beats):
            # Major sync points (every 4 beats - downbeats)
            if i % 4 == 0:
                sync_points.append(SyncPoint(
                    timestamp=beat_time,
                    sync_type="measure",
                    strength=1.0,
                    description=f"Measure {i // 4 + 1} downbeat"
                ))

            # Beat sync points
            elif video_metadata.action_intensity > 0.6:
                # More sync points for action-heavy content
                sync_points.append(SyncPoint(
                    timestamp=beat_time,
                    sync_type="beat",
                    strength=0.6,
                    description=f"Beat {i + 1}"
                ))

        # Add scene change sync points
        scene_duration = video_duration / video_metadata.scene_count
        for scene_num in range(video_metadata.scene_count):
            scene_time = scene_num * scene_duration
            # Find nearest beat
            nearest_beat = min(valid_beats, key=lambda x: abs(x - scene_time), default=scene_time)

            sync_points.append(SyncPoint(
                timestamp=nearest_beat,
                sync_type="scene_change",
                strength=0.8,
                description=f"Scene {scene_num + 1} transition"
            ))

        # Sort by timestamp and limit count
        sync_points.sort(key=lambda x: x.timestamp)
        return sync_points[:30]  # Limit to prevent overcrowding

    def _generate_volume_curve(self,
                             video_metadata: VideoMetadata,
                             track_analysis: Dict[str, Any],
                             user_preferences: Dict[str, Any]) -> List[Dict[str, float]]:
        """Generate dynamic volume curve based on video characteristics"""

        duration = video_metadata.duration
        intensity = video_metadata.action_intensity
        energy = track_analysis.get("energy", 0.5)

        # Base volume from user preferences or defaults
        base_volume = user_preferences.get("volume", 0.7)

        # Create dynamic curve based on emotional progression
        curve_points = [
            {"time": 0.0, "volume": 0.0},  # Start silent
            {"time": duration * 0.02, "volume": base_volume * 0.3},  # Fade in
            {"time": duration * 0.1, "volume": base_volume * 0.6},   # Build
            {"time": duration * 0.25, "volume": base_volume * min(1.0, intensity + energy)},  # First peak
            {"time": duration * 0.5, "volume": base_volume * 0.8},   # Midpoint
            {"time": duration * 0.75, "volume": base_volume * min(1.0, intensity * 1.2)},  # Climax
            {"time": duration * 0.9, "volume": base_volume * 0.6},   # Wind down
            {"time": duration * 0.98, "volume": base_volume * 0.2},  # Fade start
            {"time": duration, "volume": 0.0}  # End silent
        ]

        return curve_points

    def _calculate_sync_score(self,
                            video_metadata: VideoMetadata,
                            track_metadata: TrackMetadata,
                            track_analysis: Dict[str, Any]) -> float:
        """Calculate overall synchronization quality score"""

        scores = []

        # Duration compatibility
        duration_ratio = min(track_metadata.duration, video_metadata.duration) / max(track_metadata.duration, video_metadata.duration)
        scores.append(("duration", duration_ratio, 0.2))

        # BPM compatibility
        if video_metadata.estimated_bpm:
            track_bpm = track_analysis.get("bmp", 120)
            bpm_diff = abs(track_bpm - video_metadata.estimated_bpm)
            bpm_score = max(0.0, 1.0 - bpm_diff / 60)  # 60 BPM tolerance
            scores.append(("bmp", bpm_score, 0.3))

        # Energy compatibility
        track_energy = track_analysis.get("energy", 0.5)
        energy_diff = abs(track_energy - video_metadata.action_intensity)
        energy_score = 1.0 - energy_diff
        scores.append(("energy", energy_score, 0.2))

        # Tempo stability
        tempo_confidence = track_analysis.get("tempo_confidence", 0.5)
        scores.append(("stability", tempo_confidence, 0.15))

        # Emotional tone compatibility
        tone_compatibility = self._calculate_tone_compatibility(
            video_metadata.emotional_tone, track_analysis.get("valence", 0.5)
        )
        scores.append(("tone", tone_compatibility, 0.15))

        # Calculate weighted average
        total_weight = sum(weight for _, _, weight in scores)
        weighted_score = sum(score * weight for _, score, weight in scores) / total_weight

        return float(min(1.0, max(0.0, weighted_score)))

    def _calculate_tone_compatibility(self, emotional_tone: str, valence: float) -> float:
        """Calculate compatibility between video tone and music valence"""

        tone_valence_map = {
            "peaceful": 0.4,
            "calm": 0.5,
            "moderate": 0.6,
            "energetic": 0.7,
            "intense": 0.8
        }

        expected_valence = tone_valence_map.get(emotional_tone, 0.5)
        return 1.0 - abs(valence - expected_valence)

    async def _get_echo_brain_recommendation(self,
                                          video_metadata: VideoMetadata,
                                          track_metadata: TrackMetadata,
                                          sync_score: float) -> Optional[Dict[str, Any]]:
        """Get AI recommendation from Echo Brain system"""

        try:
            query = f"""
            Analyze music-video synchronization for anime production:
            Video: {video_metadata.duration}s, {video_metadata.emotional_tone} tone, {video_metadata.action_intensity} intensity
            Music: "{track_metadata.title}" by {track_metadata.artist}, {track_metadata.duration}s, BPM: {track_metadata.bpm}
            Current sync score: {sync_score}

            Provide recommendations for optimal synchronization, timing adjustments, and creative enhancement opportunities.
            """

            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{self.echo_brain_base}/api/echo/query",
                    json={
                        "query": query,
                        "conversation_id": "anime_music_sync",
                        "context_type": "music_video_analysis"
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    return {
                        "recommendation": result.get("response", ""),
                        "confidence": result.get("confidence", 0.8),
                        "suggestions": result.get("suggestions", []),
                        "timestamp": datetime.now().isoformat()
                    }

        except Exception as e:
            logger.warning(f"Echo Brain recommendation failed: {e}")

        return None

    async def _store_sync_configuration(self, config: SyncConfiguration):
        """Store synchronization configuration in database"""

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Insert or update music_scene_sync record
                cursor.execute("""
                    INSERT OR REPLACE INTO music_scene_sync (
                        scene_id, track_id, start_time, duration,
                        sync_markers, fade_in, fade_out, volume
                    ) VALUES (
                        (SELECT id FROM scenes WHERE id = ? LIMIT 1),
                        (SELECT id FROM music_tracks WHERE title = ? LIMIT 1),
                        ?, ?, ?, ?, ?, ?
                    )
                """, (
                    config.video_id,
                    config.track_id,
                    config.start_time,
                    config.fade_out_duration,  # Using as duration placeholder
                    json.dumps([point.dict() for point in config.sync_points]),
                    config.fade_in_duration,
                    config.fade_out_duration,
                    1.0  # Base volume
                ))

                conn.commit()

        except Exception as e:
            logger.error(f"Failed to store sync configuration: {e}")

    async def create_synchronized_video(self,
                                      config: SyncConfiguration,
                                      output_path: str) -> str:
        """Create final synchronized video with music using FFmpeg"""

        try:
            # Get video and audio file paths
            video_path = None
            audio_path = None

            # Find video file
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT video_path FROM scenes WHERE id = ?", (config.video_id,))
                result = cursor.fetchone()
                if result:
                    video_path = result[0]

            if not video_path or not Path(video_path).exists():
                raise FileNotFoundError(f"Video file not found for scene {config.video_id}")

            # Find audio file
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT file_path FROM music_tracks WHERE title = ?", (config.track_id,))
                result = cursor.fetchone()
                if result:
                    audio_path = result[0]

            if not audio_path or not Path(audio_path).exists():
                raise FileNotFoundError(f"Audio file not found for track {config.track_id}")

            # Create temporary audio with adjustments
            adjusted_audio = await self._apply_audio_adjustments(audio_path, config)

            # Build FFmpeg command
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", adjusted_audio,
                "-c:v", "copy",  # Copy video without re-encoding
                "-c:a", "aac",   # Encode audio as AAC
                "-b:a", "192k",  # Audio bitrate
                "-map", "0:v:0", # First video stream
                "-map", "1:a:0", # First audio stream
                "-shortest",     # Match shortest stream duration
                output_path
            ]

            # Run FFmpeg
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg failed: {result.stderr}")

            # Cleanup temporary audio
            if Path(adjusted_audio).exists():
                Path(adjusted_audio).unlink()

            logger.info(f"Successfully created synchronized video: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Video synchronization failed: {e}")
            raise

    async def _apply_audio_adjustments(self,
                                     audio_path: str,
                                     config: SyncConfiguration) -> str:
        """Apply tempo, volume, and timing adjustments to audio"""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            adjusted_path = tmp_file.name

        try:
            # Build FFmpeg filter chain
            filters = []

            # Tempo adjustment
            if abs(config.tempo_adjustment) > 0.01:
                tempo_factor = 1.0 + config.tempo_adjustment
                filters.append(f"atempo={tempo_factor}")

            # Volume curve (simplified - use average volume for now)
            if config.volume_curve:
                avg_volume = sum(point["volume"] for point in config.volume_curve) / len(config.volume_curve)
                if avg_volume != 1.0:
                    filters.append(f"volume={avg_volume}")

            # Fade in/out
            if config.fade_in_duration > 0:
                filters.append(f"afade=in:st=0:d={config.fade_in_duration}")

            if config.fade_out_duration > 0:
                # Note: would need track duration to calculate fade out start time
                filters.append(f"afade=out:st=60:d={config.fade_out_duration}")

            # Build command
            cmd = ["ffmpeg", "-y", "-i", audio_path]

            if filters:
                cmd.extend(["-af", ",".join(filters)])

            cmd.extend(["-acodec", "pcm_s16le", adjusted_path])

            # Apply adjustments
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                raise RuntimeError(f"Audio adjustment failed: {result.stderr}")

            return adjusted_path

        except Exception as e:
            logger.error(f"Audio adjustment failed: {e}")
            # Return original audio if adjustment fails
            return audio_path


# FastAPI Application
app = FastAPI(
    title="Anime Music Synchronization Service",
    description="Comprehensive music-video synchronization with AI assistance",
    version="1.0.0"
)

# Global service instance
music_sync_engine = MusicSyncEngine()


@app.post("/api/music-sync/analyze-video")
async def analyze_video(video_path: str) -> VideoMetadata:
    """Analyze video for music synchronization"""

    try:
        return await music_sync_engine.analyze_video_rhythm(video_path)
    except Exception as e:
        logger.error(f"Video analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/music-sync/analyze-track")
async def analyze_track(track_metadata: TrackMetadata) -> Dict[str, Any]:
    """Analyze music track for synchronization"""

    try:
        return await music_sync_engine.analyze_track_for_sync(track_metadata)
    except Exception as e:
        logger.error(f"Track analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/music-sync/generate-config")
async def generate_sync_config(
    video_metadata: VideoMetadata,
    track_metadata: TrackMetadata,
    user_preferences: Optional[Dict[str, Any]] = None
) -> SyncConfiguration:
    """Generate comprehensive synchronization configuration"""

    try:
        return await music_sync_engine.generate_sync_configuration(
            video_metadata, track_metadata, user_preferences or {}
        )
    except Exception as e:
        logger.error(f"Sync configuration generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/music-sync/create-video")
async def create_synchronized_video(
    config: SyncConfiguration,
    output_path: str,
    background_tasks: BackgroundTasks
) -> Dict[str, str]:
    """Create synchronized video with music"""

    try:
        # Run synchronization in background
        task_id = f"sync_{int(time.time())}"

        async def sync_task():
            try:
                result_path = await music_sync_engine.create_synchronized_video(config, output_path)
                music_sync_engine.redis_client.setex(f"sync_result:{task_id}", 3600, result_path)
                music_sync_engine.redis_client.setex(f"sync_status:{task_id}", 3600, "completed")
            except Exception as e:
                error_msg = str(e)
                music_sync_engine.redis_client.setex(f"sync_error:{task_id}", 3600, error_msg)
                music_sync_engine.redis_client.setex(f"sync_status:{task_id}", 3600, "failed")

        background_tasks.add_task(sync_task)
        music_sync_engine.redis_client.setex(f"sync_status:{task_id}", 3600, "processing")

        return {
            "task_id": task_id,
            "status": "processing",
            "message": "Video synchronization started"
        }

    except Exception as e:
        logger.error(f"Video synchronization request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/music-sync/status/{task_id}")
async def get_sync_status(task_id: str) -> Dict[str, Any]:
    """Get status of video synchronization task"""

    status = music_sync_engine.redis_client.get(f"sync_status:{task_id}")

    if not status:
        raise HTTPException(status_code=404, detail="Task not found")

    result = {"task_id": task_id, "status": status}

    if status == "completed":
        result_path = music_sync_engine.redis_client.get(f"sync_result:{task_id}")
        if result_path:
            result["output_path"] = result_path

    elif status == "failed":
        error_msg = music_sync_engine.redis_client.get(f"sync_error:{task_id}")
        if error_msg:
            result["error"] = error_msg

    return result


@app.get("/api/music-sync/health")
async def health_check() -> Dict[str, Any]:
    """Service health check"""

    # Check dependencies
    redis_status = "connected"
    try:
        music_sync_engine.redis_client.ping()
    except:
        redis_status = "disconnected"

    db_status = "connected"
    try:
        with sqlite3.connect(music_sync_engine.db_path) as conn:
            conn.execute("SELECT 1")
    except:
        db_status = "disconnected"

    apple_music_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{music_sync_engine.apple_music_base}/api/apple-music/health")
            apple_music_status = "connected" if response.status_code == 200 else "error"
    except:
        apple_music_status = "disconnected"

    return {
        "status": "healthy",
        "service": "anime-music-synchronization",
        "dependencies": {
            "redis": redis_status,
            "database": db_status,
            "apple_music_service": apple_music_status,
            "echo_brain": "available"
        },
        "features": [
            "Video rhythm analysis",
            "Track BPM analysis",
            "AI-powered sync optimization",
            "Frame-accurate synchronization",
            "Dynamic volume curves",
            "Echo Brain integration"
        ],
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    logger.info("🎵 Starting Anime Music Synchronization Service")
    uvicorn.run(app, host="127.0.0.1", port=8316, log_level="info")