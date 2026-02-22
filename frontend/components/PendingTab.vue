<template>
  <div>
    <!-- Toast notifications -->
    <div style="position: fixed; top: 16px; right: 16px; z-index: 1000; display: flex; flex-direction: column; gap: 8px;">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          :style="{
            padding: '10px 16px',
            borderRadius: '4px',
            fontSize: '13px',
            fontFamily: 'var(--font-primary)',
            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
            border: '1px solid',
            minWidth: '280px',
            background: toast.type === 'approve' ? 'rgba(80,160,80,0.15)' : toast.type === 'regen' ? 'rgba(80,120,200,0.15)' : 'rgba(160,80,80,0.15)',
            borderColor: toast.type === 'approve' ? 'var(--status-success)' : toast.type === 'regen' ? 'var(--accent-primary)' : 'var(--status-error)',
            color: toast.type === 'approve' ? 'var(--status-success)' : toast.type === 'regen' ? 'var(--accent-primary)' : 'var(--status-error)',
          }"
        >
          {{ toast.message }}
        </div>
      </TransitionGroup>
    </div>

    <!-- Batch progress overlay -->
    <div v-if="batchProgress" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); z-index: 999; display: flex; align-items: center; justify-content: center;">
      <div class="card" style="text-align: center; min-width: 300px;">
        <div class="spinner" style="width: 32px; height: 32px; margin: 0 auto 12px;"></div>
        <p style="color: var(--text-primary); margin-bottom: 4px;">{{ batchProgress.action }}</p>
        <p style="color: var(--text-muted); font-size: 13px;">{{ batchProgress.done }}/{{ batchProgress.total }}</p>
        <div class="progress-track" style="margin-top: 12px;">
          <div class="progress-bar" :style="{ width: `${(batchProgress.done / batchProgress.total) * 100}%` }"></div>
        </div>
      </div>
    </div>

    <!-- Approval modal -->
    <ImageApprovalModal
      :image="editingImage"
      :action="editingAction"
      @close="editingImage = null"
      @submit-edited="onSubmitEdited"
      @submit-quick="onSubmitQuick"
    />

    <!-- Reassign modal -->
    <ImageReassignModal
      :image="reassigningImage"
      :targets="availableReassignTargets"
      :submitting="reassigning"
      @close="reassigningImage = null"
      @submit="submitReassign"
      @create-submit="createAndReassign"
    />

    <!-- Filters and batch actions -->
    <PendingFilters
      :total-count="modelFilteredImages.length"
      :recent-count="recentCount"
      :last-refreshed-ago="lastRefreshedAgo"
      :filter-project="approvalStore.filterProject"
      :filter-character="approvalStore.filterCharacter"
      :filter-source="filterSource"
      :filter-model="filterModel"
      :sort-by="sortBy"
      :project-names="approvalStore.projectNames"
      :character-names="approvalStore.characterNames"
      :source-names="sourceNames"
      :model-names="modelNames"
      :all-filtered-count="approvalStore.filteredImages.length"
      :selected-count="selectedImages.size"
      :loading="approvalStore.loading"
      :project-image-count="projectImageCount"
      :character-image-count="characterImageCount"
      @update:filter-project="onProjectFilterChange"
      @update:filter-character="approvalStore.filterCharacter = $event"
      @update:filter-source="filterSource = $event"
      @update:filter-model="filterModel = $event"
      @update:sort-by="sortBy = $event"
      @refresh="refresh()"
      @batch-approve="batchApprove"
    />

    <!-- Replenishment Panel (collapsible) -->
    <div class="card" style="margin-bottom: 16px;" v-if="replenishVisible">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <div style="display: flex; align-items: center; gap: 12px;">
          <h3 style="margin: 0; color: var(--text-primary); font-size: 14px;">Replenishment Loop</h3>
          <span
            :style="{
              fontSize: '11px',
              padding: '2px 8px',
              borderRadius: '4px',
              background: replenishStatus?.enabled ? 'rgba(80,160,80,0.15)' : 'rgba(160,80,80,0.1)',
              color: replenishStatus?.enabled ? 'var(--status-success)' : 'var(--text-muted)',
              border: '1px solid',
              borderColor: replenishStatus?.enabled ? 'var(--status-success)' : 'var(--border-primary)',
            }"
          >{{ replenishStatus?.enabled ? 'ACTIVE' : 'OFF' }}</span>
          <span v-if="activeGenCount > 0" style="font-size: 11px; color: var(--accent-primary);">
            {{ activeGenCount }} generating...
          </span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <label style="font-size: 12px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; cursor: pointer;">
            <input
              type="checkbox"
              :checked="replenishStatus?.enabled"
              @change="toggleReplenish"
              style="accent-color: var(--status-success);"
            />
            Enable
          </label>
          <button class="btn btn-sm" @click="replenishExpanded = !replenishExpanded" style="font-size: 11px; padding: 2px 8px;">
            {{ replenishExpanded ? 'Collapse' : 'Details' }}
          </button>
          <button class="btn btn-sm" @click="fetchReplenishData" style="font-size: 11px; padding: 2px 8px;">Refresh</button>
        </div>
      </div>

      <!-- Summary row -->
      <div v-if="readinessData" style="display: flex; gap: 16px; font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">
        <span>Target: <strong style="color: var(--text-primary);">{{ replenishStatus?.default_target || 20 }}</strong></span>
        <span>Ready: <strong style="color: var(--status-success);">{{ readinessData.ready }}</strong>/{{ readinessData.total }}</span>
        <span>Deficit: <strong :style="{ color: readinessData.deficit > 0 ? 'var(--status-warning, #e0a040)' : 'var(--status-success)' }">{{ readinessData.deficit }}</strong></span>
        <span v-if="Object.keys(replenishStatus?.daily_counts || {}).length > 0">
          Today: <strong style="color: var(--accent-primary);">{{ Object.values(replenishStatus?.daily_counts || {}).reduce((a, b) => a + b, 0) }}</strong> generated
        </span>
      </div>

      <!-- Expanded: Character readiness table -->
      <div v-if="replenishExpanded && readinessData">
        <table style="width: 100%; font-size: 12px; border-collapse: collapse;">
          <thead>
            <tr style="border-bottom: 1px solid var(--border-primary); color: var(--text-muted);">
              <th style="text-align: left; padding: 4px 8px;">Character</th>
              <th style="text-align: center; padding: 4px 8px;">Approved</th>
              <th style="text-align: center; padding: 4px 8px;">Pending</th>
              <th style="text-align: center; padding: 4px 8px;">Target</th>
              <th style="text-align: left; padding: 4px 8px; min-width: 120px;">Progress</th>
              <th style="text-align: center; padding: 4px 8px;">Status</th>
              <th style="text-align: center; padding: 4px 8px;">Today</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="char in readinessData.characters"
              :key="char.slug"
              style="border-bottom: 1px solid var(--border-secondary, rgba(255,255,255,0.05));"
            >
              <td style="padding: 4px 8px; color: var(--text-primary);">{{ char.name }}</td>
              <td style="text-align: center; padding: 4px 8px; color: var(--status-success);">{{ char.approved }}</td>
              <td style="text-align: center; padding: 4px 8px; color: var(--accent-primary);">{{ char.pending || '-' }}</td>
              <td style="text-align: center; padding: 4px 8px;">
                <input
                  type="number"
                  :value="char.target"
                  @change="updateCharTarget(char.slug, $event)"
                  style="width: 50px; text-align: center; background: var(--bg-secondary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; font-size: 12px; padding: 1px 4px;"
                  min="1"
                  max="100"
                />
              </td>
              <td style="padding: 4px 8px;">
                <div style="background: var(--bg-tertiary, rgba(255,255,255,0.05)); border-radius: 3px; height: 14px; overflow: hidden; position: relative;">
                  <div
                    :style="{
                      width: `${Math.min(100, (char.approved / char.target) * 100)}%`,
                      height: '100%',
                      background: char.ready ? 'var(--status-success)' : 'var(--accent-primary)',
                      borderRadius: '3px',
                      transition: 'width 0.3s ease',
                    }"
                  ></div>
                  <span style="position: absolute; top: 0; left: 0; right: 0; text-align: center; font-size: 10px; line-height: 14px; color: var(--text-primary);">
                    {{ Math.round((char.approved / char.target) * 100) }}%
                  </span>
                </div>
              </td>
              <td style="text-align: center; padding: 4px 8px;">
                <span v-if="char.active_generation" style="color: var(--accent-primary); font-size: 11px;">generating</span>
                <span v-else-if="char.ready" style="color: var(--status-success); font-size: 11px;">ready</span>
                <span v-else-if="char.consecutive_rejects >= 5" style="color: var(--status-error); font-size: 11px;">paused</span>
                <span v-else style="color: var(--text-muted); font-size: 11px;">{{ char.deficit }} needed</span>
              </td>
              <td style="text-align: center; padding: 4px 8px; color: var(--text-muted);">{{ char.daily_generated || '-' }}</td>
            </tr>
          </tbody>
        </table>

        <!-- Safety info -->
        <div v-if="replenishStatus" style="margin-top: 12px; display: flex; gap: 16px; font-size: 11px; color: var(--text-muted);">
          <span>Cooldown: {{ replenishStatus.cooldown_seconds }}s</span>
          <span>Max concurrent: {{ replenishStatus.max_concurrent }}</span>
          <span>Daily limit: {{ replenishStatus.max_daily_per_char }}/char</span>
          <span>Batch: {{ replenishStatus.batch_size }}/round</span>
          <span>Auto-stop after {{ replenishStatus.max_consecutive_rejects }} rejects</span>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="approvalStore.loading && !batchProgress" style="text-align: center; padding: 48px;">
      <div class="spinner" style="width: 32px; height: 32px; margin: 0 auto 16px;"></div>
      <p style="color: var(--text-muted);">Loading pending images...</p>
    </div>

    <!-- Error -->
    <div v-else-if="approvalStore.error" class="card" style="background: rgba(160,80,80,0.1); border-color: var(--status-error);">
      <p style="color: var(--status-error);">{{ approvalStore.error }}</p>
      <button class="btn" @click="approvalStore.clearError()" style="margin-top: 8px;">Dismiss</button>
    </div>

    <!-- Empty -->
    <div v-else-if="modelFilteredImages.length === 0 && !batchProgress" style="text-align: center; padding: 48px;">
      <p style="color: var(--text-muted); font-size: 16px;">No pending approvals</p>
      <p style="color: var(--text-muted); font-size: 13px;">All images have been reviewed.</p>
    </div>

    <!-- Hierarchical display: Project -> Character -> Images -->
    <ProjectCharacterGrid
      v-if="modelFilteredImages.length > 0 && !approvalStore.loading && !approvalStore.error"
      :groups="projectCharacterGroups"
      :full-counts="fullCharacterCounts"
      :expanded-characters="expandedCharacters"
      :selected-images="selectedImages"
      :expanded-image="expandedImage"
      :flash-state="flashState"
      :vision-reviewing="visionReviewing"
      :action-disabled="approvalStore.loading"
      :processing-images="processingImages"
      @select-all-project="selectAllProject"
      @vision-review-project="runVisionReviewProject"
      @approve-all-project="approveAllProject"
      @select-all="selectAll"
      @vision-review="runVisionReview"
      @approve-group="approveGroup"
      @toggle-expand="toggleExpand"
      @toggle-selection="toggleSelection"
      @preview="previewImage = $event"
      @open-detail="detailImage = $event"
      @approve="openApprovalEditor($event, 'approve')"
      @reject="openApprovalEditor($event, 'reject')"
      @reassign="openReassign"
      @copy-seed="copySeed"
      @toggle-char-expand="toggleCharacterExpand"
    />

    <!-- Image detail slide-over panel (double-click) -->
    <ImageDetailPanel
      :image="detailImage"
      :action-disabled="approvalStore.loading"
      @close="detailImage = null"
      @approve="onDetailApprove"
      @reassign="(img) => { detailImage = null; openReassign(img) }"
    />

    <!-- Lightbox preview (single click) -->
    <Teleport to="body">
      <Transition name="lightbox">
        <div v-if="previewImage" class="lightbox-overlay" @click="previewImage = null">
          <img
            :src="previewImageUrl"
            :alt="previewImage.name"
            class="lightbox-img"
            @click.stop
          />
          <div class="lightbox-info" @click.stop>
            <span class="lightbox-name">{{ previewImage.character_name }} — {{ previewImage.name }}</span>
            <div class="lightbox-actions">
              <button class="btn btn-success" style="font-size: 12px; padding: 4px 12px;" @click="doApprove(previewImage!, true); previewImage = null" :disabled="approvalStore.loading">Approve</button>
              <button class="btn btn-danger" style="font-size: 12px; padding: 4px 12px;" @click="openApprovalEditor(previewImage!, 'reject'); previewImage = null" :disabled="approvalStore.loading">Reject</button>
              <button class="btn" style="font-size: 12px; padding: 4px 12px;" @click="detailImage = previewImage; previewImage = null">Edit / Details</button>
            </div>
          </div>
          <button class="lightbox-close" @click="previewImage = null">&times;</button>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useApprovalStore } from '@/stores/approval'
import { useCharactersStore } from '@/stores/characters'
import { api } from '@/api/client'
import { learningApi } from '@/api/learning'
import type { PendingImage, ReplenishmentStatus, ReadinessResponse } from '@/types'
import ImageDetailPanel from '@/components/ImageDetailPanel.vue'
import ImageApprovalModal from '@/components/pending/ImageApprovalModal.vue'
import ImageReassignModal from '@/components/pending/ImageReassignModal.vue'
import PendingFilters from '@/components/pending/PendingFilters.vue'
import ProjectCharacterGrid from '@/components/pending/ProjectCharacterGrid.vue'
import { useVisionReview } from '@/components/pending/useVisionReview'

const MIN_TRAINING = 10
const RECENT_THRESHOLD_MS = 60 * 60 * 1000 // 1 hour
const approvalStore = useApprovalStore()
const charactersStore = useCharactersStore()
const filterModel = ref('')
const filterSource = ref('')
const sortBy = ref('newest')
const lastRefreshed = ref<Date | null>(null)
const lastRefreshedAgo = ref('')
const selectedImages = ref<Set<string>>(new Set())

// --- Replenishment Loop State ---
const replenishVisible = ref(true)
const replenishExpanded = ref(false)
const replenishStatus = ref<ReplenishmentStatus | null>(null)
const readinessData = ref<ReadinessResponse | null>(null)

const activeGenCount = computed(() => {
  if (!replenishStatus.value) return 0
  return Object.values(replenishStatus.value.active_generations).filter(Boolean).length
})

async function fetchReplenishData() {
  try {
    const [status, readiness] = await Promise.all([
      learningApi.getReplenishmentStatus(),
      learningApi.getCharacterReadiness(approvalStore.filterProject || undefined),
    ])
    replenishStatus.value = status
    readinessData.value = readiness
  } catch (e) {
    console.warn('Failed to fetch replenishment data:', e)
  }
}

async function toggleReplenish() {
  const newState = !replenishStatus.value?.enabled
  try {
    await learningApi.toggleReplenishment(newState)
    showToast(
      newState ? 'Replenishment loop enabled' : 'Replenishment loop disabled',
      newState ? 'approve' : 'reject'
    )
    await fetchReplenishData()
  } catch (e: any) {
    showToast(`Toggle failed: ${e.message}`, 'reject')
  }
}

async function updateCharTarget(slug: string, event: Event) {
  const target = parseInt((event.target as HTMLInputElement).value)
  if (isNaN(target) || target < 1) return
  try {
    await learningApi.setReplenishmentTarget(target, slug)
    await fetchReplenishData()
  } catch (e: any) {
    showToast(`Failed to set target: ${e.message}`, 'reject')
  }
}

// Auto-refresh on mount (every time user navigates to this tab)
onMounted(async () => {
  await refresh()
  await fetchReplenishData()
})

// Update "last refreshed" relative time every 10s + replenishment poll every 15s
let agoInterval: ReturnType<typeof setInterval> | null = null
let replenishInterval: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  agoInterval = setInterval(updateAgo, 10000)
  replenishInterval = setInterval(() => {
    if (activeGenCount.value > 0) fetchReplenishData()
  }, 15000)
})
onUnmounted(() => {
  if (agoInterval) clearInterval(agoInterval)
  if (replenishInterval) clearInterval(replenishInterval)
})

function updateAgo() {
  if (!lastRefreshed.value) { lastRefreshedAgo.value = ''; return }
  const secs = Math.floor((Date.now() - lastRefreshed.value.getTime()) / 1000)
  if (secs < 10) lastRefreshedAgo.value = 'just now'
  else if (secs < 60) lastRefreshedAgo.value = `${secs}s ago`
  else lastRefreshedAgo.value = `${Math.floor(secs / 60)}m ago`
}

async function refresh() {
  await approvalStore.fetchPendingImages()
  lastRefreshed.value = new Date()
  updateAgo()
}

function isRecent(image: PendingImage): boolean {
  if (!image.created_at) return false
  const created = new Date(image.created_at).getTime()
  return (Date.now() - created) < RECENT_THRESHOLD_MS
}

const recentCount = computed(() => {
  return approvalStore.filteredImages.filter(img => isRecent(img)).length
})

// Source filter names with counts
const sourceNames = computed(() => {
  const counts: Record<string, number> = {}
  for (const img of approvalStore.filteredImages) {
    const src = img.source || 'generated'
    counts[src] = (counts[src] || 0) + 1
  }
  const labels: Record<string, { label: string; cssClass: string }> = {
    youtube: { label: 'YouTube', cssClass: 'source-yt' },
    generated: { label: 'Generated', cssClass: 'source-gen' },
    upload: { label: 'Upload', cssClass: 'source-upload' },
    reference: { label: 'Reference', cssClass: 'source-ref' },
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => ({
      name,
      count,
      label: labels[name]?.label || name,
      cssClass: labels[name]?.cssClass || '',
    }))
})

const expandedImage = ref<string | null>(null)
const flashState = reactive<Record<string, 'approve' | 'reject' | null>>({})
const toasts = ref<{ id: number; message: string; type: 'approve' | 'reject' | 'regen' }[]>([])
const batchProgress = ref<{ action: string; done: number; total: number } | null>(null)
const detailImage = ref<PendingImage | null>(null)
const previewImage = ref<PendingImage | null>(null)

const previewImageUrl = computed(() => {
  if (!previewImage.value) return ''
  return api.imageUrl(previewImage.value.character_slug, previewImage.value.name)
})

// Inline editor state
const editingImage = ref<PendingImage | null>(null)
const editingAction = ref<'approve' | 'reject'>('approve')

// Reassign state
const reassigningImage = ref<PendingImage | null>(null)
const reassigning = ref(false)
const processingImages = ref<Set<string>>(new Set())

const availableReassignTargets = computed(() => {
  if (!reassigningImage.value) return []
  const currentSlug = reassigningImage.value.character_slug
  return charactersStore.characters
    .filter(c => c.slug !== currentSlug)
    .sort((a, b) => a.name.localeCompare(b.name))
})

let toastId = 0

interface CharacterGroup {
  [characterName: string]: PendingImage[]
}

interface ProjectGroup {
  characters: CharacterGroup
  total: number
  checkpoint: string
  style: string
}

// Unique checkpoint models with counts
const modelNames = computed(() => {
  const counts: Record<string, number> = {}
  for (const img of approvalStore.filteredImages) {
    const model = img.checkpoint_model || 'unknown'
    counts[model] = (counts[model] || 0) + 1
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => ({ name, count, short: name.replace('.safetensors', '') }))
})

// Images filtered by source + model (on top of store's project/character filter), then sorted
const modelFilteredImages = computed(() => {
  let base = approvalStore.filteredImages
  if (filterSource.value) {
    base = base.filter(img => (img.source || 'generated') === filterSource.value)
  }
  if (filterModel.value) {
    base = base.filter(img => (img.checkpoint_model || 'unknown') === filterModel.value)
  }
  // Apply sort
  const sorted = [...base]
  switch (sortBy.value) {
    case 'newest':
      sorted.sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())
      break
    case 'oldest':
      sorted.sort((a, b) => new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime())
      break
    case 'character':
      sorted.sort((a, b) => (a.character_name || '').localeCompare(b.character_name || ''))
      break
    case 'quality-high':
      sorted.sort((a, b) => (b.metadata?.quality_score ?? -1) - (a.metadata?.quality_score ?? -1))
      break
    case 'quality-low':
      sorted.sort((a, b) => (a.metadata?.quality_score ?? 999) - (b.metadata?.quality_score ?? 999))
      break
    case 'model':
      sorted.sort((a, b) => (a.checkpoint_model || '').localeCompare(b.checkpoint_model || ''))
      break
  }
  return sorted
})

// Per-character expansion state (show all images)
const expandedCharacters = ref<Set<string>>(new Set())
const IMAGES_PER_CHAR = 24

// Hierarchical grouping: Project -> Character -> Images (with pagination)
const projectCharacterGroups = computed(() => {
  const groups: Record<string, ProjectGroup> = {}
  for (const img of modelFilteredImages.value) {
    const proj = img.project_name || 'Unknown'
    if (!groups[proj]) {
      groups[proj] = {
        characters: {},
        total: 0,
        checkpoint: img.checkpoint_model || '',
        style: img.default_style || '',
      }
    }
    if (!groups[proj].characters[img.character_name]) {
      groups[proj].characters[img.character_name] = []
    }
    groups[proj].characters[img.character_name].push(img)
    groups[proj].total++
  }
  // Apply per-character limit unless expanded
  for (const proj of Object.values(groups)) {
    for (const [charName, images] of Object.entries(proj.characters)) {
      if (!expandedCharacters.value.has(charName) && images.length > IMAGES_PER_CHAR) {
        proj.characters[charName] = images.slice(0, IMAGES_PER_CHAR)
      }
    }
  }
  return groups
})

// Full counts per character (before pagination)
const fullCharacterCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const img of modelFilteredImages.value) {
    counts[img.character_name] = (counts[img.character_name] || 0) + 1
  }
  return counts
})

function toggleCharacterExpand(charName: string) {
  if (expandedCharacters.value.has(charName)) {
    expandedCharacters.value.delete(charName)
  } else {
    expandedCharacters.value.add(charName)
  }
  expandedCharacters.value = new Set(expandedCharacters.value)
}

function projectImageCount(projectName: string): number {
  return approvalStore.pendingImages.filter(img => img.project_name === projectName).length
}

function characterImageCount(characterName: string): number {
  return approvalStore.groupedImages[characterName]?.length || 0
}

function onProjectFilterChange(value: string) {
  approvalStore.filterProject = value
  approvalStore.filterCharacter = ''
}

function showToast(message: string, type: 'approve' | 'reject' | 'regen', durationMs = 3000) {
  const id = ++toastId
  toasts.value.push({ id, message, type })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, durationMs)
}

// Vision review composable (gemma3:12b via Ollama)
const { visionReviewing, runVisionReviewProject, runVisionReview } = useVisionReview(
  showToast,
  () => approvalStore.fetchPendingImages(),
)

function toggleExpand(image: PendingImage) {
  expandedImage.value = expandedImage.value === image.id ? null : image.id
}

function toggleSelection(image: PendingImage) {
  if (selectedImages.value.has(image.id)) {
    selectedImages.value.delete(image.id)
  } else {
    selectedImages.value.add(image.id)
  }
  selectedImages.value = new Set(selectedImages.value)
}

function selectAll(images: PendingImage[]) {
  const allSelected = images.every(img => selectedImages.value.has(img.id))
  if (allSelected) {
    for (const img of images) {
      selectedImages.value.delete(img.id)
    }
  } else {
    for (const img of images) {
      selectedImages.value.add(img.id)
    }
  }
  selectedImages.value = new Set(selectedImages.value)
}

function selectAllProject(projectGroup: ProjectGroup) {
  const allImages = Object.values(projectGroup.characters).flat()
  const allSelected = allImages.every(img => selectedImages.value.has(img.id))
  if (allSelected) {
    for (const img of allImages) {
      selectedImages.value.delete(img.id)
    }
  } else {
    for (const img of allImages) {
      selectedImages.value.add(img.id)
    }
  }
  selectedImages.value = new Set(selectedImages.value)
}

function openReassign(image: PendingImage) {
  reassigningImage.value = image
  if (charactersStore.characters.length === 0) {
    charactersStore.fetchCharacters()
  }
}

async function submitReassign(image: PendingImage, targetSlug: string) {
  reassigning.value = true
  try {
    await api.reassignImage({
      character_slug: image.character_slug,
      image_name: image.name,
      target_character_slug: targetSlug,
    })
    const targetChar = charactersStore.characters.find(c => c.slug === targetSlug)
    showToast(`Moved ${image.name} -> ${targetChar?.name || targetSlug}`, 'regen')
    reassigningImage.value = null
    // Remove from local pending list — image moved to target, will appear on next refresh
    approvalStore.pendingImages = approvalStore.pendingImages.filter(img => img.id !== image.id)
    selectedImages.value.delete(image.id)
    selectedImages.value = new Set(selectedImages.value)
  } catch (e: any) {
    showToast(`Reassign failed: ${e.message}`, 'reject')
  } finally {
    reassigning.value = false
  }
}

async function createAndReassign(image: PendingImage, name: string, designPrompt: string) {
  reassigning.value = true
  try {
    // 1. Create the new character in the project
    const result = await api.createCharacter({
      name,
      project_name: image.project_name,
      design_prompt: designPrompt || undefined,
    })
    const newSlug = result.slug

    // 2. Reassign the image to the new character
    await api.reassignImage({
      character_slug: image.character_slug,
      image_name: image.name,
      target_character_slug: newSlug,
    })

    showToast(`Created ${name} & moved ${image.name}`, 'regen')
    reassigningImage.value = null
    // Remove from local pending list — no full reload needed
    approvalStore.pendingImages = approvalStore.pendingImages.filter(img => img.id !== image.id)
    selectedImages.value.delete(image.id)
    selectedImages.value = new Set(selectedImages.value)
    // Refresh characters list in background (non-blocking) so the new character shows up
    charactersStore.fetchCharacters()
  } catch (e: any) {
    showToast(`Create & reassign failed: ${e.message}`, 'reject')
  } finally {
    reassigning.value = false
  }
}

function openApprovalEditor(image: PendingImage, action: 'approve' | 'reject') {
  editingImage.value = image
  editingAction.value = action
}

function onSubmitEdited(image: PendingImage, approved: boolean, feedback: string, editedPrompt: string) {
  editingImage.value = null
  doApprove(image, approved, feedback, editedPrompt)
}

function onSubmitQuick(image: PendingImage, approved: boolean, feedback: string) {
  editingImage.value = null
  doApprove(image, approved, feedback, '')
}

async function doApprove(image: PendingImage, approved: boolean, feedback: string = '', editedPrompt: string = '') {
  if (processingImages.value.has(image.id)) return
  processingImages.value.add(image.id)
  processingImages.value = new Set(processingImages.value)

  const type = approved ? 'approve' : 'reject'
  flashState[image.id] = type

  await new Promise(r => setTimeout(r, 250))

  try {
    await approvalStore.approveImage(image, approved, feedback, editedPrompt)

    if (approved) {
      // Count remaining approved locally from the characters store dataset cache
      const slug = image.character_slug || image.character_name
      const cached = charactersStore.datasets.get(slug)
      const approvedNow = (cached?.filter(i => i.status === 'approved').length ?? 0) + 1
      if (approvedNow >= MIN_TRAINING) {
        showToast(`${image.character_name} READY TO TRAIN! (${approvedNow}/${MIN_TRAINING})`, 'approve')
      } else {
        showToast(`Approved ${image.character_name} (${approvedNow}/${MIN_TRAINING})`, type)
      }
    } else {
      showToast(`Rejected ${image.character_name} — regenerating`, type)
    }
  } catch {
    showToast(`Failed to ${type} image`, 'reject')
  }

  selectedImages.value.delete(image.id)
  selectedImages.value = new Set(selectedImages.value)
  if (expandedImage.value === image.id) expandedImage.value = null
  delete flashState[image.id]
  processingImages.value.delete(image.id)
  processingImages.value = new Set(processingImages.value)
}

async function approveGroup(groupName: string, images: PendingImage[]) {
  batchProgress.value = { action: `Approving ${images.length} for ${groupName}...`, done: 0, total: images.length }
  for (const image of images) {
    try { await approvalStore.approveImage(image, true) } catch { /* continue */ }
    selectedImages.value.delete(image.id)
    batchProgress.value!.done++
  }
  selectedImages.value = new Set(selectedImages.value)
  batchProgress.value = null
  showToast(`Approved ${images.length} for ${groupName}`, 'approve')
}

async function approveAllProject(projectName: string, projectGroup: ProjectGroup) {
  const allImages = Object.values(projectGroup.characters).flat()
  batchProgress.value = { action: `Approving ${allImages.length} for ${projectName}...`, done: 0, total: allImages.length }
  for (const image of allImages) {
    try { await approvalStore.approveImage(image, true) } catch { /* continue */ }
    selectedImages.value.delete(image.id)
    batchProgress.value!.done++
  }
  selectedImages.value = new Set(selectedImages.value)
  batchProgress.value = null
  showToast(`Approved ${allImages.length} for ${projectName}`, 'approve')
}

function copySeed(seed: number) {
  navigator.clipboard.writeText(String(seed))
  showToast(`Seed ${seed} copied`, 'approve')
}

async function onDetailApprove(image: PendingImage, approved: boolean) {
  await doApprove(image, approved)
  detailImage.value = null
}

async function batchApprove(approved: boolean) {
  const selected = approvalStore.pendingImages.filter(img => selectedImages.value.has(img.id))
  const action = approved ? 'Approving' : 'Rejecting'
  batchProgress.value = { action: `${action} ${selected.length} images...`, done: 0, total: selected.length }
  const feedback = approved ? '' : 'wrong_appearance'
  for (const image of selected) {
    try { await approvalStore.approveImage(image, approved, feedback) } catch { /* continue */ }
    batchProgress.value!.done++
  }
  batchProgress.value = null
  selectedImages.value = new Set()
  showToast(`${approved ? 'Approved' : 'Rejected'} ${selected.length} images`, approved ? 'approve' : 'reject')
}
</script>

<style scoped>
.toast-enter-active { transition: all 250ms ease; }
.toast-leave-active { transition: all 300ms ease; }
.toast-enter-from { opacity: 0; transform: translateX(40px); }
.toast-leave-to { opacity: 0; transform: translateX(40px); }

/* Lightbox */
.lightbox-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  z-index: 2000;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: zoom-out;
}
.lightbox-img {
  max-width: 90vw;
  max-height: 80vh;
  object-fit: contain;
  border-radius: 4px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
  cursor: default;
}
.lightbox-info {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 16px;
  cursor: default;
}
.lightbox-name {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
}
.lightbox-actions {
  display: flex;
  gap: 8px;
}
.lightbox-close {
  position: absolute;
  top: 16px;
  right: 20px;
  font-size: 32px;
  color: rgba(255, 255, 255, 0.7);
  background: none;
  border: none;
  cursor: pointer;
  line-height: 1;
}
.lightbox-close:hover {
  color: #fff;
}

.lightbox-enter-active { transition: opacity 150ms ease; }
.lightbox-leave-active { transition: opacity 150ms ease; }
.lightbox-enter-from,
.lightbox-leave-to { opacity: 0; }
</style>
