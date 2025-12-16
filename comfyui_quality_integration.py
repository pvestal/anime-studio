#!/usr/bin/env python3
"""
ComfyUI Quality Gates Integration
Automatically runs quality gates on ComfyUI generated images
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Add quality gates to path
sys.path.append('/opt/tower-anime-production/quality')
from anime_quality_gates_runner import QualityGatesTestRunner, ProductionTestConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ComfyUIOutputHandler(FileSystemEventHandler):
    """Watches ComfyUI output directory and runs quality gates on new images"""

    def __init__(self, quality_runner):
        self.quality_runner = quality_runner
        self.processed_files = set()

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        if file_path.endswith(('.png', '.jpg', '.jpeg')) and file_path not in self.processed_files:
            logger.info(f"🎨 New ComfyUI output detected: {file_path}")
            self.processed_files.add(file_path)

            # Run quality gates on the new image
            asyncio.create_task(self.process_new_image(file_path))

    async def process_new_image(self, image_path):
        """Run quality gates on a newly generated image"""
        try:
            # Extract character name and prompt from filename if possible
            filename = os.path.basename(image_path)

            # Basic character detection from filename
            character_name = "unknown_character"
            if "kai" in filename.lower():
                character_name = "Kai Nakamura"
                prompt = "anime male character, dark hair, serious expression, detective coat, urban setting, high quality, detailed anime art, masterpiece"
            elif "yuki" in filename.lower():
                character_name = "Yuki Sato"
                prompt = "anime female character, silver hair, blue eyes, school uniform, thoughtful expression, high quality, detailed anime art, masterpiece"
            elif "raven" in filename.lower():
                character_name = "Raven Cross"
                prompt = "anime character, black hair with red streaks, leather jacket, cyberpunk aesthetic, high quality, detailed anime art, masterpiece"
            else:
                prompt = "high quality anime character art, detailed, masterpiece"

            # Create minimal config for single frame testing
            config = ProductionTestConfig(
                required_assets=[character_name],
                asset_paths=[image_path],  # Use the image itself as asset
                frame_paths=[image_path],
                character_name=character_name,
                generation_prompt=prompt,
                frame_sequence=[image_path],  # Single frame sequence
                sequence_name=f"{character_name}_single",
                video_path="",  # Skip video tests for single images
                intended_story=f"Character portrait of {character_name}"
            )

            logger.info(f"🚪 Running quality gates for {character_name}...")

            # Run only the relevant gates (skip video gates)
            from gate_2_frame_generation import Gate2FrameQualityChecker

            gate2_checker = Gate2FrameQualityChecker("/opt/tower-anime-production")
            results = await gate2_checker.run_gate_2_tests(
                frame_paths=[image_path],
                character_name=character_name,
                prompt=prompt
            )

            # Log results
            if results.get('pass', False):
                logger.info(f"✅ {character_name} PASSED quality gates!")
                logger.info(f"   Passed frames: {results.get('passed_frames', 0)}/{results.get('frame_count', 0)}")
            else:
                logger.warning(f"⚠️ {character_name} quality issues detected")
                logger.warning(f"   Failed frames: {results.get('failed_frames', 0)}")

                # Show specific issues
                frames = results.get('frames', {})
                for frame_path, frame_result in frames.items():
                    issues = frame_result.get('issues', [])
                    if issues:
                        logger.warning(f"   Issues in {os.path.basename(frame_path)}: {', '.join(issues)}")

            # Save results with timestamp
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            results_file = f"/opt/tower-anime-production/quality/results/comfyui_auto_{timestamp}.json"

            with open(results_file, 'w') as f:
                json.dump({
                    "image_path": image_path,
                    "character_name": character_name,
                    "quality_results": results,
                    "timestamp": timestamp
                }, f, indent=2)

            logger.info(f"📊 Results saved to {results_file}")

        except Exception as e:
            logger.error(f"❌ Error processing {image_path}: {e}")

async def main():
    """Main function to start ComfyUI quality gates integration"""
    logger.info("🚀 Starting ComfyUI Quality Gates Integration")

    # Initialize quality runner
    quality_runner = QualityGatesTestRunner("/opt/tower-anime-production")

    # Setup file watcher
    event_handler = ComfyUIOutputHandler(quality_runner)
    observer = Observer()

    # Watch ComfyUI output directory
    comfyui_output_dir = "/home/patrick/ComfyUI/output"
    if os.path.exists(comfyui_output_dir):
        observer.schedule(event_handler, comfyui_output_dir, recursive=False)
        logger.info(f"👀 Watching ComfyUI output: {comfyui_output_dir}")
    else:
        logger.warning(f"⚠️ ComfyUI output directory not found: {comfyui_output_dir}")
        return

    # Start watching
    observer.start()
    logger.info("✅ Quality gates integration active - watching for new ComfyUI outputs")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 Stopping quality gates integration")
        observer.stop()

    observer.join()

if __name__ == "__main__":
    asyncio.run(main())