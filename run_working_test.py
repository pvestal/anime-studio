#!/usr/bin/env python3
"""
WORKING Quality Gates Test - Actually shows evidence
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add quality gates to path
sys.path.append('/opt/tower-anime-production/quality')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def generate_and_test():
    """Generate image with ComfyUI and run quality gates"""

    # 1. Generate image using your API
    import httpx

    generation_payload = {
        "prompt": "Kai Nakamura, anime male detective, dark hair, serious expression, detective coat, urban night setting, high quality detailed anime art, masterpiece",
        "character_name": "kai_test_evidence",
        "project_id": 1,
        "width": 768,
        "height": 768,
        "steps": 12,
        "seed": 5555
    }

    logger.info("🎨 Generating image with ComfyUI...")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "http://localhost:8328/api/anime/generate",
                json=generation_payload
            )

            if response.status_code == 200:
                result = response.json()
                job_id = result.get("job_id")
                logger.info(f"✅ Generation started: {job_id}")

                # Wait for completion
                logger.info("⏳ Waiting for generation...")
                await asyncio.sleep(8)  # Wait for generation

                # Find the generated file
                output_dir = Path("/home/patrick/ComfyUI/output")
                files = list(output_dir.glob("anime_*_00001_.png"))
                files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

                if files:
                    newest_file = str(files[0])
                    logger.info(f"📁 Found generated file: {newest_file}")

                    # Run quality gates
                    from gate_2_frame_generation import Gate2FrameQualityChecker

                    gate2_checker = Gate2FrameQualityChecker("/opt/tower-anime-production")

                    results = await gate2_checker.run_gate_2_tests(
                        frame_paths=[newest_file],
                        character_name="Kai Nakamura",
                        prompt="anime male detective, dark hair, serious expression, detective coat, urban night setting"
                    )

                    # Show evidence
                    logger.info("=" * 50)
                    logger.info("EVIDENCE OF QUALITY GATES TESTING:")
                    logger.info("=" * 50)
                    logger.info(f"File tested: {newest_file}")
                    logger.info(f"Pass/Fail: {'PASS' if results.get('pass') else 'FAIL'}")
                    logger.info(f"Frames tested: {results.get('frame_count', 0)}")
                    logger.info(f"Frames passed: {results.get('passed_frames', 0)}")

                    # Show detailed scores
                    frames = results.get('frames', {})
                    for frame_path, frame_data in frames.items():
                        logger.info(f"Frame: {os.path.basename(frame_path)}")
                        logger.info(f"  Character Fidelity: {frame_data.get('character_fidelity_score', 0):.3f}")
                        logger.info(f"  Artifact Detection: {frame_data.get('artifact_detection_score', 0):.3f}")
                        logger.info(f"  Prompt Adherence: {frame_data.get('prompt_adherence_score', 0):.3f}")
                        logger.info(f"  Overall Quality: {frame_data.get('overall_quality', 0):.3f}")
                        logger.info(f"  Issues: {frame_data.get('issues', [])}")

                    # Save evidence
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    evidence_file = f"/opt/tower-anime-production/quality/results/EVIDENCE_{timestamp}.json"

                    with open(evidence_file, 'w') as f:
                        json.dump({
                            "test_type": "WORKING_QUALITY_GATES_EVIDENCE",
                            "generated_file": newest_file,
                            "generation_payload": generation_payload,
                            "quality_results": results,
                            "timestamp": timestamp
                        }, f, indent=2)

                    logger.info(f"💾 Evidence saved to: {evidence_file}")
                    logger.info("=" * 50)

                    return True
                else:
                    logger.error("❌ No generated files found")
                    return False
            else:
                logger.error(f"❌ Generation failed: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return False

async def main():
    logger.info("🚀 Starting WORKING Quality Gates Test")
    success = await generate_and_test()

    if success:
        print("✅ Test completed - check results above")
        return 0
    else:
        print("❌ Test failed")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))