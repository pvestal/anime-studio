<template>
  <div class="echo-brain-chat">
    <!-- Chat Header -->
    <div class="chat-header">
      <h3>
        <i class="pi pi-sparkles"></i>
        Echo Brain Creative Assistant
      </h3>
      <span class="status-badge" :class="connectionStatus">
        {{ connectionStatus === 'connected' ? 'Online' : 'Offline' }}
      </span>
    </div>

    <!-- Chat History -->
    <div class="chat-history" ref="chatHistory">
      <div v-for="msg in messages" :key="msg.id" :class="`message ${msg.role}`">
        <div class="avatar">
          {{ msg.role === 'assistant' ? '🤖' : '👤' }}
        </div>
        <div class="content">
          <div class="message-text" v-html="formatMessage(msg.content)"></div>

          <!-- AI suggestions as interactive cards -->
          <div v-if="msg.suggestions && msg.suggestions.length > 0" class="suggestions">
            <div v-for="suggestion in msg.suggestions"
                 :key="suggestion.id"
                 class="suggestion-card">
              <div class="suggestion-header">
                <i :class="getSuggestionIcon(suggestion.type)"></i>
                <span>{{ getSuggestionTitle(suggestion.type) }}</span>
              </div>
              <div class="suggestion-content">
                {{ suggestion.text }}
              </div>
              <div class="suggestion-actions">
                <Button
                  label="Apply"
                  icon="pi pi-check"
                  @click="applySuggestion(suggestion)"
                  severity="success"
                  size="small" />
                <Button
                  label="Modify"
                  icon="pi pi-pencil"
                  @click="modifySuggestion(suggestion)"
                  severity="secondary"
                  size="small" />
              </div>
            </div>
          </div>

          <!-- Generated assets preview -->
          <div v-if="msg.assets && msg.assets.length > 0" class="generated-assets">
            <div v-for="asset in msg.assets" :key="asset.id" class="asset-preview">
              <img v-if="asset.type === 'image'" :src="asset.url" :alt="asset.name" />
              <div class="asset-info">
                <span>{{ asset.name }}</span>
                <Button icon="pi pi-download" text rounded @click="downloadAsset(asset)" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Typing indicator -->
      <div v-if="isTyping" class="message assistant typing">
        <div class="avatar">🤖</div>
        <div class="content">
          <div class="typing-indicator">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      </div>
    </div>

    <!-- Quick Actions Bar -->
    <div class="quick-actions">
      <Button
        v-for="action in quickActions"
        :key="action.id"
        :label="action.label"
        :icon="action.icon"
        @click="performQuickAction(action.id)"
        :severity="action.severity"
        size="small"
        class="quick-action-btn" />
    </div>

    <!-- Chat Input -->
    <div class="chat-input">
      <div class="input-wrapper">
        <Textarea
          v-model="userInput"
          placeholder="Ask Echo Brain for story ideas, character designs, visual styles, or creative suggestions..."
          :autoResize="true"
          :rows="2"
          @keydown.enter.ctrl="sendMessage"
          class="message-input" />

        <div class="input-actions">
          <Button
            icon="pi pi-paperclip"
            @click="attachContext"
            v-tooltip="'Attach context'"
            text
            rounded />
          <Button
            icon="pi pi-send"
            @click="sendMessage"
            :disabled="!userInput.trim() || isTyping"
            severity="primary"
            rounded />
        </div>
      </div>

      <!-- Context indicator -->
      <div v-if="currentContext" class="context-indicator">
        <Tag :value="`Context: ${currentContext.type}`" severity="info" />
        <span>{{ currentContext.name }}</span>
        <i class="pi pi-times" @click="clearContext"></i>
      </div>
    </div>

    <!-- Suggestion Modification Dialog -->
    <Dialog v-model:visible="showModifyDialog" header="Modify Suggestion" :modal="true" :style="{width: '50vw'}">
      <div v-if="modifyingSuggestion">
        <div class="field">
          <label>Type</label>
          <InputText v-model="modifyingSuggestion.type" disabled />
        </div>
        <div class="field">
          <label>Content</label>
          <Textarea v-model="modifyingSuggestion.text" :rows="5" style="width: 100%" />
        </div>
        <div v-if="modifyingSuggestion.data" class="field">
          <label>Parameters</label>
          <Textarea
            v-model="modifiedData"
            :rows="10"
            style="width: 100%; font-family: monospace;" />
        </div>
      </div>
      <template #footer>
        <Button label="Cancel" @click="showModifyDialog = false" severity="secondary" />
        <Button label="Apply Modified" @click="applyModifiedSuggestion" severity="primary" />
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import Dialog from 'primevue/dialog'
import Tag from 'primevue/tag'
import InputText from 'primevue/inputtext'

const props = defineProps({
  projectId: Number,
  episodeId: Number,
  characterId: Number
})

const emit = defineEmits(['suggestion-applied', 'asset-generated', 'context-updated'])

const toast = useToast()

// State
const messages = ref([])
const userInput = ref('')
const isTyping = ref(false)
const connectionStatus = ref('disconnected')
const currentContext = ref(null)
const showModifyDialog = ref(false)
const modifyingSuggestion = ref(null)
const modifiedData = ref('')

// Quick actions configuration
const quickActions = ref([
  { id: 'brainstorm_episode', label: 'Brainstorm Episode', icon: 'pi pi-book', severity: 'info' },
  { id: 'suggest_character', label: 'Design Character', icon: 'pi pi-user-plus', severity: 'success' },
  { id: 'analyze_style', label: 'Analyze Style', icon: 'pi pi-palette', severity: 'warning' },
  { id: 'search_similar', label: 'Find Similar', icon: 'pi pi-search', severity: 'secondary' },
  { id: 'improve_consistency', label: 'Improve Consistency', icon: 'pi pi-sync', severity: 'help' }
])

// Chat history ref for auto-scrolling
const chatHistory = ref(null)

// Lifecycle
onMounted(async () => {
  await connectToEchoBrain()
  loadChatHistory()

  // Set initial context if provided
  if (props.projectId) {
    setContext('project', props.projectId)
  }
})

// Watch for context changes
watch(() => props.episodeId, (newId) => {
  if (newId) {
    setContext('episode', newId)
  }
})

watch(() => props.characterId, (newId) => {
  if (newId) {
    setContext('character', newId)
  }
})

// Methods
async function connectToEchoBrain() {
  try {
    const response = await fetch('/api/echo-brain/status')
    if (response.ok) {
      connectionStatus.value = 'connected'
      addSystemMessage('Echo Brain connected and ready to assist!')
    } else {
      connectionStatus.value = 'offline'
      addSystemMessage('Echo Brain is offline. Using fallback mode.')
    }
  } catch (error) {
    console.error('Could not connect to Echo Brain:', error)
    connectionStatus.value = 'offline'
  }
}

async function sendMessage() {
  if (!userInput.value.trim() || isTyping.value) return

  const message = userInput.value
  userInput.value = ''

  // Add user message
  addMessage('user', message)

  // Show typing indicator
  isTyping.value = true

  try {
    const response = await fetch('/api/echo-brain/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        context: getContextData(),
        project_id: props.projectId,
        episode_id: props.episodeId,
        character_id: props.characterId
      })
    })

    const data = await response.json()

    // Add assistant response
    addMessage('assistant', data.response, {
      suggestions: data.suggestions,
      assets: data.generated_assets
    })

    // Handle any actions
    if (data.actions) {
      handleActions(data.actions)
    }

  } catch (error) {
    console.error('Chat error:', error)
    addMessage('assistant', 'Sorry, I encountered an error. Please try again.')
  } finally {
    isTyping.value = false
  }

  scrollToBottom()
}

async function performQuickAction(actionId) {
  isTyping.value = true

  try {
    const response = await fetch(`/api/echo-brain/quick-action/${actionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        context: getContextData(),
        project_id: props.projectId
      })
    })

    const data = await response.json()

    // Add assistant response with suggestions
    addMessage('assistant', data.message, {
      suggestions: data.suggestions,
      assets: data.assets
    })

    // Handle actions
    if (data.actions) {
      handleActions(data.actions)
    }

  } catch (error) {
    console.error('Quick action error:', error)
    addMessage('assistant', 'Failed to perform action. Please try again.')
  } finally {
    isTyping.value = false
  }

  scrollToBottom()
}

async function applySuggestion(suggestion) {
  try {
    const response = await fetch('/api/echo-brain/apply-suggestion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        suggestion,
        project_id: props.projectId
      })
    })

    const result = await response.json()

    if (result.success) {
      toast.add({
        severity: 'success',
        summary: 'Suggestion Applied',
        detail: result.message,
        life: 3000
      })

      emit('suggestion-applied', {
        type: suggestion.type,
        data: result.data
      })

      // Add confirmation message
      addMessage('assistant', `✅ ${result.message}`)

      // If assets were generated
      if (result.generated_assets) {
        emit('asset-generated', result.generated_assets)
      }
    } else {
      throw new Error(result.error)
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Application Failed',
      detail: error.message,
      life: 5000
    })
  }
}

function modifySuggestion(suggestion) {
  modifyingSuggestion.value = { ...suggestion }
  modifiedData.value = JSON.stringify(suggestion.data, null, 2)
  showModifyDialog.value = true
}

async function applyModifiedSuggestion() {
  try {
    const modifiedSuggestion = {
      ...modifyingSuggestion.value,
      data: JSON.parse(modifiedData.value)
    }

    await applySuggestion(modifiedSuggestion)
    showModifyDialog.value = false
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Invalid JSON',
      detail: 'Please check the JSON syntax',
      life: 3000
    })
  }
}

function attachContext() {
  // TODO: Implement context attachment UI
  toast.add({
    severity: 'info',
    summary: 'Attach Context',
    detail: 'Select project, episode, or character context',
    life: 3000
  })
}

function setContext(type, id) {
  currentContext.value = {
    type,
    id,
    name: `${type} #${id}`
  }
  emit('context-updated', currentContext.value)
}

function clearContext() {
  currentContext.value = null
  emit('context-updated', null)
}

function getContextData() {
  const context = {
    project_id: props.projectId,
    episode_id: props.episodeId,
    character_id: props.characterId
  }

  if (currentContext.value) {
    context.attached_context = currentContext.value
  }

  return context
}

async function downloadAsset(asset) {
  try {
    const response = await fetch(asset.url)
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = asset.name
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Download Failed',
      detail: 'Could not download asset',
      life: 3000
    })
  }
}

function handleActions(actions) {
  actions.forEach(action => {
    switch (action.type) {
      case 'refresh_gallery':
        emit('refresh-gallery')
        break
      case 'update_character':
        emit('update-character', action.data)
        break
      case 'navigate_to':
        // Handle navigation
        break
      default:
        console.log('Unhandled action:', action)
    }
  })
}

// Helper functions
function addMessage(role, content, extras = {}) {
  messages.value.push({
    id: Date.now() + Math.random(),
    role,
    content,
    timestamp: new Date(),
    ...extras
  })
}

function addSystemMessage(content) {
  addMessage('system', content)
}

function formatMessage(content) {
  // Convert markdown-like formatting to HTML
  return content
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/```(.*?)```/gs, '<pre><code>$1</code></pre>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}

function getSuggestionIcon(type) {
  const icons = {
    'storyline': 'pi pi-book',
    'character_design': 'pi pi-user',
    'visual_style': 'pi pi-palette',
    'scene_generation': 'pi pi-image',
    'improvement': 'pi pi-chart-line'
  }
  return icons[type] || 'pi pi-sparkles'
}

function getSuggestionTitle(type) {
  const titles = {
    'storyline': 'Storyline Suggestion',
    'character_design': 'Character Design',
    'visual_style': 'Visual Style',
    'scene_generation': 'Scene Generation',
    'improvement': 'Quality Improvement'
  }
  return titles[type] || 'Creative Suggestion'
}

function loadChatHistory() {
  // TODO: Load previous chat history from localStorage or API
  const savedHistory = localStorage.getItem('echo-brain-chat-history')
  if (savedHistory) {
    try {
      messages.value = JSON.parse(savedHistory).slice(-50) // Keep last 50 messages
    } catch (error) {
      console.error('Could not load chat history:', error)
    }
  }
}

function saveChat() {
  localStorage.setItem('echo-brain-chat-history', JSON.stringify(messages.value))
}

async function scrollToBottom() {
  await nextTick()
  if (chatHistory.value) {
    chatHistory.value.scrollTop = chatHistory.value.scrollHeight
  }
}

// Auto-save chat history
watch(messages, () => {
  saveChat()
}, { deep: true })
</script>

<style scoped>
.echo-brain-chat {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #0a0a0a;
  border: 1px solid #333;
  border-radius: 8px;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: #1a1a1a;
  border-bottom: 1px solid #333;
}

.chat-header h3 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  color: #e0e0e0;
}

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.85rem;
  font-weight: 600;
}

.status-badge.connected {
  background: #22c55e20;
  color: #22c55e;
}

.status-badge.offline {
  background: #ef444420;
  color: #ef4444;
}

.chat-history {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  background: #0a0a0a;
}

.message {
  display: flex;
  gap: 1rem;
  margin-bottom: 1.5rem;
  animation: fadeIn 0.3s ease-in;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.avatar {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #2a2a2a;
  flex-shrink: 0;
  font-size: 1.2rem;
}

.message.user .avatar {
  background: #667eea;
}

.message.assistant .avatar {
  background: #22c55e;
}

.content {
  flex: 1;
  color: #e0e0e0;
}

.message-text {
  padding: 0.75rem;
  background: #1a1a1a;
  border-radius: 8px;
  margin-bottom: 0.5rem;
  line-height: 1.5;
}

.message.user .message-text {
  background: #667eea20;
  border: 1px solid #667eea40;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-top: 1rem;
}

.suggestion-card {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 1rem;
  flex: 1 1 250px;
  min-width: 250px;
  transition: all 0.2s;
}

.suggestion-card:hover {
  border-color: #667eea;
  transform: translateY(-2px);
}

.suggestion-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  color: #667eea;
  font-weight: 600;
}

.suggestion-content {
  color: #999;
  font-size: 0.9rem;
  margin-bottom: 1rem;
}

.suggestion-actions {
  display: flex;
  gap: 0.5rem;
}

.generated-assets {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  margin-top: 1rem;
}

.asset-preview {
  position: relative;
  border: 1px solid #333;
  border-radius: 8px;
  overflow: hidden;
  width: 200px;
}

.asset-preview img {
  width: 100%;
  height: 150px;
  object-fit: cover;
}

.asset-info {
  padding: 0.5rem;
  background: #1a1a1a;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.85rem;
}

.typing-indicator {
  display: flex;
  gap: 0.25rem;
  padding: 0.75rem;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background: #667eea;
  border-radius: 50%;
  animation: typing 1.4s infinite;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 80%, 100% {
    opacity: 0.3;
    transform: scale(1);
  }
  40% {
    opacity: 1;
    transform: scale(1.3);
  }
}

.quick-actions {
  display: flex;
  gap: 0.5rem;
  padding: 1rem;
  background: #1a1a1a;
  border-top: 1px solid #333;
  overflow-x: auto;
}

.quick-action-btn {
  white-space: nowrap;
}

.chat-input {
  padding: 1rem;
  background: #1a1a1a;
  border-top: 1px solid #333;
}

.input-wrapper {
  display: flex;
  gap: 0.5rem;
}

.message-input {
  flex: 1;
  background: #0a0a0a !important;
  border: 1px solid #333 !important;
  color: #e0e0e0 !important;
}

.input-actions {
  display: flex;
  gap: 0.5rem;
  align-items: flex-end;
}

.context-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
  padding: 0.5rem;
  background: #0a0a0a;
  border: 1px solid #333;
  border-radius: 6px;
  font-size: 0.9rem;
}

.context-indicator i {
  cursor: pointer;
  color: #999;
}

.context-indicator i:hover {
  color: #ef4444;
}

.field {
  margin-bottom: 1rem;
}

.field label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 600;
  color: #e0e0e0;
}

/* Custom scrollbar */
.chat-history::-webkit-scrollbar {
  width: 8px;
}

.chat-history::-webkit-scrollbar-track {
  background: #1a1a1a;
}

.chat-history::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 4px;
}

.chat-history::-webkit-scrollbar-thumb:hover {
  background: #444;
}
</style>