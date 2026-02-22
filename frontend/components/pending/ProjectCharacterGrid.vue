<template>
  <div v-for="(projectGroup, projectName) in groups" :key="projectName" style="margin-bottom: 36px;">
    <!-- Project header -->
    <div style="margin-bottom: 16px; padding-bottom: 10px; border-bottom: 2px solid var(--accent-primary);">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div style="display: flex; align-items: center; gap: 12px;">
          <h3 style="font-size: 17px; font-weight: 600;">{{ projectName }}</h3>
          <span class="badge badge-pending">{{ projectGroup.total }} pending</span>
          <span v-if="projectGroup.checkpoint" class="context-tag model-tag">
            {{ projectGroup.checkpoint.replace('.safetensors', '') }}
          </span>
          <span v-if="projectGroup.style" class="context-tag style-tag">
            {{ projectGroup.style }}
          </span>
        </div>
        <div style="display: flex; gap: 8px;">
          <button class="btn" style="font-size: 12px; padding: 4px 10px;" @click="$emit('select-all-project', projectGroup)">
            Select All
          </button>
          <button
            class="btn vision-btn"
            :class="{ 'vision-active': visionReviewing === `project:${projectName}` }"
            style="font-size: 12px; padding: 4px 10px;"
            @click.stop="$emit('vision-review-project', projectName as string, projectGroup)"
            :disabled="!!visionReviewing"
          >
            <span v-if="visionReviewing === `project:${projectName}`" class="spinner" style="width: 10px; height: 10px; display: inline-block; vertical-align: middle; margin-right: 4px; border-width: 2px;"></span>
            {{ visionReviewing === `project:${projectName}` ? 'Analyzing...' : 'Vision Review All' }}
          </button>
          <button class="btn btn-success" style="font-size: 12px; padding: 4px 10px;" @click="$emit('approve-all-project', projectName as string, projectGroup)">
            Approve All
          </button>
        </div>
      </div>
    </div>

    <!-- Character subgroups within this project -->
    <div v-for="(charImages, charName) in projectGroup.characters" :key="charName" style="margin-bottom: 24px; margin-left: 12px;">
      <!-- Character header with context -->
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid var(--border-primary);">
        <div style="display: flex; align-items: center; gap: 10px;">
          <h4 style="font-size: 15px; font-weight: 500;">{{ charName }}</h4>
          <span class="badge badge-pending" style="font-size: 11px;">{{ props.fullCounts[charName as string] || charImages.length }} pending</span>
        </div>
        <div style="display: flex; gap: 6px;">
          <button class="btn" style="font-size: 11px; padding: 3px 8px;" @click="$emit('select-all', charImages)">
            Select
          </button>
          <button
            class="btn vision-btn"
            :class="{ 'vision-active': visionReviewing === charName }"
            style="font-size: 11px; padding: 3px 8px;"
            @click.stop="$emit('vision-review', charName as string, charImages)"
            :disabled="!!visionReviewing"
          >
            <span v-if="visionReviewing === charName" class="spinner" style="width: 10px; height: 10px; display: inline-block; vertical-align: middle; margin-right: 4px; border-width: 2px;"></span>
            {{ visionReviewing === charName ? 'Analyzing...' : 'Vision Review' }}
          </button>
          <button class="btn btn-success" style="font-size: 11px; padding: 3px 8px;" @click="$emit('approve-group', charName as string, charImages)">
            Approve All
          </button>
        </div>
      </div>

      <!-- Image grid -->
      <TransitionGroup name="card" tag="div" class="image-grid">
        <ImageCard
          v-for="image in charImages"
          :key="image.id"
          :image="image"
          :is-selected="selectedImages.has(image.id)"
          :is-expanded="expandedImage === image.id"
          :flash-type="flashState[image.id] || null"
          :action-disabled="actionDisabled || !!processingImages?.has(image.id)"
          @toggle-expand="$emit('toggle-expand', $event)"
          @toggle-selection="$emit('toggle-selection', $event)"
          @preview="$emit('preview', $event)"
          @open-detail="$emit('open-detail', $event)"
          @approve="$emit('approve', $event)"
          @reject="$emit('reject', $event)"
          @reassign="$emit('reassign', $event)"
          @copy-seed="$emit('copy-seed', $event)"
        />
      </TransitionGroup>

      <!-- Show All / Show Less toggle -->
      <div
        v-if="(props.fullCounts[charName as string] || 0) > charImages.length || props.expandedCharacters.has(charName as string)"
        style="text-align: center; margin-top: 8px;"
      >
        <button
          class="btn"
          style="font-size: 11px; padding: 4px 16px;"
          @click="$emit('toggle-char-expand', charName as string)"
        >
          {{ props.expandedCharacters.has(charName as string)
            ? `Show Less`
            : `Show All ${props.fullCounts[charName as string]} images` }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { PendingImage } from '@/types'
import ImageCard from '@/components/pending/ImageCard.vue'

interface CharacterGroup {
  [characterName: string]: PendingImage[]
}

interface ProjectGroup {
  characters: CharacterGroup
  total: number
  checkpoint: string
  style: string
}

const props = defineProps<{
  groups: Record<string, ProjectGroup>
  fullCounts: Record<string, number>
  expandedCharacters: Set<string>
  selectedImages: Set<string>
  expandedImage: string | null
  flashState: Record<string, 'approve' | 'reject' | null>
  visionReviewing: string | null
  actionDisabled: boolean
  processingImages?: Set<string>
}>()

defineEmits<{
  (e: 'select-all-project', projectGroup: ProjectGroup): void
  (e: 'vision-review-project', projectName: string, projectGroup: ProjectGroup): void
  (e: 'approve-all-project', projectName: string, projectGroup: ProjectGroup): void
  (e: 'select-all', images: PendingImage[]): void
  (e: 'vision-review', charName: string, images: PendingImage[]): void
  (e: 'approve-group', charName: string, images: PendingImage[]): void
  (e: 'toggle-expand', image: PendingImage): void
  (e: 'toggle-selection', image: PendingImage): void
  (e: 'preview', image: PendingImage): void
  (e: 'open-detail', image: PendingImage): void
  (e: 'approve', image: PendingImage): void
  (e: 'reject', image: PendingImage): void
  (e: 'reassign', image: PendingImage): void
  (e: 'copy-seed', seed: number): void
  (e: 'toggle-char-expand', charName: string): void
}>()
</script>

<style scoped>
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.card-enter-active { transition: opacity 300ms ease, transform 300ms ease; }
.card-leave-active { transition: opacity 200ms ease; }
.card-enter-from { opacity: 0; transform: scale(0.95); }
.card-leave-to { opacity: 0; }

/* Context tags for project headers */
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
.model-tag {
  background: rgba(160, 120, 80, 0.12);
  color: var(--status-warning);
  border-color: var(--status-warning);
}
.style-tag {
  background: rgba(120, 80, 160, 0.12);
  color: #b080d0;
  border-color: #b080d0;
}

.vision-btn {
  color: var(--accent-primary);
  transition: all 200ms ease;
}
.vision-btn:hover:not(:disabled) {
  background: rgba(80, 120, 200, 0.15);
  border-color: var(--accent-primary);
}
.vision-active {
  background: rgba(80, 120, 200, 0.12) !important;
  border-color: var(--accent-primary) !important;
  animation: vision-pulse 1.5s ease-in-out infinite;
}
@keyframes vision-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
</style>
