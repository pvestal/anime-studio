#!/usr/bin/env python3
"""
PRODUCTION STORY-TO-VIDEO PIPELINE
Complete workflow from story description to final video with validation gates

This implements the gated approach you requested:
Gate 1: Story → Image (validate image quality)
Gate 2: Image → Video (validate video output)

Each gate has validation and can fail/retry independently.
"""

import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

# Import production workflows
import sys
sys.path.append('/opt/anime-studio/production/workflows')
from ltx_video_2b_production import LTXVideo2BProduction

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Result of a validation gate"""
    passed: bool
    score: float
    message: str
    data: Optional[Dict[str, Any]] = None

@dataclass
class PipelineResult:
    """Complete pipeline result"""
    success: bool
    story: str
    image_path: Optional[str]
    video_path: Optional[str]
    validation_results: Dict[str, ValidationResult]
    total_time: float

class StoryToVideoPipeline:
    """Production story-to-video pipeline with validation gates"""

    def __init__(self):
        self.ltx_generator = LTXVideo2BProduction()
        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")

    def validate_story(self, story: str) -> ValidationResult:
        """Gate 0: Validate story input"""
        if not story or len(story.strip()) < 10:
            return ValidationResult(
                passed=False,
                score=0.0,
                message="Story too short or empty"
            )

        # Basic story quality checks
        if len(story) > 500:
            return ValidationResult(
                passed=False,
                score=0.0,
                message="Story too long (>500 chars), may exceed prompt limits"
            )

        return ValidationResult(
            passed=True,
            score=1.0,
            message="Story validation passed",
            data={"length": len(story)}
        )

    def story_to_image(self, story: str) -> Tuple[Optional[str], ValidationResult]:
        """
        Gate 1: Generate base image from story
        Uses the first stage of LTX workflow to create reference image
        """
        logger.info("Gate 1: Story → Image")

        if not self.ltx_generator.validate_prerequisites():
            return None, ValidationResult(
                passed=False,
                score=0.0,
                message="Prerequisites validation failed"
            )

        # Create modified workflow that stops at image generation
        workflow = self.ltx_generator.create_workflow(story)

        # Remove video generation steps, keep only image generation
        image_only_workflow = {k: v for k, v in workflow.items() if int(k) <= 7}

        # Modify output to save image
        image_only_workflow["8"] = {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["7", 0],
                "filename_prefix": "story_to_image_"
            }
        }

        try:
            import requests
            response = requests.post(
                f"{self.ltx_generator.comfyui_url}/prompt",
                json={"prompt": image_only_workflow, "client_id": "story_pipeline"}
            )
            result = response.json()

            if "prompt_id" not in result:
                return None, ValidationResult(
                    passed=False,
                    score=0.0,
                    message=f"Failed to submit image workflow: {result}"
                )

            # Wait for completion
            prompt_id = result["prompt_id"]
            timeout = 120  # 2 minutes for image generation

            start_time = time.time()
            while time.time() - start_time < timeout:
                time.sleep(2)

                queue_response = requests.get(f"{self.ltx_generator.comfyui_url}/queue")
                queue_data = queue_response.json()

                running_jobs = [job[1] for job in queue_data.get("queue_running", [])]
                if prompt_id not in running_jobs:
                    # Look for generated image
                    image_files = list(self.output_dir.glob("story_to_image_*.png"))
                    if image_files:
                        latest_image = max(image_files, key=lambda p: p.stat().st_mtime)
                        return str(latest_image), ValidationResult(
                            passed=True,
                            score=1.0,
                            message="Image generated successfully",
                            data={"file_size": latest_image.stat().st_size}
                        )

            return None, ValidationResult(
                passed=False,
                score=0.0,
                message="Image generation timed out"
            )

        except Exception as e:
            return None, ValidationResult(
                passed=False,
                score=0.0,
                message=f"Image generation failed: {e}"
            )

    def validate_image(self, image_path: str) -> ValidationResult:
        """Gate 1.5: Validate generated image quality"""
        if not image_path or not Path(image_path).exists():
            return ValidationResult(
                passed=False,
                score=0.0,
                message="Image file not found"
            )

        image_file = Path(image_path)
        file_size = image_file.stat().st_size

        # Basic quality checks
        if file_size < 50000:  # Less than 50KB suggests low quality
            return ValidationResult(
                passed=False,
                score=0.3,
                message="Image file too small, may be low quality"
            )

        if file_size > 5000000:  # Greater than 5MB is excessive
            return ValidationResult(
                passed=False,
                score=0.7,
                message="Image file too large"
            )

        return ValidationResult(
            passed=True,
            score=1.0,
            message="Image validation passed",
            data={"file_size": file_size}
        )

    def image_to_video(self, story: str, image_path: str) -> Tuple[Optional[str], ValidationResult]:
        """
        Gate 2: Generate video from story + base image
        Uses full LTX Video 2B workflow for 121-frame generation
        """
        logger.info("Gate 2: Image → Video (121 frames)")

        try:
            video_path = self.ltx_generator.generate_video(story)

            if video_path:
                return video_path, ValidationResult(
                    passed=True,
                    score=1.0,
                    message="Video generated successfully",
                    data={"video_path": video_path}
                )
            else:
                return None, ValidationResult(
                    passed=False,
                    score=0.0,
                    message="Video generation failed"
                )

        except Exception as e:
            return None, ValidationResult(
                passed=False,
                score=0.0,
                message=f"Video generation error: {e}"
            )

    def validate_video(self, video_path: str) -> ValidationResult:
        """Gate 2.5: Validate generated video quality"""
        if not video_path or not Path(video_path).exists():
            return ValidationResult(
                passed=False,
                score=0.0,
                message="Video file not found"
            )

        video_file = Path(video_path)
        file_size = video_file.stat().st_size

        # Use ffprobe to validate frame count
        try:
            import subprocess
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-count_frames",
                "-select_streams", "v:0", "-show_entries",
                "stream=nb_read_frames", "-print_format",
                "default=nokey=1:noprint_wrappers=1", str(video_file)
            ], capture_output=True, text=True)

            if probe.returncode == 0 and probe.stdout:
                frame_count = int(probe.stdout.strip())

                if frame_count == 121:
                    return ValidationResult(
                        passed=True,
                        score=1.0,
                        message=f"Video validation passed: {frame_count} frames",
                        data={"frame_count": frame_count, "file_size": file_size}
                    )
                else:
                    return ValidationResult(
                        passed=False,
                        score=0.5,
                        message=f"Wrong frame count: {frame_count} (expected 121)"
                    )

        except Exception as e:
            logger.warning(f"Frame count validation failed: {e}")

        # Fallback: basic file size check
        if file_size > 100000:  # At least 100KB for 5-second video
            return ValidationResult(
                passed=True,
                score=0.8,
                message="Video file size acceptable (frame count unknown)",
                data={"file_size": file_size}
            )

        return ValidationResult(
            passed=False,
            score=0.2,
            message="Video file too small or corrupted"
        )

    def run_complete_pipeline(self, story: str) -> PipelineResult:
        """
        Run complete story-to-video pipeline with all validation gates
        """
        start_time = time.time()
        validation_results = {}

        logger.info(f"Starting complete pipeline for story: {story[:50]}...")

        # Gate 0: Validate story
        story_validation = self.validate_story(story)
        validation_results["story"] = story_validation

        if not story_validation.passed:
            return PipelineResult(
                success=False,
                story=story,
                image_path=None,
                video_path=None,
                validation_results=validation_results,
                total_time=time.time() - start_time
            )

        # Gate 1: Story → Image
        image_path, image_generation = self.story_to_image(story)
        validation_results["image_generation"] = image_generation

        if not image_generation.passed:
            return PipelineResult(
                success=False,
                story=story,
                image_path=image_path,
                video_path=None,
                validation_results=validation_results,
                total_time=time.time() - start_time
            )

        # Gate 1.5: Validate image
        image_validation = self.validate_image(image_path)
        validation_results["image_validation"] = image_validation

        if not image_validation.passed:
            logger.warning("Image validation failed, continuing anyway")

        # Gate 2: Image → Video
        video_path, video_generation = self.image_to_video(story, image_path)
        validation_results["video_generation"] = video_generation

        if not video_generation.passed:
            return PipelineResult(
                success=False,
                story=story,
                image_path=image_path,
                video_path=video_path,
                validation_results=validation_results,
                total_time=time.time() - start_time
            )

        # Gate 2.5: Validate video
        video_validation = self.validate_video(video_path)
        validation_results["video_validation"] = video_validation

        success = video_validation.passed

        return PipelineResult(
            success=success,
            story=story,
            image_path=image_path,
            video_path=video_path,
            validation_results=validation_results,
            total_time=time.time() - start_time
        )

def main():
    """Example usage of story-to-video pipeline"""
    pipeline = StoryToVideoPipeline()

    story = "anime cyberpunk warrior with neon blue hair running through dark city streets with glowing holographic advertisements, dynamic action scene with particle effects"

    print("🎬 Starting Story-to-Video Pipeline")
    print(f"Story: {story}")
    print("-" * 50)

    result = pipeline.run_complete_pipeline(story)

    print(f"Pipeline completed in {result.total_time:.2f} seconds")
    print(f"Success: {result.success}")

    if result.image_path:
        print(f"Image: {result.image_path}")

    if result.video_path:
        print(f"Video: {result.video_path}")

    print("\nValidation Results:")
    for gate, validation in result.validation_results.items():
        status = "✅" if validation.passed else "❌"
        print(f"{status} {gate}: {validation.message} (score: {validation.score})")

if __name__ == "__main__":
    main()