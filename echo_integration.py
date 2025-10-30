#!/usr/bin/env python3
'''
Enhanced Echo Brain integration for anime production with git storyline control
'''

import requests
import json
import asyncio
import aiohttp
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class EchoIntegration:
    def __init__(self, echo_url='http://localhost:8309'):
        self.echo_url = echo_url
        
    async def request_quality_assessment(self, video_path, prompt, metadata):
        '''Request quality assessment through Echo'''
        task = {
            'name': 'quality_assessment',
            'type': 'LEARNING',
            'priority': 'NORMAL',
            'data': {
                'video_path': video_path,
                'prompt': prompt,
                'metadata': metadata
            }
        }
        
        response = requests.post(f'{self.echo_url}/api/tasks/add', json=task)
        return response.json()
        
    async def report_generation_complete(self, generation_id, output_path):
        '''Report completion to Echo for orchestration'''
        response = requests.post(f'{self.echo_url}/api/evaluate', json={
            'task_id': generation_id,
            'output': output_path,
            'service': 'anime_generation'
        })
        return response.json()
        
    async def request_feedback_collection(self, generation_id, quality_score):
        '''Ask Echo to collect feedback'''
        if quality_score < 70:
            task = {
                'name': 'collect_feedback',
                'type': 'OPTIMIZATION',
                'data': {
                    'generation_id': generation_id,
                    'quality_score': quality_score,
                    'action': 'improve_prompt'
                }
            }
            response = requests.post(f'{self.echo_url}/api/tasks/add', json=task)
            return response.json()

    # === GIT STORYLINE COORDINATION ===

    async def create_storyline_markers(self, project_id: int, scenes: List[Dict]) -> Dict[str, Any]:
        """
        Create storyline markers for precise video editing and re-generation

        Args:
            project_id: Project ID
            scenes: List of scene data with timing information

        Returns:
            Dict with marker metadata for editing
        """
        markers = {
            "project_id": project_id,
            "created_at": datetime.now().isoformat(),
            "total_scenes": len(scenes),
            "editing_markers": [],
            "git_references": {},
            "echo_analysis_points": []
        }

        cumulative_frames = 0

        for i, scene in enumerate(scenes):
            scene_duration = scene.get('duration_frames', 24)  # Default 1 second at 24fps

            # Create comprehensive editing marker
            marker = {
                "scene_id": i,
                "scene_name": scene.get('name', f"Scene_{i+1}"),
                "git_commit": scene.get('commit_hash', None),
                "frames": {
                    "start": cumulative_frames,
                    "end": cumulative_frames + scene_duration,
                    "duration": scene_duration
                },
                "timecode": {
                    "start": self._frames_to_timecode(cumulative_frames),
                    "end": self._frames_to_timecode(cumulative_frames + scene_duration),
                    "duration": self._frames_to_timecode(scene_duration)
                },
                "narrative": {
                    "story_beat": scene.get('story_beat', 'unknown'),
                    "character_focus": scene.get('characters', []),
                    "emotion_tone": scene.get('emotion', 'neutral')
                },
                "technical": {
                    "prompt": scene.get('prompt', ''),
                    "style": scene.get('style', 'anime'),
                    "quality_target": scene.get('quality', 'high')
                },
                "editing_notes": {
                    "transition_in": scene.get('transition_in', 'cut'),
                    "transition_out": scene.get('transition_out', 'cut'),
                    "music_sync": scene.get('music_cue', None),
                    "echo_recommendations": []
                }
            }

            markers["editing_markers"].append(marker)
            cumulative_frames += scene_duration

        # Add Echo Brain analysis for each marker
        markers["echo_analysis_points"] = await self._get_echo_editing_analysis(markers)

        return markers

    def _frames_to_timecode(self, frames: int, fps: int = 24) -> str:
        """Convert frame number to HH:MM:SS:FF timecode"""
        total_seconds = frames // fps
        remaining_frames = frames % fps
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{remaining_frames:02d}"

    async def _get_echo_editing_analysis(self, markers: Dict) -> List[Dict]:
        """Get Echo Brain's analysis of optimal editing points"""
        try:
            analysis_prompt = f"""
            Analyze these anime storyline markers for optimal editing and narrative flow:

            Project: {markers['project_id']}
            Total Scenes: {markers['total_scenes']}

            Scene Breakdown:
            {json.dumps(markers['editing_markers'], indent=2)}

            For each scene, recommend:
            1. Optimal cut points for editing
            2. Transition suggestions between scenes
            3. Music/audio sync points
            4. Visual continuity requirements
            5. Pacing adjustments
            6. Re-generation opportunities

            Focus on creating smooth, professional anime editing flow.
            """

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.echo_url}/api/echo/analyze",
                    json={
                        "query": analysis_prompt,
                        "context": {"type": "editing_analysis", "project_id": markers['project_id']}
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get('editing_recommendations', [])

            return []

        except Exception as e:
            logger.error(f"Echo editing analysis failed: {e}")
            return []

    async def embed_video_markers(self, video_path: str, markers: Dict) -> str:
        """
        Embed editing markers directly into video metadata using ffmpeg

        Args:
            video_path: Path to video file
            markers: Marker metadata to embed

        Returns:
            Path to video with embedded markers
        """
        import subprocess
        import tempfile
        from pathlib import Path

        video_path = Path(video_path)
        output_path = video_path.parent / f"{video_path.stem}_with_markers{video_path.suffix}"

        # Create metadata file for ffmpeg
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as meta_file:
            # Write ffmpeg metadata format
            meta_file.write(";FFMETADATA1\n")
            meta_file.write(f"title=Anime Project {markers['project_id']}\n")
            meta_file.write(f"creation_time={markers['created_at']}\n")
            meta_file.write(f"echo_analysis=true\n")
            meta_file.write(f"storyline_markers={json.dumps(markers)}\n")

            # Add chapter markers for each scene
            for marker in markers['editing_markers']:
                start_ms = (marker['frames']['start'] * 1000) // 24  # Convert to milliseconds
                end_ms = (marker['frames']['end'] * 1000) // 24

                meta_file.write("\n[CHAPTER]\n")
                meta_file.write("TIMEBASE=1/1000\n")
                meta_file.write(f"START={start_ms}\n")
                meta_file.write(f"END={end_ms}\n")
                meta_file.write(f"title={marker['scene_name']}\n")

            meta_file_path = meta_file.name

        try:
            # Use ffmpeg to embed metadata
            cmd = [
                'ffmpeg', '-i', str(video_path),
                '-i', meta_file_path,
                '-map_metadata', '1',
                '-codec', 'copy',
                '-y', str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                logger.info(f"✅ Embedded markers in video: {output_path}")
                return str(output_path)
            else:
                logger.error(f"FFmpeg marker embedding failed: {result.stderr}")
                return str(video_path)  # Return original if embedding fails

        except Exception as e:
            logger.error(f"Video marker embedding failed: {e}")
            return str(video_path)
        finally:
            # Clean up temp file
            try:
                Path(meta_file_path).unlink()
            except:
                pass

    async def coordinate_git_storyline_generation(self, project_data: Dict) -> Dict[str, Any]:
        """
        Complete workflow: Generate video → Create git commit → Echo analysis → Embed markers

        Args:
            project_data: Complete project data with scenes

        Returns:
            Dict with complete workflow results
        """
        project_id = project_data.get('id')
        scenes = project_data.get('scenes', [])

        workflow_result = {
            "project_id": project_id,
            "workflow_started": datetime.now().isoformat(),
            "steps": {},
            "final_outputs": {}
        }

        try:
            # Step 1: Create storyline markers
            workflow_result["steps"]["markers"] = await self.create_storyline_markers(project_id, scenes)

            # Step 2: Import git branching functions
            try:
                from git_branching import echo_analyze_storyline, echo_guided_branch_creation

                # Step 3: Create git branch with Echo guidance
                branch_name = f"project_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                workflow_result["steps"]["git_branch"] = await echo_guided_branch_creation(
                    project_id=project_id,
                    base_branch='main',
                    new_branch_name=branch_name,
                    storyline_goal=project_data.get('description', 'Anime generation project')
                )

                # Step 4: Get Echo storyline analysis
                workflow_result["steps"]["echo_analysis"] = await echo_analyze_storyline(project_id, branch_name)

            except ImportError:
                logger.warning("Git branching module not available")
                workflow_result["steps"]["git_branch"] = {"error": "Git module unavailable"}
                workflow_result["steps"]["echo_analysis"] = {"error": "Git module unavailable"}

            # Step 5: Mark workflow complete
            workflow_result["workflow_completed"] = datetime.now().isoformat()
            workflow_result["final_outputs"] = {
                "editing_markers": workflow_result["steps"]["markers"],
                "git_branch": workflow_result["steps"]["git_branch"].get("branch", {}).get("branch_name"),
                "echo_recommendations": workflow_result["steps"]["echo_analysis"].get("recommendations", [])
            }

            return workflow_result

        except Exception as e:
            logger.error(f"Git storyline workflow failed: {e}")
            workflow_result["error"] = str(e)
            return workflow_result
