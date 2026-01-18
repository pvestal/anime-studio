"""
Echo Brain Service for Anime Production
Complete implementation of the Echo Brain API endpoint design specification
"""

import json
import logging
import asyncio
import aiohttp
import os
import psycopg2
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class EchoBrainStatus(Enum):
    """Echo Brain service status"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    ERROR = "error"

@dataclass
class EchoBrainConfig:
    """Echo Brain configuration settings"""
    ollama_url: str = "http://localhost:11434"
    echo_api_url: str = "http://localhost:8309"
    model_name: str = "qwen2.5-coder:32b"
    fallback_model: str = "llama3.1:8b"
    timeout: int = 30
    max_retries: int = 3
    enabled: bool = True

@dataclass
class CreativeSuggestion:
    """Data structure for creative suggestions"""
    id: int
    type: str
    content: str
    context: Dict[str, Any]
    rating: Optional[float] = None
    used: bool = False
    created_at: datetime = None

class EchoBrainService:
    """
    Core Echo Brain service for anime production creative assistance

    Features:
    - Optional integration (fail gracefully)
    - Local-only (no external API calls)
    - Database integration for context and suggestions
    - Privacy-first approach
    """

    def __init__(self, config: Optional[EchoBrainConfig] = None):
        self.config = config or EchoBrainConfig()
        self.status = EchoBrainStatus.UNAVAILABLE
        self._init_database()

    def _init_database(self):
        """Initialize database connection and tables"""
        try:
            self.db_config = {
                'host': 'localhost',
                'database': 'anime_production',
                'user': 'patrick',
                'password': os.getenv('DATABASE_PASSWORD', '***REMOVED***')
            }
            self._create_tables()
            logger.info("Echo Brain database initialized")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")

    def _create_tables(self):
        """Create necessary tables for Echo Brain functionality"""
        create_tables_sql = """
        -- Table for storing Echo Brain suggestions
        CREATE TABLE IF NOT EXISTS echo_brain_suggestions (
            id SERIAL PRIMARY KEY,
            type VARCHAR(50) NOT NULL,
            content TEXT NOT NULL,
            context JSONB,
            project_id INTEGER REFERENCES projects(id),
            character_id INTEGER,
            scene_id INTEGER,
            rating FLOAT,
            used BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );

        -- Table for storing configuration
        CREATE TABLE IF NOT EXISTS echo_brain_config (
            key VARCHAR(100) PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW()
        );

        -- Table for tracking usage and feedback
        CREATE TABLE IF NOT EXISTS echo_brain_feedback (
            id SERIAL PRIMARY KEY,
            suggestion_id INTEGER REFERENCES echo_brain_suggestions(id),
            feedback_type VARCHAR(20) NOT NULL,
            rating INTEGER CHECK (rating >= 1 AND rating <= 5),
            comments TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );

        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_echo_suggestions_type ON echo_brain_suggestions(type);
        CREATE INDEX IF NOT EXISTS idx_echo_suggestions_project ON echo_brain_suggestions(project_id);
        CREATE INDEX IF NOT EXISTS idx_echo_suggestions_created ON echo_brain_suggestions(created_at);
        """

        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                cur.execute(create_tables_sql)
            conn.commit()
            conn.close()
            logger.info("Echo Brain tables created/verified")
        except Exception as e:
            logger.error(f"Table creation failed: {e}")

    async def check_status(self) -> Dict[str, Any]:
        """Check Echo Brain service status and configuration"""
        status_info = {
            "status": self.status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "config": {
                "enabled": self.config.enabled,
                "ollama_url": self.config.ollama_url,
                "echo_api_url": self.config.echo_api_url,
                "model": self.config.model_name
            },
            "capabilities": {
                "scene_suggestions": False,
                "dialogue_generation": False,
                "episode_continuation": False,
                "character_development": False
            },
            "last_check": None,
            "error": None
        }

        if not self.config.enabled:
            status_info["status"] = EchoBrainStatus.UNAVAILABLE.value
            status_info["error"] = "Echo Brain disabled in configuration"
            return status_info

        try:
            # Check Ollama availability
            ollama_available = await self._check_ollama()

            # Check Echo API availability
            echo_api_available = await self._check_echo_api()

            if ollama_available or echo_api_available:
                self.status = EchoBrainStatus.AVAILABLE
                status_info["status"] = EchoBrainStatus.AVAILABLE.value
                status_info["capabilities"] = {
                    "scene_suggestions": True,
                    "dialogue_generation": True,
                    "episode_continuation": True,
                    "character_development": True
                }
            else:
                self.status = EchoBrainStatus.UNAVAILABLE
                status_info["error"] = "No AI services available"

        except Exception as e:
            self.status = EchoBrainStatus.ERROR
            status_info["status"] = EchoBrainStatus.ERROR.value
            status_info["error"] = str(e)

        status_info["last_check"] = datetime.utcnow().isoformat()
        return status_info

    async def _check_ollama(self) -> bool:
        """Check if Ollama is running and model is available"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                # Check if Ollama is running
                async with session.get(f"{self.config.ollama_url}/api/version") as response:
                    if response.status != 200:
                        return False

                # Check if our preferred model is available
                async with session.get(f"{self.config.ollama_url}/api/tags") as response:
                    if response.status == 200:
                        data = await response.json()
                        models = [model['name'] for model in data.get('models', [])]
                        return (self.config.model_name in models or
                                self.config.fallback_model in models)
            return False
        except Exception as e:
            logger.debug(f"Ollama check failed: {e}")
            return False

    async def _check_echo_api(self) -> bool:
        """Check if Echo API is available"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.config.echo_api_url}/api/echo/health") as response:
                    return response.status == 200
        except Exception as e:
            logger.debug(f"Echo API check failed: {e}")
            return False

    async def get_project_context(self, project_id: int) -> Dict[str, Any]:
        """Build comprehensive project context from database"""
        context = {
            "project_id": project_id,
            "project_info": {},
            "characters": [],
            "scenes": [],
            "recent_generations": [],
            "themes": [],
            "style_preferences": {},
            "context_summary": ""
        }

        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                # Get project information
                cur.execute("""
                    SELECT name, description, status, metadata, created_at
                    FROM projects WHERE id = %s
                """, (project_id,))

                project = cur.fetchone()
                if project:
                    context["project_info"] = {
                        "name": project[0],
                        "description": project[1],
                        "status": project[2],
                        "metadata": project[3] or {},
                        "created_at": project[4].isoformat() if project[4] else None
                    }

                # Get characters
                cur.execute("""
                    SELECT id, name, description
                    FROM characters WHERE project_id = %s
                """, (project_id,))

                for char in cur.fetchall():
                    context["characters"].append({
                        "id": char[0],
                        "name": char[1],
                        "description": char[2]
                    })

                # Get scenes
                cur.execute("""
                    SELECT id, title, description, visual_description, scene_number, status
                    FROM scenes WHERE project_id = %s
                    ORDER BY scene_number
                """, (project_id,))

                for scene in cur.fetchall():
                    context["scenes"].append({
                        "id": str(scene[0]),
                        "title": scene[1],
                        "description": scene[2],
                        "visual_description": scene[3],
                        "scene_number": scene[4],
                        "status": scene[5]
                    })

                # Get recent generations
                cur.execute("""
                    SELECT job_type, prompt, status, created_at, quality_score
                    FROM production_jobs
                    WHERE project_id = %s
                    ORDER BY created_at DESC LIMIT 10
                """, (project_id,))

                for job in cur.fetchall():
                    context["recent_generations"].append({
                        "type": job[0],
                        "prompt": job[1],
                        "status": job[2],
                        "created_at": job[3].isoformat() if job[3] else None,
                        "quality_score": float(job[4]) if job[4] else None
                    })

            conn.close()

            # Generate context summary
            context["context_summary"] = self._generate_context_summary(context)

        except Exception as e:
            logger.error(f"Failed to build project context: {e}")
            context["error"] = str(e)

        return context

    def _generate_context_summary(self, context: Dict[str, Any]) -> str:
        """Generate a summary of the project context"""
        project_name = context["project_info"].get("name", "Unknown Project")
        char_count = len(context["characters"])
        scene_count = len(context["scenes"])
        gen_count = len(context["recent_generations"])

        summary = f"Project '{project_name}' with {char_count} characters, {scene_count} scenes, and {gen_count} recent generations."

        if context["characters"]:
            char_names = [c["name"] for c in context["characters"][:3]]
            summary += f" Main characters: {', '.join(char_names)}"

        return summary

    async def suggest_next_scene(self, project_id: int, current_scene: Optional[Dict] = None) -> Dict[str, Any]:
        """Suggest ideas for the next scene in the project"""
        result = {
            "suggestions": [],
            "context_used": {},
            "ai_available": self.status == EchoBrainStatus.AVAILABLE,
            "fallback_used": False
        }

        # Get project context
        context = await self.get_project_context(project_id)
        result["context_used"] = context

        if self.status == EchoBrainStatus.AVAILABLE:
            try:
                # Try AI-powered suggestions
                ai_suggestions = await self._generate_ai_scene_suggestions(context, current_scene)
                result["suggestions"] = ai_suggestions
            except Exception as e:
                logger.warning(f"AI scene suggestion failed: {e}")
                result["fallback_used"] = True
                result["ai_error"] = str(e)

        # Use fallback suggestions if AI unavailable or failed
        if not result["suggestions"]:
            result["suggestions"] = self._fallback_scene_suggestions(context)
            result["fallback_used"] = True

        # Store suggestions in database
        for suggestion in result["suggestions"]:
            await self._store_suggestion("scene_suggestion", suggestion, context, project_id)

        return result

    async def _generate_ai_scene_suggestions(self, context: Dict, current_scene: Optional[Dict] = None) -> List[Dict]:
        """Generate scene suggestions using AI"""
        prompt = self._build_scene_prompt(context, current_scene)

        # Try Echo API first, then fallback to direct Ollama
        ai_response = None

        try:
            ai_response = await self._query_echo_api(prompt)
        except Exception as e:
            logger.debug(f"Echo API failed, trying Ollama: {e}")
            try:
                ai_response = await self._query_ollama(prompt)
            except Exception as e:
                logger.debug(f"Ollama also failed: {e}")
                raise e

        return self._parse_scene_suggestions(ai_response)

    def _build_scene_prompt(self, context: Dict, current_scene: Optional[Dict] = None) -> str:
        """Build prompt for AI scene suggestion"""
        project_name = context["project_info"].get("name", "project")
        characters = ", ".join([c["name"] for c in context["characters"]])

        prompt = f"""Based on this anime project context:

Project: {project_name}
Description: {context["project_info"].get("description", "")}
Characters: {characters}
Existing scenes: {len(context["scenes"])}

"""

        if current_scene:
            prompt += f"Current scene: {current_scene.get('description', '')}\n\n"

        prompt += """Suggest 3-5 compelling next scenes for this anime. For each scene, provide:
1. Title (brief, intriguing)
2. Description (2-3 sentences)
3. Visual focus (what should be emphasized visually)
4. Emotional tone
5. Character involvement

Format as JSON with 'suggestions' array."""

        return prompt

    async def _query_echo_api(self, prompt: str) -> str:
        """Query the Echo Brain API"""
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.config.timeout)) as session:
            payload = {
                "query": prompt,
                "conversation_id": f"anime_production_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            }

            async with session.post(f"{self.config.echo_api_url}/api/echo/query", json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("response", "")
                else:
                    raise Exception(f"Echo API error: {response.status}")

    async def _query_ollama(self, prompt: str) -> str:
        """Query Ollama directly"""
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.config.timeout)) as session:
            payload = {
                "model": self.config.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9
                }
            }

            async with session.post(f"{self.config.ollama_url}/api/generate", json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("response", "")
                else:
                    raise Exception(f"Ollama error: {response.status}")

    def _parse_scene_suggestions(self, ai_response: str) -> List[Dict]:
        """Parse AI response into structured suggestions"""
        suggestions = []

        try:
            # Try to parse as JSON first
            parsed = json.loads(ai_response)
            if "suggestions" in parsed:
                suggestions = parsed["suggestions"]
            elif isinstance(parsed, list):
                suggestions = parsed
        except json.JSONDecodeError:
            # Fallback: parse text response
            suggestions = self._parse_text_suggestions(ai_response)

        # Ensure proper structure
        for i, suggestion in enumerate(suggestions):
            if isinstance(suggestion, str):
                suggestions[i] = {
                    "title": f"Scene {i+1}",
                    "description": suggestion,
                    "visual_focus": "Character interaction",
                    "emotional_tone": "neutral",
                    "characters": []
                }
            elif not all(key in suggestion for key in ["title", "description"]):
                # Fill missing fields
                suggestion.setdefault("title", f"Scene {i+1}")
                suggestion.setdefault("description", "Scene description")
                suggestion.setdefault("visual_focus", "")
                suggestion.setdefault("emotional_tone", "neutral")
                suggestion.setdefault("characters", [])

        return suggestions[:5]  # Limit to 5 suggestions

    def _parse_text_suggestions(self, text: str) -> List[Dict]:
        """Parse unstructured text into suggestions"""
        # Simple parsing logic for text responses
        lines = text.strip().split('\n')
        suggestions = []
        current_suggestion = {}

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.lower().startswith('title:') or line.startswith('1.') or line.startswith('2.'):
                if current_suggestion:
                    suggestions.append(current_suggestion)
                current_suggestion = {"title": line.split(':', 1)[-1].strip()}
            elif line.lower().startswith('description:') and current_suggestion:
                current_suggestion["description"] = line.split(':', 1)[-1].strip()
            elif current_suggestion and "description" not in current_suggestion:
                current_suggestion["description"] = line

        if current_suggestion:
            suggestions.append(current_suggestion)

        return suggestions

    def _fallback_scene_suggestions(self, context: Dict) -> List[Dict]:
        """Generate fallback suggestions when AI is unavailable"""
        project_name = context["project_info"].get("name", "project")
        characters = context["characters"]
        scene_count = len(context["scenes"])

        fallback_suggestions = [
            {
                "title": "Character Development Scene",
                "description": f"Explore the background and motivations of one of the main characters. Show their personal struggles and growth.",
                "visual_focus": "Close-up character expressions and body language",
                "emotional_tone": "introspective",
                "characters": [c["name"] for c in characters[:2]],
                "source": "fallback_template"
            },
            {
                "title": "Conflict Introduction",
                "description": "Introduce a new challenge or obstacle that the characters must face. This could be external or internal conflict.",
                "visual_focus": "Dynamic action and tension",
                "emotional_tone": "tense",
                "characters": [c["name"] for c in characters],
                "source": "fallback_template"
            },
            {
                "title": "Quiet Moment",
                "description": "A peaceful scene that allows for character interaction and dialogue. Building relationships and revealing personality.",
                "visual_focus": "Intimate settings and natural expressions",
                "emotional_tone": "calm",
                "characters": [c["name"] for c in characters[:2]],
                "source": "fallback_template"
            }
        ]

        # Customize based on project context
        if "tokyo" in project_name.lower():
            fallback_suggestions.append({
                "title": "Urban Discovery",
                "description": "Characters explore a new area of Tokyo, discovering something unexpected about the city or each other.",
                "visual_focus": "Tokyo cityscape and urban details",
                "emotional_tone": "curious",
                "characters": [c["name"] for c in characters],
                "source": "fallback_template"
            })

        return fallback_suggestions

    async def generate_dialogue(self, character_names: List[str], context: str, tone: str = "casual") -> Dict[str, Any]:
        """Generate dialogue between characters"""
        result = {
            "dialogue": [],
            "context_used": context,
            "characters": character_names,
            "tone": tone,
            "ai_available": self.status == EchoBrainStatus.AVAILABLE,
            "fallback_used": False
        }

        if self.status == EchoBrainStatus.AVAILABLE:
            try:
                ai_dialogue = await self._generate_ai_dialogue(character_names, context, tone)
                result["dialogue"] = ai_dialogue
            except Exception as e:
                logger.warning(f"AI dialogue generation failed: {e}")
                result["fallback_used"] = True
                result["ai_error"] = str(e)

        if not result["dialogue"]:
            result["dialogue"] = self._fallback_dialogue(character_names, tone)
            result["fallback_used"] = True

        # Store dialogue suggestion
        await self._store_suggestion("dialogue", result["dialogue"], {
            "characters": character_names,
            "context": context,
            "tone": tone
        })

        return result

    async def _generate_ai_dialogue(self, character_names: List[str], context: str, tone: str) -> List[Dict]:
        """Generate dialogue using AI"""
        prompt = f"""Create a dialogue between these characters: {', '.join(character_names)}

Context: {context}
Tone: {tone}

Generate 5-8 lines of natural dialogue that:
1. Shows each character's personality
2. Advances the scene/story
3. Feels authentic to the context
4. Matches the specified tone

Format as JSON array with objects containing 'character' and 'line' fields."""

        try:
            ai_response = await self._query_echo_api(prompt)
        except:
            ai_response = await self._query_ollama(prompt)

        return self._parse_dialogue_response(ai_response, character_names)

    def _parse_dialogue_response(self, response: str, character_names: List[str]) -> List[Dict]:
        """Parse AI dialogue response"""
        try:
            parsed = json.loads(response)
            if isinstance(parsed, list):
                return parsed
            elif "dialogue" in parsed:
                return parsed["dialogue"]
        except json.JSONDecodeError:
            # Parse text format
            lines = response.strip().split('\n')
            dialogue = []

            for line in lines:
                line = line.strip()
                if ':' in line and any(name in line for name in character_names):
                    parts = line.split(':', 1)
                    character = parts[0].strip().strip('"')
                    text = parts[1].strip().strip('"')
                    dialogue.append({"character": character, "line": text})

            return dialogue

        return []

    def _fallback_dialogue(self, character_names: List[str], tone: str) -> List[Dict]:
        """Generate fallback dialogue"""
        tone_templates = {
            "casual": [
                "Hey, did you notice anything strange lately?",
                "What do you think we should do?",
                "I've been thinking about what you said earlier."
            ],
            "serious": [
                "We need to discuss what happened.",
                "This situation is more complicated than I thought.",
                "I understand the gravity of our circumstances."
            ],
            "emotional": [
                "I can't believe this is happening.",
                "You've always been there for me.",
                "This means everything to me."
            ]
        }

        templates = tone_templates.get(tone, tone_templates["casual"])
        dialogue = []

        for i, template in enumerate(templates[:min(len(character_names), 3)]):
            dialogue.append({
                "character": character_names[i % len(character_names)],
                "line": template,
                "source": "fallback_template"
            })

        return dialogue

    async def continue_episode(self, project_id: int, current_episode: int) -> Dict[str, Any]:
        """Suggest how to continue or develop the current episode"""
        result = {
            "continuation_suggestions": [],
            "project_context": {},
            "current_episode": current_episode,
            "ai_available": self.status == EchoBrainStatus.AVAILABLE,
            "fallback_used": False
        }

        # Get project context
        context = await self.get_project_context(project_id)
        result["project_context"] = context

        if self.status == EchoBrainStatus.AVAILABLE:
            try:
                ai_continuation = await self._generate_ai_continuation(context, current_episode)
                result["continuation_suggestions"] = ai_continuation
            except Exception as e:
                logger.warning(f"AI episode continuation failed: {e}")
                result["fallback_used"] = True
                result["ai_error"] = str(e)

        if not result["continuation_suggestions"]:
            result["continuation_suggestions"] = self._fallback_continuation(context, current_episode)
            result["fallback_used"] = True

        # Store continuation suggestions
        for suggestion in result["continuation_suggestions"]:
            await self._store_suggestion("episode_continuation", suggestion, context, project_id)

        return result

    async def _generate_ai_continuation(self, context: Dict, current_episode: int) -> List[Dict]:
        """Generate episode continuation using AI"""
        project_name = context["project_info"].get("name", "project")
        scenes = context["scenes"]
        characters = context["characters"]

        prompt = f"""Based on this anime project:

Project: {project_name}
Current Episode: {current_episode}
Existing Scenes: {len(scenes)}
Characters: {', '.join([c['name'] for c in characters])}

Recent story developments:
"""

        # Add recent scene summaries
        for scene in scenes[-3:]:
            prompt += f"- {scene.get('title', '')}: {scene.get('description', '')}\n"

        prompt += f"""

Suggest 3-4 ways to continue episode {current_episode}:
1. Next dramatic beat or plot point
2. Character development opportunities
3. Visual storytelling ideas
4. Pacing and structure suggestions

Format as JSON with 'suggestions' array containing objects with 'type', 'title', 'description' fields."""

        try:
            ai_response = await self._query_echo_api(prompt)
        except:
            ai_response = await self._query_ollama(prompt)

        return self._parse_continuation_response(ai_response)

    def _parse_continuation_response(self, response: str) -> List[Dict]:
        """Parse AI continuation response"""
        try:
            parsed = json.loads(response)
            if "suggestions" in parsed:
                return parsed["suggestions"]
            elif isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            # Parse text response
            suggestions = []
            lines = response.strip().split('\n')
            current_suggestion = {}

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if any(line.lower().startswith(prefix) for prefix in ['1.', '2.', '3.', '4.', '-', '*']):
                    if current_suggestion:
                        suggestions.append(current_suggestion)
                    current_suggestion = {
                        "type": "continuation",
                        "title": line.split('.', 1)[-1].strip()[:50],
                        "description": line
                    }
                elif current_suggestion:
                    current_suggestion["description"] += " " + line

            if current_suggestion:
                suggestions.append(current_suggestion)

            return suggestions

        return []

    def _fallback_continuation(self, context: Dict, current_episode: int) -> List[Dict]:
        """Generate fallback continuation suggestions"""
        scenes_count = len(context["scenes"])
        characters = context["characters"]

        return [
            {
                "type": "plot_development",
                "title": "Advance Main Plot",
                "description": f"Move the central conflict forward with a new revelation or challenge for episode {current_episode}.",
                "source": "fallback_template"
            },
            {
                "type": "character_focus",
                "title": "Character Spotlight",
                "description": f"Give one of your {len(characters)} characters a moment to shine and develop their personality.",
                "source": "fallback_template"
            },
            {
                "type": "world_building",
                "title": "Expand the World",
                "description": "Introduce a new location, character, or aspect of your anime's world.",
                "source": "fallback_template"
            },
            {
                "type": "emotional_beat",
                "title": "Emotional Moment",
                "description": "Create a quieter scene that develops relationships between characters.",
                "source": "fallback_template"
            }
        ]

    async def _store_suggestion(self, suggestion_type: str, content: Any, context: Dict, project_id: int = None):
        """Store suggestion in database for learning and reference"""
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO echo_brain_suggestions
                    (type, content, context, project_id, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    RETURNING id
                """, (
                    suggestion_type,
                    json.dumps(content),
                    json.dumps(context),
                    project_id
                ))
                suggestion_id = cur.fetchone()[0]
                logger.debug(f"Stored suggestion {suggestion_id} of type {suggestion_type}")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to store suggestion: {e}")

    async def submit_feedback(self, suggestion_id: int, rating: int, comments: str = None) -> Dict[str, Any]:
        """Submit feedback for a suggestion"""
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                # Store feedback
                cur.execute("""
                    INSERT INTO echo_brain_feedback
                    (suggestion_id, feedback_type, rating, comments, created_at)
                    VALUES (%s, 'user_rating', %s, %s, NOW())
                """, (suggestion_id, rating, comments))

                # Update suggestion rating (average)
                cur.execute("""
                    UPDATE echo_brain_suggestions
                    SET rating = (
                        SELECT AVG(rating)
                        FROM echo_brain_feedback
                        WHERE suggestion_id = %s
                    ),
                    updated_at = NOW()
                    WHERE id = %s
                """, (suggestion_id, suggestion_id))

            conn.commit()
            conn.close()

            return {
                "status": "success",
                "suggestion_id": suggestion_id,
                "rating": rating,
                "message": "Feedback submitted successfully"
            }
        except Exception as e:
            logger.error(f"Failed to submit feedback: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def get_suggestions_history(self, project_id: int = None, suggestion_type: str = None, limit: int = 50) -> List[Dict]:
        """Get history of suggestions with optional filtering"""
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                query = """
                    SELECT id, type, content, rating, used, created_at
                    FROM echo_brain_suggestions
                    WHERE 1=1
                """
                params = []

                if project_id:
                    query += " AND project_id = %s"
                    params.append(project_id)

                if suggestion_type:
                    query += " AND type = %s"
                    params.append(suggestion_type)

                query += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)

                cur.execute(query, params)
                suggestions = []

                for row in cur.fetchall():
                    suggestions.append({
                        "id": row[0],
                        "type": row[1],
                        "content": json.loads(row[2]) if row[2] else {},
                        "rating": float(row[3]) if row[3] else None,
                        "used": row[4],
                        "created_at": row[5].isoformat() if row[5] else None
                    })

            conn.close()
            return suggestions
        except Exception as e:
            logger.error(f"Failed to get suggestions history: {e}")
            return []

    def update_config(self, config_updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update Echo Brain configuration"""
        try:
            for key, value in config_updates.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)

                    # Store in database
                    conn = psycopg2.connect(**self.db_config)
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO echo_brain_config (key, value, updated_at)
                            VALUES (%s, %s, NOW())
                            ON CONFLICT (key) DO UPDATE SET
                            value = EXCLUDED.value,
                            updated_at = EXCLUDED.updated_at
                        """, (key, str(value)))
                    conn.commit()
                    conn.close()

            return {
                "status": "success",
                "updated_config": {
                    "enabled": self.config.enabled,
                    "ollama_url": self.config.ollama_url,
                    "echo_api_url": self.config.echo_api_url,
                    "model_name": self.config.model_name,
                    "timeout": self.config.timeout
                }
            }
        except Exception as e:
            logger.error(f"Failed to update config: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

# Singleton instance
_echo_brain_service = None

def get_echo_brain_service() -> EchoBrainService:
    """Get singleton Echo Brain service instance"""
    global _echo_brain_service
    if _echo_brain_service is None:
        _echo_brain_service = EchoBrainService()
    return _echo_brain_service