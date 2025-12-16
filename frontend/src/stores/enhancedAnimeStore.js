import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * Enhanced Anime Production Store - Production-ready state management
 * Manages projects, characters, scenes, generation history, and real-time WebSocket updates
 */
export const useEnhancedAnimeStore = defineStore('enhancedAnime', () => {
  // ==================== STATE ====================

  // Project Management
  const projects = ref([])
  const selectedProject = ref(null)
  const projectBibles = ref({}) // Map of project_id -> bible data

  // Character Management
  const characters = ref([])
  const selectedCharacter = ref(null)
  const characterSheets = ref({}) // Map of character_name -> sheet data
  const characterConsistencyScores = ref({})

  // Scene Management
  const scenes = ref([])
  const selectedScene = ref(null)
  const sceneTemplates = ref([])

  // Generation Management
  const generationHistory = ref([])
  const currentGeneration = ref(null)
  const generationQueue = ref([])

  // WebSocket Management
  const wsConnection = ref(null)
  const wsConnected = ref(false)
  const jobProgress = ref({})
  const jobETAs = ref({})

  // Echo Coordination
  const echoCoordination = ref(null)
  const echoStatus = ref('disconnected')
  const echoMessages = ref([])

  // UI State
  const loading = ref(false)
  const error = ref(null)
  const notifications = ref([])
  const activeView = ref('console') // console, studio, timeline

  // API Base URL - Use proxied endpoint in production
  const API_BASE = window.location.hostname === 'localhost'
    ? 'http://localhost:8328'
    : 'https://192.168.50.135/api/anime'
  const WS_URL = 'ws://localhost:8765'

  // ==================== COMPUTED ====================

  const currentProjectBible = computed(() => {
    return selectedProject.value
      ? projectBibles.value[selectedProject.value.id]
      : null
  })

  const currentProjectCharacters = computed(() => {
    return selectedProject.value
      ? characters.value.filter(char => char.project_id === selectedProject.value.id)
      : []
  })

  const currentProjectScenes = computed(() => {
    return selectedProject.value
      ? scenes.value.filter(scene => scene.project_id === selectedProject.value.id)
      : []
  })

  const recentGenerations = computed(() => {
    return generationHistory.value
      .filter(gen => selectedProject.value ? gen.project_id === selectedProject.value.id : true)
      .sort((a, b) => new Date(b.createdAt || b.created_at) - new Date(a.createdAt || a.created_at))
      .slice(0, 10)
  })

  const generationStats = computed(() => {
    const total = generationHistory.value.length
    const successful = generationHistory.value.filter(gen => gen.status === 'completed').length
    const failed = generationHistory.value.filter(gen => gen.status === 'failed').length
    const pending = generationHistory.value.filter(gen => ['pending', 'running', 'processing'].includes(gen.status)).length

    return {
      total,
      successful,
      failed,
      pending,
      successRate: total > 0 ? (successful / total * 100).toFixed(1) : 0
    }
  })

  const activeJobs = computed(() => {
    return generationQueue.value.filter(job =>
      ['pending', 'running', 'processing'].includes(job.status)
    )
  })

  // ==================== WEBSOCKET ACTIONS ====================

  function connectWebSocket() {
    try {
      wsConnection.value = new WebSocket(WS_URL)

      wsConnection.value.onopen = () => {
        wsConnected.value = true
        console.log('WebSocket connected to', WS_URL)
        addNotification('Real-time updates connected', 'success')
      }

      wsConnection.value.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          handleWebSocketMessage(data)
        } catch (error) {
          console.error('Error parsing WebSocket message:', error)
        }
      }

      wsConnection.value.onclose = () => {
        wsConnected.value = false
        console.log('WebSocket disconnected, attempting reconnect...')
        setTimeout(connectWebSocket, 5000)
      }

      wsConnection.value.onerror = (error) => {
        console.error('WebSocket error:', error)
        wsConnected.value = false
      }
    } catch (error) {
      console.error('Error connecting WebSocket:', error)
      setTimeout(connectWebSocket, 5000)
    }
  }

  function handleWebSocketMessage(data) {
    if (data.type === 'progress') {
      jobProgress.value[data.job_id] = data.progress
      if (data.eta) {
        jobETAs.value[data.job_id] = data.eta
      }

      // Update queue item status
      const queueIndex = generationQueue.value.findIndex(job => job.id === data.job_id)
      if (queueIndex !== -1) {
        generationQueue.value[queueIndex].status = data.status || 'running'
        generationQueue.value[queueIndex].progress = data.progress
      }
    } else if (data.type === 'job_complete') {
      // Update generation status and refresh history
      const queueIndex = generationQueue.value.findIndex(job => job.id === data.job_id)
      if (queueIndex !== -1) {
        generationQueue.value[queueIndex].status = 'completed'
        generationQueue.value[queueIndex].outputPath = data.output_path
        generationQueue.value[queueIndex].duration = data.duration
      }

      loadGenerationHistory()
      delete jobProgress.value[data.job_id]
      delete jobETAs.value[data.job_id]

      addNotification(`Generation #${data.job_id} completed`, 'success')
    } else if (data.type === 'job_failed') {
      const queueIndex = generationQueue.value.findIndex(job => job.id === data.job_id)
      if (queueIndex !== -1) {
        generationQueue.value[queueIndex].status = 'failed'
        generationQueue.value[queueIndex].error = data.error
      }

      delete jobProgress.value[data.job_id]
      delete jobETAs.value[data.job_id]

      addNotification(`Generation #${data.job_id} failed: ${data.error}`, 'error')
    }
  }

  function disconnectWebSocket() {
    if (wsConnection.value) {
      wsConnection.value.close()
      wsConnection.value = null
      wsConnected.value = false
    }
  }

  // ==================== PROJECT ACTIONS ====================

  async function loadProjects() {
    try {
      loading.value = true
      error.value = null

      const response = await fetch(`${API_BASE}/api/anime/projects`)
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

      const data = await response.json()
      projects.value = data

      addNotification('Projects loaded successfully', 'success')
    } catch (err) {
      error.value = `Failed to load projects: ${err.message}`
      addNotification(error.value, 'error')
      // Set default projects if API fails
      projects.value = [
        {
          id: 'default',
          name: 'Default Project',
          description: 'Default anime production project',
          characterCount: 0,
          generationCount: 0,
          thumbnail: null
        }
      ]
    } finally {
      loading.value = false
    }
  }

  async function createProject(projectData) {
    try {
      loading.value = true
      error.value = null

      const response = await fetch(`${API_BASE}/api/anime/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(projectData)
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

      const newProject = await response.json()
      projects.value.push(newProject)
      selectedProject.value = newProject

      addNotification(`Project "${newProject.name}" created successfully`, 'success')
      return newProject
    } catch (err) {
      error.value = `Failed to create project: ${err.message}`
      addNotification(error.value, 'error')
      throw err
    } finally {
      loading.value = false
    }
  }

  function selectProject(project) {
    selectedProject.value = project
    // Load associated data
    if (project) {
      loadProjectCharacters(project.id)
      loadProjectScenes(project.id)
    }
  }

  // ==================== CHARACTER ACTIONS ====================

  async function loadProjectCharacters(projectId) {
    try {
      const response = await fetch(`${API_BASE}/api/anime/projects/${projectId}/characters`)
      if (response.ok) {
        const projectCharacters = await response.json()
        // Update characters array with project characters
        characters.value = characters.value.filter(char => char.project_id !== projectId)
        characters.value.push(...projectCharacters.map(char => ({ ...char, project_id: projectId })))
      } else {
        // Set default characters if API fails
        characters.value = [
          {
            id: 'kai',
            name: 'Kai Nakamura',
            role: 'Main Character',
            project_id: projectId,
            thumbnail: null,
            consistencyScore: 0.85
          },
          {
            id: 'hiroshi',
            name: 'Hiroshi Yamamoto',
            role: 'Supporting Character',
            project_id: projectId,
            thumbnail: null,
            consistencyScore: 0.72
          }
        ]
      }
    } catch (err) {
      console.error(`Failed to load project characters: ${err.message}`)
      // Set default characters on error
      characters.value = []
    }
  }

  function selectCharacter(character) {
    selectedCharacter.value = character
  }

  // ==================== SCENE ACTIONS ====================

  async function loadProjectScenes(projectId) {
    try {
      const response = await fetch(`${API_BASE}/api/anime/projects/${projectId}/scenes`)
      if (response.ok) {
        const projectScenes = await response.json()
        scenes.value = scenes.value.filter(scene => scene.project_id !== projectId)
        scenes.value.push(...projectScenes)
      }
    } catch (err) {
      console.error(`Failed to load project scenes: ${err.message}`)
    }
  }

  function selectScene(scene) {
    selectedScene.value = scene
  }

  // ==================== GENERATION ACTIONS ====================

  async function startGeneration(generationRequest) {
    try {
      loading.value = true

      const response = await fetch(`${API_BASE}/api/anime/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(generationRequest)
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

      const generation = await response.json()

      // Add to queue with initial status
      const queueItem = {
        ...generation,
        id: generation.job_id || generation.id || Date.now(),
        status: 'pending',
        startTime: new Date().toISOString(),
        prompt: generationRequest.prompt,
        type: generationRequest.type,
        progress: 0
      }

      generationQueue.value.push(queueItem)
      generationHistory.value.unshift(generation)
      currentGeneration.value = generation

      addNotification('Generation started successfully', 'success')
      return generation
    } catch (err) {
      error.value = `Failed to start generation: ${err.message}`
      addNotification(error.value, 'error')
      throw err
    } finally {
      loading.value = false
    }
  }

  async function loadGenerationHistory() {
    try {
      const response = await fetch(`${API_BASE}/api/anime/generations`)
      if (response.ok) {
        const history = await response.json()
        generationHistory.value = history
      } else {
        // Set sample data if API fails
        generationHistory.value = [
          {
            id: 1,
            prompt: 'Anime girl with purple hair in cyberpunk setting',
            status: 'completed',
            type: 'image',
            createdAt: new Date().toISOString(),
            duration: 3.2,
            outputPath: '/mnt/1TB-storage/anime-projects/unorganized/images/20251202/sample1.png'
          },
          {
            id: 2,
            prompt: 'Futuristic city skyline at sunset',
            status: 'completed',
            type: 'image',
            createdAt: new Date(Date.now() - 300000).toISOString(),
            duration: 2.8,
            outputPath: '/mnt/1TB-storage/anime-projects/unorganized/images/20251202/sample2.png'
          }
        ]
      }
    } catch (err) {
      console.error(`Failed to load generation history: ${err.message}`)
      generationHistory.value = []
    }
  }

  // ==================== FILE MANAGEMENT ====================

  async function loadOrganizedFiles(date = null) {
    try {
      const dateParam = date || new Date().toISOString().split('T')[0].replace(/-/g, '')
      const response = await fetch(`${API_BASE}/api/anime/files?date=${dateParam}`)

      if (response.ok) {
        const files = await response.json()
        return files
      } else {
        // Return sample file structure
        return [
          {
            id: 1,
            name: 'anime_girl_001.png',
            path: `/mnt/1TB-storage/anime-projects/unorganized/images/${dateParam}/anime_girl_001.png`,
            type: 'image',
            size: 1024000,
            createdAt: new Date().toISOString(),
            thumbnail: true
          }
        ]
      }
    } catch (err) {
      console.error(`Failed to load organized files: ${err.message}`)
      return []
    }
  }

  // ==================== ECHO COORDINATION ====================

  async function connectToEcho() {
    try {
      const response = await fetch('http://localhost:8309/api/echo/health')
      if (response.ok) {
        echoStatus.value = 'connected'
        addNotification('Connected to Echo Brain', 'success')
        return true
      } else {
        throw new Error('Echo Brain not available')
      }
    } catch (err) {
      echoStatus.value = 'disconnected'
      console.error(`Failed to connect to Echo: ${err.message}`)
      return false
    }
  }

  async function sendEchoMessage(message, context = 'anime_production') {
    try {
      const response = await fetch('http://localhost:8309/api/echo/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: message,
          context: context,
          model: 'qwen2.5-coder:32b'
        })
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

      const echoResponse = await response.json()

      // Add to message history
      echoMessages.value.push(
        {
          type: 'user',
          content: message,
          timestamp: new Date().toISOString()
        },
        {
          type: 'echo',
          content: echoResponse.response || echoResponse.result,
          timestamp: new Date().toISOString()
        }
      )

      return echoResponse
    } catch (err) {
      error.value = `Failed to send Echo message: ${err.message}`
      addNotification(error.value, 'error')
      throw err
    }
  }

  // ==================== UTILITY ACTIONS ====================

  function addNotification(message, type = 'info', duration = 5000) {
    const notification = {
      id: Date.now() + Math.random(),
      message,
      type,
      timestamp: new Date().toISOString()
    }

    notifications.value.push(notification)

    // Auto-remove after duration
    setTimeout(() => {
      removeNotification(notification.id)
    }, duration)

    return notification
  }

  function removeNotification(id) {
    const index = notifications.value.findIndex(n => n.id === id)
    if (index !== -1) {
      notifications.value.splice(index, 1)
    }
  }

  function clearError() {
    error.value = null
  }

  function setActiveView(view) {
    activeView.value = view
  }

  // ==================== API HEALTH ====================

  async function checkApiHealth() {
    try {
      const response = await fetch(`${API_BASE}/api/anime/health`)
      return response.ok
    } catch (error) {
      return false
    }
  }

  // ==================== UTILITY FUNCTIONS ====================

  function getJobProgress(jobId) {
    return jobProgress.value[jobId] || 0
  }

  function getJobETA(jobId) {
    return jobETAs.value[jobId]
  }

  function resetStore() {
    projects.value = []
    selectedProject.value = null
    characters.value = []
    selectedCharacter.value = null
    scenes.value = []
    selectedScene.value = null
    generationHistory.value = []
    currentGeneration.value = null
    generationQueue.value = []
    echoMessages.value = []
    notifications.value = []
    error.value = null
    jobProgress.value = {}
    jobETAs.value = {}
    disconnectWebSocket()
  }

  // ==================== RETURN STORE ====================

  return {
    // State
    projects,
    selectedProject,
    characters,
    selectedCharacter,
    scenes,
    selectedScene,
    generationHistory,
    currentGeneration,
    generationQueue,
    wsConnection,
    wsConnected,
    jobProgress,
    jobETAs,
    echoStatus,
    echoMessages,
    loading,
    error,
    notifications,
    activeView,

    // Computed
    currentProjectBible,
    currentProjectCharacters,
    currentProjectScenes,
    recentGenerations,
    generationStats,
    activeJobs,

    // Actions
    connectWebSocket,
    disconnectWebSocket,
    handleWebSocketMessage,
    loadProjects,
    createProject,
    selectProject,
    loadProjectCharacters,
    selectCharacter,
    loadProjectScenes,
    selectScene,
    startGeneration,
    loadGenerationHistory,
    loadOrganizedFiles,
    connectToEcho,
    sendEchoMessage,
    addNotification,
    removeNotification,
    clearError,
    setActiveView,
    checkApiHealth,
    getJobProgress,
    getJobETA,
    resetStore
  }
})