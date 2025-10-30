#!/usr/bin/env python3
"""
Music Synchronization Module for Anime Production
Handles syncing music tracks to scenes with precise timing markers
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import librosa
import numpy as np
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MusicSyncEngine:
    """Engine for synchronizing music tracks to anime scenes"""

    def __init__(self):
        self.apple_music_url = "http://localhost:8328"  # Assuming Apple Music service
        self.db_config = {
            'host': 'localhost',
            'database': 'anime_production',
            'user': 'patrick',
            'port': 5432,
            'options': '-c search_path=anime_api,public'
        }

    @contextmanager
    def _get_db_connection(self):
        """Get database connection with automatic cleanup"""
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def sync_music_to_scene(
        self,
        scene_id: int,
        playlist_id: Optional[str],
        track_mappings: List[Dict]
    ) -> Dict:
        """
        Sync music tracks to a scene
        
        Args:
            scene_id: Scene ID to sync music to
            playlist_id: Optional playlist ID from Apple Music
            track_mappings: List of track mapping dicts with:
                - track_id: Track identifier
                - track_name: Track name
                - artist: Artist name
                - start_time: When track starts in scene (seconds)
                - duration: Track duration (seconds)
                - volume: Volume level (0.0 to 1.0)
                - fade_in: Fade in duration (seconds)
                - fade_out: Fade out duration (seconds)
        
        Returns:
            Dict with sync results
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                # Verify scene exists
                cursor.execute("SELECT id FROM scenes WHERE id = %s", (scene_id,))
                if not cursor.fetchone():
                    return {"success": False, "error": f"Scene {scene_id} not found"}

                synced_tracks = []
                for mapping in track_mappings:
                    cursor.execute("""
                        INSERT INTO music_scene_sync
                        (scene_id, playlist_id, track_id, track_name, artist,
                         start_time, duration, volume, fade_in, fade_out, sync_markers)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        scene_id,
                        playlist_id,
                        mapping.get('track_id'),
                        mapping.get('track_name'),
                        mapping.get('artist'),
                        mapping.get('start_time', 0.0),
                        mapping.get('duration'),
                        mapping.get('volume', 1.0),
                        mapping.get('fade_in', 0.0),
                        mapping.get('fade_out', 0.0),
                        json.dumps(mapping.get('sync_markers', []))
                    ))
                    sync_id = cursor.fetchone()[0]
                    synced_tracks.append({
                        "id": sync_id,
                        "track_id": mapping.get('track_id'),
                        "track_name": mapping.get('track_name')
                    })

                conn.commit()
            
            logger.info(f"Synced {len(synced_tracks)} tracks to scene {scene_id}")
            return {
                "success": True,
                "scene_id": scene_id,
                "synced_tracks": synced_tracks
            }
            
        except Exception as e:
            logger.error(f"Error syncing music to scene: {e}")
            return {"success": False, "error": str(e)}
    
    def add_sync_marker(
        self,
        scene_id: int,
        track_id: str,
        timestamp: float,
        event_name: str,
        audio_cue: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Add a precise timing marker to a track sync
        
        Args:
            scene_id: Scene ID
            track_id: Track identifier
            timestamp: Time in seconds when event occurs
            event_name: Name of the event (e.g., "sword_clash", "explosion")
            audio_cue: Optional audio file path for sound effect
            metadata: Optional metadata dict
        
        Returns:
            Dict with marker addition result
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                # Get existing sync entry
                cursor.execute("""
                    SELECT id, sync_markers FROM music_scene_sync
                    WHERE scene_id = %s AND track_id = %s
                    ORDER BY id DESC LIMIT 1
                """, (scene_id, track_id))

                row = cursor.fetchone()
                if not row:
                    return {"success": False, "error": "Track sync not found"}

                sync_id, markers_json = row
                markers = json.loads(markers_json) if markers_json else []

                # Add new marker
                new_marker = {
                    "timestamp": timestamp,
                    "event": event_name,
                    "audio_cue": audio_cue,
                    "metadata": metadata or {}
                }
                markers.append(new_marker)

                # Update sync entry
                cursor.execute("""
                    UPDATE music_scene_sync
                    SET sync_markers = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (json.dumps(markers), sync_id))

                conn.commit()
            
            logger.info(f"Added marker '{event_name}' at {timestamp}s to scene {scene_id}")
            return {
                "success": True,
                "sync_id": sync_id,
                "marker": new_marker,
                "total_markers": len(markers)
            }
            
        except Exception as e:
            logger.error(f"Error adding sync marker: {e}")
            return {"success": False, "error": str(e)}
    
    def generate_audio_timeline(self, scene_id: int) -> Dict:
        """
        Generate complete audio timeline for a scene
        
        Args:
            scene_id: Scene ID
        
        Returns:
            Dict with timeline data including all tracks and markers
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                cursor.execute("""
                    SELECT id, track_id, track_name, artist, start_time, duration,
                           volume, fade_in, fade_out, sync_markers
                    FROM music_scene_sync
                    WHERE scene_id = %s
                    ORDER BY start_time
                """, (scene_id,))

                tracks = []
                for row in cursor.fetchall():
                    track = {
                        "id": row["id"],
                        "track_id": row["track_id"],
                        "track_name": row["track_name"],
                        "artist": row["artist"],
                        "start_time": row["start_time"],
                        "duration": row["duration"],
                        "volume": row["volume"],
                        "fade_in": row["fade_in"],
                        "fade_out": row["fade_out"],
                        "sync_markers": json.loads(row["sync_markers"]) if row["sync_markers"] else []
                    }
                    tracks.append(track)
            
            # Calculate total timeline duration
            max_end_time = max(
                [(t['start_time'] + t['duration']) for t in tracks if t['duration']],
                default=0.0
            )
            
            return {
                "success": True,
                "scene_id": scene_id,
                "total_duration": max_end_time,
                "tracks": tracks,
                "total_tracks": len(tracks),
                "total_markers": sum(len(t['sync_markers']) for t in tracks)
            }
            
        except Exception as e:
            logger.error(f"Error generating audio timeline: {e}")
            return {"success": False, "error": str(e)}
    
    def fetch_apple_music_track(self, track_id: str) -> Optional[Dict]:
        """
        Fetch track details from Apple Music service
        
        Args:
            track_id: Apple Music track ID
        
        Returns:
            Dict with track details or None
        """
        try:
            # Try to fetch from Apple Music service
            response = requests.get(
                f"{self.apple_music_url}/api/apple-music/track/{track_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Failed to fetch track {track_id}: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching Apple Music track: {e}")
            return None
    
    def calculate_beat_markers(
        self,
        audio_file: str,
        scene_duration: Optional[float] = None
    ) -> List[Dict]:
        """
        Auto-detect beats in audio file for synchronization
        
        Args:
            audio_file: Path to audio file
            scene_duration: Optional scene duration to limit analysis
        
        Returns:
            List of beat marker dicts with timestamps
        """
        try:
            if not Path(audio_file).exists():
                logger.error(f"Audio file not found: {audio_file}")
                return []
            
            # Load audio file
            y, sr = librosa.load(audio_file, duration=scene_duration)
            
            # Detect beats
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            beat_times = librosa.frames_to_time(beat_frames, sr=sr)
            
            # Create beat markers
            markers = []
            for i, beat_time in enumerate(beat_times):
                markers.append({
                    "timestamp": float(beat_time),
                    "event": f"beat_{i+1}",
                    "audio_cue": None,
                    "metadata": {
                        "beat_number": i + 1,
                        "tempo": float(tempo),
                        "auto_detected": True
                    }
                })
            
            logger.info(f"Detected {len(markers)} beats in {audio_file}")
            return markers
            
        except Exception as e:
            logger.error(f"Error calculating beat markers: {e}")
            return []
    
    def get_scene_music(self, scene_id: int) -> List[Dict]:
        """Get all music synced to a scene"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                cursor.execute("""
                    SELECT id, track_id, track_name, artist, start_time, duration,
                           volume, fade_in, fade_out, sync_markers
                    FROM music_scene_sync
                    WHERE scene_id = %s
                    ORDER BY start_time
                """, (scene_id,))

                music = []
                for row in cursor.fetchall():
                    music.append({
                        "id": row["id"],
                        "track_id": row["track_id"],
                        "track_name": row["track_name"],
                        "artist": row["artist"],
                        "start_time": row["start_time"],
                        "duration": row["duration"],
                        "volume": row["volume"],
                        "fade_in": row["fade_in"],
                        "fade_out": row["fade_out"],
                        "sync_markers": json.loads(row["sync_markers"]) if row["sync_markers"] else []
                    })

                return music
            
        except Exception as e:
            logger.error(f"Error getting scene music: {e}")
            return []

# Convenience functions for API use
music_engine = MusicSyncEngine()

def sync_music_to_scene(scene_id: int, playlist_id: Optional[str], track_mappings: List[Dict]) -> Dict:
    """Sync music tracks to a scene"""
    return music_engine.sync_music_to_scene(scene_id, playlist_id, track_mappings)

def add_sync_marker(scene_id: int, track_id: str, timestamp: float, event_name: str,
                   audio_cue: Optional[str] = None, metadata: Optional[Dict] = None) -> Dict:
    """Add a timing marker to a track"""
    return music_engine.add_sync_marker(scene_id, track_id, timestamp, event_name, audio_cue, metadata)

def generate_audio_timeline(scene_id: int) -> Dict:
    """Generate complete audio timeline for a scene"""
    return music_engine.generate_audio_timeline(scene_id)

def fetch_apple_music_track(track_id: str) -> Optional[Dict]:
    """Fetch track from Apple Music"""
    return music_engine.fetch_apple_music_track(track_id)

def calculate_beat_markers(audio_file: str, scene_duration: Optional[float] = None) -> List[Dict]:
    """Auto-detect beats for sync"""
    return music_engine.calculate_beat_markers(audio_file, scene_duration)

if __name__ == "__main__":
    # Test the music sync system
    print("Music Sync Engine initialized")
    print(f"Database: PostgreSQL anime_production at {music_engine.db_config['host']}:{music_engine.db_config['port']}")
