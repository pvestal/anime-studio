<template>
  <div>
    <!-- Header -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
      <div>
        <h2 style="font-size: 18px; font-weight: 500; margin: 0;">LoRA Training</h2>
        <p style="font-size: 12px; color: var(--text-muted); margin: 4px 0 0;">
          {{ trainingStore.loras.length }} trained &middot;
          {{ runningCount }} running &middot;
          {{ readyToTrainCount }} ready
        </p>
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <select
          v-if="projectNames.length > 1"
          v-model="selectedProject"
          class="project-select"
        >
          <option v-for="p in projectNames" :key="p" :value="p">{{ p }}</option>
        </select>
        <button class="btn" @click="trainAllReady" :disabled="readyToTrainCount === 0 || trainingStore.loading" style="font-size: 12px; color: var(--status-success); border-color: var(--status-success);">
          Train All Ready ({{ readyToTrainCount }})
        </button>
        <button class="btn" @click="reconcile" :disabled="trainingStore.loading" style="font-size: 12px;">Reconcile</button>
        <button class="btn" @click="refresh" :disabled="trainingStore.loading">Refresh</button>
      </div>
    </div>

    <!-- Summary Stats Bar -->
    <div class="stats-bar">
      <div class="stat-card">
        <div class="stat-value" style="color: var(--status-success);">{{ trainingStore.loras.length }}</div>
        <div class="stat-label">Trained LoRAs</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color: var(--status-warning);">{{ runningCount }}</div>
        <div class="stat-label">Training</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color: var(--accent-primary);">{{ readyToTrainCount }}</div>
        <div class="stat-label">Ready</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ totalApproved }}</div>
        <div class="stat-label">Approved Images</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color: var(--status-error);">{{ failedCount }}</div>
        <div class="stat-label">Failed</div>
      </div>
    </div>

    <!-- Filter Pills -->
    <div style="display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap;">
      <button
        v-for="f in filters"
        :key="f.key"
        class="pill"
        :class="{ active: activeFilter === f.key }"
        @click="activeFilter = activeFilter === f.key ? 'all' : f.key"
      >
        {{ f.label }}
        <span v-if="f.count > 0" class="pill-count">{{ f.count }}</span>
      </button>
    </div>

    <!-- Production Readiness -->
    <ProductionReadiness
      v-if="selectedProject"
      :project-name="selectedProject"
      @train="(slug: string) => startTrainingForChar({ slug, name: slug } as Character)"
      @generate="(slug: string) => openBatchGenerate(slug)"
    />

    <!-- Loading -->
    <div v-if="trainingStore.loading && filteredCharacters.length === 0" style="text-align: center; padding: 48px;">
      <div class="spinner" style="width: 32px; height: 32px; margin: 0 auto 16px;"></div>
      <p style="color: var(--text-muted);">Loading...</p>
    </div>

    <!-- Error -->
    <div v-else-if="trainingStore.error" class="card" style="background: rgba(160,80,80,0.1); border-color: var(--status-error);">
      <p style="color: var(--status-error);">{{ trainingStore.error }}</p>
      <button class="btn" @click="trainingStore.clearError()" style="margin-top: 8px;">Dismiss</button>
    </div>

    <!-- Character LoRA Grid -->
    <div v-else class="lora-grid">
      <div
        v-for="char in filteredCharacters"
        :key="char.slug"
        class="lora-card"
        :class="cardClass(char)"
      >
        <!-- Card Header -->
        <div class="lora-card-header">
          <div style="flex: 1; min-width: 0;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 15px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ char.name }}</span>
              <span v-if="charJob(char.slug)?.status === 'running'" class="badge badge-pending" style="font-size: 10px; white-space: nowrap;">
                Training E{{ charJob(char.slug)?.epoch }}/{{ charJob(char.slug)?.total_epochs }}
              </span>
            </div>
            <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">{{ char.project_name }}</div>
          </div>
          <div>
            <span v-if="charLora(char.slug)" class="status-dot status-trained" title="LoRA trained"></span>
            <span v-else-if="charStats(char.slug).canTrain" class="status-dot status-ready" title="Ready to train"></span>
            <span v-else class="status-dot status-insufficient" title="Needs more images"></span>
          </div>
        </div>

        <!-- Running Progress -->
        <div v-if="charJob(char.slug)?.status === 'running'" style="margin: 10px 0;">
          <div class="progress-track" style="height: 4px;">
            <div class="progress-bar" style="background: var(--status-warning); transition: width 0.3s ease;"
                 :style="{ width: `${((charJob(char.slug)?.epoch || 0) / (charJob(char.slug)?.total_epochs || 20)) * 100}%` }"></div>
          </div>
          <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); margin-top: 4px;">
            <span>Loss: {{ charJob(char.slug)?.loss?.toFixed(4) || '...' }}</span>
            <span>{{ elapsed(charJob(char.slug)?.started_at) }}</span>
          </div>
        </div>

        <!-- Config Pills (for trained or running) -->
        <div v-if="charLora(char.slug) || charJob(char.slug)" class="config-pills">
          <span class="config-pill arch">{{ charLora(char.slug)?.architecture || charJob(char.slug)?.model_type || 'sd15' }}</span>
          <span v-if="charJob(char.slug)?.lora_rank" class="config-pill">r{{ charJob(char.slug)?.lora_rank }}</span>
          <span v-if="charJob(char.slug)?.resolution" class="config-pill">{{ charJob(char.slug)?.resolution }}px</span>
          <span v-if="charJob(char.slug)?.epochs" class="config-pill">{{ charJob(char.slug)?.epochs }}ep</span>
          <span v-if="charJob(char.slug)?.learning_rate" class="config-pill">lr{{ charJob(char.slug)?.learning_rate }}</span>
        </div>

        <!-- LoRA Summary (trained) -->
        <div v-if="charLora(char.slug)" class="lora-summary">
          <div class="summary-row">
            <span class="summary-label">File</span>
            <span class="summary-value mono">{{ charLora(char.slug)!.filename }}</span>
          </div>
          <div class="summary-row">
            <span class="summary-label">Size</span>
            <span class="summary-value">{{ charLora(char.slug)!.size_mb }} MB</span>
          </div>
          <div v-if="charJob(char.slug)?.best_loss" class="summary-row">
            <span class="summary-label">Best Loss</span>
            <span class="summary-value" style="color: var(--status-success);">{{ charJob(char.slug)!.best_loss!.toFixed(4) }}</span>
          </div>
          <div v-if="charJob(char.slug)?.total_steps" class="summary-row">
            <span class="summary-label">Steps</span>
            <span class="summary-value">{{ charJob(char.slug)!.total_steps }}</span>
          </div>
          <div class="summary-row">
            <span class="summary-label">Trained</span>
            <span class="summary-value">{{ formatDate(charLora(char.slug)!.created_at) }}</span>
          </div>
        </div>

        <!-- Image count bar -->
        <div style="margin-top: 10px;">
          <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 3px;">
            <span style="color: var(--text-muted);">Approved</span>
            <span style="font-weight: 500;">{{ charStats(char.slug).approved }}</span>
          </div>
          <div class="progress-track" style="height: 3px;">
            <div class="progress-bar" :class="{ ready: charStats(char.slug).canTrain }" :style="{ width: `${Math.min(100, (charStats(char.slug).approved / 100) * 100)}%` }"></div>
          </div>
        </div>

        <!-- Actions -->
        <div style="margin-top: 10px; display: flex; gap: 6px; flex-wrap: wrap;">
          <button
            v-if="!charLora(char.slug) && charStats(char.slug).canTrain && charJob(char.slug)?.status !== 'running'"
            class="btn btn-success"
            style="font-size: 11px; padding: 4px 12px; flex: 1;"
            @click="startTrainingForChar(char)"
            :disabled="trainingStore.loading"
          >
            Start Training
          </button>
          <button
            v-if="charLora(char.slug) && charJob(char.slug)?.status !== 'running'"
            class="btn"
            style="font-size: 11px; padding: 4px 12px; flex: 1;"
            @click="startTrainingForChar(char)"
            :disabled="trainingStore.loading"
            title="Retrain with latest images"
          >
            Retrain
          </button>
          <button
            class="btn btn-generate"
            style="font-size: 11px; padding: 4px 8px;"
            @click="openBatchGenerate(char.slug)"
            :disabled="generatingSlug === char.slug"
            title="Generate batch of training images"
          >
            {{ generatingSlug === char.slug ? 'Queued' : 'Generate' }}
          </button>
          <button
            v-if="charJob(char.slug)?.status === 'running'"
            class="btn btn-danger"
            style="font-size: 11px; padding: 4px 8px;"
            @click="confirmCancel(charJob(char.slug)!)"
            :disabled="actionLoading === charJob(char.slug)?.job_id"
          >
            Cancel
          </button>
          <button
            v-if="charJob(char.slug) && charJob(char.slug)?.status !== 'running'"
            class="btn"
            style="font-size: 11px; padding: 4px 8px;"
            @click="toggleLog(charJob(char.slug)!.job_id)"
          >
            {{ expandedLog === charJob(char.slug)?.job_id ? 'Hide' : 'Log' }}
          </button>
          <button
            v-if="charLora(char.slug)"
            class="btn btn-danger"
            style="font-size: 11px; padding: 4px 8px;"
            @click="confirmDeleteLora(charLora(char.slug)!)"
            :disabled="actionLoading === charLora(char.slug)?.slug"
          >
            &times;
          </button>
        </div>

        <!-- Batch generate inline -->
        <div v-if="batchGenSlug === char.slug" class="batch-gen-panel">
          <div style="display: flex; align-items: center; gap: 8px;">
            <label style="font-size: 11px; color: var(--text-muted); white-space: nowrap;">Count:</label>
            <input
              v-model.number="batchGenCount"
              type="number"
              min="1"
              max="50"
              style="width: 60px; padding: 3px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
            />
            <button
              class="btn btn-success"
              style="font-size: 11px; padding: 3px 12px;"
              @click="submitBatchGenerate(char.slug)"
              :disabled="generatingSlug === char.slug || batchGenCount < 1"
            >
              Go
            </button>
            <button
              class="btn"
              style="font-size: 11px; padding: 3px 8px;"
              @click="batchGenSlug = null"
            >
              Cancel
            </button>
          </div>
          <div v-if="batchGenMessage" style="font-size: 11px; color: var(--status-success); margin-top: 4px;">
            {{ batchGenMessage }}
          </div>
        </div>

        <!-- Failed error -->
        <div v-if="charJob(char.slug)?.status === 'failed'" style="margin-top: 8px; padding: 6px 8px; background: rgba(160,80,80,0.08); border: 1px solid rgba(160,80,80,0.2); border-radius: 4px; font-size: 11px; color: var(--status-error);">
          {{ charJob(char.slug)?.error || 'Training failed — check log.' }}
        </div>

        <!-- Log viewer -->
        <div v-if="expandedLog === charJob(char.slug)?.job_id" style="margin-top: 8px;">
          <div v-if="logLoading" style="text-align: center; padding: 8px;"><div class="spinner" style="width: 16px; height: 16px; margin: 0 auto;"></div></div>
          <pre v-else-if="logLines.length > 0" class="log-viewer">{{ logLines.join('\n') }}</pre>
          <p v-else style="font-size: 11px; color: var(--text-muted);">No log output yet.</p>
        </div>
      </div>
    </div>

    <!-- Confirm dialog -->
    <ConfirmDialog
      :dialog="confirmDialogData"
      @confirm="handleConfirmAction"
      @cancel="confirmDialogData = null; pendingAction = null"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useTrainingStore } from '@/stores/training'
import { useCharactersStore } from '@/stores/characters'
import type { TrainingJob, LoraFile, Character } from '@/types'
import ConfirmDialog from './training/ConfirmDialog.vue'
import type { ConfirmDialogData } from './training/ConfirmDialog.vue'
import ProductionReadiness from './training/ProductionReadiness.vue'

const trainingStore = useTrainingStore()
const charactersStore = useCharactersStore()
const expandedLog = ref<string | null>(null)
const logLines = ref<string[]>([])
const logLoading = ref(false)
const actionLoading = ref<string | null>(null)
const activeFilter = ref<string>('all')
const confirmDialogData = ref<ConfirmDialogData | null>(null)
const pendingAction = ref<((deleteLora: boolean) => Promise<void>) | null>(null)
const selectedProject = ref<string>('')
const batchGenSlug = ref<string | null>(null)
const batchGenCount = ref(10)
const batchGenMessage = ref<string | null>(null)
const generatingSlug = ref<string | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

const projectNames = computed(() => {
  const names = new Set<string>()
  charactersStore.characters.forEach(c => { if (c.project_name) names.add(c.project_name) })
  return [...names].sort()
})

onMounted(async () => {
  trainingStore.fetchTrainingJobs()
  trainingStore.fetchLoras()
  // Set default project after characters load
  if (!selectedProject.value && projectNames.value.length > 0) {
    selectedProject.value = projectNames.value[0]
  }
  // Watch for characters loading to set default
  const stop = watch(projectNames, (names) => {
    if (!selectedProject.value && names.length > 0) {
      selectedProject.value = names[0]
      stop()
    }
  })
  pollTimer = setInterval(() => {
    trainingStore.fetchTrainingJobs()
    trainingStore.fetchLoras()
    if (expandedLog.value) fetchLog(expandedLog.value)
  }, 5000)
})

onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

// Helpers
function charStats(slug: string) {
  const s = charactersStore.getCharacterStats(slug)
  return { ...s, canTrain: s.approved >= 10 }
}

function charLora(slug: string): LoraFile | undefined {
  return trainingStore.loras.find(l => l.slug === slug)
}

function charJob(slug: string): TrainingJob | undefined {
  // Find the most recent job for this character
  const charSlug = slug
  const jobs = trainingStore.jobs
    .filter(j => (j.character_slug || j.character_name) === charSlug)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  return jobs[0]
}

function cardClass(char: Character) {
  const job = charJob(char.slug)
  if (job?.status === 'running') return 'card-running'
  if (job?.status === 'failed') return 'card-failed'
  if (charLora(char.slug)) return 'card-trained'
  if (charStats(char.slug).canTrain) return 'card-ready'
  return 'card-insufficient'
}

// Computed
const totalApproved = computed(() =>
  charactersStore.characters.reduce((sum, c) => sum + charStats(c.slug).approved, 0)
)

const runningCount = computed(() => trainingStore.jobs.filter(j => j.status === 'running' || j.status === 'queued').length)
const failedCount = computed(() => trainingStore.jobs.filter(j => j.status === 'failed').length)
const readyToTrainCount = computed(() =>
  charactersStore.characters.filter(c =>
    charStats(c.slug).canTrain && !charLora(c.slug) && charJob(c.slug)?.status !== 'running'
  ).length
)

const filters = computed(() => [
  { key: 'all', label: 'All', count: charactersStore.characters.length },
  { key: 'trained', label: 'Trained', count: charactersStore.characters.filter(c => charLora(c.slug)).length },
  { key: 'running', label: 'Training', count: charactersStore.characters.filter(c => charJob(c.slug)?.status === 'running').length },
  { key: 'ready', label: 'Ready', count: readyToTrainCount.value },
  { key: 'failed', label: 'Failed', count: charactersStore.characters.filter(c => charJob(c.slug)?.status === 'failed').length },
  { key: 'insufficient', label: 'Needs Images', count: charactersStore.characters.filter(c => !charStats(c.slug).canTrain).length },
])

const filteredCharacters = computed(() => {
  let chars = [...charactersStore.characters]
  switch (activeFilter.value) {
    case 'trained': chars = chars.filter(c => charLora(c.slug)); break
    case 'running': chars = chars.filter(c => charJob(c.slug)?.status === 'running'); break
    case 'ready': chars = chars.filter(c => charStats(c.slug).canTrain && !charLora(c.slug) && charJob(c.slug)?.status !== 'running'); break
    case 'failed': chars = chars.filter(c => charJob(c.slug)?.status === 'failed'); break
    case 'insufficient': chars = chars.filter(c => !charStats(c.slug).canTrain); break
  }
  // Sort: running first, then trained, then ready, then rest
  return chars.sort((a, b) => {
    const order = (c: Character) => {
      if (charJob(c.slug)?.status === 'running') return 0
      if (charLora(c.slug)) return 1
      if (charStats(c.slug).canTrain) return 2
      return 3
    }
    return order(a) - order(b)
  })
})

// Actions
async function startTrainingForChar(char: Character) {
  try {
    await trainingStore.startTraining({ character_name: char.slug || char.name })
  } catch (error) {
    console.error('Failed to start training:', error)
  }
}

async function trainAllReady() {
  const ready = charactersStore.characters.filter(c =>
    charStats(c.slug).canTrain && !charLora(c.slug) && charJob(c.slug)?.status !== 'running'
  )
  for (const char of ready) {
    try {
      await trainingStore.startTraining({ character_name: char.slug || char.name })
    } catch (error) {
      console.error(`Failed to start training for ${char.name}:`, error)
    }
  }
}

function openBatchGenerate(slug: string) {
  if (batchGenSlug.value === slug) {
    batchGenSlug.value = null
    return
  }
  batchGenSlug.value = slug
  batchGenCount.value = 10
  batchGenMessage.value = null
}

async function submitBatchGenerate(slug: string) {
  if (batchGenCount.value < 1) return
  generatingSlug.value = slug
  batchGenMessage.value = null
  try {
    const resp = await fetch(`/api/training/regenerate/${encodeURIComponent(slug)}?count=${batchGenCount.value}`, { method: 'POST' })
    if (resp.ok) {
      const data = await resp.json()
      batchGenMessage.value = data.message || `Queued ${batchGenCount.value} images`
    } else {
      const err = await resp.text()
      batchGenMessage.value = `Error: ${err}`
    }
  } catch (e) {
    batchGenMessage.value = `Failed: ${e}`
  } finally {
    setTimeout(() => { generatingSlug.value = null }, 3000)
  }
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function elapsed(iso?: string): string {
  if (!iso) return ''
  const sec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ${sec % 60}s`
  return `${Math.floor(min / 60)}h ${min % 60}m`
}

async function fetchLog(jobId: string) {
  logLoading.value = true
  try {
    const resp = await fetch(`/api/training/jobs/${encodeURIComponent(jobId)}/log?tail=60`)
    if (resp.ok) { const data = await resp.json(); logLines.value = data.lines || [] }
    else logLines.value = ['(Log not available)']
  } catch { logLines.value = ['(Failed to fetch log)'] }
  finally { logLoading.value = false }
}

async function toggleLog(jobId: string) {
  if (expandedLog.value === jobId) { expandedLog.value = null; logLines.value = [] }
  else { expandedLog.value = jobId; await fetchLog(jobId) }
}

function refresh() {
  trainingStore.fetchTrainingJobs()
  trainingStore.fetchLoras()
  if (expandedLog.value) fetchLog(expandedLog.value)
}

function handleConfirmAction(deleteLora: boolean) {
  if (pendingAction.value) pendingAction.value(deleteLora)
  confirmDialogData.value = null
  pendingAction.value = null
}

function confirmCancel(job: TrainingJob) {
  confirmDialogData.value = { title: 'Cancel Training', message: `Cancel training for "${job.character_name}"?`, confirmLabel: 'Cancel Job' }
  pendingAction.value = async () => { actionLoading.value = job.job_id; try { await trainingStore.cancelJob(job.job_id) } finally { actionLoading.value = null } }
}

function confirmDeleteLora(lora: LoraFile) {
  confirmDialogData.value = { title: 'Delete LoRA', message: `Delete ${lora.filename} (${lora.size_mb} MB)?`, confirmLabel: 'Delete' }
  pendingAction.value = async () => { actionLoading.value = lora.slug; try { await trainingStore.deleteLora(lora.slug) } finally { actionLoading.value = null } }
}

async function reconcile() { actionLoading.value = 'reconcile'; try { await trainingStore.reconcileJobs() } finally { actionLoading.value = null } }
</script>

<style scoped>
.stats-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}
.stat-card {
  flex: 1;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  padding: 12px 16px;
  text-align: center;
}
.stat-value {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
}
.stat-label {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-top: 2px;
}

/* Filter Pills */
.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  border: 1px solid var(--border-primary);
  border-radius: 20px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  font-family: var(--font-primary);
  transition: all 150ms ease;
}
.pill:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.pill.active {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
  color: #fff;
}
.pill-count {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 10px;
  background: rgba(255,255,255,0.2);
}
.pill:not(.active) .pill-count {
  background: var(--bg-primary);
}

/* LoRA Grid */
.lora-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}
.lora-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  padding: 14px 16px;
  border-left: 3px solid transparent;
  transition: all 150ms ease;
}
.lora-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.card-trained { border-left-color: var(--status-success); }
.card-running { border-left-color: var(--status-warning); background: rgba(200,160,60,0.03); }
.card-ready { border-left-color: var(--accent-primary); }
.card-failed { border-left-color: var(--status-error); background: rgba(160,80,80,0.03); }
.card-insufficient { opacity: 0.6; }

.lora-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}

/* Status dots */
.status-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-trained { background: var(--status-success); box-shadow: 0 0 4px var(--status-success); }
.status-ready { background: var(--accent-primary); }
.status-insufficient { background: var(--text-muted); opacity: 0.4; }

/* Config Pills */
.config-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
.config-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
  background: rgba(120,120,120,0.1);
  color: var(--text-secondary);
  font-family: 'SF Mono', 'Fira Code', monospace;
}
.config-pill.arch {
  background: rgba(100,140,200,0.15);
  color: var(--accent-primary);
  text-transform: uppercase;
}

/* LoRA Summary */
.lora-summary {
  margin-top: 10px;
  padding: 8px 10px;
  background: rgba(80,160,80,0.05);
  border: 1px solid rgba(80,160,80,0.15);
  border-radius: 6px;
}
.summary-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 0;
  font-size: 11px;
}
.summary-label {
  color: var(--text-muted);
}
.summary-value {
  color: var(--text-primary);
  font-weight: 500;
}
.summary-value.mono {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 10px;
}

/* Log viewer */
.log-viewer {
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 10px;
  line-height: 1.5;
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--text-secondary);
  font-family: 'SF Mono', 'Fira Code', monospace;
}

/* Buttons */
.btn-danger {
  color: var(--status-error);
  border-color: var(--status-error);
}
.btn-danger:hover {
  background: rgba(160,80,80,0.1);
}
.btn-success {
  color: var(--status-success);
  border-color: var(--status-success);
}
.btn-success:hover {
  background: rgba(80,160,80,0.1);
}
.btn-generate {
  color: var(--accent-primary);
  border-color: var(--accent-primary);
}
.btn-generate:hover {
  background: rgba(100,140,200,0.1);
}

/* Batch generate panel */
.batch-gen-panel {
  margin-top: 8px;
  padding: 8px 10px;
  background: rgba(100,140,200,0.06);
  border: 1px solid rgba(100,140,200,0.2);
  border-radius: 6px;
}

/* Project selector */
.project-select {
  padding: 5px 10px;
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 12px;
  font-family: var(--font-primary);
  cursor: pointer;
}
.project-select:focus {
  outline: none;
  border-color: var(--accent-primary);
}

@media (max-width: 768px) {
  .stats-bar {
    flex-wrap: wrap;
  }
  .stat-card {
    flex: 1 1 calc(33% - 8px);
    min-width: 80px;
  }
  .lora-grid {
    grid-template-columns: 1fr;
  }
}
</style>
