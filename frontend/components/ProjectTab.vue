<template>
  <div class="project-tab">

    <!-- Project Carousel -->
    <div class="carousel-container" @keydown="handleCarouselKey">
      <!-- Prev arrow -->
      <button
        class="nav-arrow nav-prev"
        :disabled="currentSlide === 0"
        @click="goToSlide(currentSlide - 1)"
      >&#8249;</button>

      <!-- Slide viewport -->
      <div class="carousel-viewport">
        <div
          class="carousel-track"
          :style="{ transform: `translateX(-${currentSlide * 100}%)` }"
        >
          <!-- Project tiles -->
          <div
            v-for="p in projectCards"
            :key="p.id"
            class="carousel-slide"
          >
            <div
              :class="['project-tile', { selected: selectedProjectId === p.id }]"
              @click="selectProject(p.id)"
            >
              <div class="tile-top-row">
                <div class="tile-header">
                  <h3 class="tile-name">{{ p.name }}</h3>
                  <div class="tile-meta">
                    <span v-if="p.genre" class="tile-genre">{{ p.genre }}</span>
                    <span v-if="p.checkpoint" class="tile-checkpoint">{{ p.checkpoint }}</span>
                  </div>
                </div>
                <button
                  class="tile-edit-btn"
                  title="Edit project"
                  @click.stop="editProjectInline(p.id)"
                >&#9998;</button>
              </div>

              <!-- Description preview -->
              <p v-if="p.description" class="tile-description">{{ p.description }}</p>

              <!-- Stats row -->
              <div class="tile-stats">
                <span class="tile-stat">
                  <span class="tile-stat-val">{{ p.character_count }}</span>
                  <span class="tile-stat-lbl">Characters</span>
                </span>
                <span class="tile-stat">
                  <span class="tile-stat-val" :style="{ color: p.trainedCount > 0 ? 'var(--status-success)' : 'var(--text-muted)' }">{{ p.trainedCount }}</span>
                  <span class="tile-stat-lbl">LoRAs</span>
                </span>
                <span class="tile-stat">
                  <span class="tile-stat-val">{{ p.approvedCount }}</span>
                  <span class="tile-stat-lbl">Approved</span>
                </span>
              </div>

              <!-- LoRA Carousel -->
              <div v-if="p.loras.length > 0" class="lora-section">
                <div class="lora-section-label">Characters &amp; LoRAs</div>
                <div class="lora-carousel-wrapper">
                  <button
                    v-if="p.loras.length > 5"
                    class="lora-arrow lora-arrow-left"
                    @click.stop="scrollLoraCarousel(p.id, -1)"
                  >&#8249;</button>
                  <div class="lora-carousel" :ref="el => setCarouselRef(p.id, el)">
                    <div
                      v-for="lora in p.loras"
                      :key="lora.slug"
                      :class="['lora-chip', lora.trained ? 'lora-trained' : 'lora-untrained']"
                      :title="lora.trained ? `${lora.filename} (${lora.size_mb} MB)` : 'Not trained'"
                    >
                      <div class="lora-thumb-wrapper">
                        <img
                          v-if="lora.thumbnail"
                          :src="lora.thumbnail"
                          class="lora-thumb"
                          loading="lazy"
                          alt=""
                        />
                        <span v-else class="lora-thumb-placeholder">{{ lora.name.charAt(0) }}</span>
                        <span class="lora-status-dot" :class="lora.trained ? 'dot-green' : 'dot-grey'"></span>
                      </div>
                      <span class="lora-name">{{ lora.name }}</span>
                    </div>
                  </div>
                  <button
                    v-if="p.loras.length > 5"
                    class="lora-arrow lora-arrow-right"
                    @click.stop="scrollLoraCarousel(p.id, 1)"
                  >&#8249;</button>
                </div>
              </div>
              <div v-else class="lora-section">
                <div class="lora-empty">No characters yet</div>
              </div>
            </div>
          </div>

          <!-- Add New Project slide -->
          <div class="carousel-slide">
            <div class="project-tile add-tile" @click="showNewForm = true">
              <div class="add-icon">+</div>
              <div class="add-label">New Project</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Next arrow -->
      <button
        class="nav-arrow nav-next"
        :disabled="currentSlide >= totalSlides - 1"
        @click="goToSlide(currentSlide + 1)"
      >&#8250;</button>
    </div>

    <!-- Dot indicators + counter -->
    <div class="carousel-indicators">
      <button
        v-for="(_, idx) in totalSlides"
        :key="idx"
        :class="['indicator-dot', { active: idx === currentSlide }]"
        @click="goToSlide(idx)"
      ></button>
      <span class="slide-counter">{{ currentSlide + 1 }} / {{ totalSlides }}</span>
    </div>

    <!-- New Project Form -->
    <NewProjectForm
      v-if="showNewForm"
      ref="newFormRef"
      :checkpoints="projectStore.checkpoints"
      :saving="projectStore.saving"
      @create="handleCreateProject"
      @cancel="showNewForm = false"
    />

    <!-- Project Detail (only when a project is selected) -->
    <template v-if="projectStore.currentProject && !showNewForm">

      <!-- Section 1: Project Basics + Generation Style (two-column) -->
      <div class="two-column">

        <!-- Left: Project Details -->
        <div class="card">
          <h4 class="section-heading">Project Basics</h4>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
            <div>
              <label class="field-label">Name</label>
              <input v-model="editProject.name" type="text" class="field-input" />
            </div>
            <div>
              <label class="field-label">Genre</label>
              <input v-model="editProject.genre" type="text" class="field-input" />
            </div>
          </div>
          <div style="margin-bottom: 10px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
              <label class="field-label" style="margin-bottom: 0;">Description</label>
              <EchoAssistButton
                context-type="description"
                :context-payload="echoContext"
                :current-value="editProject.description"
                compact
                @accept="editProject.description = $event.suggestion"
              />
            </div>
            <textarea v-model="editProject.description" rows="2" class="field-input" style="width: 100%; resize: vertical;"></textarea>
          </div>
          <div style="margin-bottom: 10px;">
            <label class="field-label">Premise</label>
            <textarea v-model="editProject.premise" rows="3" placeholder="The overall premise or logline of the project..." class="field-input" style="width: 100%; resize: vertical;"></textarea>
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
            <div>
              <label class="field-label">Content Rating</label>
              <input v-model="editProject.content_rating" type="text" placeholder="e.g. PG, PG-13, R" class="field-input" />
            </div>
          </div>
          <button
            :class="['btn', detailsSaved ? 'btn-saved' : 'btn-primary']"
            style="font-size: 12px; padding: 4px 12px; transition: all 200ms ease;"
            @click="handleUpdateProject"
            :disabled="projectStore.saving || !detailsDirty"
          >
            {{ detailsSaved ? 'Saved' : projectStore.saving ? 'Saving...' : 'Save Details' }}
          </button>
          <span v-if="!detailsDirty && !detailsSaved" style="font-size: 11px; color: var(--text-muted); margin-left: 8px;">no changes</span>
        </div>

        <!-- Right: Generation Style -->
        <GenerationStylePanel
          :style-prop="projectStore.currentProject.style"
          :checkpoints="projectStore.checkpoints"
          :saving="projectStore.saving"
          :echo-context="echoContext"
          :project-id="projectStore.currentProject.id"
          @save="handleUpdateStyle"
        />

      </div>

      <!-- Section 2: Storyline (collapsible) -->
      <div class="collapsible-section" style="margin-bottom: 20px;">
        <button class="collapsible-header" @click="storylineOpen = !storylineOpen">
          <span class="section-heading" style="margin: 0;">Storyline</span>
          <span class="collapse-indicator" :class="{ open: storylineOpen }">&#9654;</span>
        </button>
        <div v-if="storylineOpen" style="padding-top: 16px;">
          <StorylinePanel
            :sl="sl"
            :storyline-echo-payload="storylineEchoPayload"
            :dirty="storylineDirty"
            :saved="storylineSaved"
            :saving="projectStore.saving"
            @save="handleSaveStoryline"
          />
        </div>
      </div>

      <!-- Section 3: World & Art Direction (collapsible) -->
      <div class="collapsible-section" style="margin-bottom: 20px;">
        <button class="collapsible-header" @click="worldOpen = !worldOpen">
          <span class="section-heading" style="margin: 0;">World &amp; Art Direction</span>
          <span class="collapse-indicator" :class="{ open: worldOpen }">&#9654;</span>
        </button>
        <div v-if="worldOpen" style="padding-top: 16px;">
          <WorldSettingsPanel
            :ws="ws"
            :preamble-echo-payload="preambleEchoPayload"
            :production-notes-echo-payload="productionNotesEchoPayload"
            :dirty="worldDirty"
            :saved="worldSaved"
            :saving="projectStore.saving"
            @save="handleSaveWorld"
          />
        </div>
      </div>

      <!-- Quick stats bar -->
      <div class="card stats-bar">
        <RouterLink to="/characters" class="stat-item stat-link">
          <span class="stat-value">{{ characterCount }}</span>
          <span class="stat-label">Characters</span>
        </RouterLink>
        <RouterLink to="/review" class="stat-item stat-link">
          <span class="stat-value">{{ approvedImageCount }}</span>
          <span class="stat-label">Approved Images</span>
        </RouterLink>
        <RouterLink to="/train" class="stat-item stat-link">
          <span class="stat-value" :style="{ color: trainingReady ? 'var(--status-success)' : 'var(--status-warning)' }">
            {{ trainingReady ? 'Ready' : 'Not Ready' }}
          </span>
          <span class="stat-label">Training Readiness</span>
        </RouterLink>
      </div>

    </template>

    <!-- Loading state -->
    <div v-if="projectStore.loading && !projectStore.currentProject" style="text-align: center; padding: 20px; color: var(--text-muted); font-size: 13px;">
      Loading project...
    </div>

    <!-- Error -->
    <div v-if="projectStore.error" style="margin-top: 12px; padding: 8px 12px; background: rgba(160,80,80,0.1); border: 1px solid var(--status-error); border-radius: 3px;">
      <p style="color: var(--status-error); font-size: 12px; margin: 0;">{{ projectStore.error }}</p>
      <button class="btn" style="font-size: 11px; padding: 2px 8px; margin-top: 4px;" @click="projectStore.clearError()">Dismiss</button>
    </div>

    <!-- Save success feedback -->
    <div v-if="saveMessage" style="margin-top: 12px; font-size: 12px; color: var(--status-success);">
      {{ saveMessage }}
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useProjectStore } from '@/stores/project'
import { useCharactersStore } from '@/stores/characters'
import { useTrainingStore } from '@/stores/training'
import type { ProjectCreate, ProjectUpdate, StyleUpdate, StorylineUpsert, WorldSettingsUpsert } from '@/types'
import { api } from '@/api/client'
import EchoAssistButton from './EchoAssistButton.vue'
import NewProjectForm from './project/NewProjectForm.vue'
import GenerationStylePanel from './project/GenerationStylePanel.vue'
import StorylinePanel from './story/StorylinePanel.vue'
import WorldSettingsPanel from './story/WorldSettingsPanel.vue'
import { RouterLink } from 'vue-router'

const emit = defineEmits<{
  'project-selected': [projectId: number, projectName: string]
}>()

const projectStore = useProjectStore()
const charactersStore = useCharactersStore()
const trainingStore = useTrainingStore()

const showNewForm = ref(false)
const newFormRef = ref<InstanceType<typeof NewProjectForm> | null>(null)
const selectedProjectId = ref(0)
const saveMessage = ref('')

// Collapsible section state
const storylineOpen = ref(false)
const worldOpen = ref(false)

// --- Project carousel state ---
const currentSlide = ref(0)
const totalSlides = computed(() => projectStore.projects.length + 1) // +1 for "add" tile

function goToSlide(idx: number) {
  if (idx < 0 || idx >= totalSlides.value) return
  currentSlide.value = idx
}

function handleCarouselKey(e: KeyboardEvent) {
  if (e.key === 'ArrowLeft') goToSlide(currentSlide.value - 1)
  else if (e.key === 'ArrowRight') goToSlide(currentSlide.value + 1)
}

// LoRA carousel refs (inner horizontal scroll within each tile)
const loraCarouselRefs = new Map<number, HTMLElement>()

function setCarouselRef(projectId: number, el: unknown) {
  if (el instanceof HTMLElement) {
    loraCarouselRefs.set(projectId, el)
  }
}

function scrollLoraCarousel(projectId: number, direction: number) {
  const el = loraCarouselRefs.get(projectId)
  if (el) {
    el.scrollBy({ left: direction * 180, behavior: 'smooth' })
  }
}

// Cache of fetched project details for tile display
const projectDetailCache = ref<Map<number, { genre: string; checkpoint: string; description: string }>>(new Map())

async function fetchAllProjectDetails() {
  for (const p of projectStore.projects) {
    if (projectDetailCache.value.has(p.id)) continue
    try {
      const resp = await api.getProjectDetail(p.id)
      const proj = resp.project
      projectDetailCache.value.set(p.id, {
        genre: proj.genre || '',
        checkpoint: proj.style?.checkpoint_model?.replace('.safetensors', '').replace('_fp16', '') || '',
        description: proj.description || '',
      })
    } catch {
      projectDetailCache.value.set(p.id, { genre: '', checkpoint: '', description: '' })
    }
  }
}

// Build enriched project cards with LoRA info
const projectCards = computed(() => {
  return projectStore.projects.map(p => {
    const projectChars = charactersStore.characters.filter(c => c.project_name === p.name)
    const loraSet = new Set(trainingStore.loras.map(l => l.slug))

    const loras = projectChars.map(c => {
      const slug = c.slug || c.name
      const trained = loraSet.has(slug)
      const loraFile = trained ? trainingStore.loras.find(l => l.slug === slug) : null
      // Pick first approved image as thumbnail
      const dataset = charactersStore.datasets.get(slug) || []
      const firstApproved = dataset.find(img => img.status === 'approved')
      const thumbnail = firstApproved ? api.imageUrl(slug, firstApproved.name) : ''
      return {
        slug,
        name: c.name,
        trained,
        filename: loraFile?.filename || '',
        size_mb: loraFile?.size_mb || 0,
        thumbnail,
      }
    })

    const trainedCount = loras.filter(l => l.trained).length

    let approvedCount = 0
    for (const c of projectChars) {
      const stats = charactersStore.getCharacterStats(c.slug || c.name)
      approvedCount += stats.approved
    }

    const cached = projectDetailCache.value.get(p.id)
    const genre = cached?.genre || ''
    const checkpoint = cached?.checkpoint || ''
    const description = cached?.description || ''

    return {
      id: p.id,
      name: p.name,
      genre,
      description,
      character_count: p.character_count,
      checkpoint,
      loras,
      trainedCount,
      approvedCount,
    }
  })
})

// Select project
async function selectProject(projectId: number) {
  if (selectedProjectId.value === projectId) return
  selectedProjectId.value = projectId
  showNewForm.value = false
  await projectStore.fetchProjectDetail(projectId)
  const proj = projectStore.projects.find(p => p.id === projectId)
  if (proj) {
    emit('project-selected', proj.id, proj.name)
  }
}

// Edit shortcut — select + scroll to detail
function editProjectInline(projectId: number) {
  selectProject(projectId)
}

// Edit forms (populated from currentProject)
const editProject = reactive<ProjectUpdate>({
  name: '',
  description: '',
  genre: '',
  premise: '',
  content_rating: '',
})

// --- Dirty tracking (project details) ---
const savedProjectSnapshot = ref({ name: '', description: '', genre: '', premise: '', content_rating: '' })

function snapshotProject() {
  savedProjectSnapshot.value = {
    name: editProject.name || '',
    description: editProject.description || '',
    genre: editProject.genre || '',
    premise: editProject.premise || '',
    content_rating: editProject.content_rating || '',
  }
}

// Populate edit forms when currentProject changes
watch(() => projectStore.currentProject, (proj) => {
  if (!proj) return
  editProject.name = proj.name
  editProject.description = proj.description || ''
  editProject.genre = proj.genre || ''
  editProject.premise = proj.premise || ''
  editProject.content_rating = proj.content_rating || ''
  snapshotProject()
  populateStoryline()
  populateWorld()
}, { immediate: true })

watch(() => projectStore.worldSettings, () => {
  if (projectStore.currentProject) {
    populateWorld()
  }
})

const echoContext = computed(() => ({
  project_name: editProject.name || projectStore.currentProject?.name || undefined,
  project_genre: editProject.genre || projectStore.currentProject?.genre || undefined,
  project_description: editProject.description || projectStore.currentProject?.description || undefined,
  project_premise: editProject.premise || projectStore.currentProject?.premise || undefined,
  checkpoint_model: projectStore.currentProject?.style?.checkpoint_model || undefined,
  positive_prompt_template: projectStore.currentProject?.style?.positive_prompt_template || undefined,
  negative_prompt_template: projectStore.currentProject?.style?.negative_prompt_template || undefined,
}))

// --- Storyline reactive form ---
const sl = reactive<{
  title: string
  summary: string
  theme: string
  genre: string
  target_audience: string
  tone: string
  humor_style: string
  themes: string[]
  story_arcs: string[]
}>({
  title: '',
  summary: '',
  theme: '',
  genre: '',
  target_audience: '',
  tone: '',
  humor_style: '',
  themes: [],
  story_arcs: [],
})

// --- World Settings reactive form ---
const ws = reactive<{
  style_preamble: string
  art_style: string
  aesthetic: string
  color_palette: { primary: string[]; secondary: string[]; environmental: string[] }
  cinematography: { shot_types: string[]; camera_angles: string[]; lighting: string }
  world_location: { primary: string; areas: string[]; atmosphere: string }
  time_period: string
  production_notes: string
  known_issues: string[]
  negative_prompt_guidance: string
}>({
  style_preamble: '',
  art_style: '',
  aesthetic: '',
  color_palette: { primary: [], secondary: [], environmental: [] },
  cinematography: { shot_types: [], camera_angles: [], lighting: '' },
  world_location: { primary: '', areas: [], atmosphere: '' },
  time_period: '',
  production_notes: '',
  known_issues: [],
  negative_prompt_guidance: '',
})

// --- Populate forms from store ---
function populateStoryline() {
  const s = projectStore.currentProject?.storyline
  sl.title = s?.title || ''
  sl.summary = s?.summary || ''
  sl.theme = s?.theme || ''
  sl.genre = s?.genre || ''
  sl.target_audience = s?.target_audience || ''
  sl.tone = s?.tone || ''
  sl.humor_style = s?.humor_style || ''
  sl.themes = s?.themes ? [...s.themes] : []
  sl.story_arcs = s?.story_arcs ? [...s.story_arcs] : []
  snapshotStoryline()
}

function populateWorld() {
  const w = projectStore.worldSettings
  ws.style_preamble = w?.style_preamble || ''
  ws.art_style = w?.art_style || ''
  ws.aesthetic = w?.aesthetic || ''
  ws.color_palette = {
    primary: w?.color_palette?.primary ? [...w.color_palette.primary] : [],
    secondary: w?.color_palette?.secondary ? [...w.color_palette.secondary] : [],
    environmental: w?.color_palette?.environmental ? [...w.color_palette.environmental] : [],
  }
  ws.cinematography = {
    shot_types: w?.cinematography?.shot_types ? [...w.cinematography.shot_types] : [],
    camera_angles: w?.cinematography?.camera_angles ? [...w.cinematography.camera_angles] : [],
    lighting: w?.cinematography?.lighting || '',
  }
  ws.world_location = {
    primary: w?.world_location?.primary || '',
    areas: w?.world_location?.areas ? [...w.world_location.areas] : [],
    atmosphere: w?.world_location?.atmosphere || '',
  }
  ws.time_period = w?.time_period || ''
  ws.production_notes = w?.production_notes || ''
  ws.known_issues = w?.known_issues ? [...w.known_issues] : []
  ws.negative_prompt_guidance = w?.negative_prompt_guidance || ''
  snapshotWorld()
}

// --- Dirty tracking (storyline + world) ---
const slSnapshot = ref('')
const wsSnapshot = ref('')

function snapshotStoryline() {
  slSnapshot.value = JSON.stringify({
    title: sl.title, summary: sl.summary, theme: sl.theme, genre: sl.genre,
    target_audience: sl.target_audience, tone: sl.tone, humor_style: sl.humor_style,
    themes: sl.themes, story_arcs: sl.story_arcs,
  })
}

function snapshotWorld() {
  wsSnapshot.value = JSON.stringify({
    style_preamble: ws.style_preamble, art_style: ws.art_style, aesthetic: ws.aesthetic,
    color_palette: ws.color_palette, cinematography: ws.cinematography,
    world_location: ws.world_location, time_period: ws.time_period,
    production_notes: ws.production_notes, known_issues: ws.known_issues,
    negative_prompt_guidance: ws.negative_prompt_guidance,
  })
}

const storylineDirty = computed(() => {
  const current = JSON.stringify({
    title: sl.title, summary: sl.summary, theme: sl.theme, genre: sl.genre,
    target_audience: sl.target_audience, tone: sl.tone, humor_style: sl.humor_style,
    themes: sl.themes, story_arcs: sl.story_arcs,
  })
  return current !== slSnapshot.value
})

const worldDirty = computed(() => {
  const current = JSON.stringify({
    style_preamble: ws.style_preamble, art_style: ws.art_style, aesthetic: ws.aesthetic,
    color_palette: ws.color_palette, cinematography: ws.cinematography,
    world_location: ws.world_location, time_period: ws.time_period,
    production_notes: ws.production_notes, known_issues: ws.known_issues,
    negative_prompt_guidance: ws.negative_prompt_guidance,
  })
  return current !== wsSnapshot.value
})

const storylineSaved = ref(false)
const worldSaved = ref(false)

function flashSaved(target: typeof storylineSaved) {
  target.value = true
  setTimeout(() => { target.value = false }, 2000)
}

// --- Save handlers (storyline + world) ---
async function handleSaveStoryline() {
  if (!projectStore.currentProject) return
  const data: StorylineUpsert = {
    title: sl.title || undefined,
    summary: sl.summary || undefined,
    theme: sl.theme || undefined,
    genre: sl.genre || undefined,
    target_audience: sl.target_audience || undefined,
    tone: sl.tone || undefined,
    humor_style: sl.humor_style || undefined,
    themes: sl.themes.length > 0 ? sl.themes : undefined,
    story_arcs: sl.story_arcs.length > 0 ? sl.story_arcs : undefined,
  }
  await projectStore.upsertStoryline(projectStore.currentProject.id, data)
  snapshotStoryline()
  flashSaved(storylineSaved)
}

async function handleSaveWorld() {
  if (!projectStore.currentProject) return
  const data: WorldSettingsUpsert = {
    style_preamble: ws.style_preamble || undefined,
    art_style: ws.art_style || undefined,
    aesthetic: ws.aesthetic || undefined,
    color_palette: (ws.color_palette.primary.length || ws.color_palette.secondary.length || ws.color_palette.environmental.length)
      ? ws.color_palette : undefined,
    cinematography: (ws.cinematography.shot_types.length || ws.cinematography.camera_angles.length || ws.cinematography.lighting)
      ? ws.cinematography : undefined,
    world_location: (ws.world_location.primary || ws.world_location.areas.length || ws.world_location.atmosphere)
      ? ws.world_location : undefined,
    time_period: ws.time_period || undefined,
    production_notes: ws.production_notes || undefined,
    known_issues: ws.known_issues.length > 0 ? ws.known_issues : undefined,
    negative_prompt_guidance: ws.negative_prompt_guidance || undefined,
  }
  await projectStore.updateWorldSettings(projectStore.currentProject.id, data)
  snapshotWorld()
  flashSaved(worldSaved)
}

// --- Echo Assist payloads ---
const storylineEchoPayload = computed(() => ({
  project_name: projectStore.currentProject?.name || undefined,
  project_genre: sl.genre || projectStore.currentProject?.genre || undefined,
  project_description: projectStore.currentProject?.description || undefined,
  project_premise: editProject.premise || projectStore.currentProject?.premise || undefined,
  checkpoint_model: projectStore.currentProject?.style?.checkpoint_model || undefined,
  storyline_title: sl.title || undefined,
  storyline_summary: sl.summary || undefined,
  storyline_theme: sl.theme || undefined,
}))

const productionNotesEchoPayload = computed(() => ({
  project_name: projectStore.currentProject?.name || undefined,
  project_genre: sl.genre || projectStore.currentProject?.genre || undefined,
  project_description: projectStore.currentProject?.description || undefined,
  project_premise: editProject.premise || projectStore.currentProject?.premise || undefined,
  checkpoint_model: projectStore.currentProject?.style?.checkpoint_model || undefined,
  storyline_title: sl.title || undefined,
  storyline_summary: sl.summary || undefined,
  storyline_theme: sl.theme || undefined,
}))

const preambleEchoPayload = computed(() => ({
  project_name: projectStore.currentProject?.name || undefined,
  project_genre: sl.genre || projectStore.currentProject?.genre || undefined,
  project_premise: editProject.premise || projectStore.currentProject?.premise || undefined,
  checkpoint_model: projectStore.currentProject?.style?.checkpoint_model || undefined,
}))

// --- Quick stats ---
const characterCount = computed(() => {
  if (!projectStore.currentProject) return 0
  const projectName = projectStore.currentProject.name
  return charactersStore.characters.filter(c => c.project_name === projectName).length
})

const approvedImageCount = computed(() => {
  if (!projectStore.currentProject) return 0
  const projectName = projectStore.currentProject.name
  const projectChars = charactersStore.characters.filter(c => c.project_name === projectName)
  let total = 0
  for (const char of projectChars) {
    const stats = charactersStore.getCharacterStats(char.slug || char.name)
    total += stats.approved
  }
  return total
})

const trainingReady = computed(() => {
  if (!projectStore.currentProject) return false
  const projectName = projectStore.currentProject.name
  const projectChars = charactersStore.characters.filter(c => c.project_name === projectName)
  if (projectChars.length === 0) return false
  return projectChars.some(char => {
    const stats = charactersStore.getCharacterStats(char.slug || char.name)
    return stats.canTrain
  })
})

const detailsDirty = computed(() => {
  const s = savedProjectSnapshot.value
  return editProject.name !== s.name
    || editProject.description !== s.description
    || editProject.genre !== s.genre
    || editProject.premise !== s.premise
    || editProject.content_rating !== s.content_rating
})

const detailsSaved = ref(false)

function showSaved() {
  saveMessage.value = 'Saved successfully'
  setTimeout(() => { saveMessage.value = '' }, 3000)
}

async function handleCreateProject(data: ProjectCreate) {
  const projectId = await projectStore.createProject(data)
  if (projectId) {
    selectedProjectId.value = projectId
    await projectStore.fetchProjectDetail(projectId)
    await fetchAllProjectDetails()
    showNewForm.value = false
    newFormRef.value?.resetForm()
    // Navigate carousel to the new project
    const idx = projectStore.projects.findIndex(p => p.id === projectId)
    if (idx >= 0) currentSlide.value = idx
    const proj = projectStore.projects.find(p => p.id === projectId)
    if (proj) {
      emit('project-selected', proj.id, proj.name)
    }
    showSaved()
  }
}

async function handleUpdateProject() {
  if (!projectStore.currentProject) return
  await projectStore.updateProject(projectStore.currentProject.id, { ...editProject })
  snapshotProject()
  detailsSaved.value = true
  setTimeout(() => { detailsSaved.value = false }, 2000)
}

async function handleUpdateStyle(data: StyleUpdate) {
  if (!projectStore.currentProject) return
  await projectStore.updateStyle(projectStore.currentProject.id, data)
}

onMounted(async () => {
  await Promise.all([
    projectStore.fetchProjects(),
    projectStore.fetchCheckpoints(),
    trainingStore.fetchLoras(),
  ])
  // Fetch details for all projects so tiles show genre/checkpoint/description
  await fetchAllProjectDetails()
})
</script>

<style scoped>
.project-tab {
  padding: 0;
}

/* --- Project Carousel --- */
.carousel-container {
  display: flex;
  align-items: center;
  gap: 0;
  margin-bottom: 12px;
  position: relative;
  outline: none;
}

.nav-arrow {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  color: var(--text-primary);
  font-size: 24px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 120ms, color 120ms, opacity 120ms;
  z-index: 2;
}

.nav-arrow:hover:not(:disabled) {
  background: var(--accent-primary);
  color: #fff;
  border-color: var(--accent-primary);
}

.nav-arrow:disabled {
  opacity: 0.25;
  cursor: default;
}

.nav-prev { margin-right: 12px; }
.nav-next { margin-left: 12px; }

.carousel-viewport {
  flex: 1;
  overflow: hidden;
  border-radius: 10px;
}

.carousel-track {
  display: flex;
  transition: transform 350ms cubic-bezier(0.4, 0, 0.2, 1);
}

.carousel-slide {
  flex: 0 0 100%;
  min-width: 0;
  padding: 0 4px;
  box-sizing: border-box;
}

/* --- Project Tile (large) --- */
.project-tile {
  background: var(--bg-secondary);
  border: 2px solid var(--border-primary);
  border-radius: 10px;
  padding: 24px 28px;
  cursor: pointer;
  transition: border-color 150ms ease, box-shadow 150ms ease;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 220px;
}

.project-tile:hover {
  border-color: var(--accent-primary);
  box-shadow: 0 4px 20px rgba(122, 162, 247, 0.12);
}

.project-tile.selected {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 1px var(--accent-primary), 0 6px 24px rgba(122, 162, 247, 0.18);
}

/* Top row: header + edit */
.tile-top-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.tile-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.tile-name {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.3;
}

.tile-edit-btn {
  background: transparent;
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 16px;
  padding: 4px 10px;
  flex-shrink: 0;
  transition: color 100ms, border-color 100ms;
}

.tile-edit-btn:hover {
  color: var(--accent-primary);
  border-color: var(--accent-primary);
}

/* Meta badges */
.tile-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
}

.tile-genre {
  padding: 2px 10px;
  border-radius: 10px;
  background: var(--accent-primary);
  color: #fff;
  text-transform: capitalize;
  font-weight: 500;
}

.tile-checkpoint {
  padding: 2px 10px;
  border-radius: 10px;
  background: var(--bg-primary);
  color: var(--text-muted);
  border: 1px solid var(--border-primary);
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Description */
.tile-description {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Stats row */
.tile-stats {
  display: flex;
  gap: 28px;
  padding: 10px 0;
  border-top: 1px solid var(--border-primary);
  border-bottom: 1px solid var(--border-primary);
}

.tile-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.tile-stat-val {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.tile-stat-lbl {
  font-size: 10px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

/* --- LoRA section inside tile --- */
.lora-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lora-section-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.lora-carousel-wrapper {
  display: flex;
  align-items: center;
  gap: 6px;
}

.lora-carousel {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  scrollbar-width: none;
  padding: 4px 0;
  flex: 1;
  min-width: 0;
}

.lora-carousel::-webkit-scrollbar {
  display: none;
}

.lora-arrow {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-primary);
  color: var(--text-secondary);
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lora-arrow:hover {
  color: var(--accent-primary);
  border-color: var(--accent-primary);
}

.lora-arrow-right {
  transform: rotate(180deg);
}

.lora-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px 4px 4px;
  border-radius: 20px;
  font-size: 12px;
  white-space: nowrap;
  flex-shrink: 0;
  border: 1px solid var(--border-primary);
  transition: background 100ms;
}

.lora-trained {
  background: rgba(80, 160, 80, 0.1);
  border-color: var(--status-success);
  color: var(--text-primary);
}

.lora-untrained {
  background: var(--bg-primary);
  color: var(--text-muted);
}

/* Thumbnail avatar */
.lora-thumb-wrapper {
  position: relative;
  flex-shrink: 0;
  width: 32px;
  height: 32px;
}

.lora-thumb {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  object-fit: cover;
  display: block;
}

.lora-thumb-placeholder {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  color: var(--text-muted);
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
}

.lora-status-dot {
  position: absolute;
  bottom: -1px;
  right: -1px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid var(--bg-secondary);
}

.dot-green { background: var(--status-success); }
.dot-grey { background: var(--text-muted); }

.lora-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

.lora-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 4px 0;
}

/* Add tile */
.add-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-style: dashed;
  min-height: 220px;
  gap: 10px;
}

.add-tile:hover {
  background: var(--bg-tertiary);
}

.add-icon {
  font-size: 40px;
  color: var(--text-muted);
  line-height: 1;
}

.add-label {
  font-size: 14px;
  color: var(--text-muted);
}

/* --- Dot indicators --- */
.carousel-indicators {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 24px;
}

.indicator-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1px solid var(--border-primary);
  background: var(--bg-tertiary);
  cursor: pointer;
  padding: 0;
  transition: background 150ms, border-color 150ms;
}

.indicator-dot.active {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
}

.indicator-dot:hover:not(.active) {
  border-color: var(--accent-primary);
}

.slide-counter {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 8px;
}

/* --- Detail sections (unchanged) --- */
.section-heading {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.two-column {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 20px;
}
@media (max-width: 900px) {
  .two-column {
    grid-template-columns: 1fr;
  }
}
.stats-bar {
  display: flex;
  gap: 32px;
  align-items: center;
  padding: 12px 20px;
}
.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}
.stat-label {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.stat-link {
  text-decoration: none;
  cursor: pointer;
  border-radius: 4px;
  padding: 6px 12px;
  transition: background 150ms ease;
}
.stat-link:hover {
  background: rgba(122, 162, 247, 0.08);
}
.stat-link:hover .stat-label {
  text-decoration: underline;
  color: var(--accent-primary);
}
.field-label {
  font-size: 11px;
  color: var(--text-muted);
  display: block;
  margin-bottom: 4px;
}
.field-input {
  padding: 5px 8px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
  font-family: var(--font-primary);
  width: 100%;
}
.field-input:focus {
  border-color: var(--border-focus);
  outline: none;
}
.btn-saved {
  background: var(--status-success) !important;
  color: var(--bg-primary) !important;
  border-color: var(--status-success) !important;
}

/* Collapsible sections */
.collapsible-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  padding: 0 20px 0 20px;
}
.collapsible-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 14px 0;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--text-primary);
  font-family: var(--font-primary);
}
.collapsible-header:hover {
  opacity: 0.8;
}
.collapse-indicator {
  font-size: 11px;
  color: var(--text-muted);
  display: inline-block;
  transition: transform 150ms ease;
}
.collapse-indicator.open {
  transform: rotate(90deg);
}
</style>
