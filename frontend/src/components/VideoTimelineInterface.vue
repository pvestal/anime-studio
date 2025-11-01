<template>
  <div class="video-timeline-interface cyberpunk-theme">
    <!-- Timeline Header -->
    <div class="timeline-header">
      <div class="timeline-controls">
        <button class="cp-button neon-cyan" @click="playPause">
          <i :class="playing ? 'pi pi-pause' : 'pi pi-play'"></i>
        </button>
        <button class="cp-button" @click="stop">
          <i class="pi pi-stop"></i>
        </button>
        <button class="cp-button" @click="rewind">
          <i class="pi pi-step-backward"></i>
        </button>
        <button class="cp-button" @click="fastForward">
          <i class="pi pi-step-forward"></i>
        </button>
      </div>

      <div class="timeline-info">
        <span class="timecode">{{ formatTime(currentTime) }} / {{ formatTime(totalDuration) }}</span>
        <span class="fps-indicator">{{ fps }} FPS</span>
        <div class="cp-status" :class="syncStatus">{{ syncStatusText }}</div>
      </div>

      <div class="timeline-tools">
        <button class="cp-button" @click="toggleMusicSync" :class="{ 'neon-cyan': musicSyncEnabled }">
          <i class="pi pi-volume-up"></i> Music Sync
        </button>
        <button class="cp-button" @click="toggleBeatMarkers" :class="{ 'neon-cyan': beatMarkersEnabled }">
          <i class="pi pi-chart-line"></i> Beat Markers
        </button>
        <button class="cp-button" @click="exportTimeline">
          <i class="pi pi-download"></i> Export
        </button>
      </div>
    </div>

    <!-- Main Timeline Area -->
    <div class="timeline-container" ref="timelineContainer">
      <!-- Time Ruler -->
      <div class="time-ruler">
        <div
          v-for="tick in timeRulerTicks"
          :key="tick.time"
          class="time-tick"
          :style="{ left: tick.position + '%' }"
        >
          <div class="tick-line" :class="tick.type"></div>
          <div class="tick-label">{{ formatTime(tick.time) }}</div>
        </div>
      </div>

      <!-- Video Track -->
      <div class="timeline-track video-track">
        <div class="track-header">
          <span class="track-title">Video</span>
          <div class="track-controls">
            <button class="track-button" @click="toggleVideoTrack">
              <i :class="videoTrackEnabled ? 'pi pi-eye' : 'pi pi-eye-slash'"></i>
            </button>
            <button class="track-button" @click="lockVideoTrack">
              <i :class="videoTrackLocked ? 'pi pi-lock' : 'pi pi-unlock'"></i>
            </button>
          </div>
        </div>
        <div class="track-content">
          <div
            v-for="clip in videoClips"
            :key="clip.id"
            class="video-clip"
            :style="{
              left: (clip.startTime / totalDuration) * 100 + '%',
              width: (clip.duration / totalDuration) * 100 + '%'
            }"
            @click="selectClip(clip)"
            :class="{ selected: selectedClip?.id === clip.id }"
          >
            <div class="clip-thumbnail">
              <img :src="clip.thumbnailUrl" :alt="clip.name" />
            </div>
            <div class="clip-info">
              <div class="clip-name">{{ clip.name }}</div>
              <div class="clip-duration">{{ formatTime(clip.duration) }}</div>
            </div>
            <div class="clip-resize-handle left" @mousedown="startResize(clip, 'left', $event)"></div>
            <div class="clip-resize-handle right" @mousedown="startResize(clip, 'right', $event)"></div>
          </div>
        </div>
      </div>

      <!-- Audio/Music Track -->
      <div class="timeline-track audio-track">
        <div class="track-header">
          <span class="track-title">Audio</span>
          <div class="track-controls">
            <button class="track-button" @click="toggleAudioTrack">
              <i :class="audioTrackEnabled ? 'pi pi-volume-up' : 'pi pi-volume-off'"></i>
            </button>
            <button class="track-button" @click="addAudioClip">
              <i class="pi pi-plus"></i>
            </button>
          </div>
        </div>
        <div class="track-content">
          <!-- Waveform Display -->
          <div class="waveform-container" v-if="audioWaveform">
            <canvas
              ref="waveformCanvas"
              class="waveform-canvas"
              :width="timelineWidth"
              :height="60"
              @click="seekToPosition"
            ></canvas>
          </div>

          <!-- Audio Clips -->
          <div
            v-for="clip in audioClips"
            :key="clip.id"
            class="audio-clip"
            :style="{
              left: (clip.startTime / totalDuration) * 100 + '%',
              width: (clip.duration / totalDuration) * 100 + '%'
            }"
            @click="selectClip(clip)"
            :class="{ selected: selectedClip?.id === clip.id }"
          >
            <div class="clip-waveform">
              <div class="mini-waveform">
                <div
                  v-for="(bar, index) in clip.waveformBars"
                  :key="index"
                  class="waveform-bar"
                  :style="{ height: bar + '%' }"
                ></div>
              </div>
            </div>
            <div class="clip-info">
              <div class="clip-name">{{ clip.name }}</div>
              <div class="clip-bpm" v-if="clip.bpm">{{ clip.bpm }} BPM</div>
            </div>
          </div>

          <!-- Beat Markers -->
          <div v-if="beatMarkersEnabled" class="beat-markers">
            <div
              v-for="beat in beatMarkers"
              :key="beat.time"
              class="beat-marker"
              :style="{ left: (beat.time / totalDuration) * 100 + '%' }"
              :class="beat.type"
            >
              <div class="beat-line"></div>
              <div class="beat-indicator"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Character Track -->
      <div class="timeline-track character-track">
        <div class="track-header">
          <span class="track-title">Characters</span>
          <div class="track-controls">
            <button class="track-button" @click="addCharacterMarker">
              <i class="pi pi-user-plus"></i>
            </button>
          </div>
        </div>
        <div class="track-content">
          <div
            v-for="marker in characterMarkers"
            :key="marker.id"
            class="character-marker"
            :style="{ left: (marker.time / totalDuration) * 100 + '%' }"
            @click="selectMarker(marker)"
            :class="{ selected: selectedMarker?.id === marker.id }"
          >
            <div class="marker-avatar">
              <img :src="marker.character.avatarUrl" :alt="marker.character.name" />
            </div>
            <div class="marker-info">
              <div class="character-name">{{ marker.character.name }}</div>
              <div class="marker-action">{{ marker.action }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Playhead -->
      <div
        class="playhead"
        :style="{ left: (currentTime / totalDuration) * 100 + '%' }"
        @mousedown="startDragPlayhead"
      >
        <div class="playhead-line"></div>
        <div class="playhead-handle"></div>
      </div>
    </div>

    <!-- Music Synchronization Panel -->
    <div v-if="musicSyncEnabled" class="music-sync-panel cp-fade-in">
      <div class="sync-header">
        <h4>Music Synchronization</h4>
        <button class="cp-button" @click="detectBeats">
          <i class="pi pi-search"></i> Auto-Detect Beats
        </button>
      </div>

      <div class="sync-controls">
        <div class="bpm-control">
          <label>BPM</label>
          <input type="number" v-model="musicBPM" class="cp-input" min="60" max="200" />
          <button class="cp-button" @click="tapTempo">Tap Tempo</button>
        </div>

        <div class="sync-options">
          <label>
            <input type="checkbox" v-model="snapToBeats" />
            Snap clips to beats
          </label>
          <label>
            <input type="checkbox" v-model="highlightDownbeats" />
            Highlight downbeats
          </label>
          <label>
            <input type="checkbox" v-model="autoSyncEffects" />
            Auto-sync visual effects
          </label>
        </div>
      </div>

      <div class="rhythm-visualizer">
        <div class="rhythm-pattern">
          <div
            v-for="(beat, index) in rhythmPattern"
            :key="index"
            class="rhythm-beat"
            :class="{ active: beat.active, current: beat.current }"
            @click="toggleBeat(index)"
          >
            {{ index + 1 }}
          </div>
        </div>
      </div>
    </div>

    <!-- Properties Panel -->
    <div class="properties-panel" v-if="selectedClip || selectedMarker">
      <div class="panel-header">
        <h4>{{ selectedClip ? 'Clip Properties' : 'Marker Properties' }}</h4>
        <button class="cp-button" @click="clearSelection">
          <i class="pi pi-times"></i>
        </button>
      </div>

      <div v-if="selectedClip" class="clip-properties">
        <div class="property-group">
          <label>Name</label>
          <input v-model="selectedClip.name" class="cp-input" />
        </div>
        <div class="property-group">
          <label>Start Time</label>
          <input
            type="number"
            v-model="selectedClip.startTime"
            class="cp-input"
            step="0.1"
            @change="updateClipPosition"
          />
        </div>
        <div class="property-group">
          <label>Duration</label>
          <input
            type="number"
            v-model="selectedClip.duration"
            class="cp-input"
            step="0.1"
            @change="updateClipDuration"
          />
        </div>
        <div class="property-group" v-if="selectedClip.type === 'audio'">
          <label>Volume</label>
          <input
            type="range"
            v-model="selectedClip.volume"
            class="cp-slider"
            min="0"
            max="100"
          />
          <span>{{ selectedClip.volume }}%</span>
        </div>
        <div class="property-group" v-if="selectedClip.bpm">
          <label>BPM</label>
          <input v-model="selectedClip.bpm" type="number" class="cp-input" readonly />
        </div>
      </div>

      <div v-if="selectedMarker" class="marker-properties">
        <div class="property-group">
          <label>Character</label>
          <select v-model="selectedMarker.character.id" class="cp-input">
            <option v-for="char in availableCharacters" :key="char.id" :value="char.id">
              {{ char.name }}
            </option>
          </select>
        </div>
        <div class="property-group">
          <label>Action</label>
          <input v-model="selectedMarker.action" class="cp-input" />
        </div>
        <div class="property-group">
          <label>Time</label>
          <input
            type="number"
            v-model="selectedMarker.time"
            class="cp-input"
            step="0.1"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'

// Props and emits
const emit = defineEmits(['timeline-updated', 'clip-selected', 'sync-updated'])

// Reactive data
const playing = ref(false)
const currentTime = ref(0)
const totalDuration = ref(120) // 2 minutes default
const fps = ref(24)
const musicSyncEnabled = ref(true)
const beatMarkersEnabled = ref(true)
const videoTrackEnabled = ref(true)
const videoTrackLocked = ref(false)
const audioTrackEnabled = ref(true)
const timelineWidth = ref(1200)

const selectedClip = ref(null)
const selectedMarker = ref(null)

// Music sync properties
const musicBPM = ref(120)
const snapToBeats = ref(true)
const highlightDownbeats = ref(true)
const autoSyncEffects = ref(false)

// Timeline refs
const timelineContainer = ref(null)
const waveformCanvas = ref(null)

// Timeline data
const videoClips = ref([
  {
    id: 1,
    name: 'Cyberpunk Scene 1',
    startTime: 0,
    duration: 30,
    thumbnailUrl: '/api/anime/thumbnail/1',
    type: 'video'
  },
  {
    id: 2,
    name: 'Character Intro',
    startTime: 25,
    duration: 20,
    thumbnailUrl: '/api/anime/thumbnail/2',
    type: 'video'
  }
])

const audioClips = ref([
  {
    id: 3,
    name: 'Cyberpunk Soundtrack',
    startTime: 0,
    duration: 90,
    volume: 80,
    bpm: 128,
    type: 'audio',
    waveformBars: Array.from({ length: 100 }, () => Math.random() * 100)
  }
])

const characterMarkers = ref([
  {
    id: 1,
    time: 5,
    character: {
      id: 1,
      name: 'Kai Nakamura',
      avatarUrl: '/api/anime/character/1/avatar'
    },
    action: 'enters scene'
  },
  {
    id: 2,
    time: 35,
    character: {
      id: 2,
      name: 'Shadow Entity',
      avatarUrl: '/api/anime/character/2/avatar'
    },
    action: 'confrontation'
  }
])

const availableCharacters = ref([
  { id: 1, name: 'Kai Nakamura' },
  { id: 2, name: 'Shadow Entity' },
  { id: 3, name: 'Tech Operator' }
])

// Computed properties
const timeRulerTicks = computed(() => {
  const ticks = []
  const interval = totalDuration.value / 20

  for (let i = 0; i <= totalDuration.value; i += interval) {
    ticks.push({
      time: i,
      position: (i / totalDuration.value) * 100,
      type: i % (interval * 4) === 0 ? 'major' : 'minor'
    })
  }

  return ticks
})

const beatMarkers = computed(() => {
  if (!musicBPM.value) return []

  const beatInterval = 60 / musicBPM.value
  const markers = []

  for (let time = 0; time <= totalDuration.value; time += beatInterval) {
    const beatNumber = Math.round(time / beatInterval)
    markers.push({
      time,
      type: beatNumber % 4 === 0 ? 'downbeat' : 'beat'
    })
  }

  return markers
})

const rhythmPattern = computed(() => {
  return Array.from({ length: 16 }, (_, i) => ({
    active: i % 4 === 0, // Downbeats active by default
    current: false
  }))
})

const syncStatus = computed(() => {
  if (musicSyncEnabled.value && audioClips.value.length > 0) {
    return 'active'
  }
  return 'inactive'
})

const syncStatusText = computed(() => {
  return syncStatus.value === 'active' ? 'Synced' : 'No Sync'
})

const audioWaveform = computed(() => {
  return audioClips.value.length > 0
})

// Methods
function formatTime(seconds) {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  const frames = Math.floor((seconds % 1) * fps.value)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}:${frames.toString().padStart(2, '0')}`
}

function playPause() {
  playing.value = !playing.value
  if (playing.value) {
    startPlayback()
  } else {
    pausePlayback()
  }
}

function stop() {
  playing.value = false
  currentTime.value = 0
}

function rewind() {
  if (snapToBeats.value && beatMarkers.value.length > 0) {
    const prevBeat = beatMarkers.value
      .filter(beat => beat.time < currentTime.value)
      .pop()
    if (prevBeat) {
      currentTime.value = prevBeat.time
    }
  } else {
    currentTime.value = Math.max(0, currentTime.value - 1)
  }
}

function fastForward() {
  if (snapToBeats.value && beatMarkers.value.length > 0) {
    const nextBeat = beatMarkers.value
      .find(beat => beat.time > currentTime.value)
    if (nextBeat) {
      currentTime.value = nextBeat.time
    }
  } else {
    currentTime.value = Math.min(totalDuration.value, currentTime.value + 1)
  }
}

function startPlayback() {
  // Implement playback logic
  const interval = setInterval(() => {
    if (!playing.value) {
      clearInterval(interval)
      return
    }

    currentTime.value += 1 / fps.value
    if (currentTime.value >= totalDuration.value) {
      playing.value = false
      currentTime.value = totalDuration.value
    }
  }, 1000 / fps.value)
}

function pausePlayback() {
  // Playback stopped in startPlayback interval
}

function toggleMusicSync() {
  musicSyncEnabled.value = !musicSyncEnabled.value
  emit('sync-updated', { enabled: musicSyncEnabled.value, bpm: musicBPM.value })
}

function toggleBeatMarkers() {
  beatMarkersEnabled.value = !beatMarkersEnabled.value
}

function toggleVideoTrack() {
  videoTrackEnabled.value = !videoTrackEnabled.value
}

function lockVideoTrack() {
  videoTrackLocked.value = !videoTrackLocked.value
}

function toggleAudioTrack() {
  audioTrackEnabled.value = !audioTrackEnabled.value
}

function selectClip(clip) {
  selectedClip.value = clip
  selectedMarker.value = null
  emit('clip-selected', clip)
}

function selectMarker(marker) {
  selectedMarker.value = marker
  selectedClip.value = null
}

function clearSelection() {
  selectedClip.value = null
  selectedMarker.value = null
}

function seekToPosition(event) {
  const rect = event.target.getBoundingClientRect()
  const x = event.clientX - rect.left
  const percentage = x / rect.width
  currentTime.value = percentage * totalDuration.value
}

function detectBeats() {
  // Implement beat detection logic
  console.log('Detecting beats...')
}

function tapTempo() {
  // Implement tap tempo logic
  console.log('Tap tempo...')
}

function addAudioClip() {
  // Add new audio clip
  console.log('Adding audio clip...')
}

function addCharacterMarker() {
  const newMarker = {
    id: Date.now(),
    time: currentTime.value,
    character: availableCharacters.value[0],
    action: 'new action'
  }
  characterMarkers.value.push(newMarker)
}

function exportTimeline() {
  const timelineData = {
    duration: totalDuration.value,
    fps: fps.value,
    videoClips: videoClips.value,
    audioClips: audioClips.value,
    characterMarkers: characterMarkers.value,
    musicSync: {
      enabled: musicSyncEnabled.value,
      bpm: musicBPM.value
    }
  }

  const blob = new Blob([JSON.stringify(timelineData, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'anime-timeline.json'
  a.click()
}

// Drawing methods
function drawWaveform() {
  if (!waveformCanvas.value || !audioClips.value.length) return

  const canvas = waveformCanvas.value
  const ctx = canvas.getContext('2d')
  const { width, height } = canvas

  ctx.clearRect(0, 0, width, height)

  // Draw waveform for first audio clip
  const clip = audioClips.value[0]
  const barWidth = width / clip.waveformBars.length

  ctx.fillStyle = '#ff6b35'
  clip.waveformBars.forEach((bar, index) => {
    const barHeight = (bar / 100) * height
    const x = index * barWidth
    const y = (height - barHeight) / 2

    ctx.fillRect(x, y, Math.max(1, barWidth - 1), barHeight)
  })

  // Draw playhead position on waveform
  const playheadX = (currentTime.value / totalDuration.value) * width
  ctx.strokeStyle = '#00ffff'
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(playheadX, 0)
  ctx.lineTo(playheadX, height)
  ctx.stroke()
}

// Lifecycle
onMounted(() => {
  nextTick(() => {
    if (timelineContainer.value) {
      timelineWidth.value = timelineContainer.value.offsetWidth
    }
    drawWaveform()
  })
})

// Watchers
watch(currentTime, () => {
  drawWaveform()
})

watch([audioClips, timelineWidth], () => {
  nextTick(() => {
    drawWaveform()
  })
})
</script>

<style scoped>
@import '../assets/cyberpunk-theme.css';

.video-timeline-interface {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--cp-bg-primary);
  color: var(--cp-text-primary);
  font-family: var(--cp-font-family);
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: var(--cp-bg-secondary);
  border-bottom: 1px solid var(--cp-border-primary);
}

.timeline-controls {
  display: flex;
  gap: 0.5rem;
}

.timeline-info {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.timecode {
  font-family: monospace;
  font-size: 1.1rem;
  color: var(--cp-accent-primary);
}

.fps-indicator {
  font-size: 0.8rem;
  color: var(--cp-text-secondary);
}

.timeline-tools {
  display: flex;
  gap: 0.5rem;
}

.timeline-container {
  flex: 1;
  position: relative;
  overflow-x: auto;
  overflow-y: hidden;
  background: var(--cp-bg-primary);
}

.time-ruler {
  height: 30px;
  position: relative;
  background: var(--cp-bg-secondary);
  border-bottom: 1px solid var(--cp-border-primary);
}

.time-tick {
  position: absolute;
  top: 0;
  height: 100%;
}

.tick-line {
  width: 1px;
  height: 100%;
  background: var(--cp-border-primary);
}

.tick-line.major {
  background: var(--cp-accent-primary);
  width: 2px;
}

.tick-label {
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.7rem;
  color: var(--cp-text-secondary);
  white-space: nowrap;
}

.timeline-track {
  min-height: 80px;
  border-bottom: 1px solid var(--cp-border-primary);
  display: flex;
}

.track-header {
  width: 150px;
  background: var(--cp-bg-secondary);
  padding: 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-right: 1px solid var(--cp-border-primary);
}

.track-title {
  font-weight: 600;
  color: var(--cp-text-primary);
  text-transform: uppercase;
  font-size: 0.9rem;
}

.track-controls {
  display: flex;
  gap: 0.25rem;
}

.track-button {
  background: none;
  border: 1px solid var(--cp-border-primary);
  color: var(--cp-text-secondary);
  padding: 0.25rem;
  border-radius: 3px;
  cursor: pointer;
  font-size: 0.8rem;
  transition: all var(--cp-transition-fast);
}

.track-button:hover {
  color: var(--cp-accent-primary);
  border-color: var(--cp-accent-primary);
}

.track-content {
  flex: 1;
  position: relative;
  padding: 0.5rem 0;
}

.video-clip, .audio-clip {
  position: absolute;
  height: 60px;
  background: var(--cp-gradient-primary);
  border: 1px solid var(--cp-border-primary);
  border-radius: 4px;
  cursor: pointer;
  overflow: hidden;
  transition: all var(--cp-transition-fast);
  display: flex;
  align-items: center;
}

.video-clip:hover, .audio-clip:hover {
  border-color: var(--cp-accent-primary);
  box-shadow: var(--cp-glow-orange);
}

.video-clip.selected, .audio-clip.selected {
  border-color: var(--cp-neon-cyan);
  box-shadow: var(--cp-glow-cyan);
}

.clip-thumbnail {
  width: 60px;
  height: 100%;
  overflow: hidden;
}

.clip-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.clip-info {
  padding: 0.5rem;
  flex: 1;
}

.clip-name {
  font-size: 0.8rem;
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.clip-duration, .clip-bpm {
  font-size: 0.7rem;
  color: var(--cp-text-secondary);
}

.clip-resize-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 8px;
  cursor: ew-resize;
  background: var(--cp-accent-primary);
  opacity: 0;
  transition: opacity var(--cp-transition-fast);
}

.clip-resize-handle.left {
  left: 0;
}

.clip-resize-handle.right {
  right: 0;
}

.video-clip:hover .clip-resize-handle,
.audio-clip:hover .clip-resize-handle {
  opacity: 0.7;
}

.waveform-container {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
}

.waveform-canvas {
  width: 100%;
  height: 60px;
  cursor: pointer;
}

.mini-waveform {
  display: flex;
  align-items: end;
  height: 40px;
  padding: 0 0.5rem;
  gap: 1px;
}

.waveform-bar {
  width: 2px;
  background: var(--cp-accent-primary);
  min-height: 2px;
  opacity: 0.7;
}

.beat-markers {
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
  width: 1px;
}

.beat-line {
  width: 100%;
  height: 100%;
  background: var(--cp-neon-cyan);
  opacity: 0.5;
}

.beat-marker.downbeat .beat-line {
  background: var(--cp-neon-green);
  width: 2px;
  opacity: 0.8;
}

.beat-indicator {
  position: absolute;
  top: -4px;
  left: 50%;
  transform: translateX(-50%);
  width: 6px;
  height: 6px;
  background: var(--cp-neon-cyan);
  border-radius: 50%;
}

.beat-marker.downbeat .beat-indicator {
  background: var(--cp-neon-green);
  width: 8px;
  height: 8px;
}

.character-marker {
  position: absolute;
  width: 80px;
  height: 60px;
  background: var(--cp-bg-secondary);
  border: 1px solid var(--cp-border-primary);
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 0.5rem;
  transition: all var(--cp-transition-fast);
}

.character-marker:hover {
  border-color: var(--cp-accent-primary);
}

.character-marker.selected {
  border-color: var(--cp-neon-purple);
  box-shadow: var(--cp-glow-purple);
}

.marker-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  overflow: hidden;
  margin-right: 0.5rem;
}

.marker-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.marker-info {
  flex: 1;
}

.character-name {
  font-size: 0.7rem;
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.marker-action {
  font-size: 0.6rem;
  color: var(--cp-text-secondary);
}

.playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  cursor: ew-resize;
  z-index: 10;
}

.playhead-line {
  width: 100%;
  height: 100%;
  background: var(--cp-neon-red);
  box-shadow: var(--cp-glow-orange);
}

.playhead-handle {
  position: absolute;
  top: -5px;
  left: 50%;
  transform: translateX(-50%);
  width: 12px;
  height: 12px;
  background: var(--cp-neon-red);
  border-radius: 50%;
  cursor: grab;
}

.playhead-handle:active {
  cursor: grabbing;
}

.music-sync-panel {
  background: var(--cp-bg-secondary);
  border-top: 1px solid var(--cp-border-primary);
  padding: 1rem;
}

.sync-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.sync-header h4 {
  margin: 0;
  color: var(--cp-accent-primary);
}

.sync-controls {
  display: flex;
  gap: 2rem;
  margin-bottom: 1rem;
}

.bpm-control {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.bpm-control label {
  font-size: 0.8rem;
  color: var(--cp-text-secondary);
}

.bpm-control input {
  width: 80px;
}

.sync-options {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.sync-options label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8rem;
  cursor: pointer;
}

.rhythm-visualizer {
  margin-top: 1rem;
}

.rhythm-pattern {
  display: flex;
  gap: 0.25rem;
}

.rhythm-beat {
  width: 30px;
  height: 30px;
  background: var(--cp-bg-primary);
  border: 1px solid var(--cp-border-primary);
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 0.8rem;
  transition: all var(--cp-transition-fast);
}

.rhythm-beat:hover {
  border-color: var(--cp-accent-primary);
}

.rhythm-beat.active {
  background: var(--cp-accent-primary);
  color: var(--cp-text-inverse);
}

.rhythm-beat.current {
  box-shadow: var(--cp-glow-cyan);
  border-color: var(--cp-neon-cyan);
}

.properties-panel {
  position: fixed;
  right: 1rem;
  top: 50%;
  transform: translateY(-50%);
  width: 300px;
  background: var(--cp-bg-secondary);
  border: 1px solid var(--cp-border-primary);
  border-radius: 8px;
  padding: 1rem;
  z-index: 100;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--cp-border-primary);
}

.panel-header h4 {
  margin: 0;
  color: var(--cp-accent-primary);
}

.property-group {
  margin-bottom: 1rem;
}

.property-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-size: 0.8rem;
  color: var(--cp-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

@media (max-width: 768px) {
  .timeline-header {
    flex-direction: column;
    gap: 1rem;
  }

  .track-header {
    width: 100px;
  }

  .properties-panel {
    position: static;
    width: 100%;
    transform: none;
    margin-top: 1rem;
  }

  .sync-controls {
    flex-direction: column;
    gap: 1rem;
  }
}</style>