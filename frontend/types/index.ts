// Types matching actual API responses from LoRA Studio v3.0 (packages/)

export interface AppearanceData {
  species?: string
  body_type?: string
  key_colors?: Record<string, string>
  key_features?: string[]
  common_errors?: string[]
  reference_character?: string
  style?: string
  hair?: { color?: string; style?: string; length?: string }
  eyes?: { color?: string; shape?: string; special?: string }
  skin?: { tone?: string; markings?: string }
  face?: { shape?: string; features?: string }
  body?: { build?: string; height?: string; bust?: string; waist?: string; hips?: string }
  clothing?: { default_outfit?: string; style?: string }
  weapons?: Array<{ name?: string; type?: string; description?: string }>
  accessories?: string[]
  sexual?: { orientation?: string; preferences?: string; physical_traits?: string }
}

export interface Character {
  name: string
  slug: string
  image_count: number
  created_at: string
  project_name: string
  design_prompt: string
  default_style: string
  checkpoint_model: string
  cfg_scale: number | null
  steps: number | null
  resolution: string
  generation_checkpoints: Array<{ checkpoint: string; count: number }>
  // Full profile fields (populated by getCharacterDetail)
  id?: number
  project_id?: number
  description?: string | null
  personality?: string | null
  background?: string | null
  age?: number | null
  role?: string | null
  character_role?: string | null
  personality_tags?: string[] | null
  traits?: Record<string, any> | null
  appearance_data?: AppearanceData | null
  relationships?: Record<string, any> | null
  voice_profile?: Record<string, any> | null
  lora_trigger?: string | null
  lora_path?: string | null
  updated_at?: string | null
}

export interface DatasetImage {
  id: string
  name: string
  status: 'pending' | 'approved' | 'rejected'
  prompt: string
  created_at: string
  checkpoint_model: string | null
}

export interface PendingImage {
  id: string
  character_name: string
  character_slug: string
  name: string
  prompt?: string
  project_name: string
  design_prompt?: string
  checkpoint_model?: string
  default_style?: string
  status: string
  source?: 'youtube' | 'generated' | 'upload' | 'reference'
  created_at: string
  metadata?: ImageMetadata
}

export interface TrainingJob {
  job_id: string
  character_name: string
  character_slug?: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'invalidated'
  approved_images: number
  epochs: number
  learning_rate: number
  resolution: number
  lora_rank?: number
  model_type?: string
  prediction_type?: string
  checkpoint?: string
  output_path?: string
  created_at: string
  started_at?: string
  completed_at?: string
  failed_at?: string
  epoch?: number
  total_epochs?: number
  loss?: number
  best_loss?: number
  final_loss?: number
  global_step?: number
  total_steps?: number
  file_size_mb?: number
  error?: string
  pid?: number
  last_heartbeat?: string
}

export interface LoraFile {
  filename: string
  slug: string
  architecture: string
  path: string
  size_mb: number
  created_at: string
  job_id: string | null
  job_status: string | null
  checkpoint: string | null
  trained_epochs: number | null
  final_loss: number | null
  best_loss: number | null
  resolution: number | null
  lora_rank: number | null
}

export interface ApprovalRequest {
  character_name: string
  character_slug: string
  image_name: string
  approved: boolean
  feedback?: string
  edited_prompt?: string
}

export interface TrainingRequest {
  character_name: string
  epochs?: number
  learning_rate?: number
  resolution?: number
}

export interface CharacterUpdate {
  design_prompt?: string
  description?: string | null
  personality?: string | null
  background?: string | null
  age?: number | null
  role?: string | null
  character_role?: string | null
  personality_tags?: string[] | null
  traits?: Record<string, any> | null
  appearance_data?: AppearanceData | null
  relationships?: Record<string, any> | null
  voice_profile?: Record<string, any> | null
}

export interface CharacterCreate {
  name: string
  project_name: string
  description?: string
  design_prompt?: string
}

export interface IdentifyResult {
  description: string
  suggested_name: string
}

export interface VisionReview {
  character_match: number
  solo: boolean
  clarity: number
  completeness: string
  training_value: number
  caption: string
  issues: string[]
}

export interface VisionReviewResponse {
  reviewed: number
  auto_approved: number
  auto_rejected: number
  regen_queued: number
  character_slug?: string
  project?: string
  results: Array<{
    image: string
    character_slug: string
    quality_score: number | null
    solo: boolean | null
    action: 'approved' | 'rejected' | 'pending' | 'error'
    issues: string[]
  }>
}

export interface ImageMetadata {
  seed: number | null
  full_prompt: string
  negative_prompt: string | null
  design_prompt: string
  pose: string
  checkpoint_model: string
  cfg_scale: number | null
  steps: number | null
  sampler: string | null
  scheduler: string | null
  width: number | null
  height: number | null
  comfyui_prompt_id: string | null
  project_name: string
  character_name: string
  source: string
  generated_at: string | null
  backfilled?: boolean
  quality_score?: number | null
  vision_review?: VisionReview
}

export interface RegenerateRequest {
  slug: string
  count?: number
  seed?: number
  prompt_override?: string
}

export interface GalleryImage {
  filename: string
  created_at: string
  size_kb: number
}

export interface GenerateParams {
  generation_type: 'image' | 'video'
  prompt_override?: string
  negative_prompt?: string
  seed?: number
}

export interface GenerateResponse {
  prompt_id: string
  character: string
  generation_type: string
  prompt_used: string
  checkpoint: string
  seed: number
}

export interface GenerationStatus {
  status: 'pending' | 'running' | 'completed' | 'unknown' | 'error'
  progress: number
  images?: string[]
  output_files?: string[]
  error?: string
}

export interface FramePackParams {
  prompt_override?: string
  negative_prompt?: string
  image_path?: string
  seconds?: number
  steps?: number
  use_f1?: boolean
  seed?: number
  gpu_memory_preservation?: number
}

export interface FramePackResponse {
  prompt_id: string
  character: string
  model: string
  seconds: number
  source_image: string
  total_sections: number
  total_steps: number
  sampler_node_id: string
}

export interface EchoChatResponse {
  response: string
  context_used: boolean
  character_context?: string
}

export interface EchoEnhanceResponse {
  original_prompt: string
  echo_brain_context: string[]
  suggestion: string
}

// --- Project Configuration ---

export interface GenerationStyle {
  checkpoint_model: string | null
  cfg_scale: number | null
  steps: number | null
  sampler: string | null
  scheduler: string | null
  width: number | null
  height: number | null
  positive_prompt_template: string | null
  negative_prompt_template: string | null
}

export interface Storyline {
  title: string | null
  summary: string | null
  theme: string | null
  genre: string | null
  target_audience: string | null
  tone: string | null
  themes: string[] | null
  humor_style: string | null
  story_arcs: any[] | null
}

export interface WorldSettings {
  style_preamble: string | null
  art_style: string | null
  aesthetic: string | null
  color_palette: { primary: string[], secondary: string[], environmental: string[] } | null
  cinematography: { shot_types: string[], camera_angles: string[], lighting: string } | null
  world_location: { primary: string, areas: string[], atmosphere: string } | null
  time_period: string | null
  production_notes: string | null
  known_issues: string[] | null
  negative_prompt_guidance: string | null
}

export interface Project {
  id: number
  name: string
  description: string | null
  genre: string | null
  status: string | null
  default_style: string | null
  premise: string | null
  content_rating: string | null
  style: GenerationStyle | null
  storyline: Storyline | null
  world_settings: WorldSettings | null
}

export interface CheckpointFile {
  filename: string
  size_mb: number
  style_label?: string
  architecture?: string
  prompt_format?: string
  default_cfg?: number
  default_steps?: number
  default_sampler?: string
  quality_prefix?: string
  quality_negative?: string
}

export interface ProjectCreate {
  name: string
  description?: string
  genre?: string
  checkpoint_model: string
  cfg_scale?: number
  steps?: number
  sampler?: string
  width?: number
  height?: number
  positive_prompt_template?: string
  negative_prompt_template?: string
}

export interface ProjectUpdate {
  name?: string
  description?: string
  genre?: string
  premise?: string
  content_rating?: string
}

export interface StorylineUpsert {
  title?: string
  summary?: string
  theme?: string
  genre?: string
  target_audience?: string
  tone?: string
  themes?: string[]
  humor_style?: string
  story_arcs?: any[]
}

export interface WorldSettingsUpsert {
  style_preamble?: string
  art_style?: string
  aesthetic?: string
  color_palette?: { primary: string[], secondary: string[], environmental: string[] }
  cinematography?: { shot_types: string[], camera_angles: string[], lighting: string }
  world_location?: { primary: string, areas: string[], atmosphere: string }
  time_period?: string
  production_notes?: string
  known_issues?: string[]
  negative_prompt_guidance?: string
}

export interface StyleUpdate {
  checkpoint_model?: string
  cfg_scale?: number
  steps?: number
  sampler?: string
  width?: number
  height?: number
  positive_prompt_template?: string
  negative_prompt_template?: string
  reason?: string
}

export interface StyleHistoryEntry {
  id: number
  checkpoint_model: string | null
  cfg_scale: number | null
  steps: number | null
  sampler: string | null
  scheduler: string | null
  width: number | null
  height: number | null
  switched_at: string | null
  reason: string | null
  generation_count: number
  avg_quality_at_switch: number | null
  live_total: number
  live_approved: number
  live_avg_quality: number | null
}

export interface StyleCheckpointStats {
  checkpoint_model: string
  total: number
  approved: number
  rejected: number
  approval_rate: number
  avg_quality: number | null
  first_used: string | null
  last_used: string | null
}

// --- Echo Brain Narrator Assist ---

export interface NarrateRequest {
  context_type: 'storyline' | 'description' | 'positive_template' | 'negative_template' | 'design_prompt' | 'prompt_override' | 'concept' | 'scene_location' | 'scene_mood' | 'motion_prompt' | 'production_notes' | 'character_profile'
  project_name?: string
  project_genre?: string
  project_description?: string
  project_premise?: string
  storyline_title?: string
  storyline_summary?: string
  storyline_theme?: string
  checkpoint_model?: string
  positive_prompt_template?: string
  negative_prompt_template?: string
  character_name?: string
  character_slug?: string
  design_prompt?: string
  current_value?: string
  concept_description?: string
  scene_description?: string
  shot_type?: string
}

export interface NarrateResponse {
  suggestion: string
  confidence: number
  sources: string[]
  execution_time_ms: number
  context_type: string
  fields?: Record<string, any>
}

// --- Content Reconstruction Pipeline ---

export interface SceneTimeline {
  project_name: string
  source_url: string
  analyzed_at: string
  total_duration: number
  scene_count: number
  scenes: Scene[]
}

export interface Scene {
  scene_id: number
  start: number
  end: number
  duration: number
  characters: string[]
  environment: string
  frames: string[]
  frame_count: number
  mood?: {
    energy: string
    energy_ratio?: number
    tempo_present: boolean
    estimated_bpm?: number | null
    classification: string
  }
}

export interface VoiceMap {
  project_name: string
  source_url: string
  analyzed_at: string
  total_segments: number
  linked_segments: number
  segments: VoiceSegment[]
}

export interface VoiceSegment {
  path: string
  filename: string
  start: number
  end: number
  duration: number
  scene_id?: number | null
  visible_characters?: string[]
}

export interface TextExtraction {
  project_name: string
  source_url: string
  analyzed_at: string
  total_entries: number
  entries: TextEntry[]
}

export interface TextEntry {
  text: string
  type: string
  start_time?: string
  end_time?: string
  source_frame?: string
}

// --- Apple Music ---

export interface SceneAudio {
  track_id: string
  track_name: string
  track_artist: string
  preview_url: string
  fade_in: number
  fade_out: number
  start_offset: number
  auto_duck?: boolean
  generation_mode?: string
  source_playlist_id?: string
}

export interface AppleMusicTrack {
  library_id?: string
  catalog_id: string | null
  name: string
  artist: string
  album?: string
  duration_ms: number | null
  artwork_url: string | null
  preview_url: string | null
}

export interface AppleMusicPlaylist {
  id: string
  name: string
  description?: string | null
}

// --- Scene Builder ---

export interface BuilderScene {
  id: string
  project_id: number
  project_name?: string
  title: string
  description: string | null
  location: string | null
  time_of_day: string | null
  weather: string | null
  mood: string | null
  generation_status: 'draft' | 'generating' | 'completed' | 'partial' | 'failed'
  target_duration_seconds: number
  actual_duration_seconds: number | null
  total_shots: number
  completed_shots: number
  post_interpolate_fps: number | null
  post_upscale_factor: number | null
  final_video_path: string | null
  current_generating_shot_id: string | null
  narrative_text?: string | null
  emotional_tone?: string | null
  camera_directions?: string | null
  audio?: SceneAudio | null
  shots?: BuilderShot[]
  created_at: string | null
}

export interface BuilderShot {
  id: string
  shot_number: number
  shot_type: string
  camera_angle: string
  duration_seconds: number
  characters_present: string[]
  motion_prompt: string | null
  source_image_path: string | null
  first_frame_path: string | null
  last_frame_path: string | null
  output_video_path: string | null
  comfyui_prompt_id: string | null
  status: 'pending' | 'generating' | 'completed' | 'failed'
  seed: number | null
  steps: number | null
  use_f1: boolean
  quality_score: number | null
  error_message: string | null
  generation_time_seconds: number | null
  dialogue_text: string | null
  dialogue_character_slug: string | null
  video_engine: 'framepack' | 'framepack_f1' | 'ltx' | 'wan' | null
  transition_type: string | null
  transition_duration: number | null
}

export interface SceneCreateRequest {
  project_id: number
  title: string
  description?: string | null
  location?: string | null
  time_of_day?: string | null
  weather?: string | null
  mood?: string | null
  target_duration_seconds?: number
  post_interpolate_fps?: number | null
  post_upscale_factor?: number | null
}

export interface ShotCreateRequest {
  shot_number: number
  source_image_path: string
  shot_type?: string
  camera_angle?: string
  duration_seconds?: number
  motion_prompt: string
  characters_present?: string[]
  seed?: number
  steps?: number
  use_f1?: boolean
  dialogue_text?: string | null
  dialogue_character_slug?: string | null
  video_engine?: 'framepack' | 'framepack_f1' | 'ltx' | 'wan' | null
  transition_type?: string | null
  transition_duration?: number | null
}

export interface SceneGenerationStatus {
  generation_status: string
  total_shots: number
  completed_shots: number
  current_generating_shot_id: string | null
  final_video_path: string | null
  actual_duration_seconds: number | null
  shots: Array<{
    id: string
    shot_number: number
    status: string
    output_video_path: string | null
    error_message: string | null
    comfyui_prompt_id: string | null
    generation_time_seconds: number | null
    quality_score: number | null
    motion_prompt: string | null
  }>
}

export interface ApprovedImagesResponse {
  characters: Record<string, {
    character_name: string
    images: string[] | ImageWithMetadata[]
  }>
}

export interface ImageWithMetadata {
  name: string
  pose: string | null
  quality_score: number | null
  vision_summary: string | null
}

export interface ShotRecommendation {
  image_name: string
  slug: string
  score: number
  pose: string | null
  quality_score: number
  reason: string
}

export interface ShotRecommendations {
  shot_id: string
  shot_number: number
  shot_type: string
  camera_angle: string | null
  current_source: string | null
  recommendations: ShotRecommendation[]
}

export interface SceneRecommendationsResponse {
  scene_id: string
  shots: ShotRecommendations[]
}

// --- Episode Assembly ---

export interface Episode {
  id: string
  project_id: number
  project_name?: string
  episode_number: number
  title: string
  description: string | null
  story_arc: string | null
  status: 'draft' | 'assembled' | 'published'
  final_video_path: string | null
  thumbnail_path: string | null
  actual_duration_seconds: number | null
  scene_count: number
  created_at: string | null
  scenes?: EpisodeScene[]
}

export interface EpisodeScene {
  scene_id: string
  position: number
  transition: string
  title: string | null
  description: string | null
  generation_status: string
  actual_duration_seconds: number | null
  final_video_path: string | null
  total_shots: number
}

export interface EpisodeCreateRequest {
  project_id: number
  episode_number: number
  title: string
  description?: string | null
  story_arc?: string | null
}

// --- Autonomy & Learning Dashboard ---

export interface LearningStats {
  generation_history: {
    total: number
    reviewed: number
    avg_quality: number | null
    approved: number
    rejected: number
    characters_tracked: number
    checkpoints_used: number
  }
  rejections: {
    total: number
    characters_affected: number
  }
  learned_patterns: number
  autonomy_decisions: {
    total: number
    auto_approves: number
    auto_rejects: number
    regenerations: number
  }
  period: string
}

export interface EventBusStats {
  registered_events: string[]
  total_handlers: number
  total_emits: number
  total_errors: number
}

export interface ParamRecommendation {
  confidence: 'none' | 'low' | 'medium' | 'high' | 'error'
  sample_count: number
  avg_quality?: number
  cfg_scale?: number
  steps?: number
  sampler?: string
  scheduler?: string
  checkpoint?: {
    model: string
    avg_quality: number
    sample_count: number
  }
  learned_negatives: string
}

export interface DriftAlert {
  character_slug: string
  recent_avg: number
  overall_avg: number
  drift: number
  recent_count: number
  total_count: number
  alert: boolean
}

export interface QualityCharacterSummary {
  character_slug: string
  total: number
  approved: number
  rejected: number
  avg_quality: number | null
  best_quality: number | null
  worst_quality: number | null
  approval_rate: number
  last_generated: string | null
}

export interface QualityTrendPoint {
  date: string
  avg_quality: number
  count: number
  approved: number
  rejected: number
}

export interface RejectionPattern {
  category: string
  count: number
  latest_at: string | null
}

export interface CheckpointRanking {
  checkpoint: string
  avg_quality: number
  total: number
  approved: number
  rejected: number
  approval_rate: number
}

// --- IPAdapter Refinement ---

export interface RefineRequest {
  character_slug: string
  reference_image: string
  prompt_override?: string
  count?: number
  weight?: number
  denoise?: number
}

export interface RefineResponse {
  message: string
  reference_image: string
  results: Array<{ prompt_id?: string; seed?: number; error?: string }>
}

// --- Replenishment Loop ---

export interface ReplenishmentStatus {
  enabled: boolean
  default_target: number
  max_concurrent: number
  cooldown_seconds: number
  max_daily_per_char: number
  max_consecutive_rejects: number
  batch_size: number
  active_generations: Record<string, boolean>
  daily_counts: Record<string, number>
  consecutive_rejects: Record<string, number>
  last_generation: Record<string, string>
  target_overrides: Record<string, number>
}

export interface CharacterReadiness {
  name: string
  slug: string
  project_name: string
  approved: number
  pending: number
  target: number
  deficit: number
  ready: boolean
  active_generation: boolean
  daily_generated: number
  consecutive_rejects: number
}

export interface ReadinessResponse {
  project_name: string | null
  characters: CharacterReadiness[]
  total: number
  ready: number
  deficit: number
}

// --- Voice Pipeline ---

export interface VoiceSpeaker {
  id: number
  speaker_label: string
  project_name: string
  assigned_character_id: number | null
  assigned_character_slug: string | null
  embedding_path: string | null
  segment_count: number
  total_duration_seconds: number
  avg_confidence: number | null
  created_at: string
  updated_at: string
}

export interface VoiceSample {
  id?: number
  speaker_id?: number
  character_slug: string
  project_name?: string
  filename: string
  file_path: string
  approval_status: 'pending' | 'approved' | 'rejected'
  transcript?: string | null
  language?: string | null
  duration_seconds: number | null
  start_time?: number | null
  end_time?: number | null
  snr_db?: number | null
  quality_score?: number | null
  speaker_confidence?: number | null
  feedback?: string | null
  rejection_categories?: string[]
  created_at?: string
  reviewed_at?: string | null
}

export interface VoiceTrainingJob {
  id: number
  job_id: string
  character_slug: string
  character_name: string | null
  project_name: string | null
  engine: 'sovits' | 'rvc'
  status: 'queued' | 'running' | 'completed' | 'failed'
  approved_samples: number
  total_duration_seconds: number
  epochs: number | null
  model_path: string | null
  log_path: string | null
  pid: number | null
  error: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface VoiceSynthesisResult {
  job_id?: string
  output_path: string
  engine_used: string
  duration_seconds: number
  character_slug: string
  text: string
}

export interface VoiceModel {
  engine: string
  model_path?: string
  voice?: string
  quality: 'production' | 'prototype' | 'fallback'
}

export interface VoiceModelsResponse {
  character_slug: string
  available_engines: VoiceModel[]
  preferred_engine: string | null
  voice_preset: string | null
}

export interface VoiceSampleStats {
  character_slug: string
  total: number
  approved: number
  rejected: number
  pending: number
  total_approved_duration: number
}

export interface DiarizationResult {
  project: string
  audio_file: string
  speakers: Array<{
    speaker_label: string
    segment_count: number
    total_duration_seconds: number
    turns: Array<{ start: number; end: number; duration: number }>
  }>
  segment_assignments: Array<{
    path: string
    filename: string
    start: number
    end: number
    duration: number
    speaker: string | null
    speaker_confidence: number
  }>
  total_speakers: number
}

export interface SceneDialogueResult {
  scene_id: string
  dialogue_count: number
  combined_path: string | null
  total_duration_seconds: number
  lines: VoiceSynthesisResult[]
}

// --- Gap Analysis (Production Readiness) ---

export interface GapAnalysisCharacter {
  slug: string
  name: string
  approved_count: number
  has_lora: boolean
  pose_coverage: number
  pose_total: number
  pose_distribution: Record<string, number>
  pose_skew: number
  images_without_pose: number
  avg_quality: number | null
  poses_missing: string[]
}

export interface GapAnalysisScene {
  id: string
  title: string
  mood: string | null
  target_duration_seconds: number
  characters: Array<{ slug: string; name: string; has_lora: boolean }>
  shots_defined: number
  shots_completed: number
  shots_needed: number
  production_ready: boolean
}

export interface GapActionItem {
  type: 'train_lora' | 'rebalance_pose' | 'add_shots'
  priority: number
  target: string
  slug?: string
  reason: string
}

export interface GapAnalysisSummary {
  total_characters: number
  with_lora: number
  without_lora: number
  avg_pose_coverage: number
  pose_total: number
  scenes_total: number
  scenes_ready: number
  total_approved_images: number
  production_readiness_pct: number
}

export interface GapAnalysisResponse {
  project_name: string | null
  characters: GapAnalysisCharacter[]
  scenes: GapAnalysisScene[]
  summary: GapAnalysisSummary
  actions: GapActionItem[]
  pose_labels: string[]
}

// --- Orchestrator ---

export interface OrchestratorStatus {
  enabled: boolean
  training_target: number | null
  tick_interval: number
}

export interface PipelineEntry {
  id: number
  entity_type: 'character' | 'project'
  entity_id: string
  project_id: number
  phase: string
  status: 'pending' | 'active' | 'completed' | 'skipped' | 'failed' | 'blocked'
  gate_check_result: Record<string, unknown> | null
  blocked_reason?: string | null
  updated_at: string
}

export interface PipelineStatus {
  project_id: number
  characters: Record<string, PipelineEntry[]>
  project_phases: Record<string, PipelineEntry>
  progress: { total_phases: number; completed: number; active: number; failed: number; percent: number }
}

// --- Music Generation (ACE-Step) ---

export interface MusicGenerateRequest {
  mood: string
  genre?: string
  duration?: number
  bpm?: number | null
  caption?: string | null
  seed?: number | null
  instrumental?: boolean
  scene_id?: string | null
}

export interface MusicGenerateResponse {
  task_id: string
  status: string
  caption: string
  duration: number
  scene_id: string | null
}

export interface MusicTaskStatus {
  status: 'pending' | 'processing' | 'completed' | 'failed'
  output_path?: string
  cached_path?: string
  error?: string
}

export interface MusicTrack {
  filename: string
  size_kb: number
  path: string
  mood?: string
  genre?: string
  duration?: number
}

export interface MusicSuggestion {
  suggested_mood: string
  suggested_genre: string
  suggested_bpm: number
  suggested_duration: number
  reasoning: string
}

export interface PlaylistProfile {
  playlist_id: string
  track_count: number
  avg_bpm: number
  dominant_genres: string[]
  dominant_mood: string
  energy: number
  genre_breakdown: Record<string, number>
}

export interface CuratedPlaylist {
  id: number
  name: string
  description?: string | null
  created_at?: string | null
  track_count?: number
}

export interface CuratedPlaylistTrack {
  id: number
  track_id: string
  track_name: string
  track_artist: string
  preview_url: string
  source: string
  position: number
  added_at?: string | null
}

// --- Video Review ---

export interface PendingVideo {
  id: string
  scene_id: string
  shot_number: number
  shot_type: string
  camera_angle: string
  duration_seconds: number
  characters_present: string[]
  motion_prompt: string | null
  source_image_path: string | null
  output_video_path: string | null
  quality_score: number | null
  video_engine: 'framepack' | 'framepack_f1' | 'ltx' | 'wan'
  seed: number | null
  steps: number | null
  generation_time_seconds: number | null
  review_status: 'pending_review' | 'approved' | 'rejected' | 'unreviewed'
  qc_issues: string[]
  qc_category_averages: Record<string, number>
  qc_per_frame: Array<Record<string, unknown>>
  scene_title: string
  project_id: number
  project_name: string
}

export interface VideoReviewRequest {
  shot_id: string
  approved: boolean
  feedback?: string
  reject_engine?: boolean
}

export interface BatchVideoReviewRequest {
  shot_ids: string[]
  approved: boolean
  feedback?: string
}

export interface EngineStats {
  video_engine: string
  total: number
  avg_quality: number | null
  min_quality: number | null
  max_quality: number | null
  approved: number
  rejected: number
  pending: number
  avg_gen_time: number | null
}

export interface EngineBlacklistEntry {
  character_slug: string
  video_engine: string
  reason: string | null
  created_at: string | null
}

// --- Wan T2V ---

export interface WanModelsStatus {
  models: Record<string, unknown>
  standard_ready: boolean
  gguf_ready: boolean
  download_instructions: Record<string, string>
}

export interface WanGenerateParams {
  prompt: string
  width?: number
  height?: number
  num_frames?: number
  fps?: number
  steps?: number
  cfg?: number
  seed?: number | null
  use_gguf?: boolean
}

export interface WanGenerateResponse {
  prompt_id: string
  engine: string
  mode: string
  seconds: number
  resolution: string
  prefix: string
}

// --- Production Pipeline (Produce Tab) ---

export interface GpuStatus {
  nvidia: { total_mb: number; used_mb: number; free_mb: number; gpu_name: string } | null
  amd: { total_mb: number; used_mb: number; free_mb: number; gpu_name: string } | null
  ollama: { loaded_models: Array<{ name: string; size_mb: number; vram_mb: number }>; total_vram_mb: number }
  comfyui: { queue_running: number; queue_pending: number }
  host?: { cpu_percent: number; cpu_count: number; ram_total_mb: number; ram_used_mb: number; ram_free_mb: number; ram_percent: number }
}

export interface ProjectSummary {
  id: number
  name: string
  default_style: string
  character_count: number
}

export interface ModelBreakdown {
  [checkpoint: string]: number
}

export interface CharDetail {
  slug: string
  name: string
  approved: number
  loraStatus: 'lora-trained' | 'lora-training' | 'lora-ready' | 'lora-none'
  modelBreakdown: ModelBreakdown
  dominantModel: string | null
  isMixedModels: boolean
  loraCheckpoint: string | null
  loraLoss: number | null
  loraEpochs: number | null
  loraModelMismatch: boolean
  approvalRate?: number
  driftStatus?: 'ok' | 'warn' | 'critical' | null
}

export interface StageInfo {
  label: string
  summary: string
  pct: number
}

export interface ProjectCard {
  id: number
  name: string
  defaultStyle: string
  charCount: number
  loraCount: number
  characters: CharDetail[]
  charsNeedingLora: CharDetail[]
  charsWithMixedModels: CharDetail[]
  charsWithLoraMismatch: CharDetail[]
  scenes: BuilderScene[]
  totalShots: number
  completedShots: number
  episodes: Episode[]
  stages: StageInfo[]
  nextAction: string
  warnings: string[]
}

export interface ProjectQualityData {
  driftAlerts: DriftAlert[]
  trendData: QualityTrendPoint[]
  checkpointRankings: CheckpointRanking[]
  datasetStats: DatasetCharacterStats | null
  pipelineEntries: PipelineEntry[]
}

export interface DatasetCharacterStats {
  slug: string
  name: string
  project_name: string
  approved: number
  pending: number
  rejected: number
  total: number
  approval_rate: number
  model_breakdown: Record<string, number>
  dominant_model: string | null
  is_mixed_models: boolean
}

export interface DatasetStatsResponse {
  characters: DatasetCharacterStats[]
  totals: { approved: number; pending: number; rejected: number; total: number }
}

// --- Narrative State Machine (NSM) ---

export interface CharacterSceneState {
  scene_id: string
  character_slug: string
  clothing: string | null
  hair_state: string | null
  injuries: Array<{ type: string; severity: string; location: string; countdown?: number }>
  accessories: string[]
  body_state: string
  emotional_state: string
  energy_level: string
  relationship_context: Record<string, unknown>
  location_in_scene: string | null
  carrying: string[]
  state_source: 'auto' | 'manual' | 'ai_initialized' | 'propagated'
  version: number
  created_at?: string
  updated_at?: string
}

export interface ImageVisualTags {
  character_slug: string
  project_name: string | null
  image_name: string
  clothing: string | null
  hair_state: string | null
  expression: string | null
  body_state: string | null
  pose: string | null
  accessories: string[]
  setting: string | null
  quality_score: number | null
  nsfw_level: number
  face_visible: boolean | null
  full_body: boolean | null
  tagged_by: string
  confidence: number
}

export interface RegenerationQueueItem {
  id: number
  scene_id: string
  scene_title: string
  shot_id: string | null
  reason: string
  priority: number
  source_scene_id: string | null
  source_field: string | null
  status: 'pending' | 'processed' | 'cancelled'
  created_at: string | null
}
