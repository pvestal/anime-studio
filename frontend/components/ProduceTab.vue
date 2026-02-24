<template>
  <div class="produce-dashboard">
    <!-- Header -->
    <div class="produce-header">
      <h2>Produce</h2>
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
          <span v-if="comfyQueue.queue_running > 0 || comfyQueue.queue_pending > 0" class="gpu-chip gpu-busy">
            ComfyUI {{ comfyQueue.queue_running }}R / {{ comfyQueue.queue_pending }}Q
          </span>
        </div>
        <div style="display: flex; gap: 6px; align-items: center;">
          <button class="btn btn-sm" :class="orchestratorStatus?.enabled ? 'btn-danger-sm' : 'btn-success-sm'"
                  @click="toggleOrchestrator" :title="orchestratorStatus?.enabled ? 'Disable orchestrator' : 'Enable orchestrator'">
            Orchestrator {{ orchestratorStatus?.enabled ? 'On' : 'Off' }}
          </button>
          <button class="btn btn-secondary" @click="refreshAll" :disabled="loading">
            {{ loading ? 'Loading...' : 'Refresh' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Active Jobs Banner -->
    <div v-if="runningTrainingJobs.length > 0 || comfyQueue.queue_running > 0" class="active-jobs">
      <div class="active-jobs-header">Active Right Now</div>
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
      <div v-if="comfyQueue.queue_running > 0" class="active-job-row">
        <span class="active-job-dot" style="background: var(--status-warning);"></span>
        <span class="active-job-label"><strong>ComfyUI</strong> generating</span>
        <span class="active-job-detail">{{ comfyQueue.queue_running }} running, {{ comfyQueue.queue_pending }} queued</span>
      </div>
    </div>

    <!-- Recent Failures Banner -->
    <div v-if="recentFailures.length > 0" class="failures-banner">
      <div class="failures-header">Recent Failures</div>
      <div v-for="job in recentFailures" :key="job.job_id" class="failure-row">
        <span style="color: var(--status-error);">Training {{ job.character_name }} failed</span>
        <span class="failure-error">{{ job.error || 'Unknown error' }}</span>
        <span class="failure-time">{{ elapsed(job.failed_at || job.created_at) }}</span>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading && projectCards.length === 0" style="text-align: center; padding: 48px;">
      <div class="spinner" style="width: 32px; height: 32px; margin: 0 auto 16px;"></div>
      <p style="color: var(--text-muted);">Loading...</p>
    </div>

    <!-- Per-Project Cards -->
    <ProjectPipelineCard
      v-for="proj in projectCards"
      :key="proj.id"
      :project="proj"
      :expanded="expandedProjects.has(proj.id)"
      :qualityData="qualityDataMap.get(proj.id) ?? null"
      :qualityLoading="qualityLoadingSet.has(proj.id)"
      :actionLoading="actionLoading"
      @toggle="toggleProject"
      @openTraining="openTrainingPanel"
      @trainAll="trainAll"
      @generateScenes="generateScenes"
      @overrideEntry="overrideEntry"
      @initOrchestrator="initOrchestrator"
    />

    <!-- No projects -->
    <div v-if="!loading && projectCards.length === 0" style="text-align: center; padding: 48px; color: var(--text-muted);">
      No projects found.
    </div>

    <!-- System Section (collapsible) -->
    <div v-if="learningStats" class="system-section">
      <div class="system-toggle" @click="showSystem = !showSystem">
        <span class="system-title">System</span>
        <span class="toggle-arrow" :class="{ open: showSystem }">&#9654;</span>
      </div>
      <template v-if="showSystem">
        <!-- Autonomy stats -->
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

        <!-- EventBus -->
        <div v-if="eventStats" style="margin-top: 12px;">
          <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 6px;">EventBus</div>
          <div class="event-chips">
            <span class="chip" v-for="evt in eventStats.registered_events" :key="evt">{{ evt }}</span>
            <span class="chip chip-count">{{ eventStats.total_handlers }} handlers</span>
            <span class="chip chip-count">{{ eventStats.total_emits }} emits</span>
            <span class="chip chip-error" v-if="eventStats.total_errors > 0">{{ eventStats.total_errors }} errors</span>
          </div>
        </div>
      </template>
    </div>

    <!-- Training Panel slide-over -->
    <TrainingPanel
      :open="trainingPanelOpen"
      :filterProject="trainingPanelProject"
      :filterCharacter="trainingPanelCharacter"
      @close="trainingPanelOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useProductionData } from '@/composables/useProductionData'
import ProjectPipelineCard from './ProjectPipelineCard.vue'
import TrainingPanel from './training/TrainingPanel.vue'
import type { TrainingJob, ProjectCard } from '@/types'

const {
  loading,
  actionLoading,
  gpuStatus,
  expandedProjects,
  qualityDataMap,
  qualityLoadingSet,
  learningStats,
  eventStats,
  orchestratorStatus,
  nvidiaBusy,
  comfyQueue,
  ollamaModels,
  runningTrainingJobs,
  recentFailures,
  projectCards,
  refreshAll,
  toggleProject,
  trainAll,
  generateScenes,
  toggleOrchestrator,
  initOrchestrator,
  overrideEntry,
} = useProductionData()

// Training panel state
const trainingPanelOpen = ref(false)
const trainingPanelProject = ref<string | undefined>()
const trainingPanelCharacter = ref<string | undefined>()
const showSystem = ref(false)

function openTrainingPanel(params: { projectName: string; characterSlug?: string }) {
  trainingPanelProject.value = params.projectName
  trainingPanelCharacter.value = params.characterSlug
  trainingPanelOpen.value = true
}

// Utility functions
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
</script>

<style scoped>
.produce-dashboard { max-width: 1200px; margin: 0 auto; }

.produce-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;
}
.produce-header h2 { font-size: 18px; font-weight: 500; margin: 0; }
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
.btn-sm { padding: 3px 10px; font-size: 12px; }
.btn-success-sm { border-color: var(--status-success, #4caf50); color: var(--status-success, #4caf50); }
.btn-danger-sm { border-color: var(--status-error, #f44336); color: var(--status-error, #f44336); }

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

/* System section */
.system-section {
  background: var(--bg-secondary); border: 1px solid var(--border-primary);
  border-radius: 6px; padding: 12px 16px; margin-top: 16px;
}
.system-toggle {
  display: flex; justify-content: space-between; align-items: center;
  cursor: pointer; user-select: none;
}
.system-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.3px; }
.toggle-arrow { font-size: 10px; color: var(--text-muted); transition: transform 150ms ease; display: inline-block; }
.toggle-arrow.open { transform: rotate(90deg); }

/* Mini stats */
.mini-stat {
  display: flex; flex-direction: column; align-items: center;
  padding: 8px 16px; background: var(--bg-primary); border-radius: 4px;
  border: 1px solid var(--border-primary);
}
.mini-value { font-size: 18px; font-weight: 600; color: var(--text-primary); }
.mini-label { font-size: 10px; color: var(--text-muted); margin-top: 2px; }

/* Event chips */
.event-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  padding: 3px 10px; border-radius: 12px; font-size: 12px;
  background: var(--bg-primary); border: 1px solid var(--border-primary); color: var(--text-secondary);
}
.chip-count { background: var(--accent-primary); color: #fff; border-color: var(--accent-primary); opacity: 0.9; }
.chip-error { background: var(--status-error, #f44336); color: #fff; border-color: var(--status-error, #f44336); }

/* Spinner */
.spinner {
  border: 3px solid var(--border-primary); border-top: 3px solid var(--accent-primary);
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 900px) {
  .gpu-chips { display: none; }
}
</style>
