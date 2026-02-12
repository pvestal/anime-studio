<template>
  <div class="cp-character-panel cp-fade-in">
    <div class="character-header">
      <h3>Character Generation Controls</h3>
      <div class="character-actions">
        <button class="cp-button neon-cyan" @click="randomizeParameters">
          <i class="pi pi-refresh"></i> Randomize
        </button>
        <button class="cp-button primary" @click="generateCharacter" :disabled="generating">
          <i class="pi pi-play"></i> {{ generating ? 'Generating...' : 'Generate' }}
        </button>
      </div>
    </div>

    <div class="parameter-grid">
      <!-- Character Type -->
      <div class="parameter-group">
        <label>Character Type</label>
        <select v-model="parameters.characterType" class="cp-input">
          <option value="protagonist">Protagonist</option>
          <option value="antagonist">Antagonist</option>
          <option value="supporting">Supporting Character</option>
          <option value="background">Background Character</option>
          <option value="creature">Creature/Monster</option>
        </select>
      </div>

      <!-- Art Style -->
      <div class="parameter-group">
        <label>Art Style</label>
        <select v-model="parameters.artStyle" class="cp-input">
          <option value="cyberpunk">Cyberpunk</option>
          <option value="psychological_thriller">Psychological Thriller</option>
          <option value="traditional_anime">Traditional Anime</option>
          <option value="dark_fantasy">Dark Fantasy</option>
          <option value="industrial">Industrial</option>
        </select>
      </div>

      <!-- Age Range -->
      <div class="cp-parameter-slider">
        <label>Age: {{ parameters.age }}</label>
        <input
          type="range"
          v-model="parameters.age"
          min="8"
          max="80"
          class="cp-slider"
        />
      </div>

      <!-- Cyberpunk Tech Level -->
      <div class="cp-parameter-slider">
        <label>Tech Enhancement: {{ parameters.techLevel }}%</label>
        <input
          type="range"
          v-model="parameters.techLevel"
          min="0"
          max="100"
          class="cp-slider"
        />
      </div>

      <!-- Psychological Intensity -->
      <div class="cp-parameter-slider">
        <label>Psychological Intensity: {{ parameters.psychIntensity }}%</label>
        <input
          type="range"
          v-model="parameters.psychIntensity"
          min="0"
          max="100"
          class="cp-slider"
        />
      </div>

      <!-- Lighting -->
      <div class="parameter-group">
        <label>Lighting</label>
        <select v-model="parameters.lighting" class="cp-input">
          <option value="neon_glow">Neon Glow</option>
          <option value="industrial_harsh">Industrial Harsh</option>
          <option value="ambient_dark">Ambient Dark</option>
          <option value="backlighting">Dramatic Backlighting</option>
          <option value="natural">Natural Light</option>
        </select>
      </div>

      <!-- Color Palette -->
      <div class="parameter-group">
        <label>Color Palette</label>
        <div class="color-palette-grid">
          <div
            v-for="palette in colorPalettes"
            :key="palette.name"
            :class="['color-swatch', { active: parameters.colorPalette === palette.name }]"
            @click="parameters.colorPalette = palette.name"
            :style="{ background: palette.gradient }"
          >
            <span>{{ palette.name }}</span>
          </div>
        </div>
      </div>

      <!-- Character Mood -->
      <div class="parameter-group">
        <label>Character Mood</label>
        <div class="mood-grid">
          <button
            v-for="mood in moods"
            :key="mood"
            :class="['mood-button', { active: parameters.mood === mood }]"
            @click="parameters.mood = mood"
          >
            {{ mood }}
          </button>
        </div>
      </div>

      <!-- Advanced Settings -->
      <div class="parameter-group advanced-settings">
        <label>
          <input type="checkbox" v-model="parameters.enableGlow" />
          Enable Neon Glow Effects
        </label>
        <label>
          <input type="checkbox" v-model="parameters.enableParticles" />
          Add Atmospheric Particles
        </label>
        <label>
          <input type="checkbox" v-model="parameters.enableMotionBlur" />
          Enable Motion Blur
        </label>
      </div>

      <!-- Model Selection -->
      <div class="parameter-group">
        <label>AI Model</label>
        <select v-model="selectedModel" class="cp-input" @change="updateModel">
          <option v-for="model in availableModels" :key="model.name" :value="model.name">
            {{ model.display_name }} - {{ model.description }}
          </option>
        </select>
      </div>

      <!-- Quality Preset -->
      <div class="parameter-group">
        <label>Quality Preset</label>
        <select v-model="selectedQuality" class="cp-input" @change="updateQuality">
          <option v-for="preset in qualityPresets" :key="preset.name" :value="preset.name">
            {{ preset.display_name }} - {{ preset.description }}
          </option>
        </select>
      </div>

      <!-- Custom Prompt -->
      <div class="parameter-group full-width">
        <label>Custom Prompt Enhancement</label>
        <textarea
          v-model="parameters.customPrompt"
          class="cp-input"
          rows="3"
          placeholder="Add specific details, clothing, expressions, environment..."
        ></textarea>
      </div>
    </div>

    <!-- Generation Progress -->
    <div v-if="generating" class="generation-progress">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: generationProgress + '%' }"></div>
      </div>
      <div class="progress-text">{{ generationStatus }}</div>
    </div>

    <!-- Generated Character Preview -->
    <div v-if="generatedCharacter" class="character-preview">
      <h4>Generated Character</h4>
      <div class="preview-grid">
        <div class="preview-image">
          <img :src="generatedCharacter.imageUrl" alt="Generated Character" />
        </div>
        <div class="preview-details">
          <div class="detail-item">
            <strong>Type:</strong> {{ generatedCharacter.type }}
          </div>
          <div class="detail-item">
            <strong>Style:</strong> {{ generatedCharacter.style }}
          </div>
          <div class="detail-item">
            <strong>Prompt:</strong> {{ generatedCharacter.prompt }}
          </div>
        </div>
      </div>
      <div class="preview-actions">
        <button class="cp-button" @click="useCharacter">Use in Scene</button>
        <button class="cp-button" @click="saveCharacter">Save to Library</button>
        <button class="cp-button" @click="regenerateVariation">Generate Variation</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

// Props and emits
const emit = defineEmits(['character-generated', 'character-selected'])

// Reactive data
const generating = ref(false)
const generationProgress = ref(0)
const generationStatus = ref('')
const generatedCharacter = ref(null)

const parameters = ref({
  characterType: 'protagonist',
  artStyle: 'cyberpunk',
  age: 25,
  techLevel: 50,
  psychIntensity: 30,
  lighting: 'neon_glow',
  colorPalette: 'cyberpunk_orange',
  mood: 'determined',
  enableGlow: true,
  enableParticles: false,
  enableMotionBlur: false,
  customPrompt: ''
})

// Model and Quality Selection
const selectedModel = ref('')
const selectedQuality = ref('')
const availableModels = ref([])
const qualityPresets = ref([])

// Color palettes based on generated anime frames
const colorPalettes = [
  {
    name: 'cyberpunk_orange',
    gradient: 'linear-gradient(45deg, #ff6b35, #ffaa44)'
  },
  {
    name: 'neon_cyan',
    gradient: 'linear-gradient(45deg, #00ffff, #0088ff)'
  },
  {
    name: 'purple_psych',
    gradient: 'linear-gradient(45deg, #8a2be2, #da70d6)'
  },
  {
    name: 'industrial_grey',
    gradient: 'linear-gradient(45deg, #666666, #999999)'
  },
  {
    name: 'warm_natural',
    gradient: 'linear-gradient(45deg, #deb887, #f4a460)'
  }
]

const moods = [
  'determined', 'mysterious', 'aggressive', 'calm', 'fearful',
  'confident', 'brooding', 'manic', 'contemplative', 'menacing'
]

// Methods
async function generateCharacter() {
  generating.value = true
  generationProgress.value = 0
  generatedCharacter.value = null

  try {
    // Simulate generation progress
    const steps = [
      { progress: 20, status: 'Analyzing parameters...' },
      { progress: 40, status: 'Building character prompt...' },
      { progress: 60, status: 'Generating base character...' },
      { progress: 80, status: 'Applying style effects...' },
      { progress: 100, status: 'Finalizing character...' }
    ]

    for (const step of steps) {
      generationProgress.value = step.progress
      generationStatus.value = step.status
      await new Promise(resolve => setTimeout(resolve, 1000))
    }

    // Create the character generation prompt
    const prompt = buildCharacterPrompt()

    // Call the actual generation API (placeholder for now)
    const response = await fetch('/api/anime/generate-character', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, parameters: parameters.value })
    })

    if (response.ok) {
      generatedCharacter.value = await response.json()
      emit('character-generated', generatedCharacter.value)
    } else {
      throw new Error('Generation failed')
    }

  } catch (error) {
    console.error('Character generation failed:', error)
    generationStatus.value = 'Generation failed'
  } finally {
    generating.value = false
  }
}

function buildCharacterPrompt() {
  const { characterType, artStyle, age, lighting, colorPalette, mood, customPrompt } = parameters.value

  let prompt = `${characterType} character, ${artStyle} style, age ${age}, ${mood} expression, ${lighting} lighting`

  if (parameters.value.techLevel > 50) {
    prompt += ', cybernetic enhancements, tech elements'
  }

  if (parameters.value.psychIntensity > 60) {
    prompt += ', psychological thriller atmosphere, intense gaze, dark undertones'
  }

  if (parameters.value.enableGlow) {
    prompt += ', neon glow effects, atmospheric lighting'
  }

  if (parameters.value.enableParticles) {
    prompt += ', atmospheric particles, dust motes, environmental effects'
  }

  if (customPrompt) {
    prompt += `, ${customPrompt}`
  }

  return prompt
}

function randomizeParameters() {
  parameters.value.age = Math.floor(Math.random() * 72) + 8
  parameters.value.techLevel = Math.floor(Math.random() * 100)
  parameters.value.psychIntensity = Math.floor(Math.random() * 100)
  parameters.value.lighting = ['neon_glow', 'industrial_harsh', 'ambient_dark', 'backlighting', 'natural'][Math.floor(Math.random() * 5)]
  parameters.value.mood = moods[Math.floor(Math.random() * moods.length)]
  parameters.value.colorPalette = colorPalettes[Math.floor(Math.random() * colorPalettes.length)].name
}

function useCharacter() {
  emit('character-selected', generatedCharacter.value)
}

function saveCharacter() {
  // Save to character library
  console.log('Saving character to library')
}

function regenerateVariation() {
  generateCharacter()
}

// API Functions for Model and Quality Selection
async function loadModels() {
  try {
    const response = await fetch('/api/anime/models')
    if (response.ok) {
      availableModels.value = await response.json()
      // Set default model if none selected
      if (availableModels.value.length > 0 && !selectedModel.value) {
        selectedModel.value = availableModels.value[0].name
      }
    }
  } catch (error) {
    console.error('Failed to load models:', error)
  }
}

async function loadQualityPresets() {
  try {
    const response = await fetch('/api/anime/quality-presets')
    if (response.ok) {
      qualityPresets.value = await response.json()
      // Set default quality if none selected
      if (qualityPresets.value.length > 0 && !selectedQuality.value) {
        selectedQuality.value = qualityPresets.value[0].name
      }
    }
  } catch (error) {
    console.error('Failed to load quality presets:', error)
  }
}

async function updateModel() {
  try {
    const response = await fetch('/api/anime/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: selectedModel.value
      })
    })
    if (!response.ok) {
      console.error('Failed to update model')
    }
  } catch (error) {
    console.error('Failed to update model:', error)
  }
}

async function updateQuality() {
  try {
    const response = await fetch('/api/anime/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        quality_preset: selectedQuality.value
      })
    })
    if (!response.ok) {
      console.error('Failed to update quality')
    }
  } catch (error) {
    console.error('Failed to update quality:', error)
  }
}

// Load initial data on component mount
import { onMounted } from 'vue'

onMounted(() => {
  loadModels()
  loadQualityPresets()
})

// Watch for parameter changes
watch(parameters, () => {
  if (generatedCharacter.value) {
    // Clear previous generation when parameters change
    generatedCharacter.value = null
  }
}, { deep: true })
</script>

<style scoped>
.character-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--cp-border-primary);
}

.character-header h3 {
  color: var(--cp-accent-primary);
  margin: 0;
  font-family: var(--cp-font-family-display);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.character-actions {
  display: flex;
  gap: 0.5rem;
}

.parameter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.parameter-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.parameter-group.full-width {
  grid-column: 1 / -1;
}

.parameter-group label {
  color: var(--cp-text-secondary);
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.color-palette-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 0.5rem;
}

.color-swatch {
  height: 40px;
  border-radius: 4px;
  cursor: pointer;
  border: 2px solid transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.7rem;
  font-weight: 600;
  text-shadow: 0 0 4px rgba(0, 0, 0, 0.8);
  color: white;
  transition: all var(--cp-transition-fast);
}

.color-swatch:hover {
  transform: scale(1.05);
}

.color-swatch.active {
  border-color: var(--cp-accent-primary);
  box-shadow: var(--cp-glow-orange);
}

.mood-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
  gap: 0.5rem;
}

.mood-button {
  padding: 0.5rem;
  background: var(--cp-bg-primary);
  border: 1px solid var(--cp-border-primary);
  color: var(--cp-text-primary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.7rem;
  text-transform: uppercase;
  transition: all var(--cp-transition-fast);
}

.mood-button:hover {
  border-color: var(--cp-accent-primary);
}

.mood-button.active {
  background: var(--cp-accent-primary);
  color: var(--cp-text-inverse);
}

.advanced-settings {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.advanced-settings label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8rem;
  cursor: pointer;
}

.generation-progress {
  margin: 1rem 0;
  padding: 1rem;
  background: var(--cp-bg-secondary);
  border: 1px solid var(--cp-border-primary);
  border-radius: 4px;
}

.progress-bar {
  height: 8px;
  background: var(--cp-bg-primary);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-fill {
  height: 100%;
  background: var(--cp-gradient-accent);
  transition: width var(--cp-transition-normal);
  position: relative;
}

.progress-fill::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.4), transparent);
  animation: shimmer 1.5s infinite;
}

.progress-text {
  font-size: 0.8rem;
  color: var(--cp-text-secondary);
  text-align: center;
}

.character-preview {
  margin-top: 2rem;
  padding: 1.5rem;
  background: var(--cp-bg-secondary);
  border: 1px solid var(--cp-border-primary);
  border-radius: 8px;
}

.character-preview h4 {
  color: var(--cp-accent-primary);
  margin: 0 0 1rem 0;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.preview-grid {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 1rem;
  margin-bottom: 1rem;
}

.preview-image img {
  width: 100%;
  height: 200px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid var(--cp-border-primary);
}

.preview-details {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.detail-item {
  font-size: 0.9rem;
}

.detail-item strong {
  color: var(--cp-accent-primary);
}

.preview-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .parameter-grid {
    grid-template-columns: 1fr;
  }

  .character-header {
    flex-direction: column;
    gap: 1rem;
    align-items: stretch;
  }

  .preview-grid {
    grid-template-columns: 1fr;
  }
}</style>