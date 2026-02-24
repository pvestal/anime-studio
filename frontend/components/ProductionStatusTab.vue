<template>
  <div class="status-dashboard">
    <!-- Header -->
    <div class="status-header">
      <h2>Production Status</h2>
      <div class="header-controls">
        <div v-if="gpuStatus" class="gpu-chips">
          <span class="gpu-chip" :class="nvidiaBusy ? 'gpu-busy' : 'gpu-free'"
                :title="`NVIDIA ${gpuStatus.nvidia?.gpu_name || 'N/A'} — ${gpuStatus.nvidia ? gpuStatus.nvidia.used_mb + '/' + gpuStatus.nvidia.total_mb + 'MB' : 'offline'}`">
            NVIDIA {{ nvidiaBusy ? 'Generating' : gpuStatus.nvidia ? gpuStatus.nvidia.free_mb + 'MB free' : 'offline' }}
          </span>
          <span class="gpu-chip gpu-free"
                :title="`AMD ${gpuStatus.amd?.gpu_name || 'N/A'} — Ollama${ollamaModels.length ? ': ' + ollamaModels.join(', ') : ''}`">
            AMD {{ gpuStatus.amd ? gpuStatus.amd.free_mb + 'MB free' : 'N/A' }}
          </span>
          <span v-if="comfyQueue.running > 0 || comfyQueue.pending > 0" class="gpu-chip gpu-busy">
            ComfyUI {{ comfyQueue.running }}R / {{ comfyQueue.pending }}Q
          </span>
        </div>
        <button class="btn btn-secondary" @click="refreshAll" :disabled="loading">
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <!-- Active Jobs -->
    <div v-if="runningTrainingJobs.length > 0 || comfyQueue.running > 0" class="active-jobs">
      <div class="active-jobs-header">Active Right Now</div>
      <!-- Training jobs with real progress -->
      <div v-for="job in runningTrainingJobs" :key="job.job_id" class="active-job-row">
        <span class="active-job-dot"></span>
        <span class="active-job-label">Training <strong>{{ job.character_name }}</strong></span>
        <span class="active-job-detail">{{ shortModel(job.checkpoint) }} &middot; {{ job.model_type || 'sd15' }} &middot; E{{ job.epoch || 0 }}/{{ job.total_epochs || job.epochs || 20 }}</span>
        <div class="active-job-bar">
          <div class="active-job-bar-fill" :style="{ width: trainingPct(job) + '%' }"></div>
        </div>
        <span class="active-job-pct">{{ trainingPct(job) }}%</span>
        <span v-if="job.loss" class="active-job-loss">loss {{ job.loss.toFixed(4) }}</span>
        <span class="active-job-time">{{ elapsed(job.started_at) }}</span>
      </div>
      <!-- ComfyUI -->
      <div v-if="comfyQueue.running > 0" class="active-job-row">
        <span class="active-job-dot" style="background: var(--status-warning);"></span>
        <span class="active-job-label"><strong>ComfyUI</strong> generating</span>
        <span class="active-job-detail">{{ comfyQueue.running }} running, {{ comfyQueue.pending }} queued</span>
      </div>
    </div>

    <!-- Recent failures -->
    <div v-if="recentFailures.length > 0" class="failures-banner">
      <div class="failures-header">Recent Failures</div>
      <div v-for="job in recentFailures" :key="job.job_id" class="failure-row">
        <span style="color: var(--status-error);">Training {{ job.character_name }} failed</span>
        <span class="failure-error">{{ job.error || 'Unknown error' }}</span>
        <span class="failure-time">{{ elapsed(job.failed_at || job.created_at) }}</span>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading && projects.length === 0" style="text-align: center; padding: 48px;">
      <div class="spinner" style="width: 32px; height: 32px; margin: 0 auto 16px;"></div>
      <p style="color: var(--text-muted);">Loading...</p>
    </div>

    <!-- Per-Project Cards -->
    <div v-for="proj in projectCards" :key="proj.id" class="project-card">
      <div class="project-card-header" @click="toggleProject(proj.id)">
        <div style="display: flex; align-items: center; gap: 10px;">
          <span class="toggle-arrow" :class="{ open: expandedProjects.has(proj.id) }">&#9654;</span>
          <span class="project-card-title">{{ proj.name }}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 10px;">
          <!-- Stage summary pills -->
          <span v-for="s in proj.stages" :key="s.label"
                class="stage-pill"
                :class="s.pct >= 100 ? 'pill-done' : s.pct > 0 ? 'pill-partial' : 'pill-empty'">
            {{ s.label }} {{ s.summary }}
          </span>
        </div>
      </div>

      <!-- Expanded detail -->
      <template v-if="expandedProjects.has(proj.id)">
        <!-- Warnings banner -->
        <div v-if="proj.warnings.length > 0" class="model-warnings">
          <div v-for="(w, i) in proj.warnings" :key="i" class="model-warning-row">
            <span class="warning-icon">!</span> {{ w }}
          </div>
        </div>

        <!-- Characters + LoRAs -->
        <div class="detail-section">
          <div class="detail-section-header">
            <span>Characters &amp; LoRAs</span>
            <span class="detail-count">{{ proj.loraCount }}/{{ proj.charCount }} trained</span>
          </div>
          <div class="char-grid">
            <div v-for="ch in proj.characters" :key="ch.slug" class="char-row" :class="{ 'char-row-warn': ch.isMixedModels || ch.loraModelMismatch }">
              <span class="char-status-dot" :class="ch.loraStatus"></span>
              <span class="char-name">{{ ch.name }}</span>
              <span class="char-images">{{ ch.approved }} imgs</span>
              <span class="char-model-info">
                <template v-if="ch.loraStatus === 'lora-trained'">
                  <span class="lora-badge">LoRA</span>
                  <span class="model-name" :class="{ 'model-mismatch': ch.loraModelMismatch }"
                        :title="ch.loraModelMismatch ? `Trained on ${ch.loraCheckpoint} but ${ch.approved} images mostly from ${ch.dominantModel}` : ch.loraCheckpoint || ''">
                    {{ shortModel(ch.loraCheckpoint) }}
                  </span>
                  <span v-if="ch.loraLoss" class="lora-loss">loss {{ ch.loraLoss.toFixed(3) }}</span>
                </template>
                <template v-else-if="ch.loraStatus === 'lora-training'">
                  <span class="training-badge">training...</span>
                </template>
                <template v-else-if="ch.approved >= 10">ready to train</template>
                <template v-else>needs {{ 10 - ch.approved }} more images</template>
              </span>
              <span v-if="ch.isMixedModels" class="mixed-badge" :title="modelBreakdownText(ch.modelBreakdown)">mixed</span>
              <span v-else-if="ch.dominantModel" class="char-dominant-model" :title="ch.dominantModel || ''">{{ shortModel(ch.dominantModel) }}</span>
            </div>
          </div>
          <div v-if="proj.charsNeedingLora.length > 0" class="detail-actions">
            <button class="btn btn-action" @click="trainAll(proj)" :disabled="actionLoading === 'train-' + proj.id">
              Train {{ proj.charsNeedingLora.length }} Ready LoRAs
            </button>
          </div>
        </div>

        <!-- Scenes & Shots -->
        <div class="detail-section">
          <div class="detail-section-header">
            <span>Scenes &amp; Shots</span>
            <span class="detail-count">{{ proj.scenes.length }} scenes, {{ proj.totalShots }} shots</span>
          </div>
          <div v-if="proj.scenes.length > 0" class="scene-list">
            <div v-for="scene in proj.scenes" :key="scene.id" class="scene-row">
              <span class="scene-status-dot" :class="'scene-' + scene.generation_status"></span>
              <span class="scene-title">{{ scene.title }}</span>
              <span class="scene-shots">{{ scene.completed_shots }}/{{ scene.total_shots }} shots done</span>
              <span class="scene-video" v-if="scene.final_video_path" style="color: var(--status-success);">assembled</span>
              <span class="scene-status-label">{{ scene.generation_status }}</span>
            </div>
          </div>
          <div v-else style="color: var(--text-muted); font-size: 12px; padding: 8px 0;">
            No scenes yet.
          </div>
          <div v-if="proj.scenes.length === 0" class="detail-actions">
            <button class="btn btn-action" @click="generateScenes(proj)" :disabled="actionLoading === 'scenes-' + proj.id">
              Generate Scenes from Story
            </button>
          </div>
        </div>

        <!-- Episodes -->
        <div class="detail-section">
          <div class="detail-section-header">
            <span>Episodes</span>
            <span class="detail-count">{{ proj.episodes.length }} episodes</span>
          </div>
          <div v-if="proj.episodes.length > 0" class="episode-list">
            <div v-for="ep in proj.episodes" :key="ep.id" class="episode-row">
              <span class="episode-num">E{{ ep.episode_number }}</span>
              <span class="episode-title">{{ ep.title }}</span>
              <span class="episode-status" :class="'ep-' + ep.status">{{ ep.status }}</span>
              <span v-if="ep.scene_count" class="episode-scenes">{{ ep.scene_count }} scenes</span>
              <span v-if="ep.actual_duration_seconds" class="episode-duration">{{ Math.round(ep.actual_duration_seconds) }}s</span>
            </div>
          </div>
          <div v-else style="color: var(--text-muted); font-size: 12px; padding: 8px 0;">
            No episodes yet.
          </div>
        </div>

        <!-- Next Step -->
        <div class="next-step" v-if="proj.nextAction">
          <strong>Next:</strong> {{ proj.nextAction }}
        </div>
      </template>
    </div>

    <!-- No projects -->
    <div v-if="!loading && projects.length === 0" style="text-align: center; padding: 48px; color: var(--text-muted);">
      No projects found.
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { storyApi } from '@/api/story'
import { learningApi } from '@/api/learning'
import type { DatasetStatsResponse, DatasetCharacterStats } from '@/api/learning'
import { trainingApi } from '@/api/training'
import { scenesApi } from '@/api/scenes'
import { episodesApi } from '@/api/episodes'
import type { TrainingJob, LoraFile, BuilderScene, Episode } from '@/types'
import { createRequest } from '@/api/base'

const systemRequest = createRequest('/api/system')

interface ProjectSummary { id: number; name: string; default_style: string; character_count: number }

interface GpuStatus {
  nvidia: { total_mb: number; used_mb: number; free_mb: number; gpu_name: string } | null
  amd: { total_mb: number; used_mb: number; free_mb: number; gpu_name: string } | null
  ollama: { loaded_models: Array<{ name: string; size_mb: number; vram_mb: number }>; total_vram_mb: number }
  comfyui: { queue_running: number; queue_pending: number }
}

interface ModelBreakdown { [checkpoint: string]: number }

interface CharDetail {
  slug: string
  name: string
  approved: number
  loraStatus: 'lora-trained' | 'lora-training' | 'lora-ready' | 'lora-none'
  modelBreakdown: ModelBreakdown
  dominantModel: string | null
  isMixedModels: boolean
  loraCheckpoint: string | null
  loraLoss: number | null
  loraEpochs: number | null
  loraModelMismatch: boolean  // LoRA trained on different checkpoint than dominant image model
}

interface StageInfo {
  label: string
  summary: string
  pct: number
}

interface ProjectCard {
  id: number
  name: string
  defaultStyle: string
  charCount: number
  loraCount: number
  characters: CharDetail[]
  charsNeedingLora: CharDetail[]
  charsWithMixedModels: CharDetail[]
  charsWithLoraMismatch: CharDetail[]
  scenes: BuilderScene[]
  totalShots: number
  completedShots: number
  episodes: Episode[]
  stages: StageInfo[]
  nextAction: string
  warnings: string[]
}

const loading = ref(false)
const actionLoading = ref<string | null>(null)
const projects = ref<ProjectSummary[]>([])
const allLoras = ref<LoraFile[]>([])
const trainingJobs = ref<TrainingJob[]>([])
const gpuStatus = ref<GpuStatus | null>(null)
const expandedProjects = reactive(new Set<number>())

const projectDataMap = ref<Map<number, {
  stats: DatasetStatsResponse | null
  scenes: BuilderScene[]
  episodes: Episode[]
}>>(new Map())

let jobPollTimer: ReturnType<typeof setInterval> | null = null
let fullRefreshTimer: ReturnType<typeof setInterval> | null = null

// GPU computed
const nvidiaBusy = computed(() => {
  if (!gpuStatus.value?.comfyui) return false
  return gpuStatus.value.comfyui.queue_running > 0 || gpuStatus.value.comfyui.queue_pending > 0
})

const comfyQueue = computed(() => gpuStatus.value?.comfyui ?? { running: 0, pending: 0 })

const ollamaModels = computed(() =>
  gpuStatus.value?.ollama?.loaded_models?.map(m => m.name) ?? []
)

// Training jobs computed
const runningTrainingJobs = computed(() =>
  trainingJobs.value.filter(j => j.status === 'running' || j.status === 'queued')
)

const recentFailures = computed(() =>
  trainingJobs.value
    .filter(j => j.status === 'failed')
    .sort((a, b) => new Date(b.failed_at || b.created_at).getTime() - new Date(a.failed_at || a.created_at).getTime())
    .slice(0, 3)
)

function trainingPct(job: TrainingJob): number {
  const epoch = job.epoch || 0
  const total = job.total_epochs || job.epochs || 20
  return total > 0 ? Math.round((epoch / total) * 100) : 0
}

function shortModel(name?: string | null): string {
  if (!name) return ''
  return name
    .replace('.safetensors', '')
    .replace('_fp16', '')
    .replace('_v51', ' v5.1')
    .replace('V6XL', ' V6')
    .replace('V3.0', ' V3')
    .replace('_v12', ' v12')
}

function modelBreakdownText(breakdown: ModelBreakdown): string {
  return Object.entries(breakdown)
    .sort((a, b) => b[1] - a[1])
    .map(([model, count]) => `${shortModel(model)}: ${count}`)
    .join('\n')
}

function elapsed(iso?: string): string {
  if (!iso) return ''
  const sec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ${sec % 60}s`
  const hrs = Math.floor(min / 60)
  if (hrs < 24) return `${hrs}h ${min % 60}m`
  return `${Math.floor(hrs / 24)}d ago`
}

// Build project cards from data
const projectCards = computed<ProjectCard[]>(() => {
  const loraBySlug = new Map(allLoras.value.map(l => [l.slug, l]))
  const trainingSlugs = new Set(
    runningTrainingJobs.value.map(j => j.character_slug || j.character_name)
  )

  const cards: ProjectCard[] = []

  for (const proj of projects.value) {
    const data = projectDataMap.value.get(proj.id)
    const charStats: DatasetCharacterStats[] = data?.stats?.characters ?? []
    const scenes: BuilderScene[] = data?.scenes ?? []
    const episodes: Episode[] = data?.episodes ?? []
    const charCount = charStats.length || proj.character_count

    // Build character detail with model lineage
    const characters: CharDetail[] = charStats.map(c => {
      const lora = loraBySlug.get(c.slug)
      let loraStatus: CharDetail['loraStatus'] = 'lora-none'
      if (lora) loraStatus = 'lora-trained'
      else if (trainingSlugs.has(c.slug)) loraStatus = 'lora-training'
      else if (c.approved >= 10) loraStatus = 'lora-ready'

      const modelBreakdown: ModelBreakdown = (c as any).model_breakdown ?? {}
      const dominantModel: string | null = (c as any).dominant_model ?? null
      const isMixedModels: boolean = (c as any).is_mixed_models ?? false
      const loraCheckpoint: string | null = lora?.checkpoint ?? null
      const loraLoss: number | null = lora?.final_loss ?? null
      const loraEpochs: number | null = lora?.trained_epochs ?? null

      // Flag if LoRA was trained on a different model than the dominant image source
      const loraModelMismatch = !!(loraCheckpoint && dominantModel &&
        dominantModel !== 'unknown' && dominantModel !== 'no_meta' &&
        loraCheckpoint !== dominantModel)

      return {
        slug: c.slug, name: c.name, approved: c.approved, loraStatus,
        modelBreakdown, dominantModel, isMixedModels,
        loraCheckpoint, loraLoss, loraEpochs, loraModelMismatch,
      }
    })

    const loraCount = characters.filter(c => c.loraStatus === 'lora-trained').length
    const charsNeedingLora = characters.filter(c => c.loraStatus === 'lora-ready')
    const charsWithMixedModels = characters.filter(c => c.isMixedModels)
    const charsWithLoraMismatch = characters.filter(c => c.loraModelMismatch)

    const totalShots = scenes.reduce((s, sc) => s + (sc.total_shots || 0), 0)
    const completedShots = scenes.reduce((s, sc) => s + (sc.completed_shots || 0), 0)
    const assembledEps = episodes.filter(e => e.status === 'assembled' || e.status === 'published').length

    // Stage summary pills
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

    // Collect warnings
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

// Data loading
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

async function refreshAll() {
  loading.value = true
  try {
    const resp = await storyApi.getProjects()
    projects.value = resp.projects
    // Auto-expand first project if none expanded
    if (expandedProjects.size === 0 && resp.projects.length > 0) {
      expandedProjects.add(resp.projects[0].id)
    }
    await Promise.all([loadProjectDetails(), loadTrainingJobs(), loadLoras(), loadGpuStatus()])
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
  if (expandedProjects.has(id)) expandedProjects.delete(id)
  else expandedProjects.add(id)
}

// Actions
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

onMounted(() => {
  refreshAll()
  jobPollTimer = setInterval(pollJobs, 5000)
  fullRefreshTimer = setInterval(refreshAll, 30000)
})

onUnmounted(() => {
  if (jobPollTimer) clearInterval(jobPollTimer)
  if (fullRefreshTimer) clearInterval(fullRefreshTimer)
})
</script>

<style scoped>
.status-dashboard { max-width: 1200px; margin: 0 auto; }

.status-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;
}
.status-header h2 { font-size: 18px; font-weight: 500; margin: 0; }
.header-controls { display: flex; gap: 10px; align-items: center; }

/* GPU chips */
.gpu-chips { display: flex; gap: 6px; }
.gpu-chip {
  padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 500; border: 1px solid;
  white-space: nowrap;
}
.gpu-free { background: rgba(80,160,80,0.1); color: var(--status-success, #4caf50); border-color: rgba(80,160,80,0.3); }
.gpu-busy { background: rgba(255,152,0,0.1); color: var(--status-warning, #ff9800); border-color: rgba(255,152,0,0.3); }

.btn {
  padding: 6px 14px; border: 1px solid var(--border-primary); border-radius: 4px;
  background: var(--bg-secondary); color: var(--text-primary); cursor: pointer;
  font-size: 13px; font-family: var(--font-primary);
}
.btn:hover { background: var(--bg-tertiary, var(--bg-secondary)); }
.btn:disabled { opacity: 0.5; cursor: default; }
.btn-secondary { border-color: var(--accent-primary); color: var(--accent-primary); }
.btn-action {
  font-size: 12px; padding: 4px 12px;
  border-color: var(--accent-primary); color: var(--accent-primary);
}
.btn-action:hover { background: rgba(122,162,247,0.1); }

/* Active Jobs */
.active-jobs {
  background: rgba(122,162,247,0.06); border: 1px solid rgba(122,162,247,0.2);
  border-radius: 6px; padding: 10px 14px; margin-bottom: 14px;
}
.active-jobs-header {
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
  color: var(--accent-primary); margin-bottom: 8px;
}
.active-job-row {
  display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 12px;
  flex-wrap: wrap;
}
.active-job-dot {
  width: 8px; height: 8px; border-radius: 50%; background: var(--accent-primary);
  animation: pulse 2s ease-in-out infinite; flex-shrink: 0;
}
.active-job-label { color: var(--text-primary); }
.active-job-detail { color: var(--text-muted); font-size: 11px; }
.active-job-bar { width: 100px; height: 4px; background: var(--bg-primary); border-radius: 2px; overflow: hidden; }
.active-job-bar-fill { height: 100%; background: var(--accent-primary); transition: width 0.3s ease; }
.active-job-pct { font-weight: 600; color: var(--accent-primary); min-width: 32px; }
.active-job-loss { color: var(--text-muted); font-size: 11px; font-family: 'SF Mono', monospace; }
.active-job-time { color: var(--text-muted); font-size: 11px; margin-left: auto; }

@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

/* Failures banner */
.failures-banner {
  background: rgba(244,67,54,0.06); border: 1px solid rgba(244,67,54,0.2);
  border-radius: 6px; padding: 10px 14px; margin-bottom: 14px;
}
.failures-header {
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
  color: var(--status-error, #f44336); margin-bottom: 6px;
}
.failure-row { display: flex; align-items: center; gap: 8px; padding: 3px 0; font-size: 12px; }
.failure-error {
  color: var(--text-muted); font-size: 11px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; max-width: 400px;
}
.failure-time { color: var(--text-muted); font-size: 11px; margin-left: auto; }

/* Project cards */
.project-card {
  background: var(--bg-secondary); border: 1px solid var(--border-primary);
  border-radius: 8px; padding: 0; margin-bottom: 12px; overflow: hidden;
}
.project-card-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; cursor: pointer; user-select: none;
}
.project-card-header:hover { background: rgba(122,162,247,0.03); }
.project-card-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }

.toggle-arrow {
  font-size: 10px; color: var(--text-muted); transition: transform 150ms ease; display: inline-block;
}
.toggle-arrow.open { transform: rotate(90deg); }

/* Stage pills in collapsed header */
.stage-pill {
  font-size: 10px; padding: 2px 8px; border-radius: 10px; white-space: nowrap;
}
.pill-done { background: rgba(80,160,80,0.15); color: var(--status-success, #4caf50); }
.pill-partial { background: rgba(122,162,247,0.15); color: var(--accent-primary); }
.pill-empty { background: var(--bg-primary); color: var(--text-muted); }

/* Detail sections */
.detail-section {
  padding: 12px 16px; border-top: 1px solid var(--border-primary);
}
.detail-section-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;
  font-size: 12px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;
  letter-spacing: 0.3px;
}
.detail-count { font-weight: 400; color: var(--text-muted); text-transform: none; }
.detail-actions { margin-top: 8px; display: flex; gap: 8px; }

/* Character grid */
.char-grid { display: grid; gap: 0; }
.char-row {
  display: grid; grid-template-columns: 16px 1fr 70px 1.2fr auto; gap: 8px; align-items: center;
  padding: 5px 0; font-size: 12px; border-bottom: 1px solid rgba(255,255,255,0.03);
}
.char-row:last-child { border-bottom: none; }
.char-row-warn { background: rgba(255,152,0,0.04); }
.char-status-dot { width: 8px; height: 8px; border-radius: 50%; }
.lora-trained { background: var(--status-success, #4caf50); box-shadow: 0 0 4px var(--status-success, #4caf50); }
.lora-training { background: var(--status-warning, #ff9800); animation: pulse 2s infinite; }
.lora-ready { background: var(--accent-primary); }
.lora-none { background: var(--text-muted); opacity: 0.3; }
.char-name { color: var(--text-primary); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.char-images { color: var(--text-muted); text-align: right; font-size: 11px; }
.char-model-info { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-muted); overflow: hidden; }
.lora-badge {
  font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 3px;
  background: rgba(80,160,80,0.15); color: var(--status-success, #4caf50); flex-shrink: 0;
}
.training-badge {
  font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 3px;
  background: rgba(255,152,0,0.15); color: var(--status-warning, #ff9800); flex-shrink: 0;
}
.model-name {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: 'SF Mono', 'Consolas', monospace; font-size: 10px;
}
.model-mismatch { color: var(--status-error, #f44336); font-weight: 600; }
.lora-loss { font-size: 10px; font-family: 'SF Mono', monospace; color: var(--text-muted); flex-shrink: 0; }
.mixed-badge {
  font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 3px; cursor: help;
  background: rgba(255,152,0,0.15); color: var(--status-warning, #ff9800); flex-shrink: 0;
}
.char-dominant-model {
  font-size: 10px; font-family: 'SF Mono', 'Consolas', monospace; color: var(--text-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; opacity: 0.6;
}

/* Model warnings */
.model-warnings {
  background: rgba(255,152,0,0.06); border-top: 1px solid rgba(255,152,0,0.2);
  padding: 8px 16px;
}
.model-warning-row {
  font-size: 12px; color: var(--status-warning, #ff9800); padding: 2px 0;
}
.warning-icon {
  display: inline-flex; width: 16px; height: 16px; align-items: center; justify-content: center;
  border-radius: 50%; background: var(--status-warning, #ff9800); color: #000;
  font-size: 10px; font-weight: 800; margin-right: 6px; flex-shrink: 0;
}

/* Scene list */
.scene-list { display: grid; gap: 0; }
.scene-row {
  display: grid; grid-template-columns: 16px 1fr 100px auto auto; gap: 8px; align-items: center;
  padding: 4px 0; font-size: 12px; border-bottom: 1px solid rgba(255,255,255,0.03);
}
.scene-row:last-child { border-bottom: none; }
.scene-status-dot { width: 8px; height: 8px; border-radius: 50%; }
.scene-draft { background: var(--text-muted); opacity: 0.3; }
.scene-generating { background: var(--status-warning, #ff9800); animation: pulse 2s infinite; }
.scene-completed { background: var(--status-success, #4caf50); }
.scene-partial { background: var(--accent-primary); }
.scene-failed { background: var(--status-error, #f44336); }
.scene-title { color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scene-shots { color: var(--text-muted); font-size: 11px; text-align: right; }
.scene-video { font-size: 11px; }
.scene-status-label { font-size: 10px; color: var(--text-muted); text-align: right; }

/* Episode list */
.episode-list { display: grid; gap: 0; }
.episode-row {
  display: grid; grid-template-columns: 30px 1fr 70px 70px 50px; gap: 8px; align-items: center;
  padding: 4px 0; font-size: 12px; border-bottom: 1px solid rgba(255,255,255,0.03);
}
.episode-row:last-child { border-bottom: none; }
.episode-num { font-weight: 600; color: var(--text-muted); }
.episode-title { color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.episode-status { font-size: 11px; text-align: center; padding: 1px 6px; border-radius: 3px; }
.ep-draft { background: var(--bg-primary); color: var(--text-muted); }
.ep-assembled { background: rgba(80,160,80,0.15); color: var(--status-success, #4caf50); }
.ep-published { background: rgba(122,162,247,0.15); color: var(--accent-primary); }
.episode-scenes { font-size: 11px; color: var(--text-muted); text-align: right; }
.episode-duration { font-size: 11px; color: var(--text-muted); text-align: right; }

/* Next step */
.next-step {
  padding: 10px 16px; border-top: 1px solid var(--border-primary);
  font-size: 12px; color: var(--text-muted); background: rgba(122,162,247,0.03);
}
.next-step strong { color: var(--accent-primary); }

/* Spinner */
.spinner {
  border: 3px solid var(--border-primary); border-top: 3px solid var(--accent-primary);
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 900px) {
  .stage-pill { display: none; }
  .char-row { grid-template-columns: 16px 1fr 60px; }
  .char-model-info { display: none; }
  .mixed-badge, .char-dominant-model { display: none; }
  .scene-row { grid-template-columns: 16px 1fr 80px; }
  .scene-video, .scene-status-label { display: none; }
  .episode-row { grid-template-columns: 30px 1fr 70px; }
  .episode-scenes, .episode-duration { display: none; }
}
</style>
