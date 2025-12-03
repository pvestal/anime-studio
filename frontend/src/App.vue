<template>
  <div class="dark-mode" style="height: 100vh; background: #0a0a0a; color: #e0e0e0;">
    <Toast />

    <Toolbar style="background: #1a1a1a; border-bottom: 1px solid #333; padding: 0.5rem 1rem;">
      <template #start>
        <h2 style="margin: 0; font-size: 1.5rem; font-weight: 600;">
          <i class="pi pi-terminal" style="margin-right: 0.5rem;"></i>
          Echo Brain Anime Studio
        </h2>
      </template>
      <template #end>
        <Button :label="getViewButtonLabel()"
                :icon="getViewButtonIcon()"
                @click="toggleView"
                severity="secondary" style="margin-right: 0.5rem;" />
        <Button label="New Project" icon="pi pi-plus" @click="showNewProjectDialog = true" style="margin-right: 0.5rem;" v-if="viewMode === 'studio'" />
        <Button label="New Scene" icon="pi pi-file" @click="showNewSceneDialog = true" :disabled="!selectedProject" severity="secondary" style="margin-right: 0.5rem;" v-if="viewMode === 'studio'" />
        <Button label="Generate" icon="pi pi-play" @click="generateScene" :disabled="!selectedScene" severity="success" v-if="viewMode === 'studio'" />
      </template>
    </Toolbar>

    <!-- Dashboard View -->
    <AnimeDashboard v-if="viewMode === 'dashboard'" />

    <!-- Console View -->
    <EchoAnimeConsole v-if="viewMode === 'console'" />

    <!-- Studio View -->
    <Splitter v-if="viewMode === 'studio'" style="height: calc(100vh - 60px);">
      <!-- Left Panel: Projects -->
      <SplitterPanel :size="20" :minSize="15">
        <div style="padding: 1rem; height: 100%; overflow-y: auto;">
          <h3 style="margin-top: 0;">Projects</h3>
          <InputText v-model="projectSearch" placeholder="Search projects..." style="width: 100%; margin-bottom: 1rem;" />

          <div v-for="project in filteredProjects" :key="project.id"
               @click="selectProject(project)"
               :class="['project-card', { 'selected': selectedProject?.id === project.id }]"
               style="padding: 0.75rem; margin-bottom: 0.5rem; border: 1px solid #333; border-radius: 6px; cursor: pointer; transition: all 0.2s;">
            <div style="font-weight: 600; margin-bottom: 0.25rem;">{{ project.name }}</div>
            <Tag :value="project.status" :severity="getStatusSeverity(project.status)" style="font-size: 0.75rem;" />
            <div style="font-size: 0.8rem; color: #999; margin-top: 0.25rem;">{{ formatDate(project.created_at) }}</div>
          </div>
        </div>
      </SplitterPanel>

      <!-- Center Panel: Scenes -->
      <SplitterPanel :size="50" :minSize="30">
        <div style="padding: 1rem; height: 100%; display: flex; flex-direction: column;">
          <h3 style="margin-top: 0;">Scenes</h3>

          <DataTable :value="scenes" v-model:selection="selectedScene" selectionMode="single"
                     :paginator="true" :rows="10"
                     style="flex: 1;"
                     :rowHover="true"
                     @row-select="onSceneSelect">
            <Column field="scene_number" header="#" style="width: 60px;"></Column>
            <Column field="description" header="Description" style="max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"></Column>
            <Column field="characters" header="Characters" style="max-width: 200px;">
              <template #body="slotProps">
                {{ slotProps.data.characters || 'None' }}
              </template>
            </Column>
            <Column field="status" header="Status" style="width: 120px;">
              <template #body="slotProps">
                <Tag :value="slotProps.data.status" :severity="getStatusSeverity(slotProps.data.status)" />
              </template>
            </Column>
            <Column header="Actions" style="width: 150px;">
              <template #body="slotProps">
                <Button icon="pi pi-play" @click="generateSceneById(slotProps.data.id)" size="small" severity="success" text />
                <Button icon="pi pi-eye" v-if="slotProps.data.video_path" @click="viewVideo(slotProps.data.video_path)" size="small" text />
              </template>
            </Column>
          </DataTable>
        </div>
      </SplitterPanel>

      <!-- Right Panel: Properties -->
      <SplitterPanel :size="30" :minSize="20">
        <div style="padding: 1rem; height: 100%; overflow-y: auto;">
          <h3 style="margin-top: 0;">Properties</h3>

          <div v-if="selectedProject && !selectedScene">
            <Card style="background: #1a1a1a; border: 1px solid #333;">
              <template #title>Project: {{ selectedProject.name }}</template>
              <template #content>
                <div style="margin-bottom: 1rem;">
                  <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Description</label>
                  <Textarea v-model="selectedProject.description" rows="4" style="width: 100%;" />
                </div>
                <div style="margin-bottom: 1rem;">
                  <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Status</label>
                  <InputText v-model="selectedProject.status" style="width: 100%;" />
                </div>
                <Button label="Save" icon="pi pi-save" @click="saveProject" style="width: 100%;" />
              </template>
            </Card>
          </div>

          <div v-if="selectedScene">
            <Card style="background: #1a1a1a; border: 1px solid #333;">
              <template #title>Scene {{ selectedScene.scene_number }}</template>
              <template #content>
                <div style="margin-bottom: 1rem;">
                  <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Description</label>
                  <Textarea v-model="selectedScene.description" rows="4" style="width: 100%;" />
                </div>
                <div style="margin-bottom: 1rem;">
                  <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Characters</label>
                  <InputText v-model="selectedScene.characters" style="width: 100%;" />
                </div>
                <div style="margin-bottom: 1rem;">
                  <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Status</label>
                  <Tag :value="selectedScene.status" :severity="getStatusSeverity(selectedScene.status)" />
                </div>
                <Button label="Save Scene" icon="pi pi-save" @click="saveScene" style="width: 100%; margin-bottom: 0.5rem;" />
                <Button label="Generate Video" icon="pi pi-play" @click="generateScene" severity="success" style="width: 100%;" />
              </template>
            </Card>
          </div>

          <div v-if="!selectedProject && !selectedScene" style="text-align: center; color: #666; margin-top: 2rem;">
            <i class="pi pi-info-circle" style="font-size: 3rem; margin-bottom: 1rem;"></i>
            <p>Select a project or scene to view properties</p>
          </div>
        </div>
      </SplitterPanel>
    </Splitter>

    <!-- New Project Dialog -->
    <Dialog v-model:visible="showNewProjectDialog" header="New Project" :modal="true" :style="{'width': '450px'}">
      <div style="margin-bottom: 1rem;">
        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Project Name</label>
        <InputText v-model="newProject.name" style="width: 100%;" />
      </div>
      <div style="margin-bottom: 1rem;">
        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Description</label>
        <Textarea v-model="newProject.description" rows="4" style="width: 100%;" />
      </div>
      <template #footer>
        <Button label="Cancel" @click="showNewProjectDialog = false" severity="secondary" />
        <Button label="Create" @click="createProject" />
      </template>
    </Dialog>

    <!-- New Scene Dialog -->
    <Dialog v-model:visible="showNewSceneDialog" header="New Scene" :modal="true" :style="{'width': '450px'}">
      <div style="margin-bottom: 1rem;">
        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Scene Number</label>
        <InputText v-model.number="newScene.scene_number" type="number" style="width: 100%;" />
      </div>
      <div style="margin-bottom: 1rem;">
        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Description</label>
        <Textarea v-model="newScene.description" rows="4" style="width: 100%;" />
      </div>
      <div style="margin-bottom: 1rem;">
        <label style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Characters</label>
        <InputText v-model="newScene.characters" style="width: 100%;" />
      </div>
      <template #footer>
        <Button label="Cancel" @click="showNewSceneDialog = false" severity="secondary" />
        <Button label="Create" @click="createScene" />
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import EchoAnimeConsole from './components/EchoAnimeConsole.vue'
import AnimeDashboard from './components/AnimeDashboard.vue'

const toast = useToast()
const API_BASE = 'http://192.168.50.135:8323/api/anime'

// View Mode
const viewMode = ref('dashboard')

// State
const projects = ref([])
const scenes = ref([])
const selectedProject = ref(null)
const selectedScene = ref(null)
const projectSearch = ref('')
const showNewProjectDialog = ref(false)
const showNewSceneDialog = ref(false)

const newProject = ref({ name: '', description: '' })
const newScene = ref({ scene_number: 1, description: '', characters: '' })

// View toggle
function toggleView() {
  const modes = ['dashboard', 'console', 'studio']
  const currentIndex = modes.indexOf(viewMode.value)
  viewMode.value = modes[(currentIndex + 1) % modes.length]
}

// Computed
const filteredProjects = computed(() => {
  if (!projectSearch.value) return projects.value
  return projects.value.filter(p =>
    p.name.toLowerCase().includes(projectSearch.value.toLowerCase())
  )
})

// Methods
async function loadProjects() {
  try {
    const response = await fetch(`${API_BASE}/episodes`)
    projects.value = await response.json()
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to load projects', life: 3000 })
  }
}

async function selectProject(project) {
  selectedProject.value = project
  selectedScene.value = null
  await loadScenes(project.id)
}

async function loadScenes(projectId) {
  try {
    const response = await fetch(`${API_BASE}/episodes/${projectId}/scenes`)
    scenes.value = await response.json()
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to load scenes', life: 3000 })
  }
}

function onSceneSelect(event) {
  selectedScene.value = event.data
}

async function createProject() {
  try {
    const response = await fetch(`${API_BASE}/episodes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newProject.value)
    })
    const project = await response.json()
    projects.value.push(project)
    showNewProjectDialog.value = false
    newProject.value = { name: '', description: '' }
    toast.add({ severity: 'success', summary: 'Success', detail: 'Project created', life: 3000 })
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to create project', life: 3000 })
  }
}

async function createScene() {
  if (!selectedProject.value) return

  try {
    const response = await fetch(`${API_BASE}/episodes/${selectedProject.value.id}/scenes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newScene.value)
    })
    const scene = await response.json()
    scenes.value.push(scene)
    showNewSceneDialog.value = false
    newScene.value = { scene_number: scenes.value.length + 1, description: '', characters: '' }
    toast.add({ severity: 'success', summary: 'Success', detail: 'Scene created', life: 3000 })
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to create scene', life: 3000 })
  }
}

async function saveProject() {
  if (!selectedProject.value) return

  try {
    await fetch(`${API_BASE}/episodes/${selectedProject.value.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(selectedProject.value)
    })
    toast.add({ severity: 'success', summary: 'Success', detail: 'Project saved', life: 3000 })
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to save project', life: 3000 })
  }
}

async function saveScene() {
  if (!selectedScene.value || !selectedProject.value) return

  try {
    await fetch(`${API_BASE}/scenes/${selectedScene.value.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(selectedScene.value)
    })
    toast.add({ severity: 'success', summary: 'Success', detail: 'Scene saved', life: 3000 })
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to save scene', life: 3000 })
  }
}

function generateScene() {
  if (!selectedScene.value) return
  toast.add({ severity: 'info', summary: 'Generation Started', detail: 'Scene generation queued (ComfyUI integration pending)', life: 5000 })
}

function generateSceneById(sceneId) {
  toast.add({ severity: 'info', summary: 'Generation Started', detail: `Scene ${sceneId} generation queued`, life: 3000 })
}

function viewVideo(videoPath) {
  toast.add({ severity: 'info', summary: 'Video', detail: `Video: ${videoPath}`, life: 3000 })
}

function getStatusSeverity(status) {
  const statusMap = {
    'active': 'success',
    'pending': 'warning',
    'processing': 'info',
    'completed': 'success',
    'failed': 'danger'
  }
  return statusMap[status] || 'secondary'
}

function formatDate(dateString) {
  if (!dateString) return ''
  return new Date(dateString).toLocaleDateString()
}

function getViewButtonLabel() {
  const labels = {
    'dashboard': 'Console View',
    'console': 'Studio View',
    'studio': 'Dashboard View'
  }
  return labels[viewMode.value] || 'Dashboard View'
}

function getViewButtonIcon() {
  const icons = {
    'dashboard': 'pi pi-terminal',
    'console': 'pi pi-desktop',
    'studio': 'pi pi-chart-bar'
  }
  return icons[viewMode.value] || 'pi pi-chart-bar'
}

// Initialize
onMounted(() => {
  loadProjects()
})
</script>

<style scoped>
.project-card:hover {
  background: #222;
  border-color: #555 !important;
}

.project-card.selected {
  background: #2a2a2a;
  border-color: #667eea !important;
}
</style>
