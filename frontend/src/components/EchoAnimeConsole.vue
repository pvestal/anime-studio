<template>
  <div class="echo-anime-console">
    <!-- Console Header -->
    <div class="console-header">
      <div class="console-title">
        <span class="prompt-symbol">$</span>
        <span class="title-text">echo-brain-anime-coordinator</span>
        <div class="echo-status" :class="{ 'connected': echoConnected }">
          <span class="status-dot"></span>
          {{ echoConnected ? 'CONNECTED' : 'DISCONNECTED' }}
        </div>
      </div>
      <div class="console-controls">
        <button class="console-btn" @click="clearConsole">clear</button>
        <button class="console-btn" @click="refreshEchoStatus">status</button>
      </div>
    </div>

    <!-- Main Console Output -->
    <div class="console-output" ref="consoleOutput">
      <div v-for="(line, index) in consoleLines" :key="index"
           :class="['console-line', line.type]">
        <span class="timestamp">{{ formatTimestamp(line.timestamp) }}</span>
        <span class="line-content">{{ line.content }}</span>
      </div>
    </div>

    <!-- Console Input -->
    <div class="console-input">
      <span class="input-prompt">echo-anime $</span>
      <input
        v-model="inputCommand"
        @keyup.enter="executeCommand"
        @keydown.tab.prevent="autocomplete"
        class="input-field"
        placeholder="Type command (generate, status, characters, help)"
        ref="inputField"
      />
    </div>

    <!-- Echo Coordination Panel -->
    <div class="coordination-panel" v-if="currentCoordination">
      <div class="panel-header">
        <span class="panel-title">ECHO COORDINATION ACTIVE</span>
        <span class="coordination-id">{{ currentCoordination.orchestration_id }}</span>
      </div>
      <div class="coordination-content">
        <div class="coord-item">
          <span class="coord-label">PROMPT:</span>
          <span class="coord-value">{{ currentCoordination.original_prompt }}</span>
        </div>
        <div class="coord-item">
          <span class="coord-label">ENHANCED:</span>
          <span class="coord-value">{{ currentCoordination.enhanced_prompt }}</span>
        </div>
        <div class="coord-item">
          <span class="coord-label">CHARACTER:</span>
          <span class="coord-value">{{ currentCoordination.character || 'None' }}</span>
        </div>
        <div class="coord-item">
          <span class="coord-label">STATUS:</span>
          <span class="coord-value status">{{ currentCoordination.status }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'

// Console state
const consoleLines = ref([])
const inputCommand = ref('')
const consoleOutput = ref(null)
const inputField = ref(null)
const echoConnected = ref(false)
const currentCoordination = ref(null)

// Available commands
const commands = {
  'help': 'Show available commands',
  'status': 'Check Echo Brain anime system status',
  'characters': 'List available characters',
  'generate': 'Start anime generation (usage: generate "prompt" [character])',
  'clear': 'Clear console output',
  'history': 'Show generation history'
}

// Initialize console
onMounted(async () => {
  addConsoleLine('system', 'Echo Brain Anime Coordinator v1.0')
  addConsoleLine('system', 'Initializing connection to Echo Brain...')

  await checkEchoConnection()

  if (echoConnected.value) {
    addConsoleLine('success', 'Connected to Echo Brain anime coordination system')
    await loadEchoStatus()
  } else {
    addConsoleLine('error', 'Failed to connect to Echo Brain - check service status')
  }

  addConsoleLine('info', 'Type "help" for available commands')
  focusInput()
})

async function checkEchoConnection() {
  try {
    const response = await fetch('https://192.168.50.135/api/echo/health', {
      method: 'GET'
    })
    echoConnected.value = response.ok
  } catch (error) {
    echoConnected.value = false
  }
}

async function loadEchoStatus() {
  try {
    const response = await fetch('https://192.168.50.135/api/echo/anime/system/status')
    if (response.ok) {
      const status = await response.json()
      addConsoleLine('info', `System Status: ${status.overall_status.toUpperCase()}`)
      addConsoleLine('info', `Active Coordinators: ${status.components.echo_coordination.coordinators_loaded}`)
      addConsoleLine('info', `Characters Loaded: ${status.components.character_management.characters_loaded}`)
      addConsoleLine('info', `Learning Engine: ${status.components.style_learning.active ? 'ACTIVE' : 'INACTIVE'}`)
    }
  } catch (error) {
    addConsoleLine('error', 'Failed to load Echo status')
  }
}

async function executeCommand() {
  const command = inputCommand.value.trim()
  if (!command) return

  // Add command to console
  addConsoleLine('command', `$ ${command}`)
  inputCommand.value = ''

  // Parse command
  const parts = command.split(' ')
  const cmd = parts[0].toLowerCase()
  const args = parts.slice(1)

  switch (cmd) {
    case 'help':
      showHelp()
      break
    case 'status':
      await refreshEchoStatus()
      break
    case 'characters':
      await showCharacters()
      break
    case 'generate':
      await handleGenerate(args)
      break
    case 'clear':
      clearConsole()
      break
    case 'history':
      await showHistory()
      break
    default:
      addConsoleLine('error', `Unknown command: ${cmd}. Type "help" for available commands.`)
  }

  await nextTick()
  scrollToBottom()
  focusInput()
}

function showHelp() {
  addConsoleLine('info', 'Available commands:')
  Object.entries(commands).forEach(([cmd, desc]) => {
    addConsoleLine('info', `  ${cmd.padEnd(12)} - ${desc}`)
  })
}

async function refreshEchoStatus() {
  addConsoleLine('info', 'Checking Echo Brain status...')
  await checkEchoConnection()
  if (echoConnected.value) {
    await loadEchoStatus()
  } else {
    addConsoleLine('error', 'Echo Brain not responding')
  }
}

async function showCharacters() {
  try {
    addConsoleLine('info', 'Loading character data from Echo Brain...')
    const response = await fetch('https://192.168.50.135/api/echo/anime/characters')
    if (response.ok) {
      const data = await response.json()
      addConsoleLine('success', `Found ${data.count} characters:`)
      data.characters.forEach(char => {
        addConsoleLine('info', `  • ${char.name} (source: ${char.sources.join(', ')})`)
      })
    } else {
      addConsoleLine('error', 'Failed to load characters')
    }
  } catch (error) {
    addConsoleLine('error', `Error loading characters: ${error.message}`)
  }
}

async function handleGenerate(args) {
  if (args.length === 0) {
    addConsoleLine('error', 'Usage: generate "prompt" [character]')
    addConsoleLine('info', 'Example: generate "walking in Tokyo street" "Kai Nakamura"')
    return
  }

  // Parse prompt and character
  const fullArgs = args.join(' ')
  const promptMatch = fullArgs.match(/"([^"]+)"/)
  const characterMatch = fullArgs.match(/"[^"]+"\s+"([^"]+)"/)

  if (!promptMatch) {
    addConsoleLine('error', 'Prompt must be in quotes. Example: generate "walking in street"')
    return
  }

  const prompt = promptMatch[1]
  const character = characterMatch ? characterMatch[1] : null

  addConsoleLine('command', `Initiating generation with Echo Brain coordination...`)
  addConsoleLine('info', `Prompt: "${prompt}"`)
  if (character) {
    addConsoleLine('info', `Character: "${character}"`)
  }

  try {
    const requestBody = { prompt }
    if (character) {
      requestBody.character = character
    }

    const response = await fetch('https://192.168.50.135/api/echo/anime/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody)
    })

    if (response.ok) {
      const result = await response.json()

      // Show Echo coordination details
      addConsoleLine('success', `Echo coordination started: ${result.orchestration_id}`)
      addConsoleLine('info', `Generation type: ${result.generation_result.generation_type}`)
      addConsoleLine('info', `Workflow: ${result.generation_result.workflow_used}`)
      addConsoleLine('info', `Status: ${result.generation_result.status}`)
      addConsoleLine('info', `Prompt ID: ${result.generation_result.prompt_id}`)

      // Show Echo's enhancements
      if (result.character_consistency?.enhanced_prompt) {
        addConsoleLine('success', 'Echo enhanced prompt with character consistency')
        addConsoleLine('info', `Enhanced: "${result.character_consistency.enhanced_prompt}"`)
      }

      // Store current coordination for panel
      currentCoordination.value = {
        orchestration_id: result.orchestration_id,
        original_prompt: prompt,
        enhanced_prompt: result.character_consistency?.enhanced_prompt || prompt,
        character: character,
        status: result.generation_result.status,
        prompt_id: result.generation_result.prompt_id
      }

      // Start monitoring
      monitorGeneration(result.generation_result.prompt_id)

    } else {
      addConsoleLine('error', 'Generation request failed')
    }
  } catch (error) {
    addConsoleLine('error', `Generation error: ${error.message}`)
  }
}

async function monitorGeneration(promptId) {
  let attempts = 0
  const maxAttempts = 20

  const checkStatus = async () => {
    try {
      const response = await fetch(`http://127.0.0.1:8188/history/${promptId}`)
      const history = await response.json()

      if (history && Object.keys(history).length > 0) {
        addConsoleLine('success', `Generation completed: ${promptId}`)
        if (currentCoordination.value) {
          currentCoordination.value.status = 'completed'
        }
        return
      }

      attempts++
      if (attempts < maxAttempts) {
        setTimeout(checkStatus, 3000)
      } else {
        addConsoleLine('warning', 'Generation monitoring timeout - check ComfyUI manually')
      }
    } catch (error) {
      addConsoleLine('info', `Generation still processing... (${attempts}/${maxAttempts})`)
      attempts++
      if (attempts < maxAttempts) {
        setTimeout(checkStatus, 3000)
      }
    }
  }

  setTimeout(checkStatus, 3000)
}

async function showHistory() {
  addConsoleLine('info', 'Loading generation history from Echo Brain...')
  // This would need a history endpoint - for now show placeholder
  addConsoleLine('info', 'Generation history feature requires additional Echo endpoint')
}

function addConsoleLine(type, content) {
  consoleLines.value.push({
    type,
    content,
    timestamp: new Date()
  })
}

function clearConsole() {
  consoleLines.value = []
  addConsoleLine('system', 'Console cleared')
}

function formatTimestamp(date) {
  return date.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

function scrollToBottom() {
  if (consoleOutput.value) {
    consoleOutput.value.scrollTop = consoleOutput.value.scrollHeight
  }
}

function focusInput() {
  if (inputField.value) {
    inputField.value.focus()
  }
}

function autocomplete() {
  const input = inputCommand.value.toLowerCase()
  const matchingCommands = Object.keys(commands).filter(cmd =>
    cmd.startsWith(input)
  )

  if (matchingCommands.length === 1) {
    inputCommand.value = matchingCommands[0] + ' '
  }
}
</script>

<style scoped>
.echo-anime-console {
  background: #0a0a0a;
  color: #e0e0e0;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  height: 100vh;
  display: flex;
  flex-direction: column;
  border: 1px solid #333;
}

.console-header {
  background: #1a1a1a;
  border-bottom: 1px solid #333;
  padding: 0.5rem 1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.console-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.prompt-symbol {
  color: #10b981;
  font-weight: bold;
}

.title-text {
  color: #e0e0e0;
  font-weight: 600;
}

.echo-status {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.8rem;
  color: #ef4444;
}

.echo-status.connected {
  color: #10b981;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.console-controls {
  display: flex;
  gap: 0.5rem;
}

.console-btn {
  background: transparent;
  border: 1px solid #555;
  color: #e0e0e0;
  padding: 0.25rem 0.5rem;
  border-radius: 3px;
  font-family: inherit;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}

.console-btn:hover {
  background: #333;
  border-color: #777;
}

.console-output {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  line-height: 1.4;
}

.console-line {
  margin-bottom: 0.25rem;
  display: flex;
  gap: 0.5rem;
}

.console-line.system {
  color: #8b5cf6;
}

.console-line.success {
  color: #10b981;
}

.console-line.error {
  color: #ef4444;
}

.console-line.warning {
  color: #f59e0b;
}

.console-line.info {
  color: #3b82f6;
}

.console-line.command {
  color: #e0e0e0;
  font-weight: bold;
}

.timestamp {
  color: #666;
  font-size: 0.8rem;
  min-width: 60px;
}

.console-input {
  background: #1a1a1a;
  border-top: 1px solid #333;
  padding: 0.5rem 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.input-prompt {
  color: #10b981;
  font-weight: bold;
}

.input-field {
  flex: 1;
  background: transparent;
  border: none;
  color: #e0e0e0;
  font-family: inherit;
  font-size: 1rem;
  outline: none;
}

.input-field::placeholder {
  color: #666;
}

.coordination-panel {
  background: #1a1a1a;
  border-top: 1px solid #333;
  border-bottom: 1px solid #333;
}

.panel-header {
  background: #065f46;
  padding: 0.5rem 1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-title {
  color: #e0e0e0;
  font-weight: bold;
  font-size: 0.9rem;
}

.coordination-id {
  color: #10b981;
  font-size: 0.8rem;
  font-family: inherit;
}

.coordination-content {
  padding: 0.75rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.coord-item {
  display: flex;
  gap: 0.5rem;
}

.coord-label {
  color: #888;
  min-width: 80px;
  font-size: 0.9rem;
}

.coord-value {
  color: #e0e0e0;
  font-size: 0.9rem;
}

.coord-value.status {
  color: #10b981;
  text-transform: uppercase;
}

/* Scrollbar styling */
.console-output::-webkit-scrollbar {
  width: 8px;
}

.console-output::-webkit-scrollbar-track {
  background: #1a1a1a;
}

.console-output::-webkit-scrollbar-thumb {
  background: #555;
  border-radius: 4px;
}

.console-output::-webkit-scrollbar-thumb:hover {
  background: #777;
}
</style>