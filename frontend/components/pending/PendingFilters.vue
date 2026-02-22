<template>
  <div>
    <!-- Header with filters and batch actions -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 8px;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <h2 style="font-size: 18px; font-weight: 500;">Pending Approval</h2>
        <span style="font-size: 13px; color: var(--text-muted);">
          {{ totalCount }} images
        </span>
        <span v-if="recentCount > 0" class="new-badge">
          {{ recentCount }} new
        </span>
        <span v-if="lastRefreshedAgo" style="font-size: 11px; color: var(--text-muted);">
          Updated {{ lastRefreshedAgo }}
        </span>
      </div>
      <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
        <select :value="filterProject" @change="$emit('update:filterProject', ($event.target as HTMLSelectElement).value)" style="min-width: 200px;">
          <option value="">All Projects</option>
          <option v-for="name in projectNames" :key="name" :value="name">
            {{ name }} ({{ projectImageCount(name) }})
          </option>
        </select>
        <select :value="filterCharacter" @change="$emit('update:filterCharacter', ($event.target as HTMLSelectElement).value)" style="min-width: 180px;">
          <option value="">All Characters</option>
          <option v-for="name in characterNames" :key="name" :value="name">
            {{ name }} ({{ characterImageCount(name) }})
          </option>
        </select>
        <select :value="sortBy" @change="$emit('update:sortBy', ($event.target as HTMLSelectElement).value)" style="min-width: 140px;">
          <option value="newest">Newest First</option>
          <option value="oldest">Oldest First</option>
          <option value="character">By Character</option>
          <option value="quality-high">Quality (High)</option>
          <option value="quality-low">Quality (Low)</option>
          <option value="model">By Model</option>
        </select>
        <button class="btn" @click="$emit('refresh')" :disabled="loading">
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
        <button
          v-if="selectedCount > 0"
          class="btn btn-success"
          @click="$emit('batch-approve', true)"
          :disabled="loading"
        >
          Approve {{ selectedCount }}
        </button>
        <button
          v-if="selectedCount > 0"
          class="btn btn-danger"
          @click="$emit('batch-approve', false)"
          :disabled="loading"
        >
          Reject {{ selectedCount }}
        </button>
      </div>
    </div>

    <!-- Source filter chips -->
    <div style="display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center;">
      <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-right: 4px;">Source:</span>
      <button
        class="source-chip"
        :class="{ active: !filterSource }"
        @click="$emit('update:filterSource', '')"
      >
        All ({{ allFilteredCount }})
      </button>
      <button
        v-for="s in sourceNames"
        :key="s.name"
        class="source-chip"
        :class="{ active: filterSource === s.name, [s.cssClass]: true }"
        @click="$emit('update:filterSource', filterSource === s.name ? '' : s.name)"
      >
        {{ s.label }} ({{ s.count }})
      </button>
    </div>

    <!-- Model filter chips / indicator -->
    <div v-if="modelNames.length > 0" style="display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; align-items: center;">
      <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-right: 4px;">Model:</span>
      <template v-if="modelNames.length > 1">
        <button
          class="model-chip"
          :class="{ active: !filterModel }"
          @click="$emit('update:filterModel', '')"
        >
          All ({{ allFilteredCount }})
        </button>
        <button
          v-for="m in modelNames"
          :key="m.name"
          class="model-chip"
          :class="{ active: filterModel === m.name }"
          @click="$emit('update:filterModel', filterModel === m.name ? '' : m.name)"
        >
          {{ m.short }} ({{ m.count }})
        </button>
      </template>
      <span v-else class="model-chip active" style="cursor: default;">
        {{ modelNames[0].short }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface SourceInfo {
  name: string
  count: number
  label: string
  cssClass: string
}

export interface ModelInfo {
  name: string
  count: number
  short: string
}

defineProps<{
  totalCount: number
  recentCount: number
  lastRefreshedAgo: string
  filterProject: string
  filterCharacter: string
  filterSource: string
  filterModel: string
  sortBy: string
  projectNames: string[]
  characterNames: string[]
  sourceNames: SourceInfo[]
  modelNames: ModelInfo[]
  allFilteredCount: number
  selectedCount: number
  loading: boolean
  projectImageCount: (name: string) => number
  characterImageCount: (name: string) => number
}>()

defineEmits<{
  (e: 'update:filterProject', value: string): void
  (e: 'update:filterCharacter', value: string): void
  (e: 'update:filterSource', value: string): void
  (e: 'update:filterModel', value: string): void
  (e: 'update:sortBy', value: string): void
  (e: 'refresh'): void
  (e: 'batch-approve', approved: boolean): void
}>()
</script>

<style scoped>
/* Source filter chips */
.source-chip {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 12px;
  border: 1px solid var(--border-primary);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  font-family: var(--font-primary);
  transition: all 150ms ease;
  white-space: nowrap;
}
.source-chip:hover { border-color: var(--accent-primary); color: var(--accent-primary); }
.source-chip.active { background: rgba(80, 120, 200, 0.15); border-color: var(--accent-primary); color: var(--accent-primary); font-weight: 500; }
.source-chip.source-yt.active { background: rgba(200, 50, 50, 0.15); border-color: #e04040; color: #e04040; }
.source-chip.source-upload.active { background: rgba(80, 160, 80, 0.15); border-color: var(--status-success); color: var(--status-success); }

/* Model filter chips */
.model-chip {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 12px;
  border: 1px solid var(--border-primary);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  font-family: var(--font-primary);
  transition: all 150ms ease;
  white-space: nowrap;
}
.model-chip:hover {
  border-color: var(--status-warning);
  color: var(--status-warning);
}
.model-chip.active {
  background: rgba(160, 120, 80, 0.15);
  border-color: var(--status-warning);
  color: var(--status-warning);
  font-weight: 500;
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
</style>
