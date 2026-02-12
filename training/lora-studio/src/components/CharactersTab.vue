<template>
  <div>
    <!-- Training feedback toast -->
    <div v-if="trainingMessage" style="position: fixed; top: 16px; right: 16px; z-index: 1000; padding: 10px 16px; border-radius: 4px; font-size: 13px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); background: rgba(80,160,80,0.15); border: 1px solid var(--status-success); color: var(--status-success); min-width: 280px;">
      {{ trainingMessage }}
    </div>

    <!-- Stats bar -->
    <div style="display: flex; gap: 16px; margin-bottom: 24px;">
      <div class="card" style="flex: 1; text-align: center;">
        <div style="font-size: 28px; font-weight: 600; color: var(--accent-primary);">
          {{ readyCount }}
        </div>
        <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase;">Ready to Train</div>
      </div>
      <div class="card" style="flex: 1; text-align: center;">
        <div style="font-size: 28px; font-weight: 600; color: var(--status-warning);">
          {{ needsMoreCount }}
        </div>
        <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase;">Need More Approvals</div>
      </div>
      <div class="card" style="flex: 1; text-align: center;">
        <div style="font-size: 28px; font-weight: 600; color: var(--status-success);">
          {{ approvedCount }}
        </div>
        <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase;">Total Approved</div>
      </div>
    </div>

    <!-- Filters -->
    <div style="display: flex; gap: 12px; margin-bottom: 16px; align-items: center; flex-wrap: wrap;">
      <select v-model="filterProject" style="min-width: 200px;">
        <option value="">All Projects</option>
        <option v-for="name in projectNames" :key="name" :value="name">{{ name }}</option>
      </select>
      <select v-model="filterCharacter" style="min-width: 180px;">
        <option value="">All Characters</option>
        <option v-for="c in filteredCharacterNames" :key="c" :value="c">{{ c }}</option>
      </select>
      <button class="btn" @click="charactersStore.fetchCharacters()" :disabled="charactersStore.loading">Refresh</button>
    </div>

    <!-- Model filter chips -->
    <div v-if="modelNames.length > 1" style="display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; align-items: center;">
      <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-right: 4px;">Model:</span>
      <button
        class="model-chip"
        :class="{ active: !filterModel }"
        @click="filterModel = ''"
      >
        All ({{ charactersStore.characters.length }})
      </button>
      <button
        v-for="m in modelNames"
        :key="m.name"
        class="model-chip"
        :class="{ active: filterModel === m.name }"
        @click="filterModel = filterModel === m.name ? '' : m.name"
      >
        {{ m.short }} ({{ m.count }})
      </button>
    </div>

    <!-- Loading -->
    <div v-if="charactersStore.loading" style="text-align: center; padding: 48px;">
      <div class="spinner" style="width: 32px; height: 32px; margin: 0 auto 16px;"></div>
      <p style="color: var(--text-muted);">Loading characters...</p>
    </div>

    <!-- Error -->
    <div v-else-if="charactersStore.error" class="card" style="background: rgba(160,80,80,0.1); border-color: var(--status-error);">
      <p style="color: var(--status-error);">{{ charactersStore.error }}</p>
      <button class="btn" @click="charactersStore.clearError()" style="margin-top: 8px;">Dismiss</button>
    </div>

    <!-- Grouped by project -->
    <div v-else>
      <div v-for="(group, projectName) in projectGroups" :key="projectName" style="margin-bottom: 32px;">
        <!-- Project header -->
        <div style="margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid var(--border-primary);">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <h3 style="font-size: 17px; font-weight: 600;">{{ projectName }}</h3>
            <span style="font-size: 12px; color: var(--text-muted);">
              {{ group.characters.length }} characters
            </span>
          </div>
          <!-- Project generation settings -->
          <div v-if="group.style" style="display: flex; gap: 12px; margin-top: 6px; flex-wrap: wrap;">
            <span class="meta-tag">{{ group.style.default_style }}</span>
            <span class="meta-tag" style="color: var(--accent-primary);">{{ group.style.checkpoint_model }}</span>
            <span v-if="group.style.cfg_scale" class="meta-tag">CFG {{ group.style.cfg_scale }}</span>
            <span v-if="group.style.steps" class="meta-tag">{{ group.style.steps }} steps</span>
            <span v-if="group.style.resolution" class="meta-tag">{{ group.style.resolution }}</span>
          </div>
        </div>

        <!-- Characters grid within project -->
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px;">
          <div
            v-for="character in group.characters"
            :key="character.slug"
            class="card"
            :style="stats(character.name).canTrain ? { borderColor: 'var(--status-success)' } : {}"
          >
            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px;">
              <h3 style="font-size: 15px; font-weight: 500;">{{ character.name }}</h3>
              <span
                v-if="stats(character.name).canTrain"
                class="badge badge-approved"
                style="font-size: 11px;"
              >
                Ready
              </span>
            </div>

            <!-- SSOT design prompt (click to edit) -->
            <div v-if="editingSlug === character.slug" style="margin-bottom: 8px;">
              <textarea
                v-model="editPromptText"
                style="width: 100%; min-height: 60px; font-size: 11px; padding: 5px 8px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--accent-primary); border-radius: 3px; resize: vertical; font-family: var(--font-primary); line-height: 1.4;"
                @keydown.escape="cancelEdit"
              ></textarea>
              <div style="display: flex; gap: 4px; margin-top: 4px;">
                <button class="btn btn-success" style="font-size: 11px; padding: 3px 8px;" @click="savePrompt(character)" :disabled="savingPrompt">
                  {{ savingPrompt ? 'Saving...' : 'Save' }}
                </button>
                <button class="btn" style="font-size: 11px; padding: 3px 8px; color: var(--accent-primary);" @click="saveAndRegenerate(character)" :disabled="savingPrompt">
                  Save & Regenerate
                </button>
                <button class="btn" style="font-size: 11px; padding: 3px 8px;" @click="cancelEdit">Cancel</button>
              </div>
            </div>
            <div
              v-else-if="character.design_prompt"
              style="font-size: 11px; color: var(--text-muted); margin-bottom: 8px; padding: 5px 8px; background: var(--bg-secondary); border-radius: 3px; border-left: 2px solid var(--accent-primary); line-height: 1.4; max-height: 48px; overflow: hidden; cursor: pointer;"
              :title="'Click to edit design prompt'"
              @click="startEdit(character)"
            >
              {{ character.design_prompt }}
            </div>

            <!-- Approved progress toward threshold -->
            <div style="margin-bottom: 12px;">
              <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
                <span :style="{ color: stats(character.name).canTrain ? 'var(--status-success)' : 'var(--text-secondary)' }">
                  {{ stats(character.name).approved }}/{{ MIN_TRAINING_IMAGES }} approved
                </span>
                <span v-if="stats(character.name).pending > 0" style="color: var(--text-muted);">
                  {{ stats(character.name).pending }} pending
                </span>
                <span v-else-if="!stats(character.name).canTrain" style="color: var(--status-error); font-size: 11px;">
                  Need {{ MIN_TRAINING_IMAGES - stats(character.name).approved }} more
                </span>
              </div>
              <div class="progress-track" style="height: 6px;">
                <div
                  class="progress-bar"
                  :class="{ ready: stats(character.name).canTrain }"
                  :style="{ width: `${Math.min(100, (stats(character.name).approved / MIN_TRAINING_IMAGES) * 100)}%` }"
                ></div>
              </div>
            </div>

            <!-- Action area -->
            <div style="display: flex; gap: 6px;">
              <button
                v-if="stats(character.name).canTrain"
                class="btn btn-success"
                style="flex: 1; font-size: 13px;"
                @click="startTraining(character.name)"
                :disabled="trainingStore.loading"
              >
                Start Training ({{ stats(character.name).approved }} images)
              </button>
              <template v-else>
                <button
                  class="btn"
                  style="flex: 1; font-size: 12px;"
                  @click="generateMore(character)"
                  :disabled="generatingSlug === character.slug"
                >
                  {{ generatingSlug === character.slug ? 'Queued...' : `Generate ${MIN_TRAINING_IMAGES - stats(character.name).approved} More` }}
                </button>
                <span v-if="stats(character.name).pending > 0" style="font-size: 11px; color: var(--text-muted); align-self: center;">
                  {{ stats(character.name).pending }} pending
                </span>
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty -->
    <div v-if="!charactersStore.loading && charactersStore.characters.length === 0" style="text-align: center; padding: 48px;">
      <p style="color: var(--text-muted);">No characters found</p>
      <button class="btn" @click="charactersStore.fetchCharacters()" style="margin-top: 8px;">Refresh</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useCharactersStore } from '@/stores/characters'
import { useTrainingStore } from '@/stores/training'
import { api } from '@/api/client'
import type { Character } from '@/types'

const MIN_TRAINING_IMAGES = 10

const charactersStore = useCharactersStore()
const trainingStore = useTrainingStore()
const filterProject = ref('')
const filterCharacter = ref('')
const filterModel = ref('')
const generatingSlug = ref<string | null>(null)
const editingSlug = ref<string | null>(null)
const editPromptText = ref('')
const savingPrompt = ref(false)
const trainingMessage = ref('')

const projectNames = computed(() => {
  const names = new Set<string>()
  for (const c of charactersStore.characters) {
    if (c.project_name && c.project_name !== 'Unknown') names.add(c.project_name)
  }
  return [...names].sort()
})

const modelNames = computed(() => {
  const counts: Record<string, number> = {}
  for (const c of charactersStore.characters) {
    const model = c.checkpoint_model || 'unknown'
    counts[model] = (counts[model] || 0) + 1
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => ({ name, count, short: name.replace('.safetensors', '') }))
})

const filteredCharacterNames = computed(() => {
  return charactersStore.characters
    .filter(c => !filterProject.value || c.project_name === filterProject.value)
    .map(c => c.name)
    .sort()
})

const approvedCount = computed(() => {
  let total = 0
  for (const images of charactersStore.datasets.values()) {
    total += images.filter(img => img.status === 'approved').length
  }
  return total
})

const readyCount = computed(() => {
  return charactersStore.characters.filter(c => stats(c.name).canTrain).length
})

const needsMoreCount = computed(() => {
  return charactersStore.characters.filter(c => !stats(c.name).canTrain && stats(c.name).total > 0).length
})

interface ProjectGroup {
  characters: Character[]
  style: {
    default_style: string
    checkpoint_model: string
    cfg_scale: number | null
    steps: number | null
    resolution: string
  } | null
}

// Group characters by project, filtered by dropdowns
const projectGroups = computed(() => {
  const groups: Record<string, ProjectGroup> = {}
  for (const c of charactersStore.characters) {
    const proj = c.project_name || 'Unknown'
    if (filterProject.value && proj !== filterProject.value) continue
    if (filterCharacter.value && c.name !== filterCharacter.value) continue
    if (filterModel.value && (c.checkpoint_model || 'unknown') !== filterModel.value) continue
    if (!groups[proj]) {
      groups[proj] = {
        characters: [],
        style: c.checkpoint_model ? {
          default_style: c.default_style,
          checkpoint_model: c.checkpoint_model,
          cfg_scale: c.cfg_scale,
          steps: c.steps,
          resolution: c.resolution,
        } : null,
      }
    }
    groups[proj].characters.push(c)
  }
  for (const group of Object.values(groups)) {
    group.characters.sort((a, b) => {
      const sa = stats(a.name)
      const sb = stats(b.name)
      if (sa.canTrain !== sb.canTrain) return sa.canTrain ? -1 : 1
      return sb.approved - sa.approved
    })
  }
  return groups
})

function stats(name: string) {
  const s = charactersStore.getCharacterStats(name)
  return { ...s, canTrain: s.approved >= MIN_TRAINING_IMAGES }
}

function startEdit(character: Character) {
  editingSlug.value = character.slug
  editPromptText.value = character.design_prompt || ''
}

function cancelEdit() {
  editingSlug.value = null
  editPromptText.value = ''
}

async function savePrompt(character: Character) {
  if (!editPromptText.value.trim()) return
  savingPrompt.value = true
  try {
    await api.updateCharacter(character.slug, { design_prompt: editPromptText.value.trim() })
    editingSlug.value = null
    await charactersStore.fetchCharacters()
  } catch (error) {
    console.error('Failed to update design prompt:', error)
  } finally {
    savingPrompt.value = false
  }
}

async function saveAndRegenerate(character: Character) {
  if (!editPromptText.value.trim()) return
  savingPrompt.value = true
  try {
    await api.updateCharacter(character.slug, { design_prompt: editPromptText.value.trim() })
    editingSlug.value = null
    const need = Math.max(1, MIN_TRAINING_IMAGES - stats(character.name).approved)
    await api.regenerate(character.slug, need)
    await charactersStore.fetchCharacters()
  } catch (error) {
    console.error('Failed to save and regenerate:', error)
  } finally {
    savingPrompt.value = false
  }
}

async function generateMore(character: Character) {
  const slug = character.slug
  const need = MIN_TRAINING_IMAGES - stats(character.name).approved
  if (need <= 0) return
  generatingSlug.value = slug
  try {
    await api.regenerate(slug, need)
  } catch (error) {
    console.error('Failed to generate:', error)
  } finally {
    setTimeout(() => { generatingSlug.value = null }, 2000)
  }
}

async function startTraining(characterName: string) {
  try {
    await trainingStore.startTraining({
      character_name: characterName,
      epochs: 20,
      learning_rate: 0.0001,
      resolution: 512,
    })
    trainingMessage.value = `Training started for ${characterName}! Check Training Jobs tab.`
    setTimeout(() => { trainingMessage.value = '' }, 5000)
  } catch (error: any) {
    trainingMessage.value = `Failed: ${error?.message || error}`
    setTimeout(() => { trainingMessage.value = '' }, 5000)
  }
}
</script>

<style scoped>
.meta-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
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
