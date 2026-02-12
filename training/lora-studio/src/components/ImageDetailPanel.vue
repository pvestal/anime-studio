<template>
  <Teleport to="body">
    <Transition name="panel">
      <div v-if="image" class="panel-overlay" @click.self="$emit('close')">
        <div class="panel-content">
          <!-- Header -->
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <h3 style="font-size: 16px; font-weight: 500;">{{ image.character_name }} - {{ image.name }}</h3>
            <button class="btn" style="font-size: 14px; padding: 4px 10px;" @click="$emit('close')">Close</button>
          </div>

          <!-- Image preview -->
          <div style="text-align: center; margin-bottom: 16px; background: var(--bg-primary); border-radius: 4px; padding: 8px;">
            <img
              :src="imageUrl"
              :alt="image.name"
              style="max-width: 100%; max-height: 400px; border-radius: 3px;"
            />
          </div>

          <!-- Metadata section -->
          <div v-if="meta" style="margin-bottom: 16px;">
            <h4 style="font-size: 13px; font-weight: 500; margin-bottom: 8px; color: var(--text-secondary);">Generation Metadata</h4>
            <div class="meta-grid">
              <div class="meta-row">
                <span class="meta-label">Seed</span>
                <span class="meta-value" style="display: flex; align-items: center; gap: 6px;">
                  <template v-if="meta.seed">
                    <code style="cursor: pointer; color: var(--accent-primary);" @click="copySeed" :title="'Click to copy'">{{ meta.seed }}</code>
                    <span v-if="seedCopied" style="font-size: 10px; color: var(--status-success);">copied</span>
                  </template>
                  <span v-else style="color: var(--text-muted);">unknown</span>
                </span>
              </div>
              <div class="meta-row">
                <span class="meta-label">Model</span>
                <span class="meta-value">{{ meta.checkpoint_model || 'unknown' }}</span>
              </div>
              <div v-if="meta.cfg_scale" class="meta-row">
                <span class="meta-label">CFG</span>
                <span class="meta-value">{{ meta.cfg_scale }}</span>
              </div>
              <div v-if="meta.steps" class="meta-row">
                <span class="meta-label">Steps</span>
                <span class="meta-value">{{ meta.steps }}</span>
              </div>
              <div v-if="meta.sampler" class="meta-row">
                <span class="meta-label">Sampler</span>
                <span class="meta-value">{{ meta.sampler }} / {{ meta.scheduler || 'normal' }}</span>
              </div>
              <div v-if="meta.width" class="meta-row">
                <span class="meta-label">Size</span>
                <span class="meta-value">{{ meta.width }}x{{ meta.height }}</span>
              </div>
              <div v-if="meta.pose" class="meta-row">
                <span class="meta-label">Pose</span>
                <span class="meta-value">{{ meta.pose }}</span>
              </div>
              <div v-if="meta.source" class="meta-row">
                <span class="meta-label">Source</span>
                <span class="meta-value">{{ meta.source }}</span>
              </div>
              <div v-if="meta.quality_score != null" class="meta-row">
                <span class="meta-label">Quality</span>
                <span class="meta-value">
                  <span :style="{ color: qualityColor(meta.quality_score) }">{{ (meta.quality_score * 100).toFixed(0) }}%</span>
                </span>
              </div>
            </div>
          </div>

          <!-- Full prompt (expandable) -->
          <div style="margin-bottom: 16px;">
            <h4 style="font-size: 13px; font-weight: 500; margin-bottom: 6px; color: var(--text-secondary);">Full Prompt</h4>
            <div style="font-size: 11px; padding: 8px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 3px; line-height: 1.5; max-height: 120px; overflow-y: auto; color: var(--text-secondary);">
              {{ meta?.full_prompt || image.prompt || 'No prompt data' }}
            </div>
          </div>

          <!-- Editable prompt for regeneration -->
          <div style="margin-bottom: 16px;">
            <h4 style="font-size: 13px; font-weight: 500; margin-bottom: 6px; color: var(--text-secondary);">Regenerate Variant</h4>
            <textarea
              v-model="editablePrompt"
              style="width: 100%; min-height: 50px; font-size: 11px; padding: 6px 8px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; resize: vertical; font-family: var(--font-primary); line-height: 1.4;"
              placeholder="Edit prompt for regeneration..."
            ></textarea>
            <div style="display: flex; gap: 6px; margin-top: 6px; align-items: center;">
              <label style="font-size: 11px; color: var(--text-muted);">Seed:</label>
              <input
                v-model="editableSeed"
                type="number"
                style="width: 120px; font-size: 11px; padding: 3px 6px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
                placeholder="random"
              />
              <label style="font-size: 11px; color: var(--text-muted);">Count:</label>
              <input
                v-model.number="regenCount"
                type="number"
                min="1"
                max="10"
                style="width: 60px; font-size: 11px; padding: 3px 6px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
              />
              <button
                class="btn"
                style="font-size: 11px; padding: 4px 10px; color: var(--accent-primary);"
                @click="regenerateVariant"
                :disabled="regenerating"
              >
                {{ regenerating ? 'Queued...' : 'Regenerate Variant' }}
              </button>
            </div>
          </div>

          <!-- IPAdapter Refinement -->
          <div style="margin-bottom: 16px;">
            <h4 style="font-size: 13px; font-weight: 500; margin-bottom: 6px; color: var(--text-secondary);">IPAdapter Refinement</h4>
            <div style="display: flex; gap: 6px; align-items: center;">
              <label style="font-size: 11px; color: var(--text-muted);">Weight:</label>
              <input
                v-model.number="ipaWeight"
                type="number"
                min="0.1"
                max="1.5"
                step="0.1"
                style="width: 60px; font-size: 11px; padding: 3px 6px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
              />
              <label style="font-size: 11px; color: var(--text-muted);">Denoise:</label>
              <input
                v-model.number="ipaDenoise"
                type="number"
                min="0.1"
                max="1.0"
                step="0.05"
                style="width: 60px; font-size: 11px; padding: 3px 6px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
              />
              <button
                class="btn"
                style="font-size: 11px; padding: 4px 10px; color: var(--accent-primary);"
                @click="refineWithIPAdapter"
                :disabled="refining"
              >
                {{ refining ? 'Queued...' : 'Use as Reference' }}
              </button>
            </div>
          </div>

          <!-- Action buttons -->
          <div style="display: flex; gap: 8px; padding-top: 12px; border-top: 1px solid var(--border-primary);">
            <button class="btn btn-success" style="flex: 1;" @click="$emit('approve', image, true)" :disabled="actionDisabled">
              Approve
            </button>
            <button class="btn btn-danger" style="flex: 1;" @click="$emit('approve', image, false)" :disabled="actionDisabled">
              Reject
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api } from '@/api/client'
import type { PendingImage, ImageMetadata } from '@/types'

const props = defineProps<{
  image: PendingImage | null
  actionDisabled?: boolean
}>()

defineEmits<{
  close: []
  approve: [image: PendingImage, approved: boolean]
}>()

const meta = ref<ImageMetadata | null>(null)
const loading = ref(false)
const seedCopied = ref(false)
const editablePrompt = ref('')
const editableSeed = ref<string>('')
const regenCount = ref(3)
const regenerating = ref(false)
const ipaWeight = ref(0.8)
const ipaDenoise = ref(0.65)
const refining = ref(false)

const imageUrl = computed(() => {
  if (!props.image) return ''
  return api.imageUrl(props.image.character_slug, props.image.name)
})

watch(() => props.image, async (img) => {
  if (!img) {
    meta.value = null
    return
  }
  // Use inline metadata if available, otherwise fetch
  if (img.metadata) {
    meta.value = img.metadata
  } else {
    loading.value = true
    try {
      meta.value = await api.getImageMetadata(img.character_slug, img.name)
    } catch {
      meta.value = null
    } finally {
      loading.value = false
    }
  }
  // Pre-fill editable fields
  editablePrompt.value = meta.value?.design_prompt || img.design_prompt || ''
  editableSeed.value = meta.value?.seed ? String(meta.value.seed) : ''
}, { immediate: true })

function copySeed() {
  if (meta.value?.seed) {
    navigator.clipboard.writeText(String(meta.value.seed))
    seedCopied.value = true
    setTimeout(() => { seedCopied.value = false }, 1500)
  }
}

function qualityColor(score: number): string {
  if (score >= 0.7) return 'var(--status-success)'
  if (score >= 0.4) return 'var(--status-warning)'
  return 'var(--status-error)'
}

async function refineWithIPAdapter() {
  if (!props.image) return
  refining.value = true
  try {
    await api.refineImage({
      character_slug: props.image.character_slug,
      reference_image: props.image.name,
      prompt_override: editablePrompt.value.trim() || undefined,
      count: regenCount.value,
      weight: ipaWeight.value,
      denoise: ipaDenoise.value,
    })
  } catch (error) {
    console.error('Failed to refine:', error)
  } finally {
    setTimeout(() => { refining.value = false }, 2000)
  }
}

async function regenerateVariant() {
  if (!props.image) return
  regenerating.value = true
  try {
    await api.regenerateCustom({
      slug: props.image.character_slug,
      count: regenCount.value,
      seed: editableSeed.value ? parseInt(editableSeed.value) : undefined,
      prompt_override: editablePrompt.value.trim() || undefined,
    })
  } catch (error) {
    console.error('Failed to regenerate:', error)
  } finally {
    setTimeout(() => { regenerating.value = false }, 2000)
  }
}
</script>

<style scoped>
.panel-overlay {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}

.panel-content {
  width: 480px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-primary);
  padding: 20px;
  overflow-y: auto;
}

.panel-enter-active,
.panel-leave-active {
  transition: all 200ms ease;
}
.panel-enter-from .panel-content,
.panel-leave-to .panel-content {
  transform: translateX(100%);
}
.panel-enter-from,
.panel-leave-to {
  opacity: 0;
}

.meta-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.meta-row {
  display: flex;
  justify-content: space-between;
  padding: 3px 8px;
  font-size: 12px;
  background: var(--bg-primary);
  border-radius: 2px;
}

.meta-label {
  color: var(--text-muted);
  min-width: 80px;
}

.meta-value {
  color: var(--text-secondary);
  text-align: right;
}
</style>
