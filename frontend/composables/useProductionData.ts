/**
 * Unified data layer for the Produce tab.
 * Merges all data fetching from ProductionStatusTab + AnalyticsTab.
 * Polling: 5s for jobs+GPU, 30s full refresh.
 * Quality data loaded lazily per expanded project.
 */
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { storyApi } from '@/api/story'
import { learningApi } from '@/api/learning'
import { trainingApi } from '@/api/training'
import { scenesApi } from '@/api/scenes'
import { episodesApi } from '@/api/episodes'
import { createRequest } from '@/api/base'
import type {
  TrainingJob,
  LoraFile,
  BuilderScene,
  Episode,
  GpuStatus,
  ProjectSummary,
  CharDetail,
  StageInfo,
  ProjectCard,
  ProjectQualityData,
  ModelBreakdown,
  LearningStats,
  EventBusStats,
  DriftAlert,
  OrchestratorStatus,
  PipelineEntry,
  DatasetStatsResponse,
  DatasetCharacterStats,
} from '@/types'

const systemRequest = createRequest('/api/system')

export function useProductionData() {
  // Core state
  const loading = ref(false)
  const actionLoading = ref<string | null>(null)
  const projects = ref<ProjectSummary[]>([])
  const allLoras = ref<LoraFile[]>([])
  const trainingJobs = ref<TrainingJob[]>([])
  const gpuStatus = ref<GpuStatus | null>(null)
  const expandedProjects = reactive(new Set<number>())

  // Per-project base data (stats, scenes, episodes)
  const projectDataMap = ref<Map<number, {
    stats: DatasetStatsResponse | null
    scenes: BuilderScene[]
    episodes: Episode[]
  }>>(new Map())

  // Per-project quality data (lazy-loaded on expand)
  const qualityDataMap = ref<Map<number, ProjectQualityData>>(new Map())
  const qualityLoadingSet = reactive(new Set<number>())

  // System-level data (analytics)
  const learningStats = ref<LearningStats | null>(null)
  const eventStats = ref<EventBusStats | null>(null)
  const orchestratorStatus = ref<OrchestratorStatus | null>(null)

  let jobPollTimer: ReturnType<typeof setInterval> | null = null
  let fullRefreshTimer: ReturnType<typeof setInterval> | null = null

  // --- GPU computed ---
  const nvidiaBusy = computed(() => {
    if (!gpuStatus.value?.comfyui) return false
    return gpuStatus.value.comfyui.queue_running > 0 || gpuStatus.value.comfyui.queue_pending > 0
  })

  const comfyQueue = computed(() => gpuStatus.value?.comfyui ?? { queue_running: 0, queue_pending: 0 })

  const ollamaModels = computed(() =>
    gpuStatus.value?.ollama?.loaded_models?.map(m => m.name) ?? []
  )

  // --- Training jobs computed ---
  const runningTrainingJobs = computed(() =>
    trainingJobs.value.filter(j => j.status === 'running' || j.status === 'queued')
  )

  const recentFailures = computed(() =>
    trainingJobs.value
      .filter(j => j.status === 'failed')
      .sort((a, b) => new Date(b.failed_at || b.created_at).getTime() - new Date(a.failed_at || a.created_at).getTime())
      .slice(0, 3)
  )

  // --- Build project cards ---
  const projectCards = computed<ProjectCard[]>(() => {
    const loraBySlug = new Map(allLoras.value.map(l => [l.slug, l]))
    const trainingSlugs = new Set(
      runningTrainingJobs.value.map(j => j.character_slug || j.character_name)
    )

    const cards: ProjectCard[] = []

    for (const proj of projects.value) {
      const data = projectDataMap.value.get(proj.id)
      const quality = qualityDataMap.value.get(proj.id)
      const charStats: DatasetCharacterStats[] = data?.stats?.characters ?? []
      const scenes: BuilderScene[] = data?.scenes ?? []
      const episodes: Episode[] = data?.episodes ?? []
      const charCount = charStats.length || proj.character_count

      // Build drift map for character-level drift indicators
      const driftMap = new Map<string, DriftAlert>()
      if (quality?.driftAlerts) {
        for (const alert of quality.driftAlerts) {
          driftMap.set(alert.character_slug, alert)
        }
      }

      // Build character detail with model lineage + quality data
      const characters: CharDetail[] = charStats.map(c => {
        const lora = loraBySlug.get(c.slug)
        let loraStatus: CharDetail['loraStatus'] = 'lora-none'
        if (lora) loraStatus = 'lora-trained'
        else if (trainingSlugs.has(c.slug)) loraStatus = 'lora-training'
        else if (c.approved >= 10) loraStatus = 'lora-ready'

        const modelBreakdown: ModelBreakdown = c.model_breakdown ?? {}
        const dominantModel: string | null = c.dominant_model ?? null
        const isMixedModels: boolean = c.is_mixed_models ?? false
        const loraCheckpoint: string | null = lora?.checkpoint ?? null
        const loraLoss: number | null = lora?.final_loss ?? null
        const loraEpochs: number | null = lora?.trained_epochs ?? null

        const loraModelMismatch = !!(loraCheckpoint && dominantModel &&
          dominantModel !== 'unknown' && dominantModel !== 'no_meta' &&
          loraCheckpoint !== dominantModel)

        // Quality enrichments
        const approvalRate = c.total > 0 ? c.approval_rate : undefined
        const drift = driftMap.get(c.slug)
        let driftStatus: CharDetail['driftStatus'] = null
        if (drift) {
          driftStatus = drift.alert ? 'critical' : 'warn'
        }

        return {
          slug: c.slug, name: c.name, approved: c.approved, loraStatus,
          modelBreakdown, dominantModel, isMixedModels,
          loraCheckpoint, loraLoss, loraEpochs, loraModelMismatch,
          approvalRate, driftStatus,
        }
      })

      const loraCount = characters.filter(c => c.loraStatus === 'lora-trained').length
      const charsNeedingLora = characters.filter(c => c.loraStatus === 'lora-ready')
      const charsWithMixedModels = characters.filter(c => c.isMixedModels)
      const charsWithLoraMismatch = characters.filter(c => c.loraModelMismatch)

      const totalShots = scenes.reduce((s, sc) => s + (sc.total_shots || 0), 0)
      const completedShots = scenes.reduce((s, sc) => s + (sc.completed_shots || 0), 0)
      const assembledEps = episodes.filter(e => e.status === 'assembled' || e.status === 'published').length

      const stages: StageInfo[] = [
        { label: 'Chars', summary: `${charCount}`, pct: charCount > 0 ? 100 : 0 },
        { label: 'Imgs', summary: `${(data?.stats?.totals.approved ?? 0).toLocaleString()}`, pct: charStats.length > 0 ? Math.round((charStats.filter(c => c.approved >= 50).length / charStats.length) * 100) : 0 },
        { label: 'LoRA', summary: `${loraCount}/${charCount}`, pct: charCount > 0 ? Math.round((loraCount / charCount) * 100) : 0 },
        { label: 'Scenes', summary: `${scenes.length}`, pct: scenes.length > 0 ? 100 : 0 },
        { label: 'Video', summary: `${completedShots}/${totalShots}`, pct: totalShots > 0 ? Math.round((completedShots / totalShots) * 100) : 0 },
        { label: 'Eps', summary: `${assembledEps}`, pct: episodes.length > 0 ? Math.round((assembledEps / episodes.length) * 100) : 0 },
      ]

      // Next action
      let nextAction = ''
      if (charCount === 0) nextAction = 'Add characters'
      else if (charsNeedingLora.length > 0) nextAction = `Train LoRAs for ${charsNeedingLora.map(c => c.name).slice(0, 3).join(', ')}${charsNeedingLora.length > 3 ? ' +' + (charsNeedingLora.length - 3) + ' more' : ''}`
      else if (loraCount < charCount) nextAction = `${charCount - loraCount} characters need more approved images before LoRA training`
      else if (scenes.length === 0) nextAction = 'Generate scenes from story'
      else if (totalShots === 0) nextAction = `Add shots to ${scenes.length} scenes`
      else if (completedShots < totalShots) nextAction = `${totalShots - completedShots} shots still need video generation`
      else if (assembledEps === 0 && scenes.length > 0) nextAction = 'Assemble scenes into episodes'
      else if (assembledEps > 0) nextAction = 'Review and publish'

      // Warnings
      const warnings: string[] = []
      if (charsWithMixedModels.length > 0) {
        warnings.push(`${charsWithMixedModels.length} character${charsWithMixedModels.length > 1 ? 's have' : ' has'} images from multiple checkpoints`)
      }
      if (charsWithLoraMismatch.length > 0) {
        warnings.push(`${charsWithLoraMismatch.length} LoRA${charsWithLoraMismatch.length > 1 ? 's' : ''} trained on different checkpoint than image majority`)
      }

      cards.push({
        id: proj.id, name: proj.name, defaultStyle: proj.default_style, charCount, loraCount, characters,
        charsNeedingLora, charsWithMixedModels, charsWithLoraMismatch,
        scenes, totalShots, completedShots,
        episodes, stages, nextAction, warnings,
      })
    }

    return cards
  })

  // --- Data loading ---
  async function loadGpuStatus() {
    try { gpuStatus.value = await systemRequest<GpuStatus>('/gpu/status') } catch { /* optional */ }
  }

  async function loadTrainingJobs() {
    try {
      const resp = await trainingApi.getTrainingJobs()
      trainingJobs.value = resp.training_jobs
    } catch { /* non-critical */ }
  }

  async function loadLoras() {
    try {
      const resp = await trainingApi.getTrainedLoras()
      allLoras.value = resp.loras
    } catch { /* non-critical */ }
  }

  async function loadProjectDetails() {
    const newData = new Map(projectDataMap.value)
    await Promise.all(projects.value.map(async (proj) => {
      const [statsR, scenesR, episodesR] = await Promise.allSettled([
        learningApi.getDatasetStats(proj.name),
        scenesApi.listScenes(proj.id),
        episodesApi.listEpisodes(proj.id),
      ])
      newData.set(proj.id, {
        stats: statsR.status === 'fulfilled' ? statsR.value : null,
        scenes: scenesR.status === 'fulfilled' ? scenesR.value.scenes : [],
        episodes: episodesR.status === 'fulfilled' ? episodesR.value.episodes : [],
      })
    }))
    projectDataMap.value = newData
  }

  async function loadSystemStats() {
    try {
      const [stats, events, orch] = await Promise.allSettled([
        learningApi.getLearningStats(),
        learningApi.getEventStats(),
        learningApi.getOrchestratorStatus(),
      ])
      learningStats.value = stats.status === 'fulfilled' ? stats.value : null
      eventStats.value = events.status === 'fulfilled' ? events.value : null
      orchestratorStatus.value = orch.status === 'fulfilled' ? orch.value : null
    } catch { /* non-critical */ }
  }

  // Lazy-load quality data for a specific project
  async function loadProjectQuality(projectId: number) {
    if (qualityLoadingSet.has(projectId)) return
    qualityLoadingSet.add(projectId)

    const proj = projects.value.find(p => p.id === projectId)
    if (!proj) { qualityLoadingSet.delete(projectId); return }

    try {
      const [rankingsR, driftR, trendR, pipelineR] = await Promise.allSettled([
        learningApi.getCheckpointRankings(proj.name),
        learningApi.getDriftAlerts({ project_name: proj.name }),
        learningApi.getQualityTrend({ project_name: proj.name, days: 14 }),
        learningApi.getOrchestratorPipeline(projectId),
      ])

      // Flatten pipeline entries
      const pipelineEntries: PipelineEntry[] = []
      if (pipelineR.status === 'fulfilled' && pipelineR.value) {
        const data = pipelineR.value
        if (data.characters) {
          for (const [slug, phases] of Object.entries(data.characters as Record<string, PipelineEntry[]>)) {
            for (const p of phases) {
              pipelineEntries.push({ ...p, entity_id: slug, entity_type: 'character' })
            }
          }
        }
        if (data.project_phases) {
          for (const [phase, entry] of Object.entries(data.project_phases as Record<string, PipelineEntry>)) {
            pipelineEntries.push({ ...entry, phase, entity_type: 'project' })
          }
        }
      }

      const newMap = new Map(qualityDataMap.value)
      newMap.set(projectId, {
        driftAlerts: driftR.status === 'fulfilled' ? driftR.value.alerts : [],
        trendData: trendR.status === 'fulfilled' ? trendR.value.trend : [],
        checkpointRankings: rankingsR.status === 'fulfilled' ? rankingsR.value.rankings : [],
        datasetStats: null,
        pipelineEntries,
      })
      qualityDataMap.value = newMap
    } catch { /* non-critical */ }
    finally { qualityLoadingSet.delete(projectId) }
  }

  async function refreshAll() {
    loading.value = true
    try {
      const resp = await storyApi.getProjects()
      projects.value = resp.projects
      if (expandedProjects.size === 0 && resp.projects.length > 0) {
        expandedProjects.add(resp.projects[0].id)
      }
      await Promise.all([loadProjectDetails(), loadTrainingJobs(), loadLoras(), loadGpuStatus(), loadSystemStats()])
      // Reload quality for expanded projects
      for (const id of expandedProjects) {
        loadProjectQuality(id)
      }
    } catch (e) {
      console.error('Failed to refresh:', e)
    } finally {
      loading.value = false
    }
  }

  async function pollJobs() {
    await Promise.all([loadTrainingJobs(), loadGpuStatus()])
  }

  function toggleProject(id: number) {
    if (expandedProjects.has(id)) {
      expandedProjects.delete(id)
    } else {
      expandedProjects.add(id)
      // Lazy-load quality data
      if (!qualityDataMap.value.has(id)) {
        loadProjectQuality(id)
      }
    }
  }

  // --- Actions ---
  async function trainAll(proj: ProjectCard) {
    actionLoading.value = 'train-' + proj.id
    try {
      for (const ch of proj.charsNeedingLora) {
        await trainingApi.startTraining({ character_name: ch.slug })
      }
      await Promise.all([loadTrainingJobs(), loadLoras()])
    } catch (e) {
      console.error('Train failed:', e)
    } finally {
      actionLoading.value = null
    }
  }

  async function generateScenes(proj: ProjectCard) {
    actionLoading.value = 'scenes-' + proj.id
    try {
      await scenesApi.generateScenesFromStory(proj.id)
      await loadProjectDetails()
    } catch (e) {
      console.error('Scene generation failed:', e)
    } finally {
      actionLoading.value = null
    }
  }

  async function toggleOrchestrator() {
    const enable = !orchestratorStatus.value?.enabled
    try {
      await learningApi.toggleOrchestrator(enable)
      orchestratorStatus.value = await learningApi.getOrchestratorStatus()
    } catch (e) {
      console.error('Failed to toggle orchestrator:', e)
    }
  }

  async function orchestratorTick() {
    try {
      await learningApi.orchestratorTick()
      // Reload pipeline for expanded projects
      for (const id of expandedProjects) {
        loadProjectQuality(id)
      }
    } catch (e) {
      console.error('Tick failed:', e)
    }
  }

  async function initOrchestrator(projectId: number) {
    try {
      await learningApi.initializeOrchestrator(projectId)
      await loadProjectQuality(projectId)
    } catch (e) {
      console.error('Initialize failed:', e)
    }
  }

  async function overrideEntry(entry: PipelineEntry, action: 'skip' | 'reset' | 'complete') {
    try {
      await learningApi.orchestratorOverride({
        entity_type: entry.entity_type,
        entity_id: entry.entity_id,
        phase: entry.phase,
        action,
      })
      // Reload pipeline for the project
      if (entry.project_id) {
        await loadProjectQuality(entry.project_id)
      }
    } catch (e) {
      console.error('Override failed:', e)
    }
  }

  // --- Lifecycle ---
  onMounted(() => {
    refreshAll()
    jobPollTimer = setInterval(pollJobs, 5000)
    fullRefreshTimer = setInterval(refreshAll, 30000)
  })

  onUnmounted(() => {
    if (jobPollTimer) clearInterval(jobPollTimer)
    if (fullRefreshTimer) clearInterval(fullRefreshTimer)
  })

  return {
    // State
    loading,
    actionLoading,
    projects,
    allLoras,
    trainingJobs,
    gpuStatus,
    expandedProjects,
    projectDataMap,
    qualityDataMap,
    qualityLoadingSet,
    learningStats,
    eventStats,
    orchestratorStatus,

    // Computed
    nvidiaBusy,
    comfyQueue,
    ollamaModels,
    runningTrainingJobs,
    recentFailures,
    projectCards,

    // Actions
    refreshAll,
    toggleProject,
    trainAll,
    generateScenes,
    toggleOrchestrator,
    orchestratorTick,
    initOrchestrator,
    overrideEntry,
    loadProjectQuality,
  }
}
