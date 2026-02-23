"""
Visual Agent
Builds ComfyUI workflows from story bible data and submits them for generation.
All prompts are assembled from the DB — no hardcoded style strings.
"""

import json
import logging
import re
from typing import Optional, Dict, Any
import httpx
import uuid

import sys
import os
sys.path.insert(0, '/opt/anime-studio')

from services.story_engine.story_manager import StoryManager
from services.story_engine.vector_store import StoryVectorStore

logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"


class VisualAgent:
    """
    Generates visual content for scenes using ComfyUI workflows.

    Workflow:
    1. Load scene context from StoryManager.get_scene_with_context()
    2. Assemble visual prompts from: character designs, setting descriptions, mood, camera directions
    3. Build ComfyUI workflow JSON with AnimateDiff nodes
    4. Submit workflow to ComfyUI API
    5. Monitor progress and store results in scene_assets table
    """

    def __init__(self):
        self.story_manager = StoryManager()
        self.vector_store = StoryVectorStore()

    def generate_scene_visuals(self, scene_id: str, style_override: Optional[str] = None) -> dict:
        """
        Generate visual assets for a scene.

        Args:
            scene_id: UUID string of the scene
            style_override: Optional style prompt to override DB settings

        Returns:
            {
                "workflow_id": str,
                "status": str,  # "queued", "running", "completed", "failed"
                "assets": [{"type": str, "path": str, "metadata": dict}],
                "warnings": [...],  # Any issues encountered
                "prompt_used": str  # Final assembled prompt for debugging
            }
        """
        context = self.story_manager.get_scene_with_context(scene_id)
        if not context:
            raise ValueError(f"Scene {scene_id} not found")

        # Assemble visual prompt from story bible
        prompt = self._assemble_visual_prompt(context, style_override)

        # Get production profile for technical settings
        production_profile = self._get_production_profile(context["project_id"])

        # Build ComfyUI workflow
        workflow = self._build_comfyui_workflow(prompt, production_profile, context)

        # Submit to ComfyUI
        workflow_id = self._submit_workflow(workflow)

        # Store initial record in scene_assets
        asset_record = self._create_asset_record(scene_id, workflow_id, prompt, context)

        return {
            "workflow_id": workflow_id,
            "status": "queued",
            "asset_id": asset_record["id"],
            "prompt_used": prompt,
            "warnings": []
        }

    def check_generation_status(self, workflow_id: str) -> dict:
        """Check status of a ComfyUI workflow and update asset record."""
        try:
            response = httpx.get(f"{COMFYUI_URL}/history/{workflow_id}", timeout=30.0)
            response.raise_for_status()

            history = response.json()
            if workflow_id not in history:
                return {"status": "not_found", "message": "Workflow not found in ComfyUI history"}

            workflow_data = history[workflow_id]
            status = workflow_data.get("status", {})

            if status.get("completed", False):
                # Download and store outputs
                outputs = self._process_workflow_outputs(workflow_id, workflow_data)
                self._update_asset_record(workflow_id, "completed", outputs)
                return {"status": "completed", "outputs": outputs}
            elif "error" in status:
                self._update_asset_record(workflow_id, "failed", error=status["error"])
                return {"status": "failed", "error": status["error"]}
            else:
                return {"status": "running", "progress": status.get("progress", 0)}

        except Exception as e:
            logger.error(f"Failed to check workflow status: {e}")
            return {"status": "error", "message": str(e)}

    def _assemble_visual_prompt(self, context: dict, style_override: Optional[str] = None) -> str:
        """Build visual prompt entirely from DB context."""
        scene = context["scene"]
        episode = context["episode"]
        characters = context["characters"]
        world_rules = context.get("world_rules", {})

        # Base setting and mood
        setting = scene.get("setting_description", "unspecified location")
        mood = scene.get("emotional_tone", "neutral")
        camera = scene.get("camera_directions", "medium shot")

        # Character visual descriptions
        char_visuals = []
        for c in characters:
            visual_desc = c.get("visual_description", "")
            outfit = c.get("default_outfit", "")
            if visual_desc or outfit:
                char_visuals.append(f"{c['name']}: {visual_desc} {outfit}".strip())

        char_block = ", ".join(char_visuals) if char_visuals else "no specific characters"

        # Episode tone profile for visual style
        tone_profile = episode.get("tone_profile") or {}
        if isinstance(tone_profile, str):
            try:
                tone_profile = json.loads(tone_profile)
            except:
                tone_profile = {}

        visual_tone = tone_profile.get("visual", "anime style")

        # World visual rules
        visual_rules = world_rules.get("visual", {})
        art_style = visual_rules.get("art_style", "modern anime")
        color_palette = visual_rules.get("color_palette", "vibrant")

        # Use style override or build from DB
        if style_override:
            style_prompt = style_override
        else:
            style_elements = [art_style, color_palette, visual_tone]
            style_prompt = ", ".join([s for s in style_elements if s])

        # Assemble final prompt
        prompt = f"{setting}, {char_block}, {camera}, {mood} mood, {style_prompt}, high quality anime"

        # Clean up prompt
        prompt = re.sub(r',\s*,', ',', prompt)  # Remove double commas
        prompt = re.sub(r'\s+', ' ', prompt)    # Normalize spaces

        return prompt.strip()

    def _get_production_profile(self, project_id: int) -> dict:
        """Get visual production settings from DB."""
        try:
            conn = self.story_manager.get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT settings FROM production_profiles
                    WHERE project_id = %s AND profile_type = 'visual'
                    ORDER BY updated_at DESC LIMIT 1
                """, (project_id,))

                result = cur.fetchone()
                if result:
                    settings = result[0] if isinstance(result, tuple) else result["settings"]
                    if isinstance(settings, str):
                        return json.loads(settings)
                    return settings

        except Exception as e:
            logger.warning(f"Could not load visual production profile: {e}")

        # Default settings
        return {
            "resolution": "1024x1024",
            "steps": 25,
            "cfg_scale": 7.0,
            "sampler": "euler_a",
            "frame_count": 16,  # For AnimateDiff
            "motion_scale": 0.7
        }

    def _build_comfyui_workflow(self, prompt: str, profile: dict, context: dict) -> dict:
        """Build ComfyUI workflow JSON with AnimateDiff nodes."""

        # Extract resolution
        resolution = profile.get("resolution", "1024x1024")
        width, height = map(int, resolution.split('x'))

        workflow = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 42,
                    "steps": profile.get("steps", 25),
                    "cfg": profile.get("cfg_scale", 7.0),
                    "sampler_name": profile.get("sampler", "euler_a"),
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["11", 0],
                    "positive": ["4", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                }
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["11", 1]
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": profile.get("frame_count", 16)
                }
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "low quality, blurry, distorted, bad anatomy",
                    "clip": ["11", 1]
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["12", 0]
                }
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": f"scene_{context['scene']['id']}",
                    "images": ["8", 0]
                }
            },
            "10": {
                "class_type": "AnimateDiffLoader",
                "inputs": {
                    "model_name": "mm_sd_v15_v2.ckpt"
                }
            },
            "11": {
                "class_type": "AnimateDiffModelLoader",
                "inputs": {
                    "model": ["13", 0],
                    "motion_model": ["10", 0]
                }
            },
            "12": {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": "vae-ft-mse-840000-ema-pruned.safetensors"
                }
            },
            "13": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "realisticVisionV60B1_v51VAE.safetensors"
                }
            },
            "14": {
                "class_type": "AnimateDiffCombine",
                "inputs": {
                    "frame_rate": 8,
                    "loop_count": 0,
                    "filename_prefix": f"anim_scene_{context['scene']['id']}",
                    "format": "video/h264-mp4",
                    "pix_fmt": "yuv420p",
                    "crf": 20,
                    "save_metadata": True,
                    "images": ["8", 0]
                }
            }
        }

        return workflow

    def _submit_workflow(self, workflow: dict) -> str:
        """Submit workflow to ComfyUI and return workflow ID."""
        try:
            # Generate unique client ID
            client_id = str(uuid.uuid4())

            # Submit workflow
            response = httpx.post(
                f"{COMFYUI_URL}/prompt",
                json={
                    "prompt": workflow,
                    "client_id": client_id
                },
                timeout=30.0
            )
            response.raise_for_status()

            result = response.json()
            workflow_id = result["prompt_id"]

            logger.info(f"Submitted ComfyUI workflow {workflow_id}")
            return workflow_id

        except Exception as e:
            logger.error(f"Failed to submit ComfyUI workflow: {e}")
            raise

    def _create_asset_record(self, scene_id: str, workflow_id: str, prompt: str, context: dict) -> dict:
        """Create initial asset record in database."""
        try:
            conn = self.story_manager.get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO scene_assets
                    (scene_id, asset_type, generation_prompt, file_path, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    RETURNING id
                """, (
                    scene_id,
                    "visual_animation",
                    prompt,
                    f"pending://{workflow_id}",  # Temporary path until generation completes
                    json.dumps({
                        "workflow_id": workflow_id,
                        "status": "queued",
                        "episode_id": context["episode"]["id"],
                        "project_id": context["project_id"]
                    })
                ))

                result = cur.fetchone()
                asset_id = result[0] if isinstance(result, tuple) else result["id"]

                conn.commit()

                return {"id": asset_id, "workflow_id": workflow_id}

        except Exception as e:
            logger.error(f"Failed to create asset record: {e}")
            raise

    def _update_asset_record(self, workflow_id: str, status: str, outputs: Optional[list] = None, error: Optional[str] = None):
        """Update asset record with generation results."""
        try:
            conn = self.story_manager.get_connection()
            with conn.cursor() as cur:
                if status == "completed" and outputs:
                    # Update with successful results
                    primary_output = outputs[0] if outputs else None
                    file_path = primary_output.get("path", "") if primary_output else ""

                    cur.execute("""
                        UPDATE scene_assets
                        SET file_path = %s,
                            metadata = jsonb_set(
                                metadata,
                                '{status}',
                                '"completed"'
                            ) || jsonb_build_object(
                                'outputs', %s::jsonb,
                                'completed_at', to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
                            ),
                            updated_at = NOW()
                        WHERE metadata->>'workflow_id' = %s
                    """, (file_path, json.dumps(outputs), workflow_id))

                elif status == "failed":
                    # Update with error
                    cur.execute("""
                        UPDATE scene_assets
                        SET metadata = jsonb_set(
                            jsonb_set(metadata, '{status}', '"failed"'),
                            '{error}',
                            %s::jsonb
                        ),
                        updated_at = NOW()
                        WHERE metadata->>'workflow_id' = %s
                    """, (json.dumps(error) if error else 'null', workflow_id))

                conn.commit()

        except Exception as e:
            logger.error(f"Failed to update asset record: {e}")

    def _process_workflow_outputs(self, workflow_id: str, workflow_data: dict) -> list:
        """Download and process ComfyUI workflow outputs."""
        outputs = []

        try:
            # Get output info from workflow data
            output_info = workflow_data.get("outputs", {})

            for node_id, node_outputs in output_info.items():
                for output_type, files in node_outputs.items():
                    if output_type in ["images", "gifs", "videos"]:
                        for file_info in files:
                            filename = file_info.get("filename", "")
                            if filename:
                                # Download file from ComfyUI
                                file_path = self._download_comfyui_file(filename, workflow_id)
                                if file_path:
                                    outputs.append({
                                        "type": output_type.rstrip('s'),  # images -> image
                                        "path": file_path,
                                        "metadata": file_info
                                    })

        except Exception as e:
            logger.error(f"Failed to process workflow outputs: {e}")

        return outputs

    def _download_comfyui_file(self, filename: str, workflow_id: str) -> Optional[str]:
        """Download file from ComfyUI output folder."""
        try:
            # Create output directory
            output_dir = f"/opt/anime-studio/generated_assets/visuals"
            os.makedirs(output_dir, exist_ok=True)

            # Download file
            response = httpx.get(f"{COMFYUI_URL}/view?filename={filename}", timeout=60.0)
            response.raise_for_status()

            # Save with workflow-specific name
            file_ext = filename.split('.')[-1] if '.' in filename else 'png'
            local_filename = f"{workflow_id}_{filename}"
            file_path = os.path.join(output_dir, local_filename)

            with open(file_path, 'wb') as f:
                f.write(response.content)

            logger.info(f"Downloaded visual asset: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Failed to download ComfyUI file {filename}: {e}")
            return None