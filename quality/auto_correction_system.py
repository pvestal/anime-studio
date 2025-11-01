#!/usr/bin/env python3
"""
Auto-Correction System for Anime Quality Control
Automatically corrects failed generations by adjusting ComfyUI workflow parameters
Learns from successful/failed attempts to improve future generations
"""

import asyncio
import json
import logging
import aiohttp
import numpy as np
import os
import hvac
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AutoCorrectionSystem:
    def __init__(self):
        self.comfyui_url = "http://127.0.0.1:8188"
        self.echo_brain_url = "http://127.0.0.1:8309"

        # Database connection with secure credential management
        self.db_params = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'database': os.getenv('DB_NAME', 'tower_consolidated'),
            'user': os.getenv('DB_USER', 'patrick'),
            'password': self._get_secure_db_password()
        }

    def _get_secure_db_password(self) -> str:
        """Securely retrieve database password from Vault or environment"""
        try:
            # Try Vault first
            vault_client = hvac.Client(url=os.getenv('VAULT_ADDR', 'http://127.0.0.1:8200'))

            # Get vault token
            vault_token = os.getenv('VAULT_TOKEN')
            if not vault_token:
                token_paths = [
                    Path('/opt/vault/.vault-token'),
                    Path('/opt/vault/data/vault-token')
                ]
                for token_path in token_paths:
                    if token_path.exists():
                        vault_token = token_path.read_text().strip()
                        break

            if vault_token:
                vault_client.token = vault_token
                if vault_client.is_authenticated():
                    # Try different secret paths
                    for path in ['secret/tower/database', 'secret/anime_production/database']:
                        try:
                            response = vault_client.secrets.kv.v2.read_secret_version(path=path)
                            if response and 'data' in response and 'data' in response['data']:
                                password = response['data']['data'].get('password')
                                if password:
                                    logger.info(f"Retrieved database password from Vault")
                                    return password
                        except Exception:
                            continue
        except Exception as e:
            logger.warning(f"Failed to retrieve password from Vault: {e}")

        # Fallback to environment variable
        env_password = os.getenv('DB_PASSWORD')
        if env_password:
            logger.info("Using database password from environment variable")
            return env_password

        # Critical security warning
        logger.critical("SECURITY WARNING: No secure password found, using empty password")
        return ''

        # Correction strategies
        self.correction_strategies = {
            'resolution': self.fix_resolution,
            'quality': self.fix_quality,
            'duration': self.fix_duration,
            'fps': self.fix_fps,
            'brightness': self.fix_brightness,
            'contrast': self.fix_contrast,
            'blur': self.fix_blur
        }

        # Parameter learning database
        self.successful_params = {}
        self.failed_params = {}

        # Load learned parameters
        asyncio.create_task(self.load_learned_parameters())

    async def load_learned_parameters(self):
        """Load previously learned successful and failed parameters"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Load successful parameters
            cur.execute("""
                SELECT prompt_hash, workflow_params, quality_score
                FROM successful_workflows
                WHERE created_at > NOW() - INTERVAL '30 days'
                ORDER BY quality_score DESC
            """)

            successful_rows = cur.fetchall()
            for row in successful_rows:
                self.successful_params[row['prompt_hash']] = {
                    'params': json.loads(row['workflow_params']),
                    'quality_score': row['quality_score']
                }

            # Load failed parameters to avoid repeating
            cur.execute("""
                SELECT prompt_hash, workflow_params, rejection_reasons
                FROM failed_workflows
                WHERE created_at > NOW() - INTERVAL '7 days'
            """)

            failed_rows = cur.fetchall()
            for row in failed_rows:
                prompt_hash = row['prompt_hash']
                if prompt_hash not in self.failed_params:
                    self.failed_params[prompt_hash] = []
                self.failed_params[prompt_hash].append({
                    'params': json.loads(row['workflow_params']),
                    'rejection_reasons': json.loads(row['rejection_reasons'])
                })

            cur.close()
            conn.close()

            logger.info(f"Loaded {len(self.successful_params)} successful and {len(self.failed_params)} failed parameter sets")

        except Exception as e:
            logger.error(f"Error loading learned parameters: {e}")

    async def process_quality_failure(self, prompt_id: str, original_prompt: str, quality_result: Dict, original_workflow: Dict) -> Optional[Dict]:
        """Process a quality failure and generate corrected workflow"""
        try:
            rejection_reasons = quality_result.get('rejection_reasons', [])
            logger.info(f"Processing quality failure for {prompt_id}: {rejection_reasons}")

            # Generate prompt hash for learning
            prompt_hash = hashlib.md5(original_prompt.encode()).hexdigest()

            # Store failed attempt
            await self.store_failed_attempt(prompt_hash, original_workflow, rejection_reasons)

            # Generate corrections
            corrected_workflow = await self.generate_corrections(
                original_workflow,
                rejection_reasons,
                original_prompt,
                quality_result
            )

            if corrected_workflow:
                logger.info(f"✅ Generated corrected workflow for {prompt_id}")
                return corrected_workflow
            else:
                logger.warning(f"❌ Could not generate corrections for {prompt_id}")
                return None

        except Exception as e:
            logger.error(f"Error processing quality failure: {e}")
            return None

    async def generate_corrections(self, original_workflow: Dict, rejection_reasons: List[str], prompt: str, quality_result: Dict) -> Optional[Dict]:
        """Generate corrected workflow based on failure analysis"""
        try:
            corrected_workflow = json.loads(json.dumps(original_workflow))  # Deep copy

            corrections_applied = []

            for reason in rejection_reasons:
                reason_lower = reason.lower()

                if 'resolution' in reason_lower:
                    correction = await self.fix_resolution(corrected_workflow, reason, quality_result)
                    if correction:
                        corrections_applied.append('resolution')

                elif 'quality' in reason_lower or 'blur' in reason_lower:
                    correction = await self.fix_quality(corrected_workflow, reason, quality_result)
                    if correction:
                        corrections_applied.append('quality')

                elif 'duration' in reason_lower:
                    correction = await self.fix_duration(corrected_workflow, reason, quality_result)
                    if correction:
                        corrections_applied.append('duration')

                elif 'frame rate' in reason_lower or 'fps' in reason_lower:
                    correction = await self.fix_fps(corrected_workflow, reason, quality_result)
                    if correction:
                        corrections_applied.append('fps')

                elif 'brightness' in reason_lower:
                    correction = await self.fix_brightness(corrected_workflow, reason, quality_result)
                    if correction:
                        corrections_applied.append('brightness')

                elif 'contrast' in reason_lower:
                    correction = await self.fix_contrast(corrected_workflow, reason, quality_result)
                    if correction:
                        corrections_applied.append('contrast')

            # Apply learned optimizations
            await self.apply_learned_optimizations(corrected_workflow, prompt)

            # Enhance prompt with Echo Brain
            corrected_workflow = await self.enhance_prompt_with_echo(corrected_workflow, prompt, rejection_reasons)

            if corrections_applied:
                logger.info(f"Applied corrections: {corrections_applied}")
                return corrected_workflow
            else:
                logger.warning("No corrections could be applied")
                return None

        except Exception as e:
            logger.error(f"Error generating corrections: {e}")
            return None

    async def fix_resolution(self, workflow: Dict, reason: str, quality_result: Dict) -> bool:
        """Fix resolution issues"""
        try:
            current_resolution = quality_result.get('resolution', (512, 512))
            current_width, current_height = current_resolution

            # Find Empty Latent Image node
            for node_id, node_data in workflow.get('prompt', {}).items():
                if node_data.get('class_type') == 'EmptyLatentImage':
                    inputs = node_data.get('inputs', {})

                    # Increase resolution intelligently
                    if current_width < 1024 or current_height < 1024:
                        new_width = max(1024, current_width * 1.5)
                        new_height = max(1024, current_height * 1.5)
                    else:
                        new_width = current_width * 1.2
                        new_height = current_height * 1.2

                    # Ensure dimensions are multiples of 8 (SD requirement)
                    new_width = int(new_width // 8) * 8
                    new_height = int(new_height // 8) * 8

                    inputs['width'] = new_width
                    inputs['height'] = new_height

                    logger.info(f"Resolution correction: {current_width}x{current_height} → {new_width}x{new_height}")
                    return True

            return False

        except Exception as e:
            logger.error(f"Error fixing resolution: {e}")
            return False

    async def fix_quality(self, workflow: Dict, reason: str, quality_result: Dict) -> bool:
        """Fix quality issues by adjusting sampling parameters"""
        try:
            corrections_applied = False

            # Find KSampler node
            for node_id, node_data in workflow.get('prompt', {}).items():
                if node_data.get('class_type') == 'KSampler':
                    inputs = node_data.get('inputs', {})

                    # Increase steps for better quality
                    current_steps = inputs.get('steps', 20)
                    if current_steps < 30:
                        inputs['steps'] = min(50, current_steps + 10)
                        corrections_applied = True

                    # Adjust CFG scale
                    current_cfg = inputs.get('cfg', 7.0)
                    if current_cfg < 8.0:
                        inputs['cfg'] = min(12.0, current_cfg + 1.5)
                        corrections_applied = True

                    # Use better sampler if needed
                    current_sampler = inputs.get('sampler_name', 'euler')
                    if current_sampler in ['euler', 'euler_a']:
                        inputs['sampler_name'] = 'dpmpp_2m'
                        inputs['scheduler'] = 'karras'
                        corrections_applied = True

                    # Reduce denoising if too high
                    current_denoise = inputs.get('denoise', 1.0)
                    if current_denoise > 0.9:
                        inputs['denoise'] = 0.85
                        corrections_applied = True

            if corrections_applied:
                logger.info("Applied quality corrections: increased steps, adjusted CFG, improved sampler")

            return corrections_applied

        except Exception as e:
            logger.error(f"Error fixing quality: {e}")
            return False

    async def fix_duration(self, workflow: Dict, reason: str, quality_result: Dict) -> bool:
        """Fix duration issues for video generation"""
        try:
            # Look for video generation nodes
            for node_id, node_data in workflow.get('prompt', {}).items():
                class_type = node_data.get('class_type', '')

                # Common video nodes
                if 'video' in class_type.lower() or 'animate' in class_type.lower():
                    inputs = node_data.get('inputs', {})

                    # Increase frame count or duration
                    if 'frame_count' in inputs:
                        current_frames = inputs.get('frame_count', 16)
                        inputs['frame_count'] = max(30, current_frames * 1.5)
                        logger.info(f"Duration correction: increased frames to {inputs['frame_count']}")
                        return True

                    if 'duration' in inputs:
                        current_duration = inputs.get('duration', 1.0)
                        inputs['duration'] = max(3.0, current_duration * 2)
                        logger.info(f"Duration correction: increased duration to {inputs['duration']}s")
                        return True

            return False

        except Exception as e:
            logger.error(f"Error fixing duration: {e}")
            return False

    async def fix_fps(self, workflow: Dict, reason: str, quality_result: Dict) -> bool:
        """Fix frame rate issues"""
        try:
            for node_id, node_data in workflow.get('prompt', {}).items():
                class_type = node_data.get('class_type', '')

                if 'video' in class_type.lower() or 'fps' in str(node_data).lower():
                    inputs = node_data.get('inputs', {})

                    if 'fps' in inputs:
                        current_fps = inputs.get('fps', 15)
                        inputs['fps'] = max(24, current_fps + 6)
                        logger.info(f"FPS correction: increased to {inputs['fps']}")
                        return True

                    if 'frame_rate' in inputs:
                        current_fps = inputs.get('frame_rate', 15)
                        inputs['frame_rate'] = max(24, current_fps + 6)
                        logger.info(f"Frame rate correction: increased to {inputs['frame_rate']}")
                        return True

            return False

        except Exception as e:
            logger.error(f"Error fixing FPS: {e}")
            return False

    async def fix_brightness(self, workflow: Dict, reason: str, quality_result: Dict) -> bool:
        """Fix brightness issues by adjusting prompt"""
        try:
            # Find text encode nodes and adjust prompts
            for node_id, node_data in workflow.get('prompt', {}).items():
                if node_data.get('class_type') == 'CLIPTextEncode':
                    inputs = node_data.get('inputs', {})
                    current_text = inputs.get('text', '')

                    if 'bright' not in current_text.lower() and 'well-lit' not in current_text.lower():
                        # Add brightness enhancement to positive prompt
                        if len(current_text) > 50:  # Likely positive prompt
                            inputs['text'] = f"{current_text}, well-lit, bright lighting, proper exposure"
                            logger.info("Brightness correction: added lighting enhancement to prompt")
                            return True

            return False

        except Exception as e:
            logger.error(f"Error fixing brightness: {e}")
            return False

    async def fix_contrast(self, workflow: Dict, reason: str, quality_result: Dict) -> bool:
        """Fix contrast issues"""
        try:
            for node_id, node_data in workflow.get('prompt', {}).items():
                if node_data.get('class_type') == 'CLIPTextEncode':
                    inputs = node_data.get('inputs', {})
                    current_text = inputs.get('text', '')

                    if 'contrast' not in current_text.lower() and 'sharp' not in current_text.lower():
                        if len(current_text) > 50:  # Likely positive prompt
                            inputs['text'] = f"{current_text}, high contrast, sharp details, vivid colors"
                            logger.info("Contrast correction: added contrast enhancement to prompt")
                            return True

            return False

        except Exception as e:
            logger.error(f"Error fixing contrast: {e}")
            return False

    async def fix_blur(self, workflow: Dict, reason: str, quality_result: Dict) -> bool:
        """Fix blur issues"""
        try:
            corrections_applied = False

            # Increase sampling steps and adjust CFG
            for node_id, node_data in workflow.get('prompt', {}).items():
                if node_data.get('class_type') == 'KSampler':
                    inputs = node_data.get('inputs', {})

                    # More steps for sharper results
                    current_steps = inputs.get('steps', 20)
                    inputs['steps'] = max(40, current_steps + 15)

                    # Adjust CFG for sharpness
                    inputs['cfg'] = 9.0

                    corrections_applied = True

                # Add sharpness to prompt
                elif node_data.get('class_type') == 'CLIPTextEncode':
                    inputs = node_data.get('inputs', {})
                    current_text = inputs.get('text', '')

                    if 'sharp' not in current_text.lower() and len(current_text) > 50:
                        inputs['text'] = f"{current_text}, sharp focus, high detail, crisp image"
                        corrections_applied = True

            if corrections_applied:
                logger.info("Blur correction: increased steps, adjusted CFG, added sharpness to prompt")

            return corrections_applied

        except Exception as e:
            logger.error(f"Error fixing blur: {e}")
            return False

    async def apply_learned_optimizations(self, workflow: Dict, prompt: str):
        """Apply optimizations learned from successful generations"""
        try:
            prompt_hash = hashlib.md5(prompt.encode()).hexdigest()

            # Check if we have successful parameters for similar prompts
            best_match = None
            best_score = 0

            for stored_hash, stored_data in self.successful_params.items():
                # Simple similarity check - in production, use more sophisticated matching
                if stored_data['quality_score'] > best_score:
                    best_match = stored_data
                    best_score = stored_data['quality_score']

            if best_match and best_score > 0.8:
                # Apply successful parameters
                successful_params = best_match['params']

                for node_id, node_data in workflow.get('prompt', {}).items():
                    if node_id in successful_params:
                        stored_inputs = successful_params[node_id].get('inputs', {})
                        current_inputs = node_data.get('inputs', {})

                        # Apply key parameters that often affect quality
                        for param in ['steps', 'cfg', 'sampler_name', 'scheduler']:
                            if param in stored_inputs:
                                current_inputs[param] = stored_inputs[param]

                logger.info(f"Applied learned optimizations from successful generation (score: {best_score})")

        except Exception as e:
            logger.error(f"Error applying learned optimizations: {e}")

    async def enhance_prompt_with_echo(self, workflow: Dict, original_prompt: str, rejection_reasons: List[str]) -> Dict:
        """Use Echo Brain to enhance the prompt based on quality issues"""
        try:
            # Prepare enhancement request for Echo Brain
            enhancement_request = {
                "original_prompt": original_prompt,
                "quality_issues": rejection_reasons,
                "task": "enhance_prompt_for_quality",
                "context": "anime_quality_correction"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.echo_brain_url}/api/query", json={
                    "query": f"Enhance this anime prompt to fix quality issues: {original_prompt}. Issues to fix: {', '.join(rejection_reasons)}",
                    "context": "anime_quality_enhancement"
                }) as response:

                    if response.status == 200:
                        result = await response.json()
                        enhanced_prompt = result.get('response', original_prompt)

                        # Update the positive prompt in the workflow
                        for node_id, node_data in workflow.get('prompt', {}).items():
                            if node_data.get('class_type') == 'CLIPTextEncode':
                                inputs = node_data.get('inputs', {})
                                current_text = inputs.get('text', '')

                                # Assume the longer text is the positive prompt
                                if len(current_text) > len(enhanced_prompt) * 0.5:
                                    inputs['text'] = enhanced_prompt
                                    logger.info(f"Enhanced prompt with Echo Brain: {enhanced_prompt[:100]}...")
                                    break

        except Exception as e:
            logger.error(f"Error enhancing prompt with Echo Brain: {e}")

        return workflow

    async def submit_corrected_workflow(self, workflow: Dict, original_prompt_id: str) -> Optional[str]:
        """Submit corrected workflow to ComfyUI"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.comfyui_url}/prompt", json=workflow) as response:
                    if response.status == 200:
                        result = await response.json()
                        new_prompt_id = result.get("prompt_id")

                        if new_prompt_id:
                            logger.info(f"✅ Submitted corrected workflow: {new_prompt_id} (correction of {original_prompt_id})")

                            # Store the correction relationship
                            await self.store_correction_relationship(original_prompt_id, new_prompt_id, workflow)

                            return new_prompt_id
                    else:
                        logger.error(f"Failed to submit corrected workflow: {response.status}")

        except Exception as e:
            logger.error(f"Error submitting corrected workflow: {e}")

        return None

    async def store_failed_attempt(self, prompt_hash: str, workflow: Dict, rejection_reasons: List[str]):
        """Store failed attempt for learning"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO failed_workflows (prompt_hash, workflow_params, rejection_reasons, created_at)
                VALUES (%s, %s, %s, %s)
            """, (
                prompt_hash,
                json.dumps(workflow),
                json.dumps(rejection_reasons),
                datetime.now()
            ))

            conn.commit()
            cur.close()
            conn.close()

        except Exception as e:
            logger.error(f"Error storing failed attempt: {e}")

    async def store_successful_attempt(self, prompt_hash: str, workflow: Dict, quality_score: float):
        """Store successful attempt for learning"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO successful_workflows (prompt_hash, workflow_params, quality_score, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (prompt_hash) DO UPDATE SET
                    workflow_params = EXCLUDED.workflow_params,
                    quality_score = EXCLUDED.quality_score,
                    updated_at = NOW()
                WHERE successful_workflows.quality_score < EXCLUDED.quality_score
            """, (
                prompt_hash,
                json.dumps(workflow),
                quality_score,
                datetime.now()
            ))

            conn.commit()
            cur.close()
            conn.close()

        except Exception as e:
            logger.error(f"Error storing successful attempt: {e}")

    async def store_correction_relationship(self, original_prompt_id: str, corrected_prompt_id: str, corrected_workflow: Dict):
        """Store the relationship between original and corrected workflows"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO workflow_corrections (original_prompt_id, corrected_prompt_id, corrected_workflow, created_at)
                VALUES (%s, %s, %s, %s)
            """, (
                original_prompt_id,
                corrected_prompt_id,
                json.dumps(corrected_workflow),
                datetime.now()
            ))

            conn.commit()
            cur.close()
            conn.close()

        except Exception as e:
            logger.error(f"Error storing correction relationship: {e}")

    async def get_correction_success_rate(self) -> Dict:
        """Get statistics on correction success rates"""
        try:
            conn = psycopg2.connect(**self.db_params)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT
                    COUNT(*) as total_corrections,
                    SUM(CASE WHEN qa2.passes_standards THEN 1 ELSE 0 END) as successful_corrections,
                    AVG(qa2.quality_score) as avg_corrected_quality,
                    AVG(qa1.quality_score) as avg_original_quality
                FROM workflow_corrections wc
                JOIN quality_assessments qa1 ON qa1.prompt_id = wc.original_prompt_id
                JOIN quality_assessments qa2 ON qa2.prompt_id = wc.corrected_prompt_id
                WHERE wc.created_at > NOW() - INTERVAL '7 days'
            """)

            result = cur.fetchone()

            if result and result['total_corrections'] > 0:
                success_rate = result['successful_corrections'] / result['total_corrections']
                quality_improvement = result['avg_corrected_quality'] - result['avg_original_quality']

                return {
                    'success_rate': success_rate,
                    'total_corrections': result['total_corrections'],
                    'successful_corrections': result['successful_corrections'],
                    'quality_improvement': quality_improvement,
                    'avg_corrected_quality': result['avg_corrected_quality'],
                    'avg_original_quality': result['avg_original_quality']
                }

            cur.close()
            conn.close()

        except Exception as e:
            logger.error(f"Error getting correction success rate: {e}")

        return {
            'success_rate': 0.0,
            'total_corrections': 0,
            'successful_corrections': 0,
            'quality_improvement': 0.0
        }

# Database table creation
async def create_correction_tables():
    """Create tables for auto-correction system"""
    try:
        # Use secure database connection parameters
        auto_correction = AutoCorrectionSystem()
        conn = psycopg2.connect(**auto_correction.db_params)
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS failed_workflows (
                id SERIAL PRIMARY KEY,
                prompt_hash VARCHAR(32),
                workflow_params JSONB,
                rejection_reasons JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS successful_workflows (
                id SERIAL PRIMARY KEY,
                prompt_hash VARCHAR(32) UNIQUE,
                workflow_params JSONB,
                quality_score FLOAT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS workflow_corrections (
                id SERIAL PRIMARY KEY,
                original_prompt_id VARCHAR(255),
                corrected_prompt_id VARCHAR(255),
                corrected_workflow JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_failed_prompt_hash ON failed_workflows(prompt_hash);
            CREATE INDEX IF NOT EXISTS idx_successful_prompt_hash ON successful_workflows(prompt_hash);
            CREATE INDEX IF NOT EXISTS idx_corrections_original ON workflow_corrections(original_prompt_id);
            CREATE INDEX IF NOT EXISTS idx_corrections_corrected ON workflow_corrections(corrected_prompt_id);
        """)

        conn.commit()
        cur.close()
        conn.close()
        logger.info("Auto-correction tables created/verified")

    except Exception as e:
        logger.error(f"Error creating correction tables: {e}")

# API endpoints for integration
async def main():
    """Main entry point for testing"""
    await create_correction_tables()

    # Example usage
    correction_system = AutoCorrectionSystem()

    # Example quality failure
    quality_result = {
        'quality_score': 0.3,
        'resolution': (512, 512),
        'passes_standards': False,
        'rejection_reasons': ['Resolution too low: 512x512 < 1024x1024', 'Overall quality too low: 0.3 < 0.7']
    }

    # Example workflow
    example_workflow = {
        "prompt": {
            "1": {
                "inputs": {
                    "text": "anime girl fighting monster",
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "3": {
                "inputs": {
                    "seed": 12345,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler"
            },
            "5": {
                "inputs": {
                    "width": 512,
                    "height": 512,
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage"
            }
        }
    }

    corrected = await correction_system.process_quality_failure(
        "test_prompt_123",
        "anime girl fighting monster",
        quality_result,
        example_workflow
    )

    if corrected:
        print("✅ Correction generated successfully")
        print(json.dumps(corrected, indent=2))
    else:
        print("❌ Could not generate correction")

if __name__ == "__main__":
    asyncio.run(main())