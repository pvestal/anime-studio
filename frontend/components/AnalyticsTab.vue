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

        <!-- Pipeline entries -->
        <div v-if="pipelineEntries.length > 0" style="display: flex; flex-direction: column; gap: 4px;">
          <div class="pipeline-row pipeline-header">
            <span>Entity</span>
            <span>Phase</span>
            <span>Status</span>
            <span>Updated</span>
            <span></span>
          </div>
          <div v-for="entry in pipelineEntries" :key="entry.id" class="pipeline-row" :class="'pipeline-' + entry.status">
            <span class="pipeline-entity">{{ entry.entity_type === 'character' ? entry.entity_id : 'Project' }}</span>
            <span>{{ entry.phase.replace(/_/g, ' ') }}</span>
            <span class="pipeline-status-badge" :class="'pstatus-' + entry.status">{{ entry.status }}</span>
            <span style="color: var(--text-muted); font-size: 11px;">{{ formatRelativeTime(entry.updated_at) }}</span>
            <span style="display: flex; gap: 4px;">
              <button v-if="entry.status === 'active' || entry.status === 'pending'" class="btn btn-sm" style="font-size: 10px; padding: 1px 6px;"
                @click="overrideEntry(entry, 'skip')">Skip</button>
              <button v-if="entry.status === 'failed'" class="btn btn-sm" style="font-size: 10px; padding: 1px 6px;"
                @click="overrideEntry(entry, 'reset')">Reset</button>
            </span>
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
      pipelineEntries.value = data.entries
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

/* Orchestrator Pipeline */
.pipeline-row {
  display: grid;
  grid-template-columns: 1fr 1fr 80px 80px 60px;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  font-size: 12px;
  border-bottom: 1px solid var(--border-primary);
}
.pipeline-header {
  font-weight: 500;
  color: var(--text-muted);
  font-size: 11px;
  text-transform: uppercase;
}
.pipeline-entity {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pipeline-active { background: rgba(122, 162, 247, 0.05); }
.pipeline-completed { opacity: 0.6; }
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
.chip-enabled { background: rgba(80, 160, 80, 0.2); color: var(--status-success, #4caf50); border-color: var(--status-success, #4caf50); }
.chip-disabled { background: var(--bg-tertiary); color: var(--text-muted); }
.btn-success-sm { border-color: var(--status-success, #4caf50); color: var(--status-success, #4caf50); }
.btn-danger-sm { border-color: var(--status-error, #f44336); color: var(--status-error, #f44336); }

@media (max-width: 900px) {
  .stats-grid { grid-template-columns: repeat(3, 1fr); }
  .quality-row { grid-template-columns: 1fr 50px 1fr 50px; }
}
</style>
