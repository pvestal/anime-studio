/**
 * Story domain: projects, characters, storylines, styles, world settings, checkpoints.
 * Backend: /api/story/*
 */
import type {
  Character,
  CharacterCreate,
  CharacterUpdate,
  Project,
  ProjectCreate,
  ProjectUpdate,
  StorylineUpsert,
  StyleUpdate,
  StyleHistoryEntry,
  StyleCheckpointStats,
  WorldSettings,
  WorldSettingsUpsert,
  CheckpointFile,
} from '@/types'
import { createRequest } from './base'

const request = createRequest('/api/story')

export const storyApi = {
  // --- Characters ---

  async getCharacters(): Promise<{ characters: Character[] }> {
    return request('/characters')
  },

  async createCharacter(data: CharacterCreate): Promise<{ message: string; slug: string }> {
    return request('/characters', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  async updateCharacter(slug: string, update: CharacterUpdate): Promise<{ message: string; design_prompt: string }> {
    return request(`/characters/${encodeURIComponent(slug)}`, {
      method: 'PATCH',
      body: JSON.stringify(update),
    })
  },

  // --- Projects ---

  async getProjects(): Promise<{ projects: Array<{ id: number; name: string; default_style: string; character_count: number }> }> {
    return request('/projects')
  },

  async getProjectDetail(projectId: number): Promise<{ project: Project }> {
    return request(`/projects/${projectId}`)
  },

  async createProject(data: ProjectCreate): Promise<{ project_id: number; style_name: string; message: string }> {
    return request('/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  async updateProject(projectId: number, data: ProjectUpdate): Promise<{ message: string }> {
    return request(`/projects/${projectId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  },

  // --- Storyline ---

  async upsertStoryline(projectId: number, data: StorylineUpsert): Promise<{ message: string }> {
    return request(`/projects/${projectId}/storyline`, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  },

  // --- Style ---

  async updateStyle(projectId: number, data: StyleUpdate): Promise<{ message: string }> {
    return request(`/projects/${projectId}/style`, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  },

  async getStyleHistory(projectId: number): Promise<{ history: StyleHistoryEntry[] }> {
    return request(`/projects/${projectId}/style-history`)
  },

  async getStyleStats(projectId: number): Promise<{ project_name: string; checkpoints: StyleCheckpointStats[] }> {
    return request(`/projects/${projectId}/style-stats`)
  },

  // --- World Settings ---

  async getWorldSettings(projectId: number): Promise<{ world_settings: WorldSettings | null }> {
    return request(`/projects/${projectId}/world`)
  },

  async updateWorldSettings(projectId: number, data: WorldSettingsUpsert): Promise<{ message: string }> {
    return request(`/projects/${projectId}/world`, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  },

  // --- Checkpoints ---

  async getCheckpoints(): Promise<{ checkpoints: CheckpointFile[] }> {
    return request('/checkpoints')
  },
}
