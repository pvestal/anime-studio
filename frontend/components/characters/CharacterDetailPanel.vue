<template>
  <div class="panel-overlay" @click.self="$emit('close')" @keydown.escape.window="$emit('close')">
    <div class="panel-slide">
      <!-- Header -->
      <div class="panel-header">
        <div>
          <h2 style="font-size: 18px; font-weight: 500; margin: 0;">{{ character.name }}</h2>
          <span style="font-size: 12px; color: var(--text-muted);">{{ character.project_name }}</span>
        </div>
        <button class="btn" style="font-size: 16px; padding: 4px 10px; line-height: 1;" @click="$emit('close')">&times;</button>
      </div>

      <!-- Training status bar -->
      <div class="panel-section" style="padding: 12px 20px; background: var(--bg-primary);">
        <div style="display: flex; gap: 24px; align-items: center; font-size: 13px;">
          <div>
            <span :style="{ color: characterStats.canTrain ? 'var(--status-success)' : 'var(--text-secondary)', fontWeight: 600 }">
              {{ characterStats.approved }}/{{ minTrainingImages }}
            </span>
            <span style="color: var(--text-muted);"> approved</span>
          </div>
          <div v-if="characterStats.pending > 0">
            <span style="font-weight: 600;">{{ characterStats.pending }}</span>
            <span style="color: var(--text-muted);"> pending</span>
          </div>
          <span
            v-if="characterStats.canTrain"
            class="badge badge-approved"
            style="font-size: 11px;"
          >Ready to Train</span>
        </div>
        <div class="progress-track" style="height: 6px; margin-top: 8px;">
          <div
            class="progress-bar"
            :class="{ ready: characterStats.canTrain }"
            :style="{ width: `${Math.min(100, (characterStats.approved / minTrainingImages) * 100)}%` }"
          ></div>
        </div>
      </div>

      <!-- Design Prompt Editor -->
      <div class="panel-section">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
          <label style="font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Design Prompt</label>
          <EchoAssistButton
            context-type="design_prompt"
            :context-payload="{
              project_name: character.project_name,
              character_name: character.name,
              character_slug: character.slug,
              checkpoint_model: character.checkpoint_model,
            }"
            :current-value="promptText"
            compact
            @accept="promptText = $event.suggestion"
          />
        </div>
        <textarea
          v-model="promptText"
          rows="8"
          class="prompt-textarea"
          placeholder="Enter design prompt for this character..."
        ></textarea>
        <div style="display: flex; gap: 6px; margin-top: 8px;">
          <button
            class="btn"
            :class="{ 'btn-primary': promptDirty }"
            style="font-size: 12px;"
            @click="savePrompt"
            :disabled="!promptDirty || saving"
          >
            {{ saving ? 'Saving...' : promptSaved ? 'Saved' : 'Save Prompt' }}
          </button>
          <button
            class="btn"
            style="font-size: 12px; color: var(--accent-primary);"
            @click="saveAndRegenerate"
            :disabled="!promptDirty || saving"
          >
            Save & Regenerate
          </button>
        </div>
      </div>

      <!-- Quick Actions -->
      <div class="panel-section" style="display: flex; gap: 8px; padding: 12px 20px;">
        <button
          v-if="!characterStats.canTrain"
          class="btn"
          style="font-size: 12px; color: var(--accent-primary); border-color: var(--accent-primary);"
          @click="$emit('generate-more', character)"
        >
          Generate {{ minTrainingImages - characterStats.approved }} More
        </button>
        <RouterLink
          v-if="characterStats.canTrain"
          to="/train"
          class="btn"
          style="font-size: 12px; text-decoration: none; color: var(--status-success); border-color: var(--status-success);"
        >
          Start Training
        </RouterLink>
        <RouterLink
          to="/review"
          class="btn"
          style="font-size: 12px; text-decoration: none;"
        >
          Review Images
        </RouterLink>
      </div>

      <!-- Image Gallery -->
      <div class="panel-section" style="flex: 1; overflow-y: auto;">
        <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px;">
          Approved Images ({{ approvedImages.length }})
        </div>
        <div v-if="approvedImages.length === 0" style="text-align: center; padding: 24px; color: var(--text-muted); font-size: 13px;">
          No approved images yet
        </div>
        <div v-else class="image-grid">
          <img
            v-for="img in approvedImages"
            :key="img.name"
            :src="imageUrl(img.name)"
            class="gallery-image"
            loading="lazy"
            @click="openImage(img.name)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { RouterLink } from 'vue-router'
import type { Character, DatasetImage } from '@/types'
import { api } from '@/api/client'
import EchoAssistButton from '../EchoAssistButton.vue'

interface CharacterStats {
  total: number
  approved: number
  pending: number
  canTrain: boolean
}

const props = defineProps<{
  character: Character
  datasetImages: DatasetImage[]
  characterStats: CharacterStats
  minTrainingImages: number
}>()

const emit = defineEmits<{
  close: []
  'save-prompt': [payload: { character: Character; text: string }]
  'generate-more': [character: Character]
  refresh: []
}>()

const promptText = ref(props.character.design_prompt || '')
const saving = ref(false)
const promptSaved = ref(false)

watch(() => props.character, (c) => {
  promptText.value = c.design_prompt || ''
  promptSaved.value = false
})

const promptDirty = computed(() => promptText.value !== (props.character.design_prompt || ''))

const approvedImages = computed(() =>
  props.datasetImages.filter(img => img.status === 'approved')
)

function imageUrl(name: string): string {
  return api.imageUrl(props.character.slug, name)
}

function openImage(name: string) {
  window.open(imageUrl(name), '_blank')
}

async function savePrompt() {
  if (!promptDirty.value) return
  saving.value = true
  try {
    await api.updateCharacter(props.character.slug, { design_prompt: promptText.value.trim() })
    promptSaved.value = true
    setTimeout(() => { promptSaved.value = false }, 2000)
    emit('refresh')
  } catch (error) {
    console.error('Failed to save prompt:', error)
  } finally {
    saving.value = false
  }
}

async function saveAndRegenerate() {
  if (!promptDirty.value) return
  saving.value = true
  try {
    await api.updateCharacter(props.character.slug, { design_prompt: promptText.value.trim() })
    emit('refresh')
    emit('generate-more', props.character)
  } catch (error) {
    console.error('Failed to save and regenerate:', error)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.panel-overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: flex-end;
}
.panel-slide {
  width: 520px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-primary);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: slideIn 200ms ease;
}
@keyframes slideIn {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-primary);
}
.panel-section {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-primary);
}
.prompt-textarea {
  width: 100%;
  padding: 10px 12px;
  font-size: 13px;
  font-family: var(--font-primary);
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  resize: vertical;
  line-height: 1.5;
}
.prompt-textarea:focus {
  border-color: var(--accent-primary);
  outline: none;
}
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 8px;
}
.gallery-image {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid var(--border-primary);
  cursor: pointer;
  transition: border-color 150ms ease;
}
.gallery-image:hover {
  border-color: var(--accent-primary);
}
.btn-primary {
  background: var(--accent-primary);
  color: #fff;
  border-color: var(--accent-primary);
}
</style>
