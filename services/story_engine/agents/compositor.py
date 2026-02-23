"""
Compositor Agent
Assembles final video output from visual assets, audio, and subtitles.
"""

import json
import logging
import os
import subprocess
from typing import List, Dict, Optional
import tempfile

import sys
sys.path.insert(0, '/opt/anime-studio')

from services.story_engine.story_manager import StoryManager

logger = logging.getLogger(__name__)


class Compositor:
    """
    Assembles final video from generated assets.

    Workflow:
    1. Take visual assets (images/video) from VisualAgent
    2. Take audio track from AudioAgent
    3. Generate subtitles/captions from dialogue data
    4. Composite everything using ffmpeg with effects (Ken Burns for stills, transitions, etc.)
    5. Output final video file
    """

    def __init__(self):
        self.story_manager = StoryManager()
        self.output_base = "/mnt/1TB-storage/anime_production/output"
        os.makedirs(self.output_base, exist_ok=True)

    def compose_scene(self,
                     scene_id: str,
                     visual_assets: List[str],
                     audio_path: str,
                     dialogue_data: List[Dict],
                     duration: float = None) -> dict:
        """
        Compose final video for a scene.

        Args:
            scene_id: UUID string of the scene
            visual_assets: List of image/video file paths from VisualAgent
            audio_path: Path to mixed audio from AudioAgent
            dialogue_data: Dialogue data for subtitle generation
            duration: Target duration in seconds (uses audio duration if not specified)

        Returns:
            {
                "video_path": str,         # Path to final video
                "subtitle_path": str,      # Path to SRT file
                "duration": float,         # Final duration
                "resolution": str,         # Output resolution
                "warnings": list          # Any issues
            }
        """
        scene_dir = os.path.join(self.output_base, f"scene_{scene_id}")
        os.makedirs(scene_dir, exist_ok=True)

        # Generate subtitles first
        subtitle_path = os.path.join(scene_dir, "subtitles.srt")
        self._generate_subtitles(dialogue_data, subtitle_path)

        # If no visual assets, create a black video
        if not visual_assets:
            visual_assets = [self._create_placeholder_image(scene_dir)]

        # Determine duration from audio if not specified
        if not duration and audio_path and os.path.exists(audio_path):
            duration = self._get_audio_duration(audio_path)
        elif not duration:
            duration = 10.0  # Default duration

        # Build video from assets
        if len(visual_assets) == 1 and visual_assets[0].endswith(('.mp4', '.webm', '.mov')):
            # Single video file - just add audio and subtitles
            temp_video = visual_assets[0]
        else:
            # Images - create slideshow with Ken Burns effect
            temp_video = os.path.join(scene_dir, "temp_video.mp4")
            self._create_slideshow(visual_assets, temp_video, duration)

        # Compose final video with audio and subtitles
        final_video = os.path.join(scene_dir, "final.mp4")
        self._compose_final(temp_video, audio_path, subtitle_path, final_video, duration)

        return {
            "video_path": final_video,
            "subtitle_path": subtitle_path,
            "duration": duration,
            "resolution": "1920x1080",
            "warnings": []
        }

    def _generate_subtitles(self, dialogue_data: List[Dict], output_path: str) -> None:
        """Generate SRT subtitle file from dialogue data."""
        srt_lines = []
        for idx, dialogue in enumerate(dialogue_data):
            if not dialogue.get("line"):
                continue

            # Calculate timing (simple approach - 3 seconds per line)
            start_time = dialogue.get("timing_offset", idx * 3.0)
            end_time = start_time + 3.0

            # Format as SRT
            srt_lines.append(str(idx + 1))
            srt_lines.append(f"{self._format_srt_time(start_time)} --> {self._format_srt_time(end_time)}")

            # Add character name if present
            char_name = dialogue.get("character_name", "")
            if char_name:
                srt_lines.append(f"{char_name}: {dialogue['line']}")
            else:
                srt_lines.append(dialogue["line"])
            srt_lines.append("")  # Empty line between entries

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_lines))

    def _format_srt_time(self, seconds: float) -> str:
        """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _create_placeholder_image(self, output_dir: str) -> str:
        """Create a black placeholder image if no visuals provided."""
        placeholder_path = os.path.join(output_dir, "placeholder.png")
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=black:s=1920x1080:d=1",
            "-frames:v", "1",
            placeholder_path
        ], capture_output=True)
        return placeholder_path

    def _get_audio_duration(self, audio_path: str) -> float:
        """Get duration of audio file."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            return float(result.stdout.strip())
        except:
            return 10.0

    def _create_slideshow(self, images: List[str], output_path: str, duration: float) -> None:
        """Create video slideshow from images with Ken Burns effect."""
        if not images:
            return

        # Calculate duration per image
        time_per_image = duration / len(images)

        # Build filter for Ken Burns effect on each image
        inputs = []
        filter_parts = []

        for idx, img_path in enumerate(images):
            inputs.extend(["-loop", "1", "-t", str(time_per_image), "-i", img_path])

            # Ken Burns effect: slow zoom and pan
            # Random between zoom in and zoom out for variety
            if idx % 2 == 0:
                # Zoom in
                filter_parts.append(
                    f"[{idx}]scale=2560:1440,zoompan=z='zoom+0.002':d={int(time_per_image*25)}:s=1920x1080[v{idx}]"
                )
            else:
                # Zoom out
                filter_parts.append(
                    f"[{idx}]scale=2560:1440,zoompan=z='if(lte(zoom,1.0),1.3,max(1.001,zoom-0.002))':d={int(time_per_image*25)}:s=1920x1080[v{idx}]"
                )

        # Concatenate all video streams
        concat_inputs = "".join([f"[v{idx}]" for idx in range(len(images))])
        filter_parts.append(f"{concat_inputs}concat=n={len(images)}:v=1:a=0[out]")

        filter_complex = ";".join(filter_parts)

        # Build ffmpeg command
        cmd = ["ffmpeg", "-y"]
        cmd.extend(inputs)
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", "25",
            output_path
        ])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Slideshow creation error: {result.stderr}")

    def _compose_final(self,
                      video_path: str,
                      audio_path: Optional[str],
                      subtitle_path: Optional[str],
                      output_path: str,
                      duration: float) -> None:
        """Compose final video with audio and subtitles."""
        cmd = ["ffmpeg", "-y"]

        # Input video
        cmd.extend(["-i", video_path])

        # Input audio if available
        if audio_path and os.path.exists(audio_path):
            cmd.extend(["-i", audio_path])

        # Add subtitles if available
        vf_filters = []
        if subtitle_path and os.path.exists(subtitle_path):
            # Escape special characters in path for ffmpeg filter
            escaped_path = subtitle_path.replace(":", "\\:").replace("'", "\\'")
            vf_filters.append(f"subtitles='{escaped_path}':force_style='Fontsize=24,PrimaryColour=&HFFFFFF&'")

        # Apply video filters if any
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])

        # Output settings
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-pix_fmt", "yuv420p"
        ])

        # Audio settings if we have audio
        if audio_path and os.path.exists(audio_path):
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest"  # Match shortest stream duration
            ])
        else:
            # No audio - just use video duration
            cmd.extend(["-t", str(duration)])

        cmd.append(output_path)

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Final composition error: {result.stderr}")

    def compose_episode(self, episode_id: str, scene_videos: List[Dict]) -> dict:
        """
        Compose full episode from multiple scene videos.

        Args:
            episode_id: Episode UUID
            scene_videos: List of {"scene_id": str, "video_path": str, "order": int}

        Returns:
            {
                "episode_path": str,
                "duration": float,
                "scene_count": int
            }
        """
        if not scene_videos:
            return {"error": "No scene videos provided", "episode_path": None}

        # Sort by order
        scene_videos.sort(key=lambda x: x.get("order", 0))

        episode_dir = os.path.join(self.output_base, f"episode_{episode_id}")
        os.makedirs(episode_dir, exist_ok=True)

        # Create concat file for ffmpeg
        concat_file = os.path.join(episode_dir, "concat.txt")
        with open(concat_file, "w") as f:
            for scene in scene_videos:
                if os.path.exists(scene["video_path"]):
                    f.write(f"file '{scene['video_path']}'\n")

        # Concatenate all scenes
        output_path = os.path.join(episode_dir, "episode.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Episode composition error: {result.stderr}")
            return {"error": "Composition failed", "episode_path": None}

        # Get final duration
        duration = self._get_audio_duration(output_path)

        return {
            "episode_path": output_path,
            "duration": duration,
            "scene_count": len(scene_videos)
        }