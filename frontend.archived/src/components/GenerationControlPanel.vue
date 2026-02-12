<template>
  <div class="generation-control-panel">
    <!-- Header -->
    <div class="panel-header">
      <h3>Generation Controls</h3>
      <div class="vram-status" :class="{ 'warning': vramUsage > 80, 'critical': vramUsage > 95 }">
        <span class="vram-label">VRAM:</span>
        <span class="vram-usage">{{ formatBytes(vramUsed) }} / {{ formatBytes(vramTotal) }}</span>
        <div class="vram-bar">
          <div class="vram-fill" :style="{ width: vramUsage + '%' }"></div>
        </div>
      </div>
    </div>

    <!-- Explicit Generation Type Selection -->
    <div class="control-section generation-type-section">
      <label class="control-label">Generation Type</label>
      <div class="type-selector">
        <div class="type-options">
          <div @click="selectedGenerationType = 'image'"
               :class="['type-option', { 'selected': selectedGenerationType === 'image' }]">
            <i class="pi pi-image type-icon"></i>
            <span class="type-label">Generate Image</span>
            <span class="type-description">Single frame artwork</span>
          </div>
          <div @click="selectedGenerationType = 'video'"
               :class="['type-option', { 'selected': selectedGenerationType === 'video' }]">
            <i class="pi pi-video type-icon"></i>
            <span class="type-label">Generate Video</span>
            <span class="type-description">Animated sequence</span>
          </div>
        </div>
      </div>
      <div v-if="!selectedGenerationType" class="selection-warning">
        <i class="pi pi-exclamation-triangle"></i>
        <span>Please select generation type before proceeding</span>
      </div>
    </div>

    <!-- Quality Presets -->
    <div class="control-section">
      <label class="control-label">Quality Preset</label>
      <select v-model="selectedPreset" @change="applyPreset" class="control-select">
        <option value="">Select preset...</option>
        <option v-for="preset in qualityPresets" :key="preset.name" :value="preset.name">
          {{ preset.name }} - {{ preset.description }}
        </option>
      </select>
      <div class="preset-info" v-if="currentPresetInfo">
        <div class="info-item">
          <span class="info-label">Estimated Time:</span>
          <span class="info-value">{{ currentPresetInfo.estimated_time }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">Quality Level:</span>
          <span class="info-value">{{ currentPresetInfo.quality_level }}/10</span>
        </div>
      </div>
    </div>

    <!-- Model Selection -->
    <div class="control-section">
      <label class="control-label">Model</label>
      <select v-model="selectedModel" class="control-select">
        <option value="">Select model...</option>
        <option v-for="model in availableModels" :key="model.name" :value="model.name">
          {{ model.name }} ({{ formatBytes(model.size) }})
        </option>
      </select>
      <div class="model-info" v-if="currentModelInfo">
        <div class="info-item">
          <span class="info-label">Type:</span>
          <span class="info-value">{{ currentModelInfo.type }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">VRAM Required:</span>
          <span class="info-value">{{ formatBytes(currentModelInfo.vram_required) }}</span>
        </div>
      </div>
    </div>

    <!-- Generation Settings -->
    <div class="control-section">
      <label class="control-label">Generation Settings</label>

      <div class="setting-row">
        <label class="setting-label">Steps:</label>
        <input
          type="range"
          v-model="settings.steps"
          min="10"
          max="100"
          class="setting-slider"
        />
        <span class="setting-value">{{ settings.steps }}</span>
      </div>

      <div class="setting-row">
        <label class="setting-label">CFG Scale:</label>
        <input
          type="range"
          v-model="settings.cfgScale"
          min="1"
          max="20"
          step="0.5"
          class="setting-slider"
        />
        <span class="setting-value">{{ settings.cfgScale }}</span>
      </div>

      <div class="setting-row">
        <label class="setting-label">Seed:</label>
        <input
          type="number"
          v-model="settings.seed"
          class="setting-input"
          placeholder="Random"
        />
        <button @click="randomizeSeed" class="setting-button">
          <i class="pi pi-refresh"></i>
        </button>
      </div>

      <div class="setting-row" v-if="selectedGenerationType === 'image'">
        <label class="setting-label">Batch Size:</label>
        <select v-model="settings.batchSize" class="setting-select">
          <option value="1">1 image</option>
          <option value="2">2 images</option>
          <option value="4">4 images</option>
        </select>
      </div>

      <!-- Video-specific settings -->
      <div v-if="selectedGenerationType === 'video'" class="video-settings">
        <div class="setting-row">
          <label class="setting-label">Duration:</label>
          <select v-model="settings.videoDuration" class="setting-select">
            <option value="2">2 seconds</option>
            <option value="5">5 seconds</option>
            <option value="10">10 seconds</option>
            <option value="30">30 seconds</option>
          </select>
        </div>

        <div class="setting-row">
          <label class="setting-label">Frame Rate:</label>
          <select v-model="settings.frameRate" class="setting-select">
            <option value="8">8 FPS (Smooth)</option>
            <option value="12">12 FPS (Standard)</option>
            <option value="24">24 FPS (Cinematic)</option>
          </select>
        </div>

        <div class="setting-row">
          <label class="setting-label">Motion Strength:</label>
          <input
            type="range"
            v-model="settings.motionStrength"
            min="0.1"
            max="1.0"
            step="0.1"
            class="setting-slider"
          />
          <span class="setting-value">{{ settings.motionStrength }}</span>
        </div>
      </div>
    </div>

    <!-- Advanced Settings Toggle -->
    <div class="control-section">
      <button @click="showAdvanced = !showAdvanced" class="toggle-button">
        <i :class="showAdvanced ? 'pi pi-chevron-down' : 'pi pi-chevron-right'"></i>
        Advanced Settings
      </button>

      <div v-if="showAdvanced" class="advanced-settings">
        <div class="setting-row">
          <label class="setting-label">Sampler:</label>
          <select v-model="settings.sampler" class="setting-select">
            <option value="euler_a">Euler A</option>
            <option value="euler">Euler</option>
            <option value="dpm++_2m">DPM++ 2M</option>
            <option value="dpm++_sde">DPM++ SDE</option>
          </select>
        </div>

        <div class="setting-row">
          <label class="setting-label">Scheduler:</label>
          <select v-model="settings.scheduler" class="setting-select">
            <option value="normal">Normal</option>
            <option value="karras">Karras</option>
            <option value="exponential">Exponential</option>
          </select>
        </div>

        <div class="setting-row">
          <label class="setting-label">Denoise Strength:</label>
          <input
            type="range"
            v-model="settings.denoiseStrength"
            min="0"
            max="1"
            step="0.05"
            class="setting-slider"
          />
          <span class="setting-value">{{ settings.denoiseStrength }}</span>
        </div>
      </div>
    </div>

    <!-- Action Buttons -->
    <div class="control-actions">
      <button @click="saveSettings" class="action-button secondary">
        <i class="pi pi-save"></i>
        Save Settings
      </button>
      <button @click="resetToDefaults" class="action-button secondary">
        <i class="pi pi-refresh"></i>
        Reset
      </button>
      <button @click="startGeneration" class="action-button primary" :disabled="!canGenerate">
        <i class="pi pi-play"></i>
        {{ generating ? 'Generating...' : 'Generate' }}
      </button>
    </div>
  </div>
</template>

<script>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import API, { buildUrl } from '@/config/api'

export default {
  name: 'GenerationControlPanel',
  emits: ['generate', 'settings-changed'],
  setup(props, { emit }) {
    const qualityPresets = ref([])
    const availableModels = ref([])
    const selectedPreset = ref('')
    const selectedModel = ref('')
    const showAdvanced = ref(false)
    const generating = ref(false)
    const selectedGenerationType = ref('')

    // VRAM tracking
    const vramUsed = ref(0)
    const vramTotal = ref(12000000000) // 12GB default
    const vramUsage = computed(() => vramTotal.value > 0 ? (vramUsed.value / vramTotal.value) * 100 : 0)

    // Generation settings
    const settings = reactive({
      steps: 20,
      cfgScale: 7.5,
      seed: null,
      batchSize: 1,
      sampler: 'euler_a',
      scheduler: 'normal',
      denoiseStrength: 0.75,
      // Video-specific settings
      videoDuration: 5,
      frameRate: 12,
      motionStrength: 0.7
    })

    // Computed properties
    const currentPresetInfo = computed(() => {
      if (!selectedPreset.value) return null
      return qualityPresets.value.find(p => p.name === selectedPreset.value)
    })

    const currentModelInfo = computed(() => {
      if (!selectedModel.value) return null
      return availableModels.value.find(m => m.name === selectedModel.value)
    })

    const canGenerate = computed(() => {
      return selectedModel.value && !generating.value && vramUsage.value < 95 && selectedGenerationType.value
    })

    // Methods - Using centralized API configuration
    const loadQualityPresets = async () => {
      try {
        const response = await fetch(buildUrl(API.QUALITY_PRESETS))
        qualityPresets.value = await response.json()
      } catch (error) {
        console.error('Failed to load quality presets:', error)
      }
    }

    const loadAvailableModels = async () => {
      try {
        const response = await fetch(buildUrl(API.MODELS))
        availableModels.value = await response.json()
      } catch (error) {
        console.error('Failed to load models:', error)
      }
    }

    const updateVramUsage = async () => {
      try {
        const response = await fetch(buildUrl(API.VRAM_STATUS))
        const data = await response.json()
        vramUsed.value = data.used
        vramTotal.value = data.total
      } catch (error) {
        console.error('Failed to get VRAM status:', error)
      }
    }

    const applyPreset = () => {
      const preset = currentPresetInfo.value
      if (preset && preset.settings) {
        Object.assign(settings, preset.settings)
        emit('settings-changed', settings)
      }
    }

    const randomizeSeed = () => {
      settings.seed = Math.floor(Math.random() * 2147483647)
    }

    const saveSettings = () => {
      localStorage.setItem('anime-generation-settings', JSON.stringify(settings))
      // Also emit to parent
      emit('settings-changed', settings)
    }

    const resetToDefaults = () => {
      Object.assign(settings, {
        steps: 20,
        cfgScale: 7.5,
        seed: null,
        batchSize: 1,
        sampler: 'euler_a',
        scheduler: 'normal',
        denoiseStrength: 0.75
      })
      selectedPreset.value = ''
      emit('settings-changed', settings)
    }

    const startGeneration = () => {
      if (!canGenerate.value) return

      const generationConfig = {
        type: selectedGenerationType.value,
        model: selectedModel.value,
        preset: selectedPreset.value,
        settings: { ...settings }
      }

      emit('generate', generationConfig)
    }

    const formatBytes = (bytes) => {
      if (!bytes) return '0 B'
      const k = 1024
      const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
    }

    // Load saved settings
    const loadSavedSettings = () => {
      const saved = localStorage.getItem('anime-generation-settings')
      if (saved) {
        try {
          Object.assign(settings, JSON.parse(saved))
        } catch (error) {
          console.warn('Failed to load saved settings:', error)
        }
      }
    }

    // Lifecycle
    onMounted(() => {
      loadQualityPresets()
      loadAvailableModels()
      loadSavedSettings()
      updateVramUsage()

      // Update VRAM every 5 seconds
      setInterval(updateVramUsage, 5000)
    })

    // Watch for settings changes
    watch(settings, (newSettings) => {
      emit('settings-changed', newSettings)
    }, { deep: true })

    return {
      qualityPresets,
      availableModels,
      selectedPreset,
      selectedModel,
      selectedGenerationType,
      showAdvanced,
      generating,
      vramUsed,
      vramTotal,
      vramUsage,
      settings,
      currentPresetInfo,
      currentModelInfo,
      canGenerate,
      applyPreset,
      randomizeSeed,
      saveSettings,
      resetToDefaults,
      startGeneration,
      formatBytes
    }
  }
}
</script>

<style scoped>
.generation-control-panel {
  background: #0f0f0f;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 1rem;
  color: #e0e0e0;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #333;
}

.panel-header h3 {
  margin: 0;
  color: #3b82f6;
  font-size: 1.2rem;
  font-weight: 600;
}

.vram-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
}

.vram-status.warning {
  color: #f59e0b;
}

.vram-status.critical {
  color: #ef4444;
}

.vram-label {
  font-weight: 600;
}

.vram-bar {
  width: 60px;
  height: 6px;
  background: #1a1a1a;
  border-radius: 3px;
  overflow: hidden;
}

.vram-fill {
  height: 100%;
  background: #3b82f6;
  transition: width 0.3s ease;
}

.vram-status.warning .vram-fill {
  background: #f59e0b;
}

.vram-status.critical .vram-fill {
  background: #ef4444;
}

.control-section {
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #222;
}

.control-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.control-label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 600;
  color: #3b82f6;
  font-size: 0.9rem;
}

.control-select, .setting-select, .setting-input {
  width: 100%;
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  font-family: inherit;
  font-size: 0.9rem;
}

.control-select:focus, .setting-select:focus, .setting-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
}

.preset-info, .model-info {
  margin-top: 0.75rem;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
}

.info-item {
  display: flex;
  justify-content: space-between;
  padding: 0.25rem 0.5rem;
  background: #1a1a1a;
  border-radius: 4px;
  font-size: 0.8rem;
}

.info-label {
  color: #999;
}

.info-value {
  color: #e0e0e0;
  font-weight: 500;
}

.setting-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.setting-label {
  min-width: 100px;
  font-size: 0.9rem;
  color: #ccc;
}

.setting-slider {
  flex: 1;
  height: 4px;
  background: #333;
  border-radius: 2px;
  outline: none;
  -webkit-appearance: none;
}

.setting-slider::-webkit-slider-thumb {
  appearance: none;
  width: 16px;
  height: 16px;
  background: #3b82f6;
  border-radius: 50%;
  cursor: pointer;
}

.setting-slider::-moz-range-thumb {
  width: 16px;
  height: 16px;
  background: #3b82f6;
  border-radius: 50%;
  cursor: pointer;
  border: none;
}

.setting-value {
  min-width: 40px;
  text-align: right;
  font-weight: 500;
  color: #3b82f6;
}

.setting-input {
  flex: 1;
  max-width: 120px;
}

.setting-button {
  padding: 0.25rem 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
  font-size: 0.8rem;
}

.setting-button:hover {
  background: #333;
}

.toggle-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: none;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.9rem;
  width: 100%;
  justify-content: flex-start;
}

.toggle-button:hover {
  background: #1a1a1a;
}

.advanced-settings {
  margin-top: 1rem;
  padding: 1rem;
  background: #0a0a0a;
  border: 1px solid #222;
  border-radius: 4px;
}

.control-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid #333;
}

.action-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border: 1px solid #333;
  border-radius: 4px;
  font-family: inherit;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-button.primary {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
  flex: 1;
}

.action-button.primary:hover:not(:disabled) {
  background: #2563eb;
}

.action-button.primary:disabled {
  background: #374151;
  color: #6b7280;
  cursor: not-allowed;
}

.action-button.secondary {
  background: #1a1a1a;
  color: #e0e0e0;
}

.action-button.secondary:hover {
  background: #333;
}

/* Generation Type Selection */
.generation-type-section {
  background: #0f0f0f;
  border: 2px solid #333;
  border-radius: 8px;
  padding: 1rem;
}

.type-selector {
  margin-bottom: 1rem;
}

.type-options {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.type-option {
  background: #1a1a1a;
  border: 2px solid #333;
  border-radius: 8px;
  padding: 1.5rem 1rem;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  position: relative;
}

.type-option:hover {
  border-color: #3b82f6;
  transform: translateY(-2px);
}

.type-option.selected {
  background: #1e2a4a;
  border-color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.type-option.selected::before {
  content: '✓';
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  background: #3b82f6;
  color: white;
  border-radius: 50%;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-weight: bold;
}

.type-icon {
  font-size: 2rem;
  color: #3b82f6;
  margin-bottom: 0.75rem;
}

.type-label {
  font-weight: 600;
  color: #e0e0e0;
  margin-bottom: 0.25rem;
  font-size: 1rem;
}

.type-description {
  font-size: 0.85rem;
  color: #999;
}

.selection-warning {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: #4a2d2d;
  border: 1px solid #ef4444;
  border-radius: 4px;
  color: #fca5a5;
  font-size: 0.9rem;
}

.selection-warning i {
  color: #ef4444;
}

/* Video Settings */
.video-settings {
  background: #0a0a0a;
  border-radius: 6px;
  padding: 1rem;
  margin-top: 0.5rem;
  border: 1px solid #1e40af;
}

.video-settings .setting-row {
  margin-bottom: 1rem;
}

.video-settings .setting-row:last-child {
  margin-bottom: 0;
}
</style>