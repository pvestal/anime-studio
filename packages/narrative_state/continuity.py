"""Temporal continuity — state-aware source selection and prompt building for video generation.

Integrates with builder.py to ensure generated videos reflect character states.
"""

import logging
from pathlib import Path
from typing import Any

from packages.core.db import connect_direct

logger = logging.getLogger(__name__)


async def get_shot_state_context(
    conn, scene_id: str, shot: dict,
) -> dict[str, dict[str, Any]]:
    """Build per-character state + prompt additions for a shot.

    Returns {character_slug: {"state": {...}, "prompt_additions": str, "negative_additions": str}}
    """
    chars = shot.get("characters_present") or []
    if not chars:
        return {}

    result = {}
    for slug in chars:
        if not isinstance(slug, str):
            continue

        row = await conn.fetchrow(
            "SELECT * FROM character_scene_state "
            "WHERE scene_id = $1 AND character_slug = $2",
            scene_id, slug,
        )
        if not row:
            continue

        state = dict(row)
        prompt_parts = []
        negative_parts = []

        # Clothing
        if state.get("clothing"):
            prompt_parts.append(f"wearing {state['clothing']}")

        # Hair state
        if state.get("hair_state"):
            prompt_parts.append(f"{state['hair_state']} hair")

        # Expression (for motion/behavior in video)
        emotional = state.get("emotional_state", "calm")
        if emotional != "calm":
            emotion_motion = {
                "furious": "aggressive movements, intense expression",
                "angry": "tense body language, angry expression",
                "irritated": "slight frown, restless",
                "happy": "cheerful expression, lively movement",
                "content": "relaxed, slight smile",
                "sad": "downcast eyes, slow movement",
                "melancholy": "wistful expression",
                "scared": "wide eyes, trembling slightly",
                "anxious": "fidgeting, nervous glances",
                "terrified": "frozen in fear, wide eyes",
                "shocked": "stunned expression, mouth agape",
                "surprised": "raised eyebrows, alert posture",
                "determined": "set jaw, focused gaze",
                "focused": "intent concentration",
            }
            motion = emotion_motion.get(emotional, f"{emotional} expression")
            prompt_parts.append(motion)

        # Body state
        body = state.get("body_state", "clean")
        if body != "clean":
            prompt_parts.append(f"{body} appearance")
            if body == "clean":
                negative_parts.append("dirty, bloody, stained")

        # Energy (affects motion style)
        energy = state.get("energy_level", "normal")
        if energy == "exhausted":
            prompt_parts.append("sluggish movement, exhausted")
        elif energy == "tired":
            prompt_parts.append("slow movement")
        elif energy == "energized":
            prompt_parts.append("energetic movement")

        # Injuries
        injuries = state.get("injuries", [])
        if injuries:
            import json
            if isinstance(injuries, str):
                try:
                    injuries = json.loads(injuries)
                except (json.JSONDecodeError, TypeError):
                    injuries = []
            for inj in injuries[:2]:
                if isinstance(inj, dict):
                    loc = inj.get("location", "")
                    sev = inj.get("severity", "")
                    if loc and sev:
                        prompt_parts.append(f"{sev} injury on {loc}")

        # Carrying items (important for video — character should be holding things)
        carrying = state.get("carrying", [])
        if carrying:
            prompt_parts.append(f"holding {', '.join(carrying[:2])}")

        result[slug] = {
            "state": state,
            "prompt_additions": ", ".join(prompt_parts) if prompt_parts else "",
            "negative_additions": ", ".join(negative_parts) if negative_parts else "",
        }

    return result


async def select_continuity_source(
    conn,
    project_id: int,
    character_slug: str,
    target_state: dict[str, Any] | None,
    scene_id: str,
) -> str | None:
    """State-aware continuity frame selection.

    Prefer frames matching current clothing/expression over most-recent frame.
    Falls back to standard continuity frame when no state exists.
    """
    # Standard continuity frame (fallback)
    standard_frame = await conn.fetchrow("""
        SELECT frame_path FROM character_continuity_frames
        WHERE project_id = $1 AND character_slug = $2 AND scene_id != $3
    """, project_id, character_slug, scene_id)

    standard_path = None
    if standard_frame and standard_frame["frame_path"]:
        if Path(standard_frame["frame_path"]).exists():
            standard_path = standard_frame["frame_path"]

    if not target_state:
        return standard_path

    # Try to find a frame from a scene with matching state
    matching_rows = await conn.fetch("""
        SELECT ccf.frame_path, css.clothing, css.emotional_state, css.hair_state
        FROM character_continuity_frames ccf
        JOIN character_scene_state css
            ON css.scene_id = ccf.scene_id AND css.character_slug = ccf.character_slug
        WHERE ccf.project_id = $1
            AND ccf.character_slug = $2
            AND ccf.scene_id != $3
            AND ccf.frame_path IS NOT NULL
    """, project_id, character_slug, scene_id)

    if not matching_rows:
        return standard_path

    # Score each frame by state similarity
    best_path = standard_path
    best_score = 0.0

    for row in matching_rows:
        if not row["frame_path"] or not Path(row["frame_path"]).exists():
            continue

        score = 0.0
        # Clothing match (most important)
        if row["clothing"] and target_state.get("clothing"):
            if row["clothing"].lower().strip() == target_state["clothing"].lower().strip():
                score += 0.5
            elif any(w in row["clothing"].lower() for w in target_state["clothing"].lower().split()):
                score += 0.25

        # Expression match
        if row["emotional_state"] and target_state.get("emotional_state"):
            if row["emotional_state"] == target_state["emotional_state"]:
                score += 0.3
            # Close emotions
            elif row["emotional_state"] in ("calm", "content") and target_state["emotional_state"] in ("calm", "content"):
                score += 0.2

        # Hair match
        if row["hair_state"] and target_state.get("hair_state"):
            if row["hair_state"].lower() == target_state["hair_state"].lower():
                score += 0.2

        if score > best_score:
            best_score = score
            best_path = row["frame_path"]

    if best_score > 0:
        logger.info(
            f"Continuity: state-matched frame for {character_slug} "
            f"(score={best_score:.2f}) vs standard"
        )

    return best_path


def build_multi_character_state_prompt(
    characters: list[dict[str, Any]],
    motion_prompt: str,
    relationship_context: dict[str, Any] | None = None,
) -> str:
    """Build a Wan T2V prompt encoding all characters' states + relationships.

    Args:
        characters: List of {name, slug, design_prompt, state: {...}} dicts.
        motion_prompt: The shot's action description.
        relationship_context: Optional relationship data between characters.
    """
    char_blocks = []
    for char in characters:
        state = char.get("state", {})
        parts = [f"{char['name']}: {char.get('design_prompt', '').strip().rstrip(',. ')}"]

        if state.get("clothing"):
            parts.append(f"wearing {state['clothing']}")
        if state.get("emotional_state") and state["emotional_state"] != "calm":
            parts.append(f"{state['emotional_state']}")
        if state.get("body_state") and state["body_state"] != "clean":
            parts.append(f"{state['body_state']}")
        if state.get("carrying"):
            parts.append(f"holding {', '.join(state['carrying'][:2])}")

        char_blocks.append(", ".join(parts))

    prompt_parts = [". ".join(char_blocks)]

    # Relationship context (e.g., "tension between X and Y")
    if relationship_context:
        for key, val in relationship_context.items():
            if isinstance(val, str) and val:
                prompt_parts.append(val)

    prompt_parts.append(f"Scene: {motion_prompt}")

    return ". ".join(prompt_parts)
