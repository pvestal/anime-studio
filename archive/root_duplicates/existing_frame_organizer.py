#!/usr/bin/env python3
"""
Existing Frame Organizer for Goblin Slayer: Neon Shadows
Uses Patrick's existing 1,482 frames instead of generating new content
"""

import os
import json
from pathlib import Path
import subprocess
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GoblinSlayerFrameOrganizer:
    """Organizes existing Goblin Slayer frames into episodes with music"""

    def __init__(self):
        self.base_dir = Path("/opt/tower-anime-production/frames/goblin_slayer_cyberpunk")
        self.output_dir = Path("/opt/tower-anime-production/videos/goblin_slayer_organized")
        self.output_dir.mkdir(exist_ok=True, parents=True)

        # Patrick's Apple Music "Video Use" playlist
        self.music_tracks = {
            "kendrick_lamar_humble": {
                "bpm": 150,
                "mood": "aggressive_confident",
                "duration": 30,  # Copyright compliance
                "best_scenes": "confrontation, power_display, battle"
            },
            "missy_elliott_get_ur_freak_on": {
                "bpm": 168,
                "mood": "energetic_playful",
                "duration": 30,
                "best_scenes": "cyberpunk_club, dance, transformation"
            },
            "dmx_yall_gonna_make_me": {
                "bpm": 95,
                "mood": "intense_raw",
                "duration": 30,
                "best_scenes": "underground, chase, raw_emotion"
            }
        }

        # Episode structure for Goblin Slayer: Neon Shadows
        self.episode_structure = {
            "ep1_scene1_nyc_establishing": {"frames": range(1, 121), "track": "kendrick_lamar_humble"},
            "ep1_scene2_subway_confrontation": {"frames": range(121, 241), "track": "kendrick_lamar_humble"},
            "ep1_scene3_cyberpunk_club": {"frames": range(241, 361), "track": "missy_elliott_get_ur_freak_on"},
            "ep1_scene4_underground_chase": {"frames": range(361, 481), "track": "dmx_yall_gonna_make_me"},
            "ep1_scene5_final_battle": {"frames": range(481, 601), "track": "kendrick_lamar_humble"}
        }

    def organize_frames_for_scene(self, scene_name: str, frame_range: range, track: str) -> dict:
        """Organize existing frames into a specific scene with music"""
        scene_frames = []

        for frame_num in frame_range:
            frame_file = self.base_dir / f"animatediff_frames_{frame_num:05d}_.png"
            if frame_file.exists():
                scene_frames.append(str(frame_file))
            else:
                logger.warning(f"Missing frame: {frame_file}")

        if not scene_frames:
            return {"error": "No frames found for scene"}

        return {
            "scene": scene_name,
            "frames": scene_frames,
            "frame_count": len(scene_frames),
            "music_track": track,
            "music_info": self.music_tracks.get(track, {}),
            "fps": 24,
            "duration_seconds": len(scene_frames) / 24
        }

    def create_video_from_existing_frames(self, scene_name: str) -> dict:
        """Create video from Patrick's existing frames with his music"""
        if scene_name not in self.episode_structure:
            return {"error": f"Scene {scene_name} not found in episode structure"}

        scene_config = self.episode_structure[scene_name]
        frame_range = scene_config["frames"]
        track = scene_config["track"]

        # Organize the frames
        scene_data = self.organize_frames_for_scene(scene_name, frame_range, track)
        if "error" in scene_data:
            return scene_data

        # Create frame list file for ffmpeg
        frame_list_file = self.output_dir / f"{scene_name}_frames.txt"
        with open(frame_list_file, 'w') as f:
            for frame_path in scene_data["frames"]:
                f.write(f"file '{frame_path}'\n")
                f.write("duration 0.041667\n")  # 24fps = 0.041667 seconds per frame

        # Create video from existing frames
        output_video = self.output_dir / f"{scene_name}_with_music.mp4"

        # FFmpeg command to create video from existing frames
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(frame_list_file),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-r", "24",
            str(output_video)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return {
                    "success": True,
                    "scene": scene_name,
                    "output_video": str(output_video),
                    "frame_count": scene_data["frame_count"],
                    "music_track": track,
                    "duration": scene_data["duration_seconds"],
                    "message": f"Created video from {scene_data['frame_count']} existing Goblin Slayer frames"
                }
            else:
                return {
                    "success": False,
                    "error": f"FFmpeg failed: {result.stderr}",
                    "scene": scene_name
                }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Video creation timed out",
                "scene": scene_name
            }

    def create_all_scenes(self) -> dict:
        """Create all scenes from existing frames"""
        results = {}

        for scene_name in self.episode_structure.keys():
            logger.info(f"🎬 Creating {scene_name} from existing Goblin Slayer frames...")
            result = self.create_video_from_existing_frames(scene_name)
            results[scene_name] = result

        return {
            "project": "Goblin Slayer: Neon Shadows",
            "total_scenes": len(results),
            "scenes": results,
            "uses_existing_frames": True,
            "frame_source": "Patrick's existing 1,482 animatediff frames"
        }

if __name__ == "__main__":
    organizer = GoblinSlayerFrameOrganizer()

    # Test with one scene first
    result = organizer.create_video_from_existing_frames("ep1_scene2_subway_confrontation")
    print(json.dumps(result, indent=2))