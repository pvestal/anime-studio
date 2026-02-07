"""
Audio Agent
Generates TTS dialogue, background music, and final audio mix for scenes.
"""

import json
import logging
import os
import subprocess
from typing import Optional, List, Dict
import tempfile
import uuid

import sys
sys.path.insert(0, '/opt/tower-anime-production')

from services.story_engine.story_manager import StoryManager

logger = logging.getLogger(__name__)

# Check for available TTS (edge-tts is lightweight and free)
try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False
    logger.warning("edge-tts not installed. Install with: pip install edge-tts")

# Voice mapping for characters
DEFAULT_VOICES = {
    "Patrick": "en-US-BrianNeural",      # Approachable, casual male voice (the human protagonist)
    "Claude": "en-US-ChristopherNeural", # Reliable, authoritative voice (overly helpful AI)
    "Claude Code": "en-US-AndrewNeural", # Warm, confident voice (the practical version)
    "DeepSeek": "en-US-EricNeural",      # Different male voice (the terse coder)
    "Echo": "en-US-AvaNeural",           # Expressive female voice (the system that won't work)
    "The Void": "en-US-GuyNeural",       # Deep, ominous voice
    "default": "en-US-AriaNeural"        # Default female voice
}


class AudioAgent:
    """
    Generates audio content for scenes: TTS dialogue, background music, sound effects.

    Workflow:
    1. Take dialogue lines from WritingAgent output
    2. Map each character to their TTS voice (from voice_profile in DB)
    3. Generate TTS for each line
    4. Mix dialogue with background music based on audio_mood
    5. Output final mixed audio file
    """

    def __init__(self):
        self.story_manager = StoryManager()
        self.output_base = "/mnt/1TB-storage/anime_production/audio"
        os.makedirs(self.output_base, exist_ok=True)

    async def generate_scene_audio(self, scene_id: str, dialogue_data: List[Dict]) -> dict:
        """
        Generate complete audio for a scene.

        Args:
            scene_id: UUID string of the scene
            dialogue_data: List of dialogue entries from WritingAgent:
                [{"character_name": str, "line": str, "emotion": str, "timing_offset": float}, ...]

        Returns:
            {
                "audio_path": str,           # Path to final mixed audio
                "dialogue_tracks": list,     # Individual dialogue files
                "duration": float,           # Total duration in seconds
                "warnings": list             # Any issues encountered
            }
        """
        if not HAS_EDGE_TTS:
            return {
                "error": "TTS not available. Install edge-tts: pip install edge-tts",
                "audio_path": None,
                "dialogue_tracks": [],
                "duration": 0.0,
                "warnings": ["edge-tts not installed"]
            }

        # Get scene context for audio mood
        context = self.story_manager.get_scene_with_context(scene_id)
        if not context:
            raise ValueError(f"Scene {scene_id} not found")

        scene_dir = os.path.join(self.output_base, f"scene_{scene_id}")
        os.makedirs(scene_dir, exist_ok=True)

        # Generate TTS for each dialogue line
        dialogue_tracks = []
        for idx, dialogue in enumerate(dialogue_data):
            if not dialogue.get("line"):
                continue

            # Get voice for character
            char_name = dialogue.get("character_name", "default")
            voice = self._get_character_voice(context, char_name)

            # Generate TTS
            output_file = os.path.join(scene_dir, f"dialogue_{idx:03d}_{char_name}.mp3")
            await self._generate_tts(dialogue["line"], voice, output_file, dialogue.get("emotion"))

            if os.path.exists(output_file):
                dialogue_tracks.append({
                    "file": output_file,
                    "character": char_name,
                    "timing_offset": dialogue.get("timing_offset", idx * 3.0)
                })

        # Mix dialogue tracks into final audio
        final_audio = os.path.join(scene_dir, "final_audio.mp3")
        duration = self._mix_audio_tracks(dialogue_tracks, final_audio,
                                         audio_mood=context["scene"].get("audio_mood", "neutral"))

        return {
            "audio_path": final_audio,
            "dialogue_tracks": dialogue_tracks,
            "duration": duration,
            "warnings": []
        }

    def _get_character_voice(self, context: dict, character_name: str) -> str:
        """Map character to TTS voice based on voice_profile in DB or defaults."""
        # First check if character has a voice_profile in the DB
        for char in context.get("characters", []):
            if char["name"] == character_name and char.get("voice_profile"):
                profile = char["voice_profile"]
                if isinstance(profile, dict):
                    return profile.get("tts_voice", DEFAULT_VOICES.get(character_name, DEFAULT_VOICES["default"]))
                elif isinstance(profile, str):
                    # If it's a direct voice name
                    return profile

        # Fallback to defaults
        return DEFAULT_VOICES.get(character_name, DEFAULT_VOICES["default"])

    async def _generate_tts(self, text: str, voice: str, output_file: str, emotion: Optional[str] = None) -> None:
        """Generate TTS using edge-tts."""
        # Create TTS with edge-tts
        # Note: edge-tts may not support rate/pitch directly in Communicate
        # Using default parameters for now
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)

    def _mix_audio_tracks(self, dialogue_tracks: List[Dict], output_file: str, audio_mood: str = "neutral") -> float:
        """Mix dialogue tracks together using ffmpeg."""
        if not dialogue_tracks:
            # Create silent audio if no dialogue
            subprocess.run([
                "ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=5",
                "-y", output_file
            ], capture_output=True)
            return 5.0

        # Build ffmpeg filter for mixing dialogue at different time offsets
        inputs = []
        filter_parts = []

        for idx, track in enumerate(dialogue_tracks):
            inputs.extend(["-i", track["file"]])
            delay_ms = int(track["timing_offset"] * 1000)
            filter_parts.append(f"[{idx}]adelay={delay_ms}|{delay_ms}[d{idx}]")

        # Mix all delayed tracks
        mix_inputs = "".join([f"[d{idx}]" for idx in range(len(dialogue_tracks))])
        filter_parts.append(f"{mix_inputs}amix=inputs={len(dialogue_tracks)}:duration=longest")

        filter_complex = ";".join(filter_parts)

        # Run ffmpeg
        cmd = ["ffmpeg", "-y"]
        cmd.extend(inputs)
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-ac", "2", "-ar", "44100", output_file])

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"ffmpeg error: {result.stderr}")
            return 0.0

        # Get duration of final audio
        probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", output_file]
        duration_result = subprocess.run(probe_cmd, capture_output=True, text=True)

        try:
            duration = float(duration_result.stdout.strip())
        except:
            duration = 10.0  # Default fallback

        return duration


# Synchronous wrapper for use in non-async contexts
def generate_scene_audio_sync(scene_id: str, dialogue_data: List[Dict]) -> dict:
    """Synchronous wrapper for generate_scene_audio."""
    import asyncio
    agent = AudioAgent()
    return asyncio.run(agent.generate_scene_audio(scene_id, dialogue_data))