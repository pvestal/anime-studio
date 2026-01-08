"""Echo Brain Memory Service for FramePack video generation.

Manages character/story/visual state persistence across scenes and segments,
with learning from generation quality feedback.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class CharacterState:
    """Character state for a scene."""

    character_id: int
    character_name: str
    outfit_description: str
    hair_style: str
    accessories: List[str]
    facial_expression: str
    body_pose: str
    emotional_state: str
    position_description: str
    facing_direction: str


@dataclass
class StoryState:
    """Story/narrative state for a scene."""

    plot_summary: str
    prior_context: str
    upcoming_context: str
    tension_level: float
    pacing: str
    story_beat: str
    key_dialogue: List[str]
    music_mood: str


@dataclass
class VisualState:
    """Visual style state for a scene."""

    lighting_type: str
    lighting_direction: str
    lighting_color: str
    shadow_intensity: float
    primary_colors: List[str]
    accent_colors: List[str]
    color_temperature: str
    saturation_level: str
    camera_angle: str
    camera_movement: str
    depth_of_field: str
    style_keywords: List[str]
    negative_style_keywords: List[str]


@dataclass
class SceneContext:
    """Complete scene context combining all memory types."""

    scene_id: int
    scene_number: int
    scene_title: str
    location: str
    time_of_day: str
    weather: str
    mood: str
    characters: List[CharacterState]
    story: Optional[StoryState]
    visual: Optional[VisualState]


class EchoBrainMemory:
    """Echo Brain memory service for FramePack generation.

    Manages:
    - Character state per scene (outfit, expression, pose)
    - Story context per scene (plot, tension, pacing)
    - Visual style per scene (lighting, colors, camera)
    - Quality feedback learning (successful/failed prompt elements)
    """

    def __init__(self, database_url: str):
        """Initialize Echo Brain Memory service.

        Args:
            database_url: PostgreSQL connection URL
        """
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Establish database connection pool."""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(self.database_url, min_size=2, max_size=10)
            logger.info("Echo Brain Memory connected to database")

    async def close(self) -> None:
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Echo Brain Memory disconnected from database")

    async def get_scene_context(self, scene_id: int) -> Optional[SceneContext]:
        """Load complete scene context including character/story/visual state.

        Args:
            scene_id: Database ID of the scene

        Returns:
            SceneContext with all memory data, or None if scene not found
        """
        async with self.pool.acquire() as conn:
            # Get scene basic info
            scene = await conn.fetchrow(
                """
                SELECT id, scene_number, scene_title, location, time_of_day, weather, mood
                FROM movie_scenes WHERE id = $1
                """,
                scene_id,
            )

            if not scene:
                logger.warning(f"Scene {scene_id} not found")
                return None

            # Get character states
            characters = await conn.fetch(
                """
                SELECT csm.*, ac.character_name
                FROM character_scene_memory csm
                JOIN anime_characters ac ON csm.character_id = ac.id
                WHERE csm.scene_id = $1
                """,
                scene_id,
            )

            character_states = [
                CharacterState(
                    character_id=c["character_id"],
                    character_name=c["character_name"],
                    outfit_description=c["outfit_description"] or "",
                    hair_style=c["hair_style"] or "",
                    accessories=c["accessories"] or [],
                    facial_expression=c["facial_expression"] or "",
                    body_pose=c["body_pose"] or "",
                    emotional_state=c["emotional_state"] or "",
                    position_description=c["position_description"] or "",
                    facing_direction=c["facing_direction"] or "",
                )
                for c in characters
            ]

            # Get story state
            story_row = await conn.fetchrow(
                "SELECT * FROM story_state_memory WHERE scene_id = $1",
                scene_id,
            )

            story_state = None
            if story_row:
                story_state = StoryState(
                    plot_summary=story_row["plot_summary"] or "",
                    prior_context=story_row["prior_context"] or "",
                    upcoming_context=story_row["upcoming_context"] or "",
                    tension_level=story_row["tension_level"] or 0.5,
                    pacing=story_row["pacing"] or "medium",
                    story_beat=story_row["story_beat"] or "",
                    key_dialogue=story_row["key_dialogue"] or [],
                    music_mood=story_row["music_mood"] or "",
                )

            # Get visual state
            visual_row = await conn.fetchrow(
                "SELECT * FROM visual_style_memory WHERE scene_id = $1",
                scene_id,
            )

            visual_state = None
            if visual_row:
                visual_state = VisualState(
                    lighting_type=visual_row["lighting_type"] or "",
                    lighting_direction=visual_row["lighting_direction"] or "",
                    lighting_color=visual_row["lighting_color"] or "",
                    shadow_intensity=visual_row["shadow_intensity"] or 0.5,
                    primary_colors=visual_row["primary_colors"] or [],
                    accent_colors=visual_row["accent_colors"] or [],
                    color_temperature=visual_row["color_temperature"] or "neutral",
                    saturation_level=visual_row["saturation_level"] or "normal",
                    camera_angle=visual_row["camera_angle"] or "",
                    camera_movement=visual_row["camera_movement"] or "",
                    depth_of_field=visual_row["depth_of_field"] or "",
                    style_keywords=visual_row["style_keywords"] or [],
                    negative_style_keywords=visual_row["negative_style_keywords"] or [],
                )

            return SceneContext(
                scene_id=scene["id"],
                scene_number=scene["scene_number"],
                scene_title=scene["scene_title"] or "",
                location=scene["location"] or "",
                time_of_day=scene["time_of_day"] or "",
                weather=scene["weather"] or "",
                mood=scene["mood"] or "",
                characters=character_states,
                story=story_state,
                visual=visual_state,
            )

    async def generate_motion_prompt(
        self, scene_id: int, segment_num: int, action: str
    ) -> Tuple[str, str]:
        """Generate FramePack motion prompt using context AND learned patterns.

        Args:
            scene_id: Scene to generate for
            segment_num: Segment number within scene
            action: Base action description (e.g., "character walks forward")

        Returns:
            Tuple of (positive_prompt, negative_prompt)
        """
        context = await self.get_scene_context(scene_id)
        if not context:
            # Fallback to basic prompt
            return action, "low quality, blurry, distorted"

        # Build base prompt from context
        prompt_parts = []

        # Scene setting
        if context.location:
            prompt_parts.append(context.location)
        if context.time_of_day:
            prompt_parts.append(f"{context.time_of_day} lighting")
        if context.weather and context.weather != "clear":
            prompt_parts.append(context.weather)
        if context.mood:
            prompt_parts.append(f"{context.mood} atmosphere")

        # Character descriptions
        for char in context.characters:
            char_desc = []
            char_desc.append(char.character_name)
            if char.outfit_description:
                char_desc.append(f"wearing {char.outfit_description}")
            if char.facial_expression:
                char_desc.append(f"{char.facial_expression} expression")
            if char.body_pose:
                char_desc.append(char.body_pose)
            if char.position_description:
                char_desc.append(char.position_description)
            prompt_parts.append(", ".join(char_desc))

        # Visual style
        if context.visual:
            if context.visual.lighting_type:
                prompt_parts.append(f"{context.visual.lighting_type} lighting")
            if context.visual.camera_angle:
                prompt_parts.append(f"{context.visual.camera_angle} shot")
            if context.visual.camera_movement:
                prompt_parts.append(f"{context.visual.camera_movement} camera")
            prompt_parts.extend(context.visual.style_keywords)

        # Action
        prompt_parts.append(action)

        # Story context for emotional tone
        if context.story:
            if context.story.tension_level > 0.7:
                prompt_parts.append("intense")
            elif context.story.tension_level < 0.3:
                prompt_parts.append("calm")

        # Get learned enhancements
        for char in context.characters:
            learned = await self._get_learned_enhancements(char.character_id)
            prompt_parts.extend(learned)

        # Build positive prompt
        positive_prompt = ", ".join(filter(None, prompt_parts))

        # Build negative prompt
        negative_parts = ["low quality", "blurry", "distorted", "deformed"]
        if context.visual and context.visual.negative_style_keywords:
            negative_parts.extend(context.visual.negative_style_keywords)

        # Remove failed patterns from positive prompt
        positive_prompt = await self._remove_failed_patterns(positive_prompt)

        negative_prompt = ", ".join(negative_parts)

        logger.info(
            f"Generated prompt for scene {scene_id} segment {segment_num}: {positive_prompt[:100]}..."
        )

        return positive_prompt, negative_prompt

    async def _get_learned_enhancements(self, character_id: int) -> List[str]:
        """Query successful prompt elements from past generations.

        Args:
            character_id: Character to get enhancements for

        Returns:
            List of successful prompt elements (score > 0.7)
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT unnest(successful_elements) as element, COUNT(*) as cnt
                FROM generation_quality_feedback
                WHERE character_id = $1 AND overall_score >= 0.7
                GROUP BY element
                ORDER BY cnt DESC
                LIMIT 5
                """,
                character_id,
            )

            elements = [row["element"] for row in rows if row["element"]]
            if elements:
                logger.debug(f"Learned enhancements for character {character_id}: {elements}")
            return elements

    async def _remove_failed_patterns(self, prompt: str) -> str:
        """Remove elements that produced poor results (score < 0.4).

        Args:
            prompt: Original prompt string

        Returns:
            Cleaned prompt with failed patterns removed
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT unnest(failed_elements) as element, COUNT(*) as cnt
                FROM generation_quality_feedback
                WHERE overall_score < 0.4
                GROUP BY element
                HAVING COUNT(*) >= 3
                ORDER BY cnt DESC
                LIMIT 20
                """,
            )

            failed_patterns = [row["element"] for row in rows if row["element"]]

            cleaned_prompt = prompt
            for pattern in failed_patterns:
                if pattern.lower() in cleaned_prompt.lower():
                    # Remove the failed pattern (case-insensitive)
                    import re

                    cleaned_prompt = re.sub(
                        rf",?\s*{re.escape(pattern)}\s*,?",
                        ", ",
                        cleaned_prompt,
                        flags=re.IGNORECASE,
                    )
                    logger.debug(f"Removed failed pattern: {pattern}")

            # Clean up double commas and spaces
            cleaned_prompt = ", ".join(filter(None, cleaned_prompt.split(",")))

            return cleaned_prompt.strip()

    async def record_quality_feedback(
        self,
        segment_id: int,
        metrics: Dict[str, Any],
        prompt: str,
        character_id: Optional[int] = None,
    ) -> int:
        """Store quality scores and extract successful/failed elements.

        Args:
            segment_id: ID of the generation segment
            metrics: Quality metrics dict with scores
            prompt: The prompt that was used
            character_id: Optional character ID for character-specific learning

        Returns:
            ID of the created feedback record
        """
        overall_score = metrics.get("overall_score", 0.0)
        frame_consistency = metrics.get("frame_consistency_score")
        motion_smoothness = metrics.get("motion_smoothness_score")
        character_accuracy = metrics.get("character_accuracy_score")
        style_consistency = metrics.get("style_consistency_score")

        # Extract prompt elements
        prompt_elements = [e.strip() for e in prompt.split(",") if e.strip()]

        # Categorize elements based on score
        successful_elements = []
        failed_elements = []

        if overall_score >= 0.7:
            # High quality - these elements contributed to success
            successful_elements = prompt_elements
            logger.info(f"Recording {len(successful_elements)} successful elements")
        elif overall_score < 0.4:
            # Low quality - these elements may have caused issues
            failed_elements = prompt_elements
            logger.info(f"Recording {len(failed_elements)} failed elements")

        async with self.pool.acquire() as conn:
            feedback_id = await conn.fetchval(
                """
                INSERT INTO generation_quality_feedback (
                    segment_id, character_id, overall_score,
                    frame_consistency_score, motion_smoothness_score,
                    character_accuracy_score, style_consistency_score,
                    full_prompt, successful_elements, failed_elements,
                    generation_parameters
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING id
                """,
                segment_id,
                character_id,
                overall_score,
                frame_consistency,
                motion_smoothness,
                character_accuracy,
                style_consistency,
                prompt,
                successful_elements,
                failed_elements,
                metrics.get("parameters", {}),
            )

            logger.info(f"Recorded quality feedback {feedback_id} for segment {segment_id}")
            return feedback_id

    async def propagate_to_next_scene(self, scene_id: int) -> Optional[int]:
        """Carry character/story state forward to the next scene.

        Creates memory records for the next scene based on current scene state,
        maintaining continuity for outfit, position, emotional arc, etc.

        Args:
            scene_id: Current scene ID

        Returns:
            Next scene ID if propagation successful, None otherwise
        """
        async with self.pool.acquire() as conn:
            # Get current scene info
            current_scene = await conn.fetchrow(
                """
                SELECT movie_id, scene_number, exit_keyframe_path
                FROM movie_scenes WHERE id = $1
                """,
                scene_id,
            )

            if not current_scene:
                logger.warning(f"Scene {scene_id} not found for propagation")
                return None

            # Find next scene
            next_scene = await conn.fetchrow(
                """
                SELECT id FROM movie_scenes
                WHERE movie_id = $1 AND scene_number = $2
                """,
                current_scene["movie_id"],
                current_scene["scene_number"] + 1,
            )

            if not next_scene:
                logger.info(f"No next scene after scene {scene_id}")
                return None

            next_scene_id = next_scene["id"]

            # Copy character states (maintaining continuity)
            await conn.execute(
                """
                INSERT INTO character_scene_memory (
                    scene_id, character_id, outfit_description, hair_style,
                    accessories, facial_expression, body_pose, emotional_state,
                    position_description, facing_direction
                )
                SELECT $1, character_id, outfit_description, hair_style,
                       accessories, facial_expression, body_pose, emotional_state,
                       position_description, facing_direction
                FROM character_scene_memory
                WHERE scene_id = $2 AND exited_scene_at IS NULL
                ON CONFLICT (scene_id, character_id) DO UPDATE SET
                    outfit_description = EXCLUDED.outfit_description,
                    hair_style = EXCLUDED.hair_style,
                    accessories = EXCLUDED.accessories
                """,
                next_scene_id,
                scene_id,
            )

            # Propagate story context
            current_story = await conn.fetchrow(
                "SELECT * FROM story_state_memory WHERE scene_id = $1",
                scene_id,
            )

            if current_story:
                await conn.execute(
                    """
                    INSERT INTO story_state_memory (
                        scene_id, prior_context, tension_level, pacing
                    ) VALUES ($1, $2, $3, $4)
                    ON CONFLICT (scene_id) DO UPDATE SET
                        prior_context = EXCLUDED.prior_context
                    """,
                    next_scene_id,
                    current_story["plot_summary"],  # Current becomes prior
                    current_story["tension_level"],
                    current_story["pacing"],
                )

            # Set entry keyframe from current scene's exit
            if current_scene["exit_keyframe_path"]:
                await conn.execute(
                    """
                    UPDATE movie_scenes
                    SET entry_keyframe_path = $1
                    WHERE id = $2 AND entry_keyframe_path IS NULL
                    """,
                    current_scene["exit_keyframe_path"],
                    next_scene_id,
                )

            logger.info(f"Propagated state from scene {scene_id} to scene {next_scene_id}")
            return next_scene_id

    async def initialize_scene_memory(
        self,
        scene_id: int,
        characters: List[Dict[str, Any]],
        story: Optional[Dict[str, Any]] = None,
        visual: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize memory for a new scene.

        Args:
            scene_id: Scene to initialize
            characters: List of character state dicts
            story: Optional story state dict
            visual: Optional visual style dict
        """
        async with self.pool.acquire() as conn:
            # Insert character states
            for char in characters:
                await conn.execute(
                    """
                    INSERT INTO character_scene_memory (
                        scene_id, character_id, outfit_description, hair_style,
                        accessories, facial_expression, body_pose, emotional_state,
                        position_description, facing_direction
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (scene_id, character_id) DO UPDATE SET
                        outfit_description = EXCLUDED.outfit_description,
                        hair_style = EXCLUDED.hair_style,
                        accessories = EXCLUDED.accessories,
                        facial_expression = EXCLUDED.facial_expression,
                        body_pose = EXCLUDED.body_pose,
                        emotional_state = EXCLUDED.emotional_state,
                        position_description = EXCLUDED.position_description,
                        facing_direction = EXCLUDED.facing_direction
                    """,
                    scene_id,
                    char["character_id"],
                    char.get("outfit_description"),
                    char.get("hair_style"),
                    char.get("accessories", []),
                    char.get("facial_expression"),
                    char.get("body_pose"),
                    char.get("emotional_state"),
                    char.get("position_description"),
                    char.get("facing_direction"),
                )

            # Insert story state
            if story:
                await conn.execute(
                    """
                    INSERT INTO story_state_memory (
                        scene_id, plot_summary, prior_context, upcoming_context,
                        tension_level, pacing, story_beat, key_dialogue, music_mood
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (scene_id) DO UPDATE SET
                        plot_summary = EXCLUDED.plot_summary,
                        prior_context = EXCLUDED.prior_context,
                        upcoming_context = EXCLUDED.upcoming_context,
                        tension_level = EXCLUDED.tension_level,
                        pacing = EXCLUDED.pacing,
                        story_beat = EXCLUDED.story_beat,
                        key_dialogue = EXCLUDED.key_dialogue,
                        music_mood = EXCLUDED.music_mood
                    """,
                    scene_id,
                    story.get("plot_summary"),
                    story.get("prior_context"),
                    story.get("upcoming_context"),
                    story.get("tension_level", 0.5),
                    story.get("pacing", "medium"),
                    story.get("story_beat"),
                    story.get("key_dialogue", []),
                    story.get("music_mood"),
                )

            # Insert visual state
            if visual:
                await conn.execute(
                    """
                    INSERT INTO visual_style_memory (
                        scene_id, lighting_type, lighting_direction, lighting_color,
                        shadow_intensity, primary_colors, accent_colors,
                        color_temperature, saturation_level, camera_angle,
                        camera_movement, depth_of_field, style_keywords,
                        negative_style_keywords
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    ON CONFLICT (scene_id) DO UPDATE SET
                        lighting_type = EXCLUDED.lighting_type,
                        lighting_direction = EXCLUDED.lighting_direction,
                        lighting_color = EXCLUDED.lighting_color,
                        shadow_intensity = EXCLUDED.shadow_intensity,
                        primary_colors = EXCLUDED.primary_colors,
                        accent_colors = EXCLUDED.accent_colors,
                        color_temperature = EXCLUDED.color_temperature,
                        saturation_level = EXCLUDED.saturation_level,
                        camera_angle = EXCLUDED.camera_angle,
                        camera_movement = EXCLUDED.camera_movement,
                        depth_of_field = EXCLUDED.depth_of_field,
                        style_keywords = EXCLUDED.style_keywords,
                        negative_style_keywords = EXCLUDED.negative_style_keywords
                    """,
                    scene_id,
                    visual.get("lighting_type"),
                    visual.get("lighting_direction"),
                    visual.get("lighting_color"),
                    visual.get("shadow_intensity", 0.5),
                    visual.get("primary_colors", []),
                    visual.get("accent_colors", []),
                    visual.get("color_temperature", "neutral"),
                    visual.get("saturation_level", "normal"),
                    visual.get("camera_angle"),
                    visual.get("camera_movement"),
                    visual.get("depth_of_field"),
                    visual.get("style_keywords", []),
                    visual.get("negative_style_keywords", []),
                )

            logger.info(f"Initialized memory for scene {scene_id}")
