/**
 * Scene Builder domain: scene CRUD, shot CRUD, generation, assembly, audio.
 * Backend: /api/scenes/* (scene_router mounted at /api with /scenes prefix in decorators)
 */
import type {
  BuilderScene,
  SceneCreateRequest,
  ShotCreateRequest,
  SceneGenerationStatus,
  ApprovedImagesResponse,
  AppleMusicTrack,
  AppleMusicPlaylist,
  SceneRecommendationsResponse,
  WanModelsStatus,
  WanGenerateParams,
  WanGenerateResponse,
  MusicGenerateRequest,
  MusicGenerateResponse,
  MusicTaskStatus,
  MusicTrack,
} from '@/types'
import { createRequest } from './base'

const request = createRequest('/api/scenes')
const genRequest = createRequest('/api')
const audioRequest = createRequest('/api/audio')
const SCENES_BASE = '/api/scenes'
const MUSIC_API = '/api/music'

export const scenesApi = {
  async listScenes(projectId: number): Promise<{ scenes: BuilderScene[] }> {
    return request(`?project_id=${projectId}`)
  },

  async createScene(data: SceneCreateRequest): Promise<{ id: string; scene_number: number }> {
    return request('', { method: 'POST', body: JSON.stringify(data) })
  },

  async getScene(sceneId: string): Promise<BuilderScene> {
    return request(`/${sceneId}`)
  },

  async updateScene(sceneId: string, data: Partial<SceneCreateRequest>): Promise<{ message: string }> {
    return request(`/${sceneId}`, { method: 'PATCH', body: JSON.stringify(data) })
  },

  async deleteScene(sceneId: string): Promise<{ message: string }> {
    return request(`/${sceneId}`, { method: 'DELETE' })
  },

  async createShot(sceneId: string, data: ShotCreateRequest): Promise<{ id: string; shot_number: number }> {
    return request(`/${sceneId}/shots`, { method: 'POST', body: JSON.stringify(data) })
  },

  async updateShot(sceneId: string, shotId: string, data: Partial<ShotCreateRequest>): Promise<{ message: string }> {
    return request(`/${sceneId}/shots/${shotId}`, { method: 'PATCH', body: JSON.stringify(data) })
  },

  async deleteShot(sceneId: string, shotId: string): Promise<{ message: string }> {
    return request(`/${sceneId}/shots/${shotId}`, { method: 'DELETE' })
  },

  async generateScene(sceneId: string): Promise<{ message: string; total_shots: number; estimated_minutes: number }> {
    return request(`/${sceneId}/generate`, { method: 'POST' })
  },

  async getSceneStatus(sceneId: string): Promise<SceneGenerationStatus> {
    return request(`/${sceneId}/status`)
  },

  async regenerateShot(sceneId: string, shotId: string): Promise<{ message: string; comfyui_prompt_id: string }> {
    return request(`/${sceneId}/shots/${shotId}/regenerate`, { method: 'POST' })
  },

  async assembleScene(sceneId: string): Promise<{ message: string; video_path: string; duration_seconds: number; shots_included: number }> {
    return request(`/${sceneId}/assemble`, { method: 'POST' })
  },

  sceneVideoUrl(sceneId: string): string {
    return `${SCENES_BASE}/${sceneId}/video`
  },

  shotVideoUrl(sceneId: string, shotId: string): string {
    return `${SCENES_BASE}/${sceneId}/shots/${shotId}/video`
  },

  async getApprovedImagesForScene(sceneId: string, projectId: number): Promise<ApprovedImagesResponse> {
    return request(`/${sceneId}/approved-images?project_id=${projectId}`)
  },

  async getApprovedImagesWithMetadata(sceneId: string, projectId: number): Promise<ApprovedImagesResponse> {
    return request(`/${sceneId}/approved-images?project_id=${projectId}&include_metadata=true`)
  },

  async getShotRecommendations(sceneId: string, topN: number = 5): Promise<SceneRecommendationsResponse> {
    return request(`/${sceneId}/shot-recommendations?top_n=${topN}`)
  },

  // --- Story to Scenes ---

  async generateScenesFromStory(projectId: number): Promise<{
    project_id: number
    scenes: Array<{
      title: string; description: string; location: string;
      time_of_day: string; mood: string; characters: string[]
      suggested_shots: Array<{
        shot_type: string; description: string; motion_prompt: string; duration_seconds: number
      }>
    }>
    count: number
  }> {
    return request(`/generate-from-story?project_id=${projectId}`, { method: 'POST' })
  },

  // --- Motion Presets ---

  async getMotionPresets(shotType?: string): Promise<{ presets: string[] | Record<string, string[]>; shot_type?: string }> {
    const q = shotType ? `?shot_type=${encodeURIComponent(shotType)}` : ''
    return request(`/motion-presets${q}`)
  },

  // --- Scene Audio ---

  async setSceneAudio(sceneId: string, data: {
    track_id: string; preview_url: string; track_name: string; track_artist: string;
    fade_in?: number; fade_out?: number; start_offset?: number;
  }): Promise<{ message: string }> {
    return request(`/${sceneId}/audio`, { method: 'POST', body: JSON.stringify(data) })
  },

  async removeSceneAudio(sceneId: string): Promise<{ message: string }> {
    return request(`/${sceneId}/audio`, { method: 'DELETE' })
  },

  // --- Apple Music (via Echo Brain /api/music) ---

  async getAppleMusicStatus(): Promise<{ authorized: boolean; user_id?: string }> {
    const resp = await fetch(`${MUSIC_API}/status`)
    if (!resp.ok) throw new Error('Music status check failed')
    return resp.json()
  },

  async getAppleMusicPlaylists(): Promise<{ data: AppleMusicPlaylist[] }> {
    const resp = await fetch(`${MUSIC_API}/playlists`)
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(err.detail || `Playlists failed (${resp.status})`)
    }
    const raw = await resp.json()
    const data = (raw.data || []).map((pl: { id: string; attributes?: { name?: string; description?: { standard?: string } } }) => ({
      id: pl.id,
      name: pl.attributes?.name || 'Untitled',
      description: pl.attributes?.description?.standard || null,
    }))
    return { data }
  },

  async getPlaylistTracks(playlistId: string): Promise<{ playlist_id: string; tracks: AppleMusicTrack[]; total: number }> {
    const resp = await fetch(`${MUSIC_API}/playlists/${playlistId}/tracks`)
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(err.detail || `Tracks failed (${resp.status})`)
    }
    return resp.json()
  },

  async searchAppleMusic(query: string): Promise<Record<string, unknown>> {
    const resp = await fetch(`${MUSIC_API}/search?q=${encodeURIComponent(query)}&types=songs&limit=10`)
    if (!resp.ok) throw new Error('Search failed')
    return resp.json()
  },

  // --- Wan T2V ---

  async getWanModels(): Promise<WanModelsStatus> {
    return genRequest('/generate/wan/models')
  },

  async generateWan(params: WanGenerateParams): Promise<WanGenerateResponse> {
    const qs = new URLSearchParams({ prompt: params.prompt })
    if (params.width) qs.set('width', String(params.width))
    if (params.height) qs.set('height', String(params.height))
    if (params.num_frames) qs.set('num_frames', String(params.num_frames))
    if (params.fps) qs.set('fps', String(params.fps))
    if (params.steps) qs.set('steps', String(params.steps))
    if (params.cfg) qs.set('cfg', String(params.cfg))
    if (params.seed != null) qs.set('seed', String(params.seed))
    if (params.use_gguf !== undefined) qs.set('use_gguf', String(params.use_gguf))
    return genRequest(`/generate/wan?${qs}`, { method: 'POST' })
  },

  // --- ACE-Step Music Generation ---

  async generateMusic(params: MusicGenerateRequest): Promise<MusicGenerateResponse> {
    return audioRequest('/generate-music', { method: 'POST', body: JSON.stringify(params) })
  },

  async getMusicTaskStatus(taskId: string): Promise<MusicTaskStatus> {
    return audioRequest(`/generate-music/${taskId}/status`)
  },

  async listGeneratedMusic(): Promise<{ tracks: MusicTrack[]; total: number }> {
    return audioRequest('/music')
  },

  generatedMusicUrl(filename: string): string {
    return `/api/audio/music/${encodeURIComponent(filename)}`
  },
}
