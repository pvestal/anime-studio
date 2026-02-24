<template>
  <div class="project-card">
    <div class="project-card-header" @click="$emit('toggle', project.id)">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span class="toggle-arrow" :class="{ open: expanded }">&#9654;</span>
        <span class="project-card-title">{{ project.name }}</span>
        <!-- Alert badge -->
        <span v-if="alertCount > 0" class="alert-badge" :title="`${alertCount} warning${alertCount > 1 ? 's' : ''}`">
          {{ alertCount }}
        </span>
      </div>
      <div style="display: flex; align-items: center; gap: 10px;">
        <!-- Quality sparkline (tiny SVG) -->
        <svg v-if="trendData.length > 1" class="sparkline" :viewBox="`0 0 80 24`" preserveAspectRatio="none">
          <polyline :points="sparklinePoints" class="sparkline-line" />
        </svg>
        <!-- Stage summary pills -->
        <span v-for="s in project.stages" :key="s.label"
              class="stage-pill"
              :class="s.pct >= 100 ? 'pill-done' : s.pct > 0 ? 'pill-partial' : 'pill-empty'">
          {{ s.label }} {{ s.summary }}
        </span>
      </div>
    </div>

    <!-- Expanded detail -->
    <template v-if="expanded">
      <!-- Warnings banner -->
      <div v-if="project.warnings.length > 0" class="model-warnings">
        <div v-for="(w, i) in project.warnings" :key="i" class="model-warning-row">
          <span class="warning-icon">!</span> {{ w }}
        </div>
      </div>

      <!-- Characters & LoRAs -->
      <div class="detail-section">
        <div class="detail-section-header">
          <span>Characters &amp; LoRAs</span>
          <span class="detail-count">{{ project.loraCount }}/{{ project.charCount }} trained</span>
        </div>
        <div class="char-grid">
          <div v-for="ch in project.characters" :key="ch.slug" class="char-row" :class="{ 'char-row-warn': ch.isMixedModels || ch.loraModelMismatch }">
            <span class="char-status-dot" :class="ch.loraStatus"></span>
            <span class="char-name">{{ ch.name }}</span>
            <span class="char-images">{{ ch.approved }} imgs</span>
            <span class="char-model-info">
              <template v-if="ch.loraStatus === 'lora-trained'">
                <span class="lora-badge">LoRA</span>
                <span class="model-name" :class="{ 'model-mismatch': ch.loraModelMismatch }"
                      :title="ch.loraModelMismatch ? `Trained on ${ch.loraCheckpoint} but images mostly from ${ch.dominantModel}` : ch.loraCheckpoint || ''">
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
            <!-- Approval rate -->
            <span v-if="ch.approvalRate != null" class="char-approval" :class="rateClass(ch.approvalRate)">
              {{ (ch.approvalRate * 100).toFixed(0) }}%
            </span>
            <!-- Drift indicator -->
            <span v-if="ch.driftStatus" class="drift-dot" :class="'drift-' + ch.driftStatus"
                  :title="ch.driftStatus === 'critical' ? 'Quality drifting down significantly' : 'Quality drift detected'"></span>
            <span v-if="ch.isMixedModels" class="mixed-badge" :title="modelBreakdownText(ch.modelBreakdown)">mixed</span>
            <span v-else-if="ch.dominantModel" class="char-dominant-model" :title="ch.dominantModel || ''">{{ shortModel(ch.dominantModel) }}</span>
            <!-- Manage button -->
            <button class="btn-manage" @click.stop="$emit('openTraining', { projectName: project.name, characterSlug: ch.slug })" title="Manage training">
              Manage
            </button>
          </div>
        </div>
        <div v-if="project.charsNeedingLora.length > 0" class="detail-actions">
          <button class="btn btn-action" @click.stop="$emit('trainAll', project)" :disabled="actionLoading === 'train-' + project.id">
            Train {{ project.charsNeedingLora.length }} Ready LoRAs
          </button>
        </div>
      </div>

      <!-- Quality Insights (lazy-loaded) -->
      <div v-if="qualityLoading" class="detail-section" style="text-align: center; padding: 20px;">
        <div class="spinner" style="width: 20px; height: 20px; margin: 0 auto;"></div>
        <p style="font-size: 11px; color: var(--text-muted); margin-top: 8px;">Loading quality data...</p>
      </div>
      <div v-else-if="hasQualityData" class="detail-section">
        <div class="detail-section-header">
          <span>Quality Insights</span>
        </div>
        <div class="quality-row-container">
          <!-- Top checkpoint -->
          <div v-if="checkpointRankings.length > 0" class="quality-item">
            <div class="quality-item-label">Top Checkpoint</div>
            <div class="quality-item-value">
              {{ shortModel(checkpointRankings[0].checkpoint) }}
              <span class="quality-pct">{{ (checkpointRankings[0].avg_quality * 100).toFixed(0) }}% avg</span>
            </div>
            <div v-for="(ckpt, idx) in checkpointRankings.slice(1, 3)" :key="ckpt.checkpoint" class="quality-sub">
              #{{ idx + 2 }} {{ shortModel(ckpt.checkpoint) }} {{ (ckpt.avg_quality * 100).toFixed(0) }}%
            </div>
          </div>

          <!-- Drift alerts -->
          <div v-if="driftAlerts.length > 0" class="quality-item">
            <div class="quality-item-label">Drift Alerts</div>
            <div v-for="alert in driftAlerts.slice(0, 3)" :key="alert.character_slug" class="drift-card-mini"
                 :class="{ 'drift-critical': alert.alert }">
              <strong>{{ alert.character_slug }}</strong>
              <span class="drift-badge-mini" :class="alert.alert ? 'badge-critical' : 'badge-warn'">
                {{ alert.drift > 0 ? '+' : '' }}{{ (alert.drift * 100).toFixed(1) }}%
              </span>
            </div>
          </div>

          <!-- Mini quality trend chart -->
          <div v-if="trendData.length > 1" class="quality-item quality-item-chart">
            <div class="quality-item-label">14d Trend</div>
            <svg :viewBox="`0 0 ${chartW} ${chartH}`" class="trend-chart-mini">
              <line v-for="y in [0.4, 0.6, 0.8]" :key="y"
                    :x1="10" :x2="chartW - 10"
                    :y1="trendY(y)" :y2="trendY(y)"
                    class="grid-line-mini" />
              <polyline :points="trendLinePoints" class="trend-line-mini" />
              <circle v-for="(pt, i) in trendPointsMapped" :key="i"
                      :cx="pt.x" :cy="pt.y" r="2" class="trend-dot-mini" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Scenes & Shots -->
      <div class="detail-section">
        <div class="detail-section-header">
          <span>Scenes &amp; Shots</span>
          <span class="detail-count">{{ project.scenes.length }} scenes, {{ project.totalShots }} shots</span>
        </div>
        <div v-if="project.scenes.length > 0" class="scene-list">
          <div v-for="scene in project.scenes" :key="scene.id" class="scene-row">
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
        <div v-if="project.scenes.length === 0" class="detail-actions">
          <button class="btn btn-action" @click.stop="$emit('generateScenes', project)" :disabled="actionLoading === 'scenes-' + project.id">
            Generate Scenes from Story
          </button>
        </div>
      </div>

      <!-- Episodes -->
      <div class="detail-section">
        <div class="detail-section-header">
          <span>Episodes</span>
          <span class="detail-count">{{ project.episodes.length }} episodes</span>
        </div>
        <div v-if="project.episodes.length > 0" class="episode-list">
          <div v-for="ep in project.episodes" :key="ep.id" class="episode-row">
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

      <!-- Orchestrator Pipeline (per-project) -->
      <div v-if="pipelineEntries.length > 0" class="detail-section">
        <div class="detail-section-header">
          <span>Production Pipeline</span>
        </div>
        <!-- Project phases -->
        <div v-if="projectPhases.length > 0" class="orch-card" :class="{ 'orch-card-dim': projectPhases.every(p => p.status === 'completed') }">
          <div class="orch-card-header">
            <span class="orch-card-title">Project</span>
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
                <button v-if="p.status === 'failed'" class="btn btn-sm orch-action-btn" @click.stop="$emit('overrideEntry', p, 'reset')">Reset</button>
                <button v-if="p.status === 'active' || p.status === 'pending'" class="btn btn-sm orch-action-btn" @click.stop="$emit('overrideEntry', p, 'skip')">Skip</button>
              </template>
            </span>
          </div>
        </div>
        <!-- Character phases -->
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
                  <button v-if="p.status === 'failed'" class="btn btn-sm orch-action-btn" @click.stop="$emit('overrideEntry', p, 'reset')">Reset</button>
                  <button v-if="p.status === 'active'" class="btn btn-sm orch-action-btn" @click.stop="$emit('overrideEntry', p, 'skip')">Skip</button>
                </template>
              </span>
            </div>
          </div>
        </div>
      </div>
      <div v-else-if="expanded && !qualityLoading" class="detail-section">
        <div class="detail-section-header">
          <span>Production Pipeline</span>
        </div>
        <div style="color: var(--text-muted); font-size: 12px; padding: 4px 0;">
          No pipeline entries. <button class="btn-link" @click.stop="$emit('initOrchestrator', project.id)">Initialize</button>
        </div>
      </div>

      <!-- Next Step -->
      <div class="next-step" v-if="project.nextAction">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span><strong>Next:</strong> {{ project.nextAction }}</span>
          <div style="display: flex; gap: 6px;">
            <button v-if="project.charsNeedingLora.length > 0" class="btn btn-action"
                    @click.stop="$emit('trainAll', project)" :disabled="actionLoading === 'train-' + project.id">
              Train Ready
            </button>
            <button v-if="project.scenes.length === 0" class="btn btn-action"
                    @click.stop="$emit('generateScenes', project)" :disabled="actionLoading === 'scenes-' + project.id">
              Generate Scenes
            </button>
            <button class="btn btn-action" @click.stop="$emit('openTraining', { projectName: project.name })">
              Manage Training
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ProjectCard, ProjectQualityData, DriftAlert, QualityTrendPoint, CheckpointRanking, PipelineEntry, ModelBreakdown } from '@/types'

const props = defineProps<{
  project: ProjectCard
  expanded: boolean
  qualityData: ProjectQualityData | null
  qualityLoading: boolean
  actionLoading: string | null
}>()

defineEmits<{
  toggle: [id: number]
  openTraining: [params: { projectName: string; characterSlug?: string }]
  trainAll: [project: ProjectCard]
  generateScenes: [project: ProjectCard]
  overrideEntry: [entry: PipelineEntry, action: 'skip' | 'reset' | 'complete']
  initOrchestrator: [projectId: number]
}>()

// Quality data shortcuts
const driftAlerts = computed<DriftAlert[]>(() => props.qualityData?.driftAlerts ?? [])
const trendData = computed<QualityTrendPoint[]>(() => props.qualityData?.trendData ?? [])
const checkpointRankings = computed<CheckpointRanking[]>(() => props.qualityData?.checkpointRankings ?? [])
const pipelineEntries = computed<PipelineEntry[]>(() => props.qualityData?.pipelineEntries ?? [])

const hasQualityData = computed(() =>
  driftAlerts.value.length > 0 || trendData.value.length > 1 || checkpointRankings.value.length > 0
)

const alertCount = computed(() => {
  return props.project.warnings.length + driftAlerts.value.filter(a => a.alert).length
})

// Sparkline (collapsed header)
const sparklinePoints = computed(() => {
  const data = trendData.value
  if (data.length < 2) return ''
  const maxQ = Math.max(...data.map(d => d.avg_quality), 1)
  const minQ = Math.min(...data.map(d => d.avg_quality), 0)
  const range = maxQ - minQ || 1
  const step = 80 / (data.length - 1)
  return data.map((d, i) => `${i * step},${24 - ((d.avg_quality - minQ) / range) * 20}`).join(' ')
})

// Trend chart (expanded)
const chartW = 400
const chartH = 100

function trendY(val: number): number {
  return chartH - 10 - (val * (chartH - 20))
}

const trendPointsMapped = computed(() => {
  if (!trendData.value.length) return []
  const w = chartW - 20
  const step = trendData.value.length > 1 ? w / (trendData.value.length - 1) : 0
  return trendData.value.map((pt, i) => ({
    x: 10 + i * step,
    y: trendY(pt.avg_quality),
  }))
})

const trendLinePoints = computed(() =>
  trendPointsMapped.value.map(p => `${p.x},${p.y}`).join(' ')
)

// Orchestrator groupings
const projectPhases = computed(() =>
  pipelineEntries.value
    .filter(e => e.entity_type === 'project')
    .sort((a, b) => {
      const order = ['scene_planning', 'shot_prep', 'video_gen', 'scene_assembly', 'episode', 'publishing']
      return (order.indexOf(a.phase) ?? 99) - (order.indexOf(b.phase) ?? 99)
    })
)

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

// Utilities
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

function rateClass(rate: number): string {
  if (rate >= 0.6) return 'rate-high'
  if (rate >= 0.3) return 'rate-mid'
  return 'rate-low'
}
</script>

<style scoped>
/* Project card */
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

.alert-badge {
  font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 10px;
  background: rgba(255,152,0,0.2); color: var(--status-warning, #ff9800);
}

/* Sparkline */
.sparkline { width: 80px; height: 24px; flex-shrink: 0; }
.sparkline-line { fill: none; stroke: var(--accent-primary); stroke-width: 1.5; opacity: 0.7; }

/* Stage pills */
.stage-pill {
  font-size: 10px; padding: 2px 8px; border-radius: 10px; white-space: nowrap;
}
.pill-done { background: rgba(80,160,80,0.15); color: var(--status-success, #4caf50); }
.pill-partial { background: rgba(122,162,247,0.15); color: var(--accent-primary); }
.pill-empty { background: var(--bg-primary); color: var(--text-muted); }

/* Warnings */
.model-warnings {
  background: rgba(255,152,0,0.06); border-top: 1px solid rgba(255,152,0,0.2);
  padding: 8px 16px;
}
.model-warning-row { font-size: 12px; color: var(--status-warning, #ff9800); padding: 2px 0; }
.warning-icon {
  display: inline-flex; width: 16px; height: 16px; align-items: center; justify-content: center;
  border-radius: 50%; background: var(--status-warning, #ff9800); color: #000;
  font-size: 10px; font-weight: 800; margin-right: 6px; flex-shrink: 0;
}

/* Detail sections */
.detail-section { padding: 12px 16px; border-top: 1px solid var(--border-primary); }
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
  display: grid; grid-template-columns: 16px 1fr 70px 1.2fr 45px 16px auto auto; gap: 8px; align-items: center;
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

/* Approval rate column */
.char-approval { font-size: 11px; text-align: center; font-weight: 500; }
.rate-high { color: var(--status-success, #4caf50); }
.rate-mid { color: var(--status-warning, #ff9800); }
.rate-low { color: var(--status-error, #f44336); }

/* Drift indicator dot */
.drift-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
.drift-warn { background: var(--status-warning, #ff9800); }
.drift-critical { background: var(--status-error, #f44336); animation: pulse 2s infinite; }

/* Manage button */
.btn-manage {
  font-size: 10px; padding: 1px 8px; border-radius: 3px; cursor: pointer;
  background: transparent; border: 1px solid var(--border-primary); color: var(--text-muted);
  font-family: var(--font-primary); transition: all 150ms ease;
}
.btn-manage:hover { border-color: var(--accent-primary); color: var(--accent-primary); }

/* Quality Insights row */
.quality-row-container { display: flex; gap: 16px; flex-wrap: wrap; }
.quality-item {
  flex: 1; min-width: 160px; padding: 8px 10px;
  background: var(--bg-primary); border-radius: 4px; border: 1px solid var(--border-primary);
}
.quality-item-chart { min-width: 280px; flex: 2; }
.quality-item-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 4px; }
.quality-item-value { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.quality-pct { font-size: 11px; color: var(--text-muted); font-weight: 400; margin-left: 4px; }
.quality-sub { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

/* Mini drift cards */
.drift-card-mini {
  display: flex; justify-content: space-between; align-items: center;
  padding: 3px 0; font-size: 12px; border-left: 2px solid var(--status-warning, #ff9800);
  padding-left: 6px; margin-top: 4px;
}
.drift-card-mini.drift-critical { border-left-color: var(--status-error, #f44336); }
.drift-badge-mini {
  font-size: 10px; padding: 0 6px; border-radius: 8px; font-weight: 500;
}
.badge-warn { background: rgba(255, 152, 0, 0.2); color: var(--status-warning, #ff9800); }
.badge-critical { background: rgba(244, 67, 54, 0.2); color: var(--status-error, #f44336); }

/* Mini trend chart */
.trend-chart-mini { width: 100%; height: auto; }
.grid-line-mini { stroke: var(--border-primary); stroke-width: 0.5; stroke-dasharray: 3 3; }
.trend-line-mini { fill: none; stroke: var(--accent-primary); stroke-width: 1.5; stroke-linejoin: round; }
.trend-dot-mini { fill: var(--accent-primary); }

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

/* Orchestrator */
.orch-grid {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 8px;
}
.orch-card {
  background: var(--bg-primary); border: 1px solid var(--border-primary);
  border-radius: 6px; padding: 10px 12px; transition: opacity 150ms ease;
}
.orch-card:first-child { margin-bottom: 8px; }
.orch-card-dim { opacity: 0.6; }
.orch-card:hover .orch-action-btn { opacity: 1; }
.orch-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.orch-card-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.orch-card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 6px; min-height: 20px; }
.orch-card-actions { display: flex; gap: 4px; }
.orch-action-btn { font-size: 10px !important; padding: 1px 6px !important; opacity: 0; transition: opacity 150ms ease; }
.orch-card:hover .orch-action-btn, .orch-action-btn:focus { opacity: 1; }
.phase-pills { display: flex; flex-wrap: wrap; gap: 4px; }
.phase-pill { font-size: 11px; padding: 2px 8px; border-radius: 10px; white-space: nowrap; }
.phase-pill.pstatus-active { animation: pill-pulse 2s ease-in-out infinite; }
@keyframes pill-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
.pipeline-status-badge { font-size: 11px; padding: 1px 6px; border-radius: 3px; }
.pstatus-pending { background: var(--bg-tertiary); color: var(--text-secondary); }
.pstatus-active { background: rgba(122, 162, 247, 0.2); color: var(--accent-primary); }
.pstatus-completed { background: rgba(80, 160, 80, 0.2); color: var(--status-success, #4caf50); }
.pstatus-skipped { background: var(--bg-tertiary); color: var(--text-muted); }
.pstatus-failed { background: rgba(160, 80, 80, 0.2); color: var(--status-error, #f44336); }
.pstatus-blocked { background: rgba(255, 152, 0, 0.2); color: var(--status-warning, #ff9800); }

/* Next step */
.next-step {
  padding: 10px 16px; border-top: 1px solid var(--border-primary);
  font-size: 12px; color: var(--text-muted); background: rgba(122,162,247,0.03);
}
.next-step strong { color: var(--accent-primary); }

/* Buttons */
.btn {
  padding: 6px 14px; border: 1px solid var(--border-primary); border-radius: 4px;
  background: var(--bg-secondary); color: var(--text-primary); cursor: pointer;
  font-size: 13px; font-family: var(--font-primary);
}
.btn:hover { background: var(--bg-tertiary, var(--bg-secondary)); }
.btn:disabled { opacity: 0.5; cursor: default; }
.btn-action {
  font-size: 12px; padding: 4px 12px;
  border-color: var(--accent-primary); color: var(--accent-primary);
}
.btn-action:hover { background: rgba(122,162,247,0.1); }
.btn-sm { padding: 3px 10px; font-size: 12px; }
.btn-link {
  background: none; border: none; color: var(--accent-primary); cursor: pointer;
  font-size: 12px; font-family: var(--font-primary); text-decoration: underline;
  padding: 0;
}

/* Spinner */
.spinner {
  border: 3px solid var(--border-primary); border-top: 3px solid var(--accent-primary);
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

@media (max-width: 900px) {
  .stage-pill { display: none; }
  .sparkline { display: none; }
  .char-row { grid-template-columns: 16px 1fr 60px; }
  .char-model-info, .char-approval, .drift-dot, .mixed-badge, .char-dominant-model, .btn-manage { display: none; }
  .scene-row { grid-template-columns: 16px 1fr 80px; }
  .scene-video, .scene-status-label { display: none; }
  .episode-row { grid-template-columns: 30px 1fr 70px; }
  .episode-scenes, .episode-duration { display: none; }
  .orch-grid { grid-template-columns: 1fr; }
  .quality-row-container { flex-direction: column; }
}
</style>
