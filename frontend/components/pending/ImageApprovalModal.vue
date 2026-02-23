<template>
  <!-- Inline prompt editor overlay -->
  <div v-if="image" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); z-index: 998; display: flex; align-items: center; justify-content: center;" @click.self="$emit('close')" @keydown.escape.window="$emit('close')">
    <div class="card" style="min-width: 700px; max-width: 850px;">
      <h4 style="font-size: 14px; font-weight: 500; margin-bottom: 8px;">
        {{ action === 'approve' ? 'Approve' : 'Reject' }} — {{ image.character_name }}
      </h4>

      <div style="display: flex; gap: 16px;">
        <!-- Left: image preview -->
        <div style="flex-shrink: 0;">
          <img
            :src="imageSrc"
            :alt="image.name"
            style="width: 200px; height: 200px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border-primary);"
          />
          <div style="font-size: 10px; color: var(--text-muted); margin-top: 4px; max-width: 200px; word-break: break-all;">
            {{ image.name }}
          </div>
        </div>

        <!-- Right: editing controls -->
        <div style="flex: 1; min-width: 0;">
          <label style="font-size: 11px; font-weight: 500; color: var(--accent-primary); display: block; margin-bottom: 4px;">
            {{ action === 'reject' ? 'Design Prompt — edit this to fix what the model generates next' : 'Design Prompt — edit to refine the training caption' }}
          </label>
          <p v-if="action === 'reject'" style="font-size: 10px; color: var(--text-muted); margin-bottom: 6px;">
            This is the prompt that controls ALL future image generation for this character. Change it here to fix the output.
          </p>
          <textarea
            ref="editPromptEl"
            v-model="promptText"
            @keydown.ctrl.enter="submitEdited"
            @keydown.meta.enter="submitEdited"
            style="width: 100%; min-height: 80px; font-size: 12px; padding: 8px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; resize: vertical; font-family: var(--font-primary); line-height: 1.5;"
            :style="promptEdited ? 'border-color: var(--accent-primary); box-shadow: 0 0 4px rgba(80,120,200,0.3);' : action === 'reject' ? 'border-color: var(--danger);' : ''"
          ></textarea>
          <div style="display: flex; justify-content: space-between; margin-top: 2px;">
            <span style="font-size: 10px;" :style="{ color: promptEdited ? 'var(--accent-primary)' : 'var(--text-muted)' }">{{ promptText.length }} chars{{ promptEdited ? ' (edited)' : '' }}</span>
            <span style="font-size: 10px; color: var(--text-muted);">Ctrl+Enter to submit</span>
          </div>

          <!-- Structured rejection reasons (only show on reject) -->
          <div v-if="action === 'reject'" style="margin-top: 10px;">
            <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 6px;">
              What's wrong? (adds to negative prompt for regeneration)
            </label>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
              <button
                v-for="reason in rejectionReasons"
                :key="reason.id"
                :class="['rejection-chip', { active: selectedReasons.has(reason.id) }]"
                @click="toggleReason(reason.id)"
              >
                {{ reason.label }}
              </button>
            </div>
          </div>

          <div style="margin-top: 8px;">
            <label style="font-size: 11px; color: var(--text-muted);">Additional notes (optional):</label>
            <input
              v-model="feedbackText"
              type="text"
              :placeholder="action === 'reject' ? 'e.g., wrong hair color, needs more detail' : 'e.g., good pose, accurate colors'"
              style="width: 100%; padding: 6px 8px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; margin-top: 4px;"
            />
          </div>
        </div>
      </div>

      <div style="display: flex; gap: 8px; margin-top: 14px;">
        <button
          :class="action === 'approve' ? 'btn btn-success' : 'btn btn-danger'"
          :style="{ flex: '1', opacity: promptEdited ? 1 : 0.5 }"
          @click="submitEdited"
        >
          {{ action === 'approve' ? 'Approve' : 'Reject' }} &amp; Update Prompt
        </button>
        <button
          :class="action === 'approve' ? 'btn btn-success' : 'btn btn-danger'"
          :style="{ flex: '1', opacity: promptEdited ? 0.5 : 1 }"
          @click="submitQuick"
        >
          {{ action === 'approve' ? 'Approve' : 'Reject' }} (keep prompt)
        </button>
        <button class="btn" @click="$emit('close')">Cancel</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { PendingImage } from '@/types'
import { api } from '@/api/client'
import { useApprovalStore } from '@/stores/approval'

const approvalStore = useApprovalStore()

const props = defineProps<{
  image: PendingImage | null
  action: 'approve' | 'reject'
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'submit-edited', image: PendingImage, approved: boolean, feedback: string, editedPrompt: string): void
  (e: 'submit-quick', image: PendingImage, approved: boolean, feedback: string): void
}>()

const imageSrc = computed(() => {
  if (!props.image) return ''
  return api.imageUrl(props.image.character_slug || props.image.character_name, props.image.name)
})

const promptText = ref('')
const originalPrompt = ref('')
const feedbackText = ref('')
const selectedReasons = ref<Set<string>>(new Set())

const promptEdited = computed(() => promptText.value !== originalPrompt.value)

// Structured rejection reason categories (IDs match backend REJECTION_NEGATIVE_MAP)
const rejectionReasons = [
  { id: 'wrong_appearance', label: 'Wrong Appearance' },
  { id: 'wrong_style', label: 'Wrong Style' },
  { id: 'bad_quality', label: 'Bad Quality' },
  { id: 'not_solo', label: 'Not Solo' },
  { id: 'wrong_pose', label: 'Wrong Pose' },
  { id: 'wrong_expression', label: 'Wrong Expression' },
]

// Reset state when a new image/action is set
watch(() => [props.image, props.action], () => {
  if (props.image) {
    // design_prompt comes from character_designs map (no longer on each image)
    const designPrompt = approvalStore.characterDesigns[props.image.character_slug] || ''
    const initial = designPrompt || props.image.prompt || ''
    promptText.value = initial
    originalPrompt.value = initial
    feedbackText.value = ''
    selectedReasons.value = props.action === 'reject' ? new Set(['wrong_appearance']) : new Set()
  }
}, { immediate: true })

function toggleReason(id: string) {
  if (selectedReasons.value.has(id)) {
    selectedReasons.value.delete(id)
  } else {
    selectedReasons.value.add(id)
  }
  selectedReasons.value = new Set(selectedReasons.value)
}

function buildFeedbackString(): string {
  const parts: string[] = [...selectedReasons.value]
  if (feedbackText.value.trim()) {
    parts.push(feedbackText.value.trim())
  }
  return parts.length > 0 ? parts.join('|') : ''
}

function submitEdited() {
  if (!props.image) return
  emit('submit-edited', props.image, props.action === 'approve', buildFeedbackString(), promptText.value)
}

function submitQuick() {
  if (!props.image) return
  emit('submit-quick', props.image, props.action === 'approve', buildFeedbackString())
}
</script>

<style scoped>
.rejection-chip {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 12px;
  border: 1px solid var(--border-primary);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  font-family: var(--font-primary);
  transition: all 150ms ease;
}
.rejection-chip:hover {
  border-color: var(--status-error);
  color: var(--status-error);
}
.rejection-chip.active {
  background: rgba(160, 80, 80, 0.2);
  border-color: var(--status-error);
  color: var(--status-error);
  font-weight: 500;
}
</style>
