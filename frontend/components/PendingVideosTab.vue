<template>
  <div>
    <!-- Error banner -->
    <div v-if="store.error" class="error-banner">
      {{ store.error }}
      <button @click="store.clearError()" style="margin-left: 8px; font-size: 12px;">&times;</button>
    </div>

    <!-- Filter bar -->
    <div class="filter-bar">
      <div class="filter-group">
        <!-- Project filter -->
        <select v-model="projectFilter" class="filter-select" @change="onProjectChange">
          <option :value="null">All Projects</option>
          <option v-for="[id, name] in store.projectNames" :key="id" :value="id">
            {{ name }}
          </option>
        </select>

        <!-- Character filter -->
        <select v-model="characterFilter" class="filter-select" @change="onCharacterChange">
          <option value="">All Characters</option>
          <option v-for="[slug, count] in sortedCharacters" :key="slug" :value="slug">
            {{ slug }} ({{ count }})
          </option>
        </select>
      </div>

      <!-- Engine chips -->
      <div class="engine-chips">
        <button
          class="chip"
          :class="{ active: store.filterEngine === '' }"
          @click="store.filterEngine = ''"
        >
          All ({{ store.filteredVideos.length }})
        </button>
        <button
          v-for="[engine, count] in sortedEngines"
          :key="engine"
          class="chip"
          :class="{ active: store.filterEngine === engine, [`engine-${engine}`]: true }"
          @click="store.filterEngine = store.filterEngine === engine ? '' : engine"
        >
          {{ engineLabel(engine) }} ({{ count }})
        </button>
      </div>

      <!-- Batch actions -->
      <div class="batch-actions">
        <button v-if="store.selectedIds.size > 0" class="btn btn-success btn-sm" @click="batchApprove">
          Approve {{ store.selectedIds.size }}
        </button>
        <button v-if="store.selectedIds.size > 0" class="btn btn-danger btn-sm" @click="batchReject">
          Reject {{ store.selectedIds.size }}
        </button>
        <button v-if="store.filteredVideos.length > 0" class="btn btn-sm" @click="toggleSelectAll">
          {{ allSelected ? 'Deselect All' : 'Select All' }}
        </button>
        <button class="btn btn-sm" @click="refresh" :disabled="store.loading">
          Refresh
        </button>
      </div>
    </div>

    <!-- Engine stats panel (collapsible) -->
    <details v-if="store.engineStats.length > 0" class="stats-panel">
      <summary class="stats-summary">Engine Quality Stats</summary>
      <div class="stats-grid">
        <div v-for="stat in store.engineStats" :key="stat.video_engine" class="stat-card">
          <div class="stat-header">
            <span :class="['engine-badge-sm', `engine-${stat.video_engine}`]">
              {{ engineLabel(stat.video_engine) }}
            </span>
            <span class="stat-count">{{ stat.total }} shots</span>
          </div>
          <div class="stat-row">
            <span>Avg Quality</span>
            <span :style="{ color: qualityColor(stat.avg_quality ?? 0) }">
              {{ stat.avg_quality != null ? (stat.avg_quality * 100).toFixed(0) + '%' : 'N/A' }}
            </span>
          </div>
          <div class="stat-row">
            <span>Approved / Rejected</span>
            <span>
              <span style="color: var(--status-success);">{{ stat.approved }}</span>
              /
              <span style="color: var(--status-error);">{{ stat.rejected }}</span>
            </span>
          </div>
          <div v-if="stat.avg_gen_time" class="stat-row">
            <span>Avg Gen Time</span>
            <span>{{ stat.avg_gen_time }}s</span>
          </div>
        </div>
      </div>
      <!-- Blacklist -->
      <div v-if="store.blacklist.length > 0" style="margin-top: 12px;">
        <h4 style="font-size: 12px; color: var(--status-error); margin-bottom: 6px;">Blacklisted Engines</h4>
        <div v-for="bl in store.blacklist" :key="`${bl.character_slug}-${bl.video_engine}`" class="blacklist-row">
          <span class="context-tag char-tag">{{ bl.character_slug }}</span>
          <span :class="['engine-badge-sm', `engine-${bl.video_engine}`]">{{ engineLabel(bl.video_engine) }}</span>
          <span style="font-size: 11px; color: var(--text-muted);">{{ bl.reason || 'No reason' }}</span>
        </div>
      </div>
    </details>

    <!-- Loading -->
    <div v-if="store.loading" style="text-align: center; padding: 40px; color: var(--text-muted);">
      <div class="spinner" style="width: 32px; height: 32px; margin: 0 auto 12px;"></div>
      Loading pending videos...
    </div>

    <!-- Empty state -->
    <div v-else-if="store.filteredVideos.length === 0" style="text-align: center; padding: 40px; color: var(--text-muted);">
      <p>No pending videos for review.</p>
      <p style="font-size: 12px; margin-top: 8px;">Videos will appear here after scene generation with QC review.</p>
    </div>

    <!-- Video grid -->
    <div v-else class="video-grid">
      <VideoCard
        v-for="video in store.filteredVideos"
        :key="video.id"
        :video="video"
        :is-selected="store.selectedIds.has(video.id)"
        @toggle-selection="store.toggleSelection"
        @approve="onApprove"
        @reject="onReject"
        @reject-engine="onRejectEngine"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { PendingVideo } from '@/types'
import { useVideoReviewStore } from '@/stores/videoReview'
import VideoCard from './pending/VideoCard.vue'

const store = useVideoReviewStore()

const projectFilter = ref<number | null>(null)
const characterFilter = ref<string>('')

const ENGINE_LABELS: Record<string, string> = {
  framepack: 'FramePack',
  framepack_f1: 'FramePack F1',
  ltx: 'LTX',
  wan: 'Wan 2.1',
}

function engineLabel(engine: string): string {
  return ENGINE_LABELS[engine] || engine
}

function qualityColor(score: number): string {
  if (score >= 0.7) return 'var(--status-success)'
  if (score >= 0.4) return 'var(--status-warning)'
  return 'var(--status-error)'
}

const sortedEngines = computed(() => {
  return Object.entries(store.engineCounts).sort((a, b) => b[1] - a[1])
})

const sortedCharacters = computed(() => {
  return Object.entries(store.characterCounts).sort((a, b) => b[1] - a[1])
})

const allSelected = computed(() => {
  return store.filteredVideos.length > 0 && store.filteredVideos.every(v => store.selectedIds.has(v.id))
})

function onProjectChange() {
  store.filterProject = projectFilter.value
  store.filterCharacter = ''
  characterFilter.value = ''
  store.fetchPendingVideos()
  store.fetchEngineStats()
}

function onCharacterChange() {
  store.filterCharacter = characterFilter.value
  store.fetchEngineStats()
}

function toggleSelectAll() {
  if (allSelected.value) {
    store.clearSelection()
  } else {
    store.selectAll()
  }
}

async function onApprove(video: PendingVideo) {
  await store.reviewVideo(video.id, true)
}

async function onReject(video: PendingVideo) {
  await store.reviewVideo(video.id, false, 'Rejected via video review')
}

async function onRejectEngine(video: PendingVideo) {
  await store.reviewVideo(video.id, false, `Engine ${video.video_engine} rejected for ${video.characters_present[0] || 'character'}`, true)
}

async function batchApprove() {
  await store.batchReview(true, 'Batch approved')
}

async function batchReject() {
  await store.batchReview(false, 'Batch rejected')
}

function refresh() {
  store.fetchPendingVideos()
  store.fetchEngineStats()
}

onMounted(() => {
  store.fetchPendingVideos()
  store.fetchEngineStats()
})
</script>

<style scoped>
.error-banner {
  background: rgba(200, 80, 80, 0.15);
  border: 1px solid var(--status-error);
  color: var(--status-error);
  padding: 8px 12px;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.filter-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 16px;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
}

.filter-group {
  display: flex;
  gap: 8px;
}

.filter-select {
  font-size: 12px;
  padding: 4px 8px;
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
  font-family: var(--font-primary);
}

.engine-chips {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.chip {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 12px;
  border: 1px solid var(--border-primary);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-family: var(--font-primary);
  transition: all 150ms ease;
}
.chip:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.chip.active {
  background: var(--accent-primary);
  color: #fff;
  border-color: var(--accent-primary);
}
.chip.active.engine-framepack { background: #2d8a4e; border-color: #2d8a4e; }
.chip.active.engine-framepack_f1 { background: #3ba55d; border-color: #3ba55d; }
.chip.active.engine-ltx { background: #4e7dd4; border-color: #4e7dd4; }
.chip.active.engine-wan { background: #d4844e; border-color: #d4844e; }

.batch-actions {
  display: flex;
  gap: 6px;
  margin-left: auto;
}

.btn-sm {
  font-size: 11px;
  padding: 4px 10px;
}

.stats-panel {
  margin-bottom: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  padding: 0;
}
.stats-summary {
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}
.stats-summary:hover {
  color: var(--accent-primary);
}
.stats-panel[open] .stats-summary {
  border-bottom: 1px solid var(--border-primary);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
  padding: 12px;
}

.stat-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  padding: 8px;
}
.stat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.stat-count {
  font-size: 11px;
  color: var(--text-muted);
}
.stat-row {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 2px;
}

.engine-badge-sm {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
  color: #fff;
}
.engine-badge-sm.engine-framepack { background: #2d8a4e; }
.engine-badge-sm.engine-framepack_f1 { background: #3ba55d; }
.engine-badge-sm.engine-ltx { background: #4e7dd4; }
.engine-badge-sm.engine-wan { background: #d4844e; }

.blacklist-row {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 4px 12px;
  font-size: 12px;
}

.context-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 2px;
  border: 1px solid var(--border-primary);
  white-space: nowrap;
}
.char-tag {
  background: rgba(80, 120, 200, 0.12);
  color: var(--accent-primary);
  border-color: var(--accent-primary);
  font-weight: 500;
}

.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
</style>
