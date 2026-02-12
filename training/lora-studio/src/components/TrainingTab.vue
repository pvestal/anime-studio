<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <div>
        <h2 style="font-size: 18px; font-weight: 500;">Training Jobs</h2>
        <p style="font-size: 12px; color: var(--text-muted);">LoRA training produces ComfyUI-compatible .safetensors files</p>
      </div>
      <button class="btn" @click="refresh" :disabled="trainingStore.loading">
        Refresh
      </button>
    </div>

    <!-- Stats bar -->
    <div v-if="trainingStore.jobs.length > 0" style="display: flex; gap: 12px; margin-bottom: 20px;">
      <div class="card" style="flex: 1; text-align: center; padding: 12px;">
        <div style="font-size: 24px; font-weight: 600; color: var(--status-success);">{{ completedCount }}</div>
        <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Completed</div>
      </div>
      <div class="card" style="flex: 1; text-align: center; padding: 12px;">
        <div style="font-size: 24px; font-weight: 600; color: var(--status-warning);">{{ runningCount }}</div>
        <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Running</div>
      </div>
      <div class="card" style="flex: 1; text-align: center; padding: 12px;">
        <div style="font-size: 24px; font-weight: 600; color: var(--status-error);">{{ failedCount }}</div>
        <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Failed</div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="trainingStore.loading" style="text-align: center; padding: 48px;">
      <div class="spinner" style="width: 32px; height: 32px; margin: 0 auto 16px;"></div>
      <p style="color: var(--text-muted);">Loading training jobs...</p>
    </div>

    <!-- Error -->
    <div v-else-if="trainingStore.error" class="card" style="background: rgba(160,80,80,0.1); border-color: var(--status-error);">
      <p style="color: var(--status-error);">{{ trainingStore.error }}</p>
      <button class="btn" @click="trainingStore.clearError()" style="margin-top: 8px;">Dismiss</button>
    </div>

    <!-- Empty -->
    <div v-else-if="trainingStore.jobs.length === 0" style="text-align: center; padding: 48px;">
      <p style="color: var(--text-muted); font-size: 16px;">No training jobs yet</p>
      <p style="color: var(--text-muted); font-size: 13px; margin-top: 8px;">
        Go to <strong>Characters</strong> tab and click "Start Training" on a character with 10+ approved images.
      </p>
    </div>

    <!-- Jobs list (newest first) -->
    <div v-else style="display: flex; flex-direction: column; gap: 12px;">
      <div
        v-for="job in sortedJobs"
        :key="job.job_id"
        class="card"
        :style="jobBorderStyle(job)"
      >
        <!-- Header: character name + status badge -->
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
          <div style="display: flex; align-items: center; gap: 12px;">
            <h3 style="font-size: 16px; font-weight: 500;">{{ job.character_name }}</h3>
            <span class="badge" :class="statusClass(job.status)">{{ job.status }}</span>
          </div>
          <div style="display: flex; gap: 8px; align-items: center;">
            <button
              v-if="job.status === 'running' || job.status === 'completed' || job.status === 'failed'"
              class="btn"
              style="font-size: 11px; padding: 3px 8px;"
              @click="toggleLog(job.job_id)"
            >
              {{ expandedLog === job.job_id ? 'Hide Log' : 'View Log' }}
            </button>
          </div>
        </div>

        <!-- Running: epoch progress bar -->
        <div v-if="job.status === 'running' && job.epoch && job.total_epochs" style="margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
            <span style="color: var(--text-secondary);">
              Epoch {{ job.epoch }}/{{ job.total_epochs }}
            </span>
            <span v-if="job.loss != null" style="color: var(--text-muted);">
              Loss: {{ job.loss.toFixed(6) }}
            </span>
          </div>
          <div class="progress-track" style="height: 6px;">
            <div
              class="progress-bar"
              style="background: var(--status-warning);"
              :style="{ width: `${(job.epoch / job.total_epochs) * 100}%` }"
            ></div>
          </div>
        </div>

        <!-- Config grid -->
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px 16px; font-size: 13px; margin-bottom: 8px;">
          <div>
            <div style="color: var(--text-muted); font-size: 11px;">Images</div>
            <div style="color: var(--text-primary); font-weight: 500;">{{ job.approved_images }}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 11px;">Epochs</div>
            <div style="color: var(--text-primary); font-weight: 500;">{{ job.epochs }}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 11px;">Learning Rate</div>
            <div style="color: var(--text-primary); font-weight: 500;">{{ job.learning_rate }}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 11px;">Resolution</div>
            <div style="color: var(--text-primary); font-weight: 500;">{{ job.resolution }}</div>
          </div>
          <div v-if="job.checkpoint">
            <div style="color: var(--text-muted); font-size: 11px;">Checkpoint</div>
            <div style="color: var(--text-primary); font-weight: 500; font-size: 11px;">{{ job.checkpoint.replace('.safetensors', '') }}</div>
          </div>
        </div>

        <!-- Completed: results -->
        <div v-if="job.status === 'completed'" style="background: rgba(80,160,80,0.08); border: 1px solid rgba(80,160,80,0.2); border-radius: 4px; padding: 10px 12px; margin-top: 8px;">
          <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 6px 16px; font-size: 12px;">
            <div v-if="job.best_loss != null">
              <span style="color: var(--text-muted);">Best Loss:</span>
              <span style="color: var(--status-success); font-weight: 500; margin-left: 4px;">{{ job.best_loss.toFixed(6) }}</span>
            </div>
            <div v-if="job.final_loss != null">
              <span style="color: var(--text-muted);">Final Loss:</span>
              <span style="color: var(--text-secondary); margin-left: 4px;">{{ job.final_loss.toFixed(6) }}</span>
            </div>
            <div v-if="job.total_steps">
              <span style="color: var(--text-muted);">Steps:</span>
              <span style="color: var(--text-secondary); margin-left: 4px;">{{ job.total_steps }}</span>
            </div>
            <div v-if="job.file_size_mb">
              <span style="color: var(--text-muted);">File Size:</span>
              <span style="color: var(--text-secondary); margin-left: 4px;">{{ job.file_size_mb }} MB</span>
            </div>
          </div>
          <div v-if="job.output_path" style="margin-top: 8px; font-size: 11px; color: var(--text-muted); font-family: monospace; word-break: break-all;">
            {{ job.output_path }}
          </div>
        </div>

        <!-- Failed: error message -->
        <div v-if="job.status === 'failed'" style="background: rgba(160,80,80,0.08); border: 1px solid rgba(160,80,80,0.2); border-radius: 4px; padding: 10px 12px; margin-top: 8px;">
          <div v-if="job.error" style="font-size: 12px; color: var(--status-error); font-family: monospace; word-break: break-all;">
            {{ job.error }}
          </div>
          <div v-else style="font-size: 12px; color: var(--status-error);">
            Training failed — check the log for details.
          </div>
        </div>

        <!-- Timestamps -->
        <div style="display: flex; gap: 16px; margin-top: 10px; font-size: 11px; color: var(--text-muted);">
          <span>Created: {{ formatTime(job.created_at) }}</span>
          <span v-if="job.started_at">Started: {{ formatTime(job.started_at) }}</span>
          <span v-if="job.completed_at">Completed: {{ formatTime(job.completed_at) }}</span>
          <span v-if="job.failed_at">Failed: {{ formatTime(job.failed_at) }}</span>
          <span v-if="job.status === 'running' && job.started_at" style="color: var(--status-warning);">
            Running for {{ elapsed(job.started_at) }}
          </span>
        </div>

        <!-- Log viewer -->
        <div v-if="expandedLog === job.job_id" style="margin-top: 12px;">
          <div v-if="logLoading" style="text-align: center; padding: 16px;">
            <div class="spinner" style="width: 20px; height: 20px; margin: 0 auto;"></div>
          </div>
          <pre v-else-if="logLines.length > 0" style="background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 4px; padding: 10px 12px; font-size: 11px; line-height: 1.5; max-height: 300px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; color: var(--text-secondary);">{{ logLines.join('\n') }}</pre>
          <p v-else style="font-size: 12px; color: var(--text-muted); padding: 8px;">No log output yet.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useTrainingStore } from '@/stores/training'
import type { TrainingJob } from '@/types'

const trainingStore = useTrainingStore()
const expandedLog = ref<string | null>(null)
const logLines = ref<string[]>([])
const logLoading = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

// Auto-refresh every 5s while any job is running
onMounted(() => {
  pollTimer = setInterval(() => {
    const hasActive = trainingStore.jobs.some(j => j.status === 'running' || j.status === 'queued')
    if (hasActive) {
      trainingStore.fetchTrainingJobs()
      if (expandedLog.value) fetchLog(expandedLog.value)
    }
  }, 5000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

const sortedJobs = computed(() => {
  return [...trainingStore.jobs].sort((a, b) =>
    new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  )
})

const completedCount = computed(() => trainingStore.jobs.filter(j => j.status === 'completed').length)
const runningCount = computed(() => trainingStore.jobs.filter(j => j.status === 'running' || j.status === 'queued').length)
const failedCount = computed(() => trainingStore.jobs.filter(j => j.status === 'failed').length)

function statusClass(status: string): string {
  switch (status) {
    case 'completed': return 'badge-approved'
    case 'running': return 'badge-pending'
    case 'queued': return 'badge-pending'
    case 'failed': return 'badge-rejected'
    default: return ''
  }
}

function jobBorderStyle(job: TrainingJob) {
  if (job.status === 'completed') return { borderLeftColor: 'var(--status-success)', borderLeftWidth: '3px' }
  if (job.status === 'running') return { borderLeftColor: 'var(--status-warning)', borderLeftWidth: '3px' }
  if (job.status === 'failed') return { borderLeftColor: 'var(--status-error)', borderLeftWidth: '3px' }
  return {}
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

function elapsed(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ${sec % 60}s`
  return `${Math.floor(min / 60)}h ${min % 60}m`
}

async function fetchLog(jobId: string) {
  logLoading.value = true
  try {
    const resp = await fetch(`/api/lora/training/jobs/${encodeURIComponent(jobId)}/log?tail=100`)
    if (resp.ok) {
      const data = await resp.json()
      logLines.value = data.lines || []
    } else {
      logLines.value = ['(Log not available)']
    }
  } catch {
    logLines.value = ['(Failed to fetch log)']
  } finally {
    logLoading.value = false
  }
}

async function toggleLog(jobId: string) {
  if (expandedLog.value === jobId) {
    expandedLog.value = null
    logLines.value = []
  } else {
    expandedLog.value = jobId
    await fetchLog(jobId)
  }
}

function refresh() {
  trainingStore.fetchTrainingJobs()
  if (expandedLog.value) fetchLog(expandedLog.value)
}
</script>
