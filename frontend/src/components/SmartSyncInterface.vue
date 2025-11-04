<template>
  <div class="smart-sync-interface">
    <!-- Header with Mode Selector -->
    <div class="interface-header">
      <div class="header-title">
        <h2>Music + Video Sync Studio</h2>
        <div class="service-status" :class="serviceStatus">
          <div class="status-indicator"></div>
          <span>{{ serviceStatusText }}</span>
        </div>
      </div>

      <div class="view-mode-selector">
        <button
          v-for="mode in viewModes"
          :key="mode.id"
          @click="$emit('changeMode', mode.id)"
          class="mode-btn"
          :class="{ active: currentMode === mode.id }"
        >
          {{ mode.icon }} {{ mode.label }}
        </button>
      </div>
    </div>

    <!-- Main Smart Sync Interface -->
    <div class="smart-sync-content">
      <!-- Template Quick Select -->
      <div class="template-selector">
        <h3>Choose Your Scene Type</h3>
        <div class="template-grid">
          <div
            v-for="template in templates"
            :key="template.id"
            @click="selectTemplate(template)"
            class="template-card"
            :class="{ selected: selectedTemplate?.id === template.id }"
          >
            <div class="template-icon">{{ template.icon }}</div>
            <div class="template-name">{{ template.name }}</div>
            <div class="template-description">{{ template.description }}</div>
          </div>
        </div>
      </div>

      <!-- Drag & Drop Zone -->
      <div class="drop-zone-container">
        <div class="drop-zones">
          <!-- Video Drop Zone -->
          <div
            class="drop-zone video-zone"
            :class="{ 'drag-over': isDragOverVideo, 'has-file': selectedVideo }"
            @dragover.prevent="isDragOverVideo = true"
            @dragleave.prevent="isDragOverVideo = false"
            @drop.prevent="handleVideoDrop"
            @click="triggerVideoUpload"
          >
            <input
              ref="videoInput"
              type="file"
              accept="video/*"
              @change="handleVideoSelect"
              style="display: none"
            >
            <div v-if="!selectedVideo" class="drop-content">
              <i class="pi pi-video drop-icon"></i>
              <div class="drop-text">
                <div class="drop-title">Drop your video here</div>
                <div class="drop-subtitle">or click to browse</div>
              </div>
            </div>
            <div v-else class="file-preview">
              <video :src="selectedVideo.url" class="video-preview" muted></video>
              <div class="file-info">
                <div class="file-name">{{ selectedVideo.name }}</div>
                <div class="file-details">{{ formatDuration(selectedVideo.duration) }} • {{ formatFileSize(selectedVideo.size) }}</div>
              </div>
              <button @click.stop="removeVideo" class="remove-btn">
                <i class="pi pi-times"></i>
              </button>
            </div>
          </div>

          <div class="sync-arrow">
            <i class="pi pi-arrow-right"></i>
            <span>Smart Sync</span>
          </div>

          <!-- Music Drop Zone -->
          <div
            class="drop-zone music-zone"
            :class="{ 'drag-over': isDragOverMusic, 'has-file': selectedMusic, 'auto-selected': autoSelectedMusic }"
            @dragover.prevent="isDragOverMusic = true"
            @dragleave.prevent="isDragOverMusic = false"
            @drop.prevent="handleMusicDrop"
            @click="triggerMusicUpload"
          >
            <input
              ref="musicInput"
              type="file"
              accept="audio/*"
              @change="handleMusicSelect"
              style="display: none"
            >
            <div v-if="!selectedMusic && !autoSelectedMusic" class="drop-content">
              <i class="pi pi-music drop-icon"></i>
              <div class="drop-text">
                <div class="drop-title">Drop music here</div>
                <div class="drop-subtitle">or let AI choose</div>
              </div>
            </div>
            <div v-else-if="autoSelectedMusic" class="auto-selection">
              <i class="pi pi-magic drop-icon"></i>
              <div class="auto-text">
                <div class="auto-title">AI will select perfect music</div>
                <div class="auto-subtitle">based on your {{ selectedTemplate?.name || 'scene' }}</div>
              </div>
              <button @click.stop="triggerMusicUpload" class="browse-btn">
                <i class="pi pi-folder-open"></i> Browse Instead
              </button>
            </div>
            <div v-else class="file-preview">
              <div class="audio-preview">
                <i class="pi pi-music"></i>
                <button @click.stop="playMusic" class="play-btn">
                  <i :class="isPlaying ? 'pi pi-pause' : 'pi pi-play'"></i>
                </button>
              </div>
              <div class="file-info">
                <div class="file-name">{{ selectedMusic.name }}</div>
                <div class="file-details">{{ formatDuration(selectedMusic.duration) }} • {{ formatFileSize(selectedMusic.size) }}</div>
              </div>
              <button @click.stop="removeMusic" class="remove-btn">
                <i class="pi pi-times"></i>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Smart Sync Button -->
      <div class="sync-action">
        <button
          @click="performSmartSync"
          :disabled="!canSync || isSyncing"
          class="smart-sync-btn"
          :class="{ pulsing: canSync && !isSyncing }"
        >
          <i :class="isSyncing ? 'pi pi-spin pi-spinner' : 'pi pi-magic'"></i>
          <span v-if="isSyncing">{{ syncStatus }}</span>
          <span v-else>{{ smartSyncButtonText }}</span>
        </button>

        <div v-if="canSync && !isSyncing" class="sync-description">
          AI will analyze your {{ selectedTemplate?.name || 'video' }} and create perfect sync
        </div>
      </div>

      <!-- Progress Indicator -->
      <div v-if="isSyncing" class="sync-progress">
        <div class="progress-steps">
          <div v-for="step in syncSteps" :key="step.id" class="progress-step" :class="step.status">
            <div class="step-icon">
              <i v-if="step.status === 'pending'" class="pi pi-circle"></i>
              <i v-else-if="step.status === 'active'" class="pi pi-spin pi-spinner"></i>
              <i v-else class="pi pi-check"></i>
            </div>
            <div class="step-label">{{ step.label }}</div>
          </div>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: syncProgress + '%' }"></div>
        </div>
        <div class="progress-text">{{ syncProgress }}% complete</div>
      </div>

      <!-- Results Preview -->
      <div v-if="syncResult" class="sync-result">
        <div class="result-header">
          <h3>✨ Sync Complete!</h3>
          <div class="result-stats">
            <span class="stat">{{ syncResult.bpm }} BPM detected</span>
            <span class="stat">{{ syncResult.sync_quality }} sync quality</span>
            <span class="stat">{{ formatDuration(syncResult.duration) }} duration</span>
          </div>
        </div>

        <div class="result-preview">
          <video
            :src="syncResult.preview_url"
            class="result-video"
            controls
            autoplay
            muted
          ></video>
        </div>

        <div class="result-actions">
          <button @click="exportToJellyfin" class="export-btn primary">
            <i class="pi pi-download"></i> Export to Jellyfin
          </button>
          <button @click="tryDifferentMusic" class="try-different-btn">
            <i class="pi pi-refresh"></i> Try Different Music
          </button>
          <button @click="showAdvancedControls" class="advanced-btn">
            <i class="pi pi-cog"></i> Fine-tune
          </button>
        </div>
      </div>

      <!-- Help & Tips -->
      <div v-if="!selectedVideo && !selectedMusic" class="help-section">
        <div class="help-card">
          <h4>🎬 Quick Start Guide</h4>
          <ol>
            <li>Choose your scene type above</li>
            <li>Drop your video file</li>
            <li>Let AI select music or drop your own</li>
            <li>Click "Smart Sync" and watch the magic!</li>
          </ol>
        </div>

        <div class="tips-card">
          <h4>💡 Pro Tips</h4>
          <ul>
            <li><strong>Action scenes:</strong> Work best with high-energy music</li>
            <li><strong>Emotional scenes:</strong> Slower music syncs to dialogue</li>
            <li><strong>Custom music:</strong> Upload your own for unique results</li>
            <li><strong>Need control?</strong> Switch to Quick Controls mode</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'

// Props & Emits
const props = defineProps({
  currentMode: {
    type: String,
    default: 'smart'
  }
})

const emit = defineEmits(['changeMode'])

// State
const serviceStatus = ref('connected')
const selectedTemplate = ref(null)
const selectedVideo = ref(null)
const selectedMusic = ref(null)
const autoSelectedMusic = ref(false)
const isDragOverVideo = ref(false)
const isDragOverMusic = ref(false)
const isSyncing = ref(false)
const isPlaying = ref(false)
const syncProgress = ref(0)
const syncStatus = ref('')
const syncResult = ref(null)

// Refs
const videoInput = ref(null)
const musicInput = ref(null)

// View modes for mode selector
const viewModes = [
  { id: 'smart', label: 'Smart Sync', icon: '✨' },
  { id: 'quick', label: 'Quick Controls', icon: '⚙️' },
  { id: 'professional', label: 'Professional', icon: '🎛️' }
]

// Templates for different anime scenarios
const templates = ref([
  {
    id: 'action',
    name: 'Action Scene',
    description: 'High-energy music synced to fast cuts',
    icon: '⚔️',
    settings: {
      energy: 'high',
      syncType: 'beat_sync',
      style: 'epic_orchestral',
      bpm: 140
    }
  },
  {
    id: 'emotional',
    name: 'Emotional Scene',
    description: 'Gentle music that follows dialogue',
    icon: '💝',
    settings: {
      energy: 'low',
      syncType: 'manual_sync',
      style: 'emotional_piano',
      bpm: 80
    }
  },
  {
    id: 'cyberpunk',
    name: 'Cyberpunk',
    description: 'Electronic beats for futuristic scenes',
    icon: '🌃',
    settings: {
      energy: 'high',
      syncType: 'tempo_match',
      style: 'cyberpunk_electronic',
      bpm: 120
    }
  },
  {
    id: 'battle',
    name: 'Epic Battle',
    description: 'Orchestral power for fight scenes',
    icon: '⚡',
    settings: {
      energy: 'extreme',
      syncType: 'beat_sync',
      style: 'battle_drums',
      bpm: 160
    }
  },
  {
    id: 'mysterious',
    name: 'Mysterious',
    description: 'Ambient sounds for suspense',
    icon: '🌙',
    settings: {
      energy: 'low',
      syncType: 'auto_sync',
      style: 'mysterious_ambient',
      bpm: 90
    }
  },
  {
    id: 'traditional',
    name: 'Japanese Traditional',
    description: 'Cultural music for authentic scenes',
    icon: '🏮',
    settings: {
      energy: 'medium',
      syncType: 'manual_sync',
      style: 'japanese_traditional',
      bpm: 100
    }
  }
])

// Sync process steps
const syncSteps = ref([
  { id: 'analyze', label: 'Analyzing video', status: 'pending' },
  { id: 'music', label: 'Selecting music', status: 'pending' },
  { id: 'sync', label: 'Syncing audio', status: 'pending' },
  { id: 'render', label: 'Rendering result', status: 'pending' }
])

// Computed
const serviceStatusText = computed(() => {
  const statuses = {
    connected: 'Ready to sync',
    connecting: 'Connecting...',
    disconnected: 'Service unavailable'
  }
  return statuses[serviceStatus.value] || 'Unknown'
})

const canSync = computed(() => {
  return selectedVideo.value && (selectedMusic.value || autoSelectedMusic.value) && selectedTemplate.value
})

const smartSyncButtonText = computed(() => {
  if (!selectedTemplate.value) return 'Choose scene type first'
  if (!selectedVideo.value) return 'Add video to continue'
  if (!selectedMusic.value && !autoSelectedMusic.value) return 'Add music or let AI choose'
  return `✨ Create ${selectedTemplate.value.name} Sync`
})

// Watchers
watch(selectedTemplate, (newTemplate) => {
  if (newTemplate && selectedVideo.value && !selectedMusic.value) {
    autoSelectedMusic.value = true
  }
})

// Methods
const selectTemplate = (template) => {
  selectedTemplate.value = template
  if (selectedVideo.value && !selectedMusic.value) {
    autoSelectedMusic.value = true
  }
}

const triggerVideoUpload = () => {
  videoInput.value?.click()
}

const triggerMusicUpload = () => {
  autoSelectedMusic.value = false
  musicInput.value?.click()
}

const handleVideoDrop = (event) => {
  isDragOverVideo.value = false
  const files = event.dataTransfer.files
  if (files.length > 0 && files[0].type.startsWith('video/')) {
    processVideoFile(files[0])
  }
}

const handleVideoSelect = (event) => {
  const file = event.target.files[0]
  if (file) {
    processVideoFile(file)
  }
}

const processVideoFile = (file) => {
  const url = URL.createObjectURL(file)
  const video = document.createElement('video')

  video.onloadedmetadata = () => {
    selectedVideo.value = {
      file,
      name: file.name,
      size: file.size,
      duration: video.duration,
      url
    }

    // Auto-enable AI music selection if template is selected
    if (selectedTemplate.value && !selectedMusic.value) {
      autoSelectedMusic.value = true
    }
  }

  video.src = url
}

const handleMusicDrop = (event) => {
  isDragOverMusic.value = false
  autoSelectedMusic.value = false
  const files = event.dataTransfer.files
  if (files.length > 0 && files[0].type.startsWith('audio/')) {
    processMusicFile(files[0])
  }
}

const handleMusicSelect = (event) => {
  const file = event.target.files[0]
  if (file) {
    autoSelectedMusic.value = false
    processMusicFile(file)
  }
}

const processMusicFile = (file) => {
  const url = URL.createObjectURL(file)
  const audio = document.createElement('audio')

  audio.onloadedmetadata = () => {
    selectedMusic.value = {
      file,
      name: file.name,
      size: file.size,
      duration: audio.duration,
      url
    }
  }

  audio.src = url
}

const removeVideo = () => {
  if (selectedVideo.value?.url) {
    URL.revokeObjectURL(selectedVideo.value.url)
  }
  selectedVideo.value = null
  autoSelectedMusic.value = false
}

const removeMusic = () => {
  if (selectedMusic.value?.url) {
    URL.revokeObjectURL(selectedMusic.value.url)
  }
  selectedMusic.value = null
  autoSelectedMusic.value = false
}

const playMusic = () => {
  // Toggle play/pause for music preview
  isPlaying.value = !isPlaying.value
  // In real implementation, would control audio playback
}

const performSmartSync = async () => {
  if (!canSync.value) return

  isSyncing.value = true
  syncProgress.value = 0
  syncResult.value = null

  // Reset steps
  syncSteps.value.forEach(step => step.status = 'pending')

  try {
    // Step 1: Analyze video
    syncSteps.value[0].status = 'active'
    syncStatus.value = 'Analyzing video content...'
    await new Promise(resolve => setTimeout(resolve, 2000))
    syncSteps.value[0].status = 'complete'
    syncProgress.value = 25

    // Step 2: Select/analyze music
    syncSteps.value[1].status = 'active'
    if (autoSelectedMusic.value) {
      syncStatus.value = 'AI selecting perfect music...'
    } else {
      syncStatus.value = 'Analyzing music...'
    }
    await new Promise(resolve => setTimeout(resolve, 2000))
    syncSteps.value[1].status = 'complete'
    syncProgress.value = 50

    // Step 3: Sync audio
    syncSteps.value[2].status = 'active'
    syncStatus.value = 'Creating perfect sync...'
    await new Promise(resolve => setTimeout(resolve, 3000))
    syncSteps.value[2].status = 'complete'
    syncProgress.value = 75

    // Step 4: Render
    syncSteps.value[3].status = 'active'
    syncStatus.value = 'Rendering final video...'
    await new Promise(resolve => setTimeout(resolve, 2000))
    syncSteps.value[3].status = 'complete'
    syncProgress.value = 100

    // Simulate result
    syncResult.value = {
      preview_url: selectedVideo.value.url, // In real implementation, this would be the synced video
      bpm: selectedTemplate.value.settings.bpm,
      sync_quality: 'Excellent',
      duration: selectedVideo.value.duration,
      file_path: '/tmp/synced_video.mp4'
    }

  } catch (error) {
    console.error('Smart sync failed:', error)
    syncStatus.value = 'Sync failed - please try again'
  } finally {
    isSyncing.value = false
  }
}

const exportToJellyfin = async () => {
  // Export to Jellyfin library
  console.log('Exporting to Jellyfin...')
}

const tryDifferentMusic = () => {
  selectedMusic.value = null
  autoSelectedMusic.value = true
  syncResult.value = null
  // Trigger new music selection
}

const showAdvancedControls = () => {
  emit('changeMode', 'quick')
}

// Utility functions
const formatDuration = (seconds) => {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

const formatFileSize = (bytes) => {
  const mb = bytes / (1024 * 1024)
  return `${mb.toFixed(1)} MB`
}

// Lifecycle
onMounted(() => {
  // Check service status
  // In real implementation, check actual service health
})
</script>

<style scoped>
.smart-sync-interface {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  border-radius: 12px;
  padding: 24px;
  color: #f1f5f9;
  min-height: 600px;
}

.interface-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding-bottom: 20px;
  border-bottom: 1px solid #334155;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-title h2 {
  margin: 0;
  color: #00d4aa;
  text-shadow: 0 0 10px rgba(0, 212, 170, 0.3);
  font-size: 1.75rem;
}

.service-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 0.875rem;
  background: rgba(15, 23, 42, 0.5);
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
}

.view-mode-selector {
  display: flex;
  gap: 4px;
  background: rgba(15, 23, 42, 0.5);
  border-radius: 8px;
  padding: 4px;
}

.mode-btn {
  padding: 8px 16px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s ease;
  font-weight: 500;
  font-size: 0.875rem;
}

.mode-btn:hover {
  color: #e2e8f0;
  background: rgba(51, 65, 85, 0.3);
}

.mode-btn.active {
  background: linear-gradient(135deg, #00d4aa 0%, #059669 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(0, 212, 170, 0.2);
}

.template-selector {
  margin-bottom: 32px;
}

.template-selector h3 {
  color: #e2e8f0;
  margin-bottom: 16px;
  text-align: center;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  max-width: 1000px;
  margin: 0 auto;
}

.template-card {
  background: rgba(15, 23, 42, 0.5);
  border: 2px solid #334155;
  border-radius: 12px;
  padding: 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.template-card:hover {
  border-color: #00d4aa;
  transform: translateY(-2px);
}

.template-card.selected {
  border-color: #00d4aa;
  background: rgba(0, 212, 170, 0.1);
  box-shadow: 0 8px 25px rgba(0, 212, 170, 0.2);
}

.template-icon {
  font-size: 2rem;
  margin-bottom: 8px;
}

.template-name {
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 4px;
}

.template-description {
  font-size: 0.75rem;
  color: #94a3b8;
  line-height: 1.4;
}

.drop-zone-container {
  margin-bottom: 32px;
}

.drop-zones {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 24px;
  align-items: center;
  max-width: 800px;
  margin: 0 auto;
}

.drop-zone {
  border: 3px dashed #475569;
  border-radius: 16px;
  padding: 32px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  min-height: 200px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  position: relative;
}

.drop-zone:hover {
  border-color: #00d4aa;
  background: rgba(0, 212, 170, 0.05);
}

.drop-zone.drag-over {
  border-color: #00d4aa;
  background: rgba(0, 212, 170, 0.1);
  transform: scale(1.02);
}

.drop-zone.has-file {
  border-color: #22c55e;
  background: rgba(34, 197, 94, 0.1);
}

.drop-zone.auto-selected {
  border-color: #7c3aed;
  background: rgba(124, 58, 237, 0.1);
}

.drop-icon {
  font-size: 3rem;
  color: #64748b;
  margin-bottom: 16px;
}

.drop-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 4px;
}

.drop-subtitle {
  color: #94a3b8;
  font-size: 0.875rem;
}

.sync-arrow {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #00d4aa;
  font-weight: 600;
}

.sync-arrow i {
  font-size: 1.5rem;
}

.file-preview {
  width: 100%;
  text-align: center;
}

.video-preview {
  width: 100%;
  max-width: 200px;
  border-radius: 8px;
  margin-bottom: 12px;
}

.audio-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-bottom: 12px;
}

.audio-preview i {
  font-size: 2rem;
  color: #00d4aa;
}

.play-btn {
  padding: 12px;
  background: #00d4aa;
  border: none;
  border-radius: 50%;
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
}

.play-btn:hover {
  background: #059669;
  transform: scale(1.1);
}

.file-info {
  margin-bottom: 8px;
}

.file-name {
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 4px;
  word-break: break-word;
}

.file-details {
  font-size: 0.875rem;
  color: #94a3b8;
}

.remove-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  padding: 6px;
  background: #ef4444;
  border: none;
  border-radius: 50%;
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
}

.remove-btn:hover {
  background: #dc2626;
  transform: scale(1.1);
}

.auto-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #7c3aed;
  margin-bottom: 4px;
}

.auto-subtitle {
  color: #a78bfa;
  font-size: 0.875rem;
  margin-bottom: 16px;
}

.browse-btn {
  padding: 8px 16px;
  background: rgba(124, 58, 237, 0.2);
  border: 1px solid #7c3aed;
  border-radius: 6px;
  color: #a78bfa;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 0.875rem;
}

.browse-btn:hover {
  background: rgba(124, 58, 237, 0.3);
  color: #c4b5fd;
}

.sync-action {
  text-align: center;
  margin-bottom: 32px;
}

.smart-sync-btn {
  padding: 16px 32px;
  background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
  border: none;
  border-radius: 12px;
  color: white;
  font-size: 1.25rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  display: inline-flex;
  align-items: center;
  gap: 12px;
  min-width: 250px;
  justify-content: center;
}

.smart-sync-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #6d28d9 0%, #5b21b6 100%);
  transform: translateY(-2px);
  box-shadow: 0 12px 30px rgba(124, 58, 237, 0.3);
}

.smart-sync-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.smart-sync-btn.pulsing {
  animation: pulse-glow 2s infinite;
}

.sync-description {
  margin-top: 12px;
  color: #94a3b8;
  font-size: 0.875rem;
}

.sync-progress {
  background: rgba(15, 23, 42, 0.5);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 32px;
}

.progress-steps {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.progress-step {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  transition: all 0.2s ease;
}

.progress-step.pending {
  color: #64748b;
}

.progress-step.active {
  background: rgba(124, 58, 237, 0.1);
  color: #7c3aed;
}

.progress-step.complete {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
}

.step-icon {
  font-size: 1.25rem;
}

.progress-bar {
  height: 8px;
  background: #334155;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 12px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #7c3aed, #00d4aa);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-text {
  text-align: center;
  color: #94a3b8;
  font-weight: 600;
}

.sync-result {
  background: rgba(34, 197, 94, 0.1);
  border: 2px solid #22c55e;
  border-radius: 12px;
  padding: 24px;
  text-align: center;
}

.result-header h3 {
  color: #22c55e;
  margin-bottom: 12px;
  font-size: 1.5rem;
}

.result-stats {
  display: flex;
  justify-content: center;
  gap: 24px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.stat {
  padding: 6px 12px;
  background: rgba(34, 197, 94, 0.2);
  border-radius: 20px;
  color: #22c55e;
  font-size: 0.875rem;
  font-weight: 600;
}

.result-video {
  width: 100%;
  max-width: 500px;
  border-radius: 8px;
  margin-bottom: 24px;
}

.result-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.export-btn, .try-different-btn, .advanced-btn {
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 8px;
}

.export-btn.primary {
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
  color: white;
}

.export-btn.primary:hover {
  background: linear-gradient(135deg, #16a34a 0%, #15803d 100%);
  transform: translateY(-2px);
}

.try-different-btn {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
  color: white;
}

.try-different-btn:hover {
  background: linear-gradient(135deg, #d97706 0%, #b45309 100%);
}

.advanced-btn {
  background: linear-gradient(135deg, #6b7280 0%, #4b5563 100%);
  color: white;
}

.advanced-btn:hover {
  background: linear-gradient(135deg, #4b5563 0%, #374151 100%);
}

.help-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-top: 32px;
}

.help-card, .tips-card {
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 20px;
}

.help-card h4, .tips-card h4 {
  color: #00d4aa;
  margin-bottom: 16px;
  font-size: 1.1rem;
}

.help-card ol {
  margin: 0;
  padding-left: 20px;
  color: #e2e8f0;
}

.help-card li {
  margin-bottom: 8px;
  line-height: 1.5;
}

.tips-card ul {
  margin: 0;
  padding-left: 20px;
  color: #e2e8f0;
}

.tips-card li {
  margin-bottom: 8px;
  line-height: 1.5;
}

.tips-card strong {
  color: #00d4aa;
}

/* Responsive Design */
@media (max-width: 768px) {
  .interface-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .template-grid {
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  }

  .drop-zones {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .sync-arrow {
    transform: rotate(90deg);
  }

  .progress-steps {
    grid-template-columns: 1fr;
  }

  .result-stats {
    flex-direction: column;
    gap: 8px;
  }

  .result-actions {
    flex-direction: column;
  }

  .help-section {
    grid-template-columns: 1fr;
  }
}

@keyframes pulse-glow {
  0%, 100% {
    box-shadow: 0 4px 12px rgba(124, 58, 237, 0.3);
  }
  50% {
    box-shadow: 0 8px 25px rgba(124, 58, 237, 0.5);
  }
}
</style>