#!/usr/bin/env python3
"""
Echo Brain Service Integration for Anime Production
Provides AI-powered content generation and suggestions
"""

import json
import requests
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class EchoBrainConfig:
    """Configuration for Echo Brain service."""
    base_url: str = "http://localhost:8309"
    model: str = "llama3.1:8b"  # Better quality model
    temperature: float = 0.7
    max_tokens: int = 500  # Reduce tokens for faster response
    timeout: int = 60  # Allow more time for quality responses
    enabled: bool = True

class EchoBrainService:
    """Service class for interacting with Echo Brain AI."""

    def __init__(self):
        self.config = EchoBrainConfig()
        self._session = requests.Session()

    def check_status(self) -> Dict[str, Any]:
        """Check if Echo Brain service is available."""
        if not self.config.enabled:
            return {
                "status": "disabled",
                "message": "Echo Brain integration is disabled"
            }

        try:
            response = self._session.get(
                f"{self.config.base_url}/api/echo/health",
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "online",
                    "message": "Echo Brain is operational",
                    "models": data.get("available_models", []),
                    "current_model": self.config.model
                }
        except requests.RequestException as e:
            logger.warning(f"Echo Brain health check failed: {e}")

        return {
            "status": "offline",
            "message": "Echo Brain service is not available",
            "fallback": "Using default values"
        }

    def generate_suggestion(self, prompt: str, context: Optional[Dict] = None) -> str:
        """Generate a suggestion using Echo Brain."""
        if not self.config.enabled:
            return "Echo Brain is disabled. Using default suggestion."

        try:
            payload = {
                "query": prompt,
                "model": self.config.model,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "conversation_id": f"anime_production_{context.get('project_id', 'default')}" if context else "anime_production_default"
            }

            response = self._session.post(
                f"{self.config.base_url}/api/echo/query",
                json=payload,
                timeout=self.config.timeout
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("response", "No suggestion generated")

        except requests.RequestException as e:
            logger.error(f"Echo Brain query failed: {e}")

        return "Echo Brain unavailable. Please provide manual input."

    def suggest_scene_details(self, context: Dict[str, Any], current_prompt: str) -> Dict[str, Any]:
        """Suggest enhanced scene details based on context."""
        prompt = f"""
        Given the following anime project context:
        Project: {context.get('project_name', 'Unknown')}
        Genre: {context.get('genre', 'General')}
        Style: {context.get('style', 'Standard anime')}
        Characters: {json.dumps(context.get('characters', []))}

        Current scene prompt: {current_prompt}

        Please suggest improvements and additional details for this scene. Include:
        1. Enhanced visual descriptions (lighting, atmosphere, camera angles)
        2. Character emotions and body language
        3. Background details and environment
        4. Sound/music suggestions
        5. Mood and tone adjustments

        Format the response as JSON with keys: visual_details, character_expressions, environment, audio_suggestions, mood
        """

        response = self.generate_suggestion(prompt, context)

        # Try to parse as JSON, fallback to structured dict
        try:
            if "{" in response and "}" in response:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except:
            pass

        # Fallback structure
        return {
            "visual_details": "Standard anime scene with appropriate lighting",
            "character_expressions": "Characters display emotions fitting the scene",
            "environment": "Background matches the setting description",
            "audio_suggestions": "Ambient sounds appropriate to location",
            "mood": "Atmosphere matches narrative tone",
            "raw_suggestion": response[:500] if response else "No suggestion available"
        }

    def generate_dialogue(self, character: Dict[str, Any], scene_context: str, emotion: str = "neutral") -> Dict[str, Any]:
        """Generate character-appropriate dialogue."""
        prompt = f"""
        Character: {character.get('name', 'Unknown')}
        Personality: {character.get('personality', 'Not specified')}
        Background: {character.get('background', 'Not specified')}
        Traits: {character.get('traits', {})}

        Scene Context: {scene_context}

        Emotion for this dialogue: {emotion}

        Generate dialogue where this character speaks. Include:
        1. The dialogue text
        2. Brief description of delivery (e.g., "sarcastically", "whispering")
        3. Notes on what makes this dialogue fit the character

        Format as JSON with keys: dialogue, delivery, character_notes
        """

        response = self.generate_suggestion(prompt)

        try:
            if "{" in response and "}" in response:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except:
            pass

        return {
            "dialogue": f"{character.get('name', 'Character')} speaks...",
            "delivery": "in character-appropriate manner",
            "character_notes": "Dialogue should reflect character personality",
            "raw_response": response[:500]
        }

    def continue_episode(self, episode_context: Dict, direction: str = "continue") -> Dict[str, Any]:
        """Suggest continuation for an episode."""
        prompt = f"""
        Episode: {episode_context.get('title', 'Unknown Episode')}
        Current Story: {episode_context.get('summary', 'No summary')}

        Previous Scenes:
        {json.dumps(episode_context.get('scenes', []), indent=2)}

        Direction for continuation: {direction}

        Suggest 3 possible next scenes. For each scene include:
        - scene_number (continue from current)
        - title
        - setting
        - characters involved
        - brief prompt
        - how it advances the story

        Format as JSON with key "scene_suggestions" containing an array of scene objects.
        """

        response = self.generate_suggestion(prompt)

        try:
            if "{" in response and "}" in response:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except:
            pass

        return {
            "scene_suggestions": [
                {
                    "scene_number": len(episode_context.get('scenes', [])) + 1,
                    "title": "Next Scene",
                    "setting": "Appropriate location",
                    "characters": ["Main characters"],
                    "prompt": "Continue the story naturally",
                    "story_advancement": "Moves plot forward"
                }
            ]
        }

    def analyze_storyline(self, episodes: List[Dict], focus: str = "consistency") -> Dict[str, Any]:
        """Analyze storyline for consistency and improvements."""
        prompt = f"""
        Analyze the following episode storyline for {focus}:

        Episodes:
        {json.dumps(episodes, indent=2)}

        Please analyze:
        1. Character arc consistency
        2. Plot hole detection
        3. Pacing issues
        4. Theme coherence
        5. Suggested improvements

        Format response as JSON with keys:
        - character_analysis
        - plot_issues
        - pacing_notes
        - theme_coherence
        - improvements (array of suggestions)
        """

        response = self.generate_suggestion(prompt)

        try:
            if "{" in response and "}" in response:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except:
            pass

        return {
            "character_analysis": "Characters show consistent development",
            "plot_issues": [],
            "pacing_notes": "Pacing appears appropriate",
            "theme_coherence": "Themes are maintained throughout",
            "improvements": ["Consider adding more character moments"],
            "raw_response": response[:500]
        }

    def brainstorm_ideas(self, project_context: Dict, theme: str, constraints: List[str] = None) -> Dict[str, Any]:
        """Brainstorm new ideas for a project."""
        prompt = f"""
        Project: {project_context.get('name', 'Unknown')}
        Current Genre: {project_context.get('genre', 'Anime')}
        Theme to explore: {theme}

        Constraints:
        {json.dumps(constraints or [], indent=2)}

        Generate 5 creative ideas that could be added to this project.
        Each idea should include:
        - title
        - brief description
        - how it fits the theme
        - potential scene/episode concept

        Format as JSON with key "ideas" containing an array of idea objects.
        """

        response = self.generate_suggestion(prompt)

        try:
            if "{" in response and "}" in response:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except:
            pass

        return {
            "ideas": [
                {
                    "title": "Creative Concept",
                    "description": "An interesting new direction for the story",
                    "theme_fit": "Aligns with the requested theme",
                    "scene_concept": "Could be developed into a compelling scene"
                }
            ],
            "raw_response": response[:500]
        }

    def batch_suggest_scenes(self, scenes: List[Dict], focus: str = "consistency") -> Dict[str, Any]:
        """Batch process multiple scenes for suggestions."""
        suggestions = {}

        for scene in scenes[:5]:  # Limit to 5 scenes to avoid timeout
            scene_id = scene.get('id')
            prompt = f"""
            Scene: {scene.get('prompt', '')}
            Focus: {focus}

            Suggest brief improvements for:
            1. Visual enhancement
            2. Character consistency
            3. Narrative flow

            Keep response under 100 words. Format as JSON with keys:
            - visual_notes
            - character_notes
            - narrative_notes
            """

            response = self.generate_suggestion(prompt)

            try:
                if "{" in response and "}" in response:
                    json_start = response.find("{")
                    json_end = response.rfind("}") + 1
                    json_str = response[json_start:json_end]
                    suggestions[scene_id] = json.loads(json_str)
                else:
                    suggestions[scene_id] = {
                        "visual_notes": "Consider enhancing visual details",
                        "character_notes": "Ensure character consistency",
                        "narrative_notes": "Maintain narrative flow"
                    }
            except:
                suggestions[scene_id] = {
                    "visual_notes": "Standard visual approach",
                    "character_notes": "Character as defined",
                    "narrative_notes": "Continue narrative"
                }

        return {
            "batch_count": len(suggestions),
            "focus": focus,
            "suggestions": suggestions
        }

# Global instance
echo_brain_service = EchoBrainService()