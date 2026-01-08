"""
Echo Brain Creative Assistant - The AI-powered creative partner for anime production
Provides brainstorming, style suggestions, and semantic search capabilities
"""

import asyncio
import json
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime
import random  # Use random instead of numpy for now
from sqlalchemy.orm import Session
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

class EchoBrainAssistant:
    """
    Creative AI assistant that integrates with Ollama for:
    - Story generation and brainstorming
    - Visual style analysis and suggestions
    - Semantic search across projects
    - Character consistency management
    """

    def __init__(self, db_session: Session = None):
        self.ollama_url = "http://localhost:11434"
        self.creative_model = "llama3.2"          # For story ideas
        self.style_model = "mistral"              # For visual style analysis
        self.embedding_model = "nomic-embed-text" # For semantic search
        self.db = db_session

        # Verify Ollama connection
        self._verify_ollama_connection()

    def _verify_ollama_connection(self):
        """Check if Ollama is available and models are installed"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags")
            if response.status_code != 200:
                logger.warning("Ollama not available, using fallback mode")
                self.ollama_available = False
            else:
                models = response.json().get("models", [])
                self.available_models = [m["name"] for m in models]
                self.ollama_available = True
                logger.info(f"Ollama connected with models: {self.available_models}")
        except Exception as e:
            logger.warning(f"Could not connect to Ollama: {e}")
            self.ollama_available = False

    async def ollama_complete(self, prompt: str, model: str = None, json_mode: bool = False) -> Dict:
        """Complete prompt using Ollama"""
        if not self.ollama_available:
            return self._fallback_response(prompt)

        model = model or self.creative_model

        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json" if json_mode else None
                }
            )

            if response.status_code == 200:
                result = response.json()
                return {
                    "text": result.get("response", ""),
                    "model": model,
                    "success": True
                }
            else:
                return self._fallback_response(prompt)

        except Exception as e:
            logger.error(f"Ollama completion error: {e}")
            return self._fallback_response(prompt)

    def _fallback_response(self, prompt: str) -> Dict:
        """Provide structured fallback when Ollama unavailable"""
        # Extract key information from prompt to generate reasonable response
        if "storyline" in prompt.lower():
            return {
                "text": self._generate_storyline_fallback(),
                "model": "fallback",
                "success": False
            }
        elif "visual style" in prompt.lower() or "stable diffusion" in prompt.lower():
            return {
                "text": self._generate_style_fallback(),
                "model": "fallback",
                "success": False
            }
        else:
            return {
                "text": "AI assistant temporarily unavailable. Using template response.",
                "model": "fallback",
                "success": False
            }

    async def brainstorm_storyline(self, project_id: int, theme: str, context: Dict = None) -> Dict:
        """Generate storyline ideas based on project context"""

        # Build context from database if available
        context_info = ""
        if self.db and project_id:
            # Get project info using raw SQL to avoid import issues
            try:
                from sqlalchemy import text
                result = self.db.execute(
                    text("SELECT * FROM projects WHERE id = :id"),
                    {"id": project_id}
                )
                project = result.fetchone()
                if project:
                    context_info += f"Project: {project['name']}\nDescription: {project['description']}\n"
            except Exception as e:
                logger.warning(f"Could not fetch project info: {e}")

        prompt = f"""
        {context_info}
        Theme: {theme}
        Additional Context: {json.dumps(context) if context else 'None'}

        Generate 5 episode outlines for an anime series with:
        1. Episode titles that are compelling and thematic
        2. 3-scene breakdown per episode with clear progression
        3. Character arc suggestions for main and supporting characters
        4. Visual style recommendations for each episode's mood
        5. Key emotional beats and turning points

        Format as JSON with structure:
        {{
            "episodes": [
                {{
                    "title": "Episode Title",
                    "number": 1,
                    "synopsis": "Brief episode summary",
                    "scenes": [
                        {{
                            "scene_number": 1,
                            "description": "Scene description",
                            "characters": ["character1", "character2"],
                            "mood": "emotional tone",
                            "visual_style": "style keywords"
                        }}
                    ],
                    "character_arcs": {{
                        "protagonist": "development in this episode",
                        "supporting": "their role"
                    }},
                    "key_moment": "the pivotal scene"
                }}
            ],
            "overall_theme": "series theme",
            "visual_identity": "consistent style across episodes"
        }}
        """

        response = await self.ollama_complete(prompt, model=self.creative_model, json_mode=True)

        try:
            if response["success"]:
                storyline_data = json.loads(response["text"])
            else:
                storyline_data = self._generate_storyline_fallback_json()

            return {
                "success": response["success"],
                "storyline": storyline_data,
                "model_used": response["model"]
            }
        except json.JSONDecodeError:
            return {
                "success": False,
                "storyline": self._generate_storyline_fallback_json(),
                "model_used": "fallback"
            }

    async def suggest_visual_style(self, character_description: str, mood: str, art_style: str = "anime") -> Dict:
        """Convert character/mood into detailed Stable Diffusion prompt"""

        prompt = f"""
        Character Description: {character_description}
        Desired Mood: {mood}
        Art Style: {art_style}

        Create a detailed Stable Diffusion prompt for generating this character. Include:

        1. Physical appearance details
        2. Art style specifics (e.g., "anime style, cel shaded, studio trigger")
        3. Lighting description (e.g., "dramatic rim lighting, soft ambient occlusion")
        4. Color palette (e.g., "warm sunset colors, orange and purple tones")
        5. Composition (e.g., "medium shot, rule of thirds, dynamic pose")
        6. Quality tags (e.g., "masterpiece, best quality, highly detailed")
        7. Negative prompt suggestions

        Format the response as a JSON object:
        {{
            "main_prompt": "complete SD prompt",
            "negative_prompt": "things to avoid",
            "style_tags": ["tag1", "tag2"],
            "lighting": "lighting description",
            "color_palette": "color description",
            "composition": "composition notes",
            "checkpoint_recommendation": "suggested model"
        }}
        """

        response = await self.ollama_complete(prompt, model=self.style_model, json_mode=True)

        try:
            if response["success"]:
                style_data = json.loads(response["text"])
            else:
                style_data = self._generate_style_fallback_json(character_description, mood)

            return {
                "success": response["success"],
                "style": style_data,
                "model_used": response["model"]
            }
        except json.JSONDecodeError:
            return {
                "success": False,
                "style": self._generate_style_fallback_json(character_description, mood),
                "model_used": "fallback"
            }

    async def create_embedding(self, text: str) -> List[float]:
        """Create vector embedding for semantic search"""
        if not self.ollama_available:
            # Return random embedding as fallback
            return [random.gauss(0, 1) for _ in range(768)]

        try:
            response = requests.post(
                f"{self.ollama_url}/api/embeddings",
                json={
                    "model": self.embedding_model,
                    "prompt": text
                }
            )

            if response.status_code == 200:
                return response.json()["embedding"]
            else:
                # Fallback to random embedding
                return [random.gauss(0, 1) for _ in range(768)]

        except Exception as e:
            logger.error(f"Embedding creation error: {e}")
            return [random.gauss(0, 1) for _ in range(768)]

    async def analyze_character_consistency(self, character_id: int, generated_images: List[str]) -> Dict:
        """Analyze character consistency across multiple generated images"""

        prompt = f"""
        Analyze character consistency across {len(generated_images)} generated images.
        Character ID: {character_id}

        Evaluate:
        1. Visual consistency (hair color, eye color, outfit style)
        2. Art style consistency
        3. Character proportions
        4. Emotional expression range
        5. Quality variance

        Provide recommendations for improving consistency.

        Return as JSON:
        {{
            "consistency_score": 0.0 to 1.0,
            "issues": ["list of inconsistencies"],
            "recommendations": ["improvement suggestions"],
            "best_examples": ["indices of best images"],
            "worst_examples": ["indices of problematic images"]
        }}
        """

        response = await self.ollama_complete(prompt, model=self.style_model, json_mode=True)

        try:
            if response["success"]:
                analysis = json.loads(response["text"])
            else:
                analysis = {
                    "consistency_score": 0.75,
                    "issues": ["Analysis unavailable - using default assessment"],
                    "recommendations": ["Ensure consistent checkpoint", "Use same LoRA strength"],
                    "best_examples": [0, 1],
                    "worst_examples": []
                }

            return {
                "success": response["success"],
                "analysis": analysis,
                "model_used": response["model"]
            }
        except json.JSONDecodeError:
            return {
                "success": False,
                "analysis": {
                    "consistency_score": 0.75,
                    "issues": ["Analysis failed"],
                    "recommendations": ["Review generation parameters"],
                    "best_examples": [],
                    "worst_examples": []
                },
                "model_used": "fallback"
            }

    async def expand_scene_description(self, brief_scene: str, context: Dict = None) -> Dict:
        """Expand brief scene description into detailed production notes"""

        prompt = f"""
        Brief Scene: {brief_scene}
        Context: {json.dumps(context) if context else 'None'}

        Expand this into detailed production notes including:
        1. Full scene description (3-5 sentences)
        2. Character positions and actions
        3. Background environment details
        4. Lighting and time of day
        5. Camera angle suggestions
        6. Emotional tone and pacing
        7. Sound/music notes

        Format as JSON:
        {{
            "expanded_description": "full description",
            "characters": [
                {{"name": "character", "action": "what they're doing", "emotion": "feeling"}}
            ],
            "environment": "detailed background",
            "lighting": "lighting setup",
            "camera": "angle and movement",
            "mood": "emotional tone",
            "audio_notes": "sound and music"
        }}
        """

        response = await self.ollama_complete(prompt, model=self.creative_model, json_mode=True)

        try:
            if response["success"]:
                scene_data = json.loads(response["text"])
            else:
                scene_data = self._generate_scene_fallback_json(brief_scene)

            return {
                "success": response["success"],
                "scene": scene_data,
                "model_used": response["model"]
            }
        except json.JSONDecodeError:
            return {
                "success": False,
                "scene": self._generate_scene_fallback_json(brief_scene),
                "model_used": "fallback"
            }

    # Fallback generators for when Ollama is unavailable

    def _generate_storyline_fallback(self) -> str:
        """Text fallback for storyline generation"""
        return """
        Episode ideas (template):
        1. "The Beginning" - Introduction to the world and main character
        2. "First Challenge" - Character faces initial conflict
        3. "New Allies" - Meeting supporting characters
        4. "Rising Stakes" - Conflict intensifies
        5. "Resolution" - First arc conclusion
        """

    def _generate_storyline_fallback_json(self) -> Dict:
        """JSON fallback for storyline generation"""
        return {
            "episodes": [
                {
                    "title": f"Episode {i}: Template Episode",
                    "number": i,
                    "synopsis": "Episode synopsis placeholder",
                    "scenes": [
                        {
                            "scene_number": j,
                            "description": f"Scene {j} description",
                            "characters": ["protagonist", "supporting"],
                            "mood": "neutral",
                            "visual_style": "standard anime"
                        } for j in range(1, 4)
                    ],
                    "character_arcs": {
                        "protagonist": "Character development",
                        "supporting": "Supporting role"
                    },
                    "key_moment": "Pivotal scene"
                } for i in range(1, 6)
            ],
            "overall_theme": "Hero's journey",
            "visual_identity": "Modern anime style"
        }

    def _generate_style_fallback(self) -> str:
        """Text fallback for style generation"""
        return """
        masterpiece, best quality, highly detailed, anime style,
        dramatic lighting, cinematic composition, rule of thirds,
        vibrant colors, sharp focus, trending on artstation
        """

    def _generate_style_fallback_json(self, character: str, mood: str) -> Dict:
        """JSON fallback for style generation"""
        return {
            "main_prompt": f"{character}, {mood} mood, anime style, masterpiece, best quality, highly detailed",
            "negative_prompt": "worst quality, low quality, blurry, bad anatomy, bad hands",
            "style_tags": ["anime", "detailed", mood.lower()],
            "lighting": "soft ambient lighting with rim light",
            "color_palette": "vibrant anime colors",
            "composition": "medium shot, rule of thirds",
            "checkpoint_recommendation": "AOM3A1B.safetensors"
        }

    def _generate_scene_fallback_json(self, brief: str) -> Dict:
        """JSON fallback for scene expansion"""
        return {
            "expanded_description": f"Detailed version of: {brief}",
            "characters": [
                {"name": "Character 1", "action": "primary action", "emotion": "determined"}
            ],
            "environment": "Detailed environment description",
            "lighting": "Natural daylight",
            "camera": "Medium shot, slight low angle",
            "mood": "Neutral to positive",
            "audio_notes": "Ambient sounds with subtle background music"
        }

    async def search_similar_content(self, query: str, content_type: str = "all") -> Dict:
        """Search for similar projects, characters, or scenes using embeddings"""
        query_embedding = await self.create_embedding(query)

        results = {
            "projects": [],
            "characters": [],
            "scenes": [],
            "query": query,
            "embedding_used": len(query_embedding) > 0
        }

        # TODO: Implement actual database search with embeddings
        # This is a placeholder structure

        return results