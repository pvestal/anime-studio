import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAnimeStore } from './animeStore'

/**
 * Video Generation Store - Specialized store for video generation workflows
 * Extends the main anime store with video-specific functionality
 */
export const useVideoStore = defineStore('video', () => {
  const animeStore = useAnimeStore()

  // Video-specific state
  const activeVideoJobs = ref(new Map())
  const videoProgress = ref({})
  const videoWebsockets = ref(new Map())
  const videoHistory = ref([])

  // Computed properties
  const currentVideoGeneration = computed(() => {
    return animeStore.currentGeneration?.type === 'video'
      ? animeStore.currentGeneration
      : null
  })

  const videoGenerationStats = computed(() => {
    const videos = videoHistory.value
    const total = videos.length
    const successful = videos.filter(v => v.status === 'completed').length
    const failed = videos.filter(v => v.status === 'failed').length
    const pending = videos.filter(v => v.status === 'processing').length

    return {
      total,
      successful,
      failed,
      pending,
      successRate: total > 0 ? (successful / total * 100).toFixed(1) : 0
    }
  })

  // Video generation actions
  async function startVideoGeneration(videoRequest) {
    try {
      const response = await fetch('/api/anime/generate/video', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...videoRequest,
          type: 'video'
        })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to start video generation')
      }

      const videoGeneration = await response.json()

      // Add to video history
      videoHistory.value.unshift(videoGeneration)

      // Store active job
      activeVideoJobs.value.set(videoGeneration.job_id, videoGeneration)

      animeStore.addNotification('Video generation started successfully', 'success')
      return videoGeneration
    } catch (err) {
      animeStore.addNotification(`Video generation failed: ${err.message}`, 'error')
      throw err
    }
  }

  async function getVideoStatus(jobId) {
    try {
      const response = await fetch(`/api/anime/generation/${jobId}/status`)

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const status = await response.json()

      // Update video progress
      videoProgress.value[jobId] = status

      // Update active job if it exists
      if (activeVideoJobs.value.has(jobId)) {
        const job = activeVideoJobs.value.get(jobId)
        activeVideoJobs.value.set(jobId, { ...job, ...status })
      }

      // Update video history
      const historyIndex = videoHistory.value.findIndex(v => v.job_id === jobId)
      if (historyIndex !== -1) {
        videoHistory.value[historyIndex] = {
          ...videoHistory.value[historyIndex],
          ...status
        }
      }

      return status
    } catch (err) {
      console.error(`Failed to get video status: ${err.message}`)
      throw err
    }
  }

  function connectVideoWebSocket(jobId) {
    const wsUrl = `ws://localhost:8328/ws/progress/${jobId}`
    const websocket = new WebSocket(wsUrl)

    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data)

      // Update progress
      videoProgress.value[jobId] = data

      // Update active job
      if (activeVideoJobs.value.has(jobId)) {
        const job = activeVideoJobs.value.get(jobId)
        activeVideoJobs.value.set(jobId, { ...job, ...data })
      }

      // If completed or failed, clean up
      if (data.status === 'completed' || data.status === 'failed') {
        disconnectVideoWebSocket(jobId)

        if (data.status === 'completed') {
          animeStore.addNotification('Video generation completed!', 'success')
        } else {
          animeStore.addNotification(`Video generation failed: ${data.error}`, 'error')
        }
      }
    }

    websocket.onerror = () => {
      console.warn(`Video WebSocket error for job ${jobId}, falling back to polling`)
      // Fall back to polling
      pollVideoStatus(jobId)
    }

    websocket.onclose = () => {
      videoWebsockets.value.delete(jobId)
    }

    videoWebsockets.value.set(jobId, websocket)
    return websocket
  }

  function disconnectVideoWebSocket(jobId) {
    if (videoWebsockets.value.has(jobId)) {
      const ws = videoWebsockets.value.get(jobId)
      ws.close()
      videoWebsockets.value.delete(jobId)
    }
  }

  function pollVideoStatus(jobId) {
    const pollInterval = setInterval(async () => {
      try {
        const status = await getVideoStatus(jobId)

        if (status.status === 'completed' || status.status === 'failed') {
          clearInterval(pollInterval)
        }
      } catch (err) {
        console.error('Video polling error:', err)
        // Continue polling even on error
      }
    }, 3000)

    // Clean up after 10 minutes
    setTimeout(() => clearInterval(pollInterval), 600000)
  }

  function getVideoUrl(jobId) {
    return `/api/anime/video/${jobId}`
  }

  function downloadVideo(jobId, filename) {
    const link = document.createElement('a')
    link.href = getVideoUrl(jobId)
    link.download = filename || `anime_video_${jobId}.mp4`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  async function shareVideo(jobId, title, description) {
    const videoUrl = window.location.origin + getVideoUrl(jobId)

    if (navigator.share) {
      try {
        await navigator.share({
          title: title || 'Generated Anime Video',
          text: description || 'Check out this anime video I generated!',
          url: videoUrl
        })
        return true
      } catch (err) {
        console.log('Share cancelled or failed:', err)
      }
    }

    // Fallback to clipboard
    try {
      await navigator.clipboard.writeText(videoUrl)
      animeStore.addNotification('Video URL copied to clipboard', 'success')
      return true
    } catch (err) {
      console.error('Failed to copy to clipboard:', err)
      animeStore.addNotification('Failed to share video', 'error')
      return false
    }
  }

  function clearVideoJob(jobId) {
    activeVideoJobs.value.delete(jobId)
    delete videoProgress.value[jobId]
    disconnectVideoWebSocket(jobId)
  }

  function clearAllVideoJobs() {
    // Close all websockets
    videoWebsockets.value.forEach(ws => ws.close())

    // Clear all data
    activeVideoJobs.value.clear()
    videoProgress.value = {}
    videoWebsockets.value.clear()
  }

  // Cleanup on unmount
  function cleanup() {
    clearAllVideoJobs()
  }

  return {
    // State
    activeVideoJobs: computed(() => Object.fromEntries(activeVideoJobs.value)),
    videoProgress,
    videoHistory,

    // Computed
    currentVideoGeneration,
    videoGenerationStats,

    // Actions
    startVideoGeneration,
    getVideoStatus,
    connectVideoWebSocket,
    disconnectVideoWebSocket,
    pollVideoStatus,
    getVideoUrl,
    downloadVideo,
    shareVideo,
    clearVideoJob,
    clearAllVideoJobs,
    cleanup
  }
})