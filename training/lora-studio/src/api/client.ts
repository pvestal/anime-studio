import type { Character, DatasetImage, PendingImage, TrainingJob, ApprovalRequest, TrainingRequest, CharacterUpdate, ImageMetadata, RegenerateRequest, GalleryImage, GenerateParams, GenerateResponse, GenerationStatus, EchoChatResponse, EchoEnhanceResponse } from '@/types'

const API_BASE = '/api/lora'

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new ApiError(response.status, errorText)
  }

  return response.json()
}

export const api = {
  // Characters
  async getCharacters(): Promise<{ characters: Character[] }> {
    return request('/characters')
  },

  // Dataset
  async getCharacterDataset(characterName: string): Promise<{ character: string; images: DatasetImage[] }> {
    return request(`/dataset/${encodeURIComponent(characterName)}`)
  },

  // Approval
  async getPendingApprovals(): Promise<{ pending_images: PendingImage[] }> {
    return request('/approval/pending')
  },

  async approveImage(approval: ApprovalRequest): Promise<{ message: string; regeneration_queued?: boolean }> {
    return request('/approval/approve', {
      method: 'POST',
      body: JSON.stringify(approval),
    })
  },

  async updateCharacter(slug: string, update: CharacterUpdate): Promise<{ message: string; design_prompt: string }> {
    return request(`/characters/${encodeURIComponent(slug)}`, {
      method: 'PATCH',
      body: JSON.stringify(update),
    })
  },

  async getImageMetadata(characterSlug: string, imageName: string): Promise<ImageMetadata> {
    return request(`/dataset/${encodeURIComponent(characterSlug)}/image/${encodeURIComponent(imageName)}/metadata`)
  },

  async regenerate(characterSlug: string, count: number = 1): Promise<{ message: string }> {
    return request(`/regenerate/${encodeURIComponent(characterSlug)}?count=${count}`, {
      method: 'POST',
    })
  },

  async regenerateCustom(params: RegenerateRequest): Promise<{ message: string }> {
    const qp = new URLSearchParams()
    if (params.count) qp.set('count', String(params.count))
    if (params.seed) qp.set('seed', String(params.seed))
    if (params.prompt_override) qp.set('prompt_override', params.prompt_override)
    return request(`/regenerate/${encodeURIComponent(params.slug)}?${qp.toString()}`, {
      method: 'POST',
    })
  },

  // Training
  async getTrainingJobs(): Promise<{ training_jobs: TrainingJob[] }> {
    return request('/training/jobs')
  },

  async startTraining(training: TrainingRequest): Promise<{ message: string; job_id: string; approved_images: number }> {
    return request('/training/start', {
      method: 'POST',
      body: JSON.stringify(training),
    })
  },

  // IPAdapter refinement
  async refineImage(params: {
    character_slug: string
    reference_image: string
    prompt_override?: string
    count?: number
    weight?: number
    denoise?: number
  }): Promise<{ message: string; results: Array<{ prompt_id?: string; seed?: number; error?: string }> }> {
    return request('/refine', {
      method: 'POST',
      body: JSON.stringify(params),
    })
  },

  // Projects
  async getProjects(): Promise<{ projects: Array<{ id: number; name: string; default_style: string; character_count: number }> }> {
    return request('/projects')
  },

  // Feedback
  async getFeedback(characterSlug: string): Promise<{ character: string; rejection_count: number; negative_additions: string[] }> {
    return request(`/feedback/${encodeURIComponent(characterSlug)}`)
  },

  async clearFeedback(characterSlug: string): Promise<{ message: string }> {
    return request(`/feedback/${encodeURIComponent(characterSlug)}`, { method: 'DELETE' })
  },

  // Ingestion
  async ingestYoutube(url: string, characterSlug: string, maxFrames: number = 20, fps: number = 2): Promise<{ frames_extracted: number; character: string }> {
    return request('/ingest/youtube', {
      method: 'POST',
      body: JSON.stringify({ url, character_slug: characterSlug, max_frames: maxFrames, fps }),
    })
  },

  async ingestYoutubeProject(url: string, projectName: string, maxFrames: number = 60, fps: number = 4): Promise<{
    frames_extracted: number; project: string; characters_seeded: number; per_character: Record<string, number>
  }> {
    return request('/ingest/youtube-project', {
      method: 'POST',
      body: JSON.stringify({ url, project_name: projectName, max_frames: maxFrames, fps }),
    })
  },

  async ingestImage(file: File, characterSlug: string): Promise<{ image: string; character: string }> {
    const formData = new FormData()
    formData.append('file', file)
    const response = await fetch(`${API_BASE}/ingest/image?character_slug=${encodeURIComponent(characterSlug)}`, {
      method: 'POST',
      body: formData,
    })
    if (!response.ok) throw new ApiError(response.status, await response.text())
    return response.json()
  },

  async ingestVideo(file: File, characterSlug: string, fps: number = 0.5): Promise<{ frames_extracted: number; character: string }> {
    const formData = new FormData()
    formData.append('file', file)
    const response = await fetch(`${API_BASE}/ingest/video?character_slug=${encodeURIComponent(characterSlug)}&fps=${fps}`, {
      method: 'POST',
      body: formData,
    })
    if (!response.ok) throw new ApiError(response.status, await response.text())
    return response.json()
  },

  async scanComfyUI(): Promise<{ new_images: number; matched: Record<string, number>; unmatched_count: number }> {
    return request('/ingest/scan-comfyui', { method: 'POST' })
  },

  // Image URL helper
  imageUrl(characterSlug: string, imageName: string): string {
    return `${API_BASE}/dataset/${encodeURIComponent(characterSlug)}/image/${encodeURIComponent(imageName)}`
  },

  // --- Generation ---

  async generateForCharacter(slug: string, params: GenerateParams): Promise<GenerateResponse> {
    return request(`/generate/${encodeURIComponent(slug)}`, {
      method: 'POST',
      body: JSON.stringify(params),
    })
  },

  async getGenerationStatus(promptId: string): Promise<GenerationStatus> {
    return request(`/generate/${encodeURIComponent(promptId)}/status`)
  },

  async clearStuckGenerations(): Promise<{ message: string; cancelled: number }> {
    return request('/generate/clear-stuck', { method: 'POST' })
  },

  // --- Gallery ---

  async getGallery(limit: number = 50): Promise<{ images: GalleryImage[] }> {
    return request(`/gallery?limit=${limit}`)
  },

  galleryImageUrl(filename: string): string {
    return `${API_BASE}/gallery/image/${encodeURIComponent(filename)}`
  },

  // --- Echo Brain ---

  async echoChat(message: string, characterSlug?: string): Promise<EchoChatResponse> {
    return request('/echo/chat', {
      method: 'POST',
      body: JSON.stringify({ message, character_slug: characterSlug }),
    })
  },

  async echoEnhancePrompt(prompt: string, characterSlug?: string): Promise<EchoEnhanceResponse> {
    return request('/echo/enhance-prompt', {
      method: 'POST',
      body: JSON.stringify({ prompt, character_slug: characterSlug }),
    })
  },

  async echoStatus(): Promise<{ status: string }> {
    return request('/echo/status')
  },
}
