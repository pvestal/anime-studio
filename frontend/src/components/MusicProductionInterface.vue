<template>
  <div class="music-production-interface">
    <!-- Header with Service Status -->
    <div class="interface-header">
      <div class="header-title">
        <h2>Music Production Studio</h2>
        <div class="service-status" :class="serviceStatus">
          <div class="status-indicator"></div>
          <span>{{ serviceStatusText }}</span>
        </div>
      </div>

      <div class="header-actions">
        <button @click="refreshServices" class="refresh-btn">
          <i class="pi pi-refresh"></i> Refresh
        </button>
        <button @click="toggleCompactMode" class="compact-btn" :class="{ active: compactMode }">
          <i class="pi pi-window-minimize"></i> Compact
        </button>
      </div>
    </div>

    <!-- Service Integration Tabs -->
    <div class="service-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        @click="activeTab = tab.id"
        class="tab-button"
        :class="{ active: activeTab === tab.id }"
      >
        {{ tab.icon }} {{ tab.label }}
      </button>
    </div>

    <!-- AI Music Generation Tab -->
    <div v-show="activeTab === 'generation'" class="tab-content generation-tab">
      <div class="generation-controls">
        <div class="control-grid">
          <div class="control-group">
            <label>Music Style</label>
            <select v-model="generationParams.style" class="style-select">
              <option value="epic_orchestral">Epic Orchestral</option>
              <option value="cyberpunk_electronic">Cyberpunk Electronic</option>
              <option value="emotional_piano">Emotional Piano</option>
              <option value="battle_drums">Battle Drums</option>
              <option value="mysterious_ambient">Mysterious Ambient</option>
              <option value="japanese_traditional">Japanese Traditional</option>
              <option value="synthwave">Synthwave</option>
            </select>
          </div>

          <div class="control-group">
            <label>Duration (seconds)</label>
            <input
              v-model.number="generationParams.duration"
              type="range"
              min="5"
              max="300"
              class="duration-slider"
            >
            <span class="duration-display">{{ generationParams.duration }}s</span>
          </div>

          <div class="control-group">
            <label>Target BPM</label>
            <input
              v-model.number="generationParams.bpm"
              type="range"
              min="60"
              max="180"
              class="bpm-slider"
            >
            <span class="bpm-display">{{ generationParams.bpm }}</span>
          </div>

          <div class="control-group">
            <label>Energy Level</label>
            <select v-model="generationParams.energy" class="energy-select">
              <option value="low">Low (Calm)</option>
              <option value="medium">Medium (Balanced)</option>
              <option value="high">High (Intense)</option>
              <option value="extreme">Extreme (Epic)</option>
            </select>
          </div>
        </div>

        <div class="generation-actions">
          <button
            @click="generateMusic"
            :disabled="isGenerating"
            class="generate-btn primary"
          >
            <i :class="isGenerating ? 'pi pi-spin pi-spinner' : 'pi pi-play'"></i>
            {{ isGenerating ? 'Generating...' : 'Generate Music' }}
          </button>

          <button @click="previewGeneration" :disabled="!lastGenerated" class="preview-btn">
            <i class="pi pi-volume-up"></i> Preview
          </button>
        </div>
      </div>

      <!-- Generation Progress -->
      <div v-if="isGenerating" class="generation-progress">
        <div class="progress-header">
          <span>Generating {{ generationParams.style.replace('_', ' ') }}...</span>
          <span>{{ Math.round(generationProgress) }}%</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: generationProgress + '%' }"></div>
        </div>
        <div class="progress-status">{{ generationStatus }}</div>
      </div>

      <!-- Generated Tracks -->
      <div v-if="generatedTracks.length > 0" class="generated-tracks">
        <h3>Generated Tracks</h3>
        <div class="tracks-grid">
          <div
            v-for="track in generatedTracks"
            :key="track.id"
            class="track-item"
            :class="{ selected: selectedTrack?.id === track.id }"
            @click="selectTrack(track)"
          >
            <div class="track-header">
              <span class="track-name">{{ track.name }}</span>
              <div class="track-actions">
                <button @click="playTrack(track)" class="play-btn">
                  <i :class="isPlaying && currentTrack?.id === track.id ? 'pi pi-pause' : 'pi pi-play'"></i>
                </button>
                <button @click="downloadTrack(track)" class="download-btn">
                  <i class="pi pi-download"></i>
                </button>
              </div>
            </div>
            <div class="track-info">
              <div class="track-bpm">{{ track.bpm }} BPM</div>
              <div class="track-duration">{{ formatDuration(track.duration) }}</div>
              <div class="track-size">{{ formatFileSize(track.size) }}</div>
            </div>
            <div class="track-waveform">
              <canvas
                :ref="'waveform-' + track.id"
                class="mini-waveform"
                :width="200"
                :height="40"
              ></canvas>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- BPM Analysis Tab -->
    <div v-show="activeTab === 'analysis'" class="tab-content analysis-tab">
      <div class="analysis-controls">
        <div class="file-upload">
          <label for="audio-upload" class="upload-label">
            <i class="pi pi-upload"></i> Upload Audio File
          </label>
          <input
            id="audio-upload"
            type="file"
            accept="audio/*"
            @change="handleFileUpload"
            class="upload-input"
          >
        </div>

        <div class="analysis-options">
          <label>
            <input type="checkbox" v-model="analysisOptions.detectKey">
            Detect Musical Key
          </label>
          <label>
            <input type="checkbox" v-model="analysisOptions.detectBeats">
            Extract Beat Markers
          </label>
          <label>
            <input type="checkbox" v-model="analysisOptions.energyAnalysis">
            Energy Level Analysis
          </label>
        </div>

        <button
          @click="analyzeAudio"
          :disabled="!selectedFile || isAnalyzing"
          class="analyze-btn"
        >
          <i :class="isAnalyzing ? 'pi pi-spin pi-spinner' : 'pi pi-chart-bar'"></i>
          {{ isAnalyzing ? 'Analyzing...' : 'Analyze Audio' }}
        </button>
      </div>

      <!-- Analysis Results -->
      <div v-if="analysisResults" class="analysis-results">
        <h3>Analysis Results</h3>
        <div class="results-grid">
          <div class="result-card">
            <div class="result-label">BPM</div>
            <div class="result-value large">{{ analysisResults.bpm.toFixed(1) }}</div>
            <div class="result-confidence">{{ (analysisResults.confidence * 100).toFixed(1) }}% confidence</div>
          </div>

          <div class="result-card" v-if="analysisResults.key">
            <div class="result-label">Musical Key</div>
            <div class="result-value">{{ analysisResults.key }}</div>
          </div>

          <div class="result-card" v-if="analysisResults.energy">
            <div class="result-label">Energy Level</div>
            <div class="result-value">{{ analysisResults.energy.toFixed(0) }}%</div>
            <div class="energy-bar">
              <div class="energy-fill" :style="{ width: analysisResults.energy + '%' }"></div>
            </div>
          </div>

          <div class="result-card" v-if="analysisResults.tempo_class">
            <div class="result-label">Tempo Class</div>
            <div class="result-value">{{ analysisResults.tempo_class }}</div>
          </div>
        </div>

        <!-- Beat Markers Visualization -->
        <div v-if="analysisResults.beats" class="beats-visualization">
          <h4>Beat Pattern</h4>
          <div class="beats-timeline">
            <div
              v-for="(beat, index) in analysisResults.beats.slice(0, 32)"
              :key="index"
              class="beat-marker"
              :class="{ strong: index % 4 === 0 }"
              :style="{ left: (beat.time / analysisResults.duration) * 100 + '%' }"
            >
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Apple Music Integration Tab -->
    <div v-show="activeTab === 'apple'" class="tab-content apple-tab">
      <div class="apple-music-controls">
        <div class="search-section">
          <div class="search-input-group">
            <input
              v-model="appleSearch.query"
              @keyup.enter="searchAppleMusic"
              placeholder="Search Apple Music..."
              class="search-input"
            >
            <select v-model="appleSearch.mood" class="mood-select">
              <option value="">All Moods</option>
              <option value="cinematic">Cinematic</option>
              <option value="epic">Epic</option>
              <option value="emotional">Emotional</option>
              <option value="action">Action</option>
              <option value="mysterious">Mysterious</option>
            </select>
            <button @click="searchAppleMusic" class="search-btn">
              <i class="pi pi-search"></i> Search
            </button>
          </div>
        </div>

        <!-- Search Results -->
        <div v-if="appleSearchResults.length > 0" class="search-results">
          <h3>Apple Music Results</h3>
          <div class="results-list">
            <div
              v-for="track in appleSearchResults"
              :key="track.id"
              class="apple-track-item"
              @click="selectAppleTrack(track)"
              :class="{ selected: selectedAppleTrack?.id === track.id }"
            >
              <img :src="track.artwork" :alt="track.name" class="track-artwork">
              <div class="track-details">
                <div class="track-title">{{ track.name }}</div>
                <div class="track-artist">{{ track.artist }}</div>
                <div class="track-album">{{ track.album }}</div>
              </div>
              <div class="track-meta">
                <div class="track-duration">{{ formatDuration(track.duration) }}</div>
                <div class="track-relevance" v-if="track.relevance_score">
                  {{ track.relevance_score }}% match
                </div>
              </div>
              <div class="track-actions">
                <button @click="previewAppleTrack(track)" class="preview-btn">
                  <i class="pi pi-play"></i>
                </button>
                <button @click="analyzeAppleTrack(track)" class="analyze-btn">
                  <i class="pi pi-chart-bar"></i>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Video Sync Tab -->
    <div v-show="activeTab === 'sync'" class="tab-content sync-tab">
      <div class="sync-controls">
        <div class="sync-setup">
          <div class="file-selection">
            <div class="file-group">
              <label>Video File</label>
              <select v-model="syncParams.videoFile" class="file-select">
                <option value="">Select video...</option>
                <option v-for="video in availableVideos" :key="video.path" :value="video.path">
                  {{ video.name }}
                </option>
              </select>
            </div>

            <div class="file-group">
              <label>Audio File</label>
              <select v-model="syncParams.audioFile" class="file-select">
                <option value="">Select audio...</option>
                <option v-for="audio in availableAudio" :key="audio.path" :value="audio.path">
                  {{ audio.name }}
                </option>
              </select>
            </div>
          </div>

          <div class="sync-options">
            <label>Sync Type</label>
            <select v-model="syncParams.syncType" class="sync-type-select">
              <option value="beat_sync">Beat Synchronization</option>
              <option value="manual_sync">Manual Alignment</option>
              <option value="auto_sync">Auto Alignment</option>
              <option value="tempo_match">Tempo Matching</option>
            </select>
          </div>

          <button
            @click="syncVideoAudio"
            :disabled="!syncParams.videoFile || !syncParams.audioFile || isSyncing"
            class="sync-btn primary"
          >
            <i :class="isSyncing ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'"></i>
            {{ isSyncing ? 'Syncing...' : 'Sync Video & Audio' }}
          </button>
        </div>

        <!-- Sync Progress -->
        <div v-if="isSyncing" class="sync-progress">
          <div class="progress-header">
            <span>Synchronizing video and audio...</span>
            <span>{{ Math.round(syncProgress) }}%</span>
          </div>
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: syncProgress + '%' }"></div>
          </div>
          <div class="progress-status">{{ syncStatus }}</div>
        </div>

        <!-- Sync Results -->
        <div v-if="syncResults" class="sync-results">
          <h3>Sync Complete</h3>
          <div class="results-info">
            <div class="info-item">
              <label>Output File:</label>
              <span>{{ syncResults.synced_path }}</span>
            </div>
            <div class="info-item">
              <label>BPM Detected:</label>
              <span>{{ syncResults.bpm_detected }} BPM</span>
            </div>
            <div class="info-item">
              <label>Sync Quality:</label>
              <span :class="getSyncQualityClass(syncResults.sync_quality)">
                {{ syncResults.sync_quality }}
              </span>
            </div>
          </div>

          <div class="result-actions">
            <button @click="previewSyncedVideo" class="preview-btn">
              <i class="pi pi-play"></i> Preview Result
            </button>
            <button @click="addToJellyfin" class="jellyfin-btn">
              <i class="pi pi-plus"></i> Add to Jellyfin
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'

// Reactive state
const activeTab = ref('generation')
const serviceStatus = ref('connected')
const compactMode = ref(false)
const isGenerating = ref(false)
const isAnalyzing = ref(false)
const isSyncing = ref(false)
const isPlaying = ref(false)

const generationProgress = ref(0)
const generationStatus = ref('')
const syncProgress = ref(0)
const syncStatus = ref('')

// Generation parameters
const generationParams = reactive({
  style: 'epic_orchestral',
  duration: 30,
  bpm: 120,
  energy: 'medium'
})

// File handling
const selectedFile = ref(null)
const selectedTrack = ref(null)
const selectedAppleTrack = ref(null)
const currentTrack = ref(null)

// Analysis
const analysisOptions = reactive({
  detectKey: true,
  detectBeats: true,
  energyAnalysis: true
})
const analysisResults = ref(null)

// Apple Music
const appleSearch = reactive({
  query: '',
  mood: ''
})
const appleSearchResults = ref([])

// Sync parameters
const syncParams = reactive({
  videoFile: '',
  audioFile: '',
  syncType: 'beat_sync'
})
const syncResults = ref(null)

// Data arrays
const generatedTracks = ref([])
const availableVideos = ref([])
const availableAudio = ref([])

// Computed
const serviceStatusText = computed(() => {
  const statuses = {
    connected: 'Music Service Connected',
    connecting: 'Connecting...',
    disconnected: 'Service Unavailable'
  }
  return statuses[serviceStatus.value] || 'Unknown'
})

const tabs = [
  { id: 'generation', label: 'AI Generation', icon: '' },
  { id: 'analysis', label: 'BPM Analysis', icon: '' },
  { id: 'apple', label: 'Apple Music', icon: '' },
  { id: 'sync', label: 'Video Sync', icon: '' }
]

// Methods
const refreshServices = async () => {
  try {
    const response = await fetch('http://127.0.0.1:8308/api/health')
    serviceStatus.value = response.ok ? 'connected' : 'disconnected'
  } catch (error) {
    serviceStatus.value = 'disconnected'
  }
}

const toggleCompactMode = () => {
  compactMode.value = !compactMode.value
}

// AI Music Generation
const generateMusic = async () => {
  isGenerating.value = true
  generationProgress.value = 0
  generationStatus.value = 'Initializing generation...'

  try {
    // Simulate progress
    const progressInterval = setInterval(() => {
      generationProgress.value += Math.random() * 10
      if (generationProgress.value >= 100) {
        clearInterval(progressInterval)
      }
    }, 500)

    const response = await fetch('http://127.0.0.1:8308/api/generate/music', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        style: generationParams.style,
        duration: generationParams.duration,
        bpm: generationParams.bpm,
        energy: generationParams.energy
      })
    })

    if (response.ok) {
      const result = await response.json()
      generatedTracks.value.unshift({
        id: result.track_id,
        name: `${generationParams.style} - ${new Date().toLocaleTimeString()}`,
        bpm: result.bpm || generationParams.bpm,
        duration: result.duration || generationParams.duration,
        size: result.file_size || 0,
        path: result.file_path
      })

      generationStatus.value = 'Generation complete!'
    }
  } catch (error) {
    console.error('Generation failed:', error)
    generationStatus.value = 'Generation failed'
  } finally {
    isGenerating.value = false
    generationProgress.value = 100
  }
}

const previewGeneration = () => {
  if (generatedTracks.value.length > 0) {
    playTrack(generatedTracks.value[0])
  }
}

// BPM Analysis
const handleFileUpload = (event) => {
  selectedFile.value = event.target.files[0]
}

const analyzeAudio = async () => {
  if (!selectedFile.value) return

  isAnalyzing.value = true

  try {
    const formData = new FormData()
    formData.append('audio', selectedFile.value)

    const response = await fetch('http://127.0.0.1:8308/api/analyze/upload', {
      method: 'POST',
      body: formData
    })

    if (response.ok) {
      const result = await response.json()
      analysisResults.value = result
    }
  } catch (error) {
    console.error('Analysis failed:', error)
  } finally {
    isAnalyzing.value = false
  }
}

// Apple Music Integration
const searchAppleMusic = async () => {
  if (!appleSearch.query) return

  try {
    const response = await fetch('http://127.0.0.1:8315/api/music/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: appleSearch.query,
        mood: appleSearch.mood
      })
    })

    if (response.ok) {
      const result = await response.json()
      appleSearchResults.value = result.tracks || []
    }
  } catch (error) {
    console.error('Apple Music search failed:', error)
  }
}

const selectAppleTrack = (track) => {
  selectedAppleTrack.value = track
}

const previewAppleTrack = (track) => {
  // In a real implementation, this would play the 30-second preview
  console.log('Playing preview for:', track.name)
}

const analyzeAppleTrack = async (track) => {
  try {
    const response = await fetch(`http://127.0.0.1:8315/api/apple-music/track/${track.id}/analysis`)
    if (response.ok) {
      const analysis = await response.json()
      console.log('Apple Music track analysis:', analysis)
    }
  } catch (error) {
    console.error('Apple Music analysis failed:', error)
  }
}

// Video Sync
const syncVideoAudio = async () => {
  isSyncing.value = true
  syncProgress.value = 0
  syncStatus.value = 'Starting sync process...'

  try {
    // Simulate progress
    const progressInterval = setInterval(() => {
      syncProgress.value += Math.random() * 8
      if (syncProgress.value >= 100) {
        clearInterval(progressInterval)
      }
    }, 1000)

    const response = await fetch('http://127.0.0.1:8308/api/sync/video-audio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_path: syncParams.videoFile,
        audio_path: syncParams.audioFile,
        sync_type: syncParams.syncType
      })
    })

    if (response.ok) {
      const result = await response.json()
      syncResults.value = result
      syncStatus.value = 'Sync complete!'
    }
  } catch (error) {
    console.error('Sync failed:', error)
    syncStatus.value = 'Sync failed'
  } finally {
    isSyncing.value = false
    syncProgress.value = 100
  }
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

const getSyncQualityClass = (quality) => {
  return {
    'quality-high': quality === 'High',
    'quality-medium': quality === 'Medium',
    'quality-low': quality === 'Low'
  }
}

const selectTrack = (track) => {
  selectedTrack.value = track
}

const playTrack = (track) => {
  if (isPlaying.value && currentTrack.value?.id === track.id) {
    isPlaying.value = false
    currentTrack.value = null
  } else {
    isPlaying.value = true
    currentTrack.value = track
  }
}

const downloadTrack = (track) => {
  // In a real implementation, this would download the file
  console.log('Downloading:', track.name)
}

const previewSyncedVideo = () => {
  console.log('Previewing synced video:', syncResults.value.synced_path)
}

const addToJellyfin = async () => {
  if (!syncResults.value) return

  try {
    const response = await fetch('http://127.0.0.1:8308/api/jellyfin/add-track', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        track_id: syncResults.value.synced_path,
        category: 'AI_Generated'
      })
    })

    if (response.ok) {
      console.log('Added to Jellyfin successfully')
    }
  } catch (error) {
    console.error('Failed to add to Jellyfin:', error)
  }
}

// Lifecycle
onMounted(async () => {
  await refreshServices()

  // Load available files
  availableVideos.value = [
    { name: 'Anime Scene 1', path: '/mnt/1TB-storage/ComfyUI/output/anime_30sec_final_00006.mp4' },
    { name: 'Echo Video', path: '/mnt/1TB-storage/ComfyUI/output/echo_video_877c3aba_00001.mp4' }
  ]

  availableAudio.value = [
    { name: 'Epic Track 1', path: '/opt/tower-music-production/generated/epic_track_001.wav' },
    { name: 'Cyberpunk Beat', path: '/opt/tower-music-production/generated/cyberpunk_beat.wav' }
  ]
})
</script>

<style scoped>
.music-production-interface {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  border-radius: 12px;
  padding: 20px;
  color: #f1f5f9;
  min-height: 600px;
}

.interface-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
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

.service-status.disconnected .status-indicator {
  background: #ef4444;
}

.service-status.connecting .status-indicator {
  background: #f59e0b;
  animation: pulse 1s infinite;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.refresh-btn, .compact-btn {
  padding: 8px 16px;
  background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
  border: 1px solid #334155;
  border-radius: 6px;
  color: #f1f5f9;
  cursor: pointer;
  transition: all 0.2s ease;
}

.refresh-btn:hover, .compact-btn:hover {
  background: linear-gradient(135deg, #334155 0%, #475569 100%);
  transform: translateY(-1px);
}

.compact-btn.active {
  background: linear-gradient(135deg, #00d4aa 0%, #059669 100%);
  border-color: #00d4aa;
}

.service-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 24px;
  background: rgba(15, 23, 42, 0.5);
  border-radius: 8px;
  padding: 4px;
}

.tab-button {
  flex: 1;
  padding: 12px 16px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s ease;
  font-weight: 500;
}

.tab-button:hover {
  color: #e2e8f0;
  background: rgba(51, 65, 85, 0.3);
}

.tab-button.active {
  background: linear-gradient(135deg, #00d4aa 0%, #059669 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(0, 212, 170, 0.2);
}

.tab-content {
  min-height: 400px;
}

/* Generation Tab Styles */
.control-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.control-group label {
  font-weight: 600;
  color: #e2e8f0;
  font-size: 0.875rem;
}

.style-select, .energy-select {
  padding: 8px 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #f1f5f9;
}

.duration-slider, .bpm-slider {
  appearance: none;
  height: 6px;
  background: #334155;
  border-radius: 3px;
  outline: none;
}

.duration-slider::-webkit-slider-thumb, .bpm-slider::-webkit-slider-thumb {
  appearance: none;
  width: 18px;
  height: 18px;
  background: #00d4aa;
  border-radius: 50%;
  cursor: pointer;
}

.duration-display, .bpm-display {
  font-weight: 600;
  color: #00d4aa;
  text-align: center;
}

.generation-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.generate-btn, .preview-btn {
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

.generate-btn.primary {
  background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
  color: white;
}

.generate-btn.primary:hover:not(:disabled) {
  background: linear-gradient(135deg, #6d28d9 0%, #5b21b6 100%);
  transform: translateY(-2px);
}

.generate-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.preview-btn {
  background: linear-gradient(135deg, #059669 0%, #047857 100%);
  color: white;
}

.preview-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #047857 0%, #065f46 100%);
}

.generation-progress {
  margin: 24px 0;
  padding: 16px;
  background: rgba(15, 23, 42, 0.5);
  border-radius: 8px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-weight: 600;
}

.progress-bar {
  height: 8px;
  background: #334155;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 8px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #7c3aed, #00d4aa);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-status {
  font-size: 0.875rem;
  color: #94a3b8;
}

.generated-tracks h3 {
  color: #e2e8f0;
  margin-bottom: 16px;
}

.tracks-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.track-item {
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.track-item:hover {
  border-color: #00d4aa;
  transform: translateY(-2px);
}

.track-item.selected {
  border-color: #00d4aa;
  background: rgba(0, 212, 170, 0.1);
}

.track-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.track-name {
  font-weight: 600;
  color: #e2e8f0;
}

.track-actions {
  display: flex;
  gap: 4px;
}

.play-btn, .download-btn {
  padding: 6px;
  background: #334155;
  border: 1px solid #475569;
  border-radius: 4px;
  color: #f1f5f9;
  cursor: pointer;
  transition: all 0.2s ease;
}

.play-btn:hover {
  background: #059669;
  border-color: #059669;
}

.download-btn:hover {
  background: #7c3aed;
  border-color: #7c3aed;
}

.track-info {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  font-size: 0.875rem;
  color: #94a3b8;
}

.track-bpm {
  font-weight: 600;
  color: #00d4aa;
}

.mini-waveform {
  width: 100%;
  height: 40px;
  background: #1e293b;
  border-radius: 4px;
}

/* Analysis Tab Styles */
.analysis-controls {
  display: flex;
  flex-direction: column;
  gap: 24px;
  margin-bottom: 32px;
}

.upload-label {
  display: inline-block;
  padding: 12px 24px;
  background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
  border: 2px dashed #475569;
  border-radius: 8px;
  color: #f1f5f9;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: center;
}

.upload-label:hover {
  border-color: #00d4aa;
  background: linear-gradient(135deg, #334155 0%, #475569 100%);
}

.upload-input {
  display: none;
}

.analysis-options {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.analysis-options label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #e2e8f0;
  cursor: pointer;
}

.analyze-btn {
  padding: 12px 24px;
  background: linear-gradient(135deg, #059669 0%, #047857 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
}

.analyze-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #047857 0%, #065f46 100%);
  transform: translateY(-2px);
}

.analyze-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.analysis-results h3 {
  color: #e2e8f0;
  margin-bottom: 16px;
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.result-card {
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}

.result-label {
  font-size: 0.875rem;
  color: #94a3b8;
  margin-bottom: 8px;
}

.result-value {
  font-size: 1.5rem;
  font-weight: bold;
  color: #00d4aa;
  margin-bottom: 4px;
}

.result-value.large {
  font-size: 2.5rem;
}

.result-confidence {
  font-size: 0.75rem;
  color: #64748b;
}

.energy-bar {
  height: 8px;
  background: #334155;
  border-radius: 4px;
  overflow: hidden;
  margin-top: 8px;
}

.energy-fill {
  height: 100%;
  background: linear-gradient(90deg, #22c55e 0%, #f59e0b 50%, #ef4444 100%);
  transition: width 0.3s ease;
}

.beats-visualization h4 {
  color: #e2e8f0;
  margin-bottom: 12px;
}

.beats-timeline {
  position: relative;
  height: 40px;
  background: #1e293b;
  border-radius: 4px;
  overflow: hidden;
}

.beat-marker {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: rgba(0, 212, 170, 0.6);
}

.beat-marker.strong {
  background: #00d4aa;
  width: 3px;
}

/* Apple Music Tab Styles */
.search-input-group {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.search-input {
  flex: 1;
  padding: 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #f1f5f9;
}

.mood-select {
  padding: 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #f1f5f9;
}

.search-btn {
  padding: 12px 24px;
  background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
  border: none;
  border-radius: 6px;
  color: white;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.search-btn:hover {
  background: linear-gradient(135deg, #6d28d9 0%, #5b21b6 100%);
}

.search-results h3 {
  color: #e2e8f0;
  margin-bottom: 16px;
}

.results-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.apple-track-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid #334155;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.apple-track-item:hover {
  border-color: #00d4aa;
  transform: translateY(-1px);
}

.apple-track-item.selected {
  border-color: #00d4aa;
  background: rgba(0, 212, 170, 0.1);
}

.track-artwork {
  width: 60px;
  height: 60px;
  border-radius: 6px;
  object-fit: cover;
}

.track-details {
  flex: 1;
}

.track-title {
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 4px;
}

.track-artist {
  color: #94a3b8;
  margin-bottom: 2px;
}

.track-album {
  font-size: 0.875rem;
  color: #64748b;
}

.track-meta {
  text-align: right;
  margin-right: 16px;
}

.track-duration {
  font-family: monospace;
  color: #94a3b8;
  margin-bottom: 4px;
}

.track-relevance {
  font-size: 0.875rem;
  color: #00d4aa;
  font-weight: 600;
}

/* Sync Tab Styles */
.sync-setup {
  display: flex;
  flex-direction: column;
  gap: 24px;
  margin-bottom: 32px;
}

.file-selection {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.file-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-group label {
  font-weight: 600;
  color: #e2e8f0;
}

.file-select, .sync-type-select {
  padding: 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #f1f5f9;
}

.sync-btn {
  padding: 12px 24px;
  background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
}

.sync-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #b91c1c 0%, #991b1b 100%);
  transform: translateY(-2px);
}

.sync-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.sync-progress {
  margin: 24px 0;
  padding: 16px;
  background: rgba(15, 23, 42, 0.5);
  border-radius: 8px;
}

.sync-results {
  padding: 16px;
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid #22c55e;
  border-radius: 8px;
}

.sync-results h3 {
  color: #22c55e;
  margin-bottom: 16px;
}

.results-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.info-item {
  display: flex;
  gap: 12px;
}

.info-item label {
  font-weight: 600;
  color: #94a3b8;
  min-width: 120px;
}

.info-item span {
  color: #e2e8f0;
}

.quality-high { color: #22c55e; }
.quality-medium { color: #f59e0b; }
.quality-low { color: #ef4444; }

.result-actions {
  display: flex;
  gap: 12px;
}

.jellyfin-btn {
  padding: 8px 16px;
  background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
  border: none;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
}

.jellyfin-btn:hover {
  background: linear-gradient(135deg, #6d28d9 0%, #5b21b6 100%);
}

/* Responsive Design */
@media (max-width: 768px) {
  .interface-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .service-tabs {
    flex-direction: column;
  }

  .control-grid {
    grid-template-columns: 1fr;
  }

  .file-selection {
    grid-template-columns: 1fr;
  }

  .search-input-group {
    flex-direction: column;
  }

  .apple-track-item {
    flex-direction: column;
    text-align: center;
  }

  .track-meta {
    text-align: center;
    margin-right: 0;
  }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>