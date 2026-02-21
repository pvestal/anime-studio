/**
 * Training domain: datasets, approvals, feedback, training jobs, ingestion, voice extraction.
 * Backend: /api/training/* (main), /api/audio/* (voice extraction endpoints)
 */
import type {
  DatasetImage,
  PendingImage,
  TrainingJob,
  ApprovalRequest,
  TrainingRequest,
  ImageMetadata,
  RegenerateRequest,
  SceneTimeline,
  VoiceMap,
  TextExtraction,
  LoraFile,
  IdentifyResult,
} from '@/types'
import { createRequest, ApiError } from './base'

const request = createRequest('/api/training')
const audioRequest = createRequest('/api/audio')
const TRAINING_BASE = '/api/training'

export const trainingApi = {
  // --- Dataset ---

  async getCharacterDataset(characterName: string): Promise<{ character: string; images: DatasetImage[] }> {
    return request(`/dataset/${encodeURIComponent(characterName)}`)
  },

  async getImageMetadata(characterSlug: string, imageName: string): Promise<ImageMetadata> {
    return request(`/dataset/${encodeURIComponent(characterSlug)}/image/${encodeURIComponent(imageName)}/metadata`)
  },

  imageUrl(characterSlug: string, imageName: string): string {
    return `${TRAINING_BASE}/dataset/${encodeURIComponent(characterSlug)}/image/${encodeURIComponent(imageName)}`
  },

  async identifyCharacter(characterSlug: string, imageName: string): Promise<IdentifyResult> {
    return request(`/identify/${encodeURIComponent(characterSlug)}/${encodeURIComponent(imageName)}`)
  },

  // --- Approval ---

  async getPendingApprovals(): Promise<{ pending_images: PendingImage[]; character_designs?: Record<string, string> }> {
    return request('/approval/pending')
  },

  async approveImage(approval: ApprovalRequest): Promise<{ message: string; regeneration_queued?: boolean }> {
    return request('/approval/approve', {
      method: 'POST',
      body: JSON.stringify(approval),
    })
  },

  async reassignImage(params: { character_slug: string; image_name: string; target_character_slug: string }): Promise<{ message: string; source: string; target: string }> {
    return request('/approval/reassign', {
      method: 'POST',
      body: JSON.stringify(params),
    })
  },

  async bulkReject(params: { character_slug: string; criteria: string; quality_threshold?: number; dry_run?: boolean }): Promise<{
    dry_run: boolean; character_slug: string; criteria: string; matched_count?: number; rejected_count?: number; matched_images?: string[]; rejected_images?: string[]
  }> {
    return request('/approval/bulk-reject', {
      method: 'POST',
      body: JSON.stringify(params),
    })
  },

  // --- Regeneration ---

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

  // --- Variant Generation ---

  async generateVariant(characterSlug: string, imageName: string, params: {
    count?: number; weight?: number; denoise?: number;
    prompt_override?: string; seed_offset?: number;
  } = {}): Promise<{ message: string; reference_image: string; variants: Array<{ prompt_id?: string; seed?: number; error?: string }> }> {
    return request(`/variant/${encodeURIComponent(characterSlug)}/${encodeURIComponent(imageName)}`, {
      method: 'POST',
      body: JSON.stringify(params),
    })
  },

  // --- IPAdapter Refinement (legacy — prefer generateVariant) ---

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

  // --- Reference Images ---

  async getReferenceImages(slug: string): Promise<{ character_slug: string; images: string[]; count: number }> {
    return request(`/characters/${encodeURIComponent(slug)}/reference-images`)
  },

  async addReferenceImage(slug: string, imageName: string): Promise<{ message: string }> {
    return request(`/characters/${encodeURIComponent(slug)}/reference-images`, {
      method: 'POST',
      body: JSON.stringify({ image_name: imageName }),
    })
  },

  async removeReferenceImage(slug: string, imageName: string): Promise<{ message: string }> {
    return request(`/characters/${encodeURIComponent(slug)}/reference-images/${encodeURIComponent(imageName)}`, {
      method: 'DELETE',
    })
  },

  // --- Feedback ---

  async getFeedback(characterSlug: string): Promise<{ character: string; rejection_count: number; negative_additions: string[] }> {
    return request(`/feedback/${encodeURIComponent(characterSlug)}`)
  },

  async clearFeedback(characterSlug: string): Promise<{ message: string }> {
    return request(`/feedback/${encodeURIComponent(characterSlug)}`, { method: 'DELETE' })
  },

  // --- Training Jobs (paths stripped: /training/jobs → /jobs since mount provides /api/training) ---

  async getTrainingJobs(): Promise<{ training_jobs: TrainingJob[] }> {
    return request('/jobs')
  },

  async startTraining(training: TrainingRequest): Promise<{ message: string; job_id: string; approved_images: number }> {
    return request('/start', {
      method: 'POST',
      body: JSON.stringify(training),
    })
  },

  async cancelTrainingJob(jobId: string): Promise<{ message: string }> {
    return request(`/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' })
  },

  async deleteTrainingJob(jobId: string): Promise<{ message: string }> {
    return request(`/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' })
  },

  async retryTrainingJob(jobId: string): Promise<{ message: string; job_id: string }> {
    return request(`/jobs/${encodeURIComponent(jobId)}/retry`, { method: 'POST' })
  },

  async invalidateTrainingJob(jobId: string, deleteLora: boolean = false): Promise<{ message: string; lora_deleted: boolean }> {
    return request(`/jobs/${encodeURIComponent(jobId)}/invalidate?delete_lora=${deleteLora}`, { method: 'POST' })
  },

  async clearFinishedJobs(days: number = 7): Promise<{ message: string; removed: number; remaining: number }> {
    return request(`/jobs/clear-finished?days=${days}`, { method: 'POST' })
  },

  async reconcileJobs(): Promise<{ message: string; reconciled: number }> {
    return request('/reconcile', { method: 'POST' })
  },

  async getTrainedLoras(): Promise<{ loras: LoraFile[] }> {
    return request('/loras')
  },

  async deleteTrainedLora(slug: string): Promise<{ message: string }> {
    return request(`/loras/${encodeURIComponent(slug)}`, { method: 'DELETE' })
  },

  // --- Clear stuck generations (in training/ingest router) ---

  async clearStuckGenerations(): Promise<{ message: string; cancelled: number }> {
    return request('/generate/clear-stuck', { method: 'POST' })
  },

  // --- Ingestion ---

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
    const response = await fetch(`${TRAINING_BASE}/ingest/image?character_slug=${encodeURIComponent(characterSlug)}`, {
      method: 'POST',
      body: formData,
    })
    if (!response.ok) throw new ApiError(response.status, await response.text())
    return response.json()
  },

  async ingestVideo(file: File, characterSlug: string, fps: number = 0.5): Promise<{ frames_extracted: number; character: string }> {
    const formData = new FormData()
    formData.append('file', file)
    const response = await fetch(`${TRAINING_BASE}/ingest/video?character_slug=${encodeURIComponent(characterSlug)}&fps=${fps}`, {
      method: 'POST',
      body: formData,
    })
    if (!response.ok) throw new ApiError(response.status, await response.text())
    return response.json()
  },

  async scanComfyUI(): Promise<{ new_images: number; matched: Record<string, number>; unmatched_count: number }> {
    return request('/ingest/scan-comfyui', { method: 'POST' })
  },

  async getSourceAnalysis(projectName: string): Promise<{ source_analysis: Record<string, unknown> }> {
    return request(`/ingest/source-analysis/${encodeURIComponent(projectName)}`)
  },

  async synthesizeContext(projectName: string): Promise<{ project_name: string; source_analysis: Record<string, unknown>; synthesis: Record<string, unknown> }> {
    return request(`/ingest/synthesize-context/${encodeURIComponent(projectName)}`, { method: 'POST' })
  },

  async ingestLocalVideo(path: string, projectName: string, maxFrames: number = 200, fps: number = 4): Promise<{
    frames_extracted: number; frames_matched?: number; per_character?: Record<string, number>;
    project: string; file_size_mb: number; status: string
  }> {
    return request('/ingest/local-video', {
      method: 'POST',
      body: JSON.stringify({ path, project_name: projectName, max_frames: maxFrames, fps }),
    })
  },

  uploadMovie(file: File, projectName: string, onProgress?: (pct: number) => void): Promise<{
    path: string; filename: string; size_mb: number; project_name: string; status: string
  }> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${TRAINING_BASE}/ingest/movie-upload?project_name=${encodeURIComponent(projectName)}`)

      if (onProgress) {
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
        })
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText))
        } else {
          reject(new ApiError(xhr.status, xhr.responseText))
        }
      }
      xhr.onerror = () => reject(new ApiError(0, 'Network error during movie upload'))

      const formData = new FormData()
      formData.append('file', file)
      xhr.send(formData)
    })
  },

  async listMovies(): Promise<{ movies: Array<{ filename: string; path: string; size_mb: number }> }> {
    return request('/ingest/movies')
  },

  async extractMovie(path: string, projectName: string, maxFrames: number = 500, fps: number = 4): Promise<{
    status: string; file: string; file_size_mb: number; project: string; characters: number; message: string
  }> {
    return request('/ingest/movie-extract', {
      method: 'POST',
      body: JSON.stringify({ path, project_name: projectName, max_frames: maxFrames, fps }),
    })
  },

  // --- Content Reconstruction ---

  async getSceneTimeline(projectName: string): Promise<SceneTimeline> {
    return request(`/ingest/timeline/${encodeURIComponent(projectName)}`)
  },

  async getVoiceMap(projectName: string): Promise<VoiceMap> {
    return request(`/ingest/voice-map/${encodeURIComponent(projectName)}`)
  },

  async getTextExtraction(projectName: string): Promise<TextExtraction> {
    return request(`/ingest/text/${encodeURIComponent(projectName)}`)
  },

  // --- Audio/Voice extraction (audio_composition package → /api/audio) ---

  async ingestVoice(url: string, projectName: string, minDuration: number = 0.5, maxDuration: number = 30): Promise<{
    segments_extracted: number; project: string; voice_dir: string;
    segments: Array<{ filename: string; start: number; end: number; duration: number }>
  }> {
    return audioRequest('/ingest/voice', {
      method: 'POST',
      body: JSON.stringify({ url, project_name: projectName, min_duration: minDuration, max_duration: maxDuration }),
    })
  },

  async listVoiceSegments(projectName: string): Promise<{
    project: string; total_segments: number; source_url?: string;
    segments: Array<{ filename: string; start: number; end: number; duration: number; size_kb?: number }>
  }> {
    return audioRequest(`/voice/${encodeURIComponent(projectName)}`)
  },

  voiceSegmentUrl(projectName: string, filename: string): string {
    return `/api/audio/voice/${encodeURIComponent(projectName)}/segment/${encodeURIComponent(filename)}`
  },

  async transcribeVoice(projectName: string, model: string = 'base'): Promise<{
    project: string; total: number; transcribed: number; characters_matched: number;
    transcriptions: Array<{ filename: string; text: string; language: string; matched_character: string | null }>
  }> {
    return audioRequest(`/voice/${encodeURIComponent(projectName)}/transcribe`, {
      method: 'POST',
      body: JSON.stringify({ model }),
    })
  },

  // --- Library ---

  async getLibrary(): Promise<{
    images: Array<{ slug: string; characterName: string; name: string; project_name: string; checkpoint_model: string }>
    characters: Array<{ slug: string; name: string; approved: number; project_name: string; checkpoint_model: string }>
    projects: string[]
    models: string[]
  }> {
    return request('/library')
  },

  // --- Ingestion progress ---

  async getIngestProgress(): Promise<Record<string, unknown>> {
    return request('/ingest/progress')
  },
}
