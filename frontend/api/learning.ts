/**
 * Learning & Autonomy domain: quality insights, drift detection, recommendations.
 * Backend: /api/system/* (inline endpoints in app.py)
 *          /api/training/dataset-stats (cross-domain call to training router)
 */
import type {
  LearningStats,
  EventBusStats,
  ParamRecommendation,
  DriftAlert,
  QualityCharacterSummary,
  QualityTrendPoint,
  RejectionPattern,
  CheckpointRanking,
  ReplenishmentStatus,
  ReadinessResponse,
  OrchestratorStatus,
  PipelineStatus,
} from '@/types'
import { createRequest } from './base'

const request = createRequest('/api/system')
const trainingRequest = createRequest('/api/training')

export interface DatasetCharacterStats {
  slug: string
  name: string
  project_name: string
  approved: number
  pending: number
  rejected: number
  total: number
  approval_rate: number
}

export interface DatasetStatsResponse {
  characters: DatasetCharacterStats[]
  totals: { approved: number; pending: number; rejected: number; total: number }
}

export const learningApi = {
  // --- Dataset Stats (from training router — /api/training/dataset-stats) ---

  async getDatasetStats(projectName?: string): Promise<DatasetStatsResponse> {
    const qs = projectName ? `?project_name=${encodeURIComponent(projectName)}` : ''
    return trainingRequest(`/dataset-stats${qs}`)
  },

  // --- Learning System ---

  async getLearningStats(): Promise<LearningStats> {
    return request('/learning/stats')
  },

  async getSuggestions(slug: string): Promise<{ character_slug: string; suggestions: ParamRecommendation | null; reason?: string }> {
    return request(`/learning/suggest/${encodeURIComponent(slug)}`)
  },

  async getRejectionPatterns(slug: string): Promise<{ character_slug: string; patterns: RejectionPattern[] }> {
    return request(`/learning/rejections/${encodeURIComponent(slug)}`)
  },

  async getCheckpointRankings(projectName: string): Promise<{ project_name: string; rankings: CheckpointRanking[] }> {
    return request(`/learning/checkpoints/${encodeURIComponent(projectName)}`)
  },

  async getQualityTrend(params: { character_slug?: string; project_name?: string; days?: number }): Promise<{ trend: QualityTrendPoint[] }> {
    const qs = new URLSearchParams()
    if (params.character_slug) qs.set('character_slug', params.character_slug)
    if (params.project_name) qs.set('project_name', params.project_name)
    if (params.days) qs.set('days', String(params.days))
    return request(`/learning/trend?${qs}`)
  },

  // --- Model Selector & Drift ---

  async getRecommendation(slug: string): Promise<{ character_slug: string; recommendation: ParamRecommendation }> {
    return request(`/recommend/${encodeURIComponent(slug)}`)
  },

  async getDriftAlerts(params?: { character_slug?: string; project_name?: string }): Promise<{ alerts: DriftAlert[]; count: number }> {
    const qs = new URLSearchParams()
    if (params?.character_slug) qs.set('character_slug', params.character_slug)
    if (params?.project_name) qs.set('project_name', params.project_name)
    return request(`/drift?${qs}`)
  },

  async getQualitySummary(projectName: string): Promise<{ project_name: string; characters: QualityCharacterSummary[] }> {
    return request(`/quality/summary/${encodeURIComponent(projectName)}`)
  },

  // --- EventBus ---

  async getEventStats(): Promise<EventBusStats> {
    return request('/events/stats')
  },

  // --- Auto-Correction & Quality Gates ---

  async getCorrectionStats(): Promise<Record<string, unknown>> {
    return request('/correction/stats')
  },

  async toggleAutoCorrection(enabled: boolean): Promise<{ auto_correction_enabled: boolean }> {
    return request(`/correction/toggle?enabled=${enabled}`, { method: 'POST' })
  },

  async getQualityGates(): Promise<{ gates: Record<string, unknown>[] }> {
    return request('/quality/gates')
  },

  async updateQualityGate(gateName: string, threshold?: number, isActive?: boolean): Promise<{ gate_name: string; updated: boolean }> {
    const qs = new URLSearchParams()
    if (threshold !== undefined) qs.set('threshold', String(threshold))
    if (isActive !== undefined) qs.set('is_active', String(isActive))
    return request(`/quality/gates/${encodeURIComponent(gateName)}?${qs}`, { method: 'PUT' })
  },

  // --- Replenishment Loop ---

  async getReplenishmentStatus(): Promise<ReplenishmentStatus> {
    return request('/replenishment/status')
  },

  async toggleReplenishment(enabled: boolean): Promise<{ replenishment_enabled: boolean }> {
    return request(`/replenishment/toggle?enabled=${enabled}`, { method: 'POST' })
  },

  async setReplenishmentTarget(target: number, characterSlug?: string): Promise<{ target: number; scope: string }> {
    const qs = new URLSearchParams({ target: String(target) })
    if (characterSlug) qs.set('character_slug', characterSlug)
    return request(`/replenishment/target?${qs}`, { method: 'POST' })
  },

  async getCharacterReadiness(projectName?: string): Promise<ReadinessResponse> {
    const qs = projectName ? `?project_name=${encodeURIComponent(projectName)}` : ''
    return request(`/replenishment/readiness${qs}`)
  },

  // --- Orchestrator ---

  async getOrchestratorStatus(): Promise<OrchestratorStatus> {
    return request('/orchestrator/status')
  },

  async toggleOrchestrator(enabled: boolean): Promise<{ enabled: boolean }> {
    return request('/orchestrator/toggle', { method: 'POST', body: JSON.stringify({ enabled }) })
  },

  async initializeOrchestrator(projectId: number, trainingTarget?: number): Promise<Record<string, unknown>> {
    return request('/orchestrator/initialize', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, training_target: trainingTarget }),
    })
  },

  async getOrchestratorPipeline(projectId: number): Promise<PipelineStatus> {
    return request(`/orchestrator/pipeline/${projectId}`)
  },

  async getOrchestratorSummary(projectId: number): Promise<{ project_id: number; summary: string }> {
    return request(`/orchestrator/summary/${projectId}`)
  },

  async orchestratorTick(): Promise<Record<string, unknown>> {
    return request('/orchestrator/tick', { method: 'POST' })
  },

  async orchestratorOverride(params: {
    entity_type: 'character' | 'project'
    entity_id: string
    phase: string
    action: 'skip' | 'reset' | 'complete'
  }): Promise<Record<string, unknown>> {
    return request('/orchestrator/override', { method: 'POST', body: JSON.stringify(params) })
  },

  async setTrainingTarget(target: number): Promise<{ training_target: number }> {
    return request('/orchestrator/training-target', { method: 'POST', body: JSON.stringify({ target }) })
  },
}
