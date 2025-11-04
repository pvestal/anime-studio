<template>
  <div class="quick-controls-interface">
    <!-- Header with Mode Selector -->
    <div class="interface-header">
      <div class="header-title">
        <h2>Quick Controls</h2>
        <div class="subtitle">Essential controls with visual timeline</div>
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

    <!-- File Selection Bar -->
    <div class="file-selection-bar">
      <div class="file-selector">
        <label>Video:</label>
        <select v-model="selectedVideo" @change="loadVideo" class="file-select">
          <option value="">Choose video...</option>
          <option v-for="video in availableVideos" :key="video.path" :value="video">
            {{ video.name }}
          </option>
        </select>
        <button @click="uploadVideo" class="upload-btn">
          <i class="pi pi-upload"></i>
        </button>
      </div>

      <div class="file-selector">
        <label>Music:</label>
        <select v-model="selectedMusic" @change="loadMusic" class="file-select">
          <option value="">Choose music...</option>
          <option v-for="music in availableMusic" :key="music.path" :value="music">
            {{ music.name }}
          </option>
        </select>
        <button @click="uploadMusic" class="upload-btn">
          <i class="pi pi-upload"></i>
        </button>
      </div>

      <div class="sync-controls">
        <button
          @click="performSync"
          :disabled="!canSync || isSyncing"
          class="sync-btn"
          :class="{ syncing: isSyncing }"
        >
          <i :class="isSyncing ? 'pi pi-spin pi-spinner' : 'pi pi-play'"></i>
          {{ isSyncing ? 'Syncing...' : 'Sync Now' }}
        </button>
      </div>
    </div>

    <!-- Main Content Area -->
    <div class="main-content">
      <!-- Visual Timeline -->
      <div class="timeline-section">
        <div class="timeline-header">
          <h3>Visual Timeline</h3>
          <div class="timeline-controls">
            <button @click="playPreview" class="play-control" :disabled="!hasValidFiles">
              <i :class="isPlaying ? 'pi pi-pause' : 'pi pi-play'"></i>
            </button>
            <div class="time-display">{{ formatTime(currentTime) }} / {{ formatTime(totalDuration) }}</div>
            <button @click="resetSync" class="reset-btn" :disabled="!syncOffset">
              <i class="pi pi-refresh"></i> Reset
            </button>
          </div>
        </div>

        <div class="timeline-container" ref="timelineContainer">
          <!-- Video Track -->
          <div v-if="selectedVideo" class="timeline-track video-track">
            <div class="track-label">Video</div>
            <div class="track-content">
              <div
                v-for="(frame, index) in videoFrames"
                :key="index"
                class="video-frame"
                :style="{ left: (frame.time / totalDuration) * 100 + '%' }"
              >
                <img :src="frame.thumbnail" :alt="`Frame ${index}`" />
              </div>
              <div class="playhead" :style="{ left: (currentTime / totalDuration) * 100 + '%' }"></div>
            </div>
          </div>

          <!-- Audio Track -->
          <div v-if="selectedMusic" class="timeline-track audio-track">
            <div class="track-label">Audio</div>
            <div class="track-content">
              <canvas
                ref="waveformCanvas"
                class="waveform"
                :width="timelineWidth"
                :height="80"
                @click="seekToPosition"
              ></canvas>
              <div
                v-for="beat in beatMarkers"
                :key="beat.id"
                class="beat-marker"
                :class="{ strong: beat.strong }"
                :style="{ left: ((beat.time + syncOffset) / totalDuration) * 100 + '%' }"
              ></div>
              <div
                class="sync-handle"
                :style="{ left: (syncOffset / totalDuration) * 100 + '%' }"
                @mousedown="startSyncDrag"
                title="Drag to adjust sync"
              ></div>
            </div>
          </div>

          <!-- Sync Quality Indicator -->
          <div v-if="syncQuality" class="sync-quality">
            <div class="quality-bar">
              <div class="quality-fill" :style="{ width: syncQuality.score + '%' }"></div>
            </div>
            <span class="quality-text">{{ syncQuality.label }} ({{ syncQuality.score }}%)</span>
          </div>
        </div>
      </div>

      <!-- Quick Controls Panel -->
      <div class="controls-panel">
        <div class="control-sections">
          <!-- Style & Energy -->
          <div class="control-section">
            <h4>Style & Feel</h4>
            <div class="control-grid">
              <div class="control-group">
                <label>Music Style</label>
                <select v-model="syncSettings.style" @change="updatePreview" class="control-select">
                  <option value="epic_orchestral">Epic Orchestral</option>
                  <option value="cyberpunk_electronic">Cyberpunk Electronic</option>
                  <option value="emotional_piano">Emotional Piano</option>
                  <option value="battle_drums">Battle Drums</option>
                  <option value="mysterious_ambient">Mysterious Ambient</option>
                  <option value="japanese_traditional">Japanese Traditional</option>
                </select>
              </div>

              <div class="control-group">
                <label>Energy Level</label>
                <div class="energy-slider-container">
                  <input
                    v-model.number="syncSettings.energy"
                    @input="updatePreview"
                    type="range"
                    min="1"
                    max="5"
                    class="energy-slider"
                  >
                  <div class="energy-labels">
                    <span>Calm</span>
                    <span>Balanced</span>
                    <span>Intense</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Sync Settings -->
          <div class="control-section">
            <h4>Sync Method</h4>
            <div class="sync-methods">
              <label
                v-for="method in syncMethods"
                :key="method.id"
                class="sync-method"
                :class="{ selected: syncSettings.method === method.id }"
              >
                <input
                  type="radio"
                  :value="method.id"
                  v-model="syncSettings.method"
                  @change="updatePreview"
                >
                <div class="method-content">
                  <div class="method-icon">{{ method.icon }}</div>
                  <div class="method-info">
                    <div class="method-name">{{ method.name }}</div>
                    <div class="method-description">{{ method.description }}</div>
                  </div>
                </div>
              </label>
            </div>
          </div>

          <!-- Timing Controls -->
          <div class="control-section">
            <h4>Fine Tuning</h4>
            <div class="timing-controls">
              <div class="control-group">
                <label>BPM Override</label>
                <div class="bpm-control">
                  <input
                    v-model.number="syncSettings.bpm"
                    @input="updatePreview"
                    type="number"
                    min="60"
                    max="200"
                    class="bpm-input"
                    :disabled="syncSettings.method === 'auto'"
                  >
                  <button @click="detectBPM" class="detect-btn" :disabled="!selectedMusic">
                    <i class="pi pi-magic"></i> Auto
                  </button>
                </div>
              </div>

              <div class="control-group">
                <label>Sync Offset (ms)</label>
                <input
                  v-model.number="syncOffset"
                  @input="updateSyncPosition"
                  type="number"
                  step="10"
                  class="offset-input"
                >
              </div>
            </div>
          </div>
        </div>

        <!-- Preset Management -->
        <div class="preset-section">
          <h4>Presets</h4>
          <div class="preset-controls">
            <select v-model="selectedPreset" @change="loadPreset" class="preset-select">
              <option value="">Choose preset...</option>
              <option v-for="preset in savedPresets" :key="preset.id" :value="preset">
                {{ preset.name }}
              </option>
            </select>
            <button @click="savePreset" class="save-preset-btn" :disabled="!hasValidSettings">
              <i class="pi pi-save"></i> Save
            </button>
            <button @click="showPresetDialog = true" class="new-preset-btn">
              <i class="pi pi-plus"></i> New
            </button>
          </div>
        </div>

        <!-- Action Buttons -->
        <div class="action-buttons">
          <button @click="previewResult" class="preview-btn" :disabled="!canPreview">
            <i class="pi pi-eye"></i> Preview Result
          </button>
          <button @click="exportResult" class="export-btn" :disabled="!syncResult">
            <i class="pi pi-download"></i> Export to Jellyfin
          </button>
          <button @click="$emit('changeMode', 'professional')" class="advanced-btn">
            <i class="pi pi-cog"></i> Advanced Mode
          </button>
        </div>
      </div>
    </div>

    <!-- Results Panel -->
    <div v-if="syncResult" class="results-panel">
      <div class="result-header">
        <h3>Sync Complete</h3>
        <div class="result-stats">
          <div class="stat">
            <label>BPM:</label>
            <span>{{ syncResult.detected_bpm }}</span>
          </div>
          <div class="stat">
            <label>Quality:</label>
            <span :class="getQualityClass(syncResult.quality)">{{ syncResult.quality }}</span>
          </div>
          <div class="stat">
            <label>Duration:</label>
            <span>{{ formatTime(syncResult.duration) }}</span>
          </div>
        </div>
      </div>

      <div class="result-preview">
        <video
          ref="resultVideo"
          :src="syncResult.preview_url"
          class="preview-video"
          controls
        ></video>
      </div>
    </div>

    <!-- Preset Save Dialog -->
    <div v-if="showPresetDialog" class="preset-dialog-overlay" @click="showPresetDialog = false">
      <div class="preset-dialog" @click.stop>
        <h3>Save Preset</h3>
        <input
          v-model="newPresetName"
          placeholder="Preset name..."
          class="preset-name-input"
          @keyup.enter="saveNewPreset"
        >
        <div class="dialog-actions">
          <button @click="showPresetDialog = false" class="cancel-btn">Cancel</button>
          <button @click="saveNewPreset" class="save-btn" :disabled="!newPresetName.trim()">
            Save
          </button>
        </div>
      </div>
    </div>

    <!-- Hidden file inputs -->
    <input
      ref="videoFileInput"
      type="file"
      accept="video/*"
      @change="handleVideoUpload"
      style="display: none"
    >
    <input
      ref="musicFileInput"
      type="file"
      accept="audio/*"
      @change="handleMusicUpload"
      style="display: none"
    >
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick, watch } from 'vue'

// Props & Emits
const props = defineProps({
  currentMode: {
    type: String,
    default: 'quick'
  }
})

const emit = defineEmits(['changeMode'])

// Refs
const timelineContainer = ref(null)
const waveformCanvas = ref(null)
const resultVideo = ref(null)
const videoFileInput = ref(null)
const musicFileInput = ref(null)

// State
const selectedVideo = ref(null)
const selectedMusic = ref(null)
const currentTime = ref(0)
const totalDuration = ref(0)
const isPlaying = ref(false)
const isSyncing = ref(false)
const syncOffset = ref(0)
const timelineWidth = ref(800)
const selectedPreset = ref('')
const showPresetDialog = ref(false)
const newPresetName = ref('')
const syncResult = ref(null)

// View modes
const viewModes = [
  { id: 'smart', label: 'Smart Sync', icon: '✨' },
  { id: 'quick', label: 'Quick Controls', icon: '⚙️' },
  { id: 'professional', label: 'Professional', icon: '🎛️' }
]

// Sync settings
const syncSettings = reactive({
  style: 'epic_orchestral',
  energy: 3,
  method: 'beat_sync',
  bpm: 120
})

// Sync methods
const syncMethods = [
  {
    id: 'beat_sync',
    name: 'Beat Sync',
    description: 'Sync to musical beats',
    icon: '🥁'
  },
  {
    id: 'auto',
    name: 'Auto Sync',
    description: 'AI determines best sync',
    icon: '🤖'
  },
  {
    id: 'manual',
    name: 'Manual',
    description: 'Manual timing control',
    icon: '✋'
  },
  {
    id: 'tempo_match',
    name: 'Tempo Match',
    description: 'Match video pacing',
    icon: '⚡'
  }
]

// Sample data
const availableVideos = ref([
  { name: 'Anime Scene 1', path: '/mnt/1TB-storage/ComfyUI/output/anime_30sec_final_00006.mp4', duration: 30 },
  { name: 'Echo Video', path: '/mnt/1TB-storage/ComfyUI/output/echo_video_877c3aba_00001.mp4', duration: 25 }
])

const availableMusic = ref([
  { name: 'Epic Track 1', path: '/opt/tower-music-production/generated/epic_track_001.wav', duration: 60 },
  { name: 'Cyberpunk Beat', path: '/opt/tower-music-production/generated/cyberpunk_beat.wav', duration: 45 }
])

const videoFrames = ref([])
const beatMarkers = ref([])
const syncQuality = ref(null)

const savedPresets = ref([
  {
    id: 1,
    name: 'Action Scene',
    settings: { style: 'epic_orchestral', energy: 5, method: 'beat_sync', bpm: 140 }
  },
  {
    id: 2,
    name: 'Emotional Scene',
    settings: { style: 'emotional_piano', energy: 2, method: 'manual', bpm: 80 }
  }
])

// Computed
const canSync = computed(() => {
  return selectedVideo.value && selectedMusic.value
})

const canPreview = computed(() => {
  return canSync.value && !isSyncing.value
})

const hasValidFiles = computed(() => {
  return selectedVideo.value && selectedMusic.value
})

const hasValidSettings = computed(() => {
  return syncSettings.style && syncSettings.energy && syncSettings.method
})

// Watchers
watch([selectedVideo, selectedMusic], () => {
  if (selectedVideo.value && selectedMusic.value) {
    generateTimeline()
  }
})

watch(syncOffset, () => {
  updateSyncVisualization()
})

// Methods
const loadVideo = () => {
  if (selectedVideo.value) {
    totalDuration.value = Math.max(totalDuration.value, selectedVideo.value.duration)
    generateVideoFrames()
  }
}

const loadMusic = () => {
  if (selectedMusic.value) {
    totalDuration.value = Math.max(totalDuration.value, selectedMusic.value.duration)
    generateWaveform()
    generateBeatMarkers()
  }
}

const uploadVideo = () => {
  videoFileInput.value?.click()
}

const uploadMusic = () => {
  musicFileInput.value?.click()
}

const handleVideoUpload = (event) => {
  const file = event.target.files[0]
  if (file) {
    // Process uploaded video file
    selectedVideo.value = {
      name: file.name,
      path: URL.createObjectURL(file),
      duration: 30 // Would be detected from actual file
    }
    loadVideo()
  }
}

const handleMusicUpload = (event) => {
  const file = event.target.files[0]
  if (file) {
    // Process uploaded music file
    selectedMusic.value = {
      name: file.name,
      path: URL.createObjectURL(file),
      duration: 60 // Would be detected from actual file
    }
    loadMusic()
  }
}

const generateTimeline = () => {
  nextTick(() => {
    if (timelineContainer.value) {
      timelineWidth.value = timelineContainer.value.offsetWidth - 100
    }
    generateVideoFrames()
    generateWaveform()
    generateBeatMarkers()
  })
}

const generateVideoFrames = () => {
  if (!selectedVideo.value) return

  // Generate sample video frame thumbnails
  videoFrames.value = Array.from({ length: 10 }, (_, i) => ({
    time: (i / 9) * selectedVideo.value.duration,
    thumbnail: `data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="60" height="40" viewBox="0 0 60 40"><rect width="60" height="40" fill="%2334d399"/><text x="30" y="25" text-anchor="middle" fill="white" font-size="10">${i + 1}</text></svg>`
  }))
}

const generateWaveform = () => {
  if (!waveformCanvas.value || !selectedMusic.value) return

  const canvas = waveformCanvas.value
  const ctx = canvas.getContext('2d')

  // Clear canvas
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  // Generate sample waveform
  ctx.strokeStyle = '#00d4aa'
  ctx.lineWidth = 1
  ctx.beginPath()

  const samples = canvas.width
  for (let i = 0; i < samples; i++) {
    const amplitude = Math.random() * 0.8 + 0.1
    const y = canvas.height / 2 + (Math.sin(i * 0.02) * amplitude * canvas.height / 2)

    if (i === 0) {
      ctx.moveTo(i, y)
    } else {
      ctx.lineTo(i, y)
    }
  }

  ctx.stroke()
}

const generateBeatMarkers = () => {
  if (!selectedMusic.value) return

  const beatsPerSecond = syncSettings.bpm / 60
  const totalBeats = Math.floor(selectedMusic.value.duration * beatsPerSecond)

  beatMarkers.value = Array.from({ length: totalBeats }, (_, i) => ({
    id: i,
    time: i / beatsPerSecond,
    strong: i % 4 === 0 // Every 4th beat is strong
  }))
}

const playPreview = () => {
  isPlaying.value = !isPlaying.value
  // In real implementation, would control actual playback
}

const seekToPosition = (event) => {
  const rect = event.target.getBoundingClientRect()
  const x = event.clientX - rect.left
  const percentage = x / rect.width
  currentTime.value = percentage * totalDuration.value
}

const startSyncDrag = (event) => {
  const startX = event.clientX
  const startOffset = syncOffset.value

  const handleMouseMove = (e) => {
    const deltaX = e.clientX - startX
    const deltaTime = (deltaX / timelineWidth.value) * totalDuration.value
    syncOffset.value = Math.max(-5, Math.min(5, startOffset + deltaTime))
  }

  const handleMouseUp = () => {
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleMouseUp)
  }

  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', handleMouseUp)
}

const updatePreview = () => {
  if (hasValidFiles.value) {
    generateBeatMarkers()
    calculateSyncQuality()
  }
}

const updateSyncPosition = () => {
  updateSyncVisualization()
  calculateSyncQuality()
}

const updateSyncVisualization = () => {
  // Update beat marker positions based on sync offset
  // This would trigger reactivity for the beat markers
}

const calculateSyncQuality = () => {
  if (!hasValidFiles.value) {
    syncQuality.value = null
    return
  }

  // Simulate sync quality calculation
  const quality = Math.max(0, 100 - Math.abs(syncOffset.value) * 10)

  let label = 'Poor'
  if (quality > 80) label = 'Excellent'
  else if (quality > 60) label = 'Good'
  else if (quality > 40) label = 'Fair'

  syncQuality.value = {
    score: Math.round(quality),
    label
  }
}

const detectBPM = async () => {
  if (!selectedMusic.value) return

  // Simulate BPM detection
  const detectedBPM = Math.floor(Math.random() * 60) + 100
  syncSettings.bpm = detectedBPM
  updatePreview()
}

const resetSync = () => {
  syncOffset.value = 0
  updateSyncVisualization()
}

const performSync = async () => {
  if (!canSync.value) return

  isSyncing.value = true

  try {
    // Simulate sync process
    await new Promise(resolve => setTimeout(resolve, 3000))

    syncResult.value = {
      detected_bpm: syncSettings.bpm,
      quality: syncQuality.value?.label || 'Good',
      duration: totalDuration.value,
      preview_url: selectedVideo.value.path,
      file_path: '/tmp/synced_video.mp4'
    }
  } catch (error) {
    console.error('Sync failed:', error)
  } finally {
    isSyncing.value = false
  }
}

const previewResult = () => {
  if (!canPreview.value) return
  // Show preview of synced result
}

const exportResult = () => {
  if (!syncResult.value) return
  // Export to Jellyfin
}

const loadPreset = () => {
  if (selectedPreset.value && selectedPreset.value.settings) {
    Object.assign(syncSettings, selectedPreset.value.settings)
    updatePreview()
  }
}

const savePreset = () => {
  showPresetDialog.value = true
}

const saveNewPreset = () => {
  if (!newPresetName.value.trim()) return

  const newPreset = {
    id: Date.now(),
    name: newPresetName.value.trim(),
    settings: { ...syncSettings }
  }

  savedPresets.value.push(newPreset)
  selectedPreset.value = newPreset

  showPresetDialog.value = false
  newPresetName.value = ''
}

// Utility functions
const formatTime = (seconds) => {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

const getQualityClass = (quality) => {
  const q = quality.toLowerCase()
  if (q.includes('excellent')) return 'quality-excellent'
  if (q.includes('good')) return 'quality-good'
  if (q.includes('fair')) return 'quality-fair'
  return 'quality-poor'
}

// Lifecycle
onMounted(() => {
  generateTimeline()
})
</script>

<style scoped>
.quick-controls-interface {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  border-radius: 12px;
  padding: 20px;
  color: #f1f5f9;
  min-height: 700px;
}

.interface-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid #334155;
}

.header-title h2 {
  margin: 0;
  color: #00d4aa;
  text-shadow: 0 0 10px rgba(0, 212, 170, 0.3);
}

.subtitle {
  color: #94a3b8;
  font-size: 0.875rem;
  margin-top: 4px;
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
}

.file-selection-bar {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 20px;
  align-items: end;
  margin-bottom: 24px;
  padding: 16px;
  background: rgba(15, 23, 42, 0.3);
  border-radius: 8px;
}

.file-selector {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-selector label {
  font-weight: 600;
  color: #e2e8f0;
  font-size: 0.875rem;
}

.file-select {
  padding: 8px 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #f1f5f9;
  flex: 1;
}

.upload-btn {
  padding: 8px;
  background: #334155;
  border: 1px solid #475569;
  border-radius: 6px;
  color: #f1f5f9;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-left: 8px;
}

.upload-btn:hover {
  background: #475569;
}

.sync-btn {
  padding: 12px 24px;
  background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 8px;
}

.sync-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #6d28d9 0%, #5b21b6 100%);
  transform: translateY(-2px);
}

.sync-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.main-content {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 24px;
  min-height: 500px;
}

.timeline-section {
  background: rgba(15, 23, 42, 0.3);
  border-radius: 8px;
  padding: 20px;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.timeline-header h3 {
  margin: 0;
  color: #e2e8f0;
}

.timeline-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.play-control {
  padding: 8px;
  background: #00d4aa;
  border: none;
  border-radius: 50%;
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
}

.play-control:hover:not(:disabled) {
  background: #059669;
  transform: scale(1.1);
}

.play-control:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.time-display {
  font-family: monospace;
  color: #94a3b8;
  min-width: 80px;
}

.reset-btn {
  padding: 6px 12px;
  background: #6b7280;
  border: none;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  font-size: 0.875rem;
}

.reset-btn:hover:not(:disabled) {
  background: #4b5563;
}

.timeline-container {
  position: relative;
  background: #1e293b;
  border-radius: 8px;
  padding: 16px;
  min-height: 200px;
}

.timeline-track {
  display: flex;
  margin-bottom: 16px;
}

.track-label {
  width: 60px;
  font-size: 0.875rem;
  font-weight: 600;
  color: #94a3b8;
  display: flex;
  align-items: center;
}

.track-content {
  flex: 1;
  position: relative;
  height: 60px;
  background: #0f172a;
  border-radius: 4px;
  margin-left: 12px;
}

.video-frame {
  position: absolute;
  top: 4px;
  width: 60px;
  height: 40px;
}

.video-frame img {
  width: 100%;
  height: 100%;
  border-radius: 2px;
  object-fit: cover;
}

.waveform {
  width: 100%;
  height: 100%;
  cursor: pointer;
}

.beat-marker {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: rgba(0, 212, 170, 0.4);
  pointer-events: none;
}

.beat-marker.strong {
  width: 2px;
  background: rgba(0, 212, 170, 0.8);
}

.sync-handle {
  position: absolute;
  top: -4px;
  bottom: -4px;
  width: 3px;
  background: #f59e0b;
  cursor: ew-resize;
  border-radius: 2px;
}

.sync-handle:hover {
  background: #d97706;
  box-shadow: 0 0 8px rgba(245, 158, 11, 0.5);
}

.playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #ef4444;
  pointer-events: none;
  z-index: 10;
}

.sync-quality {
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(15, 23, 42, 0.5);
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.quality-bar {
  flex: 1;
  height: 6px;
  background: #334155;
  border-radius: 3px;
  overflow: hidden;
}

.quality-fill {
  height: 100%;
  background: linear-gradient(90deg, #ef4444 0%, #f59e0b 50%, #22c55e 100%);
  transition: width 0.3s ease;
}

.quality-text {
  font-size: 0.875rem;
  font-weight: 600;
  color: #94a3b8;
}

.controls-panel {
  background: rgba(15, 23, 42, 0.3);
  border-radius: 8px;
  padding: 20px;
  overflow-y: auto;
}

.control-sections {
  display: flex;
  flex-direction: column;
  gap: 24px;
  margin-bottom: 24px;
}

.control-section h4 {
  margin: 0 0 12px 0;
  color: #00d4aa;
  font-size: 1rem;
}

.control-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.control-group label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #e2e8f0;
}

.control-select {
  padding: 8px 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #f1f5f9;
}

.energy-slider-container {
  position: relative;
}

.energy-slider {
  width: 100%;
  height: 6px;
  background: #334155;
  border-radius: 3px;
  outline: none;
  appearance: none;
}

.energy-slider::-webkit-slider-thumb {
  appearance: none;
  width: 18px;
  height: 18px;
  background: #00d4aa;
  border-radius: 50%;
  cursor: pointer;
}

.energy-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 0.75rem;
  color: #64748b;
}

.sync-methods {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sync-method {
  display: flex;
  align-items: center;
  padding: 12px;
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid #334155;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.sync-method:hover {
  border-color: #00d4aa;
}

.sync-method.selected {
  border-color: #00d4aa;
  background: rgba(0, 212, 170, 0.1);
}

.sync-method input {
  margin-right: 12px;
}

.method-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.method-icon {
  font-size: 1.25rem;
}

.method-name {
  font-weight: 600;
  color: #e2e8f0;
}

.method-description {
  font-size: 0.875rem;
  color: #94a3b8;
}

.timing-controls {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.bpm-control {
  display: flex;
  gap: 8px;
}

.bpm-input, .offset-input {
  flex: 1;
  padding: 8px 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #f1f5f9;
}

.detect-btn {
  padding: 8px 12px;
  background: #7c3aed;
  border: none;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  font-size: 0.875rem;
}

.detect-btn:hover:not(:disabled) {
  background: #6d28d9;
}

.preset-section {
  padding-top: 20px;
  border-top: 1px solid #334155;
  margin-bottom: 20px;
}

.preset-section h4 {
  margin: 0 0 12px 0;
  color: #00d4aa;
}

.preset-controls {
  display: flex;
  gap: 8px;
}

.preset-select {
  flex: 1;
  padding: 8px 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #f1f5f9;
}

.save-preset-btn, .new-preset-btn {
  padding: 8px 12px;
  background: #059669;
  border: none;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  font-size: 0.875rem;
}

.save-preset-btn:hover:not(:disabled), .new-preset-btn:hover {
  background: #047857;
}

.action-buttons {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preview-btn, .export-btn, .advanced-btn {
  padding: 10px 16px;
  border: none;
  border-radius: 6px;
  color: white;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
}

.preview-btn {
  background: linear-gradient(135deg, #059669 0%, #047857 100%);
}

.export-btn {
  background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
}

.advanced-btn {
  background: linear-gradient(135deg, #6b7280 0%, #4b5563 100%);
}

.preview-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #047857 0%, #065f46 100%);
}

.export-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #b91c1c 0%, #991b1b 100%);
}

.advanced-btn:hover {
  background: linear-gradient(135deg, #4b5563 0%, #374151 100%);
}

.results-panel {
  grid-column: 1 / -1;
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid #22c55e;
  border-radius: 8px;
  padding: 20px;
  margin-top: 24px;
}

.result-header {
  text-align: center;
  margin-bottom: 20px;
}

.result-header h3 {
  color: #22c55e;
  margin-bottom: 12px;
}

.result-stats {
  display: flex;
  justify-content: center;
  gap: 24px;
  flex-wrap: wrap;
}

.stat {
  display: flex;
  gap: 8px;
  padding: 6px 12px;
  background: rgba(34, 197, 94, 0.2);
  border-radius: 6px;
  font-size: 0.875rem;
}

.stat label {
  color: #94a3b8;
  font-weight: 600;
}

.stat span {
  color: #22c55e;
  font-weight: 600;
}

.quality-excellent { color: #22c55e; }
.quality-good { color: #00d4aa; }
.quality-fair { color: #f59e0b; }
.quality-poor { color: #ef4444; }

.preview-video {
  width: 100%;
  max-width: 500px;
  border-radius: 8px;
  margin: 0 auto;
  display: block;
}

.preset-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.preset-dialog {
  background: #1e293b;
  border-radius: 8px;
  padding: 24px;
  min-width: 300px;
}

.preset-dialog h3 {
  margin: 0 0 16px 0;
  color: #e2e8f0;
}

.preset-name-input {
  width: 100%;
  padding: 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #f1f5f9;
  margin-bottom: 16px;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.cancel-btn, .save-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
}

.cancel-btn {
  background: #6b7280;
  color: white;
}

.save-btn {
  background: #059669;
  color: white;
}

.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Responsive Design */
@media (max-width: 1024px) {
  .main-content {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .file-selection-bar {
    grid-template-columns: 1fr;
    gap: 12px;
  }
}

@media (max-width: 768px) {
  .interface-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .timeline-controls {
    flex-wrap: wrap;
    gap: 8px;
  }

  .preset-controls {
    flex-direction: column;
  }

  .result-stats {
    flex-direction: column;
    gap: 8px;
  }
}
</style>