"""
Creative Workflow Orchestrator - Manages the complete anime production pipeline
From story concept to final rendered output
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

import sys
sys.path.insert(0, '/opt/tower-anime-production')

from api.echo_brain.assist import EchoBrainAssistant

# Create database function
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = f"postgresql://patrick:{os.getenv('DATABASE_PASSWORD', '***REMOVED***')}@localhost/anime_production"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

logger = logging.getLogger(__name__)


class CreativeWorkflowOrchestrator:
    """
    Orchestrates the complete creative pipeline:
    Story → Characters → Scenes → Visuals
    """

    def __init__(self, project_id: int, db_session: Session = None):
        self.project_id = project_id
        self.db = db_session
        if not self.db:
            try:
                self.db = next(get_db())
            except:
                pass
        self.echo_brain = EchoBrainAssistant(self.db)
        self.generation_profiles = self._load_generation_profiles()
        self.checkpoints = self._load_available_checkpoints()

    def _load_generation_profiles(self) -> List[Dict]:
        """Load available generation profiles from database"""
        try:
            result = self.db.execute(
                text("SELECT * FROM generation_profiles WHERE is_active = true")
            )
            profiles = result.fetchall()
            return [dict(p._mapping) for p in profiles] if profiles else []
        except Exception as e:
            logger.error(f"Could not load generation profiles: {e}")
            return []

    def _load_available_checkpoints(self) -> List[Dict]:
        """Load available model checkpoints"""
        try:
            result = self.db.execute(
                text("SELECT * FROM ai_models WHERE model_type = 'checkpoint' AND is_active = true")
            )
            checkpoints = result.fetchall()
            return [dict(c._mapping) for c in checkpoints] if checkpoints else []
        except Exception as e:
            logger.error(f"Could not load checkpoints: {e}")
            return []

    async def create_complete_episode(self, episode_outline: Dict) -> Dict:
        """
        Full pipeline: Story → Characters → Scenes → Images
        """
        episode_id = None
        generated_assets = []

        try:
            # 1. Save episode to database
            episode_id = await self._save_episode(episode_outline)

            # 2. Generate detailed scene descriptions
            scenes = await self._expand_all_scenes(episode_outline.get('scenes', []))

            # 3. Process each scene
            for scene in scenes:
                scene_assets = await self._process_scene(scene, episode_id)
                generated_assets.extend(scene_assets)

            # 4. Update episode status
            await self._update_episode_status(episode_id, 'processing', generated_assets)

            return {
                "success": True,
                "episode_id": episode_id,
                "scenes_processed": len(scenes),
                "assets_generated": len(generated_assets),
                "episode_data": episode_outline
            }

        except Exception as e:
            logger.error(f"Episode creation failed: {e}")
            if episode_id:
                await self._update_episode_status(episode_id, 'failed')

            return {
                "success": False,
                "error": str(e),
                "episode_id": episode_id
            }

    async def _save_episode(self, episode_data: Dict) -> int:
        """Save episode to database"""
        try:
            result = self.db.execute(
                text("""
                INSERT INTO episodes (
                    storyline_id,
                    title,
                    description,
                    scene_breakdown,
                    status
                ) VALUES (
                    :storyline_id,
                    :title,
                    :description,
                    :scene_breakdown,
                    'pending'
                ) RETURNING id
                """),
                {
                    "storyline_id": episode_data.get('storyline_id'),
                    "title": episode_data.get('title', 'Untitled Episode'),
                    "description": episode_data.get('synopsis', ''),
                    "scene_breakdown": json.dumps(episode_data.get('scenes', []))
                }
            )
            self.db.commit()
            return result.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to save episode: {e}")
            self.db.rollback()
            raise

    async def _expand_all_scenes(self, scenes: List[Dict]) -> List[Dict]:
        """Expand all scene descriptions using Echo Brain"""
        expanded_scenes = []

        for scene in scenes:
            expanded = await self.echo_brain.expand_scene_description(
                scene.get('description', ''),
                context={
                    'scene_number': scene.get('scene_number'),
                    'characters': scene.get('characters', []),
                    'mood': scene.get('mood', 'neutral')
                }
            )

            if expanded['success']:
                scene.update(expanded['scene'])

            expanded_scenes.append(scene)

        return expanded_scenes

    async def _process_scene(self, scene: Dict, episode_id: int) -> List[Dict]:
        """Process a single scene: characters → visual prompts → generation"""
        generated_assets = []

        # Process each character in the scene
        for character_ref in scene.get('characters', []):
            character = await self._get_or_create_character(character_ref)

            if character:
                # Generate visual prompt for this character in this scene
                visual_prompt = await self._create_character_visual_prompt(
                    character, scene
                )

                # Queue image generation
                job_id = await self._queue_generation(
                    visual_prompt,
                    character_id=character['id'],
                    scene_id=scene.get('id'),
                    episode_id=episode_id
                )

                generated_assets.append({
                    'job_id': job_id,
                    'character_id': character['id'],
                    'scene': scene.get('scene_number'),
                    'prompt': visual_prompt['prompt']
                })

        return generated_assets

    async def _get_or_create_character(self, character_ref: Any) -> Optional[Dict]:
        """Get existing character or create new one"""
        try:
            if isinstance(character_ref, int):
                # Character ID provided
                result = self.db.execute(
                    text("SELECT * FROM characters WHERE id = :id"),
                    {"id": character_ref}
                )
                character = result.fetchone()
                return dict(character._mapping) if character else None

            elif isinstance(character_ref, str):
                # Character name provided - check if exists
                result = self.db.execute(
                    text("SELECT * FROM characters WHERE name = :name AND project_id = :project_id"),
                    {"name": character_ref, "project_id": self.project_id}
                )
                character = result.fetchone()

                if character:
                    return dict(character._mapping)
                else:
                    # Create new character
                    return await self._create_character(character_ref)

            elif isinstance(character_ref, dict):
                # Character data provided
                name = character_ref.get('name')
                if not name:
                    return None

                result = self.db.execute(
                    text("SELECT * FROM characters WHERE name = :name AND project_id = :project_id"),
                    {"name": name, "project_id": self.project_id}
                )
                character = result.fetchone()

                if character:
                    return dict(character._mapping)
                else:
                    return await self._create_character(name, character_ref.get('description'))

        except Exception as e:
            logger.error(f"Character retrieval failed: {e}")
            return None

    async def _create_character(self, name: str, description: str = None) -> Dict:
        """Create a new character"""
        try:
            # Generate character description if not provided
            if not description:
                description = f"Character named {name} in anime style"

            # Create embedding for character
            embedding = await self.echo_brain.create_embedding(f"{name} {description}")

            result = self.db.execute(
                text("""
                INSERT INTO characters (
                    project_id,
                    name,
                    description,
                    created_at
                ) VALUES (
                    :project_id,
                    :name,
                    :description,
                    CURRENT_TIMESTAMP
                ) RETURNING id, project_id, name, description
                """),
                {
                    "project_id": self.project_id,
                    "name": name,
                    "description": description
                }
            )
            self.db.commit()

            character = result.fetchone()
            return dict(character._mapping) if character else None

        except Exception as e:
            logger.error(f"Character creation failed: {e}")
            self.db.rollback()
            return None

    async def _create_character_visual_prompt(self, character: Dict, scene: Dict) -> Dict:
        """Generate visual prompt for character in specific scene context"""

        # Get style suggestion from Echo Brain
        style_suggestion = await self.echo_brain.suggest_visual_style(
            character_description=character.get('description', ''),
            mood=scene.get('mood', 'neutral'),
            art_style='anime'
        )

        if style_suggestion['success']:
            style_data = style_suggestion['style']
            prompt = style_data.get('main_prompt', '')
            negative = style_data.get('negative_prompt', '')
            checkpoint_name = style_data.get('checkpoint_recommendation', '')
        else:
            # Fallback prompt
            prompt = f"{character.get('name', 'character')}, {character.get('description', '')}, anime style, {scene.get('mood', 'neutral')} mood"
            negative = "worst quality, low quality, bad anatomy"
            checkpoint_name = None

        # Select best checkpoint
        checkpoint = self._select_checkpoint(
            checkpoint_name or scene.get('visual_style', 'anime')
        )

        return {
            'prompt': prompt,
            'negative_prompt': negative,
            'checkpoint': checkpoint,
            'character_id': character.get('id'),
            'scene_context': scene
        }

    def _select_checkpoint(self, style_keywords: str) -> str:
        """Smart checkpoint selection based on style keywords"""

        if not self.checkpoints:
            return "AOM3A1B.safetensors"  # Default fallback

        # Simple keyword matching for now
        # TODO: Implement embedding-based similarity search

        style_lower = style_keywords.lower()

        for checkpoint in self.checkpoints:
            checkpoint_name = checkpoint.get('model_name', '').lower()
            description = checkpoint.get('description', '').lower()

            # Check for keyword matches
            if any(keyword in checkpoint_name or keyword in description
                   for keyword in ['anime', 'aom', 'anything']):
                return checkpoint.get('file_path', checkpoint.get('model_name'))

        # Return first available checkpoint
        return self.checkpoints[0].get('file_path', self.checkpoints[0].get('model_name'))

    async def _queue_generation(self, visual_data: Dict, character_id: int = None,
                                scene_id: int = None, episode_id: int = None) -> int:
        """Queue image/video generation job"""
        try:
            # Create generation job in database
            result = self.db.execute(
                text("""
                INSERT INTO production_jobs (
                    project_id,
                    prompt,
                    negative_prompt,
                    checkpoint,
                    character_id,
                    metadata,
                    status,
                    created_at
                ) VALUES (
                    :project_id,
                    :prompt,
                    :negative_prompt,
                    :checkpoint,
                    :character_id,
                    :metadata,
                    'pending',
                    CURRENT_TIMESTAMP
                ) RETURNING id
                """),
                {
                    "project_id": self.project_id,
                    "prompt": visual_data.get('prompt', ''),
                    "negative_prompt": visual_data.get('negative_prompt', ''),
                    "checkpoint": visual_data.get('checkpoint', 'AOM3A1B.safetensors'),
                    "character_id": character_id,
                    "metadata": json.dumps({
                        'scene_id': scene_id,
                        'episode_id': episode_id,
                        'scene_context': visual_data.get('scene_context', {})
                    })
                }
            )
            self.db.commit()

            job_id = result.fetchone()[0]

            # TODO: Trigger actual generation through ComfyUI API
            # For now, just return the job ID

            return job_id

        except Exception as e:
            logger.error(f"Failed to queue generation: {e}")
            self.db.rollback()
            return 0

    async def _update_episode_status(self, episode_id: int, status: str, assets: List = None):
        """Update episode processing status"""
        try:
            metadata = {
                'status': status,
                'updated_at': datetime.now().isoformat()
            }

            if assets:
                metadata['generated_assets'] = assets

            self.db.execute(
                text("""
                UPDATE episodes
                SET status = :status,
                    metadata = :metadata
                WHERE id = :episode_id
                """),
                {
                    "status": status,
                    "metadata": json.dumps(metadata),
                    "episode_id": episode_id
                }
            )
            self.db.commit()

        except Exception as e:
            logger.error(f"Failed to update episode status: {e}")
            self.db.rollback()

    async def analyze_style_consistency(self, project_id: int = None) -> Dict:
        """Analyze visual style consistency across project"""
        project_id = project_id or self.project_id

        try:
            # Get all generated images for project
            result = self.db.execute(
                text("""
                SELECT id, prompt, checkpoint, character_id, output_path
                FROM production_jobs
                WHERE project_id = :project_id
                    AND status = 'completed'
                    AND output_path IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 100
                """),
                {"project_id": project_id}
            )

            generations = [dict(g._mapping) for g in result.fetchall()]

            if not generations:
                return {
                    "success": False,
                    "message": "No completed generations found"
                }

            # Group by character
            by_character = {}
            for gen in generations:
                char_id = gen.get('character_id', 'unknown')
                if char_id not in by_character:
                    by_character[char_id] = []
                by_character[char_id].append(gen)

            # Analyze consistency per character
            consistency_reports = {}
            for char_id, char_gens in by_character.items():
                if len(char_gens) > 1:
                    analysis = await self.echo_brain.analyze_character_consistency(
                        character_id=char_id,
                        generated_images=[g['output_path'] for g in char_gens]
                    )
                    consistency_reports[char_id] = analysis

            return {
                "success": True,
                "total_analyzed": len(generations),
                "characters_analyzed": len(consistency_reports),
                "consistency_reports": consistency_reports
            }

        except Exception as e:
            logger.error(f"Style consistency analysis failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def suggest_improvements(self, episode_id: int) -> Dict:
        """Suggest improvements for an episode based on QC analysis"""
        try:
            # Get episode data
            result = self.db.execute(
                text("SELECT * FROM episodes WHERE id = :id"),
                {"id": episode_id}
            )
            episode = result.fetchone()

            if not episode:
                return {"success": False, "message": "Episode not found"}

            episode_data = dict(episode._mapping)

            # Get QC analysis if available
            qc_result = self.db.execute(
                text("""
                SELECT * FROM qc_analyses
                WHERE episode_id = :episode_id
                ORDER BY created_at DESC
                LIMIT 1
                """),
                {"episode_id": episode_id}
            )
            qc_analysis = qc_result.fetchone()

            suggestions = {
                "episode_id": episode_id,
                "title": episode_data.get('title'),
                "improvements": []
            }

            if qc_analysis:
                qc_data = dict(qc_analysis._mapping)
                score = qc_data.get('overall_score', 0)

                if score < 0.7:
                    suggestions['improvements'].append({
                        "area": "quality",
                        "current_score": score,
                        "target_score": 0.8,
                        "actions": [
                            "Increase generation steps to 30+",
                            "Use higher quality checkpoint",
                            "Adjust CFG scale between 7-9",
                            "Enable quality enhancement LoRAs"
                        ]
                    })

                # Check for specific issues
                issues = json.loads(qc_data.get('issues', '[]'))
                for issue in issues:
                    if 'motion' in issue.lower():
                        suggestions['improvements'].append({
                            "area": "motion",
                            "issue": issue,
                            "actions": [
                                "Enable AnimateDiff for video generation",
                                "Increase motion_bucket_id to 180+",
                                "Add temporal consistency LoRA",
                                "Use video-specific checkpoint"
                            ]
                        })
                    elif 'consistency' in issue.lower():
                        suggestions['improvements'].append({
                            "area": "character_consistency",
                            "issue": issue,
                            "actions": [
                                "Use character-specific LoRA",
                                "Maintain same seed across scenes",
                                "Lock style parameters",
                                "Create character reference sheet"
                            ]
                        })

            return {
                "success": True,
                "suggestions": suggestions
            }

        except Exception as e:
            logger.error(f"Improvement suggestion failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }