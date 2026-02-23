<template>
  <!-- Reassign character modal -->
  <div v-if="image" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); z-index: 998; display: flex; align-items: center; justify-content: center;" @click.self="$emit('close')" @keydown.escape.window="$emit('close')">
    <div class="card" style="min-width: 400px; max-width: 500px;">
      <h4 style="font-size: 14px; font-weight: 500; margin-bottom: 8px;">
        Reassign Image
      </h4>
      <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 12px;">
        Move <strong>{{ image.name }}</strong> from <strong>{{ image.character_name }}</strong> to:
      </p>

      <!-- Mode toggle -->
      <div style="display: flex; gap: 0; margin-bottom: 12px; border: 1px solid var(--border-primary); border-radius: 3px; overflow: hidden;">
        <button
          :style="{
            flex: 1, padding: '6px 12px', fontSize: '12px', border: 'none', cursor: 'pointer',
            fontFamily: 'var(--font-primary)',
            background: mode === 'existing' ? 'var(--accent-primary)' : 'var(--bg-primary)',
            color: mode === 'existing' ? 'var(--bg-primary)' : 'var(--text-secondary)',
          }"
          @click="mode = 'existing'"
        >Existing Character</button>
        <button
          :style="{
            flex: 1, padding: '6px 12px', fontSize: '12px', border: 'none', cursor: 'pointer',
            fontFamily: 'var(--font-primary)',
            borderLeft: '1px solid var(--border-primary)',
            background: mode === 'new' ? 'var(--accent-primary)' : 'var(--bg-primary)',
            color: mode === 'new' ? 'var(--bg-primary)' : 'var(--text-secondary)',
          }"
          @click="mode = 'new'"
        >New Character</button>
      </div>

      <!-- Existing character dropdown -->
      <div v-if="mode === 'existing'">
        <select
          v-model="targetSlug"
          style="width: 100%; padding: 8px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; font-family: var(--font-primary);"
        >
          <option value="" disabled>Select character...</option>
          <option
            v-for="char in targets"
            :key="char.slug"
            :value="char.slug"
          >{{ char.name }} ({{ char.project_name }})</option>
        </select>
      </div>

      <!-- New character form -->
      <div v-else>
        <input
          v-model="newName"
          type="text"
          placeholder="Character name (e.g. Donkey Kong)"
          style="width: 100%; padding: 8px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; font-family: var(--font-primary); margin-bottom: 8px; box-sizing: border-box;"
        />
        <textarea
          v-model="newDesignPrompt"
          placeholder="Design prompt (optional — describe appearance for generation)"
          style="width: 100%; min-height: 60px; padding: 8px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; font-family: var(--font-primary); resize: vertical; box-sizing: border-box;"
        ></textarea>
        <p style="font-size: 10px; color: var(--text-muted); margin-top: 4px;">
          Project: <strong>{{ image.project_name }}</strong>
        </p>
      </div>

      <div style="display: flex; gap: 8px; margin-top: 12px;">
        <button
          class="btn"
          style="flex: 1; background: var(--accent-primary); color: var(--bg-primary);"
          :disabled="!canSubmit || submitting"
          @click="submit"
        >
          {{ submitting ? 'Moving...' : mode === 'new' ? 'Create & Reassign' : 'Reassign' }}
        </button>
        <button class="btn" @click="$emit('close')">Cancel</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { PendingImage } from '@/types'

interface ReassignTarget {
  slug: string
  name: string
  project_name: string
}

const props = defineProps<{
  image: PendingImage | null
  targets: ReassignTarget[]
  submitting: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'submit', image: PendingImage, targetSlug: string): void
  (e: 'create-submit', image: PendingImage, name: string, designPrompt: string): void
}>()

const mode = ref<'existing' | 'new'>('existing')
const targetSlug = ref('')
const newName = ref('')
const newDesignPrompt = ref('')

const canSubmit = computed(() => {
  if (mode.value === 'existing') return !!targetSlug.value
  return newName.value.trim().length > 0
})

// Reset state when modal opens with a new image
watch(() => props.image, () => {
  mode.value = 'existing'
  targetSlug.value = ''
  newName.value = ''
  newDesignPrompt.value = ''
})

function submit() {
  if (!props.image) return
  if (mode.value === 'existing') {
    if (!targetSlug.value) return
    emit('submit', props.image, targetSlug.value)
  } else {
    const name = newName.value.trim()
    if (!name) return
    emit('create-submit', props.image, name, newDesignPrompt.value.trim())
  }
}
</script>
