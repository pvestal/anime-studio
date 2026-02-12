<template>
  <div class="generation-mode-selector">
    <h3 class="mode-title">Generation Mode</h3>

    <div class="mode-cards">
      <div
        v-for="mode in modes"
        :key="mode.id"
        :class="['mode-card', { active: selectedMode === mode.id }]"
        @click="selectMode(mode.id)"
      >
        <div class="mode-icon">
          <component :is="mode.icon" :size="32" />
        </div>

        <div class="mode-content">
          <h4 class="mode-name">{{ mode.name }}</h4>
          <p class="mode-description">{{ mode.description }}</p>

          <div class="mode-stats">
            <div class="stat">
              <span class="stat-icon">⏱️</span>
              <span class="stat-value">{{ mode.time }}</span>
            </div>
            <div class="stat">
              <span class="stat-icon">✨</span>
              <span class="stat-value">{{ mode.quality }}</span>
            </div>
            <div class="stat">
              <span class="stat-icon">📐</span>
              <span class="stat-value">{{ mode.resolution }}</span>
            </div>
          </div>
        </div>

        <div v-if="selectedMode === mode.id" class="selected-indicator">
          ✓
        </div>
      </div>
    </div>

    <!-- Advanced Settings Toggle -->
    <div class="advanced-toggle" @click="showAdvanced = !showAdvanced">
      <span>{{ showAdvanced ? '▼' : '▶' }}</span>
      Advanced Settings
    </div>

    <!-- Advanced Settings Panel -->
    <transition name="slide">
      <div v-if="showAdvanced" class="advanced-settings">
        <div class="setting-group">
          <label>Steps</label>
          <input
            type="number"
            v-model.number="customSettings.steps"
            :min="4"
            :max="50"
            @input="updateCustomSettings"
          />
          <span class="setting-hint">{{ stepsHint }}</span>
        </div>

        <div class="setting-group">
          <label>CFG Scale</label>
          <input
            type="range"
            v-model.number="customSettings.cfgScale"
            min="1"
            max="20"
            step="0.5"
            @input="updateCustomSettings"
          />
          <span class="setting-value">{{ customSettings.cfgScale }}</span>
        </div>

        <div class="setting-group">
          <label>Sampler</label>
          <select v-model="customSettings.sampler" @change="updateCustomSettings">
            <option value="euler">Euler (Fast)</option>
            <option value="euler_a">Euler A (Varied)</option>
            <option value="dpm_fast">DPM Fast</option>
            <option value="dpmpp_2m">DPM++ 2M (Balanced)</option>
            <option value="dpmpp_2m_sde">DPM++ 2M SDE (Quality)</option>
            <option value="ddim">DDIM (Stable)</option>
          </select>
        </div>

        <div class="setting-group">
          <label>Batch Size</label>
          <input
            type="number"
            v-model.number="customSettings.batchSize"
            :min="1"
            :max="maxBatchSize"
            @input="updateCustomSettings"
          />
          <span class="setting-hint">Generate multiple variations</span>
        </div>

        <div class="setting-group checkbox-group">
          <label>
            <input
              type="checkbox"
              v-model="customSettings.enablePreview"
              @change="updateCustomSettings"
            />
            Enable real-time preview
          </label>
        </div>

        <div class="setting-group checkbox-group">
          <label>
            <input
              type="checkbox"
              v-model="customSettings.enableAutoRecovery"
              @change="updateCustomSettings"
            />
            Auto-recover from errors
          </label>
        </div>

        <button class="reset-button" @click="resetToDefaults">
          Reset to Mode Defaults
        </button>
      </div>
    </transition>

    <!-- Performance Estimate -->
    <div class="performance-estimate">
      <h4>Estimated Performance</h4>
      <div class="estimate-grid">
        <div class="estimate-item">
          <span class="estimate-label">Time:</span>
          <span class="estimate-value">{{ estimatedTime }}</span>
        </div>
        <div class="estimate-item">
          <span class="estimate-label">VRAM:</span>
          <span class="estimate-value">{{ estimatedVRAM }}</span>
        </div>
        <div class="estimate-item">
          <span class="estimate-label">Quality:</span>
          <div class="quality-bar">
            <div
              class="quality-fill"
              :style="{ width: estimatedQuality + '%' }"
              :class="qualityClass"
            ></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useAnimeStore } from '@/stores/anime'
import {
  Zap as DraftIcon,
  Cpu as StandardIcon,
  Sparkles as QualityIcon
} from 'lucide-vue-next'

const animeStore = useAnimeStore()

const modes = ref([
  {
    id: 'draft',
    name: 'Draft Mode',
    icon: DraftIcon,
    description: 'Quick iterations and previews',
    time: '<30 sec',
    quality: 'Good',
    resolution: '512x512',
    defaults: {
      steps: 8,
      cfgScale: 5.0,
      sampler: 'dpm_fast',
      width: 512,
      height: 512
    }
  },
  {
    id: 'standard',
    name: 'Standard Mode',
    icon: StandardIcon,
    description: 'Balanced speed and quality',
    time: '30-60 sec',
    quality: 'Great',
    resolution: '768x768',
    defaults: {
      steps: 15,
      cfgScale: 6.5,
      sampler: 'dpmpp_2m',
      width: 768,
      height: 768
    }
  },
  {
    id: 'quality',
    name: 'High Quality',
    icon: QualityIcon,
    description: 'Maximum quality output',
    time: '60-120 sec',
    quality: 'Excellent',
    resolution: '1024x1024',
    defaults: {
      steps: 25,
      cfgScale: 7.5,
      sampler: 'dpmpp_2m_sde',
      width: 1024,
      height: 1024
    }
  }
])

const selectedMode = ref('standard')
const showAdvanced = ref(false)

const customSettings = ref({
  steps: 15,
  cfgScale: 6.5,
  sampler: 'dpmpp_2m',
  batchSize: 1,
  enablePreview: true,
  enableAutoRecovery: true
})

const currentModeDefaults = computed(() => {
  const mode = modes.value.find(m => m.id === selectedMode.value)
  return mode ? mode.defaults : {}
})

const maxBatchSize = computed(() => {
  // Limit batch size based on mode for VRAM management
  switch(selectedMode.value) {
    case 'draft': return 8
    case 'standard': return 4
    case 'quality': return 2
    default: return 4
  }
})

const stepsHint = computed(() => {
  if (customSettings.value.steps < 8) return 'Very fast, lower quality'
  if (customSettings.value.steps < 15) return 'Fast generation'
  if (customSettings.value.steps < 25) return 'Balanced'
  if (customSettings.value.steps < 35) return 'High quality'
  return 'Maximum quality, slower'
})

const estimatedTime = computed(() => {
  const baseTime = customSettings.value.steps * 1.5 // Rough estimate
  const batchMultiplier = Math.sqrt(customSettings.value.batchSize) // Batch doesn't scale linearly
  const totalSeconds = baseTime * batchMultiplier

  if (totalSeconds < 30) return `~${Math.round(totalSeconds)}s`
  if (totalSeconds < 120) return `~${Math.round(totalSeconds / 10) * 10}s`
  return `~${Math.round(totalSeconds / 60)}min`
})

const estimatedVRAM = computed(() => {
  const mode = modes.value.find(m => m.id === selectedMode.value)
  const [width, height] = mode.resolution.split('x').map(Number)

  // Rough VRAM calculation
  const baseVRAM = (width * height) / (512 * 512) * 2000 // MB
  const batchVRAM = baseVRAM * customSettings.value.batchSize

  if (batchVRAM < 4000) return `~${Math.round(batchVRAM / 100) * 100}MB`
  return `~${(batchVRAM / 1000).toFixed(1)}GB`
})

const estimatedQuality = computed(() => {
  const stepsScore = Math.min(customSettings.value.steps / 30 * 100, 100)
  const cfgScore = Math.min(customSettings.value.cfgScale / 10 * 100, 100)
  const samplerScore = ['euler', 'dpm_fast'].includes(customSettings.value.sampler) ? 70 : 90

  return Math.round((stepsScore + cfgScore + samplerScore) / 3)
})

const qualityClass = computed(() => {
  if (estimatedQuality.value < 50) return 'quality-low'
  if (estimatedQuality.value < 75) return 'quality-medium'
  return 'quality-high'
})

function selectMode(modeId) {
  selectedMode.value = modeId
  const mode = modes.value.find(m => m.id === modeId)

  if (mode) {
    // Update custom settings to mode defaults
    customSettings.value = {
      ...customSettings.value,
      ...mode.defaults
    }

    // Update store
    animeStore.setGenerationMode(modeId, mode.defaults)
  }
}

function updateCustomSettings() {
  animeStore.updateGenerationSettings(customSettings.value)
}

function resetToDefaults() {
  const mode = modes.value.find(m => m.id === selectedMode.value)
  if (mode) {
    customSettings.value = {
      ...customSettings.value,
      ...mode.defaults
    }
    updateCustomSettings()
  }
}

// Initialize with default mode
selectMode('standard')
</script>

<style scoped>
.generation-mode-selector {
  background: #1a1a1a;
  border-radius: 12px;
  padding: 20px;
  color: #fff;
}

.mode-title {
  margin: 0 0 20px 0;
  font-size: 1.2em;
  color: #fff;
}

.mode-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 15px;
  margin-bottom: 20px;
}

.mode-card {
  background: #2a2a2a;
  border: 2px solid #3a3a3a;
  border-radius: 8px;
  padding: 15px;
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
}

.mode-card:hover {
  background: #333;
  border-color: #4a4a4a;
  transform: translateY(-2px);
}

.mode-card.active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-color: #667eea;
}

.mode-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 50px;
  height: 50px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 50%;
  margin-bottom: 10px;
}

.mode-name {
  margin: 0 0 5px 0;
  font-size: 1.1em;
}

.mode-description {
  margin: 0 0 15px 0;
  font-size: 0.9em;
  opacity: 0.8;
}

.mode-stats {
  display: flex;
  gap: 15px;
  font-size: 0.85em;
}

.stat {
  display: flex;
  align-items: center;
  gap: 5px;
}

.stat-icon {
  font-size: 1.1em;
}

.stat-value {
  opacity: 0.9;
}

.selected-indicator {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 24px;
  height: 24px;
  background: #4ade80;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
}

.advanced-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  background: #2a2a2a;
  border-radius: 6px;
  cursor: pointer;
  user-select: none;
  margin-bottom: 15px;
}

.advanced-toggle:hover {
  background: #333;
}

.advanced-settings {
  background: #2a2a2a;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.setting-group {
  margin-bottom: 15px;
}

.setting-group label {
  display: block;
  margin-bottom: 5px;
  font-size: 0.9em;
  opacity: 0.9;
}

.setting-group input[type="number"],
.setting-group input[type="range"],
.setting-group select {
  width: 100%;
  padding: 8px;
  background: #1a1a1a;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  color: #fff;
}

.setting-group input[type="range"] {
  padding: 0;
}

.setting-hint,
.setting-value {
  display: inline-block;
  margin-top: 5px;
  font-size: 0.85em;
  opacity: 0.7;
}

.checkbox-group label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.reset-button {
  width: 100%;
  padding: 10px;
  background: #3a3a3a;
  border: none;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  margin-top: 15px;
}

.reset-button:hover {
  background: #4a4a4a;
}

.performance-estimate {
  background: #2a2a2a;
  border-radius: 8px;
  padding: 15px;
}

.performance-estimate h4 {
  margin: 0 0 15px 0;
  font-size: 1em;
}

.estimate-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 15px;
}

.estimate-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.estimate-label {
  font-size: 0.85em;
  opacity: 0.7;
}

.estimate-value {
  font-size: 1.1em;
  font-weight: bold;
}

.quality-bar {
  width: 100%;
  height: 8px;
  background: #1a1a1a;
  border-radius: 4px;
  overflow: hidden;
}

.quality-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.quality-low { background: #ef4444; }
.quality-medium { background: #f59e0b; }
.quality-high { background: #4ade80; }

.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  max-height: 0;
  opacity: 0;
  transform: translateY(-10px);
}
</style>