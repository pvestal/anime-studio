<template>
  <div class="video-generation-panel">
    <!-- Header -->
    <div class="panel-header">
      <h2 class="panel-title">
        <span class="title-icon">🎬</span>
        Video Generation
      </h2>
      <div class="status-badge" :class="statusClass">
        {{ currentStatus }}
      </div>
    </div>

    <!-- Main Form -->
    <form @submit.prevent="startVideoGeneration" class="generation-form">
      <!-- Prompt Section -->
      <div class="form-section">
        <label class="form-label">Prompt</label>
        <textarea
          v-model="form.prompt"
          class="form-textarea"
          rows="3"
          placeholder="Describe your anime scene for video generation..."
          :disabled="isGenerating"
        />
        <div class="prompt-counter">{{ form.prompt.length }}/500</div>
      </div>

      <!-- Video Settings Grid -->
      <div class="settings-grid">
        <!-- Duration Settings -->
        <div class="form-group">
          <label class="form-label">Duration</label>
          <div class="duration-controls">
            <input
              v-model.number="form.frames"
              type="range"
              min="24"
              max="120"
              step="12"
              class="duration-slider"
              :disabled="isGenerating"
            />
            <div class="duration-display">
              {{ (form.frames / form.fps).toFixed(1) }}s ({{ form.frames }} frames)
            </div>
          </div>
        </div>

        <!-- FPS Selection -->
        <div class="form-group">
          <label class="form-label">Frame Rate</label>
          <select v-model.number="form.fps" class="form-select" :disabled="isGenerating">
            <option :value="8">8 FPS (Choppy)</option>
            <option :value="12">12 FPS (Stop-motion)</option>
            <option :value="24">24 FPS (Standard)</option>
            <option :value="30">30 FPS (Smooth)</option>
          </select>
        </div>

        <!-- Resolution -->
        <div class="form-group">
          <label class="form-label">Resolution</label>
          <select v-model="selectedResolution" class="form-select" :disabled="isGenerating">
            <option value="512x512">512×512 (Fast)</option>
            <option value="640x480">640×480 (4:3)</option>
            <option value="768x432">768×432 (16:9)</option>
            <option value="512x768">512×768 (Portrait)</option>
          </select>
        </div>

        <!-- Quality Settings -->
        <div class="form-group">
          <label class="form-label">Quality</label>
          <select v-model="qualityPreset" class="form-select" :disabled="isGenerating">
            <option value="draft">Draft (Fast)</option>
            <option value="balanced">Balanced</option>
            <option value="high">High Quality</option>
          </select>
        </div>
      </div>

      <!-- Advanced Settings (Collapsible) -->
      <div class="advanced-section">
        <button
          type="button"
          @click="showAdvanced = !showAdvanced"
          class="advanced-toggle"
        >
          <span>Advanced Settings</span>
          <span class="toggle-icon" :class="{ 'expanded': showAdvanced }">▼</span>
        </button>

        <transition name="expand">
          <div v-if="showAdvanced" class="advanced-controls">
            <div class="advanced-grid">
              <div class="form-group">
                <label class="form-label">Steps ({{ form.steps }})</label>
                <input
                  v-model.number="form.steps"
                  type="range"
                  min="8"
                  max="30"
                  class="form-range"
                  :disabled="isGenerating"
                />
              </div>

              <div class="form-group">
                <label class="form-label">CFG Scale ({{ form.cfg }})</label>
                <input
                  v-model.number="form.cfg"
                  type="range"
                  min="3"
                  max="15"
                  step="0.5"
                  class="form-range"
                  :disabled="isGenerating"
                />
              </div>

              <div class="form-group">
                <label class="form-label">Seed</label>
                <div class="seed-controls">
                  <input
                    v-model.number="form.seed"
                    type="number"
                    class="form-input"
                    placeholder="Random"
                    :disabled="isGenerating"
                  />
                  <button
                    type="button"
                    @click="randomizeSeed"
                    class="seed-button"
                    :disabled="isGenerating"
                  >
                    🎲
                  </button>
                </div>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">Negative Prompt</label>
              <textarea
                v-model="form.negative_prompt"
                class="form-textarea small"
                rows="2"
                placeholder="What to avoid in generation..."
                :disabled="isGenerating"
              />
            </div>
          </div>
        </transition>
      </div>

      <!-- Generation Button -->
      <button
        type="submit"
        class="generate-button"
        :disabled="!canGenerate"
        :class="{ 'generating': isGenerating }"
      >
        <span v-if="!isGenerating">
          🎬 Generate Video
        </span>
        <span v-else class="generating-text">
          <span class="spinner"></span>
          Generating...
        </span>
      </button>

      <!-- Estimated Time -->
      <div v-if="estimatedTime" class="estimate-info">
        <span class="estimate-label">Estimated time:</span>
        <span class="estimate-value">{{ estimatedTime }}</span>
      </div>
    </form>

    <!-- Progress Section -->
    <transition name="slide-down">
      <div v-if="currentJob" class="progress-section">
        <div class="progress-header">
          <h3>Generation Progress</h3>
          <div class="job-id">Job: {{ currentJob.id?.slice(0, 8) }}</div>
        </div>

        <div class="progress-bar-container">
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: progress + '%' }"
            ></div>
          </div>
          <div class="progress-text">{{ progress }}%</div>
        </div>

        <div v-if="progressMessage" class="progress-message">
          {{ progressMessage }}
        </div>

        <div v-if="timeRemaining" class="time-remaining">
          Estimated time remaining: {{ timeRemaining }}
        </div>
      </div>
    </transition>

    <!-- Result Section -->
    <transition name="slide-down">
      <div v-if="completedVideo" class="result-section">
        <div class="result-header">
          <h3>✅ Video Generated Successfully!</h3>
          <div class="generation-stats">
            Duration: {{ completedVideo.duration }}s |
            Size: {{ completedVideo.frames }} frames |
            Quality: {{ completedVideo.quality }}
          </div>
        </div>

        <div class="video-preview">
          <video
            :src="completedVideo.url"
            controls
            autoplay
            muted
            loop
            class="generated-video"
          ></video>
        </div>

        <div class="result-actions">
          <button @click="downloadVideo" class="action-button download">
            💾 Download
          </button>
          <button @click="shareVideo" class="action-button share">
            🔗 Share
          </button>
          <button @click="generateAnother" class="action-button secondary">
            🔄 Generate Another
          </button>
        </div>
      </div>
    </transition>

    <!-- Error Section -->
    <transition name="slide-down">
      <div v-if="error" class="error-section">
        <div class="error-header">
          <span class="error-icon">⚠️</span>
          <span>Generation Failed</span>
        </div>
        <div class="error-message">{{ error }}</div>
        <button @click="clearError" class="error-close">
          ✕ Dismiss
        </button>
      </div>
    </transition>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAnimeStore } from '../stores/animeStore'

export default {
  name: 'VideoGenerationPanel',
  setup() {
    const store = useAnimeStore()

    // Form state
    const form = ref({
      prompt: '',
      frames: 48,
      fps: 24,
      width: 512,
      height: 512,
      steps: 15,
      cfg: 8.0,
      seed: -1,
      negative_prompt: 'worst quality, low quality, blurry'
    })

    // UI state
    const showAdvanced = ref(false)
    const selectedResolution = ref('512x512')
    const qualityPreset = ref('balanced')
    const isGenerating = ref(false)
    const currentJob = ref(null)
    const progress = ref(0)
    const progressMessage = ref('')
    const timeRemaining = ref('')
    const completedVideo = ref(null)
    const error = ref('')
    const websocket = ref(null)

    // Computed properties
    const currentStatus = computed(() => {
      if (error.value) return 'Error'
      if (isGenerating.value) return 'Generating'
      if (completedVideo.value) return 'Complete'
      return 'Ready'
    })

    const statusClass = computed(() => {
      if (error.value) return 'status-error'
      if (isGenerating.value) return 'status-processing'
      if (completedVideo.value) return 'status-complete'
      return 'status-ready'
    })

    const canGenerate = computed(() => {
      return form.value.prompt.length > 0 && !isGenerating.value
    })

    const estimatedTime = computed(() => {
      if (!form.value.prompt) return null
      const duration = form.value.frames / form.value.fps
      const complexity = qualityPreset.value === 'high' ? 1.5 : qualityPreset.value === 'draft' ? 0.7 : 1.0
      const estimate = Math.round(duration * 30 * complexity) // ~30s per second of video
      return `${Math.floor(estimate / 60)}:${(estimate % 60).toString().padStart(2, '0')}`
    })

    // Watchers for preset changes
    const updateResolution = () => {
      const [width, height] = selectedResolution.value.split('x').map(Number)
      form.value.width = width
      form.value.height = height
    }

    const updateQualitySettings = () => {
      switch (qualityPreset.value) {
        case 'draft':
          form.value.steps = 10
          form.value.cfg = 6.0
          break
        case 'balanced':
          form.value.steps = 15
          form.value.cfg = 8.0
          break
        case 'high':
          form.value.steps = 25
          form.value.cfg = 10.0
          break
      }
    }

    // Methods
    const randomizeSeed = () => {
      form.value.seed = Math.floor(Math.random() * 2147483647)
    }

    const startVideoGeneration = async () => {
      try {
        isGenerating.value = true
        error.value = ''
        progress.value = 0
        completedVideo.value = null

        updateResolution()
        updateQualitySettings()

        const response = await fetch('/api/anime/generate/video', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...form.value,
            type: 'video'
          })
        })

        if (!response.ok) {
          const errorData = await response.json()
          throw new Error(errorData.detail || 'Failed to start video generation')
        }

        const result = await response.json()
        currentJob.value = result

        // Connect to WebSocket for progress updates
        connectWebSocket(result.job_id)

        store.addNotification('Video generation started successfully', 'success')
      } catch (err) {
        error.value = err.message
        isGenerating.value = false
        store.addNotification(`Video generation failed: ${err.message}`, 'error')
      }
    }

    const connectWebSocket = (jobId) => {
      const wsUrl = `ws://localhost:8328/ws/progress/${jobId}`
      websocket.value = new WebSocket(wsUrl)

      websocket.value.onmessage = (event) => {
        const data = JSON.parse(event.data)

        progress.value = data.progress || 0
        progressMessage.value = data.message || ''

        if (data.estimated_remaining) {
          const minutes = Math.floor(data.estimated_remaining / 60)
          const seconds = data.estimated_remaining % 60
          timeRemaining.value = `${minutes}:${seconds.toString().padStart(2, '0')}`
        }

        if (data.status === 'completed') {
          handleGenerationComplete(data)
        } else if (data.status === 'failed') {
          handleGenerationError(data.error || 'Generation failed')
        }
      }

      websocket.value.onerror = () => {
        console.warn('WebSocket connection failed, polling for updates...')
        pollForUpdates(jobId)
      }
    }

    const pollForUpdates = async (jobId) => {
      const pollInterval = setInterval(async () => {
        try {
          const response = await fetch(`/api/anime/generation/${jobId}/status`)
          if (response.ok) {
            const data = await response.json()

            progress.value = data.progress || 0

            if (data.status === 'completed') {
              clearInterval(pollInterval)
              handleGenerationComplete(data)
            } else if (data.status === 'failed') {
              clearInterval(pollInterval)
              handleGenerationError(data.error || 'Generation failed')
            }
          }
        } catch (err) {
          console.error('Polling error:', err)
        }
      }, 3000)

      // Clean up after 10 minutes
      setTimeout(() => clearInterval(pollInterval), 600000)
    }

    const handleGenerationComplete = (data) => {
      isGenerating.value = false
      progress.value = 100

      completedVideo.value = {
        url: `/api/anime/video/${currentJob.value.job_id}`,
        duration: form.value.frames / form.value.fps,
        frames: form.value.frames,
        quality: qualityPreset.value,
        path: data.output_path
      }

      store.addNotification('Video generation completed!', 'success')
      closeWebSocket()
    }

    const handleGenerationError = (errorMessage) => {
      isGenerating.value = false
      error.value = errorMessage
      store.addNotification(`Video generation failed: ${errorMessage}`, 'error')
      closeWebSocket()
    }

    const closeWebSocket = () => {
      if (websocket.value) {
        websocket.value.close()
        websocket.value = null
      }
    }

    const downloadVideo = () => {
      if (completedVideo.value) {
        const link = document.createElement('a')
        link.href = completedVideo.value.url
        link.download = `anime_video_${Date.now()}.mp4`
        link.click()
      }
    }

    const shareVideo = async () => {
      if (navigator.share && completedVideo.value) {
        try {
          await navigator.share({
            title: 'Generated Anime Video',
            text: `Check out this anime video I generated: ${form.value.prompt}`,
            url: completedVideo.value.url
          })
        } catch (err) {
          // Fallback to clipboard
          navigator.clipboard.writeText(window.location.origin + completedVideo.value.url)
          store.addNotification('Video URL copied to clipboard', 'success')
        }
      }
    }

    const generateAnother = () => {
      completedVideo.value = null
      currentJob.value = null
      progress.value = 0
      error.value = ''
    }

    const clearError = () => {
      error.value = ''
    }

    // Lifecycle
    onMounted(() => {
      randomizeSeed()
    })

    onUnmounted(() => {
      closeWebSocket()
    })

    return {
      // State
      form,
      showAdvanced,
      selectedResolution,
      qualityPreset,
      isGenerating,
      currentJob,
      progress,
      progressMessage,
      timeRemaining,
      completedVideo,
      error,

      // Computed
      currentStatus,
      statusClass,
      canGenerate,
      estimatedTime,

      // Methods
      randomizeSeed,
      startVideoGeneration,
      downloadVideo,
      shareVideo,
      generateAnother,
      clearError
    }
  }
}
</script>

<style scoped>
.video-generation-panel {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 16px;
  padding: 24px;
  color: white;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.panel-title {
  display: flex;
  align-items: center;
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
}

.title-icon {
  margin-right: 12px;
  font-size: 1.8rem;
}

.status-badge {
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.status-ready { background: rgba(16, 185, 129, 0.2); color: #10b981; }
.status-processing { background: rgba(59, 130, 246, 0.2); color: #3b82f6; }
.status-complete { background: rgba(16, 185, 129, 0.2); color: #10b981; }
.status-error { background: rgba(239, 68, 68, 0.2); color: #ef4444; }

.generation-form {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 20px;
  backdrop-filter: blur(10px);
}

.form-section {
  margin-bottom: 20px;
}

.form-label {
  display: block;
  font-weight: 600;
  margin-bottom: 8px;
  color: rgba(255, 255, 255, 0.9);
}

.form-textarea {
  width: 100%;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  padding: 12px;
  color: white;
  font-size: 14px;
  resize: vertical;
  transition: all 0.2s;
}

.form-textarea:focus {
  outline: none;
  border-color: rgba(255, 255, 255, 0.4);
  background: rgba(255, 255, 255, 0.15);
}

.form-textarea.small {
  font-size: 13px;
  padding: 10px;
}

.prompt-counter {
  text-align: right;
  font-size: 0.8rem;
  color: rgba(255, 255, 255, 0.6);
  margin-top: 4px;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
}

.duration-controls {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.duration-slider {
  width: 100%;
  accent-color: white;
}

.duration-display {
  font-size: 0.9rem;
  text-align: center;
  color: rgba(255, 255, 255, 0.8);
  padding: 4px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}

.form-select, .form-input {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  padding: 10px;
  color: white;
  font-size: 14px;
}

.form-select:focus, .form-input:focus {
  outline: none;
  border-color: rgba(255, 255, 255, 0.4);
}

.advanced-section {
  margin-bottom: 20px;
}

.advanced-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  padding: 12px;
  color: white;
  cursor: pointer;
  transition: all 0.2s;
}

.advanced-toggle:hover {
  background: rgba(255, 255, 255, 0.15);
}

.toggle-icon {
  transition: transform 0.3s;
}

.toggle-icon.expanded {
  transform: rotate(180deg);
}

.advanced-controls {
  margin-top: 16px;
  padding: 16px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
}

.advanced-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.form-range {
  width: 100%;
  accent-color: white;
  margin-top: 4px;
}

.seed-controls {
  display: flex;
  gap: 8px;
}

.seed-button {
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 6px;
  padding: 10px;
  color: white;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 44px;
}

.seed-button:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.3);
}

.generate-button {
  width: 100%;
  background: linear-gradient(45deg, #4facfe 0%, #00f2fe 100%);
  border: none;
  border-radius: 12px;
  padding: 16px;
  color: white;
  font-size: 1.1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow: 0 4px 15px rgba(79, 172, 254, 0.3);
}

.generate-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(79, 172, 254, 0.4);
}

.generate-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.generate-button.generating {
  background: linear-gradient(45deg, #667eea, #764ba2);
}

.generating-text {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid transparent;
  border-top: 2px solid white;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.estimate-info {
  text-align: center;
  margin-top: 12px;
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.7);
}

.estimate-label {
  margin-right: 8px;
}

.estimate-value {
  font-weight: 600;
  color: white;
}

.progress-section {
  margin-top: 24px;
  padding: 20px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 12px;
}

.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.progress-header h3 {
  margin: 0;
  font-size: 1.1rem;
}

.job-id {
  font-size: 0.8rem;
  color: rgba(255, 255, 255, 0.6);
  font-family: monospace;
}

.progress-bar-container {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.progress-bar {
  flex: 1;
  height: 8px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #4facfe, #00f2fe);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.progress-text {
  font-size: 0.9rem;
  font-weight: 600;
  min-width: 40px;
  text-align: right;
}

.progress-message {
  color: rgba(255, 255, 255, 0.8);
  font-size: 0.9rem;
  margin-bottom: 8px;
}

.time-remaining {
  color: rgba(255, 255, 255, 0.7);
  font-size: 0.8rem;
}

.result-section {
  margin-top: 24px;
  padding: 20px;
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.3);
  border-radius: 12px;
}

.result-header h3 {
  margin: 0 0 8px 0;
  color: #10b981;
}

.generation-stats {
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.8);
  margin-bottom: 16px;
}

.video-preview {
  margin-bottom: 16px;
}

.generated-video {
  width: 100%;
  max-width: 512px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.result-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.action-button {
  padding: 10px 16px;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-button.download {
  background: #10b981;
  color: white;
}

.action-button.share {
  background: #3b82f6;
  color: white;
}

.action-button.secondary {
  background: rgba(255, 255, 255, 0.2);
  color: white;
}

.action-button:hover {
  transform: translateY(-1px);
}

.error-section {
  margin-top: 24px;
  padding: 16px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 12px;
}

.error-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #ef4444;
  margin-bottom: 8px;
}

.error-message {
  color: rgba(255, 255, 255, 0.9);
  margin-bottom: 12px;
}

.error-close {
  background: rgba(239, 68, 68, 0.2);
  border: 1px solid rgba(239, 68, 68, 0.4);
  border-radius: 6px;
  padding: 8px 12px;
  color: white;
  cursor: pointer;
  transition: all 0.2s;
}

.error-close:hover {
  background: rgba(239, 68, 68, 0.3);
}

/* Transitions */
.expand-enter-active, .expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.expand-enter-from, .expand-leave-to {
  max-height: 0;
  opacity: 0;
}

.expand-enter-to, .expand-leave-from {
  max-height: 500px;
  opacity: 1;
}

.slide-down-enter-active, .slide-down-leave-active {
  transition: all 0.4s ease;
}

.slide-down-enter-from {
  transform: translateY(-20px);
  opacity: 0;
}

.slide-down-leave-to {
  transform: translateY(-20px);
  opacity: 0;
}

@media (max-width: 768px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }

  .advanced-grid {
    grid-template-columns: 1fr;
  }

  .result-actions {
    flex-direction: column;
  }

  .video-generation-panel {
    padding: 16px;
  }
}
</style>