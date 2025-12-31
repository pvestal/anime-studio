/**
 * Centralized API Configuration
 *
 * This file serves as the Single Source of Truth (SSOT) for all API endpoints
 * across the frontend application.
 *
 * IMPORTANT: Update these values based on your deployment environment:
 * - Development: Uses Vite proxy (relative paths)
 * - Production: Uses absolute URLs
 */

// Detect environment
const isDevelopment = import.meta.env.DEV
const isProduction = import.meta.env.PROD

// Base URLs - Update these for your environment
const API_HOSTS = {
  // Primary anime production API
  anime: isDevelopment ? '' : 'http://***REMOVED***:8305',

  // WebSocket for real-time updates
  websocket: isDevelopment ? 'ws://localhost:8765' : 'wss://***REMOVED***/api/ws',

  // Echo Brain AI service
  echo: 'http://localhost:8309',

  // ComfyUI for direct status checks
  comfyui: 'http://127.0.0.1:8188',

  // Music service
  music: 'http://127.0.0.1:8308',
  musicSearch: 'http://127.0.0.1:8315'
}

// API Endpoints
export const API = {
  // Base URL (empty for Vite proxy in development)
  BASE: API_HOSTS.anime,

  // Anime Generation
  GENERATE: '/api/anime/generate',
  GENERATE_FAST: '/api/anime/generate-fast',
  GENERATE_IMAGE: '/api/anime/generate/image',
  GENERATE_VIDEO: '/api/anime/generate/video',

  // Job Management
  JOBS: '/api/anime/jobs',
  JOB_STATUS: (jobId) => `/api/anime/jobs/${jobId}/status`,
  JOB_PROGRESS: (jobId) => `/api/anime/jobs/${jobId}/progress`,
  GENERATION_STATUS: (requestId) => `/api/anime/generation/${requestId}/status`,

  // Project Management
  PROJECTS: '/api/anime/projects',
  PROJECT: (id) => `/api/anime/projects/${id}`,
  PROJECT_BIBLE: (id) => `/api/anime/projects/${id}/bible`,
  PROJECT_CHARACTERS: (id) => `/api/anime/projects/${id}/characters`,
  PROJECT_SCENES: (id) => `/api/anime/projects/${id}/scenes`,

  // Project History & Generation
  PROJECT_HISTORY: (id) => `/api/anime/projects/${id}/history`,
  PROJECT_GENERATE: (id) => `/api/anime/projects/${id}/generate`,

  // Generation Settings
  QUALITY_PRESETS: '/api/anime/quality-presets',
  MODELS: '/api/anime/models',
  VRAM_STATUS: '/api/anime/vram-status',

  // File Management
  FILES: '/api/anime/files',
  GENERATIONS: '/api/anime/generations',

  // Health Checks
  HEALTH: '/api/anime/health',

  // Quality Assessment
  QUALITY_ASSESS: '/api/anime/quality/assess',
  QUALITY_STANDARDS: '/api/anime/quality/standards',

  // Git Operations
  GIT_STATUS: '/api/anime/git/status',
  GIT_COMMIT: '/api/anime/git/commit',
  GIT_BRANCH: '/api/anime/git/branch'
}

// WebSocket Configuration
export const WS = {
  URL: API_HOSTS.websocket,
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

// Helper function to build full URL
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
  hosts: API_HOSTS
}

export default API
