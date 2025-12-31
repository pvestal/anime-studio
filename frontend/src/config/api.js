/**
 * Tower Anime Production System - API Configuration
 *
 * Single Source of Truth (SSOT) for all API endpoints
 * Aligned with anime-system-modular architecture
 */

// Detect environment
const isDevelopment = import.meta.env.DEV
const isProduction = import.meta.env.PROD

// Base URLs - Update these for your environment
const API_HOSTS = {
  // Primary anime production API
  anime: isDevelopment ? '' : 'http://192.168.50.135:8328',

  // WebSocket for real-time job updates
  websocket: isDevelopment
    ? 'ws://localhost:8328/ws'
    : 'ws://192.168.50.135:8328/ws',

  // Echo Brain AI orchestration
  echo: 'http://192.168.50.135:8309',

  // ComfyUI for direct status checks
  comfyui: 'http://192.168.50.135:8188'
}

/**
 * API Endpoints - Modular Architecture
 *
 * Organized by domain:
 * - Health & Status
 * - Generation (still, loop, video)
 * - Characters (consistency, attributes, variations)
 * - Quality (metrics, phase gates)
 * - Story Bible
 * - Jobs & Progress
 * - Echo Brain Integration
 */
export const API = {
  // Base URL (empty for Vite proxy in development)
  BASE: API_HOSTS.anime,

  // === Health & Status ===
  HEALTH: '/api/health',
  ANIME_HEALTH: '/api/anime/health',

  // === Generation Endpoints ===
  GENERATE: '/api/anime/generate',
  GENERATE_FAST: '/api/anime/generate-fast',
  REPRODUCE: (jobId) => `/api/anime/jobs/${jobId}/reproduce`,

  // === Project Management ===
  PROJECTS: '/api/anime/projects',
  PROJECT: (id) => `/api/anime/projects/${id}`,
  PROJECT_HISTORY: (id) => `/api/anime/projects/${id}/history`,
  PROJECT_GENERATE: (id) => `/api/anime/projects/${id}/generate`,

  // === Story Bible ===
  STORY_BIBLE: (projectId) => `/api/anime/projects/${projectId}/story-bible`,

  // === Character Consistency ===
  CHARACTERS: '/api/anime/characters',
  CHARACTER: (id) => `/api/anime/characters/${id}`,
  CHARACTER_EMBEDDING: (id) => `/api/anime/characters/${id}/embedding`,
  CHARACTER_CONSISTENCY: (id) => `/api/anime/characters/${id}/consistency`,
  CHARACTER_CONSISTENCY_CHECK: (id) => `/api/anime/characters/${id}/consistency-check`,
  CHARACTER_ATTRIBUTES: (id) => `/api/anime/characters/${id}/attributes`,
  CHARACTER_VARIATIONS: (id) => `/api/anime/characters/${id}/variations`,
  CHARACTER_PROMPT: (id) => `/api/anime/characters/${id}/prompt`,

  // === Quality Metrics ===
  QUALITY_EVALUATE: '/api/anime/quality/evaluate',
  QUALITY_PHASE_GATE: (phase) => `/api/anime/quality/phase-gate/${phase}`,
  QUALITY_STANDARDS: '/api/anime/quality/standards',

  // === Job Management ===
  JOBS: '/api/anime/jobs',
  JOB: (id) => `/api/anime/jobs/${id}`,
  JOB_STATUS: (id) => `/api/anime/jobs/${id}/status`,
  JOB_PROGRESS: (id) => `/api/anime/jobs/${id}/progress`,
  JOB_PARAMS: (id) => `/api/anime/jobs/${id}/params`,
  JOB_QUALITY: (id) => `/api/anime/jobs/${id}/quality`,

  // === Generation Settings ===
  QUALITY_PRESETS: '/api/anime/quality-presets',
  MODELS: '/api/anime/models',
  VRAM_STATUS: '/api/anime/vram-status',

  // === File Management ===
  FILES: '/api/anime/files',
  GENERATIONS: '/api/anime/generations',
  IMAGES: '/api/anime/images',

  // === Echo Brain Integration ===
  ECHO_TASKS: '/api/anime/echo/tasks',
  ECHO_WEBHOOK: '/api/anime/echo/webhook',

  // === Git Operations ===
  GIT_STATUS: '/api/anime/git/status',
  GIT_COMMIT: '/api/anime/git/commit',
  GIT_BRANCH: '/api/anime/git/branch'
}

// WebSocket Configuration
export const WS = {
  BASE: API_HOSTS.websocket,
  JOB: (jobId) => `${API_HOSTS.websocket}/jobs/${jobId}`,
  RECONNECT_INTERVAL: 5000,
  MAX_RECONNECT_ATTEMPTS: 10
}

// Echo Brain Configuration
export const ECHO = {
  BASE: API_HOSTS.echo,
  HEALTH: `${API_HOSTS.echo}/api/echo/health`,
  QUERY: `${API_HOSTS.echo}/api/echo/query`
}

// ComfyUI Configuration
export const COMFYUI = {
  BASE: API_HOSTS.comfyui,
  HEALTH: `${API_HOSTS.comfyui}/system_stats`,
  QUEUE: `${API_HOSTS.comfyui}/queue`
}

/**
 * Build full URL from endpoint
 * In development, uses Vite proxy (relative paths)
 * In production, uses absolute URLs
 */
export function buildUrl(endpoint) {
  if (endpoint.startsWith('http://') || endpoint.startsWith('https://')) {
    return endpoint
  }
  return `${API.BASE}${endpoint}`
}

// Export environment info for debugging
export const ENV = {
  isDevelopment,
  isProduction,
  hosts: API_HOSTS,
  version: '2.0.0'
}

export default API
