#!/usr/bin/env python3
"""
User Interaction System for Dynamic Anime Storyline Creation
Captures user intent, decisions, and feedback throughout the generation process
"""
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
import json
from pathlib import Path


class InteractionPoint(Enum):
    """Points where users can interact with the system"""
    CHARACTER_CREATION = "character_creation"
    POSE_SELECTION = "pose_selection"
    EMOTION_SELECTION = "emotion_selection"
    STORYLINE_DECISION = "storyline_decision"
    STYLE_PREFERENCE = "style_preference"
    FEEDBACK_LOOP = "feedback_loop"
    PLOT_BRANCH = "plot_branch"
    DIALOGUE_EDIT = "dialogue_edit"
    SCENE_APPROVAL = "scene_approval"


class UserIntent:
    """Represents parsed user intent"""
    def __init__(self, action: str, target: str, parameters: Dict[str, Any]):
        self.action = action
        self.target = target
        self.parameters = parameters
        self.timestamp = datetime.utcnow()
        self.confidence = 0.0


class UserInteractionSystem:
    """
    Manages all user interactions for storyline creation
    Integrates with Echo Brain for intelligent assistance
    """

    def __init__(self, echo_url: str = "http://localhost:8309"):
        self.echo_url = echo_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.interaction_history: List[Dict] = []
        self.user_preferences: Dict[str, Any] = {}
        self.current_context: Dict[str, Any] = {}

    async def initialize(self):
        """Initialize the interaction system"""
        self.session = aiohttp.ClientSession()

    async def cleanup(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()

    async def capture_intent(self, user_input: str, context: Dict = None) -> UserIntent:
        """
        Use Echo Brain to understand user intent
        """
        try:
            # Send to Echo for intent analysis
            async with self.session.post(
                f"{self.echo_url}/api/echo/query",
                json={
                    "query": f"Analyze user intent for anime creation: {user_input}",
                    "context": context or self.current_context,
                    "model": "qwen2.5-coder:32b"
                }
            ) as response:
                if response.status == 200:
                    result = await response.json()

                    # Parse Echo's response into intent
                    intent = self._parse_echo_response(result, user_input)

                    # Record interaction
                    self.interaction_history.append({
                        "input": user_input,
                        "intent": intent.__dict__,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                    return intent
        except Exception as e:
            print(f"Echo intent analysis failed: {e}")

        # Fallback to simple intent parsing
        return self._fallback_intent_parser(user_input)

    def _parse_echo_response(self, echo_response: Dict, original_input: str) -> UserIntent:
        """Parse Echo's analysis into structured intent"""
        # Extract structured intent from Echo's response
        response_text = echo_response.get("response", "")

        # Simple parsing - in production, use NLP
        action = "generate"
        target = "image"
        parameters = {}

        if "character" in response_text.lower():
            target = "character"
            if "create" in response_text.lower():
                action = "create"
            elif "edit" in response_text.lower():
                action = "edit"

        if "story" in response_text.lower():
            target = "storyline"
            if "branch" in response_text.lower():
                action = "branch"
            elif "continue" in response_text.lower():
                action = "continue"

        intent = UserIntent(action, target, parameters)
        intent.confidence = 0.8  # Echo-based intent has high confidence

        return intent

    def _fallback_intent_parser(self, user_input: str) -> UserIntent:
        """Simple fallback intent parser"""
        input_lower = user_input.lower()

        # Basic keyword matching
        if "create" in input_lower and "character" in input_lower:
            return UserIntent("create", "character", {})
        elif "generate" in input_lower:
            return UserIntent("generate", "image", {})
        elif "change" in input_lower or "edit" in input_lower:
            return UserIntent("edit", "unknown", {})
        else:
            return UserIntent("unknown", "unknown", {})

    async def suggest_next_action(self, story_context: Dict) -> List[Dict]:
        """
        Use Echo to suggest next actions in the story
        """
        try:
            async with self.session.post(
                f"{self.echo_url}/api/echo/query",
                json={
                    "query": "Suggest next story actions based on context",
                    "context": story_context,
                    "model": "qwen2.5-coder:32b"
                }
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return self._parse_suggestions(result)
        except Exception as e:
            print(f"Echo suggestion failed: {e}")

        # Fallback suggestions
        return [
            {"action": "continue_scene", "description": "Continue with current scene"},
            {"action": "add_character", "description": "Introduce new character"},
            {"action": "change_location", "description": "Move to different location"}
        ]

    def _parse_suggestions(self, echo_response: Dict) -> List[Dict]:
        """Parse Echo's suggestions into actionable items"""
        suggestions = []
        response_text = echo_response.get("response", "")

        # Parse structured suggestions from Echo's response
        # In production, this would be more sophisticated
        lines = response_text.split("\n")
        for line in lines:
            if line.strip():
                suggestions.append({
                    "action": "suggested_action",
                    "description": line.strip()
                })

        return suggestions[:5]  # Limit to 5 suggestions

    async def capture_decision(self,
                              options: List[str],
                              context: Dict = None) -> int:
        """
        Capture user's decision from multiple options
        """
        # In a real UI, this would be interactive
        # For now, return the decision
        decision = {
            "options": options,
            "context": context,
            "timestamp": datetime.utcnow().isoformat()
        }

        self.interaction_history.append({
            "type": "decision",
            "data": decision
        })

        return 0  # Return first option for now

    async def capture_feedback(self,
                              generation_id: str,
                              rating: int,
                              comments: str = "") -> None:
        """
        Capture user feedback on generated content
        """
        feedback = {
            "generation_id": generation_id,
            "rating": rating,
            "comments": comments,
            "timestamp": datetime.utcnow().isoformat()
        }

        self.interaction_history.append({
            "type": "feedback",
            "data": feedback
        })

        # Update preferences based on feedback
        await self._update_preferences(feedback)

    async def _update_preferences(self, feedback: Dict):
        """
        Update user preferences based on feedback
        """
        rating = feedback["rating"]

        # Simple preference learning
        if rating >= 4:
            # User liked it, remember the context
            if "style" in self.current_context:
                self.user_preferences["preferred_style"] = self.current_context["style"]
        elif rating <= 2:
            # User didn't like it, avoid this
            if "style" in self.current_context:
                if "avoided_styles" not in self.user_preferences:
                    self.user_preferences["avoided_styles"] = []
                self.user_preferences["avoided_styles"].append(self.current_context["style"])

    def get_interaction_points(self, story_phase: str) -> List[InteractionPoint]:
        """
        Get available interaction points for current story phase
        """
        phase_interactions = {
            "setup": [
                InteractionPoint.CHARACTER_CREATION,
                InteractionPoint.STYLE_PREFERENCE
            ],
            "development": [
                InteractionPoint.STORYLINE_DECISION,
                InteractionPoint.EMOTION_SELECTION,
                InteractionPoint.PLOT_BRANCH
            ],
            "climax": [
                InteractionPoint.STORYLINE_DECISION,
                InteractionPoint.DIALOGUE_EDIT
            ],
            "resolution": [
                InteractionPoint.SCENE_APPROVAL,
                InteractionPoint.FEEDBACK_LOOP
            ]
        }

        return phase_interactions.get(story_phase, [])

    async def interactive_character_creation(self) -> Dict:
        """
        Guide user through character creation with Echo assistance
        """
        character = {
            "name": "",
            "appearance": {},
            "personality": [],
            "backstory": "",
            "relationships": {}
        }

        # Step 1: Basic info
        print("Let's create a character! What's their name?")
        # In real implementation, get user input
        character["name"] = "User Character"

        # Step 2: Use Echo to generate suggestions
        try:
            async with self.session.post(
                f"{self.echo_url}/api/echo/query",
                json={
                    "query": f"Suggest appearance traits for anime character named {character['name']}",
                    "model": "qwen2.5-coder:32b"
                }
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    # Parse and present suggestions
                    character["appearance"] = self._parse_appearance(result)
        except Exception as e:
            print(f"Echo suggestion failed: {e}")

        # Step 3: Personality traits
        character["personality"] = await self._select_personality_traits()

        # Step 4: Generate backstory with Echo
        character["backstory"] = await self._generate_backstory(character)

        return character

    def _parse_appearance(self, echo_response: Dict) -> Dict:
        """Parse appearance suggestions from Echo"""
        # Simple parsing - in production would be more sophisticated
        return {
            "hair_color": "pink",
            "eye_color": "blue",
            "height": "average",
            "style": "casual"
        }

    async def _select_personality_traits(self) -> List[str]:
        """Let user select personality traits"""
        available_traits = [
            "brave", "shy", "intelligent", "creative",
            "loyal", "mischievous", "serious", "cheerful"
        ]

        # In real implementation, user would select
        return ["brave", "loyal", "cheerful"]

    async def _generate_backstory(self, character: Dict) -> str:
        """Use Echo to generate character backstory"""
        try:
            async with self.session.post(
                f"{self.echo_url}/api/echo/query",
                json={
                    "query": f"Generate backstory for character: {json.dumps(character)}",
                    "model": "qwen2.5-coder:32b"
                }
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("response", "A mysterious past...")
        except Exception as e:
            print(f"Backstory generation failed: {e}")

        return "A character with an untold story..."

    def export_interaction_history(self, filepath: Path):
        """Export interaction history for analysis"""
        with open(filepath, 'w') as f:
            json.dump({
                "history": self.interaction_history,
                "preferences": self.user_preferences,
                "export_time": datetime.utcnow().isoformat()
            }, f, indent=2)

    async def adapt_to_user_style(self, base_prompt: str) -> str:
        """
        Adapt generation prompt based on learned preferences
        """
        adapted_prompt = base_prompt

        # Add preferred styles
        if "preferred_style" in self.user_preferences:
            adapted_prompt += f", {self.user_preferences['preferred_style']} style"

        # Avoid disliked styles
        if "avoided_styles" in self.user_preferences:
            for style in self.user_preferences["avoided_styles"]:
                adapted_prompt += f", not {style}"

        return adapted_prompt


class InteractiveSession:
    """
    Manages an interactive storyline creation session
    """

    def __init__(self, user_system: UserInteractionSystem):
        self.user_system = user_system
        self.session_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.story_state = {
            "phase": "setup",
            "chapters": [],
            "characters": {},
            "current_scene": None
        }

    async def start_session(self):
        """Start an interactive session"""
        print(f"🎬 Starting interactive storyline session {self.session_id}")

        # Phase 1: Setup
        await self.setup_phase()

        # Phase 2: Development
        await self.development_phase()

        # Phase 3: Resolution
        await self.resolution_phase()

    async def setup_phase(self):
        """Initial setup with user"""
        print("\n📚 Story Setup Phase")

        # Create main character
        character = await self.user_system.interactive_character_creation()
        self.story_state["characters"]["main"] = character

        # Get story premise
        print("\nWhat's your story about?")
        # In real implementation, get user input
        premise = "A magical adventure"

        # Use Echo to develop initial plot
        self.story_state["premise"] = premise

    async def development_phase(self):
        """Story development with user decisions"""
        print("\n📖 Story Development Phase")

        # Get available interactions
        interactions = self.user_system.get_interaction_points("development")

        for interaction in interactions:
            if interaction == InteractionPoint.STORYLINE_DECISION:
                # Present choices to user
                options = await self.user_system.suggest_next_action(self.story_state)
                choice = await self.user_system.capture_decision(
                    [opt["description"] for opt in options],
                    self.story_state
                )

    async def resolution_phase(self):
        """Conclude the story with user approval"""
        print("\n🎭 Story Resolution Phase")

        # Generate ending options
        # Get user approval
        # Finalize story


# Example usage
async def main():
    """Example interactive session"""
    user_system = UserInteractionSystem()
    await user_system.initialize()

    try:
        # Create interactive session
        session = InteractiveSession(user_system)
        await session.start_session()

        # Export history
        user_system.export_interaction_history(
            Path(f"/tmp/interaction_history_{session.session_id}.json")
        )

    finally:
        await user_system.cleanup()


if __name__ == "__main__":
    asyncio.run(main())