<template>
  <div
    class="image-card"
    :class="{
      selected: isSelected,
      expanded: isExpanded,
      'flash-approve': flashType === 'approve',
      'flash-reject': flashType === 'reject',
      'vision-reviewed': !!image.metadata?.vision_review,
    }"
    @click="$emit('toggle-expand', image)"
  >
    <!-- Selection checkbox -->
    <div class="select-check" @click.stop="$emit('toggle-selection', image)">
      <input type="checkbox" :checked="isSelected" />
    </div>

    <img
      :src="imageSrc"
      :alt="image.name"
      loading="lazy"
      @error="onImageError($event)"
      @click.stop="$emit('preview', image)"
      @dblclick.stop="$emit('open-detail', image)"
      style="cursor: zoom-in;"
    />

    <div class="meta">
      <!-- Context badges: always visible -->
      <div style="display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 6px;">
        <span class="context-tag char-tag">{{ image.character_name }}</span>
        <span :class="['context-tag', `source-tag-${image.source || 'generated'}`]">
          {{ sourceLabel(image.source) }}
        </span>
        <span v-if="isRecent" class="new-badge" style="font-size: 9px; padding: 0 5px;">NEW</span>
        <span v-if="image.checkpoint_model" class="context-tag model-tag">
          {{ image.checkpoint_model.replace('.safetensors', '') }}
        </span>
        <span v-if="image.metadata?.seed" class="seed-badge" @click.stop="$emit('copy-seed', image.metadata.seed)" title="Copy seed">
          {{ image.metadata.seed }}
        </span>
        <span v-if="image.metadata?.quality_score != null" class="context-tag" :style="{ color: qualityColor(image.metadata.quality_score), borderColor: qualityColor(image.metadata.quality_score) }">
          Q:{{ (image.metadata.quality_score * 100).toFixed(0) }}%
        </span>
      </div>

      <!-- Vision review inline indicators -->
      <div v-if="image.metadata?.vision_review" style="display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 4px;">
        <span class="context-tag" :style="{ color: image.metadata.vision_review.solo ? 'var(--status-success)' : 'var(--status-error)', borderColor: image.metadata.vision_review.solo ? 'var(--status-success)' : 'var(--status-error)' }">
          {{ image.metadata.vision_review.solo ? 'Solo' : 'Multi' }}
        </span>
        <span class="context-tag" style="color: var(--text-muted); border-color: var(--border-primary);">
          {{ image.metadata.vision_review.completeness }}
        </span>
        <span v-for="issue in (image.metadata.vision_review.issues || []).slice(0, 2)" :key="issue" class="context-tag" style="color: var(--status-warning); border-color: var(--status-warning);">
          {{ issue.length > 30 ? issue.slice(0, 27) + '...' : issue }}
        </span>
      </div>

      <!-- Expanded details -->
      <div v-if="isExpanded" style="margin-bottom: 8px;">
        <div v-if="image.metadata?.pose" style="font-size: 11px; color: var(--text-muted); margin-bottom: 2px;">
          Pose: {{ image.metadata.pose }}
        </div>
        <div style="font-size: 11px; color: var(--text-secondary); line-height: 1.4; padding: 4px 6px; background: var(--bg-primary); border-radius: 2px; max-height: 60px; overflow-y: auto;">
          {{ approvalStore.characterDesigns[image.character_slug] || image.prompt || 'No prompt' }}
        </div>
      </div>

      <!-- Action buttons -->
      <div style="display: flex; gap: 4px;">
        <button
          class="btn btn-success"
          style="flex: 1; font-size: 12px; padding: 4px 8px;"
          @click.stop="$emit('approve', image)"
          :disabled="actionDisabled"
        >
          Approve
        </button>
        <button
          class="btn btn-danger"
          style="flex: 1; font-size: 12px; padding: 4px 8px;"
          @click.stop="$emit('reject', image)"
          :disabled="actionDisabled"
        >
          Reject
        </button>
        <button
          class="btn"
          style="font-size: 11px; padding: 4px 6px; white-space: nowrap;"
          title="Reassign to different character"
          @click.stop="$emit('reassign', image)"
          :disabled="actionDisabled"
        >
          &#8644;
        </button>
        <button
          class="btn"
          style="font-size: 11px; padding: 4px 6px; white-space: nowrap;"
          @click.stop="$emit('open-detail', image)"
          title="Full details + regeneration controls"
        >
          More
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PendingImage } from '@/types'
import { api } from '@/api/client'
import { useApprovalStore } from '@/stores/approval'

const approvalStore = useApprovalStore()

const RECENT_THRESHOLD_MS = 60 * 60 * 1000 // 1 hour

const props = defineProps<{
  image: PendingImage
  isSelected: boolean
  isExpanded: boolean
  flashType: 'approve' | 'reject' | null
  actionDisabled: boolean
}>()

defineEmits<{
  (e: 'toggle-expand', image: PendingImage): void
  (e: 'toggle-selection', image: PendingImage): void
  (e: 'preview', image: PendingImage): void
  (e: 'open-detail', image: PendingImage): void
  (e: 'approve', image: PendingImage): void
  (e: 'reject', image: PendingImage): void
  (e: 'reassign', image: PendingImage): void
  (e: 'copy-seed', seed: number): void
}>()

const imageSrc = computed(() => {
  return api.imageUrl(props.image.character_slug, props.image.name)
})

const isRecent = computed(() => {
  if (!props.image.created_at) return false
  const created = new Date(props.image.created_at).getTime()
  return (Date.now() - created) < RECENT_THRESHOLD_MS
})

function sourceLabel(source?: string): string {
  const labels: Record<string, string> = { youtube: 'YT', generated: 'Gen', upload: 'Upload', reference: 'Ref', unclassified: 'Unknown', youtube_project: 'YT', video_upload: 'Video' }
  return labels[source || 'generated'] || source || 'Gen'
}

function qualityColor(score: number): string {
  if (score >= 0.7) return 'var(--status-success)'
  if (score >= 0.4) return 'var(--status-warning)'
  return 'var(--status-error)'
}

function onImageError(event: Event) {
  const img = event.target as HTMLImageElement
  img.style.display = 'none'
}
</script>

<style scoped>
.image-card {
  position: relative;
  cursor: pointer;
  transition: all 200ms ease;
}

.image-card.expanded {
  border-color: var(--accent-primary) !important;
  box-shadow: 0 0 8px rgba(80, 120, 200, 0.25);
}

.image-card.flash-approve {
  border-color: var(--status-success) !important;
  box-shadow: 0 0 12px rgba(80, 160, 80, 0.4);
  transform: scale(0.97);
}
.image-card.flash-reject {
  border-color: var(--status-error) !important;
  box-shadow: 0 0 12px rgba(160, 80, 80, 0.4);
  transform: scale(0.97);
}

.select-check {
  position: absolute;
  top: 6px;
  left: 6px;
  z-index: 2;
  cursor: pointer;
}
.select-check input {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--accent-primary);
}

/* Context tags for project/character/model association */
.context-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 2px;
  border: 1px solid var(--border-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 150px;
}
.char-tag {
  background: rgba(80, 120, 200, 0.12);
  color: var(--accent-primary);
  border-color: var(--accent-primary);
  font-weight: 500;
}
.model-tag {
  background: rgba(160, 120, 80, 0.12);
  color: var(--status-warning);
  border-color: var(--status-warning);
}

.seed-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 2px;
  background: rgba(80, 120, 200, 0.15);
  color: var(--accent-primary);
  border: 1px solid var(--accent-primary);
  cursor: pointer;
  font-family: monospace;
  white-space: nowrap;
}
.seed-badge:hover {
  background: rgba(80, 120, 200, 0.3);
}

/* New badge */
.new-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 8px;
  background: rgba(80, 160, 80, 0.2);
  color: var(--status-success);
  border: 1px solid var(--status-success);
  font-weight: 600;
  animation: new-pulse 2s ease-in-out 3;
}
@keyframes new-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Source tags on image cards */
.source-tag-youtube { background: rgba(200, 50, 50, 0.12); color: #e04040; border-color: #e04040; }
.source-tag-upload { background: rgba(80, 160, 80, 0.12); color: var(--status-success); border-color: var(--status-success); }
.source-tag-generated { background: rgba(120, 120, 120, 0.12); color: var(--text-muted); border-color: var(--border-primary); }
.source-tag-reference { background: rgba(160, 120, 80, 0.12); color: var(--status-warning); border-color: var(--status-warning); }

.image-card.vision-reviewed {
  border-left: 3px solid var(--accent-primary);
}
</style>
