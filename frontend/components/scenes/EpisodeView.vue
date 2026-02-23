<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <div style="font-size: 15px; font-weight: 500; color: var(--accent-primary);">Episodes</div>
      <button class="btn btn-primary" style="font-size: 12px;" @click="showCreateModal = true">+ New Episode</button>
    </div>

    <div v-if="loading" style="color: var(--text-muted); font-size: 13px;">Loading episodes...</div>
    <div v-else-if="episodes.length === 0" style="color: var(--text-muted); font-size: 13px;">
      No episodes yet. Create one to start assembling scenes into full episodes.
    </div>

    <!-- Episode List -->
    <div v-else style="display: flex; flex-direction: column; gap: 12px;">
      <div
        v-for="ep in episodes"
        :key="ep.id"
        class="card"
        :style="{ borderLeft: selectedEpisodeId === ep.id ? '3px solid var(--accent-primary)' : '3px solid transparent' }"
      >
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
          <div>
            <span style="font-size: 14px; font-weight: 500;">E{{ ep.episode_number }} — {{ ep.title }}</span>
            <span :class="statusClass(ep.status)" style="margin-left: 8px; font-size: 11px; padding: 1px 8px; border-radius: 3px;">
              {{ ep.status }}
            </span>
          </div>
        </div>
        <div v-if="ep.description" style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">{{ ep.description }}</div>
        <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
          {{ ep.scene_count }} scene{{ ep.scene_count !== 1 ? 's' : '' }}
          <span v-if="ep.actual_duration_seconds"> · {{ formatDuration(ep.actual_duration_seconds) }}</span>
          <span v-if="ep.story_arc"> · {{ ep.story_arc }}</span>
        </div>
        <div style="display: flex; gap: 6px; flex-wrap: wrap;">
          <button class="btn" style="font-size: 11px; padding: 3px 10px;" @click="openEditor(ep)">Edit</button>
          <button class="btn btn-success" style="font-size: 11px; padding: 3px 10px;" :disabled="ep.scene_count === 0" @click="assembleEpisode(ep)">Assemble</button>
          <button v-if="ep.final_video_path" class="btn" style="font-size: 11px; padding: 3px 10px;" @click="$emit('play-episode', ep)">Play</button>
          <button v-if="ep.status === 'assembled'" class="btn btn-primary" style="font-size: 11px; padding: 3px 10px;" @click="publishEpisode(ep)">Publish</button>
          <button class="btn btn-danger" style="font-size: 11px; padding: 3px 10px;" @click="deleteEpisode(ep)">Delete</button>
        </div>

        <!-- Expanded scene list when selected -->
        <div v-if="selectedEpisodeId === ep.id && selectedEpisode" style="margin-top: 12px; border-top: 1px solid var(--border-primary); padding-top: 12px;">
          <div style="font-size: 12px; font-weight: 500; margin-bottom: 8px;">Scenes in Episode</div>

          <div v-if="selectedEpisode.scenes && selectedEpisode.scenes.length > 0" style="display: flex; flex-direction: column; gap: 6px;">
            <div v-for="(s, idx) in selectedEpisode.scenes" :key="s.scene_id"
              style="display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: var(--bg-primary); border-radius: 4px; font-size: 12px;"
            >
              <span style="color: var(--text-muted); min-width: 20px;">{{ idx + 1 }}.</span>
              <span style="flex: 1;">{{ s.title || 'Untitled' }}</span>
              <span v-if="s.transition && s.transition !== 'cut'" style="font-size: 10px; color: var(--text-muted); padding: 1px 4px;">{{ s.transition }}</span>
              <span :class="statusClass(s.generation_status)" style="font-size: 10px; padding: 1px 6px; border-radius: 3px;">{{ s.generation_status }}</span>
              <span v-if="s.actual_duration_seconds" style="color: var(--text-muted);">{{ s.actual_duration_seconds.toFixed(1) }}s</span>
              <button class="btn btn-danger" style="font-size: 10px; padding: 1px 6px;" @click="removeScene(ep, s.scene_id)">×</button>
            </div>
          </div>
          <div v-else style="color: var(--text-muted); font-size: 12px;">No scenes added yet.</div>

          <!-- Add scene picker -->
          <div style="margin-top: 8px;">
            <div style="display: flex; gap: 6px; align-items: flex-end;">
              <div style="flex: 1;">
                <select v-model="addSceneId" class="field-input" style="font-size: 12px; padding: 4px 6px;">
                  <option value="">Add a scene...</option>
                  <option v-for="s in availableScenes" :key="s.id" :value="s.id">{{ s.title }} ({{ s.generation_status }})</option>
                </select>
              </div>
              <div style="width: 110px;">
                <label style="font-size: 10px; color: var(--text-muted); display: block; margin-bottom: 2px;">Transition</label>
                <select v-model="addTransition" class="field-input" style="font-size: 11px; padding: 4px 6px;">
                  <option value="fadeblack">Fade Black</option>
                  <option value="dissolve">Dissolve</option>
                  <option value="fade">Fade</option>
                  <option value="wipeleft">Wipe Left</option>
                  <option value="cut">Cut</option>
                </select>
              </div>
            </div>
            <button v-if="addSceneId" class="btn btn-primary" style="font-size: 11px; padding: 3px 10px; margin-top: 4px;" @click="addScene(ep)">Add Scene</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create Episode Modal -->
    <div v-if="showCreateModal" style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center;" @click.self="showCreateModal = false" @keydown.escape.window="showCreateModal = false">
      <div class="card" style="width: 400px;">
        <div style="font-size: 14px; font-weight: 500; margin-bottom: 16px;">New Episode</div>
        <div class="field-group">
          <label class="field-label">Episode Number</label>
          <input v-model.number="newEpisode.episode_number" type="number" min="1" class="field-input" />
        </div>
        <div class="field-group">
          <label class="field-label">Title</label>
          <input v-model="newEpisode.title" type="text" :placeholder="`Episode ${newEpisode.episode_number}`" class="field-input" />
        </div>
        <div class="field-group">
          <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
            <label class="field-label" style="margin-bottom: 0;">Description</label>
            <EchoAssistButton
              context-type="description"
              :context-payload="{
                project_name: projectStore.currentProject?.name,
                project_genre: projectStore.currentProject?.genre || undefined,
                project_premise: projectStore.currentProject?.premise || undefined,
                storyline_summary: projectStore.currentProject?.storyline?.summary || undefined,
              }"
              :current-value="newEpisode.description"
              compact
              @accept="newEpisode.description = $event.suggestion"
            />
          </div>
          <textarea v-model="newEpisode.description" rows="2" placeholder="What happens in this episode..." class="field-input" style="resize: vertical;"></textarea>
        </div>
        <div class="field-group">
          <label class="field-label">Story Arc</label>
          <input v-model="newEpisode.story_arc" type="text" placeholder="Optional story arc tag" class="field-input" />
          <div v-if="storyArcs.length > 0" style="display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px;">
            <button
              v-for="arc in storyArcs"
              :key="arc"
              type="button"
              style="padding: 2px 8px; font-size: 11px; background: var(--bg-primary); color: var(--text-secondary); border: 1px solid var(--border-primary); border-radius: 10px; cursor: pointer; font-family: var(--font-primary);"
              :style="newEpisode.story_arc === arc ? { borderColor: 'var(--accent-primary)', color: 'var(--accent-primary)', background: 'rgba(122,162,247,0.1)' } : {}"
              @click="newEpisode.story_arc = newEpisode.story_arc === arc ? '' : arc"
            >{{ arc }}</button>
          </div>
        </div>
        <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px;">
          <button class="btn" @click="showCreateModal = false">Cancel</button>
          <button class="btn btn-primary" @click="createEpisode">Create</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { Episode, BuilderScene } from '@/types'
import { episodesApi } from '@/api/episodes'
import { useProjectStore } from '@/stores/project'
import EchoAssistButton from '../EchoAssistButton.vue'

const projectStore = useProjectStore()

const props = defineProps<{
  projectId: number
  scenes: BuilderScene[]
}>()

const emit = defineEmits<{
  'play-episode': [ep: Episode]
}>()

const loading = ref(false)
const episodes = ref<Episode[]>([])
const selectedEpisodeId = ref('')
const selectedEpisode = ref<Episode | null>(null)
const showCreateModal = ref(false)
const addSceneId = ref('')
const addTransition = ref('fadeblack')

const newEpisode = ref({
  episode_number: 1,
  title: '',
  description: '',
  story_arc: '',
})

const availableScenes = ref<BuilderScene[]>([])

const storyArcs = computed(() => projectStore.currentProject?.storyline?.story_arcs || [])

watch(() => props.projectId, async (pid) => {
  if (pid) await loadEpisodes()
}, { immediate: true })

watch(() => props.scenes, (s) => {
  availableScenes.value = s.filter(sc => sc.generation_status === 'completed' || sc.generation_status === 'partial')
}, { immediate: true })

async function loadEpisodes() {
  loading.value = true
  try {
    const data = await episodesApi.listEpisodes(props.projectId)
    episodes.value = data.episodes
    // Auto-set next episode number
    const maxNum = episodes.value.reduce((m, e) => Math.max(m, e.episode_number), 0)
    newEpisode.value.episode_number = maxNum + 1
  } catch (e) {
    console.error('Failed to load episodes:', e)
  } finally {
    loading.value = false
  }
}

async function createEpisode() {
  try {
    await episodesApi.createEpisode({
      project_id: props.projectId,
      episode_number: newEpisode.value.episode_number,
      title: newEpisode.value.title || `Episode ${newEpisode.value.episode_number}`,
      description: newEpisode.value.description || undefined,
      story_arc: newEpisode.value.story_arc || undefined,
    })
    showCreateModal.value = false
    newEpisode.value = { episode_number: newEpisode.value.episode_number + 1, title: '', description: '', story_arc: '' }
    await loadEpisodes()
  } catch (e) {
    console.error('Failed to create episode:', e)
  }
}

async function openEditor(ep: Episode) {
  if (selectedEpisodeId.value === ep.id) {
    selectedEpisodeId.value = ''
    selectedEpisode.value = null
    return
  }
  try {
    selectedEpisode.value = await episodesApi.getEpisode(ep.id)
    selectedEpisodeId.value = ep.id
  } catch (e) {
    console.error('Failed to load episode:', e)
  }
}

async function addScene(ep: Episode) {
  if (!addSceneId.value) return
  const pos = (selectedEpisode.value?.scenes?.length ?? 0) + 1
  try {
    await episodesApi.addSceneToEpisode(ep.id, addSceneId.value, pos, addTransition.value)
    addSceneId.value = ''
    addTransition.value = 'fadeblack'
    selectedEpisode.value = await episodesApi.getEpisode(ep.id)
    await loadEpisodes()
  } catch (e) {
    console.error('Failed to add scene:', e)
  }
}

async function removeScene(ep: Episode, sceneId: string) {
  try {
    await episodesApi.removeSceneFromEpisode(ep.id, sceneId)
    selectedEpisode.value = await episodesApi.getEpisode(ep.id)
    await loadEpisodes()
  } catch (e) {
    console.error('Failed to remove scene:', e)
  }
}

async function assembleEpisode(ep: Episode) {
  try {
    const result = await episodesApi.assembleEpisode(ep.id)
    alert(`Episode assembled: ${result.scenes_included} scenes, ${result.duration_seconds?.toFixed(1)}s${result.scenes_missing.length ? `\nMissing: ${result.scenes_missing.join(', ')}` : ''}`)
    await loadEpisodes()
  } catch (e) {
    console.error('Assembly failed:', e)
    alert(`Assembly failed: ${e}`)
  }
}

async function publishEpisode(ep: Episode) {
  if (!confirm(`Publish "${ep.title}" to Jellyfin?`)) return
  try {
    const result = await episodesApi.publishEpisode(ep.id)
    alert(`Published: ${result.published_path}\nJellyfin scan: ${result.jellyfin_scan}`)
    await loadEpisodes()
  } catch (e) {
    console.error('Publish failed:', e)
    alert(`Publish failed: ${e}`)
  }
}

async function deleteEpisode(ep: Episode) {
  if (!confirm(`Delete episode "${ep.title}"?`)) return
  try {
    await episodesApi.deleteEpisode(ep.id)
    if (selectedEpisodeId.value === ep.id) {
      selectedEpisodeId.value = ''
      selectedEpisode.value = null
    }
    await loadEpisodes()
  } catch (e) {
    console.error('Failed to delete episode:', e)
  }
}

function statusClass(status: string): string {
  const map: Record<string, string> = {
    draft: 'badge-draft', assembled: 'badge-completed', published: 'badge-published',
    completed: 'badge-completed', partial: 'badge-partial', generating: 'badge-generating', failed: 'badge-failed',
  }
  return map[status] || 'badge-draft'
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return m > 0 ? `${m}m${s}s` : `${s}s`
}
</script>

<style scoped>
.field-group { margin-bottom: 10px; }
.field-label { font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 4px; }
.field-input {
  width: 100%; padding: 6px 8px; font-size: 13px;
  background: var(--bg-primary); color: var(--text-primary);
  border: 1px solid var(--border-primary); border-radius: 3px;
  font-family: var(--font-primary);
}
.badge-draft { background: var(--bg-tertiary); color: var(--text-secondary); }
.badge-generating { background: rgba(122, 162, 247, 0.2); color: var(--accent-primary); }
.badge-completed { background: rgba(80, 160, 80, 0.2); color: var(--status-success); }
.badge-partial { background: rgba(160, 128, 80, 0.2); color: var(--status-warning); }
.badge-failed { background: rgba(160, 80, 80, 0.2); color: var(--status-error); }
.badge-published { background: rgba(122, 200, 247, 0.2); color: #7ac8f7; }
</style>
