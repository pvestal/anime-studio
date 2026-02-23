"""
Writing Agent
Generates dialogue, narration, and captions for scenes.
All context comes from the story bible DB — nothing is hardcoded.
"""

import json
import logging
import re
from typing import Optional
import httpx

import sys
import os
sys.path.insert(0, '/opt/anime-studio')

from services.story_engine.story_manager import StoryManager
from services.story_engine.vector_store import StoryVectorStore

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434"
# gemma2:9b is good for creative writing based on availability
WRITING_MODEL = "gemma2:9b"


class WritingAgent:
    """
    Generates scene scripts, dialogue, and narration from story bible data.

    Workflow:
    1. Load scene context from StoryManager.get_scene_with_context()
    2. Assemble prompt from: character personalities, world rules, arc context, tone
    3. Generate dialogue and narration via LLM
    4. Check for contradictions via Qdrant
    5. Return structured output for audio and caption generation
    """

    def __init__(self):
        self.story_manager = StoryManager()
        self.vector_store = StoryVectorStore()

    def generate_scene_script(self, scene_id: str) -> dict:
        """
        Generate complete script for a scene.

        Returns:
            {
                "dialogue": [{"character_id": int, "character_name": str, "line": str, "emotion": str, "timing_offset": float}],
                "narration": str,
                "stage_directions": str,
                "caption_text": str,  # For SRT generation
                "warnings": [...]       # Contradiction warnings if any
            }
        """
        context = self.story_manager.get_scene_with_context(scene_id)
        if not context:
            raise ValueError(f"Scene {scene_id} not found")

        prompt = self._assemble_prompt(context)
        raw = self._call_ollama(prompt)
        parsed = self._parse_output(raw, context)

        # Check for character dialogue contradictions
        for dl in parsed.get("dialogue", []):
            if dl.get("character_id"):
                contradictions = self.vector_store.find_contradictions(
                    character_id=dl.get("character_id"),
                    new_dialogue=dl.get("line", ""),
                    project_id=context["project_id"],
                )
                if contradictions and contradictions[0]["score"] > 0.8:
                    parsed.setdefault("warnings", []).append({
                        "type": "potential_contradiction",
                        "character": dl.get("character_name", ""),
                        "new_line": dl["line"][:100],
                        "similar_existing": contradictions[0]["text"][:100],
                        "score": contradictions[0]["score"],
                    })

        return parsed

    def _assemble_prompt(self, context: dict) -> str:
        """Build LLM prompt entirely from DB context. No hardcoded content."""
        scene = context["scene"]
        episode = context["episode"]
        characters = context["characters"]
        world_rules = context.get("world_rules", {})
        arcs = context.get("active_arcs", [])

        # Character descriptions
        char_lines = []
        for c in characters:
            tags = c.get("personality_tags") or []
            if isinstance(tags, str):
                tags = json.loads(tags) if tags.startswith('[') else [tags]
            rels = c.get("relationships") or {}
            if isinstance(rels, str):
                try:
                    rels = json.loads(rels)
                except:
                    rels = {}
            char_lines.append(
                f"- {c['name']} ({c.get('character_role','supporting')}): "
                f"{c.get('description','')} "
                f"Personality: {', '.join(tags) if isinstance(tags, list) else tags}. "
                f"Relationships: {json.dumps(rels) if isinstance(rels, dict) else str(rels)}"
            )
        char_block = "\n".join(char_lines) if char_lines else "No characters specified."

        # Arc context
        arc_lines = [f"- {a['name']} ({a.get('arc_type','')}): {a.get('description','')}" for a in arcs]
        arc_block = "\n".join(arc_lines) if arc_lines else "No active story arcs."

        # Tone and narrative rules
        tone_rules = world_rules.get("tone", {})
        narrative_rules = world_rules.get("narrative", {})
        char_rules = world_rules.get("character", {})

        tone_profile = episode.get("tone_profile") or {}
        if isinstance(tone_profile, str):
            try:
                tone_profile = json.loads(tone_profile)
            except:
                tone_profile = {}

        prompt = f"""You are a screenwriter for the anime "Echo Chamber". Write the script for this scene.

EPISODE: {episode.get('title', f"Episode {episode.get('episode_number','?')}")}
Synopsis: {episode.get('synopsis', 'N/A')}
Tone: {json.dumps(tone_profile)}

SCENE:
Setting: {scene.get('setting_description', 'unspecified')}
Direction: {scene.get('narrative_text', '')}
Emotional Tone: {scene.get('emotional_tone', 'neutral')}
Camera: {scene.get('camera_directions', 'standard')}

CHARACTERS IN SCENE:
{char_block}

STORY ARCS:
{arc_block}

WORLD RULES:
Tone: {json.dumps(tone_rules) if tone_rules else 'None specified'}
Narrative: {json.dumps(narrative_rules) if narrative_rules else 'None specified'}
Character: {json.dumps(char_rules) if char_rules else 'None specified'}

Respond ONLY with valid JSON in this exact format:
{{
    "dialogue": [
        {{"character_name": "...", "line": "...", "emotion": "...", "action": "..."}}
    ],
    "narration": "Voiceover narration text or empty string",
    "stage_directions": "Visual action descriptions for the animator"
}}

Write dialogue naturally. Comedy should come from the situation, not forced jokes. Dark moments must feel earned."""

        return prompt

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama with the assembled prompt."""
        logger.info(f"Calling {WRITING_MODEL} for scene script generation...")
        response = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": WRITING_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.8,
                    "num_predict": 2048,
                    "top_p": 0.9,
                },
                "format": "json",  # Request JSON format
            },
            timeout=180.0,  # 3 minutes for first call when model loads
        )
        response.raise_for_status()
        return response.json()["response"]

    def _parse_output(self, raw: str, context: dict) -> dict:
        """Parse LLM JSON output into structured script data."""
        # Try to extract JSON
        json_match = re.search(r'\{[\s\S]*\}', raw)
        if json_match:
            try:
                parsed = json.loads(json_match.group())

                # Map character names to IDs
                name_to_id = {c["name"]: c["id"] for c in context["characters"]}
                for dl in parsed.get("dialogue", []):
                    char_name = dl.get("character_name", "")
                    dl["character_id"] = name_to_id.get(char_name, None)
                    dl.setdefault("timing_offset", 0.0)
                    dl.setdefault("emotion", "neutral")

                # Build caption text for subtitle generation
                lines = []
                for dl in parsed.get("dialogue", []):
                    lines.append(f"{dl.get('character_name','')}: {dl.get('line','')}")
                if parsed.get("narration"):
                    lines.append(f"[Narrator]: {parsed['narration']}")
                parsed["caption_text"] = "\n".join(lines)

                return parsed
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from LLM: {e}")

        # Fallback: return raw text as narration
        return {
            "dialogue": [],
            "narration": raw[:1000],
            "stage_directions": "",
            "caption_text": raw[:1000],
            "parse_warning": "LLM output was not valid JSON",
        }