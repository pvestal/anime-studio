"""Pydantic request/response models for interactive visual novel."""
from pydantic import BaseModel


class StartSessionRequest(BaseModel):
    project_id: int
    character_slugs: list[str] | None = None


class ChoiceRequest(BaseModel):
    choice_index: int


class DialogueLine(BaseModel):
    character: str
    text: str
    emotion: str = "neutral"


class StoryChoice(BaseModel):
    text: str
    tone: str = "neutral"  # neutral, bold, cautious, romantic, dramatic, humorous


class StoryEffect(BaseModel):
    type: str  # relationship, variable, flag
    target: str
    value: str | int | float | bool


class SceneData(BaseModel):
    scene_index: int
    narration: str
    image_prompt: str
    dialogue: list[DialogueLine] = []
    choices: list[StoryChoice] = []
    story_effects: list[StoryEffect] = []
    is_ending: bool = False
    ending_type: str | None = None  # good, bad, neutral, secret


class SessionInfo(BaseModel):
    session_id: str
    project_id: int
    project_name: str
    scene_count: int
    current_scene_index: int
    is_ended: bool


class ImageStatus(BaseModel):
    status: str  # pending, generating, ready, failed
    progress: float = 0.0
    url: str | None = None
