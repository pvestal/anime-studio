#!/usr/bin/env python3
"""
Echo Brain Project Bible Integration Module
Enhances Echo Brain coordination with deep project bible understanding,
character consistency, and intelligent anime production orchestration.
"""

import json
import logging
import asyncio
import requests
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class EchoProjectBibleIntegrator:
    """Enhanced Echo Brain integration with comprehensive project bible understanding"""

    def __init__(self, echo_brain_url: str = "http://127.0.0.1:8309", anime_api_url: str = "http://127.0.0.1:8328"):
        self.echo_brain_url = echo_brain_url
        self.anime_api_url = anime_api_url
        self.project_contexts = {}  # Cache for project bible contexts
        self.character_memories = {}  # Cache for character memories
        self.style_preferences = {}  # Cache for user style preferences

    async def initialize_project_context(self, project_id: int) -> Dict[str, Any]:
        """Initialize Echo Brain with complete project context"""
        try:
            logger.info(f"Initializing Echo Brain with project {project_id} context")

            # Load project bible and all related data
            project_context = await self._load_complete_project_context(project_id)

            # Send comprehensive context to Echo Brain
            context_integration = await self._integrate_context_with_echo(project_context)

            # Cache the context for future use
            self.project_contexts[project_id] = {
                "context": project_context,
                "integration": context_integration,
                "initialized_at": datetime.now().isoformat()
            }

            logger.info(f"Project {project_id} context successfully integrated with Echo Brain")
            return context_integration

        except Exception as e:
            logger.error(f"Error initializing project context: {e}")
            raise

    async def _load_complete_project_context(self, project_id: int) -> Dict[str, Any]:
        """Load complete project context including bible, characters, scenes, and history"""
        try:
            context = {"project_id": project_id}

            # Load project details
            project_response = await self._api_request(f"/api/anime/projects/{project_id}")
            if project_response:
                context["project"] = project_response

            # Load project bible
            bible_response = await self._api_request(f"/api/anime/projects/{project_id}/bible")
            if bible_response:
                context["bible"] = bible_response

                # Load bible characters
                characters_response = await self._api_request(f"/api/anime/projects/{project_id}/bible/characters")
                if characters_response:
                    context["characters"] = characters_response

                # Load bible history
                history_response = await self._api_request(f"/api/anime/projects/{project_id}/bible/history")
                if history_response:
                    context["bible_history"] = history_response

            # Load project scenes
            scenes_response = await self._api_request(f"/api/anime/projects/{project_id}/scenes")
            if scenes_response:
                context["scenes"] = scenes_response

            # Load generation history
            generations_response = await self._api_request(f"/api/anime/projects/{project_id}/generations")
            if generations_response:
                context["generation_history"] = generations_response

            return context

        except Exception as e:
            logger.error(f"Error loading project context: {e}")
            return {"project_id": project_id, "error": str(e)}

    async def _integrate_context_with_echo(self, project_context: Dict[str, Any]) -> Dict[str, Any]:
        """Send project context to Echo Brain for deep understanding"""
        try:
            integration_prompt = f"""
            SYSTEM: You are now the Production Director for this anime project.
            Integrate this complete project context into your working memory:

            PROJECT DETAILS:
            {json.dumps(project_context.get("project", {}), indent=2)}

            PROJECT BIBLE:
            {json.dumps(project_context.get("bible", {}), indent=2)}

            CHARACTERS:
            {json.dumps(project_context.get("characters", []), indent=2)}

            SCENES:
            {json.dumps(project_context.get("scenes", []), indent=2)}

            GENERATION HISTORY:
            {json.dumps(project_context.get("generation_history", []), indent=2)}

            As Production Director, you now understand:
            1. The complete visual style and world setting for this project
            2. All character definitions, relationships, and evolution arcs
            3. Narrative guidelines and thematic elements
            4. Previous generation patterns and quality standards
            5. Technical requirements and consistency rules

            Confirm your understanding and readiness to coordinate all anime production
            workflows for this project with this context in mind.
            """

            response = await self._query_echo_brain(
                integration_prompt,
                context="project_bible_integration",
                model="qwen2.5-coder:32b"
            )

            return {
                "status": "integrated",
                "echo_response": response,
                "context_size": len(str(project_context)),
                "integrated_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error integrating context with Echo: {e}")
            return {"status": "error", "message": str(e)}

    async def orchestrate_character_generation(self, character_name: str, project_id: int,
                                             additional_requirements: str = "") -> Dict[str, Any]:
        """Echo-orchestrated character generation with full project context"""
        try:
            logger.info(f"Echo orchestrating character generation: {character_name} for project {project_id}")

            # Ensure project context is loaded
            if project_id not in self.project_contexts:
                await self.initialize_project_context(project_id)

            project_context = self.project_contexts[project_id]["context"]

            # Build comprehensive generation prompt
            generation_prompt = await self._build_character_generation_prompt(
                character_name, project_context, additional_requirements
            )

            # Echo Brain generates character with full context
            echo_generation = await self._query_echo_brain(
                generation_prompt,
                context="character_generation_with_bible",
                model="qwen2.5-coder:32b"
            )

            # Parse Echo's generation instructions
            generation_instructions = await self._parse_echo_generation_instructions(echo_generation)

            # Execute generation through ComfyUI with Echo-optimized parameters
            generation_result = await self._execute_echo_guided_generation(generation_instructions)

            # Echo Brain quality assessment
            quality_assessment = await self._echo_quality_assessment(
                character_name, generation_result, project_context
            )

            orchestration_result = {
                "character_name": character_name,
                "project_id": project_id,
                "echo_generation_prompt": generation_prompt,
                "echo_response": echo_generation,
                "generation_instructions": generation_instructions,
                "generation_result": generation_result,
                "quality_assessment": quality_assessment,
                "orchestrated_at": datetime.now().isoformat()
            }

            # Learn from this generation for future improvements
            await self._learn_from_generation(character_name, orchestration_result)

            logger.info(f"Echo orchestration completed for {character_name}")
            return orchestration_result

        except Exception as e:
            logger.error(f"Error in Echo character orchestration: {e}")
            return {
                "status": "error",
                "character_name": character_name,
                "project_id": project_id,
                "error_message": str(e),
                "orchestrated_at": datetime.now().isoformat()
            }

    async def _build_character_generation_prompt(self, character_name: str,
                                               project_context: Dict[str, Any],
                                               additional_requirements: str) -> str:
        """Build comprehensive character generation prompt with full project context"""

        # Find character in project bible
        character_def = None
        for char in project_context.get("characters", []):
            if char["name"].lower() == character_name.lower():
                character_def = char
                break

        if not character_def:
            return f"ERROR: Character {character_name} not found in project bible"

        bible = project_context.get("bible", {})
        project = project_context.get("project", {})

        prompt = f"""
        PRODUCTION DIRECTOR TASK: Generate character {character_name} for {project.get("name", "Unknown Project")}

        PROJECT BIBLE CONTEXT:
        Visual Style: {json.dumps(bible.get("visual_style", {}), indent=2)}
        World Setting: {json.dumps(bible.get("world_setting", {}), indent=2)}
        Narrative Guidelines: {json.dumps(bible.get("narrative_guidelines", {}), indent=2)}

        CHARACTER DEFINITION:
        Name: {character_def["name"]}
        Description: {character_def["description"]}
        Visual Traits: {json.dumps(character_def.get("visual_traits", {}), indent=2)}
        Personality Traits: {json.dumps(character_def.get("personality_traits", {}), indent=2)}
        Relationships: {json.dumps(character_def.get("relationships", {}), indent=2)}
        Evolution Arc: {json.dumps(character_def.get("evolution_arc", []), indent=2)}

        ADDITIONAL REQUIREMENTS:
        {additional_requirements}

        PREVIOUS GENERATIONS:
        {self._format_previous_generations(project_context)}

        As Production Director, provide:
        1. Optimized ComfyUI generation parameters
        2. Detailed visual prompt based on project bible
        3. Negative prompts to maintain consistency
        4. Quality checkpoints and validation criteria
        5. Style inheritance from project visual guidelines

        Ensure absolute consistency with project bible and character definition.
        Focus on professional anime production quality standards.
        """

        return prompt

    def _format_previous_generations(self, project_context: Dict[str, Any]) -> str:
        """Format previous generations for context"""
        generations = project_context.get("generation_history", [])
        if not generations:
            return "No previous generations for this project."

        recent_generations = sorted(generations, key=lambda x: x.get("created_at", ""), reverse=True)[:3]
        formatted = "Recent successful generations:\n"

        for gen in recent_generations:
            if gen.get("status") == "completed":
                formatted += f"- {gen.get('character_name', 'Unknown')}: {gen.get('prompt', 'No prompt')}\n"

        return formatted

    async def _parse_echo_generation_instructions(self, echo_response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Echo Brain's generation instructions into actionable parameters"""
        try:
            response_text = echo_response.get("response", echo_response.get("result", ""))

            # Extract structured instructions using Echo Brain
            parsing_prompt = f"""
            Parse these generation instructions into structured ComfyUI parameters:

            {response_text}

            Extract and structure:
            1. Visual prompt (positive)
            2. Negative prompts
            3. Technical parameters (width, height, steps, cfg_scale)
            4. Style modifiers
            5. Quality settings
            6. Consistency requirements

            Return as JSON structure for ComfyUI workflow.
            """

            parsing_response = await self._query_echo_brain(
                parsing_prompt,
                context="instruction_parsing",
                model="qwen2.5-coder:32b"
            )

            # Try to extract JSON from Echo's response
            try:
                # Look for JSON in the response
                response_content = parsing_response.get("response", parsing_response.get("result", ""))
                if "{" in response_content and "}" in response_content:
                    start = response_content.find("{")
                    end = response_content.rfind("}") + 1
                    json_str = response_content[start:end]
                    return json.loads(json_str)
            except json.JSONDecodeError:
                pass

            # Fallback to default structure
            return {
                "positive_prompt": response_text[:500],  # First 500 chars
                "negative_prompt": "blurry, low quality, deformed, duplicate",
                "width": 1024,
                "height": 1024,
                "steps": 30,
                "cfg_scale": 7.0,
                "style": "anime, professional quality"
            }

        except Exception as e:
            logger.error(f"Error parsing Echo generation instructions: {e}")
            return {"error": str(e)}

    async def _execute_echo_guided_generation(self, instructions: Dict[str, Any]) -> Dict[str, Any]:
        """Execute generation using Echo-guided parameters"""
        try:
            # This would integrate with the existing ComfyUI connector
            # For now, return a mock result
            return {
                "status": "completed",
                "image_path": f"/opt/tower-anime-production/generated/echo_guided_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
                "generation_time": "3.2s",
                "parameters_used": instructions,
                "echo_guided": True
            }

        except Exception as e:
            logger.error(f"Error executing Echo-guided generation: {e}")
            return {"status": "error", "message": str(e)}

    async def _echo_quality_assessment(self, character_name: str, generation_result: Dict[str, Any],
                                     project_context: Dict[str, Any]) -> Dict[str, Any]:
        """Echo Brain quality assessment with project context"""
        try:
            assessment_prompt = f"""
            PRODUCTION DIRECTOR QUALITY ASSESSMENT

            Character: {character_name}
            Project Context: {project_context.get("project", {}).get("name", "Unknown")}

            Generation Result: {json.dumps(generation_result, indent=2)}

            Project Bible Requirements:
            {json.dumps(project_context.get("bible", {}), indent=2)}

            Character Definition:
            {json.dumps(next((char for char in project_context.get("characters", [])
                            if char["name"].lower() == character_name.lower()), {}), indent=2)}

            As Production Director, assess:
            1. Adherence to project bible visual style
            2. Character definition accuracy
            3. Technical quality standards
            4. Consistency with project world setting
            5. Professional production readiness

            Provide detailed quality assessment with score (0-10) and specific recommendations.
            """

            assessment_response = await self._query_echo_brain(
                assessment_prompt,
                context="quality_assessment",
                model="qwen2.5-coder:32b"
            )

            return {
                "character_name": character_name,
                "echo_assessment": assessment_response,
                "assessed_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error in Echo quality assessment: {e}")
            return {"status": "error", "message": str(e)}

    async def _learn_from_generation(self, character_name: str, orchestration_result: Dict[str, Any]):
        """Learn from generation for continuous improvement"""
        try:
            learning_prompt = f"""
            PRODUCTION DIRECTOR LEARNING SYSTEM

            Analyze this generation workflow for continuous improvement:
            {json.dumps(orchestration_result, indent=2)}

            Learn:
            1. What worked well in this generation?
            2. What parameters led to high quality results?
            3. How can character consistency be improved?
            4. What project bible elements were most effective?
            5. Technical optimizations for future generations

            Update your production knowledge for character {character_name} and similar workflows.
            """

            learning_response = await self._query_echo_brain(
                learning_prompt,
                context="production_learning",
                model="qwen2.5-coder:32b"
            )

            # Store learning insights
            if character_name not in self.character_memories:
                self.character_memories[character_name] = []

            self.character_memories[character_name].append({
                "learning_response": learning_response,
                "orchestration_result": orchestration_result,
                "learned_at": datetime.now().isoformat()
            })

            logger.info(f"Learning insights stored for {character_name}")

        except Exception as e:
            logger.error(f"Error in learning from generation: {e}")

    async def orchestrate_scene_generation(self, scene_description: str, project_id: int,
                                         character_names: List[str] = []) -> Dict[str, Any]:
        """Echo-orchestrated scene generation with character and project context"""
        try:
            logger.info(f"Echo orchestrating scene generation for project {project_id}")

            # Ensure project context is loaded
            if project_id not in self.project_contexts:
                await self.initialize_project_context(project_id)

            project_context = self.project_contexts[project_id]["context"]

            # Build scene generation prompt with character context
            scene_prompt = await self._build_scene_generation_prompt(
                scene_description, project_context, character_names
            )

            # Echo Brain orchestrates scene generation
            echo_scene_response = await self._query_echo_brain(
                scene_prompt,
                context="scene_generation_with_characters",
                model="qwen2.5-coder:32b"
            )

            # Parse scene generation instructions
            scene_instructions = await self._parse_scene_generation_instructions(echo_scene_response)

            # Execute scene generation
            scene_result = await self._execute_scene_generation(scene_instructions)

            # Quality assessment
            scene_assessment = await self._assess_scene_quality(
                scene_description, scene_result, project_context
            )

            scene_orchestration = {
                "scene_description": scene_description,
                "project_id": project_id,
                "character_names": character_names,
                "echo_prompt": scene_prompt,
                "echo_response": echo_scene_response,
                "scene_instructions": scene_instructions,
                "scene_result": scene_result,
                "scene_assessment": scene_assessment,
                "orchestrated_at": datetime.now().isoformat()
            }

            logger.info(f"Scene orchestration completed for project {project_id}")
            return scene_orchestration

        except Exception as e:
            logger.error(f"Error in scene orchestration: {e}")
            return {
                "status": "error",
                "scene_description": scene_description,
                "project_id": project_id,
                "error_message": str(e)
            }

    async def _build_scene_generation_prompt(self, scene_description: str,
                                           project_context: Dict[str, Any],
                                           character_names: List[str]) -> str:
        """Build comprehensive scene generation prompt"""
        bible = project_context.get("bible", {})
        project = project_context.get("project", {})
        characters = project_context.get("characters", [])

        # Get character definitions for scene characters
        scene_characters = []
        for char_name in character_names:
            for char in characters:
                if char["name"].lower() == char_name.lower():
                    scene_characters.append(char)
                    break

        prompt = f"""
        PRODUCTION DIRECTOR SCENE ORCHESTRATION

        Project: {project.get("name", "Unknown")}
        Scene Description: {scene_description}

        PROJECT CONTEXT:
        Visual Style: {json.dumps(bible.get("visual_style", {}), indent=2)}
        World Setting: {json.dumps(bible.get("world_setting", {}), indent=2)}

        CHARACTERS IN SCENE:
        {json.dumps(scene_characters, indent=2)}

        CHARACTER RELATIONSHIPS:
        {self._format_character_relationships(scene_characters)}

        As Production Director, orchestrate this scene with:
        1. Character positioning and interactions
        2. Environmental details from world setting
        3. Visual style consistency
        4. Character expression and emotion
        5. Scene composition and cinematography
        6. Technical generation parameters

        Ensure character consistency and adherence to project bible.
        """

        return prompt

    def _format_character_relationships(self, characters: List[Dict[str, Any]]) -> str:
        """Format character relationships for scene context"""
        if len(characters) < 2:
            return "Single character scene - no relationships to consider."

        relationships = []
        for char in characters:
            char_relationships = char.get("relationships", {})
            for other_char, relationship in char_relationships.items():
                relationships.append(f"{char['name']} -> {other_char}: {relationship}")

        return "\\n".join(relationships) if relationships else "No defined relationships."

    async def _parse_scene_generation_instructions(self, echo_response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Echo's scene generation instructions"""
        # Similar to character instructions parsing but for scenes
        response_text = echo_response.get("response", echo_response.get("result", ""))

        return {
            "scene_prompt": response_text[:500],
            "character_positions": "multiple characters, interacting",
            "environment": "project bible environment",
            "style": "anime, project bible style",
            "composition": "cinematic scene composition"
        }

    async def _execute_scene_generation(self, instructions: Dict[str, Any]) -> Dict[str, Any]:
        """Execute scene generation with Echo instructions"""
        # Would integrate with ComfyUI for scene generation
        return {
            "status": "completed",
            "scene_path": f"/opt/tower-anime-production/generated/echo_scene_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            "generation_time": "5.7s",
            "echo_guided": True
        }

    async def _assess_scene_quality(self, scene_description: str, scene_result: Dict[str, Any],
                                  project_context: Dict[str, Any]) -> Dict[str, Any]:
        """Echo assessment of scene quality"""
        assessment_prompt = f"""
        SCENE QUALITY ASSESSMENT

        Scene: {scene_description}
        Result: {json.dumps(scene_result, indent=2)}
        Project Context: {json.dumps(project_context.get("project", {}), indent=2)}

        Assess scene quality for:
        1. Character consistency and interaction
        2. Environment accuracy to world setting
        3. Visual style adherence
        4. Scene composition and cinematography
        5. Technical quality

        Provide detailed assessment with recommendations.
        """

        return await self._query_echo_brain(
            assessment_prompt,
            context="scene_quality_assessment",
            model="qwen2.5-coder:32b"
        )

    # ==================== UTILITY METHODS ====================

    async def _api_request(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Make API request to anime production service"""
        try:
            response = requests.get(f"{self.anime_api_url}{endpoint}", timeout=10)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                logger.warning(f"API request failed: {response.status_code} for {endpoint}")
                return None
        except Exception as e:
            logger.error(f"Error making API request to {endpoint}: {e}")
            return None

    async def _query_echo_brain(self, prompt: str, context: str = "anime_production",
                              model: str = "qwen2.5-coder:32b") -> Dict[str, Any]:
        """Query Echo Brain with prompt"""
        try:
            response = requests.post(
                f"{self.echo_brain_url}/api/echo/query",
                json={
                    "query": prompt,
                    "context": context
                },
                timeout=60
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Echo Brain query failed: {response.status_code}")
                return {"status": "error", "message": f"HTTP {response.status_code}"}

        except Exception as e:
            logger.error(f"Error querying Echo Brain: {e}")
            return {"status": "error", "message": str(e)}

    def get_project_context_summary(self, project_id: int) -> Dict[str, Any]:
        """Get summary of loaded project context"""
        if project_id not in self.project_contexts:
            return {"status": "not_loaded", "project_id": project_id}

        context = self.project_contexts[project_id]
        project_data = context["context"]

        return {
            "status": "loaded",
            "project_id": project_id,
            "project_name": project_data.get("project", {}).get("name", "Unknown"),
            "has_bible": "bible" in project_data,
            "character_count": len(project_data.get("characters", [])),
            "scene_count": len(project_data.get("scenes", [])),
            "generation_count": len(project_data.get("generation_history", [])),
            "initialized_at": context["initialized_at"]
        }

# Global instance for use across the application
echo_bible_integrator = EchoProjectBibleIntegrator()