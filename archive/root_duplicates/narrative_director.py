"""
Narrative Director System - User-driven story development with Echo assistance
Echo asks intelligent questions to help users build dynamic story-driven character generation
"""

import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class NarrativeDirector:
    """
    Story-driven character system where user drives the narrative
    and Echo assists with intelligent questions and suggestions
    """

    def __init__(self):
        self.story_beats = {
            "opening": {
                "description": "Character introduction and setup",
                "character_state": "fresh, optimistic, unmarked by conflict",
                "visual_modifiers": ["clean", "bright lighting", "hopeful expression"]
            },
            "inciting_incident": {
                "description": "The event that starts the character's journey",
                "character_state": "shocked, determined, purpose awakening",
                "visual_modifiers": ["intense eyes", "clenched jaw", "dramatic lighting"]
            },
            "first_conflict": {
                "description": "Character's first real challenge",
                "character_state": "tested, learning, some wear showing",
                "visual_modifiers": ["minor scuffs", "focused expression", "dynamic pose"]
            },
            "darkest_moment": {
                "description": "Character at their lowest point",
                "character_state": "worn down, questioning, battle-scarred",
                "visual_modifiers": ["heavy wear", "shadows", "exhausted but determined"]
            },
            "revelation": {
                "description": "Character's breakthrough moment",
                "character_state": "enlightened, resolved, transformed",
                "visual_modifiers": ["piercing gaze", "confident stance", "symbolic lighting"]
            },
            "climax": {
                "description": "Final confrontation",
                "character_state": "fully evolved, peak power, all skills mastered",
                "visual_modifiers": ["battle-ready", "intense energy", "dramatic composition"]
            },
            "resolution": {
                "description": "After the journey",
                "character_state": "changed, wiser, marked by experience",
                "visual_modifiers": ["wisdom in eyes", "scars as stories", "peaceful strength"]
            }
        }

        self.character_aspects = {
            "emotional_core": [
                "What drives this character's deepest motivations?",
                "What are they afraid of losing?",
                "What would make them compromise their values?"
            ],
            "visual_evolution": [
                "How does their appearance change through the story?",
                "What physical marks does their journey leave?",
                "How does their style reflect their internal state?"
            ],
            "relationships": [
                "Who influences this character's development?",
                "What relationships challenge them most?",
                "How do they change others around them?"
            ],
            "power_progression": [
                "What abilities do they start with?",
                "What do they gain through struggle?",
                "What do they sacrifice for power?"
            ]
        }

    def get_story_questions_for_character(self, character_name: str, story_beat: str = "opening") -> List[Dict[str, str]]:
        """Generate intelligent questions to help user develop character at specific story beat"""
        questions = []

        beat_info = self.story_beats.get(story_beat, self.story_beats["opening"])

        # Context-aware questions based on story beat
        questions.append({
            "category": "story_context",
            "question": f"At the '{story_beat}' point, where is {character_name} mentally and emotionally?",
            "purpose": "Establish character's internal state",
            "beat_context": beat_info["description"]
        })

        questions.append({
            "category": "visual_state",
            "question": f"How has {character_name}'s appearance changed by this point in the story?",
            "purpose": "Define visual evolution",
            "suggested_modifiers": beat_info["visual_modifiers"]
        })

        questions.append({
            "category": "scene_context",
            "question": f"What kind of scene are you envisioning {character_name} in right now?",
            "purpose": "Set generation context",
            "examples": ["intense dialogue", "action sequence", "quiet reflection", "confrontation"]
        })

        # Add aspect-specific questions
        for aspect, aspect_questions in self.character_aspects.items():
            questions.append({
                "category": aspect,
                "question": aspect_questions[0],  # Use first question from each aspect
                "purpose": f"Develop {aspect} understanding"
            })

        return questions

    def build_dynamic_prompt_from_answers(self, character_name: str, story_beat: str,
                                        user_answers: Dict[str, str]) -> Dict[str, Any]:
        """Convert user's story answers into dynamic character generation prompt"""

        beat_info = self.story_beats.get(story_beat, self.story_beats["opening"])

        # Extract key elements from answers
        emotional_state = user_answers.get("story_context", "determined")
        visual_changes = user_answers.get("visual_state", "no significant changes")
        scene_type = user_answers.get("scene_context", "character portrait")

        # Build dynamic prompt components
        base_character = f"{character_name}"
        story_context = f"story beat: {story_beat}, {beat_info['description']}"
        emotional_context = f"emotional state: {emotional_state}"
        visual_context = f"visual evolution: {visual_changes}"
        scene_context = f"scene: {scene_type}"

        # Combine with beat modifiers
        beat_modifiers = ", ".join(beat_info["visual_modifiers"])

        dynamic_prompt = f"{base_character}, {story_context}, {emotional_context}, {visual_context}, {scene_context}, {beat_modifiers}"

        return {
            "prompt": dynamic_prompt,
            "story_seed": f"{character_name}_{story_beat}_{hash(str(user_answers)) % 10000}",
            "narrative_context": {
                "beat": story_beat,
                "emotional_state": emotional_state,
                "visual_evolution": visual_changes,
                "scene_type": scene_type
            },
            "consistency_elements": beat_info["visual_modifiers"]
        }

    def get_echo_director_prompts(self, character_name: str, story_beat: str) -> List[str]:
        """Generate prompts for Echo to ask intelligent follow-up questions"""

        return [
            f"Ask the user about {character_name}'s emotional journey to this point",
            f"Inquire about specific visual details for the {story_beat} scene",
            f"Suggest creative possibilities for {character_name}'s character evolution",
            f"Ask about the narrative weight of this moment in the overall story",
            f"Explore how {character_name} has changed since their last appearance"
        ]


def get_narrative_questions(character_name: str, story_beat: str = "opening") -> List[Dict[str, str]]:
    """Main function for Echo to get story development questions"""
    director = NarrativeDirector()
    return director.get_story_questions_for_character(character_name, story_beat)


def build_story_driven_prompt(character_name: str, story_beat: str, user_answers: Dict[str, str]) -> Dict[str, Any]:
    """Main function for Echo to convert story answers into generation prompts"""
    director = NarrativeDirector()
    return director.build_dynamic_prompt_from_answers(character_name, story_beat, user_answers)