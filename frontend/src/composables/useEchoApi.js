import { ref } from 'vue'

/**
 * Echo Brain API Composable
 *
 * Handles all communication with Echo Brain for anime production workflows.
 * Provides intelligence routing, semantic search, quality assessment, and learning.
 */
export function useEchoApi() {
  const isLoading = ref(false)
  const lastError = ref(null)

  // Determine API base URL - use proxied endpoint in production
  const baseURL = window.location.hostname === 'localhost'
    ? 'http://localhost:8309/api/echo'
    : '/api/echo'

  /**
   * Core Orchestration: Translates user intent into actionable commands
   * @param {string} userInput - Natural language command from user
   * @param {Object} context - Current project/scene context
   * @returns {Promise<Object>} Action plan with parameters
   */
  async function translateIntent(userInput, context = {}) {
    return await apiCall('/project/orchestrate', {
      command: userInput,
      project_context: context,
      intelligence_level: 'auto' // Let Echo choose appropriate model
    })
  }

  /**
   * Semantic Search with Vector Database
   * @param {string} query - Natural language search query
   * @param {string} projectId - Project to search within
   * @param {number} topK - Number of results to return
   * @returns {Promise<Array>} Search results with similarity scores
   */
  async function semanticSearch(query, projectId = null, topK = 10) {
    return await apiCall('/semantic/search', {
      text_query: query,
      project_id: projectId,
      top_k: topK,
      include_metadata: true
    })
  }

  /**
   * Character Consistency Analysis
   * @param {string} characterName - Character to analyze
   * @param {string} imageUrl - Image URL or path
   * @param {Object} referenceSheet - Character reference data
   * @returns {Promise<Object>} Consistency scores and analysis
   */
  async function analyzeCharacterConsistency(characterName, imageUrl, referenceSheet = {}) {
    return await apiCall('/character/consistency/check', {
      character_name: characterName,
      image_url: imageUrl,
      reference_sheet: referenceSheet,
      check_features: ['appearance', 'style', 'proportions'],
      quality_threshold: 0.7
    })
  }

  /**
   * Quality Assessment for Generated Content
   * @param {Object} content - Content to assess (image, video, etc.)
   * @param {string} assessmentType - Type of assessment (frame, temporal, final)
   * @returns {Promise<Object>} Quality scores and recommendations
   */
  async function assessQuality(content, assessmentType = 'frame') {
    return await apiCall('/quality/assess', {
      content: content,
      assessment_type: assessmentType,
      quality_gates: ['character_fidelity', 'artifacts', 'prompt_adherence'],
      enable_autocorrect: true
    })
  }

  /**
   * Timeline Management
   * @param {string} action - Action to perform (branch, merge, revert)
   * @param {Object} timelineData - Timeline data and parameters
   * @returns {Promise<Object>} Updated timeline state
   */
  async function manageTimeline(action, timelineData) {
    return await apiCall('/timeline/manage', {
      action: action,
      timeline_data: timelineData,
      preserve_history: true,
      auto_resolve_conflicts: false
    })
  }

  /**
   * Style Recommendation System
   * @param {Object} context - Project context and preferences
   * @param {string} prompt - User style request
   * @returns {Promise<Object>} Style recommendations and parameters
   */
  async function recommendStyle(context, prompt = '') {
    return await apiCall('/style/recommend', {
      project_context: context,
      user_prompt: prompt,
      include_variations: true,
      max_recommendations: 5
    })
  }

  /**
   * Learning from User Feedback
   * @param {Object} feedbackData - User preferences and corrections
   * @returns {Promise<void>} Confirmation of learning
   */
  async function learnPreference(feedbackData) {
    return await apiCall('/preferences/learn', {
      ...feedbackData,
      learning_mode: 'incremental',
      confidence_weight: 1.0
    })
  }

  /**
   * Project Generation Orchestration
   * @param {Object} projectSpec - Complete project specification
   * @returns {Promise<Object>} Generation plan and job queue
   */
  async function orchestrateProject(projectSpec) {
    return await apiCall('/project/generate', {
      project_spec: projectSpec,
      generation_mode: 'adaptive',
      quality_control: 'enhanced',
      parallel_processing: true
    })
  }

  /**
   * Real-time Generation Status
   * @param {string} jobId - Generation job ID
   * @returns {Promise<Object>} Current status and progress
   */
  async function getGenerationStatus(jobId) {
    return await apiCall(`/generation/status/${jobId}`, null, 'GET')
  }

  /**
   * Echo Brain Health Check
   * @returns {Promise<Object>} System status and capabilities
   */
  async function healthCheck() {
    return await apiCall('/health', null, 'GET')
  }

  /**
   * Generic API call handler with error handling and loading states
   * @private
   */
  async function apiCall(endpoint, data = null, method = 'POST') {
    isLoading.value = true
    lastError.value = null

    try {
      const config = {
        method,
        headers: {
          'Content-Type': 'application/json',
        }
      }

      if (data && method !== 'GET') {
        config.body = JSON.stringify(data)
      }

      const response = await fetch(`${baseURL}${endpoint}`, config)

      if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`)
      }

      const result = await response.json()
      return result

    } catch (error) {
      console.error('Echo API Error:', error)
      lastError.value = error.message
      throw error
    } finally {
      isLoading.value = false
    }
  }

  /**
   * WebSocket connection for real-time updates
   * @param {Function} onMessage - Message handler
   * @param {Function} onError - Error handler
   * @returns {WebSocket} WebSocket instance
   */
  function connectWebSocket(onMessage, onError) {
    const wsURL = window.location.hostname === 'localhost'
      ? 'ws://localhost:8309/ws/echo'
      : `wss://${window.location.host}/api/echo/ws`

    const ws = new WebSocket(wsURL)

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onMessage(data)
      } catch (error) {
        console.error('WebSocket message parse error:', error)
        onError?.(error)
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      onError?.(error)
    }

    return ws
  }

  // Return public API
  return {
    // State
    isLoading,
    lastError,

    // Core Methods
    translateIntent,
    semanticSearch,
    analyzeCharacterConsistency,
    assessQuality,
    manageTimeline,
    recommendStyle,
    learnPreference,
    orchestrateProject,
    getGenerationStatus,
    healthCheck,

    // WebSocket
    connectWebSocket
  }
}