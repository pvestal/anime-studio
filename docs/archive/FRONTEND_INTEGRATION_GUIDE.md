# Frontend Integration Guide for WebSocket Progress Tracking

## Vue.js Integration

### 1. WebSocket Composable (Vue 3 Composition API)

Create a reusable composable for WebSocket connections:

```javascript
// composables/useAnimeProgress.js
import { ref, computed, onUnmounted, watch } from 'vue'

export function useAnimeProgress(jobId, options = {}) {
  // Reactive state
  const isConnected = ref(false)
  const progress = ref(0)
  const status = ref('pending')
  const message = ref('')
  const error = ref(null)
  const outputPath = ref(null)
  const estimatedRemaining = ref(0)

  // WebSocket instance
  let websocket = null
  let reconnectAttempts = 0
  const maxReconnectAttempts = options.maxReconnectAttempts || 5
  const serverUrl = options.serverUrl || 'ws://192.168.50.135:8328'

  // Computed properties
  const isProcessing = computed(() => status.value === 'processing')
  const isCompleted = computed(() => status.value === 'completed')
  const isFailed = computed(() => status.value === 'failed')
  const progressPercent = computed(() => `${progress.value}%`)

  // Connect to WebSocket
  const connect = () => {
    if (!jobId.value) return

    const wsUrl = `${serverUrl}/ws/${jobId.value}`
    websocket = new WebSocket(wsUrl)

    websocket.onopen = () => {
      isConnected.value = true
      error.value = null
      reconnectAttempts = 0
      console.log(`Connected to job ${jobId.value}`)
    }

    websocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleWebSocketMessage(data)
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
        error.value = 'Invalid message format'
      }
    }

    websocket.onclose = (event) => {
      isConnected.value = false

      if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
        // Auto-reconnect on unexpected close
        reconnectAttempts++
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000)

        setTimeout(() => {
          console.log(`Reconnecting... attempt ${reconnectAttempts}`)
          connect()
        }, delay)
      }
    }

    websocket.onerror = (err) => {
      error.value = 'WebSocket connection error'
      console.error('WebSocket error:', err)
    }
  }

  // Handle incoming WebSocket messages
  const handleWebSocketMessage = (data) => {
    if (data.type === 'progress') {
      progress.value = data.progress
      status.value = data.status
      message.value = data.message || ''
      estimatedRemaining.value = data.estimated_remaining || 0

      if (data.output_path) {
        outputPath.value = data.output_path
      }

      if (data.error) {
        error.value = data.error
      }
    } else if (data.type === 'error') {
      error.value = data.error
      status.value = 'failed'
    }
  }

  // Disconnect WebSocket
  const disconnect = () => {
    if (websocket) {
      websocket.close(1000, 'User disconnect')
      websocket = null
    }
  }

  // Watch for jobId changes
  watch(jobId, (newJobId, oldJobId) => {
    if (newJobId && newJobId !== oldJobId) {
      disconnect()
      connect()
    }
  })

  // Cleanup on unmount
  onUnmounted(() => {
    disconnect()
  })

  return {
    // State
    isConnected,
    progress,
    status,
    message,
    error,
    outputPath,
    estimatedRemaining,

    // Computed
    isProcessing,
    isCompleted,
    isFailed,
    progressPercent,

    // Methods
    connect,
    disconnect
  }
}
```

### 2. Progress Component

Create a reusable progress component:

```vue
<!-- components/AnimeProgressTracker.vue -->
<template>
  <div class="anime-progress-tracker">
    <!-- Connection Status -->
    <div class="connection-status" :class="connectionStatusClass">
      <div class="status-indicator"></div>
      <span>{{ connectionStatusText }}</span>
    </div>

    <!-- Progress Bar -->
    <div class="progress-container" v-if="jobId">
      <div class="progress-header">
        <h3>{{ jobName || `Job ${jobId}` }}</h3>
        <div class="progress-meta">
          <span class="status-badge" :class="status">{{ status }}</span>
          <span class="eta" v-if="estimatedRemaining > 0">
            ETA: {{ formatTime(estimatedRemaining) }}
          </span>
        </div>
      </div>

      <!-- Progress Bar -->
      <div class="progress-bar">
        <div
          class="progress-fill"
          :style="{ width: progressPercent }"
          :class="{ 'pulsing': isProcessing }"
        >
          <span class="progress-text">{{ progressPercent }}</span>
        </div>
      </div>

      <!-- Status Message -->
      <div class="status-message" v-if="message">
        {{ message }}
      </div>

      <!-- Error Display -->
      <div class="error-message" v-if="error">
        <i class="error-icon">⚠️</i>
        {{ error }}
      </div>

      <!-- Output Preview -->
      <div class="output-preview" v-if="isCompleted && outputPath">
        <h4>Generated Output:</h4>
        <div class="output-link">
          <a :href="outputPath" target="_blank">
            View Generated File
          </a>
        </div>
      </div>
    </div>

    <!-- Controls -->
    <div class="controls" v-if="showControls">
      <button
        @click="connect"
        :disabled="isConnected || !jobId"
        class="btn btn-primary"
      >
        Connect
      </button>
      <button
        @click="disconnect"
        :disabled="!isConnected"
        class="btn btn-secondary"
      >
        Disconnect
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAnimeProgress } from '@/composables/useAnimeProgress'

const props = defineProps({
  jobId: {
    type: String,
    required: true
  },
  jobName: {
    type: String,
    default: ''
  },
  autoConnect: {
    type: Boolean,
    default: true
  },
  showControls: {
    type: Boolean,
    default: false
  },
  serverUrl: {
    type: String,
    default: 'ws://192.168.50.135:8328'
  }
})

const emit = defineEmits(['progress', 'completed', 'error'])

// Use the WebSocket composable
const {
  isConnected,
  progress,
  status,
  message,
  error,
  outputPath,
  estimatedRemaining,
  isProcessing,
  isCompleted,
  isFailed,
  progressPercent,
  connect,
  disconnect
} = useAnimeProgress(computed(() => props.jobId), {
  serverUrl: props.serverUrl
})

// Computed properties for UI
const connectionStatusClass = computed(() => ({
  'connected': isConnected.value,
  'disconnected': !isConnected.value,
  'error': error.value
}))

const connectionStatusText = computed(() => {
  if (error.value) return 'Connection Error'
  return isConnected.value ? 'Connected' : 'Disconnected'
})

// Utility functions
const formatTime = (seconds) => {
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${minutes}m ${remainingSeconds}s`
}

// Auto-connect if enabled
if (props.autoConnect && props.jobId) {
  connect()
}

// Emit events for parent components
watch(progress, (newProgress) => {
  emit('progress', {
    jobId: props.jobId,
    progress: newProgress,
    status: status.value
  })
})

watch(isCompleted, (completed) => {
  if (completed) {
    emit('completed', {
      jobId: props.jobId,
      outputPath: outputPath.value
    })
  }
})

watch(error, (newError) => {
  if (newError) {
    emit('error', {
      jobId: props.jobId,
      error: newError
    })
  }
})
</script>

<style scoped>
.anime-progress-tracker {
  background: #2d3748;
  border-radius: 8px;
  padding: 20px;
  color: white;
  font-family: 'Inter', sans-serif;
}

.connection-status {
  display: flex;
  align-items: center;
  margin-bottom: 15px;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
}

.connection-status.connected {
  background: rgba(72, 187, 120, 0.2);
  color: #68d391;
}

.connection-status.disconnected {
  background: rgba(245, 101, 101, 0.2);
  color: #f56565;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  margin-right: 8px;
}

.progress-container {
  margin-bottom: 20px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.progress-header h3 {
  margin: 0;
  color: #e2e8f0;
  font-size: 18px;
}

.progress-meta {
  display: flex;
  gap: 12px;
  align-items: center;
}

.status-badge {
  padding: 4px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
}

.status-badge.processing {
  background: rgba(66, 153, 225, 0.2);
  color: #4299e1;
}

.status-badge.completed {
  background: rgba(72, 187, 120, 0.2);
  color: #48bb78;
}

.status-badge.failed {
  background: rgba(245, 101, 101, 0.2);
  color: #f56565;
}

.eta {
  font-size: 12px;
  color: #a0aec0;
}

.progress-bar {
  background: #4a5568;
  border-radius: 20px;
  height: 24px;
  overflow: hidden;
  position: relative;
}

.progress-fill {
  background: linear-gradient(90deg, #4299e1, #63b3ed);
  height: 100%;
  border-radius: 20px;
  transition: width 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.progress-fill.pulsing {
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.progress-text {
  font-size: 12px;
  font-weight: bold;
  color: white;
}

.status-message {
  margin-top: 8px;
  font-size: 14px;
  color: #cbd5e0;
}

.error-message {
  margin-top: 12px;
  padding: 12px;
  background: rgba(245, 101, 101, 0.1);
  border: 1px solid rgba(245, 101, 101, 0.3);
  border-radius: 4px;
  color: #f56565;
  display: flex;
  align-items: center;
  gap: 8px;
}

.output-preview {
  margin-top: 16px;
  padding: 16px;
  background: rgba(72, 187, 120, 0.1);
  border: 1px solid rgba(72, 187, 120, 0.3);
  border-radius: 4px;
}

.output-preview h4 {
  margin: 0 0 8px 0;
  color: #48bb78;
  font-size: 16px;
}

.output-link a {
  color: #4299e1;
  text-decoration: none;
  font-weight: 500;
}

.output-link a:hover {
  text-decoration: underline;
}

.controls {
  display: flex;
  gap: 12px;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: #4299e1;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #3182ce;
}

.btn-secondary {
  background: #718096;
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background: #4a5568;
}
</style>
```

### 3. System Monitor Component

```vue
<!-- components/AnimeSystemMonitor.vue -->
<template>
  <div class="system-monitor">
    <div class="monitor-header">
      <h2>System Monitor</h2>
      <div class="connection-indicator" :class="{ connected: isConnected }">
        {{ isConnected ? 'Connected' : 'Disconnected' }}
      </div>
    </div>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">{{ systemStats.totalJobs }}</div>
        <div class="stat-label">Total Jobs</div>
      </div>

      <div class="stat-card">
        <div class="stat-value">{{ systemStats.activeJobs }}</div>
        <div class="stat-label">Active Jobs</div>
      </div>

      <div class="stat-card">
        <div class="stat-value">{{ systemStats.totalConnections }}</div>
        <div class="stat-label">WebSocket Connections</div>
      </div>

      <div class="stat-card">
        <div class="stat-value">{{ systemStats.jobsWithConnections }}</div>
        <div class="stat-label">Jobs with WebSockets</div>
      </div>
    </div>

    <div class="recent-jobs" v-if="recentJobs.length > 0">
      <h3>Recent Jobs</h3>
      <div class="job-list">
        <div
          v-for="job in recentJobs"
          :key="job.id"
          class="job-item"
          :class="job.status"
        >
          <div class="job-info">
            <span class="job-id">{{ job.id }}</span>
            <span class="job-status">{{ job.status }}</span>
          </div>
          <div class="job-progress">
            <div class="progress-mini">
              <div
                class="progress-mini-fill"
                :style="{ width: `${job.progress}%` }"
              ></div>
            </div>
            <span class="progress-text">{{ job.progress }}%</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  serverUrl: {
    type: String,
    default: 'ws://192.168.50.135:8328'
  }
})

// Reactive state
const isConnected = ref(false)
const systemStats = reactive({
  totalJobs: 0,
  activeJobs: 0,
  totalConnections: 0,
  jobsWithConnections: 0
})
const recentJobs = ref([])

let websocket = null

const connect = () => {
  const wsUrl = `${props.serverUrl}/ws/monitor`
  websocket = new WebSocket(wsUrl)

  websocket.onopen = () => {
    isConnected.value = true
    console.log('System monitor connected')
  }

  websocket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)

      if (data.type === 'system_status') {
        // Update system stats
        if (data.jobs) {
          systemStats.totalJobs = data.jobs.total || 0
          systemStats.activeJobs = data.jobs.active || 0
        }

        if (data.websockets) {
          systemStats.totalConnections = data.websockets.total_connections || 0
          systemStats.jobsWithConnections = data.websockets.jobs_with_connections || 0
        }

        // Update recent jobs
        if (data.recent_jobs) {
          recentJobs.value = data.recent_jobs
        }
      }
    } catch (e) {
      console.error('Failed to parse monitor message:', e)
    }
  }

  websocket.onclose = () => {
    isConnected.value = false
    console.log('System monitor disconnected')
  }

  websocket.onerror = (error) => {
    console.error('System monitor error:', error)
  }
}

const disconnect = () => {
  if (websocket) {
    websocket.close()
    websocket = null
  }
}

onMounted(() => {
  connect()
})

onUnmounted(() => {
  disconnect()
})
</script>

<style scoped>
.system-monitor {
  background: #1a202c;
  border-radius: 8px;
  padding: 24px;
  color: white;
}

.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  border-bottom: 1px solid #4a5568;
  padding-bottom: 16px;
}

.monitor-header h2 {
  margin: 0;
  color: #e2e8f0;
}

.connection-indicator {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 500;
  background: rgba(245, 101, 101, 0.2);
  color: #f56565;
}

.connection-indicator.connected {
  background: rgba(72, 187, 120, 0.2);
  color: #48bb78;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
}

.stat-card {
  background: #2d3748;
  padding: 20px;
  border-radius: 8px;
  text-align: center;
  border: 1px solid #4a5568;
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
  color: #4299e1;
  margin-bottom: 8px;
}

.stat-label {
  font-size: 14px;
  color: #a0aec0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.recent-jobs h3 {
  margin-bottom: 16px;
  color: #e2e8f0;
}

.job-list {
  space-y: 8px;
}

.job-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: #2d3748;
  border-radius: 6px;
  border-left: 4px solid #4a5568;
}

.job-item.processing {
  border-left-color: #4299e1;
}

.job-item.completed {
  border-left-color: #48bb78;
}

.job-item.failed {
  border-left-color: #f56565;
}

.job-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.job-id {
  font-weight: 500;
  color: #e2e8f0;
}

.job-status {
  font-size: 12px;
  color: #a0aec0;
  text-transform: uppercase;
}

.job-progress {
  display: flex;
  align-items: center;
  gap: 12px;
}

.progress-mini {
  width: 80px;
  height: 4px;
  background: #4a5568;
  border-radius: 2px;
  overflow: hidden;
}

.progress-mini-fill {
  height: 100%;
  background: #4299e1;
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 12px;
  color: #a0aec0;
  min-width: 35px;
}
</style>
```

### 4. Usage Examples

```vue
<!-- In your main anime generation page -->
<template>
  <div class="anime-generation-page">
    <!-- Generation Form -->
    <form @submit.prevent="startGeneration">
      <input v-model="prompt" placeholder="Enter anime prompt" />
      <button type="submit" :disabled="isGenerating">Generate</button>
    </form>

    <!-- Progress Tracker -->
    <AnimeProgressTracker
      v-if="currentJobId"
      :job-id="currentJobId"
      :job-name="prompt"
      @completed="onGenerationComplete"
      @error="onGenerationError"
    />

    <!-- System Monitor -->
    <AnimeSystemMonitor />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import AnimeProgressTracker from '@/components/AnimeProgressTracker.vue'
import AnimeSystemMonitor from '@/components/AnimeSystemMonitor.vue'

const prompt = ref('')
const currentJobId = ref(null)
const isGenerating = ref(false)

const startGeneration = async () => {
  isGenerating.value = true

  try {
    const response = await fetch('/api/anime/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt.value })
    })

    const data = await response.json()
    currentJobId.value = data.job_id
  } catch (error) {
    console.error('Generation failed:', error)
  }
}

const onGenerationComplete = (result) => {
  isGenerating.value = false
  console.log('Generation completed:', result)
  // Handle completion
}

const onGenerationError = (error) => {
  isGenerating.value = false
  console.error('Generation error:', error)
  // Handle error
}
</script>
```

## React Integration

### WebSocket Hook for React

```javascript
// hooks/useAnimeProgress.js
import { useState, useEffect, useCallback, useRef } from 'react'

export function useAnimeProgress(jobId, options = {}) {
  const [isConnected, setIsConnected] = useState(false)
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState('pending')
  const [message, setMessage] = useState('')
  const [error, setError] = useState(null)
  const [outputPath, setOutputPath] = useState(null)

  const websocketRef = useRef(null)
  const reconnectAttemptsRef = useRef(0)
  const maxReconnectAttempts = options.maxReconnectAttempts || 5
  const serverUrl = options.serverUrl || 'ws://192.168.50.135:8328'

  const connect = useCallback(() => {
    if (!jobId) return

    const wsUrl = `${serverUrl}/ws/${jobId}`
    websocketRef.current = new WebSocket(wsUrl)

    websocketRef.current.onopen = () => {
      setIsConnected(true)
      setError(null)
      reconnectAttemptsRef.current = 0
    }

    websocketRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === 'progress') {
          setProgress(data.progress)
          setStatus(data.status)
          setMessage(data.message || '')

          if (data.output_path) {
            setOutputPath(data.output_path)
          }

          if (data.error) {
            setError(data.error)
          }
        } else if (data.type === 'error') {
          setError(data.error)
          setStatus('failed')
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
        setError('Invalid message format')
      }
    }

    websocketRef.current.onclose = (event) => {
      setIsConnected(false)

      if (event.code !== 1000 && reconnectAttemptsRef.current < maxReconnectAttempts) {
        reconnectAttemptsRef.current++
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000)

        setTimeout(() => {
          connect()
        }, delay)
      }
    }

    websocketRef.current.onerror = () => {
      setError('WebSocket connection error')
    }
  }, [jobId, serverUrl, maxReconnectAttempts])

  const disconnect = useCallback(() => {
    if (websocketRef.current) {
      websocketRef.current.close(1000, 'User disconnect')
      websocketRef.current = null
    }
  }, [])

  useEffect(() => {
    if (jobId) {
      connect()
    }

    return () => {
      disconnect()
    }
  }, [jobId, connect, disconnect])

  return {
    isConnected,
    progress,
    status,
    message,
    error,
    outputPath,
    isProcessing: status === 'processing',
    isCompleted: status === 'completed',
    isFailed: status === 'failed',
    connect,
    disconnect
  }
}
```

## Performance Considerations

### 1. Connection Pooling

For applications with many concurrent jobs, consider implementing connection pooling:

```javascript
// WebSocket connection pool manager
class WebSocketPool {
  constructor(maxConnections = 10) {
    this.maxConnections = maxConnections
    this.activeConnections = new Map()
    this.queue = []
  }

  async getConnection(jobId) {
    if (this.activeConnections.has(jobId)) {
      return this.activeConnections.get(jobId)
    }

    if (this.activeConnections.size >= this.maxConnections) {
      // Queue the request
      return new Promise((resolve) => {
        this.queue.push({ jobId, resolve })
      })
    }

    const connection = await this.createConnection(jobId)
    this.activeConnections.set(jobId, connection)
    return connection
  }

  async createConnection(jobId) {
    // Implementation here
  }

  releaseConnection(jobId) {
    this.activeConnections.delete(jobId)

    // Process queue
    if (this.queue.length > 0) {
      const { jobId: queuedJobId, resolve } = this.queue.shift()
      this.getConnection(queuedJobId).then(resolve)
    }
  }
}
```

### 2. Memory Management

```javascript
// Cleanup old progress data
const useProgressCleanup = () => {
  const progressHistory = useRef(new Map())
  const maxHistoryItems = 100

  const addProgress = (jobId, data) => {
    progressHistory.current.set(jobId, data)

    // Cleanup old entries
    if (progressHistory.current.size > maxHistoryItems) {
      const oldestKey = progressHistory.current.keys().next().value
      progressHistory.current.delete(oldestKey)
    }
  }

  return { addProgress, progressHistory: progressHistory.current }
}
```

### 3. Error Boundaries

```jsx
// React Error Boundary for WebSocket errors
class WebSocketErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('WebSocket component error:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="websocket-error">
          <h3>WebSocket Connection Error</h3>
          <p>Unable to establish real-time connection.</p>
          <button onClick={() => window.location.reload()}>
            Refresh Page
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
```

This comprehensive implementation provides production-ready WebSocket functionality with proper error handling, reconnection logic, and frontend integration patterns for both Vue.js and React.