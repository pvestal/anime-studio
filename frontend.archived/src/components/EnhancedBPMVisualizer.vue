<template>
  <div class="enhanced-bpm-visualizer">
    <!-- BPM Display Header -->
    <div class="bpm-header">
      <div class="bpm-display">
        <div class="bpm-value" :class="{ 'pulsing': isAnalyzing }">
          {{ currentBPM.toFixed(1) }}
        </div>
        <div class="bpm-label">BPM</div>
        <div class="bpm-confidence" :class="getConfidenceClass(confidence)">
          {{ confidence.toFixed(1) }}% confidence
        </div>
      </div>

      <div class="tempo-classification">
        <div class="tempo-label">{{ getTempoClassification(currentBPM) }}</div>
        <div class="key-signature" v-if="detectedKey">
          Key: {{ detectedKey }}
        </div>
      </div>

      <div class="analysis-controls">
        <button @click="toggleAnalysis" class="analysis-btn" :class="{ 'active': isAnalyzing }">
          <i :class="isAnalyzing ? 'pi pi-pause' : 'pi pi-play'"></i>
          {{ isAnalyzing ? 'Stop' : 'Analyze' }}
        </button>
        <button @click="calibrateBPM" class="calibrate-btn">
          <i class="pi pi-cog"></i> Calibrate
        </button>
      </div>
    </div>

    <!-- Real-time Waveform Display -->
    <div class="waveform-container" ref="waveformContainer">
      <canvas ref="waveformCanvas" class="waveform-canvas"></canvas>
      <div class="waveform-overlay">
        <!-- Beat markers -->
        <div v-for="beat in beatMarkers" :key="beat.id"
             class="beat-marker"
             :style="{ left: beat.position + '%' }">
          <div class="marker-line" :class="beat.strength"></div>
          <div class="marker-label" v-if="beat.label">{{ beat.label }}</div>
        </div>

        <!-- Current playhead -->
        <div class="playhead" :style="{ left: playheadPosition + '%' }"></div>
      </div>
    </div>

    <!-- Beat Grid Visualization -->
    <div class="beat-grid-container">
      <div class="beat-grid">
        <div v-for="(bar, index) in beatGrid" :key="index" class="beat-bar">
          <div v-for="(beat, beatIndex) in bar.beats" :key="beatIndex"
               class="beat-cell"
               :class="{
                 'strong': beat.strength === 'strong',
                 'medium': beat.strength === 'medium',
                 'weak': beat.strength === 'weak',
                 'current': beat.isCurrent
               }"
               @click="setBeatMarker(beat.timestamp)">
            <div class="beat-indicator"></div>
            <div class="beat-number">{{ beatIndex + 1 }}</div>
          </div>
          <div class="bar-number">{{ index + 1 }}</div>
        </div>
      </div>
    </div>

    <!-- BPM Analysis Stats -->
    <div class="analysis-stats" v-if="analysisData">
      <div class="stat-group">
        <div class="stat-item">
          <label>Avg BPM:</label>
          <span>{{ analysisData.averageBPM.toFixed(1) }}</span>
        </div>
        <div class="stat-item">
          <label>Variance:</label>
          <span>{{ analysisData.variance.toFixed(2) }}</span>
        </div>
        <div class="stat-item">
          <label>Stability:</label>
          <span :class="getStabilityClass(analysisData.stability)">
            {{ analysisData.stability }}
          </span>
        </div>
      </div>

      <div class="stat-group">
        <div class="stat-item">
          <label>Energy:</label>
          <span class="energy-meter">
            <div class="energy-bar" :style="{ width: analysisData.energy + '%' }"></div>
            {{ analysisData.energy.toFixed(0) }}%
          </span>
        </div>
        <div class="stat-item">
          <label>Rhythm Pattern:</label>
          <span>{{ analysisData.rhythmPattern }}</span>
        </div>
      </div>
    </div>

    <!-- Manual BPM Input -->
    <div class="manual-controls" v-if="showManualControls">
      <div class="manual-input-group">
        <label>Manual BPM:</label>
        <input v-model.number="manualBPM" type="number" min="60" max="200"
               @input="updateManualBPM" class="bpm-input">
        <button @click="applyManualBPM" class="apply-btn">Apply</button>
      </div>

      <div class="tap-tempo">
        <button @click="tapTempo" class="tap-btn" :class="{ 'tapping': isTapping }">
          🥁 Tap Tempo
        </button>
        <div class="tap-count" v-if="tapCount > 0">
          Taps: {{ tapCount }} | BPM: {{ tapBPM.toFixed(1) }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'

// Props
const props = defineProps({
  audioFile: String,
  videoDuration: Number,
  autoAnalyze: { type: Boolean, default: true },
  showManualControls: { type: Boolean, default: false }
})

// Emits
const emit = defineEmits(['bpmDetected', 'beatMarker', 'analysisComplete'])

// Reactive state
const currentBPM = ref(120.0)
const confidence = ref(0.0)
const detectedKey = ref(null)
const isAnalyzing = ref(false)
const playheadPosition = ref(0)
const beatMarkers = ref([])
const beatGrid = ref([])
const analysisData = ref(null)
const manualBPM = ref(120)
const tapCount = ref(0)
const tapBPM = ref(0)
const isTapping = ref(false)

// Canvas refs
const waveformCanvas = ref(null)
const waveformContainer = ref(null)

// Audio analysis variables
let audioContext = null
let analyser = null
let dataArray = null
let animationFrame = null
let tapTimes = []
let lastTapTime = 0

// Tempo classifications
const getTempoClassification = (bpm) => {
  if (bpm < 60) return 'Very Slow'
  if (bpm < 80) return 'Slow'
  if (bpm < 100) return 'Moderate'
  if (bpm < 120) return 'Moderately Fast'
  if (bpm < 140) return 'Fast'
  if (bpm < 160) return 'Very Fast'
  return 'Extremely Fast'
}

const getConfidenceClass = (conf) => {
  if (conf > 90) return 'high-confidence'
  if (conf > 70) return 'medium-confidence'
  return 'low-confidence'
}

const getStabilityClass = (stability) => {
  return {
    'stability-high': stability === 'High',
    'stability-medium': stability === 'Medium',
    'stability-low': stability === 'Low'
  }
}

// BPM Analysis Functions
const toggleAnalysis = async () => {
  if (isAnalyzing.value) {
    stopAnalysis()
  } else {
    await startAnalysis()
  }
}

const startAnalysis = async () => {
  if (!props.audioFile) {
    console.warn('No audio file provided for BPM analysis')
    return
  }

  try {
    isAnalyzing.value = true

    // Call music production service for BPM analysis
    const response = await fetch('http://127.0.0.1:8308/api/analyze/bpm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        audio_file: props.audioFile,
        return_beats: true,
        analyze_key: true
      })
    })

    if (response.ok) {
      const data = await response.json()
      currentBPM.value = data.bpm
      confidence.value = data.confidence * 100
      detectedKey.value = data.key

      // Generate beat markers
      generateBeatMarkers(data.bpm, data.beats || [])

      // Create analysis data
      analysisData.value = {
        averageBPM: data.bpm,
        variance: data.variance || 0,
        stability: data.stability || 'Medium',
        energy: data.energy || 75,
        rhythmPattern: data.pattern || '4/4'
      }

      emit('bpmDetected', { bpm: data.bpm, confidence: confidence.value, key: detectedKey.value })
      emit('analysisComplete', analysisData.value)

      // Start real-time waveform visualization
      if (audioContext) {
        startWaveformVisualization()
      }
    }
  } catch (error) {
    console.error('BPM analysis failed:', error)
    isAnalyzing.value = false
  }
}

const stopAnalysis = () => {
  isAnalyzing.value = false
  if (animationFrame) {
    cancelAnimationFrame(animationFrame)
    animationFrame = null
  }
}

const generateBeatMarkers = (bpm, beats) => {
  const beatInterval = 60 / bpm // seconds per beat
  const duration = props.videoDuration || 30 // default 30 seconds

  beatMarkers.value = []

  // Generate markers for each beat
  for (let i = 0; i * beatInterval < duration; i++) {
    const timestamp = i * beatInterval
    const position = (timestamp / duration) * 100

    beatMarkers.value.push({
      id: i,
      timestamp,
      position,
      strength: i % 4 === 0 ? 'strong' : (i % 2 === 0 ? 'medium' : 'weak'),
      label: i % 4 === 0 ? `${Math.floor(i / 4) + 1}` : null
    })
  }

  // Generate beat grid for visual representation
  generateBeatGrid(bpm, duration)
}

const generateBeatGrid = (bpm, duration) => {
  const beatsPerBar = 4
  const beatInterval = 60 / bpm
  const barsCount = Math.ceil(duration / (beatInterval * beatsPerBar))

  beatGrid.value = []

  for (let bar = 0; bar < barsCount; bar++) {
    const beats = []
    for (let beat = 0; beat < beatsPerBar; beat++) {
      const timestamp = (bar * beatsPerBar + beat) * beatInterval
      if (timestamp < duration) {
        beats.push({
          timestamp,
          strength: beat === 0 ? 'strong' : 'weak',
          isCurrent: false
        })
      }
    }
    beatGrid.value.push({ beats, barNumber: bar + 1 })
  }
}

// Waveform Visualization
const startWaveformVisualization = () => {
  if (!waveformCanvas.value) return

  const canvas = waveformCanvas.value
  const ctx = canvas.getContext('2d')

  const draw = () => {
    if (!isAnalyzing.value) return

    analyser.getByteFrequencyData(dataArray)

    ctx.fillStyle = 'rgba(2, 6, 23, 0.2)'
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    const barWidth = canvas.width / dataArray.length
    let x = 0

    for (let i = 0; i < dataArray.length; i++) {
      const barHeight = (dataArray[i] / 255) * canvas.height

      // Color based on frequency
      const hue = (i / dataArray.length) * 360
      ctx.fillStyle = `hsl(${hue}, 70%, 50%)`

      ctx.fillRect(x, canvas.height - barHeight, barWidth, barHeight)
      x += barWidth
    }

    animationFrame = requestAnimationFrame(draw)
  }

  draw()
}

// Manual Controls
const updateManualBPM = () => {
  if (manualBPM.value >= 60 && manualBPM.value <= 200) {
    generateBeatMarkers(manualBPM.value, [])
  }
}

const applyManualBPM = () => {
  currentBPM.value = manualBPM.value
  confidence.value = 100 // Manual input is 100% confident
  generateBeatMarkers(manualBPM.value, [])
  emit('bpmDetected', { bpm: manualBPM.value, confidence: 100, manual: true })
}

const tapTempo = () => {
  const now = Date.now()

  if (now - lastTapTime > 3000) {
    // Reset if more than 3 seconds since last tap
    tapTimes = []
    tapCount.value = 0
  }

  tapTimes.push(now)
  tapCount.value = tapTimes.length
  lastTapTime = now

  if (tapTimes.length >= 2) {
    // Calculate BPM from tap intervals
    const intervals = []
    for (let i = 1; i < tapTimes.length; i++) {
      intervals.push(tapTimes[i] - tapTimes[i - 1])
    }

    const avgInterval = intervals.reduce((a, b) => a + b) / intervals.length
    tapBPM.value = 60000 / avgInterval // Convert ms to BPM

    if (tapTimes.length >= 4) {
      // Apply tap tempo after 4 taps
      manualBPM.value = Math.round(tapBPM.value)
      updateManualBPM()
    }
  }

  // Visual feedback
  isTapping.value = true
  setTimeout(() => {
    isTapping.value = false
  }, 100)
}

const setBeatMarker = (timestamp) => {
  emit('beatMarker', { timestamp, type: 'manual' })
}

const calibrateBPM = async () => {
  // Advanced calibration using Echo Brain
  try {
    const response = await fetch('http://127.0.0.1:8309/api/echo/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: `Analyze the musical timing and suggest BPM calibration for this track. Current detection: ${currentBPM.value} BPM with ${confidence.value}% confidence.`,
        conversation_id: 'bpm_calibration'
      })
    })

    if (response.ok) {
      const result = await response.json()
      console.log('Echo BPM calibration suggestion:', result.response)
    }
  } catch (error) {
    console.error('BPM calibration failed:', error)
  }
}

// Setup canvas when mounted
onMounted(async () => {
  await nextTick()

  if (waveformCanvas.value && waveformContainer.value) {
    const canvas = waveformCanvas.value
    const container = waveformContainer.value

    canvas.width = container.clientWidth
    canvas.height = 120

    // Initialize audio context for real-time analysis
    try {
      audioContext = new (window.AudioContext || window.webkitAudioContext)()
      analyser = audioContext.createAnalyser()
      analyser.fftSize = 256
      dataArray = new Uint8Array(analyser.frequencyBinCount)
    } catch (error) {
      console.warn('Audio context initialization failed:', error)
    }
  }

  // Auto-start analysis if enabled
  if (props.autoAnalyze && props.audioFile) {
    await startAnalysis()
  }
})

onUnmounted(() => {
  stopAnalysis()
  if (audioContext) {
    audioContext.close()
  }
})

// Watch for audio file changes
watch(() => props.audioFile, async (newFile) => {
  if (newFile && props.autoAnalyze) {
    await startAnalysis()
  }
})
</script>

<style scoped>
.enhanced-bpm-visualizer {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 16px;
  color: #f1f5f9;
}

.bpm-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #334155;
}

.bpm-display {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.bpm-value {
  font-size: 2.5rem;
  font-weight: bold;
  color: #00d4aa;
  text-shadow: 0 0 10px rgba(0, 212, 170, 0.5);
  transition: all 0.3s ease;
}

.bpm-value.pulsing {
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}

.bpm-label {
  font-size: 0.875rem;
  color: #94a3b8;
  margin-top: 4px;
}

.bpm-confidence {
  font-size: 0.75rem;
  margin-top: 4px;
  padding: 2px 8px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.5);
}

.high-confidence { color: #22c55e; }
.medium-confidence { color: #f59e0b; }
.low-confidence { color: #ef4444; }

.tempo-classification {
  text-align: center;
}

.tempo-label {
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 4px;
}

.key-signature {
  font-size: 0.875rem;
  color: #94a3b8;
}

.analysis-controls {
  display: flex;
  gap: 8px;
}

.analysis-btn, .calibrate-btn {
  padding: 8px 16px;
  border: 1px solid #334155;
  border-radius: 6px;
  background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
  color: #f1f5f9;
  cursor: pointer;
  transition: all 0.2s ease;
}

.analysis-btn:hover, .calibrate-btn:hover {
  background: linear-gradient(135deg, #334155 0%, #475569 100%);
  transform: translateY(-1px);
}

.analysis-btn.active {
  background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
  border-color: #dc2626;
}

.waveform-container {
  position: relative;
  height: 120px;
  background: #020617;
  border: 1px solid #334155;
  border-radius: 8px;
  margin-bottom: 16px;
  overflow: hidden;
}

.waveform-canvas {
  width: 100%;
  height: 100%;
}

.waveform-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
}

.beat-marker {
  position: absolute;
  top: 0;
  bottom: 0;
  pointer-events: none;
}

.marker-line {
  width: 2px;
  height: 100%;
  background: rgba(0, 212, 170, 0.7);
}

.marker-line.strong {
  background: rgba(0, 212, 170, 1);
  width: 3px;
}

.marker-line.medium {
  background: rgba(0, 212, 170, 0.8);
}

.marker-line.weak {
  background: rgba(0, 212, 170, 0.4);
  width: 1px;
}

.marker-label {
  position: absolute;
  top: -20px;
  left: -10px;
  background: rgba(0, 212, 170, 0.9);
  color: #0f172a;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

.playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #ef4444;
  z-index: 10;
}

.beat-grid-container {
  margin-bottom: 16px;
}

.beat-grid {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 8px 0;
}

.beat-bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 120px;
}

.beat-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 24px;
  height: 24px;
  margin: 2px;
  border: 1px solid #334155;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.beat-cell:hover {
  border-color: #00d4aa;
  transform: scale(1.1);
}

.beat-cell.strong {
  background: rgba(0, 212, 170, 0.3);
  border-color: #00d4aa;
}

.beat-cell.medium {
  background: rgba(0, 212, 170, 0.2);
}

.beat-cell.weak {
  background: rgba(0, 212, 170, 0.1);
}

.beat-cell.current {
  background: #ef4444;
  border-color: #ef4444;
}

.beat-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  margin: 2px;
}

.beat-number {
  font-size: 0.625rem;
  color: #94a3b8;
}

.bar-number {
  font-size: 0.75rem;
  color: #64748b;
  margin-top: 4px;
}

.analysis-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.stat-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  background: rgba(15, 23, 42, 0.5);
  border-radius: 6px;
}

.stat-item label {
  font-size: 0.875rem;
  color: #94a3b8;
}

.stat-item span {
  font-weight: 600;
  color: #e2e8f0;
}

.stability-high { color: #22c55e; }
.stability-medium { color: #f59e0b; }
.stability-low { color: #ef4444; }

.energy-meter {
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
  width: 80px;
  height: 16px;
  background: rgba(15, 23, 42, 0.8);
  border-radius: 8px;
  overflow: hidden;
}

.energy-bar {
  height: 100%;
  background: linear-gradient(90deg, #22c55e 0%, #f59e0b 50%, #ef4444 100%);
  border-radius: 8px;
  transition: width 0.3s ease;
}

.manual-controls {
  border-top: 1px solid #334155;
  padding-top: 16px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.manual-input-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.manual-input-group label {
  font-size: 0.875rem;
  color: #94a3b8;
}

.bpm-input {
  width: 80px;
  padding: 6px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 4px;
  color: #f1f5f9;
  text-align: center;
}

.apply-btn {
  padding: 6px 12px;
  background: linear-gradient(135deg, #059669 0%, #047857 100%);
  border: none;
  border-radius: 4px;
  color: white;
  cursor: pointer;
  font-size: 0.875rem;
}

.apply-btn:hover {
  background: linear-gradient(135deg, #047857 0%, #065f46 100%);
}

.tap-tempo {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.tap-btn {
  padding: 12px 24px;
  background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
  border: none;
  border-radius: 8px;
  color: white;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.1s ease;
}

.tap-btn:hover {
  background: linear-gradient(135deg, #6d28d9 0%, #5b21b6 100%);
}

.tap-btn.tapping {
  transform: scale(0.95);
  background: linear-gradient(135deg, #a855f7 0%, #7c3aed 100%);
}

.tap-count {
  font-size: 0.75rem;
  color: #94a3b8;
  text-align: center;
}
</style>