#!/usr/bin/env python3
"""
Multi-Segment Video Generator
Generates longer videos by creating multiple segments and splicing them together
Maintains character consistency across segments while respecting VRAM limits
"""

import asyncio
import json
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MultiSegmentVideoGenerator:
    def __init__(self):
        self.comfyui_url = "http://127.0.0.1:8188"
        self.client_id = str(uuid.uuid4())
        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
        self.temp_dir = Path("/tmp/anime_segments")
        self.temp_dir.mkdir(exist_ok=True)

        # VRAM-safe segment parameters
        self.max_frames_per_segment = 120  # 5 seconds at 24fps
        self.segment_duration = 5.0  # seconds
        self.target_fps = 24

        # Character consistency parameters
        self.characters = {
            "Kai Nakamura": {
                "appearance": "anime girl, young Japanese woman, beautiful female, feminine face, delicate features, black hair, brown eyes, athletic build, 18 years old, tomboy style, female character",
                "clothing": "dark jacket, casual pants, sneakers",
                "style": "photorealistic anime, detailed shading, masterpiece quality, Tokyo street background, urban setting, beautiful anime girl art",
                "negative": "male, man, boy, masculine, masculine features, beard, mustache, multiple people, crowd, schoolgirl uniform",
            },
            "Hiroshi Yamamoto": {
                "appearance": "anime boy, young Japanese man, handsome male, masculine face, strong features, dark hair, green eyes, tall athletic build, 19 years old, cool style, male character",
                "clothing": "school uniform, white shirt, dark blazer",
                "style": "photorealistic anime, detailed shading, masterpiece quality, school courtyard background, outdoor setting, beautiful anime boy art",
                "negative": "female, woman, girl, feminine, feminine features, multiple people, crowd",
            },
        }

    async def generate_long_video(
        self,
        prompt: str,
        character_name: str,
        total_duration: float,
        output_filename: str,
        quality_preset: str = "standard",
    ) -> Optional[str]:
        """
        Generate a long video by creating segments and splicing them together

        Args:
            prompt: Base prompt for the video
            character_name: Character to maintain consistency for
            total_duration: Total desired video duration in seconds
            output_filename: Final output filename
            quality_preset: Quality setting (fast, standard, high, ultra)

        Returns:
            Path to the final spliced video or None if failed
        """
        try:
            # Calculate number of segments needed
            segments_needed = max(
                1, int(total_duration / self.segment_duration))
            actual_duration = segments_needed * self.segment_duration

            logger.info(
                f"🎬 Generating {actual_duration}s video in {segments_needed} segments"
            )
            logger.info(
                f"📊 Character: {character_name}, Quality: {quality_preset}")

            # Generate all segments
            segment_paths = []
            for segment_idx in range(segments_needed):
                segment_path = await self._generate_segment(
                    prompt=prompt,
                    character_name=character_name,
                    segment_index=segment_idx,
                    total_segments=segments_needed,
                    quality_preset=quality_preset,
                )

                if segment_path:
                    segment_paths.append(segment_path)
                    logger.info(
                        f"✅ Segment {segment_idx + 1}/{segments_needed} completed"
                    )
                else:
                    logger.error(f"❌ Segment {segment_idx + 1} failed")
                    return None

            # Splice segments together
            if len(segment_paths) > 1:
                final_path = await self._splice_segments(segment_paths, output_filename)
            else:
                # Single segment, just rename
                final_path = self.output_dir / f"{output_filename}.mp4"
                subprocess.run(
                    ["mv", str(segment_paths[0]), str(final_path)], check=True
                )

            # Cleanup temporary segments
            await self._cleanup_segments(segment_paths)

            logger.info(f"🎉 Final video generated: {final_path}")
            return str(final_path)

        except Exception as e:
            logger.error(f"❌ Video generation failed: {e}")
            return None

    async def _generate_segment(
        self,
        prompt: str,
        character_name: str,
        segment_index: int,
        total_segments: int,
        quality_preset: str,
    ) -> Optional[str]:
        """Generate a single video segment with character consistency"""

        try:
            # Create segment-specific prompt with temporal context
            segment_prompt = self._create_segment_prompt(
                prompt, character_name, segment_index, total_segments
            )

            # Load workflow template
            workflow = await self._load_workflow_template()
            if not workflow:
                return None

            # Optimize workflow for segment
            workflow = await self._optimize_segment_workflow(
                workflow, segment_prompt, character_name, quality_preset
            )

            # Generate segment
            segment_filename = f"segment_{segment_index:03d}_{uuid.uuid4().hex[:8]}.mp4"
            result_path = await self._execute_comfyui_workflow(
                workflow, segment_filename
            )

            if result_path and os.path.exists(result_path):
                logger.info(
                    f"✅ Segment {segment_index} generated: {result_path}")
                return result_path
            else:
                logger.error(f"❌ Segment {segment_index} generation failed")
                return None

        except Exception as e:
            logger.error(f"❌ Segment {segment_index} error: {e}")
            return None

    def _create_segment_prompt(
        self,
        base_prompt: str,
        character_name: str,
        segment_index: int,
        total_segments: int,
    ) -> str:
        """Create a segment-specific prompt maintaining character consistency"""

        character_info = self.characters.get(character_name, {})

        # Add temporal context for story progression
        temporal_phrases = [
            "beginning of scene, establishing shot",
            "continuing action, medium shot",
            "mid-scene development, close-up",
            "climactic moment, dynamic angle",
            "conclusion, wide shot",
        ]

        temporal_context = temporal_phrases[
            min(segment_index, len(temporal_phrases) - 1)
        ]

        # Combine all elements
        segment_prompt = (
            f"""
        {character_info.get('appearance', '')},
        {character_info.get('clothing', '')},
        {base_prompt},
        {temporal_context},
        {character_info.get('style', '')},
        smooth animation, fluid motion, consistent character design,
        masterpiece, best quality, detailed animation
        """.strip()
            .replace("\n", " ")
            .replace("  ", " ")
        )

        return segment_prompt

    async def _load_workflow_template(self) -> Optional[Dict]:
        """Load the working workflow template"""
        workflow_path = Path(
            "/opt/tower-anime-production/workflows/comfyui/anime_30sec_standard.json"
        )

        try:
            with open(workflow_path, "r") as f:
                workflow = json.load(f)
            logger.info(f"📋 Loaded workflow template: {workflow_path}")
            return workflow
        except Exception as e:
            logger.error(f"❌ Failed to load workflow: {e}")
            return None

    async def _optimize_segment_workflow(
        self, workflow: Dict, prompt: str, character_name: str, quality_preset: str
    ) -> Dict:
        """Optimize workflow for segment generation"""

        optimized = workflow.copy()
        character_info = self.characters.get(character_name, {})

        # Quality settings
        quality_settings = {
            "fast": {"steps": 20, "cfg": 7.0, "width": 512, "height": 512},
            "standard": {"steps": 30, "cfg": 7.5, "width": 768, "height": 768},
            "high": {"steps": 40, "cfg": 8.0, "width": 1024, "height": 1024},
            "ultra": {"steps": 50, "cfg": 8.5, "width": 1024, "height": 1024},
        }

        settings = quality_settings.get(
            quality_preset, quality_settings["standard"])

        # Update workflow nodes
        for node_id, node in optimized.items():
            class_type = node.get("class_type", "")

            # Update positive prompt
            if (
                class_type == "CLIPTextEncode"
                and "positive" in node.get("_meta", {}).get("title", "").lower()
            ):
                node["inputs"]["text"] = prompt

            # Update negative prompt
            elif (
                class_type == "CLIPTextEncode"
                and "negative" in node.get("_meta", {}).get("title", "").lower()
            ):
                negative_prompt = f"worst quality, low quality, blurry, distorted, {character_info.get('negative', '')}"
                node["inputs"]["text"] = negative_prompt

            # Update latent image settings
            elif class_type == "EmptyLatentImage":
                node["inputs"]["batch_size"] = self.max_frames_per_segment
                node["inputs"]["width"] = settings["width"]
                node["inputs"]["height"] = settings["height"]

            # Update sampler settings
            elif class_type == "KSampler":
                node["inputs"]["steps"] = settings["steps"]
                node["inputs"]["cfg"] = settings["cfg"]
                node["inputs"]["seed"] = (
                    int(time.time() * 1000) % 1000000
                )  # Unique seed per segment

        logger.info(
            f"🔧 Optimized workflow for {quality_preset} quality, {self.max_frames_per_segment} frames"
        )
        return optimized

    async def _execute_comfyui_workflow(
        self, workflow: Dict, filename: str
    ) -> Optional[str]:
        """Execute the workflow in ComfyUI and return the output path"""

        try:
            # Queue the workflow
            prompt = {"prompt": workflow, "client_id": self.client_id}

            response = requests.post(f"{self.comfyui_url}/prompt", json=prompt)
            response.raise_for_status()

            prompt_id = response.json()["prompt_id"]
            logger.info(f"🚀 Queued workflow with prompt_id: {prompt_id}")

            # Wait for completion
            output_path = await self._wait_for_completion(prompt_id, filename)
            return output_path

        except Exception as e:
            logger.error(f"❌ ComfyUI execution failed: {e}")
            return None

    async def _wait_for_completion(
        self, prompt_id: str, filename: str
    ) -> Optional[str]:
        """Wait for ComfyUI generation to complete"""

        max_wait = 1800  # 30 minutes per segment
        check_interval = 5
        waited = 0

        while waited < max_wait:
            try:
                # Check if generation is complete
                response = requests.get(
                    f"{self.comfyui_url}/history/{prompt_id}")
                if response.status_code == 200:
                    history = response.json()
                    if prompt_id in history:
                        # Find the output file
                        outputs = history[prompt_id].get("outputs", {})
                        for node_outputs in outputs.values():
                            if "videos" in node_outputs:
                                for video in node_outputs["videos"]:
                                    video_filename = video["filename"]
                                    source_path = self.output_dir / video_filename
                                    if source_path.exists():
                                        # Rename to our desired filename
                                        target_path = self.temp_dir / filename
                                        subprocess.run(
                                            ["cp", str(source_path),
                                             str(target_path)],
                                            check=True,
                                        )
                                        return str(target_path)

                await asyncio.sleep(check_interval)
                waited += check_interval

                if waited % 60 == 0:  # Log every minute
                    logger.info(
                        f"⏳ Waiting for generation... {waited//60}m elapsed")

            except Exception as e:
                logger.error(f"❌ Error checking completion: {e}")
                await asyncio.sleep(check_interval)
                waited += check_interval

        logger.error(f"❌ Generation timeout after {max_wait}s")
        return None

    async def _splice_segments(
        self, segment_paths: List[str], output_filename: str
    ) -> Optional[str]:
        """Splice video segments together using ffmpeg"""

        try:
            final_output = self.output_dir / f"{output_filename}.mp4"

            # Create file list for ffmpeg
            filelist_path = self.temp_dir / "segments.txt"
            with open(filelist_path, "w") as f:
                for segment_path in segment_paths:
                    f.write(f"file '{segment_path}'\n")

            # Use ffmpeg to concatenate
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(filelist_path),
                "-c",
                "copy",  # Copy streams without re-encoding
                "-avoid_negative_ts",
                "make_zero",
                str(final_output),
            ]

            logger.info(f"🔧 Splicing {len(segment_paths)} segments...")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info(f"✅ Segments spliced successfully: {final_output}")
                return str(final_output)
            else:
                logger.error(f"❌ ffmpeg error: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"❌ Splicing failed: {e}")
            return None

    async def _cleanup_segments(self, segment_paths: List[str]):
        """Clean up temporary segment files"""
        for segment_path in segment_paths:
            try:
                if os.path.exists(segment_path):
                    os.remove(segment_path)
            except Exception as e:
                logger.warning(f"⚠️ Failed to cleanup {segment_path}: {e}")


# API endpoint for integration
async def generate_long_video_api(
    prompt: str,
    character_name: str = "Kai Nakamura",
    duration: float = 5.0,
    output_name: str = None,
    quality: str = "standard",
) -> Dict:
    """API wrapper for long video generation"""

    generator = MultiSegmentVideoGenerator()

    if not output_name:
        output_name = f"anime_video_{int(time.time())}"

    try:
        result_path = await generator.generate_long_video(
            prompt=prompt,
            character_name=character_name,
            total_duration=duration,
            output_filename=output_name,
            quality_preset=quality,
        )

        if result_path:
            return {
                "success": True,
                "video_path": result_path,
                "duration": duration,
                "segments": int(duration / generator.segment_duration),
                "character": character_name,
                "quality": quality,
            }
        else:
            return {"success": False, "error": "Video generation failed"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# CLI interface for testing
async def main():
    """CLI interface for testing the multi-segment generator"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate multi-segment anime videos")
    parser.add_argument("--prompt", required=True, help="Video prompt")
    parser.add_argument(
        "--character", default="Kai Nakamura", help="Character name")
    parser.add_argument(
        "--duration", type=float, default=5.0, help="Video duration in seconds"
    )
    parser.add_argument("--output", help="Output filename (without extension)")
    parser.add_argument(
        "--quality", default="standard", choices=["fast", "standard", "high", "ultra"]
    )

    args = parser.parse_args()

    if not args.output:
        args.output = f"test_video_{int(time.time())}"

    logger.info(f"🎬 Starting video generation...")
    logger.info(f"📝 Prompt: {args.prompt}")
    logger.info(f"🎭 Character: {args.character}")
    logger.info(f"⏱️ Duration: {args.duration}s")
    logger.info(f"📊 Quality: {args.quality}")

    result = await generate_long_video_api(
        prompt=args.prompt,
        character_name=args.character,
        duration=args.duration,
        output_name=args.output,
        quality=args.quality,
    )

    if result["success"]:
        print(f"\n✅ SUCCESS!")
        print(f"📹 Video: {result['video_path']}")
        print(f"⏱️ Duration: {result['duration']}s")
        print(f"🎞️ Segments: {result['segments']}")
    else:
        print(f"\n❌ FAILED: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
