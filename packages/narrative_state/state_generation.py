"""Targeted image generation — create images matching specific narrative states.

When the recommender can't find images matching a character's state (e.g., "Rina in armor"),
this module generates targeted images with state-augmented prompts.
"""

import logging
from typing import Any

from packages.core.db import connect_direct
from packages.core.config import BASE_PATH

logger = logging.getLogger(__name__)


def build_state_augmented_prompt(
    design_prompt: str,
    state: dict[str, Any],
    scene_context: dict[str, Any] | None = None,
) -> str:
    """Inject clothing/expression/body_state into a character's design prompt.

    Args:
        design_prompt: Base character design prompt.
        state: Character state dict from character_scene_state.
        scene_context: Optional scene info (location, mood, time_of_day).

    Returns:
        Augmented prompt string.
    """
    parts = [design_prompt.strip().rstrip(",. ")]

    # Clothing override (most impactful visual change)
    if state.get("clothing"):
        parts.append(f"wearing {state['clothing']}")

    # Hair state
    if state.get("hair_state"):
        parts.append(f"{state['hair_state']} hair")

    # Emotional expression
    if state.get("emotional_state") and state["emotional_state"] != "calm":
        parts.append(f"{state['emotional_state']} expression")

    # Body state
    if state.get("body_state") and state["body_state"] != "clean":
        parts.append(f"{state['body_state']} appearance")

    # Energy level (affects posture)
    if state.get("energy_level") and state["energy_level"] != "normal":
        energy_postures = {
            "exhausted": "slumped posture",
            "tired": "slightly drooping",
            "energized": "alert posture",
            "hyperactive": "dynamic energetic pose",
        }
        posture = energy_postures.get(state["energy_level"])
        if posture:
            parts.append(posture)

    # Injuries
    injuries = state.get("injuries", [])
    for inj in injuries[:2]:  # Max 2 injuries in prompt to avoid clutter
        severity = inj.get("severity", "")
        location = inj.get("location", "")
        inj_type = inj.get("type", "wound")
        if severity and location:
            parts.append(f"{severity} {inj_type} on {location}")

    # Accessories
    accessories = state.get("accessories", [])
    if accessories:
        parts.append(f"with {', '.join(accessories[:3])}")

    # Carrying items
    carrying = state.get("carrying", [])
    if carrying:
        parts.append(f"holding {', '.join(carrying[:2])}")

    # Scene context
    if scene_context:
        if scene_context.get("location"):
            parts.append(f"in {scene_context['location']}")
        if scene_context.get("time_of_day"):
            parts.append(f"{scene_context['time_of_day']} lighting")
        if scene_context.get("mood"):
            parts.append(f"{scene_context['mood']} atmosphere")

    return ", ".join(parts)


def build_state_negative_prompt(
    state: dict[str, Any],
    base_negative: str = "low quality, blurry, distorted, watermark",
) -> str:
    """Build negative prompt additions based on state.

    E.g., if clothing is "armor", add "casual clothes, school uniform" to negative.
    """
    negatives = [base_negative]

    # If specific clothing, negate common defaults
    if state.get("clothing"):
        clothing_lower = state["clothing"].lower()
        if "armor" in clothing_lower or "battle" in clothing_lower:
            negatives.append("casual clothes, school uniform, modern clothing")
        elif "formal" in clothing_lower or "suit" in clothing_lower:
            negatives.append("casual clothes, armor, sportswear")
        elif "swimsuit" in clothing_lower or "bikini" in clothing_lower:
            negatives.append("fully clothed, armor, school uniform")

    # Body state negations
    body_state = state.get("body_state", "clean")
    if body_state == "clean":
        negatives.append("dirty, bloody, stained")
    elif body_state in ("bloody", "stained"):
        negatives.append("clean, pristine")

    return ", ".join(negatives)


async def generate_state_matching_image(
    character_slug: str,
    project_id: int,
    target_state: dict[str, Any],
    scene_context: dict[str, Any] | None = None,
) -> dict | None:
    """Generate an image matching a specific narrative state using existing ComfyUI pipeline.

    Returns generation result dict or None on failure.
    """
    conn = await connect_direct()
    try:
        # Get character's design prompt
        char_row = await conn.fetchrow(
            "SELECT name, design_prompt FROM characters "
            "WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), "
            "'[^a-z0-9_-]', '', 'g') = $1",
            character_slug,
        )
        if not char_row or not char_row["design_prompt"]:
            logger.warning(f"No design_prompt for {character_slug}")
            return None

        # Get project's generation style
        style_row = await conn.fetchrow("""
            SELECT gs.* FROM projects p
            JOIN generation_styles gs ON p.default_style = gs.style_name
            WHERE p.id = $1
        """, project_id)
        if not style_row:
            logger.warning(f"No generation style for project {project_id}")
            return None

        # Build augmented prompt
        augmented_prompt = build_state_augmented_prompt(
            char_row["design_prompt"], target_state, scene_context
        )
        negative_prompt = build_state_negative_prompt(target_state)

        logger.info(
            f"Targeted generation for {character_slug}: "
            f"state={target_state.get('clothing', '?')}, "
            f"emotion={target_state.get('emotional_state', '?')}"
        )

        # Use existing ComfyUI generation pipeline
        from packages.visual_pipeline.comfyui import submit_generation
        result = await submit_generation(
            character_slug=character_slug,
            prompt=augmented_prompt,
            negative_prompt=negative_prompt,
            checkpoint_model=style_row["checkpoint_model"],
            cfg_scale=style_row["cfg_scale"],
            steps=style_row["steps"],
            sampler=style_row["sampler"],
            width=style_row["width"],
            height=style_row["height"],
        )

        # Auto-tag the generated image if successful
        if result and result.get("image_path"):
            try:
                from .image_tagger import tag_image_visual_properties
                await tag_image_visual_properties(
                    result["image_path"],
                    character_slug,
                    char_row["design_prompt"],
                )
            except Exception as e:
                logger.debug(f"Auto-tag after state generation failed: {e}")

        return result
    except Exception as e:
        logger.error(f"State-matching generation failed for {character_slug}: {e}")
        return None
    finally:
        await conn.close()


async def fill_state_gaps(
    project_id: int,
    scene_id: str | None = None,
    dry_run: bool = True,
) -> dict:
    """Find shots where no tagged images match the required state and queue targeted generation.

    Args:
        project_id: Project to scan.
        scene_id: Optional specific scene (default: all scenes).
        dry_run: If True, only report gaps without generating.

    Returns summary of gaps found and actions taken.
    """
    conn = await connect_direct()
    try:
        # Get scenes with states
        if scene_id:
            scenes = await conn.fetch(
                "SELECT id, title, description, location, mood, time_of_day "
                "FROM scenes WHERE id = $1", scene_id
            )
        else:
            scenes = await conn.fetch(
                "SELECT id, title, description, location, mood, time_of_day "
                "FROM scenes WHERE project_id = $1 ORDER BY scene_number",
                project_id,
            )

        gaps = []
        generated = 0

        for scene in scenes:
            sid = scene["id"]

            # Get character states for this scene
            states = await conn.fetch(
                "SELECT * FROM character_scene_state WHERE scene_id = $1", sid
            )
            if not states:
                continue

            for state_row in states:
                slug = state_row["character_slug"]
                target_state = {
                    "clothing": state_row["clothing"],
                    "hair_state": state_row["hair_state"],
                    "emotional_state": state_row["emotional_state"],
                    "body_state": state_row["body_state"],
                }

                # Check if we have tagged images matching this state
                from .image_tagger import get_image_tags
                from ..scene_generation.image_recommender import score_state_match

                tags = await get_image_tags(slug)
                if not tags:
                    gaps.append({
                        "scene_id": str(sid),
                        "scene_title": scene["title"],
                        "character_slug": slug,
                        "reason": "no_tagged_images",
                        "target_state": target_state,
                    })
                    continue

                # Find best match
                best_score = max(
                    score_state_match(tag, target_state)
                    for tag in tags.values()
                )

                if best_score < 0.5:
                    gap = {
                        "scene_id": str(sid),
                        "scene_title": scene["title"],
                        "character_slug": slug,
                        "reason": "low_state_match",
                        "best_match_score": round(best_score, 3),
                        "target_state": target_state,
                    }
                    gaps.append(gap)

                    if not dry_run:
                        scene_context = {
                            "location": scene["location"],
                            "mood": scene["mood"],
                            "time_of_day": scene["time_of_day"],
                        }
                        result = await generate_state_matching_image(
                            slug, project_id, target_state, scene_context
                        )
                        if result:
                            generated += 1
                            gap["generated"] = True

        return {
            "project_id": project_id,
            "scenes_scanned": len(scenes),
            "gaps_found": len(gaps),
            "images_generated": generated,
            "dry_run": dry_run,
            "gaps": gaps,
        }
    finally:
        await conn.close()
