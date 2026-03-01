"""Core game loop: Ollama calls, state management, story context."""
import json
import logging

import httpx

from packages.core.config import OLLAMA_URL
from packages.core.db import get_connection

from .models import SceneData, DialogueLine, StoryChoice, StoryEffect
from .prompts import SYSTEM_PROMPT, build_scene_prompt, build_appearance_summary
from .session_store import SessionState, store

logger = logging.getLogger(__name__)

OLLAMA_MODEL = "gemma3:12b"
MAX_SCENES = 30


async def load_project_context(project_id: int, character_slugs: list[str] | None = None) -> dict:
    """Load project + character data from DB for session initialization."""
    async with get_connection() as conn:
        project = await conn.fetchrow(
            """SELECT p.id, p.name, p.storyline, p.world_settings,
                      gs.checkpoint_model, gs.cfg_scale, gs.steps,
                      gs.sampler, gs.scheduler, gs.width, gs.height,
                      gs.positive_prompt_template, gs.negative_prompt
               FROM projects p
               LEFT JOIN generation_styles gs ON gs.name = p.default_style
               WHERE p.id = $1""",
            project_id,
        )
        if not project:
            raise ValueError(f"Project {project_id} not found")

        # Load characters
        query = """SELECT c.name, c.slug, c.design_prompt, c.description,
                          c.personality, c.background, c.role, c.character_role,
                          c.appearance_data, c.relationships
                   FROM characters c WHERE c.project_id = $1"""
        params = [project_id]
        if character_slugs:
            query += " AND c.slug = ANY($2)"
            params.append(character_slugs)
        characters = await conn.fetch(query, *params)

    char_list = []
    for c in characters:
        appearance_data = json.loads(c["appearance_data"]) if c["appearance_data"] else None
        char_list.append({
            "name": c["name"],
            "slug": c["slug"],
            "design_prompt": c["design_prompt"] or "",
            "description": c["description"] or "",
            "personality": c["personality"] or "",
            "background": c["background"] or "",
            "role": c["character_role"] or c["role"] or "",
            "appearance_data": appearance_data,
            "appearance_summary": build_appearance_summary(appearance_data, c["design_prompt"] or ""),
            "relationships": json.loads(c["relationships"]) if c["relationships"] else {},
        })

    world_settings = json.loads(project["world_settings"]) if project["world_settings"] else {}
    world_context = _build_world_context(project["name"], project["storyline"], world_settings)

    return {
        "project_name": project["name"],
        "characters": char_list,
        "character_slugs": [c["slug"] for c in char_list],
        "world_context": world_context,
        "checkpoint_model": project["checkpoint_model"] or "Counterfeit-V3.0_fp16.safetensors",
        "generation_params": {
            "cfg_scale": float(project["cfg_scale"] or 7.0),
            "steps": int(project["steps"] or 25),
            "sampler": project["sampler"] or "euler_ancestral",
            "scheduler": project["scheduler"] or "normal",
            "width": int(project["width"] or 512),
            "height": int(project["height"] or 768),
            "negative_prompt": project["negative_prompt"] or "worst quality, low quality, blurry, deformed",
        },
    }


def _build_world_context(name: str, storyline: str | None, world_settings: dict) -> str:
    """Assemble world context string from project data."""
    parts = [f"Story: {name}"]
    if storyline:
        parts.append(storyline[:500])
    if setting := world_settings.get("setting"):
        parts.append(f"Setting: {setting}")
    if time_period := world_settings.get("time_period"):
        parts.append(f"Time period: {time_period}")
    if tone := world_settings.get("tone"):
        parts.append(f"Tone: {tone}")
    if themes := world_settings.get("themes"):
        if isinstance(themes, list):
            parts.append(f"Themes: {', '.join(themes)}")
        else:
            parts.append(f"Themes: {themes}")
    return ". ".join(parts)


async def start_session(project_id: int, character_slugs: list[str] | None = None) -> tuple[SessionState, SceneData]:
    """Initialize a session and generate the opening scene."""
    ctx = await load_project_context(project_id, character_slugs)

    session = store.create(
        project_id=project_id,
        project_name=ctx["project_name"],
        character_slugs=ctx["character_slugs"],
        characters=ctx["characters"],
        world_context=ctx["world_context"],
        checkpoint_model=ctx["checkpoint_model"],
        generation_params=ctx["generation_params"],
    )

    # Initialize relationships at 0
    for c in ctx["characters"]:
        session.relationships[c["name"]] = 0

    # Generate opening scene
    scene = await generate_scene(session)
    return session, scene


async def generate_scene(session: SessionState, choice_text: str | None = None) -> SceneData:
    """Call Ollama to generate the next scene."""
    scene_number = len(session.scenes) + 1

    prompt = build_scene_prompt(
        world_context=session.world_context,
        character_descriptions=session.characters,
        story_summary=session.story_summary,
        relationships=session.relationships,
        variables=session.variables,
        last_choice=choice_text,
        scene_number=scene_number,
        max_scenes=MAX_SCENES,
    )

    raw = await _call_ollama(prompt)
    scene = _parse_scene_response(raw, scene_number - 1)

    # Apply story effects
    for effect in scene.story_effects:
        if effect.type == "relationship" and effect.target in session.relationships:
            try:
                session.relationships[effect.target] += int(effect.value)
            except (ValueError, TypeError):
                pass
        elif effect.type == "variable":
            session.variables[effect.target] = effect.value
        elif effect.type == "flag":
            session.variables[effect.target] = effect.value

    # Store scene in history
    scene_record = scene.model_dump()
    if choice_text:
        scene_record["chosen_text"] = choice_text
    session.scenes.append(scene_record)

    if scene.is_ending:
        session.is_ended = True

    session.touch()
    return scene


async def _call_ollama(user_prompt: str) -> dict:
    """Call Ollama and parse JSON response."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "format": "json",
                "stream": False,
                "options": {
                    "temperature": 0.8,
                    "num_predict": 4096,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()

    content = data.get("message", {}).get("content", "{}")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.error("Ollama returned invalid JSON: %s", content[:500])
        # Return a fallback scene
        return {
            "narration": "The story continues, though the details are hazy...",
            "image_prompt": "anime scene, mysterious atmosphere, soft lighting",
            "dialogue": [],
            "choices": [
                {"text": "Press forward", "tone": "bold"},
                {"text": "Take a moment to reflect", "tone": "cautious"},
            ],
            "story_effects": [],
            "is_ending": False,
            "ending_type": None,
        }


def _parse_scene_response(raw: dict, scene_index: int) -> SceneData:
    """Parse raw Ollama JSON into a validated SceneData model."""
    dialogue = []
    for d in raw.get("dialogue", []):
        if isinstance(d, dict) and d.get("text"):
            dialogue.append(DialogueLine(
                character=d.get("character", "???"),
                text=d["text"],
                emotion=d.get("emotion", "neutral"),
            ))

    choices = []
    if not raw.get("is_ending", False):
        for c in raw.get("choices", []):
            if isinstance(c, dict) and c.get("text"):
                choices.append(StoryChoice(
                    text=c["text"],
                    tone=c.get("tone", "neutral"),
                ))
        # Ensure at least 2 choices if not an ending
        if len(choices) < 2:
            choices = [
                StoryChoice(text="Continue forward", tone="neutral"),
                StoryChoice(text="Consider your options", tone="cautious"),
            ]

    effects = []
    for e in raw.get("story_effects", []):
        if isinstance(e, dict) and e.get("type") and e.get("target"):
            effects.append(StoryEffect(
                type=e["type"],
                target=e["target"],
                value=e.get("value", ""),
            ))

    return SceneData(
        scene_index=scene_index,
        narration=raw.get("narration", "The scene unfolds before you..."),
        image_prompt=raw.get("image_prompt", "anime scene, detailed background"),
        dialogue=dialogue,
        choices=choices,
        story_effects=effects,
        is_ending=raw.get("is_ending", False),
        ending_type=raw.get("ending_type"),
    )
