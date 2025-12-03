/**
 * TypeScript interfaces for Anime Production Dashboard
 */

export interface Project {
  id: string
  name: string
  description: string
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
  project_id: string
  thumbnail?: string
  consistencyScore?: number
  description?: string
  basePrompt?: string
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

export interface Generation {
  id: string | number
  job_id?: string | number
  prompt: string
  type: 'image' | 'video' | 'trailer'
  status: 'pending' | 'running' | 'processing' | 'completed' | 'failed'
  project_id?: string
  character?: string
  style?: string
  outputPath?: string
  duration?: number
  progress?: number
  error?: string
  createdAt?: string
  startTime?: string
}

export interface GenerationRequest {
  prompt: string
  type: 'image' | 'video' | 'trailer'
  character?: string
  style?: string
  project_id?: string
  duration?: number
  resolution?: string
  fps?: number
}

export interface WebSocketMessage {
  type: 'progress' | 'job_complete' | 'job_failed' | 'status_update'
  job_id: string | number
  progress?: number
  eta?: string
  status?: string
  output_path?: string
  duration?: number
  error?: string
  message?: string
}

export interface Notification {
  id: string | number
  message: string
  type: 'info' | 'success' | 'warning' | 'error'
  timestamp: string
}

export interface GenerationStats {
  total: number
  successful: number
  failed: number
  pending: number
  successRate: string
}

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

export interface EchoMessage {
  type: 'user' | 'echo'
  content: string
  timestamp: string
  context?: string
  model?: string
}

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

export interface CharacterSheet {
  character_name: string
  base_prompt: string
  physical_description: string
  personality_traits: string[]
  consistency_notes: string
  reference_images: string[]
  generated_at: string
}

export interface APIResponse<T = any> {
  success: boolean
  data?: T
  error?: string
  message?: string
}

export interface GenerationQueueItem extends Generation {
  queuePosition?: number
  estimatedStartTime?: string
  priority?: 'low' | 'normal' | 'high' | 'urgent'
}

export interface PerformanceMetrics {
  avgGenerationTime: number
  totalGenerations: number
  successRate: number
  activeJobs: number
  systemLoad: number
  vramUsage: number
}

export interface StyleOption {
  value: string
  label: string
  description?: string
  preview?: string
}

// Store state interfaces
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
  activeView: 'console' | 'studio' | 'timeline' | 'files'
}

// Component props interfaces
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

// Event interfaces
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

// API endpoint interfaces
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

// Configuration interfaces
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