"""Pydantic models for narrative state API requests/responses."""

from pydantic import BaseModel


class CharacterStateUpdate(BaseModel):
    """Manual override for a character's state in a scene."""
    clothing: str | None = None
    hair_state: str | None = None
    injuries: list[dict] | None = None
    accessories: list[str] | None = None
    body_state: str | None = None
    emotional_state: str | None = None
    energy_level: str | None = None
    relationship_context: dict | None = None
    location_in_scene: str | None = None
    carrying: list[str] | None = None


class CharacterSceneState(BaseModel):
    """Full character state for a scene."""
    scene_id: str
    character_slug: str
    clothing: str | None = None
    hair_state: str | None = None
    injuries: list[dict] = []
    accessories: list[str] = []
    body_state: str = "clean"
    emotional_state: str = "calm"
    energy_level: str = "normal"
    relationship_context: dict = {}
    location_in_scene: str | None = None
    carrying: list[str] = []
    state_source: str = "auto"
    version: int = 1
