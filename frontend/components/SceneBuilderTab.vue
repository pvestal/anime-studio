<template>
  <div>
    <h2 style="font-size: 18px; font-weight: 500; margin-bottom: 16px;">Scene Builder</h2>
    <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 24px;">
      Compose shots into scenes with automatic continuity chaining and FramePack video generation.
    </p>

    <!-- Project selector -->
    <div style="display: flex; gap: 16px; margin-bottom: 24px; align-items: flex-end;">
      <div style="min-width: 260px;">
        <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Project</label>
        <select v-model="selectedProjectId" style="width: 100%;">
          <option :value="0">Select a project...</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </div>
      <button v-if="selectedProjectId" class="btn btn-primary" @click="openNewScene">+ New Scene</button>
      <button
        v-if="selectedProjectId && scenes.length > 0"
        class="btn"
        :disabled="generatingTraining"
        @click="generateTrainingFromScenes"
        title="Generate LoRA training images with poses matching your scene descriptions"
      >{{ generatingTraining ? 'Generating...' : 'Train for Scenes' }}</button>
    </div>

    <!-- Sub-view toggle (Scenes / Episodes) — hidden when episodes extracted to Publish tab -->
    <div v-if="currentView === 'library' && selectedProjectId && !hideEpisodes" style="display: flex; gap: 4px; margin-bottom: 16px;">
      <button
        :class="['btn', librarySubView === 'scenes' ? 'btn-primary' : '']"
        style="font-size: 12px; padding: 4px 14px;"
        @click="librarySubView = 'scenes'"
      >Scenes</button>
      <button
        :class="['btn', librarySubView === 'episodes' ? 'btn-primary' : '']"
        style="font-size: 12px; padding: 4px 14px;"
        @click="librarySubView = 'episodes'"
      >Episodes</button>
    </div>

    <!-- VIEW 1a: Scene Library -->
    <SceneLibraryView
      v-if="currentView === 'library' && librarySubView === 'scenes'"
      :scenes="scenes"
      :loading="loading"
      :has-project="!!selectedProjectId"
      :generating-from-story="generatingFromStory"
      :gap-by-scene-id="gapBySceneId"
      @edit="openEditor"
      @monitor="openMonitor"
      @play="playSceneVideo"
      @delete="deleteScene"
      @generate-from-story="generateFromStory"
    />

    <!-- VIEW 1b: Episodes -->
    <EpisodeView
      v-if="currentView === 'library' && librarySubView === 'episodes'"
      :project-id="selectedProjectId"
      :scenes="scenes"
      @play-episode="playEpisodeVideo"
    />

    <!-- VIEW 2: Scene Editor -->
    <SceneEditorView
      v-if="currentView === 'editor'"
      :scene="editScene"
      :scene-id="editSceneId"
      :shots="editShots"
      :selected-shot-idx="selectedShotIdx"
      :saving="saving"
      :generating="generating"
      :shot-video-src="currentShotVideoSrc"
      :source-image-url="sourceImageUrl"
      :characters="projectCharacters"
      :gap-characters="gapByCharSlug"
      @save="saveScene"
      @confirm-generate="confirmGenerate"
      @back="backToLibrary"
      @select-shot="selectShot"
      @add-shot="addShot"
      @remove-shot="removeShot"
      @browse-image="openImagePicker"
      @auto-assign="autoAssignAll"
      @update-shot-field="updateShotField"
      @update-scene="onUpdateScene"
      @audio-changed="onAudioChanged"
      @go-to-training="goToTraining"
    />

    <!-- VIEW 3: Generation Monitor -->
    <GenerationMonitorView
      v-if="currentView === 'monitor'"
      :scene-title="editScene.title || ''"
      :monitor-status="monitorStatus"
      :scene-video-src="sceneVideoSrc"
      @back="backToLibrary"
      @retry-shot="retryShot"
      @play-shot="playShotVideo"
      @reassemble="reassemble"
    />

    <!-- Image Picker Modal -->
    <ImagePickerModal
      :visible="showImagePicker"
      :loading="loadingImages"
      :approved-images="approvedImages"
      :image-url="imageUrl"
      :characters-present="currentShotCharacters"
      :recommendations="currentShotRecommendations"
      :current-shot-type="currentShotType"
      @close="showImagePicker = false"
      @select="selectImage"
    />

    <!-- Video Player Modal -->
    <div v-if="showVideoPlayer" style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center;" @click.self="showVideoPlayer = false" @keydown.escape.window="showVideoPlayer = false">
      <div style="max-width: 90vw; max-height: 90vh;">
        <video :src="videoPlayerSrc" controls autoplay style="max-width: 100%; max-height: 85vh; border-radius: 4px;"></video>
        <div style="text-align: center; margin-top: 8px;">
          <button class="btn" @click="showVideoPlayer = false">Close</button>
        </div>
      </div>
    </div>

    <!-- Generate Confirmation -->
    <div v-if="showGenerateConfirm" style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center;" @click.self="showGenerateConfirm = false" @keydown.escape.window="showGenerateConfirm = false">
      <div class="card" style="width: 400px;">
        <div style="font-size: 14px; font-weight: 500; margin-bottom: 12px;">Start Scene Generation?</div>
        <div style="font-size: 13px; color: var(--text-secondary); margin-bottom: 16px;">
          This will generate {{ editShots.length }} shot{{ editShots.length !== 1 ? 's' : '' }} sequentially with
          FramePack. Each shot's last frame becomes the next shot's first frame for continuity.
        </div>
        <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 16px;">
          Estimated time: ~{{ estimateMinutes(editShots) }} minutes
        </div>
        <div v-if="generationUnreadyChars.length > 0" style="border-left: 3px solid var(--status-warning); background: rgba(160, 128, 80, 0.1); padding: 10px 12px; margin-bottom: 16px; border-radius: 0 4px 4px 0;">
          <div style="font-size: 12px; font-weight: 500; color: var(--status-warning); margin-bottom: 6px;">Characters without LoRA</div>
          <div v-for="c in generationUnreadyChars" :key="c.slug" style="font-size: 12px; color: var(--text-secondary); margin-bottom: 2px;">
            {{ c.name }} — {{ c.reason }}
          </div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 6px;">
            FramePack doesn't use LoRAs directly, but source image quality depends on training data.
          </div>
        </div>
        <div style="display: flex; gap: 8px; justify-content: flex-end;">
          <button class="btn" @click="showGenerateConfirm = false">Cancel</button>
          <button class="btn btn-success" @click="startGeneration">Generate</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import { trainingApi } from '@/api/training'
import { useProjectStore } from '@/stores/project'
import type { BuilderScene, BuilderShot, SceneGenerationStatus, SceneAudio, ShotRecommendation, ShotRecommendations, ImageWithMetadata, GapAnalysisResponse, GapAnalysisScene, GapAnalysisCharacter } from '@/types'
import SceneLibraryView from './scenes/SceneLibraryView.vue'
import SceneEditorView from './scenes/SceneEditorView.vue'
import GenerationMonitorView from './scenes/GenerationMonitorView.vue'
import ImagePickerModal from './scenes/ImagePickerModal.vue'
import EpisodeView from './scenes/EpisodeView.vue'

const props = withDefaults(defineProps<{
  hideEpisodes?: boolean
}>(), {
  hideEpisodes: false,
})

const router = useRouter()
const projectStore = useProjectStore()

const projects = ref<Array<{ id: number; name: string }>>([])
const selectedProjectId = ref(0)
const scenes = ref<BuilderScene[]>([])
const loading = ref(false)
const saving = ref(false)
const generating = ref(false)
const currentView = ref<'library' | 'editor' | 'monitor'>('library')
const librarySubView = ref<'scenes' | 'episodes'>('scenes')
const editScene = ref<Partial<BuilderScene>>({})
const editShots = ref<Partial<BuilderShot>[]>([])
const selectedShotIdx = ref(-1)
const editSceneId = ref<string | null>(null)
const monitorStatus = ref<SceneGenerationStatus | null>(null)
let monitorInterval: ReturnType<typeof setInterval> | null = null
const showImagePicker = ref(false)
const loadingImages = ref(false)
const approvedImages = ref<Record<string, { character_name: string; images: (string | ImageWithMetadata)[] }>>({})
const showVideoPlayer = ref(false)
const videoPlayerSrc = ref('')
const showGenerateConfirm = ref(false)
const generatingFromStory = ref(false)
const shotRecommendations = ref<ShotRecommendations[]>([])
const autoAssigning = ref(false)
const generatingTraining = ref(false)
const gapAnalysis = ref<GapAnalysisResponse | null>(null)

const selectedProjectName = computed(() => {
  const p = projects.value.find(p => p.id === selectedProjectId.value)
  return p?.name || ''
})

const gapBySceneId = computed((): Record<string, GapAnalysisScene> => {
  if (!gapAnalysis.value) return {}
  const map: Record<string, GapAnalysisScene> = {}
  for (const s of gapAnalysis.value.scenes) {
    map[s.id] = s
  }
  return map
})

const gapByCharSlug = computed((): Record<string, GapAnalysisCharacter> => {
  if (!gapAnalysis.value) return {}
  const map: Record<string, GapAnalysisCharacter> = {}
  for (const c of gapAnalysis.value.characters) {
    map[c.slug] = c
  }
  return map
})

const generationUnreadyChars = computed((): Array<{ slug: string; name: string; reason: string }> => {
  if (!gapAnalysis.value) return []
  const slugsSeen = new Set<string>()
  const result: Array<{ slug: string; name: string; reason: string }> = []
  for (const shot of editShots.value) {
    const chars = (shot.characters_present as string[]) || []
    for (const slug of chars) {
      if (slugsSeen.has(slug)) continue
      slugsSeen.add(slug)
      const gc = gapByCharSlug.value[slug]
      if (gc && !gc.has_lora) {
        const reason = gc.approved_count < 10
          ? `${gc.approved_count} images (need 10+)`
          : 'LoRA not yet trained'
        result.push({ slug, name: gc.name, reason })
      }
    }
  }
  return result
})

async function loadGapAnalysis() {
  if (!selectedProjectName.value) return
  try {
    gapAnalysis.value = await trainingApi.getGapAnalysis(selectedProjectName.value)
  } catch (e) {
    console.error('Gap analysis load failed (non-blocking):', e)
    gapAnalysis.value = null
  }
}

function goToTraining() {
  router.push('/train')
}

async function generateTrainingFromScenes() {
  if (!selectedProjectName.value) return
  generatingTraining.value = true
  try {
    const result = await trainingApi.generateForScenes(selectedProjectName.value, 3)
    alert(`${result.message}\n\nPer character:\n${Object.entries(result.per_character).map(([k, v]) => `  ${k}: ${v} images`).join('\n')}`)
    // Refresh gap analysis after generation starts
    loadGapAnalysis()
  } catch (e) {
    console.error('Scene training generation failed:', e)
    alert(`Failed: ${e}`)
  } finally {
    generatingTraining.value = false
  }
}

const currentShotCharacters = computed(() => {
  if (selectedShotIdx.value < 0) return []
  const shot = editShots.value[selectedShotIdx.value]
  return (shot?.characters_present as string[]) || []
})

const currentShotRecommendations = computed((): ShotRecommendation[] => {
  if (selectedShotIdx.value < 0) return []
  const shot = editShots.value[selectedShotIdx.value]
  if (!shot?.id) return []
  const match = shotRecommendations.value.find(r => r.shot_id === shot.id)
  return match?.recommendations || []
})

const currentShotType = computed((): string | undefined => {
  if (selectedShotIdx.value < 0) return undefined
  return editShots.value[selectedShotIdx.value]?.shot_type || undefined
})

const projectCharacters = computed(() => {
  return Object.entries(approvedImages.value).map(([slug, data]) => ({
    slug,
    name: data.character_name,
  }))
})

const sceneVideoSrc = computed(() => {
  if (!editSceneId.value) return ''
  return api.sceneVideoUrl(editSceneId.value)
})

const currentShotVideoSrc = computed(() => {
  if (selectedShotIdx.value < 0) return ''
  const shot = editShots.value[selectedShotIdx.value]
  if (!shot || !editSceneId.value || !shot.id) return ''
  return api.shotVideoUrl(editSceneId.value, shot.id)
})

async function loadProjects() {
  try {
    const data = await api.getProjects()
    projects.value = data.projects
  } catch (e) {
    console.error('Failed to load projects:', e)
  }
}
loadProjects()

watch(selectedProjectId, async (pid) => {
  if (!pid) {
    scenes.value = []
    gapAnalysis.value = null
    return
  }
  await loadScenes()
  loadGapAnalysis()
  projectStore.fetchProjectDetail(pid)
})

async function loadScenes() {
  if (!selectedProjectId.value) return
  loading.value = true
  try {
    const data = await api.listScenes(selectedProjectId.value)
    scenes.value = data.scenes
  } catch (e) {
    console.error('Failed to load scenes:', e)
  } finally {
    loading.value = false
  }
}

function backToLibrary() {
  currentView.value = 'library'
  editSceneId.value = null
  stopMonitorPolling()
  loadScenes()
}

function openNewScene() {
  const ws = projectStore.worldSettings
  editScene.value = {
    title: `Scene ${scenes.value.length + 1}`,
    description: '',
    location: ws?.world_location?.primary || '',
    time_of_day: '',
    weather: '',
    mood: '',
    target_duration_seconds: 30,
  }
  editShots.value = []
  editSceneId.value = null
  selectedShotIdx.value = -1
  currentView.value = 'editor'
}

async function openEditor(scene: BuilderScene) {
  try {
    const full = await api.getScene(scene.id)
    editScene.value = { ...full }
    editShots.value = (full.shots || []).map(s => ({ ...s }))
    editSceneId.value = scene.id
    selectedShotIdx.value = editShots.value.length > 0 ? 0 : -1
    currentView.value = 'editor'
    // Pre-load approved images for character list (dialogue dropdown)
    loadApprovedImagesBackground()
    loadRecommendations()
  } catch (e) {
    console.error('Failed to load scene:', e)
  }
}

async function loadApprovedImagesBackground() {
  try {
    const data = await api.getApprovedImagesForScene(
      editSceneId.value || 'new',
      selectedProjectId.value,
    )
    approvedImages.value = data.characters
  } catch (e) {
    console.error('Failed to pre-load approved images:', e)
  }
}

async function loadRecommendations() {
  if (!editSceneId.value) return
  try {
    const data = await api.getShotRecommendations(editSceneId.value, 5)
    shotRecommendations.value = data.shots
  } catch (e) {
    console.error('Failed to load recommendations:', e)
    shotRecommendations.value = []
  }
}

async function autoAssignAll() {
  if (!editSceneId.value) return
  autoAssigning.value = true
  try {
    // Ensure recommendations are loaded
    if (shotRecommendations.value.length === 0) {
      await loadRecommendations()
    }
    let assigned = 0
    for (let i = 0; i < editShots.value.length; i++) {
      const shot = editShots.value[i]
      if (shot.source_image_path) continue // already assigned
      const match = shotRecommendations.value.find(r => r.shot_id === shot.id)
      if (match && match.recommendations.length > 0) {
        const best = match.recommendations[0]
        shot.source_image_path = `${best.slug}/images/${best.image_name}`
        assigned++
      }
    }
    if (assigned > 0) {
      await saveScene()
    }
  } catch (e) {
    console.error('Auto-assign failed:', e)
  } finally {
    autoAssigning.value = false
  }
}

function openMonitor(scene: BuilderScene) {
  editScene.value = { ...scene }
  editSceneId.value = scene.id
  currentView.value = 'monitor'
  startMonitorPolling()
}

function onUpdateScene(scene: Partial<BuilderScene>) {
  editScene.value = scene
}

function onAudioChanged(audio: SceneAudio | null) {
  editScene.value = { ...editScene.value, audio }
}

async function saveScene() {
  saving.value = true
  try {
    if (editSceneId.value) {
      // Update existing
      await api.updateScene(editSceneId.value, {
        title: editScene.value.title,
        description: editScene.value.description,
        location: editScene.value.location,
        time_of_day: editScene.value.time_of_day,
        weather: editScene.value.weather,
        mood: editScene.value.mood,
        target_duration_seconds: editScene.value.target_duration_seconds,
      })
      // Save shots
      for (const shot of editShots.value) {
        if (shot.id) {
          await api.updateShot(editSceneId.value, shot.id, {
            shot_number: shot.shot_number,
            source_image_path: shot.source_image_path || '',
            shot_type: shot.shot_type,
            camera_angle: shot.camera_angle,
            duration_seconds: shot.duration_seconds,
            motion_prompt: shot.motion_prompt || '',
            seed: shot.seed ?? undefined,
            steps: shot.steps ?? undefined,
            use_f1: shot.use_f1,
            dialogue_text: shot.dialogue_text ?? undefined,
            dialogue_character_slug: shot.dialogue_character_slug ?? undefined,
          })
        } else {
          const result = await api.createShot(editSceneId.value, {
            shot_number: shot.shot_number || 1,
            source_image_path: shot.source_image_path || '',
            shot_type: shot.shot_type || 'medium',
            camera_angle: shot.camera_angle || 'eye-level',
            duration_seconds: shot.duration_seconds || 3,
            motion_prompt: shot.motion_prompt || '',
            seed: shot.seed ?? undefined,
            steps: shot.steps ?? undefined,
            use_f1: shot.use_f1 || false,
            dialogue_text: shot.dialogue_text ?? undefined,
            dialogue_character_slug: shot.dialogue_character_slug ?? undefined,
          })
          shot.id = result.id
        }
      }
    } else {
      // Create new scene
      const result = await api.createScene({
        project_id: selectedProjectId.value,
        title: editScene.value.title || 'Untitled Scene',
        description: editScene.value.description,
        location: editScene.value.location,
        time_of_day: editScene.value.time_of_day,
        weather: editScene.value.weather,
        mood: editScene.value.mood,
        target_duration_seconds: editScene.value.target_duration_seconds || 30,
      })
      editSceneId.value = result.id
      // Now save shots
      for (const shot of editShots.value) {
        const shotResult = await api.createShot(editSceneId.value, {
          shot_number: shot.shot_number || 1,
          source_image_path: shot.source_image_path || '',
          shot_type: shot.shot_type || 'medium',
          camera_angle: shot.camera_angle || 'eye-level',
          duration_seconds: shot.duration_seconds || 3,
          motion_prompt: shot.motion_prompt || '',
          seed: shot.seed ?? undefined,
          steps: shot.steps ?? undefined,
          use_f1: shot.use_f1 || false,
          dialogue_text: shot.dialogue_text ?? undefined,
          dialogue_character_slug: shot.dialogue_character_slug ?? undefined,
        })
        shot.id = shotResult.id
      }
    }
  } catch (e) {
    console.error('Save failed:', e)
  } finally {
    saving.value = false
  }
}

async function deleteScene(scene: BuilderScene) {
  if (!confirm(`Delete scene "${scene.title}"?`)) return
  try {
    await api.deleteScene(scene.id)
    await loadScenes()
  } catch (e) {
    console.error('Delete failed:', e)
  }
}

function addShot() {
  const nextNum = editShots.value.length + 1
  const newShot: Partial<BuilderShot> = {
    shot_number: nextNum,
    shot_type: 'medium',
    camera_angle: 'eye-level',
    duration_seconds: 3,
    motion_prompt: '',
    source_image_path: '',
    status: 'pending',
    use_f1: false,
    seed: null,
    steps: null,
  }
  editShots.value.push(newShot)
  selectedShotIdx.value = editShots.value.length - 1
}

function selectShot(idx: number) {
  selectedShotIdx.value = idx
}

function updateShotField(idx: number, field: string, value: unknown) {
  if (idx >= 0 && idx < editShots.value.length) {
    ;(editShots.value[idx] as Record<string, unknown>)[field] = value
  }
}

async function removeShot(idx: number) {
  const shot = editShots.value[idx]
  if (shot.id && editSceneId.value) {
    try {
      await api.deleteShot(editSceneId.value, shot.id)
    } catch (e) {
      console.error('Failed to delete shot:', e)
    }
  }
  editShots.value.splice(idx, 1)
  // Renumber
  editShots.value.forEach((s, i) => { s.shot_number = i + 1 })
  if (selectedShotIdx.value >= editShots.value.length) {
    selectedShotIdx.value = editShots.value.length - 1
  }
}

async function openImagePicker() {
  showImagePicker.value = true
  loadingImages.value = true
  try {
    // Try metadata-enriched images first, fall back to plain
    const sceneRef = editSceneId.value || 'new'
    let data
    try {
      data = await api.getApprovedImagesWithMetadata(sceneRef, selectedProjectId.value)
    } catch {
      data = await api.getApprovedImagesForScene(sceneRef, selectedProjectId.value)
    }
    approvedImages.value = data.characters
    // Load recommendations if scene is saved
    if (editSceneId.value) {
      loadRecommendations()
    }
  } catch (e) {
    console.error('Failed to load approved images:', e)
  } finally {
    loadingImages.value = false
  }
}

function selectImage(slug: string, imageName: string) {
  if (selectedShotIdx.value >= 0) {
    editShots.value[selectedShotIdx.value].source_image_path = `${slug}/images/${imageName}`
  }
  showImagePicker.value = false
}

function imageUrl(slug: string, imageName: string): string {
  return api.imageUrl(slug, imageName)
}

function sourceImageUrl(path: string): string {
  // path format: "slug/images/filename.png"
  const parts = path.split('/')
  if (parts.length >= 3) {
    return api.imageUrl(parts[0], parts[parts.length - 1])
  }
  return ''
}

function confirmGenerate() {
  showGenerateConfirm.value = true
}

async function startGeneration() {
  showGenerateConfirm.value = false
  if (!editSceneId.value) {
    // Save first
    await saveScene()
    if (!editSceneId.value) return
  } else {
    await saveScene()
  }

  generating.value = true
  try {
    await api.generateScene(editSceneId.value)
    currentView.value = 'monitor'
    startMonitorPolling()
  } catch (e) {
    console.error('Generation failed:', e)
  } finally {
    generating.value = false
  }
}

function startMonitorPolling() {
  stopMonitorPolling()
  pollStatus()
  monitorInterval = setInterval(pollStatus, 5000)
}

function stopMonitorPolling() {
  if (monitorInterval) {
    clearInterval(monitorInterval)
    monitorInterval = null
  }
}

async function pollStatus() {
  if (!editSceneId.value) return
  try {
    monitorStatus.value = await api.getSceneStatus(editSceneId.value)
    // Stop polling if generation is done
    if (monitorStatus.value.generation_status !== 'generating') {
      stopMonitorPolling()
    }
  } catch (e) {
    console.error('Status poll failed:', e)
  }
}

async function retryShot(shot: { id: string }) {
  if (!editSceneId.value) return
  try {
    await api.regenerateShot(editSceneId.value, shot.id)
    startMonitorPolling()
  } catch (e) {
    console.error('Retry failed:', e)
  }
}

async function reassemble() {
  if (!editSceneId.value) return
  try {
    await api.assembleScene(editSceneId.value)
    await pollStatus()
  } catch (e) {
    console.error('Assemble failed:', e)
  }
}

function playSceneVideo(scene: BuilderScene) {
  videoPlayerSrc.value = api.sceneVideoUrl(scene.id)
  showVideoPlayer.value = true
}

async function generateFromStory() {
  if (!selectedProjectId.value) return
  generatingFromStory.value = true
  try {
    // Backend persists scenes + shots to DB — just reload after
    const data = await api.generateScenesFromStory(selectedProjectId.value)
    await loadScenes()
    alert(`Created ${data.count} scenes from story! Open each scene to assign source images.`)
  } catch (e) {
    console.error('Story-to-scenes failed:', e)
    alert(`Failed to generate scenes: ${e}`)
  } finally {
    generatingFromStory.value = false
  }
}

function playEpisodeVideo(ep: { id: string }) {
  videoPlayerSrc.value = api.episodeVideoUrl(ep.id)
  showVideoPlayer.value = true
}

function playShotVideo(shot: { id: string }) {
  if (!editSceneId.value) return
  videoPlayerSrc.value = api.shotVideoUrl(editSceneId.value, shot.id)
  showVideoPlayer.value = true
}

function estimateMinutes(shots: Partial<BuilderShot>[]): number {
  return shots.reduce((sum, s) => {
    const dur = s.duration_seconds || 3
    if (dur <= 2) return sum + 20
    if (dur <= 3) return sum + 13
    if (dur <= 5) return sum + 25
    return sum + 30
  }, 0)
}

onUnmounted(() => {
  stopMonitorPolling()
})
</script>
