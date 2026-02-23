<template>
  <div class="dashboard">
    <div class="dashboard-header">
      <h2>Analytics</h2>
      <div class="header-controls">
        <select v-model="selectedProject" class="select-input">
          <option value="">All Projects</option>
          <option v-for="p in projects" :key="p.id" :value="p.name">{{ p.name }}</option>
        </select>
        <button class="btn btn-secondary" @click="refreshAll" :disabled="loading">
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <!-- Real dataset stats cards -->
    <div class="stats-grid" v-if="datasetStats">
      <div class="stat-card">
        <div class="stat-value">{{ datasetStats.totals.total }}</div>
        <div class="stat-label">Total Images</div>
        <div class="stat-sub">{{ datasetStats.characters.length }} characters</div>
      </div>
      <div class="stat-card stat-approved">
        <div class="stat-value">{{ datasetStats.totals.approved }}</div>
        <div class="stat-label">Approved</div>
        <div class="stat-sub">{{ totalApprovalRate }}% approval rate</div>
      </div>
      <div class="stat-card" style="border-color: var(--status-warning, #ff9800);">
        <div class="stat-value" style="color: var(--status-warning, #ff9800);">{{ datasetStats.totals.pending }}</div>
        <div class="stat-label">Pending Review</div>
        <div class="stat-sub">awaiting decision</div>
      </div>
      <div class="stat-card stat-rejected">
        <div class="stat-value">{{ datasetStats.totals.rejected }}</div>
        <div class="stat-label">Rejected</div>
        <div class="stat-sub">{{ totalRejectRate }}% reject rate</div>
      </div>
      <div class="stat-card" v-if="learningStats" :class="{ 'stat-good': avgQuality >= 0.7, 'stat-warn': avgQuality > 0 && avgQuality < 0.7 }">
        <div class="stat-value">{{ avgQuality ? (avgQuality * 100).toFixed(0) + '%' : '--' }}</div>
        <div class="stat-label">Avg Quality</div>
        <div class="stat-sub">{{ learningStats.generation_history.reviewed }} vision reviewed</div>
      </div>
    </div>

    <!-- Character Breakdown (real data) -->
    <div class="section" v-if="datasetStats && datasetStats.characters.length > 0">
      <h3>Character Breakdown {{ selectedProject ? '' : '(select a project)' }}</h3>
      <div class="quality-table">
        <div class="quality-row quality-header">
          <span class="q-name">Character</span>
          <span class="q-stat">Approved</span>
          <span class="q-bar">Distribution</span>
          <span class="q-stat">Pending</span>
          <span class="q-stat">Rate</span>
        </div>
        <div
          class="quality-row"
          v-for="ch in sortedCharacters"
          :key="ch.slug"
        >
          <span class="q-name">{{ ch.name }}</span>
          <span class="q-stat" style="font-weight: 500;" :style="{ color: ch.approved > 0 ? 'var(--status-success, #4caf50)' : 'var(--text-muted)' }">
            {{ ch.approved }}
          </span>
          <span class="q-bar">
            <div class="bar-track">
              <div class="bar-fill bar-approved" :style="{ width: barWidth(ch.approved, ch.total) }"></div>
              <div class="bar-fill bar-pending" :style="{ width: barWidth(ch.pending, ch.total), left: barWidth(ch.approved, ch.total) }"></div>
              <div class="bar-fill bar-rejected" :style="{ width: barWidth(ch.rejected, ch.total), left: barWidth(ch.approved + ch.pending, ch.total) }"></div>
            </div>
            <span class="bar-label">{{ ch.approved }}/{{ ch.rejected }}/{{ ch.total }}</span>
          </span>
          <span class="q-stat" :style="{ color: ch.pending > 0 ? 'var(--status-warning, #ff9800)' : 'var(--text-muted)' }">
            {{ ch.pending }}
          </span>
          <span class="q-stat" :class="rateClass(ch.approval_rate)">
            {{ (ch.approval_rate * 100).toFixed(0) }}%
          </span>
        </div>
      </div>
    </div>

    <!-- Checkpoint Rankings (top-level when project selected) -->
    <div class="section" v-if="selectedProject && checkpointRankings.length > 0">
      <h3>Checkpoint Rankings</h3>
      <div class="checkpoint-card" v-for="(ckpt, idx) in checkpointRankings" :key="ckpt.checkpoint">
        <div class="ckpt-rank">#{{ idx + 1 }}</div>
        <div class="ckpt-info">
          <div class="ckpt-name">{{ ckpt.checkpoint }}</div>
          <div class="ckpt-stats">
            Quality: {{ (ckpt.avg_quality * 100).toFixed(0) }}%
            | {{ ckpt.approved }}/{{ ckpt.total }} approved
            ({{ (ckpt.approval_rate * 100).toFixed(0) }}%)
          </div>
        </div>
      </div>
    </div>

    <!-- Autonomy & Learning (collapsible) -->
    <div class="section" v-if="learningStats">
      <div class="section-toggle" @click="showAutonomy = !showAutonomy">
        <h3 style="margin-bottom: 0;">Autonomy & Learning</h3>
        <span class="toggle-arrow" :class="{ open: showAutonomy }">&#9654;</span>
      </div>

      <template v-if="showAutonomy">
        <!-- Autonomy stats row -->
        <div style="display: flex; gap: 12px; flex-wrap: wrap; margin-top: 12px;">
          <div class="mini-stat">
            <span class="mini-value">{{ learningStats.autonomy_decisions.auto_approves }}</span>
            <span class="mini-label">Auto-Approved</span>
          </div>
          <div class="mini-stat">
            <span class="mini-value">{{ learningStats.autonomy_decisions.auto_rejects }}</span>
            <span class="mini-label">Auto-Rejected</span>
          </div>
          <div class="mini-stat">
            <span class="mini-value">{{ learningStats.autonomy_decisions.regenerations }}</span>
            <span class="mini-label">Regenerations</span>
          </div>
          <div class="mini-stat">
            <span class="mini-value">{{ learningStats.learned_patterns }}</span>
            <span class="mini-label">Learned Patterns</span>
          </div>
          <div class="mini-stat">
            <span class="mini-value">{{ learningStats.generation_history.checkpoints_used }}</span>
            <span class="mini-label">Checkpoints</span>
          </div>
        </div>

        <!-- EventBus Status -->
        <div v-if="eventStats" style="margin-top: 12px;">
          <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 6px;">EventBus</div>
          <div class="event-chips">
            <span class="chip" v-for="evt in eventStats.registered_events" :key="evt">{{ evt }}</span>
            <span class="chip chip-count">{{ eventStats.total_handlers }} handlers</span>
            <span class="chip chip-count">{{ eventStats.total_emits }} emits</span>
            <span class="chip chip-error" v-if="eventStats.total_errors > 0">{{ eventStats.total_errors }} errors</span>
          </div>
        </div>

        <!-- Drift Alerts -->
        <div v-if="driftAlerts.length > 0" style="margin-top: 12px;">
          <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 6px;">Drift Alerts</div>
          <div class="drift-card" v-for="alert in driftAlerts" :key="alert.character_slug"
               :class="{ 'drift-critical': alert.alert }">
            <div class="drift-header">
              <strong>{{ alert.character_slug }}</strong>
              <span class="drift-badge" :class="alert.alert ? 'badge-critical' : 'badge-warn'">
                {{ alert.drift > 0 ? '+' : '' }}{{ (alert.drift * 100).toFixed(1) }}%
              </span>
            </div>
            <div class="drift-details">
              Recent: {{ (alert.recent_avg * 100).toFixed(0) }}% ({{ alert.recent_count }} imgs)
              vs Overall: {{ (alert.overall_avg * 100).toFixed(0) }}% ({{ alert.total_count }} imgs)
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Production Orchestrator -->
    <div class="section" v-if="selectedProject">
      <div class="section-toggle" @click="showOrchestrator = !showOrchestrator">
        <h3 style="margin-bottom: 0;">Production Orchestrator</h3>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span v-if="orchestratorStatus" class="chip" :class="orchestratorStatus.enabled ? 'chip-enabled' : 'chip-disabled'">
            {{ orchestratorStatus.enabled ? 'Enabled' : 'Disabled' }}
          </span>
          <span class="toggle-arrow" :class="{ open: showOrchestrator }">&#9654;</span>
        </div>
      </div>

      <template v-if="showOrchestrator">
        <div style="display: flex; gap: 8px; align-items: center; margin-top: 12px; margin-bottom: 12px;">
          <button class="btn btn-sm" :class="orchestratorStatus?.enabled ? 'btn-danger-sm' : 'btn-success-sm'" @click="toggleOrchestrator">
            {{ orchestratorStatus?.enabled ? 'Disable' : 'Enable' }}
          </button>
          <button class="btn btn-sm" @click="orchestratorTick" :disabled="!orchestratorStatus?.enabled">Manual Tick</button>
          <button class="btn btn-sm" @click="initOrchestrator" :disabled="!selectedProjectId">Initialize Project</button>
        </div>

        <!-- Pipeline cards -->
        <div v-if="pipelineEntries.length > 0">
          <!-- Project phases card -->
          <div v-if="projectPhases.length > 0" class="orch-card" :class="{ 'orch-card-dim': projectPhases.every(p => p.status === 'completed') }">
            <div class="orch-card-header">
              <span class="orch-card-title">Project Pipeline</span>
              <span class="pipeline-status-badge" :class="'pstatus-' + currentPhase(projectPhases).status">
                {{ currentPhase(projectPhases).status }}
              </span>
            </div>
            <div class="phase-pills">
              <span v-for="p in projectPhases" :key="p.phase" class="phase-pill" :class="'pstatus-' + p.status"
                    :title="p.phase.replace(/_/g, ' ') + ': ' + p.status">
                {{ p.phase.replace(/_/g, ' ') }}
              </span>
            </div>
            <div class="orch-card-footer">
              <span class="orch-card-actions">
                <template v-for="p in projectPhases" :key="'a-' + p.phase">
                  <button v-if="p.status === 'failed'" class="btn btn-sm orch-action-btn" @click="overrideEntry(p, 'reset')">Reset {{ p.phase.replace(/_/g, ' ') }}</button>
                  <button v-if="p.status === 'active' || p.status === 'pending'" class="btn btn-sm orch-action-btn" @click="overrideEntry(p, 'skip')">Skip {{ p.phase.replace(/_/g, ' ') }}</button>
                </template>
              </span>
              <span class="orch-card-time">{{ formatRelativeTime(latestTime(projectPhases)) }}</span>
            </div>
          </div>

          <!-- Character cards grid -->
          <div v-if="characterCards.length > 0" class="orch-grid">
            <div v-for="card in characterCards" :key="card.slug" class="orch-card" :class="{ 'orch-card-dim': card.phases.every(p => p.status === 'completed') }">
              <div class="orch-card-header">
                <span class="orch-card-title">{{ card.slug }}</span>
                <span class="pipeline-status-badge" :class="'pstatus-' + currentPhase(card.phases).status">
                  {{ currentPhase(card.phases).status }}
                </span>
              </div>
              <div class="phase-pills">
                <span v-for="p in card.phases" :key="p.phase" class="phase-pill" :class="'pstatus-' + p.status"
                      :title="p.phase.replace(/_/g, ' ') + ': ' + p.status">
                  {{ p.phase.replace(/_/g, ' ') }}
                </span>
              </div>
              <div class="orch-card-footer">
                <span class="orch-card-actions">
                  <template v-for="p in card.phases" :key="'a-' + p.phase">
                    <button v-if="p.status === 'failed'" class="btn btn-sm orch-action-btn" @click="overrideEntry(p, 'reset')">Reset</button>
                    <button v-if="p.status === 'active'" class="btn btn-sm orch-action-btn" @click="overrideEntry(p, 'skip')">Skip</button>
                  </template>
                </span>
                <span class="orch-card-time">{{ formatRelativeTime(latestTime(card.phases)) }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-else style="color: var(--text-muted); font-size: 12px; margin-top: 8px;">
          No pipeline entries. Initialize this project to start the production pipeline.
        </div>
      </template>
    </div>

    <!-- Quality Trend Chart -->
    <div class="section" v-if="trendData.length > 1">
      <h3>Quality Trend ({{ trendDays }}d)</h3>
      <div class="trend-controls">
        <button v-for="d in [7, 14, 30]" :key="d" class="btn btn-sm"
                :class="{ 'btn-active': trendDays === d }" @click="trendDays = d; loadTrend()">
          {{ d }}d
        </button>
      </div>
      <div class="chart-container">
        <svg :viewBox="`0 0 ${chartWidth} ${chartHeight}`" class="trend-chart">
          <line v-for="y in gridLines" :key="y"
                :x1="chartPad" :x2="chartWidth - chartPad"
                :y1="yScale(y)" :y2="yScale(y)"
                class="grid-line" />
          <text v-for="y in gridLines" :key="'l'+y"
                :x="chartPad - 4" :y="yScale(y) + 4" class="axis-label" text-anchor="end">
            {{ (y * 100).toFixed(0) }}%
          </text>
          <polyline :points="qualityLinePoints" class="trend-line" />
          <circle v-for="(pt, i) in trendPoints" :key="i"
                  :cx="pt.x" :cy="pt.y" r="3" class="trend-dot" />
          <text v-for="(pt, i) in trendPoints" :key="'x'+i"
                :x="pt.x" :y="chartHeight - 2" class="axis-label" text-anchor="middle">
            {{ pt.label }}
          </text>
        </svg>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { learningApi } from '@/api/learning'
import type { DatasetStatsResponse } from '@/api/learning'
import { storyApi } from '@/api/story'
import type {
  LearningStats,
  EventBusStats,
  DriftAlert,
  QualityTrendPoint,
  CheckpointRanking,
  OrchestratorStatus,
  PipelineEntry,
} from '@/types'

interface ProjectSummary { id: number; name: string; default_style: string; character_count: number }

const loading = ref(false)
const selectedProject = ref('')
const trendDays = ref(14)
const showAutonomy = ref(false)
const showOrchestrator = ref(false)
const orchestratorStatus = ref<OrchestratorStatus | null>(null)
const pipelineEntries = ref<PipelineEntry[]>([])

const projects = ref<ProjectSummary[]>([])
const datasetStats = ref<DatasetStatsResponse | null>(null)
const learningStats = ref<LearningStats | null>(null)
const eventStats = ref<EventBusStats | null>(null)
const driftAlerts = ref<DriftAlert[]>([])
const trendData = ref<QualityTrendPoint[]>([])
const checkpointRankings = ref<CheckpointRanking[]>([])

const chartWidth = 600
const chartHeight = 200
const chartPad = 40
const gridLines = [0.2, 0.4, 0.6, 0.8, 1.0]

const avgQuality = computed(() => learningStats.value?.generation_history.avg_quality ?? 0)

const totalApprovalRate = computed(() => {
  if (!datasetStats.value || !datasetStats.value.totals.total) return 0
  return Math.round(datasetStats.value.totals.approved / datasetStats.value.totals.total * 100)
})

const totalRejectRate = computed(() => {
  if (!datasetStats.value || !datasetStats.value.totals.total) return 0
  return Math.round(datasetStats.value.totals.rejected / datasetStats.value.totals.total * 100)
})

const sortedCharacters = computed(() => {
  if (!datasetStats.value) return []
  return [...datasetStats.value.characters].sort((a, b) => b.approval_rate - a.approval_rate)
})

function yScale(val: number): number {
  return chartHeight - chartPad - (val * (chartHeight - 2 * chartPad))
}

const trendPoints = computed(() => {
  if (!trendData.value.length) return []
  const w = chartWidth - 2 * chartPad
  const step = trendData.value.length > 1 ? w / (trendData.value.length - 1) : 0
  return trendData.value.map((pt, i) => ({
    x: chartPad + i * step,
    y: yScale(pt.avg_quality),
    count: pt.count,
    label: pt.date?.slice(5) || '',
  }))
})

const qualityLinePoints = computed(() =>
  trendPoints.value.map(p => `${p.x},${p.y}`).join(' ')
)

const selectedProjectId = computed(() => {
  const p = projects.value.find(p => p.name === selectedProject.value)
  return p?.id ?? null
})

// Orchestrator card groupings
const projectPhases = computed(() => {
  return pipelineEntries.value
    .filter(e => e.entity_type === 'project')
    .sort((a, b) => {
      const order = ['scene_planning', 'shot_prep', 'video_gen', 'scene_assembly', 'episode', 'publishing']
      return (order.indexOf(a.phase) ?? 99) - (order.indexOf(b.phase) ?? 99)
    })
})

const characterCards = computed(() => {
  const grouped: Record<string, PipelineEntry[]> = {}
  for (const e of pipelineEntries.value) {
    if (e.entity_type !== 'character') continue
    if (!grouped[e.entity_id]) grouped[e.entity_id] = []
    grouped[e.entity_id].push(e)
  }
  const cards = Object.entries(grouped).map(([slug, phases]) => ({
    slug,
    phases: phases.sort((a, b) => {
      const order = ['training_data', 'lora_training', 'ready']
      return (order.indexOf(a.phase) ?? 99) - (order.indexOf(b.phase) ?? 99)
    }),
  }))
  // Active/failed first, completed last
  cards.sort((a, b) => {
    const hasActive = (ps: PipelineEntry[]) => ps.some(p => p.status === 'active' || p.status === 'failed')
    const allDone = (ps: PipelineEntry[]) => ps.every(p => p.status === 'completed')
    if (hasActive(a.phases) && !hasActive(b.phases)) return -1
    if (!hasActive(a.phases) && hasActive(b.phases)) return 1
    if (allDone(a.phases) && !allDone(b.phases)) return 1
    if (!allDone(a.phases) && allDone(b.phases)) return -1
    return a.slug.localeCompare(b.slug)
  })
  return cards
})

function currentPhase(phases: PipelineEntry[]): PipelineEntry {
  return phases.find(p => p.status === 'active')
    || phases.find(p => p.status === 'failed')
    || phases.find(p => p.status === 'pending')
    || phases[phases.length - 1]
}

function latestTime(phases: PipelineEntry[]): string {
  let latest = ''
  for (const p of phases) {
    if (p.updated_at && p.updated_at > latest) latest = p.updated_at
  }
  return latest
}

function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

async function loadOrchestrator() {
  try {
    orchestratorStatus.value = await learningApi.getOrchestratorStatus()
  } catch (e) {
    console.error('Failed to load orchestrator status:', e)
  }
  if (selectedProjectId.value) {
    try {
      const data = await learningApi.getOrchestratorPipeline(selectedProjectId.value)
      // API returns { characters: {slug: phases[]}, project_phases: {phase: entry} }
      // Flatten into PipelineEntry[] for the template
      const entries: PipelineEntry[] = []
      if (data.characters) {
        for (const [slug, phases] of Object.entries(data.characters as Record<string, PipelineEntry[]>)) {
          for (const p of phases) {
            entries.push({ ...p, entity_id: slug, entity_type: 'character' })
          }
        }
      }
      if (data.project_phases) {
        for (const [phase, entry] of Object.entries(data.project_phases as Record<string, PipelineEntry>)) {
          entries.push({ ...entry, phase, entity_type: 'project' })
        }
      }
      // Sort: active/pending first, then by entity
      entries.sort((a, b) => {
        const order: Record<string, number> = { active: 0, pending: 1, blocked: 2, failed: 3, completed: 4, skipped: 5 }
        return (order[a.status] ?? 9) - (order[b.status] ?? 9)
      })
      pipelineEntries.value = entries
    } catch (e) {
      pipelineEntries.value = []
    }
  }
}

async function toggleOrchestrator() {
  const enable = !orchestratorStatus.value?.enabled
  try {
    await learningApi.toggleOrchestrator(enable)
    await loadOrchestrator()
  } catch (e) {
    console.error('Failed to toggle orchestrator:', e)
    alert(`Failed: ${e}`)
  }
}

async function orchestratorTick() {
  try {
    await learningApi.orchestratorTick()
    await loadOrchestrator()
  } catch (e) {
    console.error('Tick failed:', e)
  }
}

async function initOrchestrator() {
  if (!selectedProjectId.value) return
  try {
    await learningApi.initializeOrchestrator(selectedProjectId.value)
    await loadOrchestrator()
  } catch (e) {
    console.error('Initialize failed:', e)
    alert(`Initialize failed: ${e}`)
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
    await loadOrchestrator()
  } catch (e) {
    console.error('Override failed:', e)
  }
}

function rateClass(rate: number): string {
  if (rate >= 0.6) return 'quality-high'
  if (rate >= 0.3) return 'quality-mid'
  return 'quality-low'
}

function barWidth(count: number, total: number): string {
  if (!total) return '0%'
  return `${(count / total * 100).toFixed(1)}%`
}

async function loadDatasetStats() {
  try {
    datasetStats.value = await learningApi.getDatasetStats(selectedProject.value || undefined)
  } catch (e) {
    console.error('Failed to load dataset stats:', e)
  }
}

async function loadStats() {
  try {
    const [stats, events] = await Promise.all([
      learningApi.getLearningStats(),
      learningApi.getEventStats(),
    ])
    learningStats.value = stats
    eventStats.value = events
  } catch (e) {
    console.error('Failed to load stats:', e)
  }
}

async function loadProjectData() {
  if (!selectedProject.value) {
    checkpointRankings.value = []
    driftAlerts.value = []
    return
  }
  try {
    const [rankings, drift] = await Promise.all([
      learningApi.getCheckpointRankings(selectedProject.value),
      learningApi.getDriftAlerts({ project_name: selectedProject.value }),
    ])
    checkpointRankings.value = rankings.rankings
    driftAlerts.value = drift.alerts
  } catch (e) {
    console.error('Failed to load project data:', e)
  }
}

async function loadTrend() {
  try {
    const params: { project_name?: string; days: number } = { days: trendDays.value }
    if (selectedProject.value) params.project_name = selectedProject.value
    const result = await learningApi.getQualityTrend(params)
    trendData.value = result.trend
  } catch (e) {
    console.error('Failed to load trend:', e)
  }
}

async function refreshAll() {
  loading.value = true
  try {
    await Promise.all([loadDatasetStats(), loadStats(), loadProjectData(), loadTrend(), loadOrchestrator()])
  } finally {
    loading.value = false
  }
}

watch(selectedProject, () => {
  loadDatasetStats()
  loadProjectData()
  loadTrend()
  loadOrchestrator()
})

onMounted(async () => {
  try {
    const resp = await storyApi.getProjects()
    projects.value = resp.projects
    // Auto-select first project so data shows immediately
    if (resp.projects.length > 0 && !selectedProject.value) {
      selectedProject.value = resp.projects[0].name
    }
  } catch (e) {
    console.error('Failed to load projects:', e)
  }
  refreshAll()
})
</script>

<style scoped>
.dashboard {
  max-width: 1200px;
  margin: 0 auto;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.dashboard-header h2 {
  font-size: 18px;
  font-weight: 500;
}

.header-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}

.select-input {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  padding: 6px 12px;
  font-size: 13px;
}

.btn {
  padding: 6px 14px;
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 13px;
}

.btn:hover { background: var(--bg-tertiary, var(--bg-secondary)); }
.btn:disabled { opacity: 0.5; cursor: default; }
.btn-secondary { border-color: var(--accent-primary); color: var(--accent-primary); }
.btn-sm { padding: 3px 10px; font-size: 12px; }
.btn-active { background: var(--accent-primary); color: #fff; border-color: var(--accent-primary); }

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  padding: 16px;
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.stat-sub {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  opacity: 0.7;
}

.stat-approved .stat-value { color: var(--status-success, #4caf50); }
.stat-rejected .stat-value { color: var(--status-error, #f44336); }
.stat-good .stat-value { color: var(--status-success, #4caf50); }
.stat-warn .stat-value { color: var(--status-warning, #ff9800); }

/* Sections */
.section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 16px;
}

.section h3 {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 12px;
  color: var(--text-primary);
}

.section-toggle {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;
}

.toggle-arrow {
  font-size: 10px;
  color: var(--text-muted);
  transition: transform 150ms ease;
}

.toggle-arrow.open {
  transform: rotate(90deg);
}

/* Mini stats for autonomy section */
.mini-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 16px;
  background: var(--bg-primary);
  border-radius: 4px;
  border: 1px solid var(--border-primary);
}

.mini-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.mini-label {
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* Event Chips */
.event-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  color: var(--text-secondary);
}

.chip-count {
  background: var(--accent-primary);
  color: #fff;
  border-color: var(--accent-primary);
  opacity: 0.9;
}

.chip-error {
  background: var(--status-error, #f44336);
  color: #fff;
  border-color: var(--status-error, #f44336);
}

/* Quality Table */
.quality-table {
  font-size: 13px;
}

.quality-row {
  display: grid;
  grid-template-columns: 1.2fr 60px 1fr 60px 50px;
  gap: 8px;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid var(--border-primary);
}

.quality-header {
  font-weight: 500;
  color: var(--text-muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.q-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.q-stat { text-align: center; }
.quality-high { color: var(--status-success, #4caf50); font-weight: 500; }
.quality-mid { color: var(--status-warning, #ff9800); }
.quality-low { color: var(--status-error, #f44336); }

.q-bar { display: flex; align-items: center; gap: 6px; }

.bar-track {
  flex: 1;
  height: 8px;
  background: var(--bg-primary);
  border-radius: 4px;
  overflow: hidden;
  position: relative;
}

.bar-fill {
  height: 100%;
  position: absolute;
  top: 0;
}

.bar-approved { background: var(--status-success, #4caf50); left: 0; }
.bar-pending { background: var(--status-warning, #ff9800); }
.bar-rejected { background: var(--status-error, #f44336); }
.bar-label { font-size: 11px; color: var(--text-muted); white-space: nowrap; }

/* Drift Alerts */
.drift-card {
  padding: 10px;
  border-left: 3px solid var(--status-warning, #ff9800);
  margin-bottom: 8px;
  background: var(--bg-primary);
  border-radius: 0 4px 4px 0;
}

.drift-critical { border-left-color: var(--status-error, #f44336); }

.drift-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.drift-badge {
  font-size: 12px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 500;
}

.badge-warn { background: rgba(255, 152, 0, 0.2); color: var(--status-warning, #ff9800); }
.badge-critical { background: rgba(244, 67, 54, 0.2); color: var(--status-error, #f44336); }

.drift-details {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}

/* Checkpoint Rankings */
.checkpoint-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  background: var(--bg-primary);
  border-radius: 4px;
  margin-bottom: 6px;
}

.ckpt-rank {
  font-size: 16px;
  font-weight: 600;
  color: var(--accent-primary);
  width: 30px;
  text-align: center;
}

.ckpt-name {
  font-size: 13px;
  font-weight: 500;
  word-break: break-all;
}

.ckpt-stats {
  font-size: 11px;
  color: var(--text-muted);
}

/* Trend Chart */
.trend-controls {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}

.chart-container {
  width: 100%;
  max-width: 600px;
}

.trend-chart {
  width: 100%;
  height: auto;
}

.grid-line {
  stroke: var(--border-primary);
  stroke-width: 0.5;
  stroke-dasharray: 3 3;
}

.axis-label {
  fill: var(--text-muted);
  font-size: 10px;
}

.trend-line {
  fill: none;
  stroke: var(--accent-primary);
  stroke-width: 2;
  stroke-linejoin: round;
}

.trend-dot {
  fill: var(--accent-primary);
}

/* Orchestrator Cards */
.orch-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-top: 8px;
}
.orch-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 0;
  transition: opacity 150ms ease;
}
.orch-card:first-child { margin-bottom: 8px; }
.orch-card-dim { opacity: 0.6; }
.orch-card:hover .orch-action-btn { opacity: 1; }
.orch-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.orch-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.orch-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
  min-height: 20px;
}
.orch-card-time {
  font-size: 11px;
  color: var(--text-muted);
  margin-left: auto;
}
.orch-card-actions {
  display: flex;
  gap: 4px;
}
.orch-action-btn {
  font-size: 10px !important;
  padding: 1px 6px !important;
  opacity: 0;
  transition: opacity 150ms ease;
}
.orch-card:hover .orch-action-btn,
.orch-action-btn:focus { opacity: 1; }
.phase-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.phase-pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  white-space: nowrap;
}
.phase-pill.pstatus-active {
  animation: pill-pulse 2s ease-in-out infinite;
}
@keyframes pill-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
.pipeline-status-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  text-align: center;
}
.pstatus-pending { background: var(--bg-tertiary); color: var(--text-secondary); }
.pstatus-active { background: rgba(122, 162, 247, 0.2); color: var(--accent-primary); }
.pstatus-completed { background: rgba(80, 160, 80, 0.2); color: var(--status-success, #4caf50); }
.pstatus-skipped { background: var(--bg-tertiary); color: var(--text-muted); }
.pstatus-failed { background: rgba(160, 80, 80, 0.2); color: var(--status-error, #f44336); }
.pstatus-blocked { background: rgba(255, 152, 0, 0.2); color: var(--status-warning, #ff9800); }
.chip-enabled { background: rgba(80, 160, 80, 0.2); color: var(--status-success, #4caf50); border-color: var(--status-success, #4caf50); }
.chip-disabled { background: var(--bg-tertiary); color: var(--text-muted); }
.btn-success-sm { border-color: var(--status-success, #4caf50); color: var(--status-success, #4caf50); }
.btn-danger-sm { border-color: var(--status-error, #f44336); color: var(--status-error, #f44336); }

@media (max-width: 900px) {
  .stats-grid { grid-template-columns: repeat(3, 1fr); }
  .quality-row { grid-template-columns: 1fr 50px 1fr 50px; }
  .orch-grid { grid-template-columns: 1fr; }
}
</style>
