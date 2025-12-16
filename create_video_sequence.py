#!/usr/bin/env python3
"""
Generate VIDEO sequence with quality gates - ACTUALLY DO WHAT YOU ASKED FOR
"""

import asyncio
import json
import logging
import os
import sys
import time
import subprocess
from pathlib import Path

# Add quality gates to path
sys.path.append('/opt/tower-anime-production/quality')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def generate_frame_sequence_for_video():
    """Generate multiple frames to create a video sequence"""

    import httpx

    logger.info("🎬 Generating frame sequence for video...")

    frames = []

    # Generate 5 frames for a short video sequence
    for i in range(5):
        frame_prompt = f"Kai Nakamura, frame {i+1}/5, anime detective turning slowly in rainy alley, dark coat, serious expression, cinematic lighting, frame {i+1} of turning sequence"

        generation_payload = {
            "prompt": frame_prompt,
            "character_name": f"kai_video_frame_{i+1}",
            "project_id": 1,
            "width": 768,
            "height": 768,
            "steps": 10,
            "seed": 8000 + i
        }

        logger.info(f"🎨 Generating frame {i+1}/5...")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "http://localhost:8328/api/anime/generate",
                    json=generation_payload
                )

                if response.status_code == 200:
                    result = response.json()
                    job_id = result.get("job_id")
                    logger.info(f"✅ Frame {i+1} job: {job_id}")

                    # Wait for this frame
                    await asyncio.sleep(6)

                    # Find the generated frame
                    output_dir = Path("/home/patrick/ComfyUI/output")
                    files = list(output_dir.glob("anime_*_00001_.png"))
                    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

                    if files:
                        frame_file = str(files[0])
                        frames.append(frame_file)
                        logger.info(f"📁 Frame {i+1}: {frame_file}")
                    else:
                        logger.error(f"❌ Frame {i+1} not found")

                else:
                    logger.error(f"❌ Frame {i+1} generation failed")

        except Exception as e:
            logger.error(f"❌ Frame {i+1} error: {e}")

    return frames

async def create_video_from_frames(frames):
    """Create MP4 video from frame sequence"""

    if len(frames) < 2:
        logger.error("❌ Need at least 2 frames for video")
        return None

    logger.info(f"🎬 Creating video from {len(frames)} frames...")

    try:
        # Create output video path
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        video_output = f"/opt/tower-anime-production/generated/videos/kai_sequence_{timestamp}.mp4"

        # Ensure directory exists
        os.makedirs(os.path.dirname(video_output), exist_ok=True)

        # Create frame list for ffmpeg
        frame_list_file = f"/tmp/video_frames_{timestamp}.txt"

        with open(frame_list_file, 'w') as f:
            for frame in frames:
                f.write(f"file '{frame}'\n")
                f.write("duration 0.5\n")  # 0.5 seconds per frame = 2fps

        # Create video with ffmpeg
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", frame_list_file,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", "24",  # Output at 24fps
            video_output
        ]

        logger.info("🔧 Running ffmpeg to create video...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0 and os.path.exists(video_output):
            file_size = os.path.getsize(video_output)
            logger.info(f"✅ Video created: {video_output} ({file_size} bytes)")

            # Clean up temp file
            os.remove(frame_list_file)

            return video_output
        else:
            logger.error(f"❌ ffmpeg failed: {result.stderr}")
            return None

    except Exception as e:
        logger.error(f"❌ Video creation error: {e}")
        return None

async def run_video_quality_gates(video_path, frames):
    """Run quality gates on the generated video"""

    logger.info("🚪 Running video quality gates...")

    try:
        # Import quality gates
        from anime_quality_gates_runner import QualityGatesTestRunner, ProductionTestConfig

        # Create test configuration
        config = ProductionTestConfig(
            required_assets=["kai_character"],
            asset_paths=frames[:2],  # Use first 2 frames as assets
            frame_paths=frames,
            character_name="Kai Nakamura",
            generation_prompt="anime detective turning in rainy alley, dark coat, serious expression, cinematic lighting",
            frame_sequence=frames,
            sequence_name="kai_turning_sequence",
            video_path=video_path,
            intended_story="Detective Kai Nakamura turns around in a dark alley, rain reflecting off his coat as he senses danger",
            scene_description="Medium shot of detective in rain, dramatic lighting, turning motion"
        )

        # Run comprehensive quality gates
        runner = QualityGatesTestRunner("/opt/tower-anime-production")
        results = await runner.run_all_gates(config, parallel_execution=False)

        # Show comprehensive results
        logger.info("=" * 80)
        logger.info("COMPREHENSIVE VIDEO QUALITY GATES RESULTS:")
        logger.info("=" * 80)
        logger.info(f"Video file: {video_path}")
        logger.info(f"Overall Pass/Fail: {'PASS' if results.get('overall_pass') else 'FAIL'}")

        overall_results = results.get('overall_results', {})
        logger.info(f"Average Score: {overall_results.get('average_score', 0):.3f}")
        logger.info(f"Gates Passed: {overall_results.get('gates_passed', 0)}/{overall_results.get('total_gates', 4)}")

        # Show each gate result
        gate_summary = results.get('gate_summary', {})
        for gate_name, gate_data in gate_summary.items():
            status = "✅ PASS" if gate_data.get('passed') else "❌ FAIL"
            score = gate_data.get('score', 0)
            gate_title = gate_name.replace('_', ' ').title()
            logger.info(f"{gate_title}: {status} (Score: {score:.3f})")

        # Show issues
        issues = results.get('issues', {}).get('issues', [])
        if issues:
            logger.info("Issues found:")
            for issue in issues[:5]:
                logger.info(f"  • {issue}")

        # Save comprehensive evidence
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        comprehensive_evidence = f"/opt/tower-anime-production/quality/results/COMPREHENSIVE_VIDEO_EVIDENCE_{timestamp}.json"

        with open(comprehensive_evidence, 'w') as f:
            json.dump({
                "test_type": "COMPREHENSIVE_VIDEO_QUALITY_GATES",
                "video_path": video_path,
                "frames_used": frames,
                "comprehensive_results": results,
                "timestamp": timestamp
            }, f, indent=2)

        logger.info(f"💾 Comprehensive evidence saved: {comprehensive_evidence}")
        logger.info("=" * 80)

        return results.get('overall_pass', False)

    except Exception as e:
        logger.error(f"❌ Quality gates error: {e}")
        return False

async def main():
    """Main function - generate video sequence and test with quality gates"""

    logger.info("🎬 STARTING COMPREHENSIVE VIDEO GENERATION AND QUALITY GATES")
    logger.info("=" * 80)

    # Step 1: Generate frame sequence
    frames = await generate_frame_sequence_for_video()

    if len(frames) < 2:
        logger.error("❌ Failed to generate enough frames for video")
        return 1

    logger.info(f"✅ Generated {len(frames)} frames for video")

    # Step 2: Create video
    video_path = await create_video_from_frames(frames)

    if not video_path:
        logger.error("❌ Failed to create video")
        return 1

    logger.info(f"✅ Video created: {video_path}")

    # Step 3: Run comprehensive quality gates
    quality_pass = await run_video_quality_gates(video_path, frames)

    # Final result
    logger.info("=" * 80)
    if quality_pass:
        logger.info("🎉 COMPREHENSIVE VIDEO QUALITY GATES: PASSED")
    else:
        logger.info("💥 COMPREHENSIVE VIDEO QUALITY GATES: FAILED")

    logger.info(f"🎬 YOUR VIDEO: {video_path}")
    logger.info("=" * 80)

    return 0 if quality_pass else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))