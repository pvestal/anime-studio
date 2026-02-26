"""Story → Scenes: Auto-generate scene breakdowns from storyline using Ollama."""

import json
import logging

import httpx

from packages.core.config import OLLAMA_URL
from packages.core.db import connect_direct

logger = logging.getLogger(__name__)

STORY_TO_SCENES_PROMPT = """You are a professional anime scene planner. Given a story summary, world context, and character list, break the story into concrete production scenes.

For each scene, provide:
- title: Short scene title (3-6 words)
- description: What happens in this scene (1-2 sentences)
- location: Where the scene takes place
- time_of_day: dawn/morning/midday/afternoon/sunset/evening/night
- mood: Emotional tone (tense, peaceful, exciting, melancholic, etc.)
- characters: List of character names present
- suggested_shots: Array of shot descriptions, each with:
  - shot_type: establishing/wide/medium/close-up/action
  - description: What this shot shows
  - motion_prompt: FramePack motion description (what moves/happens in the shot)
  - duration_seconds: 2-5
  - dialogue_character: Character name who speaks in this shot (null if no dialogue)
  - dialogue_text: What the character says (null if no dialogue)

Create 3-8 scenes that tell the story naturally. Each scene should have 2-5 shots.
Include dialogue where it fits the story — not every shot needs dialogue.

Respond with ONLY valid JSON array. No markdown, no explanation.

Story Context:
{story_context}

Characters:
{character_list}

World Setting:
{world_context}"""

EPISODE_TO_SCENES_PROMPT = """You are a professional anime scene planner. You are planning scenes for Episode {episode_number}: "{episode_title}".

Episode Synopsis:
{episode_synopsis}

Background (overall series story):
{story_context}

Existing scenes in this project (for continuity — do NOT repeat these):
{existing_scenes}

Characters:
{character_list}

World Setting:
{world_context}

For each scene, provide:
- title: Short scene title (3-6 words)
- description: What happens in this scene (1-2 sentences)
- location: Where the scene takes place
- time_of_day: dawn/morning/midday/afternoon/sunset/evening/night
- mood: Emotional tone (tense, peaceful, exciting, melancholic, etc.)
- characters: List of character names present
- suggested_shots: Array of shot descriptions, each with:
  - shot_type: establishing/wide/medium/close-up/action
  - description: What this shot shows
  - motion_prompt: FramePack motion description (what moves/happens in the shot)
  - duration_seconds: 2-5
  - dialogue_character: Character name who speaks in this shot (null if no dialogue)
  - dialogue_text: What the character says (null if no dialogue)

Create 3-8 scenes that tell THIS EPISODE's story. Each scene should have 2-5 shots.
Include dialogue where it fits the story — not every shot needs dialogue.

Respond with ONLY valid JSON array. No markdown, no explanation."""


async def _get_project_context(conn, project_id: int) -> tuple[str, str, str]:
    """Fetch project storyline, characters, and world context. Returns (story_context, char_list, world_context)."""
    project = await conn.fetchrow(
        "SELECT p.name, p.description, p.genre, "
        "s.title, s.summary, s.theme, s.tone, s.themes, s.story_arcs "
        "FROM projects p "
        "LEFT JOIN storylines s ON s.project_id = p.id "
        "WHERE p.id = $1", project_id)

    if not project:
        raise ValueError(f"Project {project_id} not found")

    # Get world settings
    world = await conn.fetchrow(
        "SELECT * FROM world_settings WHERE project_id = $1", project_id)

    # Get characters
    chars = await conn.fetch(
        "SELECT name, design_prompt FROM characters WHERE project_id = $1", project_id)

    # Build story context
    story_parts = []
    if project["summary"]:
        story_parts.append(f"Summary: {project['summary']}")
    if project["theme"]:
        story_parts.append(f"Theme: {project['theme']}")
    if project["tone"]:
        story_parts.append(f"Tone: {project['tone']}")
    if project["genre"]:
        story_parts.append(f"Genre: {project['genre']}")
    if project["description"]:
        story_parts.append(f"Project: {project['description']}")
    arcs = project.get("story_arcs")
    if arcs:
        arcs_list = json.loads(arcs) if isinstance(arcs, str) else arcs
        if arcs_list:
            story_parts.append(f"Story Arcs: {', '.join(str(a) for a in arcs_list)}")
    story_context = "\n".join(story_parts) if story_parts else "No storyline defined yet."

    # Build character list
    char_list = "\n".join(
        f"- {c['name']}: {c['design_prompt'] or 'no description'}"
        for c in chars
    ) if chars else "No characters defined."

    # Build world context
    world_parts = []
    if world:
        if world.get("art_style"):
            world_parts.append(f"Art style: {world['art_style']}")
        if world.get("aesthetic"):
            world_parts.append(f"Aesthetic: {world['aesthetic']}")
        loc = world.get("world_location")
        if loc:
            loc_data = json.loads(loc) if isinstance(loc, str) else loc
            if isinstance(loc_data, dict):
                world_parts.append(f"Location: {loc_data.get('primary', '')} — {loc_data.get('atmosphere', '')}")
        if world.get("time_period"):
            world_parts.append(f"Time period: {world['time_period']}")
    world_context = "\n".join(world_parts) if world_parts else "No world settings defined."

    return story_context, char_list, world_context


def _extract_json_scenes(raw_text: str) -> list[dict]:
    """Parse and validate scene JSON from Ollama response."""
    if "```" in raw_text:
        parts = raw_text.split("```")
        for part in parts:
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("["):
                raw_text = cleaned
                break

    scenes = json.loads(raw_text)
    if not isinstance(scenes, list):
        raise ValueError("Expected JSON array of scenes")

    for i, scene in enumerate(scenes):
        scene.setdefault("title", f"Scene {i + 1}")
        scene.setdefault("description", "")
        scene.setdefault("location", "")
        scene.setdefault("time_of_day", "")
        scene.setdefault("mood", "")
        scene.setdefault("characters", [])
        scene.setdefault("suggested_shots", [])
        for shot in scene["suggested_shots"]:
            shot.setdefault("shot_type", "medium")
            shot.setdefault("description", "")
            shot.setdefault("motion_prompt", shot.get("description", ""))
            shot.setdefault("duration_seconds", 3)
            shot.setdefault("dialogue_character", None)
            shot.setdefault("dialogue_text", None)

    return scenes


async def _call_ollama(prompt: str) -> str:
    """Call Ollama and return the raw response text."""
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": "gemma3:12b",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 4096},
            },
        )
        resp.raise_for_status()
        result = resp.json()
    return result.get("response", "").strip()


async def generate_scenes_from_story(project_id: int, episode_id: str | None = None) -> list[dict]:
    """Query the DB for storyline + world + characters, then use Ollama to generate scenes.

    If episode_id is provided, generates scenes specifically for that episode using
    the episode's synopsis and story_arc as primary context.
    """
    conn = await connect_direct()
    try:
        story_context, char_list, world_context = await _get_project_context(conn, project_id)

        if episode_id:
            return await _generate_for_episode(
                conn, project_id, episode_id, story_context, char_list, world_context)

        prompt = STORY_TO_SCENES_PROMPT.format(
            story_context=story_context,
            character_list=char_list,
            world_context=world_context,
        )
        raw_text = await _call_ollama(prompt)
        scenes = _extract_json_scenes(raw_text)
        logger.info(f"Generated {len(scenes)} scenes from storyline for project {project_id}")
        return scenes
    finally:
        await conn.close()


async def _generate_for_episode(
    conn, project_id: int, episode_id: str,
    story_context: str, char_list: str, world_context: str,
) -> list[dict]:
    """Generate scenes for a specific episode."""
    import uuid
    ep_uuid = uuid.UUID(episode_id)

    episode = await conn.fetchrow(
        "SELECT episode_number, title, description, story_arc "
        "FROM episodes WHERE id = $1 AND project_id = $2",
        ep_uuid, project_id)
    if not episode:
        raise ValueError(f"Episode {episode_id} not found in project {project_id}")

    # Build episode synopsis from description + story_arc
    ep_parts = []
    if episode["description"]:
        ep_parts.append(episode["description"])
    if episode["story_arc"]:
        ep_parts.append(f"Story Arc: {episode['story_arc']}")
    episode_synopsis = "\n".join(ep_parts) if ep_parts else "No episode synopsis defined."

    # Get existing scenes for continuity context
    existing = await conn.fetch(
        "SELECT scene_number, title FROM scenes WHERE project_id = $1 "
        "ORDER BY scene_number NULLS LAST, created_at",
        project_id)
    if existing:
        existing_scenes = "\n".join(
            f"- Scene {r['scene_number']}: {r['title']}" for r in existing)
    else:
        existing_scenes = "None yet."

    prompt = EPISODE_TO_SCENES_PROMPT.format(
        episode_number=episode["episode_number"],
        episode_title=episode["title"],
        episode_synopsis=episode_synopsis,
        story_context=story_context,
        existing_scenes=existing_scenes,
        character_list=char_list,
        world_context=world_context,
    )
    raw_text = await _call_ollama(prompt)
    scenes = _extract_json_scenes(raw_text)
    logger.info(
        f"Generated {len(scenes)} scenes for episode {episode['episode_number']} "
        f"({episode['title']}) in project {project_id}")
    return scenes
