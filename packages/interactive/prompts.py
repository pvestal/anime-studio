"""System prompt and scene generation templates for visual novel engine."""

SYSTEM_PROMPT = """\
You are an interactive visual novel game master. You create immersive, branching \
narrative scenes for an anime-style visual novel. Your responses must be valid JSON \
matching the schema exactly.

RULES:
- Every scene must have narration, an image_prompt, and 2-4 choices (unless it's an ending)
- Dialogue should feel natural to each character's personality
- Choices should meaningfully branch the story — no illusion of choice
- image_prompt must describe a single anime scene optimized for Stable Diffusion: \
  character appearance, pose, expression, setting, lighting, camera angle
- Do NOT include character names in image_prompt — describe their appearance instead
- Track relationships and story variables through story_effects
- Pacing: scenes 1-5 = opening/setup, 6-15 = rising action, 15-22 = climax, 22-30 = resolution
- End the story naturally between scene 20-30 with is_ending: true and ending_type

JSON SCHEMA:
{
  "narration": "Second-person present tense narration (2-4 sentences)",
  "image_prompt": "Detailed anime scene description for image generation",
  "dialogue": [{"character": "Name", "text": "Their words", "emotion": "neutral|happy|sad|angry|surprised|scared|romantic"}],
  "choices": [{"text": "What the player does/says", "tone": "neutral|bold|cautious|romantic|dramatic|humorous"}],
  "story_effects": [{"type": "relationship|variable|flag", "target": "name_or_key", "value": "..."}],
  "is_ending": false,
  "ending_type": null
}
"""


def build_scene_prompt(
    world_context: str,
    character_descriptions: list[dict],
    story_summary: str,
    relationships: dict[str, int],
    variables: dict[str, str | int | float | bool],
    last_choice: str | None,
    scene_number: int,
    max_scenes: int = 30,
) -> str:
    """Build the user prompt for generating the next scene."""
    chars_block = ""
    for c in character_descriptions:
        chars_block += f"\n- {c['name']}: {c.get('personality', 'No personality defined')}. "
        if c.get("description"):
            chars_block += f"{c['description']} "
        if c.get("appearance_summary"):
            chars_block += f"Appearance: {c['appearance_summary']}"

    rels_block = ""
    if relationships:
        rels_block = "\nRelationships: " + ", ".join(
            f"{k}: {v:+d}" for k, v in relationships.items()
        )

    vars_block = ""
    if variables:
        vars_block = "\nStory variables: " + ", ".join(
            f"{k}={v}" for k, v in variables.items()
        )

    pacing = _get_pacing_instruction(scene_number, max_scenes)

    choice_line = ""
    if last_choice:
        choice_line = f"\nThe player chose: \"{last_choice}\""

    return f"""\
WORLD: {world_context}

CHARACTERS:{chars_block}
{rels_block}{vars_block}

STORY SO FAR:
{story_summary or "This is the opening scene. Introduce the world and characters."}
{choice_line}

This is scene {scene_number} of ~{max_scenes}. {pacing}

Generate the next scene as JSON."""


def _get_pacing_instruction(scene_number: int, max_scenes: int) -> str:
    """Return pacing guidance based on story progress."""
    ratio = scene_number / max_scenes
    if ratio <= 0.17:
        return "PACING: Opening — establish the setting, introduce characters, hint at conflict."
    elif ratio <= 0.5:
        return "PACING: Rising action — deepen relationships, introduce complications, raise stakes."
    elif ratio <= 0.73:
        return "PACING: Climax — major confrontation or revelation. Tension at peak."
    elif ratio <= 0.9:
        return "PACING: Resolution — consequences unfold, relationships resolve."
    else:
        return "PACING: This should be the FINAL scene. Set is_ending: true and ending_type based on the story outcome."


def build_appearance_summary(appearance_data: dict | None, design_prompt: str) -> str:
    """Condense character appearance for the AI context (not for image gen)."""
    if not appearance_data:
        return design_prompt[:200] if design_prompt else ""
    parts = []
    if hair := appearance_data.get("hair"):
        parts.append(f"{hair.get('color', '')} {hair.get('style', '')} hair".strip())
    if eyes := appearance_data.get("eyes"):
        parts.append(f"{eyes.get('color', '')} eyes".strip())
    if clothing := appearance_data.get("clothing"):
        if outfit := clothing.get("default_outfit"):
            parts.append(outfit)
    if features := appearance_data.get("key_features"):
        parts.extend(features[:3])
    return ", ".join(parts) if parts else design_prompt[:200]
