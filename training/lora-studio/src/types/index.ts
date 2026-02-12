// Types matching actual API responses from dataset_approval_api.py

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
}

export interface DatasetImage {
  id: string
  name: string
  status: 'pending' | 'approved' | 'rejected'
  prompt: string
  created_at: string
}

export interface PendingImage {
  id: string
  character_name: string
  character_slug: string
  name: string
  prompt: string
  project_name: string
  design_prompt: string
  checkpoint_model?: string
  default_style?: string
  status: string
  created_at: string
  metadata?: ImageMetadata
}

export interface TrainingJob {
  job_id: string
  character_name: string
  character_slug?: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  approved_images: number
  epochs: number
  learning_rate: number
  resolution: number
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
  design_prompt: string
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
  error?: string
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

export type TabType = 'characters' | 'pending' | 'training' | 'ingest' | 'generate' | 'gallery' | 'echo'
