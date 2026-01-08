"""Scene Generator for FramePack video production.

Generates all segments for a scene, chains them via last-frame extraction,
and concatenates into final scene video with quality feedback.
"""

import asyncio
import json
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from services.framepack.echo_brain_memory import EchoBrainMemory
from services.framepack.quality_analyzer import QualityAnalyzer, QualityMetrics

logger = logging.getLogger(__name__)


@dataclass
class SegmentResult:
    """Result of a segment generation."""

    segment_id: int
    segment_number: int
    video_path: Optional[str]
    quality_metrics: Optional[QualityMetrics]
    success: bool
    error: Optional[str] = None


@dataclass
class SceneResult:
    """Result of a complete scene generation."""

    scene_id: int
    final_video_path: Optional[str]
    segments: List[SegmentResult]
    total_duration: float
    average_quality: float
    success: bool


class SceneGenerator:
    """Generates complete scenes using FramePack segments.

    Features:
    - Segment chaining via first/last frame anchoring
    - Quality analysis after each segment
    - Automatic quality feedback recording
    - Final scene concatenation with ffmpeg
    """

    def __init__(
        self,
        database_url: str,
        comfyui_url: str = "http://localhost:8188",
        output_dir: str = "/mnt/1TB-storage/ComfyUI/output/framepack",
        models_dir: str = "/mnt/1TB-storage/models",
    ):
        """Initialize Scene Generator.

        Args:
            database_url: PostgreSQL connection URL
            comfyui_url: ComfyUI server URL
            output_dir: Directory for output videos
            models_dir: Directory containing FramePack models
        """
        self.memory = EchoBrainMemory(database_url)
        self.quality_analyzer = QualityAnalyzer()
        self.comfyui_url = comfyui_url
        self.output_dir = Path(output_dir)
        self.models_dir = Path(models_dir)

        # FramePack model paths
        self.framepack_model = "diffusion_models/FramePackI2V_HY_fp8_e4m3fn.safetensors"

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def connect(self) -> None:
        """Initialize connections."""
        await self.memory.connect()

    async def close(self) -> None:
        """Close connections."""
        await self.memory.close()

    async def generate_scene(self, scene_id: int) -> SceneResult:
        """Generate all segments for a scene, analyze quality, combine into video.

        This is the main entry point for scene generation.

        Args:
            scene_id: Database ID of the scene to generate

        Returns:
            SceneResult with all segment results and final video
        """
        logger.info(f"Starting generation for scene {scene_id}")

        # Get scene context
        context = await self.memory.get_scene_context(scene_id)
        if not context:
            logger.error(f"Scene {scene_id} not found")
            return SceneResult(
                scene_id=scene_id,
                final_video_path=None,
                segments=[],
                total_duration=0,
                average_quality=0,
                success=False,
            )

        # Get scene configuration from database
        scene_config = await self._get_scene_config(scene_id)
        if not scene_config:
            logger.error(f"Could not get scene config for {scene_id}")
            return SceneResult(
                scene_id=scene_id,
                final_video_path=None,
                segments=[],
                total_duration=0,
                average_quality=0,
                success=False,
            )

        # Calculate number of segments needed
        target_duration = scene_config.get("target_duration_seconds", 30)
        segment_duration = 30  # FramePack default
        num_segments = max(1, (target_duration + segment_duration - 1) // segment_duration)

        logger.info(f"Scene {scene_id}: {num_segments} segments for {target_duration}s video")

        # Generate segments sequentially (each needs previous frame)
        segments: List[SegmentResult] = []
        segment_paths: List[str] = []
        current_first_frame = scene_config.get("entry_keyframe_path")

        for seg_num in range(1, num_segments + 1):
            # Generate motion prompt from memory
            action = scene_config.get("actions", {}).get(seg_num, "character moves naturally")
            positive_prompt, negative_prompt = await self.memory.generate_motion_prompt(
                scene_id, seg_num, action
            )

            # Get or create segment record
            segment_id = await self._get_or_create_segment(
                scene_id, seg_num, positive_prompt, negative_prompt, current_first_frame
            )

            # Generate the segment
            result = await self._generate_segment(
                scene_id=scene_id,
                segment_id=segment_id,
                segment_num=seg_num,
                first_frame=current_first_frame,
                last_frame=None,  # FramePack will determine end frame
                prompt=positive_prompt,
                negative_prompt=negative_prompt,
            )

            segments.append(result)

            if result.success and result.video_path:
                segment_paths.append(result.video_path)

                # Extract last frame for next segment
                last_frame = await self._extract_last_frame(result.video_path)
                if last_frame:
                    current_first_frame = last_frame
                    await self._update_segment_frames(segment_id, last_frame_path=last_frame)

                # Record quality feedback (the learning loop)
                if result.quality_metrics:
                    char_id = context.characters[0].character_id if context.characters else None
                    await self.memory.record_quality_feedback(
                        segment_id=segment_id,
                        metrics={
                            "overall_score": result.quality_metrics.overall_score,
                            "frame_consistency_score": result.quality_metrics.frame_consistency_score,
                            "motion_smoothness_score": result.quality_metrics.motion_smoothness_score,
                            "parameters": {
                                "prompt": positive_prompt,
                                "negative_prompt": negative_prompt,
                                "segment_duration": segment_duration,
                            },
                        },
                        prompt=positive_prompt,
                        character_id=char_id,
                    )
            else:
                logger.error(f"Segment {seg_num} failed: {result.error}")
                # Continue with other segments

        # Concatenate successful segments
        final_video_path = None
        if segment_paths:
            final_video_path = await self._concatenate_segments(scene_id, segment_paths)

        # Update scene status
        await self._update_scene_status(
            scene_id,
            final_video_path=final_video_path,
            exit_keyframe=current_first_frame,  # Last frame of last segment
            completed_segments=len([s for s in segments if s.success]),
        )

        # Calculate totals
        total_duration = sum(
            self.quality_analyzer.get_video_info(s.video_path).get("duration", 0)
            if s.video_path
            else 0
            for s in segments
        )
        avg_quality = (
            sum(s.quality_metrics.overall_score for s in segments if s.quality_metrics)
            / len([s for s in segments if s.quality_metrics])
            if any(s.quality_metrics for s in segments)
            else 0
        )

        success = final_video_path is not None and len(segment_paths) > 0

        # Propagate state to next scene
        if success:
            await self.memory.propagate_to_next_scene(scene_id)

        return SceneResult(
            scene_id=scene_id,
            final_video_path=final_video_path,
            segments=segments,
            total_duration=total_duration,
            average_quality=avg_quality,
            success=success,
        )

    async def _generate_segment(
        self,
        scene_id: int,
        segment_id: int,
        segment_num: int,
        first_frame: Optional[str],
        last_frame: Optional[str],
        prompt: str,
        negative_prompt: str,
    ) -> SegmentResult:
        """Generate a single FramePack segment.

        Args:
            scene_id: Scene ID
            segment_id: Database segment ID
            segment_num: Segment number within scene
            first_frame: Path to first frame anchor image
            last_frame: Path to last frame anchor (optional)
            prompt: Positive motion prompt
            negative_prompt: Negative prompt

        Returns:
            SegmentResult with video path and quality metrics
        """
        logger.info(f"Generating segment {segment_num} for scene {scene_id}")

        try:
            # Build FramePack workflow
            workflow = self._build_framepack_workflow(
                scene_id=scene_id,
                segment_num=segment_num,
                first_frame=first_frame,
                last_frame=last_frame,
                prompt=prompt,
                negative_prompt=negative_prompt,
            )

            # Submit to ComfyUI
            prompt_id = await self._submit_to_comfyui(workflow)
            if not prompt_id:
                return SegmentResult(
                    segment_id=segment_id,
                    segment_number=segment_num,
                    video_path=None,
                    quality_metrics=None,
                    success=False,
                    error="Failed to submit to ComfyUI",
                )

            # Update segment with comfyui_prompt_id
            await self._update_segment_status(segment_id, "processing", prompt_id)

            # Wait for completion
            output_path = await self._wait_for_completion(prompt_id)
            if not output_path:
                await self._update_segment_status(segment_id, "failed")
                return SegmentResult(
                    segment_id=segment_id,
                    segment_number=segment_num,
                    video_path=None,
                    quality_metrics=None,
                    success=False,
                    error="Generation timed out or failed",
                )

            # Analyze quality
            quality_metrics = self.quality_analyzer.analyze_video(output_path)

            # Update segment with results
            await self._update_segment_completed(
                segment_id,
                output_path,
                quality_metrics.overall_score,
                quality_metrics.frame_consistency_score,
                quality_metrics.motion_smoothness_score,
            )

            return SegmentResult(
                segment_id=segment_id,
                segment_number=segment_num,
                video_path=output_path,
                quality_metrics=quality_metrics,
                success=True,
            )

        except Exception as e:
            logger.error(f"Segment generation error: {e}")
            await self._update_segment_status(segment_id, "failed", error=str(e))
            return SegmentResult(
                segment_id=segment_id,
                segment_number=segment_num,
                video_path=None,
                quality_metrics=None,
                success=False,
                error=str(e),
            )

    def _build_framepack_workflow(
        self,
        scene_id: int,
        segment_num: int,
        first_frame: Optional[str],
        last_frame: Optional[str],
        prompt: str,
        negative_prompt: str,
    ) -> Dict[str, Any]:
        """Build ComfyUI workflow for FramePack generation.

        This creates a workflow that uses:
        - FramePack I2V model for video generation
        - First/last frame anchoring for consistency
        - HunyuanVideo VAE for decoding
        """
        seed = int(time.time() * 1000) % (2**32)
        output_prefix = f"framepack/scene_{scene_id}_seg_{segment_num}"

        workflow = {
            # Load FramePack model
            "1": {
                "class_type": "FramePackHYModelLoader",
                "inputs": {
                    "model": self.framepack_model,
                    "precision": "fp8_e4m3fn",
                },
            },
            # Load VAE
            "2": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": "hunyuan_video_vae_bf16.safetensors"},
            },
            # Load CLIP
            "3": {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": "clip_l.safetensors",
                    "clip_name2": "llava_llama3_fp16.safetensors",
                    "type": "hunyuan_video",
                },
            },
            # Load CLIP Vision (for image conditioning)
            "4": {
                "class_type": "CLIPVisionLoader",
                "inputs": {"clip_name": "sigclip_vision_patch14_384.safetensors"},
            },
            # Encode positive prompt
            "5": {
                "class_type": "HYVideoCLIPTextEncode",
                "inputs": {
                    "clip": ["3", 0],
                    "prompt": prompt,
                },
            },
            # Encode negative prompt
            "6": {
                "class_type": "HYVideoCLIPTextEncode",
                "inputs": {
                    "clip": ["3", 0],
                    "prompt": negative_prompt,
                },
            },
            # Sampler settings
            "10": {
                "class_type": "FramePackSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["5", 0],
                    "negative": ["6", 0],
                    "seed": seed,
                    "steps": 20,
                    "cfg": 7.0,
                    "denoise": 1.0,
                    "num_frames": 120,  # ~4 seconds at 30fps
                    "width": 1280,
                    "height": 720,
                },
            },
            # Decode with VAE
            "11": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["10", 0],
                    "vae": ["2", 0],
                },
            },
            # Save video
            "12": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["11", 0],
                    "frame_rate": 30,
                    "loop_count": 0,
                    "filename_prefix": output_prefix,
                    "format": "video/h264-mp4",
                    "save_output": True,
                },
            },
        }

        # Add first frame conditioning if available
        if first_frame and Path(first_frame).exists():
            workflow["20"] = {
                "class_type": "LoadImage",
                "inputs": {"image": first_frame},
            }
            workflow["21"] = {
                "class_type": "CLIPVisionEncode",
                "inputs": {
                    "clip_vision": ["4", 0],
                    "image": ["20", 0],
                },
            }
            # Add image conditioning to sampler
            workflow["10"]["inputs"]["image_cond"] = ["21", 0]

        return workflow

    async def _submit_to_comfyui(self, workflow: Dict[str, Any]) -> Optional[str]:
        """Submit workflow to ComfyUI and return prompt ID."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.comfyui_url}/prompt",
                    json={"prompt": workflow},
                )

                if response.status_code == 200:
                    data = response.json()
                    prompt_id = data.get("prompt_id")
                    logger.info(f"Submitted workflow, prompt_id: {prompt_id}")
                    return prompt_id
                else:
                    logger.error(f"ComfyUI returned {response.status_code}: {response.text}")
                    return None

        except Exception as e:
            logger.error(f"Error submitting to ComfyUI: {e}")
            return None

    async def _wait_for_completion(
        self, prompt_id: str, timeout: int = 300, poll_interval: int = 5
    ) -> Optional[str]:
        """Wait for ComfyUI generation to complete.

        Args:
            prompt_id: ComfyUI prompt ID
            timeout: Maximum wait time in seconds
            poll_interval: Time between status checks

        Returns:
            Output video path if successful, None otherwise
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    # Check history for completion
                    response = await client.get(f"{self.comfyui_url}/history/{prompt_id}")

                    if response.status_code == 200:
                        history = response.json()

                        if prompt_id in history:
                            outputs = history[prompt_id].get("outputs", {})

                            # Find video output
                            for node_id, output in outputs.items():
                                if "gifs" in output:  # VHS_VideoCombine uses 'gifs' for MP4
                                    filename = output["gifs"][0]["filename"]
                                    subfolder = output["gifs"][0].get("subfolder", "")
                                    if subfolder:
                                        return str(
                                            self.output_dir.parent / subfolder / filename
                                        )
                                    return str(self.output_dir / filename)

                                if "videos" in output:
                                    filename = output["videos"][0]["filename"]
                                    return str(self.output_dir / filename)

                            # Check for errors
                            status = history[prompt_id].get("status", {})
                            if status.get("status_str") == "error":
                                logger.error(f"Generation failed: {status}")
                                return None

                    # Check queue status
                    queue_response = await client.get(f"{self.comfyui_url}/queue")
                    if queue_response.status_code == 200:
                        queue = queue_response.json()
                        # Check if still running or pending
                        running = any(
                            item[1] == prompt_id
                            for item in queue.get("queue_running", [])
                            if len(item) > 1
                        )
                        pending = any(
                            item[1] == prompt_id
                            for item in queue.get("queue_pending", [])
                            if len(item) > 1
                        )

                        if not running and not pending:
                            # Not in queue and not in history = failed
                            logger.warning(f"Prompt {prompt_id} not found in queue or history")

            except Exception as e:
                logger.warning(f"Error checking status: {e}")

            await asyncio.sleep(poll_interval)

        logger.error(f"Timeout waiting for prompt {prompt_id}")
        return None

    async def _extract_last_frame(self, video_path: str) -> Optional[str]:
        """Extract the final frame from a video for segment chaining.

        Args:
            video_path: Path to video file

        Returns:
            Path to extracted frame image
        """
        try:
            output_path = Path(video_path).with_suffix(".last_frame.png")

            cmd = [
                "ffmpeg",
                "-sseof",
                "-0.1",  # Seek to 0.1s before end
                "-i",
                video_path,
                "-vframes",
                "1",
                "-y",
                str(output_path),
                "-loglevel",
                "error",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0 and output_path.exists():
                logger.info(f"Extracted last frame: {output_path}")
                return str(output_path)
            else:
                logger.error(f"Failed to extract last frame: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"Error extracting last frame: {e}")
            return None

    async def _concatenate_segments(
        self, scene_id: int, segment_paths: List[str]
    ) -> Optional[str]:
        """Concatenate segment videos into final scene video.

        Args:
            scene_id: Scene ID for output naming
            segment_paths: List of video paths to concatenate

        Returns:
            Path to final concatenated video
        """
        if not segment_paths:
            return None

        if len(segment_paths) == 1:
            return segment_paths[0]

        try:
            output_path = self.output_dir / f"scene_{scene_id}_final.mp4"

            # Create concat file
            concat_file = self.output_dir / f"scene_{scene_id}_concat.txt"
            with open(concat_file, "w") as f:
                for path in segment_paths:
                    f.write(f"file '{path}'\n")

            cmd = [
                "ffmpeg",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                "-y",
                str(output_path),
                "-loglevel",
                "error",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            # Clean up concat file
            concat_file.unlink(missing_ok=True)

            if result.returncode == 0 and output_path.exists():
                logger.info(f"Concatenated {len(segment_paths)} segments: {output_path}")
                return str(output_path)
            else:
                logger.error(f"Concatenation failed: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"Error concatenating segments: {e}")
            return None

    # Database helper methods

    async def _get_scene_config(self, scene_id: int) -> Optional[Dict]:
        """Get scene configuration from database."""
        async with self.memory.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT target_duration_seconds, entry_keyframe_path
                FROM movie_scenes WHERE id = $1
                """,
                scene_id,
            )
            if row:
                return dict(row)
            return None

    async def _get_or_create_segment(
        self,
        scene_id: int,
        segment_num: int,
        prompt: str,
        negative_prompt: str,
        first_frame: Optional[str],
    ) -> int:
        """Get existing segment or create new one."""
        async with self.memory.pool.acquire() as conn:
            segment_id = await conn.fetchval(
                """
                INSERT INTO generation_segments (
                    scene_id, segment_number, motion_prompt, negative_prompt,
                    first_frame_path, status
                ) VALUES ($1, $2, $3, $4, $5, 'pending')
                ON CONFLICT (scene_id, segment_number) DO UPDATE SET
                    motion_prompt = EXCLUDED.motion_prompt,
                    negative_prompt = EXCLUDED.negative_prompt,
                    status = 'pending'
                RETURNING id
                """,
                scene_id,
                segment_num,
                prompt,
                negative_prompt,
                first_frame,
            )
            return segment_id

    async def _update_segment_status(
        self,
        segment_id: int,
        status: str,
        prompt_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update segment status in database."""
        async with self.memory.pool.acquire() as conn:
            if prompt_id:
                await conn.execute(
                    """
                    UPDATE generation_segments
                    SET status = $2, comfyui_prompt_id = $3
                    WHERE id = $1
                    """,
                    segment_id,
                    status,
                    prompt_id,
                )
            elif error:
                await conn.execute(
                    """
                    UPDATE generation_segments
                    SET status = $2, error_message = $3
                    WHERE id = $1
                    """,
                    segment_id,
                    status,
                    error,
                )
            else:
                await conn.execute(
                    "UPDATE generation_segments SET status = $2 WHERE id = $1",
                    segment_id,
                    status,
                )

    async def _update_segment_frames(
        self, segment_id: int, last_frame_path: str
    ) -> None:
        """Update segment with extracted last frame."""
        async with self.memory.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE generation_segments
                SET last_frame_path = $2
                WHERE id = $1
                """,
                segment_id,
                last_frame_path,
            )

    async def _update_segment_completed(
        self,
        segment_id: int,
        output_path: str,
        overall_score: float,
        consistency_score: float,
        smoothness_score: float,
    ) -> None:
        """Mark segment as completed with quality scores."""
        async with self.memory.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE generation_segments
                SET status = 'completed',
                    output_video_path = $2,
                    overall_quality_score = $3,
                    frame_consistency_score = $4,
                    motion_smoothness_score = $5,
                    completed_at = NOW()
                WHERE id = $1
                """,
                segment_id,
                output_path,
                overall_score,
                consistency_score,
                smoothness_score,
            )

    async def _update_scene_status(
        self,
        scene_id: int,
        final_video_path: Optional[str],
        exit_keyframe: Optional[str],
        completed_segments: int,
    ) -> None:
        """Update scene with final results."""
        async with self.memory.pool.acquire() as conn:
            status = "completed" if final_video_path else "failed"
            await conn.execute(
                """
                UPDATE movie_scenes
                SET status = $2,
                    final_video_path = $3,
                    exit_keyframe_path = $4,
                    completed_segments = $5
                WHERE id = $1
                """,
                scene_id,
                status,
                final_video_path,
                exit_keyframe,
                completed_segments,
            )
