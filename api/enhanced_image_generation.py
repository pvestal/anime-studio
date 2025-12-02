"""
Enhanced Image Generation with Project-Aware Asset Management
Integrates ProjectAssetManager for organized file structure and character consistency
"""

import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from project_asset_manager import ProjectAssetManager, CharacterConsistencyManager
from image_generation_fixed import generate_anime_image_production


async def generate_project_aware_image(
    prompt: str,
    project_id: int = 1,
    character_name: Optional[str] = None,
    scene_id: Optional[int] = None,
    asset_type: str = "character",
    quality: str = "medium",
    style: str = "anime",
    job_id: int = None,
    db_session = None
) -> Dict:
    """
    Enhanced image generation with project-aware asset management

    Args:
        prompt: Generation prompt
        project_id: Project ID for organization
        character_name: Character name for consistency
        scene_id: Scene ID if applicable
        asset_type: Type of asset ('character', 'scene', 'background', 'prop')
        quality: Generation quality
        style: Art style
        job_id: Database job ID
        db_session: Database session

    Returns:
        Enhanced result with organized file paths
    """

    # Initialize project asset manager
    asset_manager = ProjectAssetManager(project_id, db_session)
    consistency_manager = CharacterConsistencyManager(asset_manager)

    # Parse prompt for character information if not provided
    if not character_name and asset_type == "character":
        character_name = extract_character_name_from_prompt(prompt)

    try:
        # Get base workflow
        workflow_path = "/opt/tower-anime-production/workflows/comfyui/single_image.json"
        with open(workflow_path, 'r') as f:
            base_workflow = json.load(f)

        # Apply character consistency if character specified
        if character_name and asset_type == "character":
            enhanced_workflow = consistency_manager.prepare_character_workflow(
                character_name, base_workflow
            )

            # Update the prompt with character consistency tags
            enhanced_prompt = enhance_prompt_for_character(prompt, character_name, asset_manager)
        else:
            enhanced_workflow = base_workflow
            enhanced_prompt = prompt

        # Update database job with project context
        if db_session and job_id:
            from sqlalchemy import text

            db_session.execute(
                text("""
                    UPDATE anime_api.production_jobs
                    SET project_id = :project_id,
                        character_name = :character_name,
                        scene_id = :scene_id,
                        asset_type = :asset_type
                    WHERE id = :job_id
                """),
                {
                    "project_id": project_id,
                    "character_name": character_name,
                    "scene_id": scene_id,
                    "asset_type": asset_type,
                    "job_id": job_id
                }
            )
            db_session.commit()

        # Generate image using production function
        generation_result = await generate_anime_image_production(
            prompt=enhanced_prompt,
            quality=quality,
            style=style,
            job_id=job_id,
            db=db_session
        )

        if not generation_result["success"]:
            return generation_result

        # Check if file was actually generated
        comfyui_output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
        generated_files = []

        # Find the most recent files matching the job
        for pattern in [f"*{job_id}*.png", f"*{job_id}*.jpg", "*.png", "*.jpg"]:
            potential_files = list(comfyui_output_dir.glob(pattern))
            if potential_files:
                # Sort by creation time, get most recent
                potential_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                # Take the most recent file created in last 5 minutes
                recent_files = [
                    f for f in potential_files[:5]
                    if (datetime.now().timestamp() - f.stat().st_mtime) < 300
                ]
                if recent_files:
                    generated_files.extend(recent_files)
                    break

        if not generated_files:
            # Fallback: try to find any very recent file
            all_files = list(comfyui_output_dir.glob("*.png"))
            if all_files:
                all_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                recent_file = all_files[0]
                if (datetime.now().timestamp() - recent_file.stat().st_mtime) < 300:
                    generated_files = [recent_file]

        if not generated_files:
            return {
                "success": False,
                "error": f"Generated file not found for job {job_id}",
                "job_id": job_id
            }

        # Organize the generated file using ProjectAssetManager
        source_file = str(generated_files[0])

        generation_metadata = {
            "prompt": enhanced_prompt,
            "original_prompt": prompt,
            "quality": quality,
            "style": style,
            "workflow_type": "single_image",
            "generation_time": generation_result.get("estimated_time", "unknown"),
            "model_used": enhanced_workflow.get("1", {}).get("inputs", {}).get("ckpt_name", "unknown")
        }

        organized_path = asset_manager.organize_generated_file(
            source_path=source_file,
            asset_type=asset_type,
            prompt=enhanced_prompt,
            job_id=job_id,
            character_name=character_name,
            scene_id=scene_id,
            generation_metadata=generation_metadata
        )

        # Update database with organized path
        if db_session and job_id:
            db_session.execute(
                text("""
                    UPDATE anime_api.production_jobs
                    SET output_path = :organized_path,
                        status = 'completed',
                        completion_metadata = :metadata
                    WHERE id = :job_id
                """),
                {
                    "organized_path": organized_path,
                    "metadata": json.dumps(generation_metadata),
                    "job_id": job_id
                }
            )
            db_session.commit()

        # Enhanced result with project context
        enhanced_result = generation_result.copy()
        enhanced_result.update({
            "organized_path": organized_path,
            "original_path": source_file,
            "project_id": project_id,
            "character_name": character_name,
            "scene_id": scene_id,
            "asset_type": asset_type,
            "project_directory": str(asset_manager.project_root),
            "metadata": generation_metadata,
            "file_organization": "project_based"
        })

        return enhanced_result

    except Exception as e:
        error_result = {
            "success": False,
            "error": f"Project-aware generation failed: {str(e)}",
            "job_id": job_id,
            "project_id": project_id
        }

        # Update database with error
        if db_session and job_id:
            try:
                db_session.execute(
                    text("""
                        UPDATE anime_api.production_jobs
                        SET status = 'failed',
                            error = :error
                        WHERE id = :job_id
                    """),
                    {"error": str(e), "job_id": job_id}
                )
                db_session.commit()
            except Exception as db_error:
                print(f"Database update error: {db_error}")

        return error_result


def extract_character_name_from_prompt(prompt: str) -> Optional[str]:
    """Extract character name from prompt if possible"""
    # Simple extraction - could be enhanced with NLP
    common_names = ["sakura", "hiroshi", "akira", "yuki", "mai", "ken", "rei", "asuka"]

    prompt_lower = prompt.lower()
    for name in common_names:
        if name in prompt_lower:
            return name.title()

    # Check for "character named X" patterns
    if "named " in prompt_lower:
        parts = prompt_lower.split("named ")
        if len(parts) > 1:
            name_part = parts[1].split()[0].strip(",.!")
            if name_part.isalpha():
                return name_part.title()

    return None


def enhance_prompt_for_character(prompt: str, character_name: str, asset_manager: ProjectAssetManager) -> str:
    """Enhance prompt with character-specific consistency tags"""

    # Get project style guide
    style_guide = asset_manager.get_project_style_guide()

    enhanced_prompt = prompt

    # Add character consistency
    if character_name in style_guide:
        char_style = style_guide[character_name]

        # Add character-specific details
        if "hair_color" in char_style:
            enhanced_prompt += f", {char_style['hair_color']} hair"
        if "eye_color" in char_style:
            enhanced_prompt += f", {char_style['eye_color']} eyes"
        if "clothing_style" in char_style:
            enhanced_prompt += f", {char_style['clothing_style']}"

    # Add consistency tags
    enhanced_prompt += f", consistent character design, {character_name} character"
    enhanced_prompt += ", masterpiece, best quality, detailed"

    return enhanced_prompt