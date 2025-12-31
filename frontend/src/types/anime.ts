/**
 * Tower Anime Production System - TypeScript Types
 *
 * Aligned with anime-system-modular/backend/models/schemas.py
 * Single Source of Truth for all frontend types
 */

// === Enums ===

export enum JobType {
  STILL_IMAGE = 'still_image',
  ANIMATION_LOOP = 'animation_loop',
  FULL_VIDEO = 'full_video',
  CHARACTER_SHEET = 'character_sheet'
}

export enum JobStatus {
  PENDING = 'pending',
  QUEUED = 'queued',
  PROCESSING = 'processing',
  QUALITY_CHECK = 'quality_check',
  COMPLETED = 'completed',
  FAILED = 'failed',
  TIMEOUT = 'timeout'
}

export enum VariationType {
  OUTFIT = 'outfit',
  EXPRESSION = 'expression',
  POSE = 'pose',
  AGE_VARIANT = 'age_variant'
}

export enum Phase {
  PHASE_1_STILL = 'phase_1_still',
  PHASE_2_LOOP = 'phase_2_loop',
  PHASE_3_VIDEO = 'phase_3_video'
}

export enum EchoTaskType {
  GENERATE_IMAGE = 'generate_image',
  GENERATE_LOOP = 'generate_loop',
  GENERATE_VIDEO = 'generate_video',
  CHARACTER_DESIGN = 'character_design',
  SCENE_COMPOSITION = 'scene_composition',
  QUALITY_REVIEW = 'quality_review',
  STORY_UPDATE = 'story_update'
}

// === Base Interfaces ===

export interface Project {
  id: string
  name: string
  description?: string
  status?: string
  characterCount?: number
  generationCount?: number
  thumbnail?: string
  createdAt?: string
  updatedAt?: string
}

export interface Character {
  id: string
  name: string
  role?: string
  project_id?: string
  thumbnail?: string
  consistencyScore?: number
  description?: string
  basePrompt?: string
  // Modular architecture additions
  referenceEmbedding?: number[]
  negativeTokens?: string[]
  colorPalette?: {
    primary: string[]
    accent: string[]
  }
  loraModelPath?: string
  attributes?: CharacterAttribute[]
  variations?: CharacterVariation[]
}

export interface Scene {
  id: string
  name: string
  description: string
  project_id: string
  characters?: string[]
  duration?: number
  createdAt?: string
}

// === Character Consistency ===

export interface CharacterAttribute {
  id: string
  character_id: string
  attribute_type: string // hair_color, eye_color, outfit, etc.
  attribute_value: string
  prompt_tokens?: string[]
  priority?: number
  created_at: string
}

export interface CharacterAttributeCreate {
  attribute_type: string
  attribute_value: string
  prompt_tokens?: string[]
  priority?: number
}

export interface CharacterVariation {
  id: string
  character_id: string
  variation_name: string
  variation_type: VariationType
  prompt_modifiers?: Record<string, unknown>
  reference_image_path?: string
  created_at: string
}

export interface CharacterVariationCreate {
  variation_name: string
  variation_type: VariationType
  prompt_modifiers?: Record<string, unknown>
  reference_image_path?: string
}

export interface CharacterConsistencyUpdate {
  color_palette?: {
    primary: string[]
    accent: string[]
  }
  base_prompt?: string
  negative_tokens?: string[]
  lora_model_path?: string
}

export interface CharacterEmbeddingRequest {
  reference_image_path: string
  force_recompute?: boolean
}

export interface CharacterEmbeddingResponse {
  character_id: string
  embedding_stored: boolean
  embedding_dimensions: number
  similarity_baseline?: number
}

export interface ConsistencyCheckRequest {
  image_path: string
  threshold?: number
}

export interface ConsistencyCheckResponse {
  character_id: string
  similarity_score: number
  passes_threshold: boolean
  threshold_used: number
}

// === Generation ===

export interface LoRAConfig {
  name: string
  path: string
  weight?: number
}

export interface ControlNetConfig {
  name: string
  model: string
  weight?: number
  preprocessor?: string
}

export interface IPAdapterConfig {
  reference_image_path: string
  weight?: number
  noise?: number
}

export interface GenerationParams {
  positive_prompt: string
  negative_prompt?: string
  seed: number
  subseed?: number
  model_name: string
  model_hash?: string
  vae_name?: string
  sampler_name?: string
  scheduler?: string
  steps?: number
  cfg_scale?: number
  width?: number
  height?: number
  frame_count?: number
  fps?: number
  lora_models?: LoRAConfig[]
  controlnet_models?: ControlNetConfig[]
  ipadapter_refs?: IPAdapterConfig[]
}

export interface GenerationParamsResponse extends GenerationParams {
  id: string
  job_id: string
  created_at: string
}

export interface GenerateRequest {
  project_id?: string
  character_ids?: string[]
  job_type?: JobType
  prompt: string
  negative_prompt?: string
  width?: number
  height?: number
  steps?: number
  cfg_scale?: number
  seed?: number
  frame_count?: number
  fps?: number
  use_character_loras?: boolean
  use_ipadapter?: boolean
  ipadapter_weight?: number
  save_params?: boolean
  auto_quality_check?: boolean
  quality_thresholds?: QualityThresholds
  pose_reference_path?: string
  pose_weight?: number
  // Legacy compatibility
  type?: 'image' | 'video' | 'trailer'
  generation_type?: 'image' | 'video'
  character?: string
  style?: string
  duration?: number
}

export interface GenerateResponse {
  job_id: string
  status: JobStatus | string
  generation_params_id?: string
  seed_used?: number
  estimated_time_seconds?: number
  websocket_url?: string
  comfyui_job_id?: string
  message?: string
  error?: string
}

export interface JobProgressResponse {
  job_id: string
  status: JobStatus | string
  progress_percent: number
  current_step?: number
  total_steps?: number
  current_frame?: number
  total_frames?: number
  eta_seconds?: number
  quality_scores?: QualityScores
  output_path?: string
  error_message?: string
}

export interface ReproduceRequest {
  original_job_id: string
  modifications?: Record<string, unknown>
}

// === Quality Metrics ===

export interface QualityThresholds {
  face_similarity?: number
  aesthetic_score?: number
  temporal_lpips?: number
  motion_smoothness?: number
  subject_consistency?: number
}

export interface QualityScores {
  face_similarity?: number
  aesthetic_score?: number
  temporal_lpips?: number
  motion_smoothness?: number
  subject_consistency?: number
  passes_threshold: boolean
}

export interface QualityScoresResponse extends QualityScores {
  id: string
  job_id: string
  evaluated_at: string
}

export interface QualityEvaluationRequest {
  job_id: string
  output_path: string
  character_ids?: string[]
  thresholds?: QualityThresholds
}

// === Story Bible ===

export interface StoryBible {
  id: string
  project_id: string
  art_style: string
  color_palette?: Record<string, string[]>
  line_weight?: string
  shading_style?: string
  setting_description?: string
  time_period?: string
  mood_keywords?: string[]
  narrative_themes?: string[]
  global_seed?: number
  version: string
  created_at: string
  updated_at: string
}

export interface StoryBibleCreate {
  project_id: string
  art_style: string
  color_palette?: Record<string, string[]>
  line_weight?: string
  shading_style?: string
  setting_description?: string
  time_period?: string
  mood_keywords?: string[]
  narrative_themes?: string[]
  global_seed?: number
}

export interface StoryBibleUpdate {
  art_style?: string
  color_palette?: Record<string, string[]>
  line_weight?: string
  shading_style?: string
  setting_description?: string
  time_period?: string
  mood_keywords?: string[]
  narrative_themes?: string[]
  global_seed?: number
}

// === Project Bible (Legacy) ===

export interface ProjectBible {
  id: string
  project_id: string
  description: string
  setting: string
  theme: string
  target_audience: string
  art_style: string
  characters: Character[]
  createdAt: string
  updatedAt: string
}

// === Echo Brain Integration ===

export interface EchoTaskRequest {
  task_id: string
  task_type: EchoTaskType
  project_id: string
  priority?: number
  payload: Record<string, unknown>
  callback_url?: string
  context?: Record<string, unknown>
}

export interface EchoTaskResponse {
  task_id: string
  job_id: string
  status: JobStatus
  result?: Record<string, unknown>
  quality_scores?: QualityScores
  output_paths?: string[]
  error?: string
}

export interface EchoWebhookPayload {
  event_type: string
  task_id: string
  job_id: string
  timestamp: string
  data: Record<string, unknown>
}

export interface EchoMessage {
  type: 'user' | 'echo'
  content: string
  timestamp: string
  context?: string
  model?: string
}

// === Phase Gate & Testing ===

export interface PhaseTestSuite {
  phase: Phase
  tests: string[]
  success_criteria: Record<string, number>
  dependencies?: Phase[]
}

export interface TestResult {
  test_name: string
  phase: Phase
  passed: boolean
  score?: number
  threshold?: number
  duration_seconds: number
  error?: string
  details?: Record<string, unknown>
}

export interface PhaseGateResult {
  phase: Phase
  passed: boolean
  tests_run: number
  tests_passed: number
  overall_score: number
  individual_results: TestResult[]
  can_advance: boolean
  blocking_issues?: string[]
}

// === Job & Generation History ===

export interface Generation {
  id: string | number
  job_id?: string | number
  prompt: string
  type: 'image' | 'video' | 'trailer'
  status: JobStatus | 'pending' | 'running' | 'processing' | 'completed' | 'failed'
  project_id?: string
  character?: string
  style?: string
  outputPath?: string
  duration?: number
  progress?: number
  error?: string
  createdAt?: string
  startTime?: string
  quality_scores?: QualityScores
}

export interface GenerationQueueItem extends Generation {
  queuePosition?: number
  estimatedStartTime?: string
  priority?: 'low' | 'normal' | 'high' | 'urgent'
}

// === WebSocket ===

export type WebSocketMessageType =
  | 'progress'
  | 'job_complete'
  | 'job_failed'
  | 'status_update'
  | 'system_status'
  | 'generation_progress'
  | 'generation_complete'
  | 'generation_failed'
  | 'quality_evaluation'
  | 'task_completion'
  | 'agent_status_update'
  | 'metrics_update'

export interface WebSocketMessage {
  type: WebSocketMessageType
  job_id?: string | number
  task_id?: string
  progress?: number
  eta?: string
  status?: string
  output_path?: string
  duration?: number
  error?: string
  message?: string
  data?: Record<string, unknown>
  timestamp?: string
}

// === Notifications ===

export interface Notification {
  id: string | number
  message: string
  type: 'info' | 'success' | 'warning' | 'error'
  timestamp: string
}

// === Stats & Metrics ===

export interface GenerationStats {
  total: number
  successful: number
  failed: number
  pending: number
  successRate: string
}

export interface PerformanceMetrics {
  avgGenerationTime: number
  totalGenerations: number
  successRate: number
  activeJobs: number
  systemLoad: number
  vramUsage: number
}

// === Files ===

export interface FileItem {
  id: string | number
  name: string
  path: string
  type: 'image' | 'video' | 'audio' | 'other'
  size: number
  createdAt: string
  thumbnail?: boolean
  project_id?: string
}

// === Character Sheet ===

export interface CharacterSheet {
  character_name: string
  base_prompt: string
  physical_description: string
  personality_traits: string[]
  consistency_notes: string
  reference_images: string[]
  generated_at: string
}

// === API Responses ===

export interface APIResponse<T = unknown> {
  success: boolean
  data?: T
  error?: string
  message?: string
}

export interface APIError {
  detail: string
  status_code?: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}

// === Health Check ===

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy'
  version: string
  services: {
    database: string
    character_consistency: string
    quality_metrics: string
    echo_brain: string
    comfyui: string
  }
}

// === Store State ===

export interface AnimeStoreState {
  projects: Project[]
  selectedProject: Project | null
  characters: Character[]
  selectedCharacter: Character | null
  scenes: Scene[]
  selectedScene: Scene | null
  generationHistory: Generation[]
  currentGeneration: Generation | null
  generationQueue: GenerationQueueItem[]
  wsConnected: boolean
  jobProgress: Record<string, number>
  jobETAs: Record<string, string>
  echoStatus: 'connected' | 'disconnected'
  echoMessages: EchoMessage[]
  loading: boolean
  error: string | null
  notifications: Notification[]
  activeView: 'console' | 'studio' | 'timeline' | 'files' | 'dashboard'
}

// === Component Props ===

export interface DashboardProps {
  initialProject?: Project
  showPerformanceStats?: boolean
  autoRefresh?: boolean
  refreshInterval?: number
}

export interface GenerationFormData {
  prompt: string
  character: string | null
  style: string
  type: 'image' | 'video' | 'trailer'
  duration?: number
  resolution?: string
}

// === Events ===

export interface GenerationEvent {
  type: 'started' | 'completed' | 'failed' | 'progress'
  generation: Generation
  progress?: number
  error?: string
}

export interface ProjectEvent {
  type: 'created' | 'updated' | 'deleted' | 'selected'
  project: Project
}

// === Style Options ===

export interface StyleOption {
  value: string
  label: string
  description?: string
  preview?: string
}

// === Configuration ===

export interface DashboardConfig {
  apiBase: string
  wsUrl: string
  echoBase: string
  fileServerBase: string
  refreshInterval: number
  maxRetries: number
  timeout: number
}

export interface ThemeConfig {
  darkMode: boolean
  primaryColor: string
  successColor: string
  errorColor: string
  warningColor: string
  backgroundColor: string
  cardBackground: string
}

// === API Endpoints Interface ===

export interface APIEndpoints {
  health: string
  projects: string
  characters: string
  scenes: string
  generate: string
  generations: string
  files: string
  websocket: string
  echo: {
    health: string
    query: string
    models: string
  }
}
