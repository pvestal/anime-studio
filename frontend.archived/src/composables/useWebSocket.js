/**
 * Vue 3 Composable for WebSocket Integration with Echo Brain
 * Provides reactive WebSocket state and methods for Vue components
 */

import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import websocketService from '@/services/websocket.js'

export function useWebSocket(endpoint = 'vue_integration') {
  // Reactive state
  const isConnected = ref(false)
  const isReconnecting = ref(false)
  const connectionError = ref(null)
  const lastMessage = ref(null)

  // System state from Echo Brain
  const systemStatus = reactive({
    healthy: false,
    consciousness: 'inactive',
    working_memory: 0,
    emotional_state: {},
    active_thoughts: 0,
    agents: [],
    stats: {}
  })

  // Generation state
  const generationState = reactive({
    active: null,
    queue: [],
    queueStats: {
      pending: 0,
      running: 0,
      completed: 0
    }
  })

  // Performance metrics
  const metrics = reactive({
    cpu: 0,
    memory: 0,
    vram: {
      nvidia: 0,
      amd: 0
    },
    generationsPerHour: 0,
    avgGenerationTime: 0,
    successRate: 0,
    errorRate: 0
  })

  // Real-time logs
  const logs = ref([])
  const alerts = ref([])
  const communications = ref([])

  // Computed status
  const connectionStatus = computed(() => ({
    connected: isConnected.value,
    reconnecting: isReconnecting.value,
    error: connectionError.value,
    hasError: !!connectionError.value
  }))

  // Event handlers
  const handleConnected = (data) => {
    console.log('[useWebSocket] Connected to Echo Brain:', data)
    isConnected.value = true
    isReconnecting.value = false
    connectionError.value = null
  }

  const handleDisconnected = (data) => {
    console.log('[useWebSocket] Disconnected from Echo Brain:', data)
    isConnected.value = false
  }

  const handleError = (data) => {
    console.error('[useWebSocket] WebSocket error:', data)
    connectionError.value = data.error
  }

  const handleSystemStatus = (data) => {
    console.log('[useWebSocket] System status update:', data)
    Object.assign(systemStatus, data.stats || {})

    // Update metrics if included
    if (data.stats?.metrics) {
      Object.assign(metrics, data.stats.metrics)
    }
  }

  const handleInitialState = (data) => {
    console.log('[useWebSocket] Initial state received:', data)

    // Update system status
    if (data.system_status) {
      Object.assign(systemStatus, data.system_status)
    }

    // Update agents
    if (data.agents) {
      systemStatus.agents = data.agents
    }

    // Update alerts
    if (data.alerts) {
      alerts.value = data.alerts.slice(-10) // Keep last 10
    }

    // Update logs
    if (data.logs) {
      logs.value = data.logs.slice(-20) // Keep last 20
    }
  }

  const handleGenerationProgress = (data) => {
    console.log('[useWebSocket] Generation progress:', data)

    if (data.jobId && generationState.active?.id === data.jobId) {
      // Update active generation progress
      Object.assign(generationState.active, {
        progress: data.progress || 0,
        currentStep: data.currentStep || 0,
        totalSteps: data.totalSteps || 0,
        eta: data.eta || 0,
        elapsed: data.elapsed || 0,
        stage: data.stage || 'unknown'
      })
    }
  }

  const handleGenerationComplete = (data) => {
    console.log('[useWebSocket] Generation complete:', data)

    if (generationState.active?.id === data.jobId) {
      generationState.active.status = 'completed'
      generationState.active.progress = 100
      generationState.active.completedAt = new Date().toISOString()
    }

    // Update queue stats
    generationState.queueStats.completed++
    generationState.queueStats.running = Math.max(0, generationState.queueStats.running - 1)
  }

  const handleGenerationFailed = (data) => {
    console.log('[useWebSocket] Generation failed:', data)

    if (generationState.active?.id === data.jobId) {
      generationState.active.status = 'failed'
      generationState.active.error = data.error
      generationState.active.failedAt = new Date().toISOString()
    }

    // Update queue stats
    generationState.queueStats.running = Math.max(0, generationState.queueStats.running - 1)
  }

  const handleAgentStatusUpdate = (data) => {
    console.log('[useWebSocket] Agent status update:', data)

    // Update agent in system status
    const agentIndex = systemStatus.agents.findIndex(a => a.id === data.agent_id)
    if (agentIndex !== -1) {
      Object.assign(systemStatus.agents[agentIndex], {
        status: data.status,
        progress: data.progress,
        metadata: data.metadata || {}
      })
    }
  }

  const handleSystemAlert = (data) => {
    console.log('[useWebSocket] System alert:', data)

    alerts.value.unshift({
      id: Date.now().toString(),
      ...data,
      timestamp: new Date().toISOString()
    })

    // Keep only last 50 alerts
    if (alerts.value.length > 50) {
      alerts.value = alerts.value.slice(0, 50)
    }
  }

  const handleCommunication = (data) => {
    console.log('[useWebSocket] Communication:', data)

    communications.value.unshift({
      id: Date.now().toString(),
      ...data,
      timestamp: new Date().toISOString()
    })

    // Keep only last 100 communications
    if (communications.value.length > 100) {
      communications.value = communications.value.slice(0, 100)
    }
  }

  const handleMetricsUpdate = (data) => {
    console.log('[useWebSocket] Metrics update:', data)
    Object.assign(metrics, data.metrics || {})
  }

  const handleTaskCompletion = (data) => {
    console.log('[useWebSocket] Task completion:', data)

    // Add to communications
    communications.value.unshift({
      id: Date.now().toString(),
      source: data.agent_id,
      message: `Task completed: ${data.task_name}`,
      level: 'success',
      timestamp: new Date().toISOString()
    })
  }

  // Methods
  const connect = async (customEndpoint = null) => {
    try {
      isReconnecting.value = true
      connectionError.value = null
      await websocketService.connect(customEndpoint || endpoint)
    } catch (error) {
      console.error('[useWebSocket] Connection failed:', error)
      connectionError.value = error
    } finally {
      isReconnecting.value = false
    }
  }

  const disconnect = () => {
    websocketService.disconnect()
    isConnected.value = false
  }

  const subscribeToGeneration = (jobId) => {
    return websocketService.subscribeToGeneration(jobId)
  }

  const sendGenerationCommand = (jobId, command) => {
    return websocketService.sendGenerationCommand(jobId, command)
  }

  const requestSystemStatus = () => {
    return websocketService.requestSystemStatus()
  }

  const requestQueueStatus = () => {
    return websocketService.requestQueueStatus()
  }

  const sendMessage = (message) => {
    return websocketService.send(message)
  }

  // Clear alerts and communications
  const clearAlerts = () => {
    alerts.value = []
  }

  const clearCommunications = () => {
    communications.value = []
  }

  const clearLogs = () => {
    logs.value = []
  }

  // Lifecycle
  onMounted(() => {
    // Register all event handlers
    websocketService.on('connected', handleConnected)
    websocketService.on('disconnected', handleDisconnected)
    websocketService.on('error', handleError)
    websocketService.on('system_status', handleSystemStatus)
    websocketService.on('initial_state', handleInitialState)
    websocketService.on('generation_progress', handleGenerationProgress)
    websocketService.on('generation_complete', handleGenerationComplete)
    websocketService.on('generation_failed', handleGenerationFailed)
    websocketService.on('agent_status_update', handleAgentStatusUpdate)
    websocketService.on('system_alert', handleSystemAlert)
    websocketService.on('communication', handleCommunication)
    websocketService.on('metrics_update', handleMetricsUpdate)
    websocketService.on('task_completion', handleTaskCompletion)

    // Auto-connect
    connect()
  })

  onUnmounted(() => {
    // Unregister event handlers
    websocketService.off('connected', handleConnected)
    websocketService.off('disconnected', handleDisconnected)
    websocketService.off('error', handleError)
    websocketService.off('system_status', handleSystemStatus)
    websocketService.off('initial_state', handleInitialState)
    websocketService.off('generation_progress', handleGenerationProgress)
    websocketService.off('generation_complete', handleGenerationComplete)
    websocketService.off('generation_failed', handleGenerationFailed)
    websocketService.off('agent_status_update', handleAgentStatusUpdate)
    websocketService.off('system_alert', handleSystemAlert)
    websocketService.off('communication', handleCommunication)
    websocketService.off('metrics_update', handleMetricsUpdate)
    websocketService.off('task_completion', handleTaskCompletion)
  })

  return {
    // State
    connectionStatus,
    isConnected,
    isReconnecting,
    connectionError,
    lastMessage,
    systemStatus,
    generationState,
    metrics,
    logs,
    alerts,
    communications,

    // Methods
    connect,
    disconnect,
    subscribeToGeneration,
    sendGenerationCommand,
    requestSystemStatus,
    requestQueueStatus,
    sendMessage,
    clearAlerts,
    clearCommunications,
    clearLogs
  }
}