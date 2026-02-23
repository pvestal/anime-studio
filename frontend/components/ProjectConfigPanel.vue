<template>
  <div class="card" style="margin-bottom: 24px;">
    <!-- Header row: always visible -->
    <div
      style="display: flex; align-items: center; justify-content: space-between; cursor: pointer; user-select: none;"
      @click="expanded = !expanded"
    >
      <div style="display: flex; align-items: center; gap: 12px;">
        <span class="collapse-arrow" :class="{ open: expanded }">&#9654;</span>
        <h3 style="font-size: 15px; font-weight: 500; margin: 0;">Project Configuration</h3>
        <!-- Collapsed summary -->
        <span v-if="!expanded && projectStore.currentProject" style="font-size: 12px; color: var(--text-secondary);">
          {{ projectStore.currentProject.name }}
          <template v-if="projectStore.currentProject.style">
            &mdash; {{ projectStore.currentProject.style.checkpoint_model || 'no checkpoint' }},
            {{ projectStore.currentProject.style.steps || '?' }} steps,
            {{ projectStore.currentProject.style.width || '?' }}x{{ projectStore.currentProject.style.height || '?' }}
          </template>
        </span>
      </div>
      <span style="font-size: 11px; color: var(--text-muted);">{{ expanded ? 'collapse' : 'expand' }}</span>
    </div>

    <!-- Expanded content -->
    <div v-if="expanded" style="margin-top: 16px;">

      <!-- Project selector row -->
      <div style="display: flex; gap: 12px; align-items: flex-end; margin-bottom: 20px;">
        <div style="flex: 1;">
          <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Project</label>
          <select v-model="selectedProjectId" @change="onProjectSelect" style="width: 100%;">
            <option :value="0">Select a project...</option>
            <option v-for="p in projectStore.projects" :key="p.id" :value="p.id">
              {{ p.name }} ({{ p.character_count }} characters)
            </option>
          </select>
        </div>
        <button class="btn" style="white-space: nowrap;" @click="showNewForm = true" v-if="!showNewForm">
          + New Project
        </button>
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

        <!-- Section: Project Details -->
        <div style="margin-bottom: 20px;">
          <h4 style="font-size: 13px; font-weight: 500; color: var(--text-secondary); margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px;">Project Details</h4>
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

        <!-- Section: Storyline -->
        <StorylineSection
          :storyline="projectStore.currentProject.storyline"
          :saving="projectStore.saving"
          :echo-context="echoContext"
          @save="handleUpsertStoryline"
        />

        <!-- Section: Generation Style -->
        <GenerationStylePanel
          :style-prop="projectStore.currentProject.style"
          :checkpoints="projectStore.checkpoints"
          :saving="projectStore.saving"
          :echo-context="echoContext"
          @save="handleUpdateStyle"
        />

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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useProjectStore } from '@/stores/project'
import type { ProjectCreate, ProjectUpdate, StorylineUpsert, StyleUpdate } from '@/types'
import EchoAssistButton from './EchoAssistButton.vue'
import NewProjectForm from './project/NewProjectForm.vue'
import StorylineSection from './project/StorylineSection.vue'
import GenerationStylePanel from './project/GenerationStylePanel.vue'

const emit = defineEmits<{
  'project-selected': [projectId: number, projectName: string]
}>()

const projectStore = useProjectStore()

const expanded = ref(false)
const showNewForm = ref(false)
const newFormRef = ref<InstanceType<typeof NewProjectForm> | null>(null)
const selectedProjectId = ref(0)
const saveMessage = ref('')

// Edit forms (populated from currentProject)
const editProject = reactive<ProjectUpdate>({
  name: '',
  description: '',
  genre: '',
})

// Populate edit forms when currentProject changes
watch(() => projectStore.currentProject, (proj) => {
  if (!proj) return
  editProject.name = proj.name
  editProject.description = proj.description || ''
  editProject.genre = proj.genre || ''
  snapshotProject()
}, { immediate: true })

const echoContext = computed(() => ({
  project_name: editProject.name || projectStore.currentProject?.name || undefined,
  project_genre: editProject.genre || projectStore.currentProject?.genre || undefined,
  project_description: editProject.description || projectStore.currentProject?.description || undefined,
  project_premise: projectStore.currentProject?.premise || undefined,
  checkpoint_model: projectStore.currentProject?.style?.checkpoint_model || undefined,
  storyline_title: projectStore.currentProject?.storyline?.title || undefined,
  storyline_summary: projectStore.currentProject?.storyline?.summary || undefined,
  storyline_theme: projectStore.currentProject?.storyline?.theme || undefined,
  positive_prompt_template: projectStore.currentProject?.style?.positive_prompt_template || undefined,
  negative_prompt_template: projectStore.currentProject?.style?.negative_prompt_template || undefined,
}))

// Dirty tracking
const savedProjectSnapshot = ref({ name: '', description: '', genre: '' })

const detailsDirty = computed(() => {
  const s = savedProjectSnapshot.value
  return editProject.name !== s.name || editProject.description !== s.description || editProject.genre !== s.genre
})

const detailsSaved = ref(false)

function snapshotProject() {
  savedProjectSnapshot.value = { name: editProject.name || '', description: editProject.description || '', genre: editProject.genre || '' }
}

function showSaved() {
  saveMessage.value = 'Saved successfully'
  setTimeout(() => { saveMessage.value = '' }, 3000)
}

async function onProjectSelect() {
  if (!selectedProjectId.value) {
    projectStore.currentProject = null
    return
  }
  await projectStore.fetchProjectDetail(selectedProjectId.value)
  const proj = projectStore.projects.find(p => p.id === selectedProjectId.value)
  if (proj) {
    emit('project-selected', proj.id, proj.name)
  }
}

async function handleCreateProject(data: ProjectCreate) {
  const projectId = await projectStore.createProject(data)
  if (projectId) {
    selectedProjectId.value = projectId
    await projectStore.fetchProjectDetail(projectId)
    showNewForm.value = false
    newFormRef.value?.resetForm()
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

async function handleUpsertStoryline(data: StorylineUpsert) {
  if (!projectStore.currentProject) return
  await projectStore.upsertStoryline(projectStore.currentProject.id, data)
}

async function handleUpdateStyle(data: StyleUpdate) {
  if (!projectStore.currentProject) return
  await projectStore.updateStyle(projectStore.currentProject.id, data)
}

onMounted(async () => {
  await Promise.all([
    projectStore.fetchProjects(),
    projectStore.fetchCheckpoints(),
  ])
})
</script>

<style scoped>
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
.collapse-arrow {
  font-size: 11px;
  color: var(--text-muted);
  display: inline-block;
  transition: transform 150ms ease;
}
.collapse-arrow.open {
  transform: rotate(90deg);
}
</style>
