#!/usr/bin/env python3
"""
Test Quality Gates with YOUR Tower Characters
Uses your actual character database and ComfyUI system
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TowerCharacterTest:
    """Test your actual Tower characters with ComfyUI and quality gates"""

    def __init__(self):
        self.project_root = Path("/opt/tower-anime-production")
        self.anime_api_url = "http://localhost:8328"
        self.db_path = self.project_root / "database" / "anime.db"

    async def get_your_characters(self):
        """Get YOUR actual characters from the Tower database"""
        logger.info("📋 Loading YOUR characters from Tower database...")

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT character_id, name, design_prompt, personality, project_id
                FROM characters
                WHERE is_active = 1
                ORDER BY created_at DESC
            """)

            characters = []
            for row in cursor.fetchall():
                characters.append({
                    'character_id': row[0],
                    'name': row[1],
                    'design_prompt': row[2],
                    'personality': json.loads(row[3]) if row[3] else {},
                    'project_id': row[4]
                })

            conn.close()

            logger.info(f"✅ Found {len(characters)} of YOUR characters:")
            for char in characters:
                logger.info(f"   • {char['name']} ({char['character_id']})")
                logger.info(f"     Prompt: {char['design_prompt'][:60]}...")

            return characters

        except Exception as e:
            logger.error(f"❌ Error loading characters: {e}")
            return []

    async def generate_character_with_comfyui(self, character):
        """Generate YOUR character using ComfyUI"""
        logger.info(f"🎨 Generating {character['name']} with ComfyUI...")

        # Use your character's actual design prompt
        generation_payload = {
            "prompt": character['design_prompt'] + ", high quality, detailed anime art, masterpiece",
            "character_name": character['character_id'],
            "project_id": character['project_id'],
            "width": 768,
            "height": 768,
            "steps": 15,
            "seed": hash(character['character_id']) % 10000  # Consistent seed per character
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"🚀 Generating {character['name']} via Tower API...")

                response = await client.post(
                    f"{self.anime_api_url}/api/anime/generate",
                    json=generation_payload
                )

                if response.status_code != 200:
                    logger.error(f"❌ Generation failed: {response.status_code} - {response.text}")
                    return {"success": False, "error": response.text}

                result = response.json()
                job_id = result.get("job_id")

                logger.info(f"📋 Started job {job_id} for {character['name']}")

                # Wait for completion
                return await self._wait_for_character_generation(job_id, character)

        except Exception as e:
            logger.error(f"❌ Generation request failed: {e}")
            return {"success": False, "error": str(e)}

    async def _wait_for_character_generation(self, job_id, character, max_wait=180):
        """Wait for your character generation to complete"""
        logger.info(f"⏳ Waiting for {character['name']} generation...")

        start_time = time.time()
        last_status = None

        while time.time() - start_time < max_wait:
            try:
                # Check ComfyUI queue status
                async with httpx.AsyncClient(timeout=10.0) as client:
                    queue_response = await client.get(f"{self.anime_api_url.replace('8328', '8188')}/queue")

                    if queue_response.status_code == 200:
                        queue_data = queue_response.json()
                        running = len(queue_data.get("queue_running", []))
                        pending = len(queue_data.get("queue_pending", []))

                        current_status = f"Running: {running}, Pending: {pending}"

                        if current_status != last_status:
                            logger.info(f"📊 ComfyUI Queue - {current_status}")
                            last_status = current_status

                        # If queue is empty, generation is likely complete
                        if running == 0 and pending == 0:
                            logger.info(f"✅ {character['name']} generation appears complete!")
                            return await self._find_character_output(character)

                await asyncio.sleep(3)

            except Exception as e:
                logger.warning(f"⚠️ Error checking status: {e}")
                await asyncio.sleep(2)

        logger.error(f"❌ {character['name']} generation timed out")
        return {"success": False, "error": "Generation timed out"}

    async def _find_character_output(self, character):
        """Find generated output for your character"""
        logger.info(f"🔍 Searching for {character['name']} output files...")

        # Search common output directories
        search_dirs = [
            "/home/patrick/ComfyUI/output",
            "/opt/tower-anime-production/output",
            "/opt/tower-anime-production/outputs",
            "/opt/tower-anime-production/generated",
            "/tmp/comfyui_output"
        ]

        output_files = []

        for search_dir in search_dirs:
            search_path = Path(search_dir)
            if search_path.exists():
                # Look for recent files
                for pattern in ["*.png", "*.jpg", "*.jpeg"]:
                    files = list(search_path.glob(f"**/{pattern}"))

                    # Sort by creation time (newest first)
                    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

                    # Take recent files (last 5 minutes)
                    for file_path in files[:5]:
                        if time.time() - file_path.stat().st_mtime < 300:
                            output_files.append(str(file_path))
                            logger.info(f"📁 Found: {file_path}")

        if output_files:
            logger.info(f"🎉 Found {len(output_files)} output files for {character['name']}")
            return {
                "success": True,
                "character": character,
                "output_files": output_files
            }
        else:
            logger.warning(f"⚠️ No output files found for {character['name']}")
            return {
                "success": False,
                "error": f"No output files found for {character['name']}"
            }

    async def test_character_with_quality_gates(self, character_result):
        """Test your character with quality gates"""
        if not character_result.get("success"):
            return character_result

        character = character_result["character"]
        output_files = character_result["output_files"]

        logger.info(f"🎭 Testing {character['name']} with quality gates...")

        # Import quality gates after we know they work
        sys.path.append('/opt/tower-anime-production/quality')
        from gate_2_frame_generation import Gate2FrameQualityChecker

        # Test Gate 2: Frame Quality
        gate2_checker = Gate2FrameQualityChecker("/opt/tower-anime-production")

        try:
            results = await gate2_checker.run_gate_2_tests(
                frame_paths=output_files[:3],  # Test up to 3 frames
                character_name=character['name'],
                prompt=character['design_prompt']
            )

            logger.info(f"📊 Quality gate results for {character['name']}:")
            logger.info(f"   Pass: {results.get('pass', False)}")
            logger.info(f"   Passed frames: {results.get('passed_frames', 0)}/{results.get('frame_count', 0)}")

            return {
                "character": character,
                "quality_results": results,
                "output_files": output_files
            }

        except Exception as e:
            logger.error(f"❌ Quality gate testing failed: {e}")
            return {
                "character": character,
                "error": f"Quality testing failed: {e}",
                "output_files": output_files
            }

    async def run_comprehensive_character_test(self):
        """Run comprehensive test with YOUR actual characters"""
        logger.info("🚀 STARTING COMPREHENSIVE TEST WITH YOUR TOWER CHARACTERS")
        logger.info("=" * 80)

        # Step 1: Get your characters
        characters = await self.get_your_characters()

        if not characters:
            logger.error("❌ No characters found in your database!")
            return False

        # Test first character (can extend to test all)
        test_character = characters[0]
        logger.info(f"🎯 Testing character: {test_character['name']}")

        # Step 2: Generate with ComfyUI
        generation_result = await self.generate_character_with_comfyui(test_character)

        if not generation_result.get("success"):
            logger.error(f"❌ Generation failed: {generation_result.get('error')}")
            return False

        # Step 3: Run quality gates
        quality_result = await self.test_character_with_quality_gates(generation_result)

        # Step 4: Report results
        logger.info("=" * 80)
        logger.info(f"🎬 TEST RESULTS FOR {test_character['name'].upper()}")
        logger.info("=" * 80)

        if "quality_results" in quality_result:
            qr = quality_result["quality_results"]

            if qr.get("pass", False):
                logger.info(f"🎉 {test_character['name']} PASSED quality gates!")
                logger.info(f"✅ Frames passed: {qr.get('passed_frames', 0)}/{qr.get('frame_count', 0)}")
            else:
                logger.error(f"💥 {test_character['name']} FAILED quality gates")
                logger.error(f"❌ Failed frames: {qr.get('failed_frames', 0)}")

            # Show generated files
            output_files = quality_result.get("output_files", [])
            logger.info(f"📁 Generated files ({len(output_files)}):")
            for i, file_path in enumerate(output_files[:3], 1):
                logger.info(f"   {i}. {file_path}")

            return qr.get("pass", False)
        else:
            logger.error(f"💥 Quality testing failed: {quality_result.get('error')}")
            return False

async def main():
    """Main test function using YOUR characters"""
    logger.info("🎬 TOWER ANIME PRODUCTION - CHARACTER QUALITY GATES TEST")
    logger.info("Using YOUR actual characters from the database")

    tester = TowerCharacterTest()

    try:
        success = await tester.run_comprehensive_character_test()

        if success:
            print("🎉 YOUR CHARACTER PASSED QUALITY GATES!")
            return 0
        else:
            print("💥 Quality gates test failed")
            return 1

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))