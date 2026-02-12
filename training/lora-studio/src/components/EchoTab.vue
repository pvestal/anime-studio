<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <div>
        <h2 style="font-size: 18px; font-weight: 500;">Echo Brain</h2>
        <p style="font-size: 13px; color: var(--text-muted);">
          AI-assisted prompt enhancement and creative memory search.
        </p>
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <span
          :style="{
            display: 'inline-block',
            width: '8px', height: '8px',
            borderRadius: '50%',
            background: echoOnline ? 'var(--status-success)' : 'var(--status-error)',
          }"
        ></span>
        <span style="font-size: 12px; color: var(--text-muted);">
          {{ echoOnline ? 'Connected' : 'Offline' }}
        </span>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px;">

      <!-- Chat panel -->
      <div class="card" style="display: flex; flex-direction: column; min-height: 400px;">
        <div style="font-size: 14px; font-weight: 500; margin-bottom: 12px;">Memory Search</div>

        <!-- Character context selector -->
        <div style="margin-bottom: 12px;">
          <select v-model="chatCharSlug" style="width: 100%; font-size: 12px;">
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
            style="flex: 1; padding: 8px 12px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
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
      <div class="card" style="display: flex; flex-direction: column;">
        <div style="font-size: 14px; font-weight: 500; margin-bottom: 12px;">Enhance Prompt</div>

        <!-- Character selector -->
        <div style="margin-bottom: 12px;">
          <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Character</label>
          <select v-model="enhanceCharSlug" @change="loadDesignPrompt" style="width: 100%;">
            <option value="">Select character...</option>
            <option v-for="c in characters" :key="c.slug" :value="c.slug">
              {{ c.name }} ({{ c.project_name }})
            </option>
          </select>
        </div>

        <!-- Current prompt -->
        <div style="margin-bottom: 12px;">
          <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">
            Design Prompt
          </label>
          <textarea
            v-model="enhancePrompt"
            rows="4"
            placeholder="Enter or load a design_prompt to enhance..."
            style="width: 100%; padding: 8px 10px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; resize: vertical; font-family: var(--font-primary);"
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
            <label style="font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 6px;">
              Edit and apply to {{ enhanceCharSlug }}:
            </label>
            <textarea
              v-model="editedPrompt"
              rows="3"
              style="width: 100%; padding: 8px 10px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; resize: vertical; font-family: var(--font-primary);"
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
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useCharactersStore } from '@/stores/characters'
import { api } from '@/api/client'
import type { EchoEnhanceResponse } from '@/types'

const charactersStore = useCharactersStore()
const characters = computed(() => charactersStore.characters)

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
    // Refresh characters to pick up the change
    charactersStore.fetchCharacters()
  } catch (err: any) {
    applyMessage.value = `Error: ${err.message}`
  } finally {
    applying.value = false
  }
}
</script>
