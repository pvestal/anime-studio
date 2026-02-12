/**
 * WebSocket Service for Real-time Echo Brain Integration
 * Connects StatusDashboard.vue to Echo Brain coordination layer
 */

class WebSocketService {
  constructor() {
    this.ws = null
    this.isConnected = false
    this.isReconnecting = false
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5
    this.reconnectInterval = 1000 // Start with 1 second
    this.maxReconnectInterval = 30000 // Max 30 seconds
    this.heartbeatInterval = null
    this.messageHandlers = new Map()
    this.connectionPromise = null
    this.eventListeners = new Map()

    // Echo Brain WebSocket endpoints
    this.endpoints = {
      echo: 'wss://192.168.50.135/api/echo/ws',
      coordination: 'wss://192.168.50.135/api/coordination/ws',
      vue_integration: 'wss://192.168.50.135/api/ws'
    }
  }

  /**
   * Connect to Echo Brain WebSocket with specified endpoint
   * @param {string} endpoint - Which Echo Brain endpoint to connect to
   * @param {Object} options - Connection options
   */
  async connect(endpoint = 'vue_integration', options = {}) {
    if (this.isConnected || this.isReconnecting) {
      return this.connectionPromise
    }

    this.connectionPromise = new Promise((resolve, reject) => {
      try {
        const wsUrl = this.endpoints[endpoint] || this.endpoints.vue_integration
        console.log(`[WebSocket] Connecting to Echo Brain at: ${wsUrl}`)

        this.ws = new WebSocket(wsUrl)

        this.ws.onopen = () => {
          console.log('[WebSocket] Connected to Echo Brain')
          this.isConnected = true
          this.isReconnecting = false
          this.reconnectAttempts = 0
          this.reconnectInterval = 1000
          this.startHeartbeat()
          this.emit('connected', { endpoint, timestamp: new Date().toISOString() })
          resolve()
        }

        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            this.handleMessage(data)
          } catch (error) {
            console.error('[WebSocket] Failed to parse message:', error, event.data)
          }
        }

        this.ws.onclose = (event) => {
          console.log(`[WebSocket] Connection closed: ${event.code} - ${event.reason}`)
          this.isConnected = false
          this.stopHeartbeat()
          this.emit('disconnected', { code: event.code, reason: event.reason })

          if (!event.wasClean && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.scheduleReconnect(endpoint, options)
          }
        }

        this.ws.onerror = (error) => {
          console.error('[WebSocket] Connection error:', error)
          this.emit('error', { error, timestamp: new Date().toISOString() })
          reject(error)
        }

      } catch (error) {
        console.error('[WebSocket] Connection setup failed:', error)
        this.emit('error', { error, timestamp: new Date().toISOString() })
        reject(error)
      }
    })

    return this.connectionPromise
  }

  /**
   * Handle incoming WebSocket messages from Echo Brain
   * @param {Object} data - Message data from Echo Brain
   */
  handleMessage(data) {
    const { type, payload, timestamp } = data

    console.log(`[WebSocket] Received ${type}:`, payload)

    // Route messages to specific handlers
    switch (type) {
      case 'system_status':
        this.emit('system_status', payload)
        break

      case 'query_result':
        this.emit('query_result', payload)
        break

      case 'workflow_result':
        this.emit('workflow_result', payload)
        break

      case 'agent_status_update':
        this.emit('agent_status_update', payload)
        break

      case 'generation_progress':
        this.emit('generation_progress', payload)
        break

      case 'generation_complete':
        this.emit('generation_complete', payload)
        break

      case 'generation_failed':
        this.emit('generation_failed', payload)
        break

      case 'system_alert':
        this.emit('system_alert', payload)
        break

      case 'metrics_update':
        this.emit('metrics_update', payload)
        break

      case 'communication':
        this.emit('communication', payload)
        break

      case 'task_completion':
        this.emit('task_completion', payload)
        break

      case 'initial_state':
        this.emit('initial_state', payload)
        break

      default:
        console.warn(`[WebSocket] Unknown message type: ${type}`)
        this.emit('message', data)
    }
  }

  /**
   * Send message to Echo Brain via WebSocket
   * @param {Object} message - Message to send
   */
  send(message) {
    if (!this.isConnected || !this.ws) {
      console.warn('[WebSocket] Cannot send message - not connected')
      return false
    }

    try {
      const messageWithTimestamp = {
        ...message,
        timestamp: new Date().toISOString()
      }

      this.ws.send(JSON.stringify(messageWithTimestamp))
      console.log('[WebSocket] Sent message:', messageWithTimestamp)
      return true
    } catch (error) {
      console.error('[WebSocket] Send failed:', error)
      return false
    }
  }

  /**
   * Subscribe to specific message types
   * @param {string} event - Event type to listen for
   * @param {Function} handler - Handler function
   */
  on(event, handler) {
    if (!this.eventListeners.has(event)) {
      this.eventListeners.set(event, new Set())
    }
    this.eventListeners.get(event).add(handler)
  }

  /**
   * Unsubscribe from event
   * @param {string} event - Event type
   * @param {Function} handler - Handler to remove
   */
  off(event, handler) {
    if (this.eventListeners.has(event)) {
      this.eventListeners.get(event).delete(handler)
    }
  }

  /**
   * Emit event to all listeners
   * @param {string} event - Event type
   * @param {*} data - Event data
   */
  emit(event, data) {
    if (this.eventListeners.has(event)) {
      this.eventListeners.get(event).forEach(handler => {
        try {
          handler(data)
        } catch (error) {
          console.error(`[WebSocket] Event handler error for ${event}:`, error)
        }
      })
    }
  }

  /**
   * Start heartbeat to keep connection alive
   */
  startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      if (this.isConnected) {
        this.send({ type: 'ping' })
      }
    }, 30000) // Ping every 30 seconds
  }

  /**
   * Stop heartbeat
   */
  stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval)
      this.heartbeatInterval = null
    }
  }

  /**
   * Schedule reconnection attempt
   * @param {string} endpoint - Endpoint to reconnect to
   * @param {Object} options - Connection options
   */
  scheduleReconnect(endpoint, options) {
    if (this.isReconnecting) return

    this.isReconnecting = true
    this.reconnectAttempts++

    console.log(`[WebSocket] Scheduling reconnect attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${this.reconnectInterval}ms`)

    setTimeout(() => {
      this.isReconnecting = false
      this.connect(endpoint, options)
    }, this.reconnectInterval)

    // Exponential backoff
    this.reconnectInterval = Math.min(
      this.reconnectInterval * 1.5,
      this.maxReconnectInterval
    )
  }

  /**
   * Request generation progress updates for a specific job
   * @param {string} jobId - Generation job ID
   */
  subscribeToGeneration(jobId) {
    return this.send({
      type: 'subscribe_generation',
      payload: { jobId }
    })
  }

  /**
   * Request system status updates
   */
  requestSystemStatus() {
    return this.send({
      type: 'request_system_status'
    })
  }

  /**
   * Request queue status
   */
  requestQueueStatus() {
    return this.send({
      type: 'request_queue_status'
    })
  }

  /**
   * Send generation command (pause/resume/cancel)
   * @param {string} jobId - Generation job ID
   * @param {string} command - Command: 'pause', 'resume', 'cancel'
   */
  sendGenerationCommand(jobId, command) {
    return this.send({
      type: 'generation_command',
      payload: { jobId, command }
    })
  }

  /**
   * Disconnect from WebSocket
   */
  disconnect() {
    console.log('[WebSocket] Disconnecting from Echo Brain')
    this.stopHeartbeat()
    this.isConnected = false
    this.reconnectAttempts = this.maxReconnectAttempts // Prevent reconnection

    if (this.ws) {
      this.ws.close(1000, 'Manual disconnect')
      this.ws = null
    }
  }

  /**
   * Get connection status
   */
  getStatus() {
    return {
      connected: this.isConnected,
      reconnecting: this.isReconnecting,
      reconnectAttempts: this.reconnectAttempts,
      activeListeners: Array.from(this.eventListeners.keys())
    }
  }
}

// Export singleton instance
export const websocketService = new WebSocketService()
export default websocketService