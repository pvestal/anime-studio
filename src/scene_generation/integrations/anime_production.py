"""
Anime Production Integration
Integration with Tower Anime Production System for scene generation
"""

import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

from .production_export import (
    validate_resolution,
    build_generation_prompt,
    build_generation_parameters,
    optimize_visual_description,
    optimize_technical_specs,
    build_export_result,
    validate_scene_for_generation,
    DEFAULT_MODEL,
)

logger = logging.getLogger(__name__)

class AnimeProductionIntegration:
    """Integration with Tower Anime Production System for video generation"""

    def __init__(self, base_url: str = "http://localhost:8328"):
        self.base_url = base_url.rstrip('/')
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _get_session(self):
        """Get or create aiohttp session"""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def health_check(self) -> bool:
        """Check if Anime Production system is accessible"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/health") as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Anime Production health check failed: {e}")
            return False

    async def export_scene_descriptions(
        self,
        scene_ids: List[int],
        project_id: Optional[int] = None,
        export_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Export scene descriptions to anime production system"""
        try:
            session = await self._get_session()

            # If no project specified, create a new one
            if not project_id:
                project_id = await self._create_anime_project(export_options or {})

            # Prepare export data
            export_data = {
                "project_id": project_id,
                "scene_ids": scene_ids,
                "export_type": "scene_descriptions",
                "options": export_options or {},
                "timestamp": datetime.utcnow().isoformat(),
                "source": "scene_description_generator"
            }

            async with session.post(
                f"{self.base_url}/api/anime/projects/{project_id}/import_scenes",
                json=export_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return build_export_result(result, scene_ids, project_id)
                else:
                    error_text = await response.text()
                    logger.error(f"Scene export failed: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "error": f"Export failed: {error_text}",
                        "project_id": project_id
                    }

        except Exception as e:
            logger.error(f"Scene export error: {e}")
            return {
                "success": False,
                "error": str(e),
                "project_id": project_id
            }

    async def _create_anime_project(self, export_options: Dict[str, Any]) -> int:
        """Create a new anime project for scene export"""
        try:
            session = await self._get_session()

            project_data = {
                "name": export_options.get("project_name", f"Scene Export {datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"),
                "description": export_options.get("project_description", "Auto-generated project from scene descriptions"),
                "type": "scene_description_export",
                "settings": {
                    "resolution": export_options.get("resolution", "1920x1080"),
                    "frame_rate": export_options.get("frame_rate", 24),
                    "aspect_ratio": export_options.get("aspect_ratio", "16:9"),
                    "quality": export_options.get("quality", "high")
                },
                "created_by": "scene_description_generator"
            }

            async with session.post(
                f"{self.base_url}/api/anime/projects",
                json=project_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("id", 1)  # Default to 1 if ID not returned
                else:
                    logger.warning("Failed to create anime project, using default ID")
                    return 1

        except Exception as e:
            logger.error(f"Project creation failed: {e}")
            return 1  # Default project ID

    async def convert_scene_to_generation_prompt(
        self,
        scene_description: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert scene description to anime generation prompt"""

        # Extract key elements for anime generation
        visual_description = scene_description.get("visual_description", "")
        cinematography_notes = scene_description.get("cinematography_notes", "")
        atmosphere_description = scene_description.get("atmosphere_description", "")
        technical_specs = scene_description.get("technical_specifications", {})

        # Create comprehensive generation prompt
        generation_prompt = build_generation_prompt(
            visual_description, cinematography_notes, atmosphere_description, technical_specs
        )

        # Add technical parameters
        generation_parameters = build_generation_parameters(technical_specs)

        return {
            "prompt": generation_prompt,
            "parameters": generation_parameters,
            "scene_metadata": {
                "source": "scene_description_generator",
                "conversion_timestamp": datetime.utcnow().isoformat()
            }
        }

    async def trigger_scene_generation(
        self,
        scene_description: Dict[str, Any],
        project_id: int
    ) -> Dict[str, Any]:
        """Trigger anime generation for a specific scene"""
        try:
            session = await self._get_session()

            # Convert scene to generation format
            generation_data = await self.convert_scene_to_generation_prompt(scene_description)

            # Add project context
            generation_request = {
                "project_id": project_id,
                "prompt": generation_data["prompt"],
                "parameters": generation_data["parameters"],
                "scene_metadata": generation_data["scene_metadata"],
                "priority": "normal"
            }

            async with session.post(
                f"{self.base_url}/api/anime/generate",
                json=generation_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "generation_id": result.get("generation_id"),
                        "queue_position": result.get("queue_position"),
                        "estimated_completion": result.get("estimated_completion"),
                        "status": "queued"
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"Generation trigger failed: {error_text}"
                    }

        except Exception as e:
            logger.error(f"Scene generation trigger failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_generation_status(
        self,
        generation_id: str
    ) -> Dict[str, Any]:
        """Get status of anime generation"""
        try:
            session = await self._get_session()

            async with session.get(
                f"{self.base_url}/api/anime/generate/{generation_id}/status"
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {
                        "status": "unknown",
                        "error": "Could not retrieve generation status"
                    }

        except Exception as e:
            logger.error(f"Generation status check failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def batch_export_scenes(
        self,
        scenes_data: List[Dict[str, Any]],
        export_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Export multiple scenes in batch"""
        try:
            # Create project for batch
            project_id = await self._create_anime_project(export_options or {})

            batch_results = []
            successful_exports = 0
            failed_exports = 0

            for i, scene_data in enumerate(scenes_data):
                try:
                    # Convert scene to generation format
                    generation_data = await self.convert_scene_to_generation_prompt(scene_data)

                    # Trigger generation
                    generation_result = await self.trigger_scene_generation(scene_data, project_id)

                    if generation_result.get("success"):
                        successful_exports += 1
                        batch_results.append({
                            "scene_index": i,
                            "status": "success",
                            "generation_id": generation_result.get("generation_id")
                        })
                    else:
                        failed_exports += 1
                        batch_results.append({
                            "scene_index": i,
                            "status": "failed",
                            "error": generation_result.get("error")
                        })

                except Exception as e:
                    failed_exports += 1
                    batch_results.append({
                        "scene_index": i,
                        "status": "error",
                        "error": str(e)
                    })

            return {
                "success": True,
                "project_id": project_id,
                "batch_summary": {
                    "total_scenes": len(scenes_data),
                    "successful_exports": successful_exports,
                    "failed_exports": failed_exports,
                    "success_rate": successful_exports / len(scenes_data) if scenes_data else 0
                },
                "individual_results": batch_results
            }

        except Exception as e:
            logger.error(f"Batch export failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def validate_scene_for_generation(
        self,
        scene_description: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate scene description for anime generation compatibility"""
        return validate_scene_for_generation(scene_description)

    async def get_project_status(self, project_id: int) -> Dict[str, Any]:
        """Get status of anime project"""
        try:
            session = await self._get_session()

            async with session.get(
                f"{self.base_url}/api/anime/projects/{project_id}"
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {
                        "status": "unknown",
                        "error": "Could not retrieve project status"
                    }

        except Exception as e:
            logger.error(f"Project status check failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def list_available_models(self) -> List[str]:
        """List available anime generation models"""
        try:
            session = await self._get_session()

            async with session.get(
                f"{self.base_url}/api/anime/models"
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("models", [DEFAULT_MODEL])
                else:
                    return [DEFAULT_MODEL]

        except Exception as e:
            logger.error(f"Model listing failed: {e}")
            return [DEFAULT_MODEL]

    async def optimize_scene_for_generation(
        self,
        scene_description: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Optimize scene description for better generation results"""

        optimized = scene_description.copy()

        # Optimize visual description
        visual_desc = scene_description.get("visual_description", "")
        if visual_desc:
            optimized["visual_description"] = optimize_visual_description(visual_desc)

        # Optimize technical specifications
        tech_specs = scene_description.get("technical_specifications", {})
        if tech_specs:
            optimized["technical_specifications"] = optimize_technical_specs(tech_specs)

        # Add generation-specific enhancements
        optimized["generation_optimizations"] = {
            "prompt_enhancement": "Applied anime-specific prompt optimization",
            "technical_optimization": "Optimized technical parameters for generation",
            "quality_enhancement": "Enhanced for professional anime production"
        }

        return optimized
