<template>
  <div
    class="character-card"
    :class="{ 'card-ready': characterStats.canTrain }"
    @click="$emit('open-detail', character)"
  >
    <!-- Hero image -->
    <div class="hero-area">
      <img
        v-if="heroImage"
        :src="heroImage"
        class="hero-img"
        loading="lazy"
        alt=""
      />
      <div v-else class="hero-placeholder">
        <span class="hero-letter">{{ character.name.charAt(0) }}</span>
      </div>

      <!-- Overlay badges -->
      <div class="hero-overlay">
        <span v-if="filterModel" class="hero-badge badge-model">
          {{ approvedImages.length }} {{ shortModelName }}
        </span>
        <span v-else-if="characterStats.canTrain" class="hero-badge badge-ready">Ready</span>
        <span v-else class="hero-badge badge-count">{{ characterStats.approved }}/{{ minTrainingImages }}</span>
      </div>
    </div>

    <!-- Card body -->
    <div class="card-body">
      <h3 class="char-name">{{ character.name }}</h3>

      <!-- Secondary thumbnails -->
      <div v-if="secondaryThumbs.length > 0" class="thumb-row">
        <img
          v-for="img in secondaryThumbs"
          :key="img"
          :src="img"
          class="thumb-secondary"
          loading="lazy"
          @click.stop
        />
        <span v-if="characterStats.approved > secondaryThumbs.length + 1" class="thumb-more">
          +{{ characterStats.approved - secondaryThumbs.length - 1 }}
        </span>
      </div>

      <!-- SSOT design prompt (click to edit) -->
      <div @click.stop>
        <DesignPromptEditor
          :character="character"
          :editing="editingSlug === character.slug"
          :edit-text="editPromptText"
          :saving="savingPrompt"
          @start-edit="$emit('start-edit', character)"
          @cancel="$emit('cancel-edit')"
          @save="$emit('save-prompt', { character, text: $event })"
          @save-regenerate="$emit('save-regenerate', { character, text: $event })"
        />
      </div>

      <!-- Approved progress -->
      <div class="progress-section">
        <div class="progress-labels">
          <span :style="{ color: characterStats.canTrain ? 'var(--status-success)' : 'var(--text-secondary)' }">
            {{ characterStats.approved }}/{{ minTrainingImages }} approved
          </span>
          <span v-if="characterStats.pending > 0" class="progress-pending">
            {{ characterStats.pending }} pending
          </span>
          <span v-else-if="!characterStats.canTrain" class="progress-need">
            Need {{ minTrainingImages - characterStats.approved }} more
          </span>
        </div>
        <div class="progress-track">
          <div
            class="progress-bar"
            :class="{ ready: characterStats.canTrain }"
            :style="{ width: `${Math.min(100, (characterStats.approved / minTrainingImages) * 100)}%` }"
          ></div>
        </div>
      </div>

      <!-- Action area -->
      <div class="action-row" @click.stop>
        <button
          v-if="!characterStats.canTrain"
          class="btn action-btn"
          @click="$emit('generate-more', character)"
          :disabled="generatingSlug === character.slug"
        >
          {{ generatingSlug === character.slug ? 'Queued...' : `Generate ${minTrainingImages - characterStats.approved} More` }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Character, DatasetImage } from '@/types'
import DesignPromptEditor from './DesignPromptEditor.vue'
import { api } from '@/api/client'

interface CharacterStats {
  total: number
  approved: number
  pending: number
  canTrain: boolean
}

const props = defineProps<{
  character: Character
  characterStats: CharacterStats
  minTrainingImages: number
  editingSlug: string | null
  editPromptText: string
  savingPrompt: boolean
  generatingSlug: string | null
  trainingLoading: boolean
  datasetImages?: DatasetImage[]
  filterModel?: string
}>()

defineEmits<{
  (e: 'start-edit', character: Character): void
  (e: 'cancel-edit'): void
  (e: 'save-prompt', payload: { character: Character; text: string }): void
  (e: 'save-regenerate', payload: { character: Character; text: string }): void
  (e: 'generate-more', character: Character): void
  (e: 'open-detail', character: Character): void
}>()

const approvedImages = computed(() => {
  const images = props.datasetImages || []
  let approved = images.filter(img => img.status === 'approved')
  if (props.filterModel) {
    approved = approved.filter(img => img.checkpoint_model === props.filterModel)
  }
  return approved
})

const shortModelName = computed(() => {
  if (!props.filterModel) return ''
  return props.filterModel.replace('.safetensors', '').replace(/_/g, ' ')
})

const heroImage = computed(() => {
  const first = approvedImages.value[0]
  return first ? api.imageUrl(props.character.slug, first.name) : ''
})

const secondaryThumbs = computed(() => {
  return approvedImages.value.slice(1, 5).map(img => api.imageUrl(props.character.slug, img.name))
})
</script>

<style scoped>
.character-card {
  background: var(--bg-secondary);
  border: 2px solid var(--border-primary);
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 150ms ease, box-shadow 150ms ease, transform 100ms ease;
}

.character-card:hover {
  border-color: var(--accent-primary);
  box-shadow: 0 4px 20px rgba(122, 162, 247, 0.15);
  transform: translateY(-2px);
}

.card-ready {
  border-color: var(--status-success);
}

/* Hero image area */
.hero-area {
  position: relative;
  width: 100%;
  aspect-ratio: 3 / 4;
  overflow: hidden;
  background: var(--bg-tertiary);
}

.hero-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.hero-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
}

.hero-letter {
  font-size: 64px;
  font-weight: 700;
  color: var(--text-muted);
  opacity: 0.4;
  text-transform: uppercase;
}

.hero-overlay {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  gap: 6px;
}

.hero-badge {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  backdrop-filter: blur(8px);
}

.badge-ready {
  background: rgba(80, 160, 80, 0.85);
  color: #fff;
}

.badge-count {
  background: rgba(0, 0, 0, 0.6);
  color: var(--text-primary);
}

.badge-model {
  background: rgba(160, 120, 80, 0.85);
  color: #fff;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Card body */
.card-body {
  padding: 14px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.char-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.3;
}

/* Secondary thumbnail row */
.thumb-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.thumb-secondary {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--border-primary);
}

.thumb-more {
  font-size: 11px;
  color: var(--text-muted);
  padding: 0 4px;
  white-space: nowrap;
}

/* Progress */
.progress-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.progress-labels {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.progress-pending {
  color: var(--text-muted);
}

.progress-need {
  color: var(--status-error);
  font-size: 11px;
}

.progress-track {
  height: 6px;
  background: var(--bg-primary);
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--accent-primary);
  border-radius: 3px;
  transition: width 300ms ease;
}

.progress-bar.ready {
  background: var(--status-success);
}

/* Actions */
.action-row {
  display: flex;
  gap: 6px;
}

.action-btn {
  flex: 1;
  font-size: 12px;
}
</style>
