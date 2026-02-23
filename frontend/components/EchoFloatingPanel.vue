<template>
  <!-- Floating trigger button -->
  <button
    class="echo-fab"
    :class="{ active: open }"
    @click="open = !open"
    title="Echo Brain"
  >
    <span class="echo-fab-dot" :class="{ online: echoOnline }"></span>
    Echo
  </button>

  <!-- Slide-over panel -->
  <Teleport to="body">
    <Transition name="echo-panel">
      <div v-if="open" class="echo-overlay" @click.self="open = false" @keydown.escape.window="open = false">
        <div class="echo-panel">
          <!-- Header -->
          <div class="echo-header">
            <div style="display: flex; align-items: center; gap: 8px;">
              <h3 style="margin: 0; font-size: 15px; font-weight: 500;">Echo Brain</h3>
              <span class="echo-status-dot" :class="{ online: echoOnline }"></span>
              <span style="font-size: 11px; color: var(--text-muted);">{{ echoOnline ? 'Connected' : 'Offline' }}</span>
            </div>
            <button class="btn" style="font-size: 13px; padding: 4px 10px;" @click="open = false">Close</button>
          </div>

          <!-- Sub-tab toggle -->
          <div style="display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border-primary);">
            <button
              class="echo-subtab"
              :class="{ active: subtab === 'chat' }"
              @click="subtab = 'chat'"
            >Memory Search</button>
            <button
              class="echo-subtab"
              :class="{ active: subtab === 'enhance' }"
              @click="subtab = 'enhance'"
            >Enhance Prompt</button>
          </div>

          <!-- Chat panel -->
          <div v-if="subtab === 'chat'" style="display: flex; flex-direction: column; flex: 1; min-height: 0;">
            <!-- Character context selector -->
            <div style="margin-bottom: 12px;">
              <select v-model="chatCharSlug" class="field-input" style="width: 100%; font-size: 12px;">
                <option value="">No character context</option>
                <option v-for="c in characters" :key="c.slug" :value="c.slug">
                  {{ c.name }} ({{ c.project_name }})
                </option>
              </select>
            </div>

            <!-- Messages -->
            <div
              ref="messagesEl"
              style="flex: 1; overflow-y: auto; padding: 8px; background: var(--bg-primary); border-radius: 4px; margin-bottom: 12px; min-height: 200px;"
            >
              <div
                v-for="(msg, i) in messages"
                :key="i"
                :style="{
                  padding: '8px 12px',
                  marginBottom: '8px',
                  borderRadius: '6px',
                  fontSize: '13px',
                  whiteSpace: 'pre-wrap',
                  background: msg.role === 'user' ? 'var(--bg-secondary)' : 'transparent',
                  borderLeft: msg.role === 'echo' ? '2px solid var(--accent-primary)' : 'none',
                  color: msg.role === 'user' ? 'var(--text-primary)' : 'var(--text-secondary)',
                }"
              >
                <div style="font-size: 10px; color: var(--text-muted); margin-bottom: 4px; text-transform: uppercase;">
                  {{ msg.role === 'user' ? 'You' : 'Echo Brain' }}
                </div>
                {{ msg.text }}
              </div>

              <div v-if="chatLoading" style="padding: 8px; font-size: 12px; color: var(--text-muted);">
                Searching memories...
              </div>
            </div>

            <!-- Input -->
            <div style="display: flex; gap: 8px;">
              <input
                v-model="chatInput"
                type="text"
                placeholder="Ask Echo Brain..."
                @keyup.enter="sendChat"
                class="field-input"
                style="flex: 1;"
              />
              <button
                class="btn btn-active"
                @click="sendChat"
                :disabled="!chatInput.trim() || chatLoading"
                style="padding: 8px 16px;"
              >Send</button>
            </div>
          </div>

          <!-- Enhance Prompt panel -->
          <div v-if="subtab === 'enhance'" style="display: flex; flex-direction: column; flex: 1; min-height: 0;">
            <!-- Character selector -->
            <div style="margin-bottom: 12px;">
              <label class="field-label">Character</label>
              <select v-model="enhanceCharSlug" @change="loadDesignPrompt" class="field-input" style="width: 100%;">
                <option value="">Select character...</option>
                <option v-for="c in characters" :key="c.slug" :value="c.slug">
                  {{ c.name }} ({{ c.project_name }})
                </option>
              </select>
            </div>

            <!-- Current prompt -->
            <div style="margin-bottom: 12px;">
              <label class="field-label">Design Prompt</label>
              <textarea
                v-model="enhancePrompt"
                rows="4"
                placeholder="Enter or load a design_prompt to enhance..."
                class="field-input"
                style="width: 100%; resize: vertical;"
              ></textarea>
            </div>

            <button
              class="btn btn-active"
              @click="enhanceCurrentPrompt"
              :disabled="!enhancePrompt.trim() || enhancing"
              style="margin-bottom: 16px;"
            >
              {{ enhancing ? 'Enhancing...' : 'Get Enhancement Suggestions' }}
            </button>

            <!-- Enhancement results -->
            <div v-if="enhanceResult" style="flex: 1; overflow-y: auto;">
              <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">
                Echo Brain Context ({{ enhanceResult.echo_brain_context.length }} memories)
              </div>
              <div
                v-for="(ctx, i) in enhanceResult.echo_brain_context"
                :key="i"
                style="padding: 8px; margin-bottom: 8px; background: var(--bg-primary); border-radius: 4px; font-size: 12px; color: var(--text-secondary); border-left: 2px solid var(--accent-primary); max-height: 120px; overflow-y: auto;"
              >
                {{ ctx }}
              </div>

              <!-- Apply updated prompt -->
              <div v-if="enhanceCharSlug" style="margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-primary);">
                <label class="field-label">Edit and apply to {{ enhanceCharSlug }}:</label>
                <textarea
                  v-model="editedPrompt"
                  rows="3"
                  class="field-input"
                  style="width: 100%; resize: vertical;"
                ></textarea>
                <div style="display: flex; gap: 8px; margin-top: 8px;">
                  <button
                    class="btn btn-active"
                    @click="applyPrompt"
                    :disabled="!editedPrompt.trim() || applying"
                  >{{ applying ? 'Saving...' : 'Apply to Character' }}</button>
                  <span v-if="applyMessage" style="font-size: 12px; color: var(--status-success); align-self: center;">{{ applyMessage }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useCharactersStore } from '@/stores/characters'
import { api } from '@/api/client'
import type { EchoEnhanceResponse } from '@/types'

const charactersStore = useCharactersStore()
const characters = computed(() => charactersStore.characters)

// Panel state
const open = ref(false)
const subtab = ref<'chat' | 'enhance'>('chat')

// Echo status
const echoOnline = ref(false)

// Chat state
const chatInput = ref('')
const chatCharSlug = ref('')
const chatLoading = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
const messages = ref<Array<{ role: 'user' | 'echo'; text: string }>>([])

// Enhance state
const enhanceCharSlug = ref('')
const enhancePrompt = ref('')
const enhancing = ref(false)
const enhanceResult = ref<EchoEnhanceResponse | null>(null)
const editedPrompt = ref('')
const applying = ref(false)
const applyMessage = ref('')

onMounted(async () => {
  try {
    const status = await api.echoStatus()
    echoOnline.value = status.status === 'connected'
  } catch {
    echoOnline.value = false
  }
})

async function sendChat() {
  const text = chatInput.value.trim()
  if (!text) return

  messages.value.push({ role: 'user', text })
  chatInput.value = ''
  chatLoading.value = true

  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight

  try {
    const result = await api.echoChat(text, chatCharSlug.value || undefined)
    messages.value.push({ role: 'echo', text: result.response })
  } catch (err: any) {
    messages.value.push({ role: 'echo', text: `Error: ${err.message}` })
  } finally {
    chatLoading.value = false
    await nextTick()
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

function loadDesignPrompt() {
  const char = characters.value.find(c => c.slug === enhanceCharSlug.value)
  if (char) {
    enhancePrompt.value = char.design_prompt || ''
    editedPrompt.value = char.design_prompt || ''
  }
  enhanceResult.value = null
  applyMessage.value = ''
}

async function enhanceCurrentPrompt() {
  if (!enhancePrompt.value.trim()) return
  enhancing.value = true
  enhanceResult.value = null

  try {
    const result = await api.echoEnhancePrompt(
      enhancePrompt.value,
      enhanceCharSlug.value || undefined,
    )
    enhanceResult.value = result
    editedPrompt.value = enhancePrompt.value
  } catch (err: any) {
    enhanceResult.value = {
      original_prompt: enhancePrompt.value,
      echo_brain_context: [`Error: ${err.message}`],
      suggestion: '',
    }
  } finally {
    enhancing.value = false
  }
}

async function applyPrompt() {
  if (!enhanceCharSlug.value || !editedPrompt.value.trim()) return
  applying.value = true
  applyMessage.value = ''

  try {
    await api.updateCharacter(enhanceCharSlug.value, { design_prompt: editedPrompt.value.trim() })
    applyMessage.value = 'Saved!'
    charactersStore.fetchCharacters()
  } catch (err: any) {
    applyMessage.value = `Error: ${err.message}`
  } finally {
    applying.value = false
  }
}
</script>

<style scoped>
.echo-fab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 16px;
  border: 1px solid var(--border-primary);
  background: var(--bg-primary);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  font-family: var(--font-primary);
  transition: all 150ms ease;
}

.echo-fab:hover {
  border-color: var(--accent-primary);
  color: var(--text-primary);
}

.echo-fab.active {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
  color: #fff;
}

.echo-fab-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--status-error);
}

.echo-fab-dot.online {
  background: var(--status-success);
}

.echo-overlay {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 2000;
  display: flex;
  justify-content: flex-end;
}

.echo-panel {
  width: 480px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-primary);
  padding: 20px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.echo-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-primary);
}

.echo-status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--status-error);
}

.echo-status-dot.online {
  background: var(--status-success);
}

.echo-subtab {
  padding: 8px 16px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  font-family: var(--font-primary);
  transition: color 150ms ease;
}

.echo-subtab.active {
  border-bottom-color: var(--accent-primary);
  color: var(--accent-primary);
}

.field-label {
  font-size: 11px;
  color: var(--text-muted);
  display: block;
  margin-bottom: 4px;
}

.field-input {
  padding: 5px 8px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
  font-family: var(--font-primary);
  width: 100%;
  box-sizing: border-box;
}

.field-input:focus {
  border-color: var(--border-focus);
  outline: none;
}

/* Panel transitions */
.echo-panel-enter-active,
.echo-panel-leave-active {
  transition: all 200ms ease;
}

.echo-panel-enter-from .echo-panel,
.echo-panel-leave-to .echo-panel {
  transform: translateX(100%);
}

.echo-panel-enter-from,
.echo-panel-leave-to {
  opacity: 0;
}
</style>
