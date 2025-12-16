<template>
  <div class="project-orchestrator">
    <!-- Command Header -->
    <div class="command-header">
      <div class="header-left">
        <h2>
          <i class="pi pi-bolt"></i>
          Project Orchestrator
        </h2>
        <span class="echo-status" :class="{ 'connected': echoConnected }">
          <span class="status-dot"></span>
          {{ echoConnected ? 'Echo Brain Online' : 'Echo Brain Offline' }}
        </span>
      </div>
      <div class="header-controls">
        <Button
          icon="pi pi-refresh"
          @click="refreshEchoStatus"
          :loading="refreshing"
          severity="secondary"
          text
          v-tooltip="'Refresh Echo Status'"
        />
        <Button
          icon="pi pi-cog"
          @click="showSettings = true"
          severity="secondary"
          text
          v-tooltip="'Settings'"
        />
      </div>
    </div>

    <!-- Natural Language Command Interface -->
    <div class="command-interface">
      <div class="command-input-wrapper">
        <div class="command-prompt">
          <i class="pi pi-terminal"></i>
          <span>echo-orchestrator $</span>
        </div>
        <InputText
          v-model="userCommand"
          @keyup.enter="executeCommand"
          :loading="processing"
          placeholder="Describe what you want to create... (e.g., 'Create a fight scene between Yuki and Kaito')"
          class="command-input"
          ref="commandInput"
        />
        <Button
          icon="pi pi-play"
          @click="executeCommand"
          :loading="processing"
          severity="success"
          :disabled="!userCommand.trim()"
        />
      </div>

      <!-- Quick Actions -->
      <div class="quick-actions">
        <Button
          v-for="action in quickActions"
          :key="action.id"
          :label="action.label"
          :icon="action.icon"
          @click="executeQuickAction(action)"
          size="small"
          severity="secondary"
          outlined
        />
      </div>
    </div>

    <!-- Active Project Context -->
    <div class="context-display" v-if="selectedProject">
      <Card class="context-card">
        <template #header>
          <div class="context-header">
            <span class="context-title">Active Project Context</span>
            <Tag :value="selectedProject.status" :severity="getStatusSeverity(selectedProject.status)" />
          </div>
        </template>
        <template #content>
          <div class="context-grid">
            <div class="context-item">
              <span class="context-label">Project:</span>
              <span class="context-value">{{ selectedProject.name }}</span>
            </div>
            <div class="context-item">
              <span class="context-label">Timeline Branch:</span>
              <span class="context-value">{{ currentTimelineBranch }}</span>
            </div>
            <div class="context-item">
              <span class="context-label">Characters:</span>
              <span class="context-value">{{ projectCharacters.length }} defined</span>
            </div>
            <div class="context-item">
              <span class="context-label">Scenes:</span>
              <span class="context-value">{{ projectScenes.length }} total</span>
            </div>
          </div>
        </template>
      </Card>
    </div>

    <!-- Generation Queue -->
    <div class="generation-queue" v-if="generationQueue.length > 0">
      <h3>
        <i class="pi pi-list"></i>
        Generation Queue
      </h3>
      <div class="queue-items">
        <Card v-for="item in generationQueue" :key="item.id" class="queue-item">
          <template #content>
            <div class="queue-item-header">
              <span class="queue-item-title">{{ item.title }}</span>
              <Tag :value="item.status" :severity="getGenerationSeverity(item.status)" />
            </div>
            <div class="queue-item-details">
              <span class="queue-command">{{ item.originalCommand }}</span>
              <ProgressBar
                v-if="item.status === 'processing'"
                :value="item.progress || 0"
                :show-value="true"
                class="queue-progress"
              />
              <div class="queue-meta">
                <span>{{ formatTimestamp(item.created_at) }}</span>
                <span v-if="item.eta">ETA: {{ item.eta }}</span>
              </div>
            </div>
          </template>
        </Card>
      </div>
    </div>

    <!-- Orchestration Results -->
    <div class="orchestration-results" v-if="lastOrchestration">
      <h3>
        <i class="pi pi-check-circle"></i>
        Last Orchestration Result
      </h3>
      <Card class="result-card">
        <template #content>
          <div class="result-header">
            <span class="result-title">{{ lastOrchestration.action_type }}</span>
            <Tag :value="lastOrchestration.confidence" severity="success" />
          </div>
          <div class="result-details">
            <div class="result-interpretation">
              <strong>Echo's Interpretation:</strong>
              <p>{{ lastOrchestration.interpretation }}</p>
            </div>
            <div class="result-parameters" v-if="lastOrchestration.parameters">
              <strong>Generated Parameters:</strong>
              <pre class="parameters-code">{{ JSON.stringify(lastOrchestration.parameters, null, 2) }}</pre>
            </div>
            <div class="result-actions">
              <Button
                label="Execute Plan"
                icon="pi pi-play"
                @click="executePlan(lastOrchestration)"
                severity="success"
                :disabled="lastOrchestration.executed"
              />
              <Button
                label="Modify"
                icon="pi pi-pencil"
                @click="modifyPlan(lastOrchestration)"
                severity="secondary"
                outlined
              />
              <Button
                label="Learn from This"
                icon="pi pi-plus"
                @click="learnFromResult(lastOrchestration)"
                severity="help"
                outlined
                v-tooltip="'Teach Echo your preferences'"
              />
            </div>
          </div>
        </template>
      </Card>
    </div>

    <!-- Settings Dialog -->
    <Dialog v-model:visible="showSettings" header="Orchestrator Settings" :modal="true" :style="{ width: '500px' }">
      <div class="settings-content">
        <div class="setting-group">
          <label>Intelligence Level</label>
          <Dropdown
            v-model="settings.intelligenceLevel"
            :options="intelligenceLevels"
            optionLabel="label"
            optionValue="value"
            placeholder="Select Intelligence Level"
          />
          <small>Higher levels use more powerful models for complex tasks</small>
        </div>

        <div class="setting-group">
          <label>Auto-execution</label>
          <div class="flex align-items-center">
            <Checkbox v-model="settings.autoExecute" binary />
            <span class="ml-2">Automatically execute simple commands</span>
          </div>
        </div>

        <div class="setting-group">
          <label>Learning Mode</label>
          <Dropdown
            v-model="settings.learningMode"
            :options="learningModes"
            optionLabel="label"
            optionValue="value"
            placeholder="Select Learning Mode"
          />
        </div>
      </div>
      <template #footer>
        <Button label="Cancel" @click="showSettings = false" severity="secondary" />
        <Button label="Save" @click="saveSettings" />
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useEchoApi } from '@/composables/useEchoApi'
import { useEnhancedAnimeStore } from '@/stores/enhancedAnimeStore'

// Composables
const toast = useToast()
const echoApi = useEchoApi()
const store = useEnhancedAnimeStore()

// Refs
const userCommand = ref('')
const processing = ref(false)
const refreshing = ref(false)
const echoConnected = ref(false)
const showSettings = ref(false)
const commandInput = ref(null)
const lastOrchestration = ref(null)

// Settings
const settings = ref({
  intelligenceLevel: 'auto',
  autoExecute: false,
  learningMode: 'incremental'
})

// Options
const intelligenceLevels = ref([
  { label: 'Auto (Adaptive)', value: 'auto' },
  { label: 'Fast (1B-7B)', value: 'fast' },
  { label: 'Balanced (8B-32B)', value: 'balanced' },
  { label: 'Smart (70B+)', value: 'smart' }
])

const learningModes = ref([
  { label: 'Incremental', value: 'incremental' },
  { label: 'Conservative', value: 'conservative' },
  { label: 'Aggressive', value: 'aggressive' },
  { label: 'Disabled', value: 'disabled' }
])

const quickActions = ref([
  { id: 'new_character', label: 'New Character', icon: 'pi pi-user-plus' },
  { id: 'new_scene', label: 'New Scene', icon: 'pi pi-plus' },
  { id: 'branch_timeline', label: 'Branch Timeline', icon: 'pi pi-sitemap' },
  { id: 'quality_check', label: 'Quality Check', icon: 'pi pi-shield' }
])

// Computed
const selectedProject = computed(() => store.selectedProject)
const currentTimelineBranch = computed(() => store.currentTimelineBranch || 'main')
const projectCharacters = computed(() => store.characters.filter(c => c.project_id === selectedProject.value?.id) || [])
const projectScenes = computed(() => store.scenes.filter(s => s.project_id === selectedProject.value?.id) || [])
const generationQueue = computed(() => store.generationQueue || [])

// Methods
async function executeCommand() {
  if (!userCommand.value.trim()) return

  processing.value = true
  try {
    const context = {
      project: selectedProject.value,
      timeline_branch: currentTimelineBranch.value,
      characters: projectCharacters.value,
      scenes: projectScenes.value,
      settings: settings.value
    }

    toast.add({
      severity: 'info',
      summary: 'Processing Command',
      detail: 'Echo Brain is interpreting your request...',
      life: 3000
    })

    const result = await echoApi.translateIntent(userCommand.value, context)

    lastOrchestration.value = {
      ...result,
      originalCommand: userCommand.value,
      timestamp: new Date(),
      executed: false
    }

    toast.add({
      severity: 'success',
      summary: 'Command Processed',
      detail: `Echo interpreted: ${result.action_type}`,
      life: 5000
    })

    // Auto-execute if enabled and confidence is high
    if (settings.value.autoExecute && result.confidence > 0.8) {
      await executePlan(lastOrchestration.value)
    }

    userCommand.value = ''
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Command Failed',
      detail: error.message,
      life: 5000
    })
  } finally {
    processing.value = false
  }
}

async function executeQuickAction(action) {
  const quickCommands = {
    'new_character': 'Create a new character for this project',
    'new_scene': 'Add a new scene to the current timeline',
    'branch_timeline': 'Create a new timeline branch for experimentation',
    'quality_check': 'Run quality assessment on recent generations'
  }

  userCommand.value = quickCommands[action.id]
  await executeCommand()
}

async function executePlan(orchestration) {
  try {
    toast.add({
      severity: 'info',
      summary: 'Executing Plan',
      detail: 'Starting generation pipeline...',
      life: 3000
    })

    // Add to generation queue
    const queueItem = {
      id: Date.now(),
      title: orchestration.action_type,
      originalCommand: orchestration.originalCommand,
      status: 'queued',
      created_at: new Date(),
      parameters: orchestration.parameters
    }

    store.addToGenerationQueue(queueItem)
    orchestration.executed = true

    // Start actual generation process
    await store.executeGeneration(queueItem)

    toast.add({
      severity: 'success',
      summary: 'Plan Executed',
      detail: 'Generation started successfully',
      life: 3000
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Execution Failed',
      detail: error.message,
      life: 5000
    })
  }
}

function modifyPlan(orchestration) {
  // Populate command input with current plan for modification
  userCommand.value = `Modify: ${orchestration.originalCommand}`
  nextTick(() => {
    commandInput.value?.$el?.focus()
  })
}

async function learnFromResult(orchestration) {
  try {
    const feedbackData = {
      command: orchestration.originalCommand,
      interpretation: orchestration.interpretation,
      parameters: orchestration.parameters,
      user_satisfaction: 'positive', // Could be made interactive
      learning_category: 'command_interpretation'
    }

    await echoApi.learnPreference(feedbackData)

    toast.add({
      severity: 'success',
      summary: 'Learning Saved',
      detail: 'Echo Brain learned from your preference',
      life: 3000
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Learning Failed',
      detail: error.message,
      life: 3000
    })
  }
}

async function refreshEchoStatus() {
  refreshing.value = true
  try {
    const status = await echoApi.healthCheck()
    echoConnected.value = status.status === 'healthy'

    toast.add({
      severity: echoConnected.value ? 'success' : 'warn',
      summary: 'Echo Status',
      detail: echoConnected.value ? 'Echo Brain is online' : 'Echo Brain connection issues',
      life: 3000
    })
  } catch (error) {
    echoConnected.value = false
    toast.add({
      severity: 'error',
      summary: 'Connection Failed',
      detail: 'Could not reach Echo Brain',
      life: 3000
    })
  } finally {
    refreshing.value = false
  }
}

function saveSettings() {
  // Save settings to store/localStorage
  store.updateOrchestratorSettings(settings.value)
  showSettings.value = false

  toast.add({
    severity: 'success',
    summary: 'Settings Saved',
    detail: 'Orchestrator preferences updated',
    life: 3000
  })
}

function getStatusSeverity(status) {
  const statusMap = {
    'active': 'success',
    'pending': 'warning',
    'processing': 'info',
    'completed': 'success',
    'failed': 'danger'
  }
  return statusMap[status] || 'secondary'
}

function getGenerationSeverity(status) {
  const statusMap = {
    'queued': 'warning',
    'processing': 'info',
    'completed': 'success',
    'failed': 'danger'
  }
  return statusMap[status] || 'secondary'
}

function formatTimestamp(timestamp) {
  return new Date(timestamp).toLocaleTimeString()
}

// Initialize
onMounted(async () => {
  await refreshEchoStatus()

  // Focus command input
  nextTick(() => {
    commandInput.value?.$el?.focus()
  })
})
</script>

<style scoped>
.project-orchestrator {
  padding: 1.5rem;
  background: #0a0a0a;
  color: #e0e0e0;
  min-height: 100vh;
}

.command-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #333;
}

.header-left h2 {
  margin: 0;
  color: #00d4ff;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.echo-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  margin-left: 1rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ff6b6b;
}

.echo-status.connected .status-dot {
  background: #51cf66;
}

.command-interface {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 2rem;
}

.command-input-wrapper {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.command-prompt {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #00d4ff;
  font-family: 'Monaco', monospace;
  font-weight: 600;
  white-space: nowrap;
}

.command-input {
  flex: 1;
  font-family: 'Monaco', monospace;
}

.quick-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.context-card {
  background: #1a1a1a;
  border: 1px solid #333;
  margin-bottom: 2rem;
}

.context-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.context-title {
  font-weight: 600;
  color: #00d4ff;
}

.context-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.context-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.context-label {
  font-size: 0.75rem;
  color: #999;
  text-transform: uppercase;
  font-weight: 600;
}

.context-value {
  color: #e0e0e0;
  font-weight: 500;
}

.generation-queue h3 {
  color: #00d4ff;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.queue-items {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 2rem;
}

.queue-item {
  background: #1a1a1a;
  border: 1px solid #333;
}

.queue-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.queue-item-title {
  font-weight: 600;
  color: #e0e0e0;
}

.queue-command {
  font-size: 0.875rem;
  color: #999;
  font-style: italic;
}

.queue-progress {
  margin: 0.5rem 0;
}

.queue-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: #666;
  margin-top: 0.5rem;
}

.orchestration-results h3 {
  color: #51cf66;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.result-card {
  background: #1a1a1a;
  border: 1px solid #333;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.result-title {
  font-weight: 600;
  color: #51cf66;
  text-transform: capitalize;
}

.result-interpretation {
  margin-bottom: 1rem;
}

.result-interpretation p {
  color: #ccc;
  font-style: italic;
  margin: 0.5rem 0;
}

.parameters-code {
  background: #0a0a0a;
  border: 1px solid #333;
  border-radius: 4px;
  padding: 1rem;
  color: #00d4ff;
  font-family: 'Monaco', monospace;
  font-size: 0.875rem;
  overflow-x: auto;
  margin: 0.5rem 0 1rem 0;
}

.result-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.settings-content {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.setting-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.setting-group label {
  font-weight: 600;
  color: #e0e0e0;
}

.setting-group small {
  color: #999;
}
</style>