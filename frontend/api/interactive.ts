import { createRequest } from './base'

const request = createRequest('/api/interactive')

export interface InteractiveDialogue {
  character: string
  text: string
  emotion: string
}

export interface InteractiveChoice {
  text: string
  tone: string
}

export interface InteractiveEffect {
  type: string
  target: string
  value: string | number | boolean
}

export interface InteractiveScene {
  scene_index: number
  narration: string
  image_prompt: string
  dialogue: InteractiveDialogue[]
  choices: InteractiveChoice[]
  story_effects: InteractiveEffect[]
  is_ending: boolean
  ending_type: string | null
  chosen_text?: string
}

export interface InteractiveImageStatus {
  status: 'pending' | 'generating' | 'ready' | 'failed'
  progress: number
  url: string | null
}

export interface InteractiveSession {
  session_id: string
  project_id: number
  project_name: string
  scene_count: number
  current_scene_index: number
  is_ended: boolean
  relationships?: Record<string, number>
  variables?: Record<string, string | number | boolean>
  created_at?: number
}

export const interactiveApi = {
  async startSession(projectId: number, characterSlugs?: string[]): Promise<{
    session_id: string
    scene: InteractiveScene
    image: InteractiveImageStatus
  }> {
    return request('/sessions', {
      method: 'POST',
      body: JSON.stringify({
        project_id: projectId,
        character_slugs: characterSlugs || null,
      }),
      timeoutMs: 120000, // Ollama can take a while
    })
  },

  async listSessions(): Promise<{ sessions: InteractiveSession[] }> {
    return request('/sessions')
  },

  async getSession(sessionId: string): Promise<InteractiveSession> {
    return request(`/sessions/${sessionId}`)
  },

  async deleteSession(sessionId: string): Promise<{ message: string }> {
    return request(`/sessions/${sessionId}`, { method: 'DELETE' })
  },

  async getCurrentScene(sessionId: string): Promise<{
    scene: InteractiveScene
    image: InteractiveImageStatus
  }> {
    return request(`/sessions/${sessionId}/scene`)
  },

  async submitChoice(sessionId: string, choiceIndex: number): Promise<{
    scene: InteractiveScene
    image: InteractiveImageStatus
    session_ended: boolean
  }> {
    return request(`/sessions/${sessionId}/choose`, {
      method: 'POST',
      body: JSON.stringify({ choice_index: choiceIndex }),
      timeoutMs: 120000,
    })
  },

  async getImageStatus(sessionId: string, sceneIdx: number): Promise<InteractiveImageStatus> {
    return request(`/sessions/${sessionId}/image/${sceneIdx}`)
  },

  imageFileUrl(sessionId: string, sceneIdx: number): string {
    return `/api/interactive/sessions/${sessionId}/image/${sceneIdx}/file`
  },

  async getHistory(sessionId: string): Promise<{
    scenes: InteractiveScene[]
    relationships: Record<string, number>
    variables: Record<string, string | number | boolean>
    is_ended: boolean
  }> {
    return request(`/sessions/${sessionId}/history`)
  },
}
