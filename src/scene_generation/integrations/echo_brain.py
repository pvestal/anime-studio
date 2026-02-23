"""
Echo Brain Integration
Integration with Echo Brain system for collaborative scene creation
"""

import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

from .echo_helpers import (
    extract_scene_elements,
    categorize_optimization_sentences,
    build_quality_metrics,
    extract_validation_recommendations,
    format_production_notes,
    document_professional_enhancements,
    generate_echo_timing_notes,
    DEFAULT_PROFESSIONAL_REQUIREMENTS,
)

logger = logging.getLogger(__name__)

class EchoBrainIntegration:
    """Integration with Echo Brain for advanced scene creation collaboration"""

    def __init__(self, base_url: str = "http://localhost:8309"):
        self.base_url = base_url.rstrip('/')
        self.session = None
        self.conversation_id = "scene_description_agent"

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
        """Check if Echo Brain is accessible"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/echo/health") as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Echo Brain health check failed: {e}")
            return False

    async def collaborative_scene_creation(
        self,
        prompt: str,
        context: Dict[str, Any],
        creative_parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Collaborate with Echo Brain for advanced scene creation"""
        try:
            session = await self._get_session()

            collaboration_request = {
                "query": prompt,
                "conversation_id": self.conversation_id,
                "context": {
                    "agent": "scene_description_generator",
                    "task": "collaborative_scene_creation",
                    "scene_context": context,
                    "creative_parameters": creative_parameters or {},
                    "timestamp": datetime.utcnow().isoformat()
                },
                "parameters": {
                    "creativity": creative_parameters.get("creativity", 0.8) if creative_parameters else 0.8,
                    "technical_focus": True,
                    "professional_output": True
                }
            }

            async with session.post(
                f"{self.base_url}/api/echo/query",
                json=collaboration_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return await self._process_echo_response(result, context)
                else:
                    error_text = await response.text()
                    logger.error(f"Echo Brain collaboration failed: {response.status} - {error_text}")
                    return await self._fallback_scene_creation(prompt, context)

        except Exception as e:
            logger.error(f"Echo Brain collaboration error: {e}")
            return await self._fallback_scene_creation(prompt, context)

    async def _process_echo_response(
        self,
        echo_response: Dict[str, Any],
        original_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process and enhance Echo Brain response"""

        response_text = echo_response.get("response", "")
        metadata = echo_response.get("metadata", {})

        # Extract scene elements from Echo's response
        scene_elements = extract_scene_elements(response_text)

        # Enhance with professional scene description elements
        enhanced_description = await self._enhance_with_professional_elements(
            scene_elements, original_context
        )

        return {
            "success": True,
            "collaboration_type": "echo_brain_enhanced",
            "scene_description": enhanced_description,
            "echo_insights": {
                "original_response": response_text,
                "extracted_elements": scene_elements,
                "model_used": metadata.get("model", "unknown"),
                "response_time": metadata.get("response_time", 0)
            },
            "professional_enhancements": document_professional_enhancements(
                scene_elements, enhanced_description
            )
        }

    async def _enhance_with_professional_elements(
        self,
        scene_elements: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enhance Echo's response with professional scene description elements"""

        enhanced = {
            "professional_visual_description": "",
            "cinematography_notes": "",
            "atmosphere_description": "",
            "timing_notes": "",
            "technical_specifications": {},
            "production_notes": ""
        }

        # Combine visual elements into professional description
        visual_elements = scene_elements.get("visual_elements", [])
        environmental_details = scene_elements.get("environmental_details", [])

        visual_parts = visual_elements + environmental_details
        if visual_parts:
            enhanced["professional_visual_description"] = ". ".join(visual_parts[:3])
        else:
            enhanced["professional_visual_description"] = "Professional visual composition with balanced framing and appropriate lighting"

        # Convert character actions to cinematography notes
        character_actions = scene_elements.get("character_actions", [])
        if character_actions:
            enhanced["cinematography_notes"] = f"Camera work: {'. '.join(character_actions[:2])}"
        else:
            enhanced["cinematography_notes"] = "Standard cinematography with appropriate shot selection and movement"

        # Extract emotional content for atmosphere
        emotional_content = scene_elements.get("emotional_content", [])
        if emotional_content:
            enhanced["atmosphere_description"] = f"Atmospheric mood: {'. '.join(emotional_content[:2])}"
        else:
            enhanced["atmosphere_description"] = "Neutral atmospheric conditions appropriate for scene context"

        # Generate timing notes
        enhanced["timing_notes"] = generate_echo_timing_notes(scene_elements, context)

        # Technical specifications
        technical_suggestions = scene_elements.get("technical_suggestions", [])
        enhanced["technical_specifications"] = {
            "echo_suggestions": technical_suggestions,
            "professional_requirements": DEFAULT_PROFESSIONAL_REQUIREMENTS.copy()
        }

        # Production notes
        enhanced["production_notes"] = format_production_notes(scene_elements)

        return enhanced

    async def _fallback_scene_creation(
        self,
        prompt: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fallback scene creation when Echo Brain is unavailable"""

        return {
            "success": False,
            "collaboration_type": "fallback_generation",
            "scene_description": {
                "professional_visual_description": "Standard professional scene composition with balanced framing",
                "cinematography_notes": "Medium shot with static camera positioning",
                "atmosphere_description": "Neutral atmospheric conditions",
                "timing_notes": "Standard pacing appropriate for scene context",
                "technical_specifications": DEFAULT_PROFESSIONAL_REQUIREMENTS.copy(),
                "production_notes": "Generated using fallback scene creation due to Echo Brain unavailability"
            },
            "echo_insights": {
                "original_response": "Echo Brain unavailable",
                "error": "Could not connect to Echo Brain service",
                "fallback_used": True
            },
            "professional_enhancements": ["Fallback professional scene structure applied"]
        }

    async def log_scene_creation(self, scene_id: int, scene_description: Dict[str, Any]) -> bool:
        """Log scene creation to Echo Brain for learning"""
        try:
            session = await self._get_session()

            log_data = {
                "query": "Scene description generated",
                "conversation_id": self.conversation_id,
                "context": {
                    "agent": "scene_description_generator",
                    "task": "scene_creation_logging",
                    "scene_id": scene_id,
                    "scene_data": scene_description,
                    "timestamp": datetime.utcnow().isoformat()
                }
            }

            async with session.post(
                f"{self.base_url}/api/echo/query",
                json=log_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                return response.status == 200

        except Exception as e:
            logger.error(f"Scene creation logging failed: {e}")
            return False

    async def get_scene_optimization_suggestions(
        self,
        scene_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get optimization suggestions from Echo Brain"""
        try:
            session = await self._get_session()

            optimization_request = {
                "query": "Provide scene optimization suggestions for professional anime production",
                "conversation_id": self.conversation_id,
                "context": {
                    "agent": "scene_description_generator",
                    "task": "scene_optimization",
                    "scene_data": scene_data,
                    "optimization_focus": [
                        "visual_composition",
                        "narrative_impact",
                        "production_efficiency",
                        "audience_engagement"
                    ]
                }
            }

            async with session.post(
                f"{self.base_url}/api/echo/query",
                json=optimization_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return await self._process_optimization_response(result)
                else:
                    return {"success": False, "error": "Optimization request failed"}

        except Exception as e:
            logger.error(f"Scene optimization request failed: {e}")
            return {"success": False, "error": str(e)}

    async def _process_optimization_response(self, echo_response: Dict[str, Any]) -> Dict[str, Any]:
        """Process Echo Brain optimization suggestions"""

        response_text = echo_response.get("response", "")
        optimization_suggestions = categorize_optimization_sentences(response_text)

        return {
            "success": True,
            "optimization_suggestions": optimization_suggestions,
            "original_response": response_text,
            "categories_found": len([cat for cat in optimization_suggestions.values() if cat])
        }

    async def request_creative_expansion(
        self,
        base_scene: Dict[str, Any],
        expansion_type: str = "detailed_enhancement"
    ) -> Dict[str, Any]:
        """Request creative expansion of a scene from Echo Brain"""
        try:
            session = await self._get_session()

            expansion_request = {
                "query": f"Provide creative {expansion_type} for this scene description",
                "conversation_id": self.conversation_id,
                "context": {
                    "agent": "scene_description_generator",
                    "task": "creative_expansion",
                    "base_scene": base_scene,
                    "expansion_type": expansion_type,
                    "creative_focus": [
                        "visual_richness",
                        "atmospheric_depth",
                        "character_nuance",
                        "cinematic_quality"
                    ]
                },
                "parameters": {
                    "creativity": 0.9,
                    "detail_level": "high",
                    "professional_focus": True
                }
            }

            async with session.post(
                f"{self.base_url}/api/echo/query",
                json=expansion_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "expanded_scene": result.get("response", ""),
                        "expansion_type": expansion_type,
                        "model_used": result.get("metadata", {}).get("model", "unknown")
                    }
                else:
                    return {"success": False, "error": "Creative expansion request failed"}

        except Exception as e:
            logger.error(f"Creative expansion request failed: {e}")
            return {"success": False, "error": str(e)}

    async def validate_scene_quality(
        self,
        scene_description: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate scene quality using Echo Brain"""
        try:
            session = await self._get_session()

            validation_request = {
                "query": "Evaluate this scene description for professional anime production quality",
                "conversation_id": self.conversation_id,
                "context": {
                    "agent": "scene_description_generator",
                    "task": "quality_validation",
                    "scene_description": scene_description,
                    "validation_criteria": [
                        "visual_clarity",
                        "narrative_coherence",
                        "production_feasibility",
                        "artistic_merit"
                    ]
                }
            }

            async with session.post(
                f"{self.base_url}/api/echo/query",
                json=validation_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return await self._process_quality_validation(result)
                else:
                    return {"success": False, "error": "Quality validation failed"}

        except Exception as e:
            logger.error(f"Quality validation failed: {e}")
            return {"success": False, "error": str(e)}

    async def _process_quality_validation(self, echo_response: Dict[str, Any]) -> Dict[str, Any]:
        """Process Echo Brain quality validation response"""

        response_text = echo_response.get("response", "")
        quality_metrics = build_quality_metrics(response_text)

        return {
            "success": True,
            "quality_metrics": quality_metrics,
            "validation_response": response_text,
            "recommendations": extract_validation_recommendations(response_text)
        }
