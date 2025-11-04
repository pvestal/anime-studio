<template>
  <div class="music-video-sync-studio">
    <!-- Mode-specific Interface -->
    <SmartSyncInterface
      v-if="currentMode === 'smart'"
      :currentMode="currentMode"
      @changeMode="handleModeChange"
    />

    <QuickControlsInterface
      v-else-if="currentMode === 'quick'"
      :currentMode="currentMode"
      @changeMode="handleModeChange"
    />

    <ProfessionalInterface
      v-else-if="currentMode === 'professional'"
      :currentMode="currentMode"
      @changeMode="handleModeChange"
    />

    <!-- Mode Tutorial Overlay -->
    <div v-if="showTutorial" class="tutorial-overlay" @click="hideTutorial">
      <div class="tutorial-content" @click.stop>
        <div class="tutorial-header">
          <h3>{{ tutorialData.title }}</h3>
          <button @click="hideTutorial" class="close-btn">
            <i class="pi pi-times"></i>
          </button>
        </div>

        <div class="tutorial-body">
          <div class="tutorial-description">
            {{ tutorialData.description }}
          </div>

          <div class="tutorial-features">
            <h4>Key Features:</h4>
            <ul>
              <li v-for="feature in tutorialData.features" :key="feature">
                {{ feature }}
              </li>
            </ul>
          </div>

          <div class="tutorial-best-for">
            <h4>Best for:</h4>
            <p>{{ tutorialData.bestFor }}</p>
          </div>
        </div>

        <div class="tutorial-actions">
          <button @click="hideTutorial" class="got-it-btn">
            Got it!
          </button>
          <label class="dont-show-again">
            <input type="checkbox" v-model="dontShowTutorial">
            Don't show again
          </label>
        </div>
      </div>
    </div>

    <!-- Quick Help Floating Button -->
    <div class="help-float">
      <button @click="showHelp" class="help-btn" title="Help & Tips">
        <i class="pi pi-question-circle"></i>
      </button>
    </div>

    <!-- Context Help Panel -->
    <div v-if="showHelpPanel" class="help-panel">
      <div class="help-header">
        <h3>{{ currentModeData.name }} Help</h3>
        <button @click="showHelpPanel = false" class="close-help-btn">
          <i class="pi pi-times"></i>
        </button>
      </div>

      <div class="help-content">
        <div class="mode-description">
          <p>{{ currentModeData.helpText }}</p>
        </div>

        <div class="quick-tips">
          <h4>Quick Tips:</h4>
          <ul>
            <li v-for="tip in currentModeData.tips" :key="tip">
              {{ tip }}
            </li>
          </ul>
        </div>

        <div class="mode-switching">
          <h4>Switch Modes:</h4>
          <div class="mode-buttons">
            <button
              v-for="mode in allModes"
              :key="mode.id"
              @click="handleModeChange(mode.id)"
              class="mode-switch-btn"
              :class="{ active: currentMode === mode.id }"
            >
              {{ mode.icon }} {{ mode.name }}
            </button>
          </div>
        </div>

        <div class="keyboard-shortcuts" v-if="currentModeData.shortcuts">
          <h4>Keyboard Shortcuts:</h4>
          <div class="shortcuts-list">
            <div
              v-for="shortcut in currentModeData.shortcuts"
              :key="shortcut.key"
              class="shortcut-item"
            >
              <kbd>{{ shortcut.key }}</kbd>
              <span>{{ shortcut.action }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import SmartSyncInterface from './SmartSyncInterface.vue'
import QuickControlsInterface from './QuickControlsInterface.vue'
// Note: Professional mode will be imported when created
// import ProfessionalInterface from './ProfessionalInterface.vue'

// State
const currentMode = ref('smart')
const showTutorial = ref(false)
const showHelpPanel = ref(false)
const dontShowTutorial = ref(false)

// Mode configuration
const allModes = [
  {
    id: 'smart',
    name: 'Smart Sync',
    icon: '✨',
    helpText: 'Smart Sync automatically analyzes your video and creates perfect music synchronization with minimal input. Just choose your scene type, drop your files, and let AI do the rest.',
    tips: [
      'Choose the scene template that best matches your video content',
      'Let AI select music for optimal matching, or upload your own',
      'The sync process analyzes video pacing and music beats automatically',
      'Preview results immediately after sync completes',
      'Export directly to Jellyfin for easy access'
    ],
    shortcuts: [
      { key: 'Space', action: 'Play/pause preview' },
      { key: 'Ctrl + O', action: 'Upload video file' },
      { key: 'Ctrl + M', action: 'Upload music file' },
      { key: 'Enter', action: 'Start Smart Sync' }
    ]
  },
  {
    id: 'quick',
    name: 'Quick Controls',
    icon: '⚙️',
    helpText: 'Quick Controls provides essential timing and style controls with a visual timeline. Perfect for users who want some control over the sync process without overwhelming complexity.',
    tips: [
      'Use the visual timeline to see video frames and audio waveform',
      'Drag the sync handle to manually adjust timing',
      'Beat markers show where music beats align with video',
      'Save your settings as presets for future use',
      'Real-time sync quality feedback helps optimize results'
    ],
    shortcuts: [
      { key: 'Space', action: 'Play/pause timeline' },
      { key: 'Left/Right arrows', action: 'Seek timeline' },
      { key: 'Shift + Drag', action: 'Fine-tune sync offset' },
      { key: 'Ctrl + S', action: 'Save preset' },
      { key: 'Tab', action: 'Switch between controls' }
    ]
  },
  {
    id: 'professional',
    name: 'Professional',
    icon: '🎛️',
    helpText: 'Professional mode provides complete control over all aspects of music-video synchronization. Access advanced audio analysis, manual beat editing, and batch processing capabilities.',
    tips: [
      'Access all original interface controls organized by function',
      'Manual beat editing for precise synchronization',
      'Advanced audio analysis with spectral view',
      'Batch process multiple video-music combinations',
      'Custom template creation and sharing'
    ],
    shortcuts: [
      { key: 'Ctrl + Tab', action: 'Switch between tool panels' },
      { key: 'Ctrl + B', action: 'Manual beat detection' },
      { key: 'Ctrl + E', action: 'Export settings' },
      { key: 'F11', action: 'Fullscreen timeline view' }
    ]
  }
]

// Tutorial data
const tutorialData = computed(() => {
  const modeData = allModes.find(mode => mode.id === currentMode.value)
  return {
    title: `Welcome to ${modeData?.name}!`,
    description: modeData?.helpText || '',
    features: modeData?.tips || [],
    bestFor: getBestForText(currentMode.value)
  }
})

const currentModeData = computed(() => {
  return allModes.find(mode => mode.id === currentMode.value) || allModes[0]
})

// Methods
const handleModeChange = (newMode) => {
  const oldMode = currentMode.value
  currentMode.value = newMode

  // Show tutorial for new mode if user hasn't disabled it
  if (!dontShowTutorial.value && oldMode !== newMode) {
    showModeTransitionTutorial()
  }

  // Close help panel when switching modes
  showHelpPanel.value = false

  // Track mode usage for analytics
  trackModeSwitch(oldMode, newMode)
}

const showModeTransitionTutorial = () => {
  showTutorial.value = true
}

const hideTutorial = () => {
  showTutorial.value = false

  // Save tutorial preference
  if (dontShowTutorial.value) {
    localStorage.setItem('music-sync-tutorial-disabled', 'true')
  }
}

const showHelp = () => {
  showHelpPanel.value = !showHelpPanel.value
}

const getBestForText = (mode) => {
  switch (mode) {
    case 'smart':
      return 'Content creators who want quick, professional results without technical complexity. Perfect for social media, YouTube videos, and general anime content.'
    case 'quick':
      return 'Editors who need some control over timing and style but don\'t want to dive into technical details. Great for AMVs and custom anime projects.'
    case 'professional':
      return 'Audio engineers, professional editors, and advanced users who need complete control over every aspect of synchronization. Ideal for commercial productions.'
    default:
      return ''
  }
}

const trackModeSwitch = (from, to) => {
  // Analytics tracking for mode usage patterns
  console.log(`Mode switch: ${from} → ${to}`)

  // In real implementation, send to analytics service
  // analytics.track('mode_switch', { from, to, timestamp: Date.now() })
}

const initializeTutorialPreference = () => {
  const tutorialDisabled = localStorage.getItem('music-sync-tutorial-disabled')
  dontShowTutorial.value = tutorialDisabled === 'true'
}

const handleKeyboardShortcuts = (event) => {
  // Global keyboard shortcuts
  if (event.ctrlKey && event.key === 'h') {
    event.preventDefault()
    showHelp()
  }

  if (event.ctrlKey && event.key === '1') {
    event.preventDefault()
    handleModeChange('smart')
  }

  if (event.ctrlKey && event.key === '2') {
    event.preventDefault()
    handleModeChange('quick')
  }

  if (event.ctrlKey && event.key === '3') {
    event.preventDefault()
    handleModeChange('professional')
  }
}

// Lifecycle
onMounted(() => {
  initializeTutorialPreference()

  // Add global keyboard shortcut listener
  document.addEventListener('keydown', handleKeyboardShortcuts)

  // Show initial tutorial for first-time users
  const isFirstTime = !localStorage.getItem('music-sync-visited')
  if (isFirstTime && !dontShowTutorial.value) {
    setTimeout(() => {
      showTutorial.value = true
    }, 1000)
    localStorage.setItem('music-sync-visited', 'true')
  }
})

// Cleanup
onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyboardShortcuts)
})

// Provide temporary Professional mode component until it's created
const ProfessionalInterface = {
  props: ['currentMode'],
  emits: ['changeMode'],
  template: `
    <div class="professional-placeholder">
      <div class="placeholder-header">
        <h2>🎛️ Professional Mode</h2>
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

      <div class="placeholder-content">
        <div class="coming-soon">
          <i class="pi pi-cog placeholder-icon"></i>
          <h3>Professional Mode Coming Soon</h3>
          <p>This mode will include all advanced controls from the original interface, organized and improved based on professional workflow needs.</p>

          <div class="planned-features">
            <h4>Planned Features:</h4>
            <ul>
              <li>🎵 Advanced audio analysis with spectral view</li>
              <li>✂️ Manual beat editing and sync point control</li>
              <li>🔄 Batch processing for multiple videos</li>
              <li>📊 Detailed sync quality metrics</li>
              <li>🎨 Custom template creation and sharing</li>
              <li>📁 Project file management</li>
              <li>🔧 Plugin system for custom processors</li>
            </ul>
          </div>

          <div class="placeholder-actions">
            <button @click="$emit('changeMode', 'quick')" class="go-quick-btn">
              ⚙️ Use Quick Controls
            </button>
            <button @click="$emit('changeMode', 'smart')" class="go-smart-btn">
              ✨ Use Smart Sync
            </button>
          </div>
        </div>
      </div>
    </div>
  `,
  setup() {
    const viewModes = [
      { id: 'smart', label: 'Smart Sync', icon: '✨' },
      { id: 'quick', label: 'Quick Controls', icon: '⚙️' },
      { id: 'professional', label: 'Professional', icon: '🎛️' }
    ]

    return { viewModes }
  }
}
</script>

<style scoped>
.music-video-sync-studio {
  position: relative;
  min-height: 600px;
}

/* Tutorial Overlay */
.tutorial-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  backdrop-filter: blur(4px);
}

.tutorial-content {
  background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
  border-radius: 16px;
  padding: 32px;
  max-width: 500px;
  max-height: 80vh;
  overflow-y: auto;
  border: 1px solid #00d4aa;
  box-shadow: 0 20px 50px rgba(0, 212, 170, 0.2);
}

.tutorial-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #475569;
}

.tutorial-header h3 {
  margin: 0;
  color: #00d4aa;
  font-size: 1.5rem;
}

.close-btn {
  padding: 6px;
  background: #ef4444;
  border: none;
  border-radius: 50%;
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
}

.close-btn:hover {
  background: #dc2626;
  transform: scale(1.1);
}

.tutorial-description {
  color: #e2e8f0;
  line-height: 1.6;
  margin-bottom: 20px;
}

.tutorial-features h4,
.tutorial-best-for h4 {
  color: #00d4aa;
  margin-bottom: 12px;
  font-size: 1rem;
}

.tutorial-features ul {
  margin: 0;
  padding-left: 20px;
  color: #e2e8f0;
  line-height: 1.6;
}

.tutorial-features li {
  margin-bottom: 8px;
}

.tutorial-best-for {
  margin-top: 20px;
}

.tutorial-best-for p {
  color: #e2e8f0;
  line-height: 1.6;
  margin: 0;
}

.tutorial-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #475569;
}

.got-it-btn {
  padding: 12px 24px;
  background: linear-gradient(135deg, #00d4aa 0%, #059669 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.got-it-btn:hover {
  background: linear-gradient(135deg, #059669 0%, #047857 100%);
  transform: translateY(-2px);
}

.dont-show-again {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #94a3b8;
  font-size: 0.875rem;
  cursor: pointer;
}

/* Floating Help Button */
.help-float {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1000;
}

.help-btn {
  padding: 16px;
  background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
  border: none;
  border-radius: 50%;
  color: white;
  font-size: 1.25rem;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 8px 25px rgba(124, 58, 237, 0.3);
}

.help-btn:hover {
  background: linear-gradient(135deg, #6d28d9 0%, #5b21b6 100%);
  transform: translateY(-2px);
  box-shadow: 0 12px 30px rgba(124, 58, 237, 0.4);
}

/* Context Help Panel */
.help-panel {
  position: fixed;
  top: 50%;
  right: 24px;
  transform: translateY(-50%);
  width: 350px;
  max-height: 80vh;
  background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
  border-radius: 12px;
  border: 1px solid #00d4aa;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
  z-index: 1500;
  overflow: hidden;
}

.help-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: rgba(0, 212, 170, 0.1);
  border-bottom: 1px solid #475569;
}

.help-header h3 {
  margin: 0;
  color: #00d4aa;
  font-size: 1.25rem;
}

.close-help-btn {
  padding: 4px;
  background: transparent;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s ease;
}

.close-help-btn:hover {
  background: rgba(148, 163, 184, 0.1);
  color: #e2e8f0;
}

.help-content {
  padding: 20px;
  overflow-y: auto;
  max-height: calc(80vh - 70px);
}

.mode-description p {
  color: #e2e8f0;
  line-height: 1.6;
  margin-bottom: 20px;
}

.quick-tips h4,
.mode-switching h4,
.keyboard-shortcuts h4 {
  color: #00d4aa;
  margin-bottom: 12px;
  font-size: 1rem;
}

.quick-tips ul {
  margin: 0 0 20px 0;
  padding-left: 16px;
  color: #e2e8f0;
}

.quick-tips li {
  margin-bottom: 8px;
  line-height: 1.5;
}

.mode-buttons {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 20px;
}

.mode-switch-btn {
  padding: 8px 12px;
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid #334155;
  border-radius: 6px;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: left;
}

.mode-switch-btn:hover {
  border-color: #00d4aa;
  color: #e2e8f0;
}

.mode-switch-btn.active {
  background: rgba(0, 212, 170, 0.1);
  border-color: #00d4aa;
  color: #00d4aa;
}

.shortcuts-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.shortcut-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: rgba(15, 23, 42, 0.5);
  border-radius: 6px;
}

.shortcut-item kbd {
  background: #475569;
  border: 1px solid #64748b;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 0.75rem;
  color: #e2e8f0;
  font-family: monospace;
}

.shortcut-item span {
  color: #94a3b8;
  font-size: 0.875rem;
}

/* Professional Mode Placeholder Styles */
.professional-placeholder {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  border-radius: 12px;
  padding: 24px;
  color: #f1f5f9;
  min-height: 600px;
}

.placeholder-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding-bottom: 20px;
  border-bottom: 1px solid #334155;
}

.placeholder-header h2 {
  margin: 0;
  color: #00d4aa;
  text-shadow: 0 0 10px rgba(0, 212, 170, 0.3);
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

.placeholder-content {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 500px;
}

.coming-soon {
  text-align: center;
  max-width: 600px;
}

.placeholder-icon {
  font-size: 4rem;
  color: #64748b;
  margin-bottom: 24px;
}

.coming-soon h3 {
  color: #e2e8f0;
  margin-bottom: 16px;
  font-size: 1.75rem;
}

.coming-soon p {
  color: #94a3b8;
  line-height: 1.6;
  margin-bottom: 32px;
  font-size: 1.1rem;
}

.planned-features {
  background: rgba(15, 23, 42, 0.5);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 32px;
  text-align: left;
}

.planned-features h4 {
  color: #00d4aa;
  margin-bottom: 16px;
  text-align: center;
}

.planned-features ul {
  margin: 0;
  padding-left: 0;
  list-style: none;
}

.planned-features li {
  padding: 8px 0;
  color: #e2e8f0;
  border-bottom: 1px solid rgba(51, 65, 85, 0.5);
}

.planned-features li:last-child {
  border-bottom: none;
}

.placeholder-actions {
  display: flex;
  gap: 16px;
  justify-content: center;
}

.go-quick-btn, .go-smart-btn {
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  color: white;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.go-quick-btn {
  background: linear-gradient(135deg, #059669 0%, #047857 100%);
}

.go-smart-btn {
  background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
}

.go-quick-btn:hover {
  background: linear-gradient(135deg, #047857 0%, #065f46 100%);
  transform: translateY(-2px);
}

.go-smart-btn:hover {
  background: linear-gradient(135deg, #6d28d9 0%, #5b21b6 100%);
  transform: translateY(-2px);
}

/* Responsive Design */
@media (max-width: 768px) {
  .help-panel {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    left: 0;
    width: 100%;
    max-height: 100vh;
    transform: none;
    border-radius: 0;
  }

  .tutorial-content {
    margin: 20px;
    max-height: calc(100vh - 40px);
  }

  .placeholder-actions {
    flex-direction: column;
  }
}
</style>