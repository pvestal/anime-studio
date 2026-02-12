<template>
  <div class="generation-progress">
    <!-- Header -->
    <div class="progress-header">
      <h3>{{ title }}</h3>
      <div class="progress-actions">
        <button
          v-if="canCancel"
          @click="cancelGeneration"
          class="action-button cancel"
        >
          Cancel
        </button>
        <button
          v-if="status === 'failed' && canRetry"
          @click="retryGeneration"
          class="action-button retry"
        >
          Retry
        </button>
      </div>
    </div>

    <!-- Main Progress Display -->
    <div class="progress-main">
      <!-- Preview Image -->
      <div class="preview-container">
        <div v-if="previewImage" class="preview-image">
          <img :src="previewImage" :alt="currentPhase" />
          <div class="preview-overlay" v-if="status === 'processing'">
            <div class="spinner"></div>
          </div>
        </div>
        <div v-else class="preview-placeholder">
          <div class="placeholder-content">
            <component :is="phaseIcon" :size="48" />
            <p>{{ placeholderText }}</p>
          </div>
        </div>
      </div>

      <!-- Progress Information -->
      <div class="progress-info">
        <!-- Phase Indicator -->
        <div class="phase-indicator">
          <span class="phase-label">Phase:</span>
          <span class="phase-name">{{ phaseName }}</span>
        </div>

        <!-- Progress Bar -->
        <div class="progress-bar-container">
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: progress + '%' }"
              :class="progressClass"
            ></div>
            <div class="progress-markers">
              <div
                v-for="marker in progressMarkers"
                :key="marker.phase"
                :style="{ left: marker.position + '%' }"
                :title="marker.label"
                class="progress-marker"
                :class="{ active: progress >= marker.position }"
              ></div>
            </div>
          </div>
          <span class="progress-percentage">{{ Math.round(progress) }}%</span>
        </div>

        <!-- Contextual Message -->
        <div class="progress-message">
          <transition name="fade" mode="out-in">
            <p :key="message">{{ message }}</p>
          </transition>
        </div>

        <!-- Time Information -->
        <div class="time-info">
          <div class="time-item">
            <span class="time-label">Elapsed:</span>
            <span class="time-value">{{ formatTime(elapsedTime) }}</span>
          </div>
          <div v-if="estimatedTimeRemaining" class="time-item">
            <span class="time-label">Remaining:</span>
            <span class="time-value">{{ formatTime(estimatedTimeRemaining) }}</span>
          </div>
        </div>

        <!-- Step Counter -->
        <div v-if="currentStep && totalSteps" class="step-counter">
          Step {{ currentStep }} of {{ totalSteps }}
        </div>
      </div>
    </div>

    <!-- Error Recovery Panel -->
    <transition name="slide">
      <div v-if="errorInfo" class="error-panel">
        <div class="error-header">
          <AlertCircle :size="20" />
          <span>Generation Issue Detected</span>
        </div>

        <div class="error-content">
          <p class="error-message">{{ errorInfo.user_message }}</p>

          <div v-if="errorInfo.suggestions" class="error-suggestions">
            <h4>Suggested Solutions:</h4>
            <ul>
              <li v-for="(suggestion, index) in errorInfo.suggestions" :key="index">
                {{ suggestion }}
              </li>
            </ul>
          </div>

          <div v-if="errorInfo.auto_fix_available" class="auto-fix-panel">
            <h4>Automatic Fix Available</h4>
            <p>We can automatically adjust the following settings:</p>
            <div class="fix-params">
              <div
                v-for="(value, key) in errorInfo.auto_fix_params"
                :key="key"
                class="fix-param"
              >
                <span class="param-key">{{ formatParamKey(key) }}:</span>
                <span class="param-value">{{ value }}</span>
              </div>
            </div>
            <button @click="applyAutoFix" class="auto-fix-button">
              Apply Fix & Retry
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Batch Progress (if multiple generations) -->
    <div v-if="batchJobs && batchJobs.length > 1" class="batch-progress">
      <h4>Batch Progress</h4>
      <div class="batch-items">
        <div
          v-for="job in batchJobs"
          :key="job.id"
          class="batch-item"
          :class="getBatchItemClass(job)"
        >
          <div class="batch-item-icon">
            <CheckCircle v-if="job.status === 'completed'" :size="16" />
            <Loader v-else-if="job.status === 'processing'" :size="16" class="spinning" />
            <XCircle v-else-if="job.status === 'failed'" :size="16" />
            <Clock v-else :size="16" />
          </div>
          <span class="batch-item-label">{{ job.label || `Job ${job.index}` }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useAnimeStore } from '@/stores/anime'
import {
  Loader,
  CheckCircle,
  XCircle,
  AlertCircle,
  Clock,
  Zap,
  Cpu,
  Sparkles,
  Image as ImageIcon,
  Wand2
} from 'lucide-vue-next'

const props = defineProps({
  jobId: {
    type: String,
    required: true
  },
  title: {
    type: String,
    default: 'Generating Anime Art'
  },
  onComplete: {
    type: Function,
    default: null
  },
  onError: {
    type: Function,
    default: null
  }
})

const animeStore = useAnimeStore()

// WebSocket connection
let ws = null
let reconnectTimer = null
let startTime = null
let elapsedTimer = null

// Reactive state
const status = ref('connecting')
const progress = ref(0)
const currentPhase = ref('INITIALIZING')
const phaseName = ref('Initializing')
const message = ref('Connecting to generation service...')
const previewImage = ref(null)
const currentStep = ref(0)
const totalSteps = ref(20)
const elapsedTime = ref(0)
const estimatedTimeRemaining = ref(null)
const errorInfo = ref(null)
const batchJobs = ref(null)

// Phase icons mapping
const phaseIcons = {
  INITIALIZING: Wand2,
  LOADING_MODELS: Cpu,
  PROCESSING_PROMPT: ImageIcon,
  GENERATING_LATENTS: Sparkles,
  REFINING_DETAILS: Sparkles,
  APPLYING_STYLE: Sparkles,
  FINALIZING: CheckCircle,
  SAVING: CheckCircle,
  COMPLETE: CheckCircle
}

// Progress markers for visual reference
const progressMarkers = [
  { phase: 'loading', position: 10, label: 'Loading' },
  { phase: 'processing', position: 25, label: 'Processing' },
  { phase: 'generating', position: 50, label: 'Generating' },
  { phase: 'refining', position: 75, label: 'Refining' },
  { phase: 'finalizing', position: 90, label: 'Finalizing' }
]

const phaseIcon = computed(() => phaseIcons[currentPhase.value] || Loader)

const placeholderText = computed(() => {
  if (status.value === 'connecting') return 'Connecting...'
  if (status.value === 'failed') return 'Generation failed'
  if (status.value === 'completed') return 'Generation complete!'
  return 'Generating your artwork...'
})

const progressClass = computed(() => {
  if (status.value === 'failed') return 'progress-error'
  if (status.value === 'completed') return 'progress-success'
  if (progress.value < 30) return 'progress-early'
  if (progress.value < 70) return 'progress-mid'
  return 'progress-late'
})

const canCancel = computed(() =>
  ['processing', 'queued'].includes(status.value)
)

const canRetry = computed(() =>
  status.value === 'failed' && !errorInfo.value?.auto_fix_available
)

function connectWebSocket() {
  const wsUrl = `ws://localhost:8329/ws/generate/${props.jobId}`

  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    console.log('WebSocket connected for job:', props.jobId)
    status.value = 'connected'
    message.value = 'Connected. Waiting for generation to start...'
  }

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    handleWebSocketMessage(data)
  }

  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
    status.value = 'error'
    message.value = 'Connection error. Retrying...'
    scheduleReconnect()
  }

  ws.onclose = () => {
    console.log('WebSocket closed')
    if (status.value !== 'completed' && status.value !== 'failed') {
      scheduleReconnect()
    }
  }
}

function handleWebSocketMessage(data) {
  switch(data.type) {
    case 'status':
      updateFromStatus(data.data)
      break

    case 'progress':
      updateProgress(data)
      break

    case 'error':
      handleError(data)
      break

    case 'recovery_success':
      handleRecoverySuccess(data)
      break

    case 'complete':
      handleComplete(data)
      break

    default:
      console.log('Unknown message type:', data.type)
  }
}

function updateFromStatus(statusData) {
  status.value = statusData.status
  progress.value = statusData.progress || 0
  message.value = statusData.message || ''

  if (statusData.phase) {
    currentPhase.value = statusData.phase
    phaseName.value = getPhaseDisplayName(statusData.phase)
  }
}

function updateProgress(data) {
  status.value = 'processing'
  progress.value = data.percentage || 0
  currentPhase.value = data.phase || currentPhase.value
  phaseName.value = data.phase_message || phaseName.value
  message.value = data.message || message.value
  currentStep.value = data.current_step || currentStep.value
  totalSteps.value = data.total_steps || totalSteps.value

  if (data.preview_image) {
    previewImage.value = data.preview_image
  }

  if (data.estimated_time_remaining) {
    estimatedTimeRemaining.value = data.estimated_time_remaining
  }
}

function handleError(data) {
  status.value = 'failed'
  errorInfo.value = data
  message.value = data.user_message || 'Generation failed'

  if (props.onError) {
    props.onError(data)
  }
}

function handleRecoverySuccess(data) {
  status.value = 'recovering'
  message.value = data.message || 'Applying automatic fixes...'
  errorInfo.value = null

  // Reset progress for retry
  progress.value = 0
  currentStep.value = 0
}

function handleComplete(data) {
  status.value = 'completed'
  progress.value = 100
  message.value = 'Generation complete!'

  if (data.output_paths && data.output_paths.length > 0) {
    // Update store with results
    animeStore.setGenerationResults(props.jobId, data.output_paths)
  }

  if (props.onComplete) {
    props.onComplete(data)
  }
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer)

  reconnectTimer = setTimeout(() => {
    console.log('Attempting to reconnect WebSocket...')
    connectWebSocket()
  }, 2000)
}

function cancelGeneration() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: 'cancel' }))
  }

  animeStore.cancelGeneration(props.jobId)
  status.value = 'cancelled'
  message.value = 'Generation cancelled'
}

function retryGeneration() {
  errorInfo.value = null
  animeStore.retryGeneration(props.jobId)
}

function applyAutoFix() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      action: 'apply_auto_fix',
      params: errorInfo.value.auto_fix_params
    }))
  }

  status.value = 'recovering'
  message.value = 'Applying fixes and retrying...'
}

function formatTime(seconds) {
  if (!seconds || seconds < 0) return '--'

  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)

  if (mins > 0) {
    return `${mins}m ${secs}s`
  }
  return `${secs}s`
}

function formatParamKey(key) {
  return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

function getPhaseDisplayName(phase) {
  const names = {
    INITIALIZING: 'Preparing Workspace',
    LOADING_MODELS: 'Loading AI Models',
    PROCESSING_PROMPT: 'Understanding Request',
    GENERATING_LATENTS: 'Creating Composition',
    REFINING_DETAILS: 'Refining Details',
    APPLYING_STYLE: 'Applying Art Style',
    FINALIZING: 'Finalizing Output',
    SAVING: 'Saving Creation',
    COMPLETE: 'Complete!'
  }
  return names[phase] || phase
}

function getBatchItemClass(job) {
  return {
    'batch-item-completed': job.status === 'completed',
    'batch-item-processing': job.status === 'processing',
    'batch-item-failed': job.status === 'failed',
    'batch-item-queued': job.status === 'queued'
  }
}

function updateElapsedTime() {
  if (startTime && status.value === 'processing') {
    elapsedTime.value = Math.floor((Date.now() - startTime) / 1000)
  }
}

onMounted(() => {
  connectWebSocket()
  startTime = Date.now()

  // Update elapsed time every second
  elapsedTimer = setInterval(updateElapsedTime, 1000)
})

onUnmounted(() => {
  if (ws) {
    ws.close()
  }

  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
  }

  if (elapsedTimer) {
    clearInterval(elapsedTimer)
  }
})
</script>

<style scoped>
.generation-progress {
  background: #1a1a1a;
  border-radius: 12px;
  padding: 20px;
  color: #fff;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.progress-header h3 {
  margin: 0;
  font-size: 1.2em;
}

.progress-actions {
  display: flex;
  gap: 10px;
}

.action-button {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  font-size: 0.9em;
  cursor: pointer;
  transition: all 0.3s ease;
}

.action-button.cancel {
  background: #ef4444;
  color: white;
}

.action-button.cancel:hover {
  background: #dc2626;
}

.action-button.retry {
  background: #3b82f6;
  color: white;
}

.action-button.retry:hover {
  background: #2563eb;
}

.progress-main {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 20px;
  margin-bottom: 20px;
}

@media (max-width: 768px) {
  .progress-main {
    grid-template-columns: 1fr;
  }
}

.preview-container {
  aspect-ratio: 1;
  background: #2a2a2a;
  border-radius: 8px;
  overflow: hidden;
  position: relative;
}

.preview-image {
  width: 100%;
  height: 100%;
  position: relative;
}

.preview-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.preview-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.placeholder-content {
  text-align: center;
  opacity: 0.7;
}

.progress-info {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 15px;
}

.phase-indicator {
  display: flex;
  gap: 10px;
  align-items: center;
}

.phase-label {
  font-size: 0.9em;
  opacity: 0.7;
}

.phase-name {
  font-weight: bold;
  color: #667eea;
}

.progress-bar-container {
  display: flex;
  align-items: center;
  gap: 15px;
}

.progress-bar {
  flex: 1;
  height: 24px;
  background: #2a2a2a;
  border-radius: 12px;
  overflow: hidden;
  position: relative;
}

.progress-fill {
  height: 100%;
  transition: width 0.3s ease;
  border-radius: 12px;
}

.progress-early { background: linear-gradient(90deg, #667eea, #764ba2); }
.progress-mid { background: linear-gradient(90deg, #f59e0b, #ef4444); }
.progress-late { background: linear-gradient(90deg, #10b981, #3b82f6); }
.progress-success { background: #4ade80; }
.progress-error { background: #ef4444; }

.progress-markers {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
}

.progress-marker {
  position: absolute;
  top: 50%;
  width: 2px;
  height: 60%;
  background: rgba(255, 255, 255, 0.2);
  transform: translateY(-50%);
}

.progress-marker.active {
  background: rgba(255, 255, 255, 0.4);
}

.progress-percentage {
  font-weight: bold;
  min-width: 45px;
}

.progress-message {
  min-height: 24px;
}

.progress-message p {
  margin: 0;
  font-size: 0.95em;
  opacity: 0.9;
}

.time-info {
  display: flex;
  gap: 30px;
}

.time-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.time-label {
  font-size: 0.85em;
  opacity: 0.7;
}

.time-value {
  font-weight: bold;
}

.step-counter {
  font-size: 0.9em;
  opacity: 0.8;
}

.error-panel {
  background: #2a2a2a;
  border: 1px solid #ef4444;
  border-radius: 8px;
  padding: 15px;
  margin-top: 20px;
}

.error-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 15px;
  color: #ef4444;
  font-weight: bold;
}

.error-content {
  font-size: 0.95em;
}

.error-message {
  margin: 0 0 15px 0;
}

.error-suggestions {
  margin-bottom: 15px;
}

.error-suggestions h4 {
  margin: 0 0 10px 0;
  font-size: 1em;
}

.error-suggestions ul {
  margin: 0;
  padding-left: 20px;
}

.error-suggestions li {
  margin-bottom: 5px;
  opacity: 0.9;
}

.auto-fix-panel {
  background: #1a1a1a;
  border-radius: 6px;
  padding: 15px;
  margin-top: 15px;
}

.auto-fix-panel h4 {
  margin: 0 0 10px 0;
  font-size: 1em;
  color: #4ade80;
}

.fix-params {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 15px 0;
}

.fix-param {
  display: flex;
  gap: 5px;
  padding: 5px 10px;
  background: #2a2a2a;
  border-radius: 4px;
  font-size: 0.85em;
}

.param-key {
  opacity: 0.7;
}

.param-value {
  font-weight: bold;
  color: #4ade80;
}

.auto-fix-button {
  width: 100%;
  padding: 10px;
  background: #4ade80;
  border: none;
  border-radius: 6px;
  color: #1a1a1a;
  font-weight: bold;
  cursor: pointer;
  transition: background 0.3s ease;
}

.auto-fix-button:hover {
  background: #22c55e;
}

.batch-progress {
  background: #2a2a2a;
  border-radius: 8px;
  padding: 15px;
}

.batch-progress h4 {
  margin: 0 0 15px 0;
  font-size: 1em;
}

.batch-items {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
}

.batch-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: #1a1a1a;
  border-radius: 6px;
  font-size: 0.85em;
}

.batch-item-completed { border: 1px solid #4ade80; }
.batch-item-processing { border: 1px solid #3b82f6; }
.batch-item-failed { border: 1px solid #ef4444; }
.batch-item-queued { border: 1px solid #6b7280; }

.batch-item-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

.spinning {
  animation: spin 1s linear infinite;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateY(-10px);
  opacity: 0;
}
</style>