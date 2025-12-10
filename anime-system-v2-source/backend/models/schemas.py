"""
Tower Anime Production System - Pydantic Models
Extends existing models with consistency, quality, and video production support
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field


# === Enums ===

class JobType(str, Enum):
    STILL_IMAGE = "still_image"
    ANIMATION_LOOP = "animation_loop"
    FULL_VIDEO = "full_video"
    CHARACTER_SHEET = "character_sheet"


class JobStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    QUALITY_CHECK = "quality_check"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class VariationType(str, Enum):
    OUTFIT = "outfit"
    EXPRESSION = "expression"
    POSE = "pose"
    AGE_VARIANT = "age_variant"


class Phase(str, Enum):
    PHASE_1_STILL = "phase_1_still"
    PHASE_2_LOOP = "phase_2_loop"
    PHASE_3_VIDEO = "phase_3_video"


# === Character Models ===

class CharacterAttributeCreate(BaseModel):
    attribute_type: str  # hair_color, eye_color, outfit, etc.
    attribute_value: str
    prompt_tokens: Optional[List[str]] = []
    priority: int = 0


class CharacterAttributeResponse(CharacterAttributeCreate):
    id: UUID
    character_id: UUID
    created_at: datetime


class CharacterVariationCreate(BaseModel):
    variation_name: str
    variation_type: VariationType
    prompt_modifiers: Dict[str, Any] = {}
    reference_image_path: Optional[str] = None


class CharacterVariationResponse(CharacterVariationCreate):
    id: UUID
    character_id: UUID
    created_at: datetime


class CharacterConsistencyUpdate(BaseModel):
    """Update character with consistency anchors"""
    color_palette: Optional[Dict[str, List[str]]] = None  # {"primary": ["#hex"], "accent": ["#hex"]}
    base_prompt: Optional[str] = None
    negative_tokens: Optional[List[str]] = None
    lora_model_path: Optional[str] = None


class CharacterEmbeddingRequest(BaseModel):
    """Request to compute/store face embedding"""
    reference_image_path: str
    force_recompute: bool = False


class CharacterEmbeddingResponse(BaseModel):
    character_id: UUID
    embedding_stored: bool
    embedding_dimensions: int
    similarity_baseline: Optional[float] = None


class ConsistencyCheckRequest(BaseModel):
    """Check generated image against character reference"""
    image_path: str
    threshold: float = 0.70


class ConsistencyCheckResponse(BaseModel):
    character_id: UUID
    similarity_score: float
    passes_threshold: bool
    threshold_used: float


# === Generation Models ===

class LoRAConfig(BaseModel):
    name: str
    path: str
    weight: float = 0.8


class ControlNetConfig(BaseModel):
    name: str
    model: str
    weight: float = 1.0
    preprocessor: Optional[str] = None


class IPAdapterConfig(BaseModel):
    reference_image_path: str
    weight: float = 0.8
    noise: float = 0.0


class GenerationParams(BaseModel):
    """Full generation parameters for reproducibility"""
    positive_prompt: str
    negative_prompt: str = ""
    seed: int
    subseed: Optional[int] = None
    model_name: str
    model_hash: Optional[str] = None
    vae_name: Optional[str] = None
    sampler_name: str = "euler"
    scheduler: str = "normal"
    steps: int = 20
    cfg_scale: float = 7.0
    width: int = 512
    height: int = 768
    frame_count: int = 1
    fps: int = 24
    lora_models: List[LoRAConfig] = []
    controlnet_models: List[ControlNetConfig] = []
    ipadapter_refs: List[IPAdapterConfig] = []


class GenerationParamsResponse(GenerationParams):
    id: UUID
    job_id: UUID
    created_at: datetime


# === Quality Models ===

class QualityThresholds(BaseModel):
    """Quality gates by phase"""
    face_similarity: float = 0.70
    aesthetic_score: float = 5.5
    temporal_lpips: float = 0.15  # Lower is better
    motion_smoothness: float = 0.95
    subject_consistency: float = 0.90


class QualityScores(BaseModel):
    """Measured quality metrics"""
    face_similarity: Optional[float] = None
    aesthetic_score: Optional[float] = None
    temporal_lpips: Optional[float] = None  # Video only
    motion_smoothness: Optional[float] = None  # Video only
    subject_consistency: Optional[float] = None  # Video only
    passes_threshold: bool = False


class QualityScoresResponse(QualityScores):
    id: UUID
    job_id: UUID
    evaluated_at: datetime


class QualityEvaluationRequest(BaseModel):
    """Request quality evaluation for a job output"""
    job_id: UUID
    output_path: str
    character_ids: List[UUID] = []  # For face consistency check
    thresholds: Optional[QualityThresholds] = None


# === Job Models (Extended) ===

class GenerateRequest(BaseModel):
    """Extended generation request"""
    project_id: UUID
    character_ids: List[UUID] = []
    job_type: JobType = JobType.STILL_IMAGE
    prompt: str
    negative_prompt: str = ""
    
    # Generation params
    width: int = 512
    height: int = 768
    steps: int = 20
    cfg_scale: float = 7.0
    seed: Optional[int] = None  # Auto-generate if not provided
    
    # Video params (Phase 2+)
    frame_count: int = 1
    fps: int = 24
    
    # Consistency options
    use_character_loras: bool = True
    use_ipadapter: bool = True
    ipadapter_weight: float = 0.8
    
    # Quality options
    save_params: bool = True  # Store for reproducibility
    auto_quality_check: bool = True
    quality_thresholds: Optional[QualityThresholds] = None
    
    # Pose control
    pose_reference_path: Optional[str] = None
    pose_weight: float = 1.0


class GenerateResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    generation_params_id: Optional[UUID] = None
    seed_used: int
    estimated_time_seconds: float
    websocket_url: str


class JobProgressResponse(BaseModel):
    """Real-time job progress"""
    job_id: UUID
    status: JobStatus
    progress_percent: float
    current_step: Optional[int] = None
    total_steps: Optional[int] = None
    current_frame: Optional[int] = None
    total_frames: Optional[int] = None
    eta_seconds: Optional[float] = None
    quality_scores: Optional[QualityScores] = None
    output_path: Optional[str] = None
    error_message: Optional[str] = None


class ReproduceRequest(BaseModel):
    """Reproduce a previous generation"""
    original_job_id: UUID
    modifications: Optional[Dict[str, Any]] = None  # Override specific params


# === Story Bible Models ===

class StoryBibleCreate(BaseModel):
    project_id: UUID
    art_style: str
    color_palette: Dict[str, List[str]] = {}
    line_weight: str = "medium"
    shading_style: str = "cel-shaded"
    setting_description: str = ""
    time_period: str = ""
    mood_keywords: List[str] = []
    narrative_themes: List[str] = []
    global_seed: Optional[int] = None


class StoryBibleUpdate(BaseModel):
    art_style: Optional[str] = None
    color_palette: Optional[Dict[str, List[str]]] = None
    line_weight: Optional[str] = None
    shading_style: Optional[str] = None
    setting_description: Optional[str] = None
    time_period: Optional[str] = None
    mood_keywords: Optional[List[str]] = None
    narrative_themes: Optional[List[str]] = None
    global_seed: Optional[int] = None


class StoryBibleResponse(StoryBibleCreate):
    id: UUID
    version: str
    created_at: datetime
    updated_at: datetime


# === Echo Brain Integration Models ===

class EchoTaskType(str, Enum):
    GENERATE_IMAGE = "generate_image"
    GENERATE_LOOP = "generate_loop"
    GENERATE_VIDEO = "generate_video"
    CHARACTER_DESIGN = "character_design"
    SCENE_COMPOSITION = "scene_composition"
    QUALITY_REVIEW = "quality_review"
    STORY_UPDATE = "story_update"


class EchoTaskRequest(BaseModel):
    """Request from Echo Brain to anime system"""
    task_id: UUID
    task_type: EchoTaskType
    project_id: UUID
    priority: int = 5
    payload: Dict[str, Any]
    callback_url: Optional[str] = None
    context: Optional[Dict[str, Any]] = None  # Story context, character states


class EchoTaskResponse(BaseModel):
    """Response to Echo Brain"""
    task_id: UUID
    job_id: UUID
    status: JobStatus
    result: Optional[Dict[str, Any]] = None
    quality_scores: Optional[QualityScores] = None
    output_paths: List[str] = []
    error: Optional[str] = None


class EchoWebhookPayload(BaseModel):
    """Webhook callback to Echo Brain"""
    event_type: str  # job.completed, job.failed, quality.passed, quality.failed
    task_id: UUID
    job_id: UUID
    timestamp: datetime
    data: Dict[str, Any]


# === Testing Models ===

class PhaseTestSuite(BaseModel):
    """Test suite for a development phase"""
    phase: Phase
    tests: List[str]
    success_criteria: Dict[str, float]
    dependencies: List[Phase] = []


class TestResult(BaseModel):
    test_name: str
    phase: Phase
    passed: bool
    score: Optional[float] = None
    threshold: Optional[float] = None
    duration_seconds: float
    error: Optional[str] = None
    details: Dict[str, Any] = {}


class PhaseGateResult(BaseModel):
    """Result of phase gate evaluation"""
    phase: Phase
    passed: bool
    tests_run: int
    tests_passed: int
    overall_score: float
    individual_results: List[TestResult]
    can_advance: bool
    blocking_issues: List[str] = []
