<template>
  <div class="echo-collaboration">
    <!-- Echo Status Bar -->
    <div class="echo-status-bar">
      <div class="echo-indicator" :class="{ 'connected': echoConnected, 'active': echoActive }">
        <i class="pi pi-circle-fill"></i>
        <span>Echo Brain {{ echoConnected ? 'Connected' : 'Disconnected' }}</span>
      </div>
      <div class="echo-mode">
        <Tag :value="echoMode" :severity="echoMode === 'Production Director' ? 'success' : 'info'" />
      </div>
    </div>

    <!-- Real-time Echo Feedback -->
    <Card class="echo-feedback-card" v-if="currentEchoFeedback">
      <template #title>
        <i class="pi pi-brain"></i> Echo Brain Analysis
      </template>
      <template #content>
        <div class="echo-message">{{ currentEchoFeedback.message }}</div>
        <div class="echo-suggestions" v-if="currentEchoFeedback.suggestions">
          <h4>Suggestions:</h4>
          <ul>
            <li v-for="suggestion in currentEchoFeedback.suggestions" :key="suggestion">
              {{ suggestion }}
            </li>
          </ul>
        </div>
        <div class="echo-confidence">
          Confidence: {{ Math.round(currentEchoFeedback.confidence * 100) }}%
        </div>
      </template>
    </Card>

    <!-- Echo Generation Coordinator -->
    <Card class="echo-coordinator" v-if="showCoordinator">
      <template #title>
        <i class="pi pi-cog"></i> Echo Generation Coordinator
      </template>
      <template #content>
        <div class="coordinator-section">
          <h4>Character Consistency</h4>
          <div class="character-analysis" v-if="characterAnalysis">
            <p><strong>Character:</strong> {{ characterAnalysis.character_name }}</p>
            <p><strong>Consistency Score:</strong> {{ characterAnalysis.consistency_score }}/1.0</p>
            <div class="visual-traits">
              <Chip v-for="trait in characterAnalysis.visual_traits" :key="trait" :label="trait" />
            </div>
          </div>
        </div>

        <div class="coordinator-section">
          <h4>Style Learning</h4>
          <div class="style-preferences" v-if="stylePreferences">
            <div v-for="(value, key) in stylePreferences" :key="key" class="preference-item">
              <span class="preference-label">{{ key }}:</span>
              <span class="preference-value">{{ value }}</span>
            </div>
          </div>
        </div>

        <div class="coordinator-section">
          <h4>Generation Progress</h4>
          <div class="generation-status" v-if="currentGeneration">
            <ProgressBar :value="currentGeneration.progress" />
            <p>{{ currentGeneration.status_message }}</p>
            <div v-if="currentGeneration.echo_insights" class="echo-insights">
              <strong>Echo Insights:</strong> {{ currentGeneration.echo_insights }}
            </div>
          </div>
        </div>
      </template>
    </Card>

    <!-- Echo Chat Interface -->
    <Card class="echo-chat" v-if="showChat">
      <template #title>
        <i class="pi pi-comments"></i> Chat with Echo Brain
      </template>
      <template #content>
        <div class="chat-messages" ref="chatMessages">
          <div v-for="message in chatHistory" :key="message.id"
               :class="['chat-message', message.sender]">
            <div class="message-header">
              <strong>{{ message.sender === 'user' ? 'You' : 'Echo Brain' }}</strong>
              <span class="timestamp">{{ formatTime(message.timestamp) }}</span>
            </div>
            <div class="message-content">{{ message.content }}</div>
          </div>
        </div>
        <div class="chat-input">
          <InputText v-model="chatMessage" @keyup.enter="sendMessage"
                     placeholder="Ask Echo about generation, characters, or project..."
                     style="width: 100%;" />
          <Button icon="pi pi-send" @click="sendMessage" />
        </div>
      </template>
    </Card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, nextTick } from 'vue'
import { useToast } from 'primevue/usetoast'

const toast = useToast()

// Echo Connection State
const echoConnected = ref(false)
const echoActive = ref(false)
const echoMode = ref('Standby')
const echoSocket = ref(null)

// Echo Feedback
const currentEchoFeedback = ref(null)
const characterAnalysis = ref(null)
const stylePreferences = ref(null)
const currentGeneration = ref(null)

// UI State
const showCoordinator = ref(true)
const showChat = ref(false)

// Chat
const chatHistory = ref([])
const chatMessage = ref('')
const chatMessages = ref(null)

// Props
const props = defineProps({
  selectedProject: Object,
  selectedScene: Object,
  generationActive: Boolean
})

// Initialize Echo connection
async function connectToEcho() {
  try {
    // Check Echo health
    const healthResponse = await fetch('https://192.168.50.135/api/echo/health', {
      method: 'GET',
      headers: { 'Accept': 'application/json' }
    })

    if (healthResponse.ok) {
      echoConnected.value = true
      echoMode.value = 'Production Director'

      // Establish WebSocket for real-time collaboration
      initializeWebSocket()

      // Load initial Echo state
      await loadEchoState()

      toast.add({
        severity: 'success',
        summary: 'Echo Connected',
        detail: 'Echo Brain is ready for collaboration',
        life: 3000
      })
    }
  } catch (error) {
    console.error('Echo connection failed:', error)
    echoConnected.value = false
    toast.add({
      severity: 'warn',
      summary: 'Echo Disconnected',
      detail: 'Echo Brain unavailable - working in basic mode',
      life: 3000
    })
  }
}

function initializeWebSocket() {
  // Note: WebSocket endpoint would need to be implemented in Echo Brain
  try {
    echoSocket.value = new WebSocket('wss://192.168.50.135/api/echo/studio/collaborate')

    echoSocket.value.onopen = () => {
      echoActive.value = true
      console.log('Echo WebSocket connected')
    }

    echoSocket.value.onmessage = (event) => {
      const data = JSON.parse(event.data)
      handleEchoMessage(data)
    }

    echoSocket.value.onclose = () => {
      echoActive.value = false
      console.log('Echo WebSocket disconnected')
    }
  } catch (error) {
    console.error('WebSocket connection failed:', error)
  }
}

function handleEchoMessage(data) {
  switch (data.type) {
    case 'feedback':
      currentEchoFeedback.value = data.payload
      break
    case 'character_analysis':
      characterAnalysis.value = data.payload
      break
    case 'generation_progress':
      currentGeneration.value = data.payload
      break
    case 'chat_response':
      addChatMessage('echo', data.payload.message)
      break
  }
}

async function loadEchoState() {
  try {
    // Load character analysis if character is selected
    if (props.selectedScene?.characters) {
      const charResponse = await fetch(`https://192.168.50.135/api/echo/anime/characters`, {
        method: 'GET'
      })
      if (charResponse.ok) {
        const characters = await charResponse.json()
        characterAnalysis.value = characters[0] // Simplified for demo
      }
    }

    // Load style preferences
    const prefResponse = await fetch(`https://192.168.50.135/api/echo/anime/preferences/summary`, {
      method: 'GET'
    })
    if (prefResponse.ok) {
      stylePreferences.value = await prefResponse.json()
    }
  } catch (error) {
    console.error('Failed to load Echo state:', error)
  }
}

async function sendMessage() {
  if (!chatMessage.value.trim()) return

  addChatMessage('user', chatMessage.value)
  const message = chatMessage.value
  chatMessage.value = ''

  try {
    const response = await fetch('https://192.168.50.135/api/echo/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: message,
        context: {
          type: 'anime_studio_chat',
          project: props.selectedProject,
          scene: props.selectedScene
        }
      })
    })

    if (response.ok) {
      const data = await response.json()
      addChatMessage('echo', data.response)
    }
  } catch (error) {
    addChatMessage('echo', 'Sorry, I encountered an error processing your request.')
  }
}

function addChatMessage(sender, content) {
  chatHistory.value.push({
    id: Date.now(),
    sender,
    content,
    timestamp: new Date()
  })

  nextTick(() => {
    if (chatMessages.value) {
      chatMessages.value.scrollTop = chatMessages.value.scrollHeight
    }
  })
}

function formatTime(date) {
  return date.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Expose methods for parent component
defineExpose({
  requestEchoFeedback: async (prompt, character) => {
    if (!echoConnected.value) return null

    try {
      const response = await fetch('https://192.168.50.135/api/echo/anime/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, character })
      })

      if (response.ok) {
        const feedback = await response.json()
        currentEchoFeedback.value = feedback
        return feedback
      }
    } catch (error) {
      console.error('Echo feedback request failed:', error)
    }
    return null
  },

  startEchoGeneration: async (generationRequest) => {
    if (!echoConnected.value) return null

    try {
      const response = await fetch('https://192.168.50.135/api/echo/anime/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(generationRequest)
      })

      if (response.ok) {
        const result = await response.json()
        currentGeneration.value = result
        return result
      }
    } catch (error) {
      console.error('Echo generation request failed:', error)
    }
    return null
  }
})

// Lifecycle
onMounted(() => {
  connectToEcho()
})

onUnmounted(() => {
  if (echoSocket.value) {
    echoSocket.value.close()
  }
})
</script>

<style scoped>
.echo-collaboration {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.echo-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 6px;
}

.echo-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #999;
}

.echo-indicator.connected {
  color: #10b981;
}

.echo-indicator.active {
  color: #3b82f6;
}

.echo-feedback-card, .echo-coordinator, .echo-chat {
  background: #1a1a1a !important;
  border: 1px solid #333;
}

.echo-message {
  font-size: 1rem;
  margin-bottom: 1rem;
}

.echo-suggestions ul {
  list-style: none;
  padding: 0;
}

.echo-suggestions li {
  background: #2a2a2a;
  padding: 0.5rem;
  margin: 0.25rem 0;
  border-radius: 4px;
  border-left: 3px solid #3b82f6;
}

.echo-confidence {
  font-size: 0.9rem;
  color: #999;
  text-align: right;
}

.coordinator-section {
  margin-bottom: 1.5rem;
}

.coordinator-section h4 {
  margin: 0 0 0.5rem 0;
  color: #e0e0e0;
}

.visual-traits {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.preference-item {
  display: flex;
  justify-content: space-between;
  padding: 0.25rem 0;
  border-bottom: 1px solid #333;
}

.preference-label {
  font-weight: 600;
}

.generation-status {
  background: #2a2a2a;
  padding: 1rem;
  border-radius: 6px;
}

.echo-insights {
  margin-top: 0.5rem;
  padding: 0.5rem;
  background: #1e293b;
  border-radius: 4px;
  border-left: 3px solid #06b6d4;
}

.chat-messages {
  height: 200px;
  overflow-y: auto;
  border: 1px solid #333;
  border-radius: 4px;
  padding: 0.5rem;
  background: #0a0a0a;
}

.chat-message {
  margin-bottom: 1rem;
  padding: 0.5rem;
  border-radius: 6px;
}

.chat-message.user {
  background: #1e293b;
  margin-left: 2rem;
}

.chat-message.echo {
  background: #065f46;
  margin-right: 2rem;
}

.message-header {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
  margin-bottom: 0.25rem;
  opacity: 0.8;
}

.chat-input {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
</style>