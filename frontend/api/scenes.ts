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
  MusicSuggestion,
  PlaylistProfile,
  CuratedPlaylist,
  CuratedPlaylistTrack,
  PendingVideo,
  VideoReviewRequest,
  BatchVideoReviewRequest,
  EngineStats,
  EngineBlacklistEntry,
} from '@/types'
import { createRequest } from './base'

const request = createRequest('/api/scenes')
const genRequest = createRequest('/api')
const audioRequest = createRequest('/api/audio')
const voiceRequest = createRequest('/api/voice')
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

  async generateScenesFromStory(projectId: number, episodeId?: string): Promise<{
    project_id: number
    scenes: Array<{
      scene_id: string; scene_number: number; title: string;
      shots_created: number; shot_ids: string[]
    }>
    count: number
  }> {
    let url = `/generate-from-story?project_id=${projectId}`
    if (episodeId) url += `&episode_id=${episodeId}`
    return request(url, { method: 'POST' })
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

  // --- Music Pipeline (via anime-studio proxy → Echo Brain) ---

  async suggestMusicForScene(sceneMood: string, sceneDescription?: string, timeOfDay?: string): Promise<MusicSuggestion> {
    return audioRequest('/suggest-music', {
      method: 'POST',
      body: JSON.stringify({
        scene_mood: sceneMood,
        scene_description: sceneDescription || '',
        time_of_day: timeOfDay || '',
      }),
    })
  },

  async analyzePlaylist(playlistId: string): Promise<PlaylistProfile> {
    return audioRequest('/analyze-playlist', {
      method: 'POST',
      body: JSON.stringify({ playlist_id: playlistId }),
    })
  },

  async generateFromPlaylist(playlistId: string, mode: string = 'style_matched', duration: number = 60): Promise<{
    task_id: string; status: string; profile: PlaylistProfile; prompt: string; mode: string
  }> {
    return audioRequest('/generate-from-playlist', {
      method: 'POST',
      body: JSON.stringify({ playlist_id: playlistId, mode, duration }),
    })
  },

  async listCuratedPlaylists(): Promise<{ playlists: CuratedPlaylist[] }> {
    return audioRequest('/curated-playlists')
  },

  async createCuratedPlaylist(name: string, description?: string): Promise<CuratedPlaylist> {
    return audioRequest('/curated-playlists', {
      method: 'POST',
      body: JSON.stringify({ name, description }),
    })
  },

  async deleteCuratedPlaylist(playlistId: number): Promise<{ message: string }> {
    return audioRequest(`/curated-playlists/${playlistId}`, { method: 'DELETE' })
  },

  async getCuratedPlaylistTracks(playlistId: number): Promise<{ playlist_id: number; tracks: CuratedPlaylistTrack[] }> {
    return audioRequest(`/curated-playlists/${playlistId}/tracks`)
  },

  async addToCuratedPlaylist(playlistId: number, track: {
    track_id: string; name: string; artist: string; preview_url: string; source: string
  }): Promise<{ id: number; playlist_id: number; position: number }> {
    return audioRequest(`/curated-playlists/${playlistId}/tracks`, {
      method: 'POST',
      body: JSON.stringify(track),
    })
  },

  async removeFromCuratedPlaylist(playlistId: number, trackId: string): Promise<{ message: string }> {
    return audioRequest(`/curated-playlists/${playlistId}/tracks/${encodeURIComponent(trackId)}`, {
      method: 'DELETE',
    })
  },

  async mixSceneAudio(sceneId: string): Promise<{ output_path: string; ducking_applied: boolean }> {
    return audioRequest('/mix-scene-audio', {
      method: 'POST',
      body: JSON.stringify({ scene_id: sceneId }),
    })
  },

  // --- Video Review ---

  async getPendingVideos(filters?: {
    project_id?: number; video_engine?: string; character_slug?: string
  }): Promise<{ pending_videos: PendingVideo[]; total: number }> {
    const params = new URLSearchParams()
    if (filters?.project_id) params.set('project_id', String(filters.project_id))
    if (filters?.video_engine) params.set('video_engine', filters.video_engine)
    if (filters?.character_slug) params.set('character_slug', filters.character_slug)
    const qs = params.toString()
    return request(`/pending-videos${qs ? '?' + qs : ''}`)
  },

  async reviewVideo(data: VideoReviewRequest): Promise<{
    message: string; shot_id: string; review_status: string; engine_blacklisted: boolean
  }> {
    return request('/review-video', { method: 'POST', body: JSON.stringify(data) })
  },

  async batchReviewVideo(data: BatchVideoReviewRequest): Promise<{
    message: string; updated: number; total: number; review_status: string
  }> {
    return request('/batch-review-video', { method: 'POST', body: JSON.stringify(data) })
  },

  async getEngineStats(filters?: {
    project_id?: number; character_slug?: string
  }): Promise<{ engine_stats: EngineStats[]; blacklist: EngineBlacklistEntry[] }> {
    const params = new URLSearchParams()
    if (filters?.project_id) params.set('project_id', String(filters.project_id))
    if (filters?.character_slug) params.set('character_slug', filters.character_slug)
    const qs = params.toString()
    return request(`/engine-stats${qs ? '?' + qs : ''}`)
  },

  // --- Voice Synthesis ---

  async synthesizeShotDialogue(shotId: string, engine?: string): Promise<{
    output_path: string; engine_used: string; duration_seconds: number;
    character_slug: string; text: string; job_id: string
  }> {
    const qs = engine ? `?engine=${encodeURIComponent(engine)}` : ''
    return voiceRequest(`/shot/${shotId}/synthesize${qs}`, { method: 'POST', timeoutMs: 130000 })
  },

  synthesisAudioUrl(jobId: string): string {
    return `/api/voice/synthesis/${jobId}/audio`
  },

  sceneDialogueAudioUrl(sceneId: string): string {
    return `${SCENES_BASE}/${sceneId}/dialogue-audio`
  },

  async getSceneDialogueStatus(sceneId: string): Promise<{
    scene_id: string; has_dialogue_audio: boolean; dialogue_audio_path: string | null
  }> {
    return request(`/${sceneId}/dialogue-status`)
  },

  async synthesizeEpisodeDialogue(episodeId: string): Promise<{
    episode_id: string; scenes_processed: number; scenes_skipped: number;
    scenes_failed: number; total_scenes: number; results: Array<{
      scene_id: string; position: number; title: string; status: string;
      dialogue_audio_path?: string; error?: string; reason?: string
    }>
  }> {
    return voiceRequest(`/episode/${episodeId}/synthesize-all`, { method: 'POST', timeoutMs: 300000 })
  },

  async getVoiceModels(characterSlug: string): Promise<{
    character_slug: string; available_engines: Array<{ engine: string; quality: string }>;
    preferred_engine: string | null; voice_preset: string | null
  }> {
    return voiceRequest(`/models/${characterSlug}`)
  },
}
