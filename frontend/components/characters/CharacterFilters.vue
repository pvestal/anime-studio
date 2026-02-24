<template>
  <div>
    <!-- Filters -->
    <div class="filter-row">
      <select v-model="localFilterProject" style="min-width: 200px;">
        <option value="">All Projects</option>
        <option v-for="name in projectNames" :key="name" :value="name">{{ name }}</option>
      </select>
      <select v-model="localFilterCharacter" style="min-width: 180px;">
        <option value="">All Characters</option>
        <option v-for="c in filteredCharacterNames" :key="c" :value="c">{{ c }}</option>
      </select>
      <button class="btn" @click="$emit('refresh')" :disabled="loading">Refresh</button>
    </div>

    <!-- Model filter chips — only shown when multiple checkpoints exist in current view -->
    <div v-if="modelNames.length > 1" class="model-filter-row">
      <span class="model-label">Model:</span>
      <button
        class="model-chip"
        :class="{ active: !localFilterModel }"
        @click="localFilterModel = ''"
      >
        All ({{ projectFilteredCharacters.length }})
      </button>
      <button
        v-for="m in modelNames"
        :key="m.name"
        class="model-chip"
        :class="{ active: localFilterModel === m.name }"
        @click="localFilterModel = localFilterModel === m.name ? '' : m.name"
      >
        {{ m.short }} ({{ m.count }})
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Character } from '@/types'

const props = defineProps<{
  characters: Character[]
  filterProject: string
  filterCharacter: string
  filterModel: string
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'update:filterProject', value: string): void
  (e: 'update:filterCharacter', value: string): void
  (e: 'update:filterModel', value: string): void
  (e: 'refresh'): void
}>()

const localFilterProject = computed({
  get: () => props.filterProject,
  set: (v: string) => {
    emit('update:filterProject', v)
    // Clear model filter when project changes — pills will recompute
    if (props.filterModel) emit('update:filterModel', '')
  },
})

const localFilterCharacter = computed({
  get: () => props.filterCharacter,
  set: (v: string) => emit('update:filterCharacter', v),
})

const localFilterModel = computed({
  get: () => props.filterModel,
  set: (v: string) => emit('update:filterModel', v),
})

const projectNames = computed(() => {
  const names = new Set<string>()
  for (const c of props.characters) {
    if (c.project_name && c.project_name !== 'Unknown') names.add(c.project_name)
  }
  return [...names].sort()
})

// Characters filtered by project only (before model filter) — pills are scoped to this
const projectFilteredCharacters = computed(() => {
  if (!props.filterProject) return props.characters
  return props.characters.filter(c => c.project_name === props.filterProject)
})

const modelNames = computed(() => {
  const counts: Record<string, number> = {}
  for (const c of projectFilteredCharacters.value) {
    const checkpoints = c.generation_checkpoints
    if (checkpoints && checkpoints.length > 0) {
      const seen = new Set<string>()
      for (const gc of checkpoints) {
        if (!seen.has(gc.checkpoint)) {
          counts[gc.checkpoint] = (counts[gc.checkpoint] || 0) + 1
          seen.add(gc.checkpoint)
        }
      }
    }
    // No fallback — only show pills for checkpoints with actual generation history
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => ({ name, count, short: name.replace('.safetensors', '') }))
})

const filteredCharacterNames = computed(() => {
  return props.characters
    .filter(c => !props.filterProject || c.project_name === props.filterProject)
    .map(c => c.name)
    .sort()
})
</script>

<style scoped>
.filter-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: center;
  flex-wrap: wrap;
}

.model-filter-row {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
  align-items: center;
}

.model-label {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  margin-right: 4px;
}

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
</style>
