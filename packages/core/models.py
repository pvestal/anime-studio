"""Pydantic models — all request/response schemas for the API."""

from pydantic import BaseModel
from typing import Dict, List, Optional


class ImageApproval(BaseModel):
    character_name: str
    image_name: str
    approved: bool
    feedback: Optional[str] = None
    edited_prompt: Optional[str] = None


class ApprovalRequest(BaseModel):
    character_name: str
    character_slug: Optional[str] = None
    image_name: str
    approved: bool
    feedback: Optional[str] = None
    edited_prompt: Optional[str] = None


class ReassignRequest(BaseModel):
    character_slug: str
    image_name: str
    target_character_slug: str


class CharacterCreate(BaseModel):
    name: str
    project_name: str
    description: Optional[str] = None
    design_prompt: Optional[str] = None
    reference_images: Optional[List[str]] = None


class DatasetImageCreate(BaseModel):
    source_url: Optional[str] = None
    prompt: Optional[str] = None
    tags: Optional[List[str]] = None


class TrainingRequest(BaseModel):
    character_name: str
    epochs: Optional[int] = 20
    learning_rate: Optional[float] = 1e-4
    resolution: Optional[int] = 512
    lora_rank: Optional[int] = None  # Auto-set by router: 64 for SDXL, 32 for SD1.5


class DatasetStatus(BaseModel):
    character_name: str
    total_images: int
    approved_images: int
    pending_images: int
    rejected_images: int


class GenerateRequest(BaseModel):
    generation_type: str = "image"  # "image" or "video"
    prompt_override: Optional[str] = None
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None
    style_override: Optional[str] = None  # e.g. "pony_nsfw_xl" to override project default


class FramePackRequest(BaseModel):
    character_slug: str
    prompt_override: Optional[str] = None
    negative_prompt: Optional[str] = None
    image_path: Optional[str] = None  # Reference image filename in ComfyUI/input/
    seconds: float = 3.0
    steps: int = 25
    use_f1: bool = False
    seed: Optional[int] = None
    gpu_memory_preservation: float = 6.0


class EchoChatRequest(BaseModel):
    message: str
    character_slug: Optional[str] = None


class EchoEnhanceRequest(BaseModel):
    prompt: str
    character_slug: Optional[str] = None


class NarrateRequest(BaseModel):
    context_type: str  # storyline | description | positive_template | negative_template | design_prompt | prompt_override | concept
    project_name: Optional[str] = None
    project_genre: Optional[str] = None
    project_description: Optional[str] = None
    storyline_title: Optional[str] = None
    storyline_summary: Optional[str] = None
    storyline_theme: Optional[str] = None
    checkpoint_model: Optional[str] = None
    positive_prompt_template: Optional[str] = None
    negative_prompt_template: Optional[str] = None
    character_name: Optional[str] = None
    character_slug: Optional[str] = None
    design_prompt: Optional[str] = None
    current_value: Optional[str] = None
    concept_description: Optional[str] = None


class VisionReviewRequest(BaseModel):
    character_slug: Optional[str] = None
    project_name: Optional[str] = None
    update_captions: bool = False
    max_images: int = 50
    auto_reject_threshold: float = 0.4
    auto_approve_threshold: float = 0.8
    regenerate: bool = True
    model: Optional[str] = None  # override VISION_MODEL
    include_approved: bool = False


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    genre: Optional[str] = None
    checkpoint_model: str
    cfg_scale: Optional[float] = 7.0
    steps: Optional[int] = 25
    sampler: Optional[str] = "DPM++ 2M Karras"
    width: Optional[int] = 768
    height: Optional[int] = 768
    positive_prompt_template: Optional[str] = "masterpiece, best quality, highly detailed"
    negative_prompt_template: Optional[str] = "worst quality, low quality, blurry, deformed"


class StorylineUpsert(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    theme: Optional[str] = None
    genre: Optional[str] = None
    target_audience: Optional[str] = None
    tone: Optional[str] = None
    themes: Optional[List[str]] = None
    humor_style: Optional[str] = None
    story_arcs: Optional[List[str]] = None


class WorldSettingsUpsert(BaseModel):
    style_preamble: Optional[str] = None
    art_style: Optional[str] = None
    aesthetic: Optional[str] = None
    color_palette: Optional[Dict] = None
    cinematography: Optional[Dict] = None
    world_location: Optional[Dict] = None
    time_period: Optional[str] = None
    production_notes: Optional[str] = None
    known_issues: Optional[List[str]] = None
    negative_prompt_guidance: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    genre: Optional[str] = None
    premise: Optional[str] = None
    content_rating: Optional[str] = None


class StyleUpdate(BaseModel):
    checkpoint_model: Optional[str] = None
    cfg_scale: Optional[float] = None
    steps: Optional[int] = None
    sampler: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    positive_prompt_template: Optional[str] = None
    negative_prompt_template: Optional[str] = None
    reason: Optional[str] = None


class BulkRejectRequest(BaseModel):
    character_slug: Optional[str] = None
    project_name: Optional[str] = None
    criteria: str  # "solo_false", "no_vision_review", "low_quality"
    quality_threshold: Optional[float] = 0.4
    dry_run: bool = True


# --- Scene Builder Models ---

class SceneCreateRequest(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    time_of_day: Optional[str] = None
    weather: Optional[str] = None
    mood: Optional[str] = None
    target_duration_seconds: int = 30


class ShotCreateRequest(BaseModel):
    shot_number: int
    source_image_path: str
    shot_type: str = "medium"
    camera_angle: str = "eye-level"
    duration_seconds: float = 3.0
    motion_prompt: str
    characters_present: List[str] = []
    seed: Optional[int] = None
    steps: Optional[int] = None
    use_f1: bool = False
    dialogue_text: Optional[str] = None
    dialogue_character_slug: Optional[str] = None
    transition_type: str = "dissolve"  # dissolve, fade, fadeblack, wipeleft, slideup, etc.
    transition_duration: float = 0.3  # seconds of crossfade overlap


class ShotUpdateRequest(BaseModel):
    shot_number: Optional[int] = None
    source_image_path: Optional[str] = None
    shot_type: Optional[str] = None
    camera_angle: Optional[str] = None
    duration_seconds: Optional[float] = None
    motion_prompt: Optional[str] = None
    characters_present: Optional[List[str]] = None
    seed: Optional[int] = None
    steps: Optional[int] = None
    use_f1: Optional[bool] = None
    dialogue_text: Optional[str] = None
    dialogue_character_slug: Optional[str] = None
    transition_type: Optional[str] = None
    transition_duration: Optional[float] = None


class SceneUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    time_of_day: Optional[str] = None
    weather: Optional[str] = None
    mood: Optional[str] = None
    target_duration_seconds: Optional[int] = None


class SceneAudioRequest(BaseModel):
    track_id: str
    preview_url: str
    track_name: str
    track_artist: str
    fade_in: Optional[float] = 1.0
    fade_out: Optional[float] = 2.0
    start_offset: Optional[float] = 0


# --- Episode Assembly Models ---

class EpisodeCreateRequest(BaseModel):
    project_id: int
    episode_number: int
    title: str
    description: Optional[str] = None
    story_arc: Optional[str] = None


class EpisodeUpdateRequest(BaseModel):
    episode_number: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    story_arc: Optional[str] = None


class EpisodeAddSceneRequest(BaseModel):
    scene_id: str
    position: int
    transition: str = "cut"


class EpisodeReorderRequest(BaseModel):
    scene_order: List[str]  # List of scene_ids in desired order


# --- Voice Pipeline Models ---

class VoiceDiarizeRequest(BaseModel):
    project_name: str

class VoiceSpeakerAssignRequest(BaseModel):
    character_id: Optional[int] = None
    character_slug: str

class VoiceSampleApprovalRequest(BaseModel):
    character_slug: str
    filename: str
    approved: bool
    feedback: Optional[str] = None
    transcript: Optional[str] = None
    rejection_categories: Optional[List[str]] = None

class VoiceBatchApprovalRequest(BaseModel):
    character_slug: str
    filenames: List[str]
    approved: bool
    feedback: Optional[str] = None

class VoiceTrainRequest(BaseModel):
    character_slug: str
    character_name: Optional[str] = None
    project_name: Optional[str] = None
    epochs: Optional[int] = None

class VoiceSynthesizeRequest(BaseModel):
    character_slug: str
    text: str
    engine: Optional[str] = None  # 'rvc', 'sovits', 'edge-tts', or None for auto

class VoiceSceneDialogueRequest(BaseModel):
    dialogue_list: Optional[List[Dict]] = None
    description: Optional[str] = None
    characters: Optional[List[str]] = None
    pause_seconds: Optional[float] = 0.5


# --- Music Generation Models ---

class MusicGenerateRequest(BaseModel):
    scene_id: Optional[str] = None
    mood: str = "ambient"
    genre: str = "orchestral"
    duration: float = 30.0
    instrumental: bool = True
    bpm: Optional[int] = None
    key: Optional[str] = None
    seed: Optional[int] = None
    caption: Optional[str] = None  # free-form override
