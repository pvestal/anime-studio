<template>
  <div class="anime-dashboard">
    <!-- Header with Status Indicators -->
    <div class="dashboard-header">
      <h1 class="dashboard-title">Anime Production Dashboard</h1>
      <div class="status-indicators">
        <div class="status-item" :class="{ connected: wsConnected }">
          <i class="pi pi-circle-fill"></i>
          <span>{{ wsConnected ? 'Live Updates' : 'Reconnecting...' }}</span>
        </div>
        <div class="status-item" :class="{ connected: apiHealthy }">
          <i class="pi pi-circle-fill"></i>
          <span>{{ apiHealthy ? 'API Ready' : 'API Down' }}</span>
        </div>
        <div class="performance-metric">
          <i class="pi pi-clock"></i>
          <span>Avg: {{ avgGenerationTime }}s</span>
        </div>
      </div>
    </div>

    <!-- Main Dashboard Grid -->
    <div class="dashboard-grid">
      <!-- Project Grid Section -->
      <Card class="dashboard-section projects-section">
        <template #title>
          <div class="section-header">
            <i class="pi pi-folder"></i>
            <span>Active Projects</span>
            <Button
              icon="pi pi-plus"
              size="small"
              class="add-button"
              @click="showCreateProject = true"
            />
          </div>
        </template>
        <template #content>
          <div class="projects-grid">
            <div
              v-for="project in projects"
              :key="project.id"
              class="project-card"
              :class="{ selected: selectedProject?.id === project.id }"
              @click="selectProject(project)"
            >
              <div class="project-thumbnail">
                <img v-if="project.thumbnail" :src="project.thumbnail" :alt="project.name" />
                <div v-else class="placeholder-thumbnail">
                  <i class="pi pi-image"></i>
                </div>
              </div>
              <div class="project-info">
                <h4>{{ project.name }}</h4>
                <p class="project-description">{{ project.description }}</p>
                <div class="project-stats">
                  <span class="stat">{{ project.characterCount || 0 }} chars</span>
                  <span class="stat">{{ project.generationCount || 0 }} images</span>
                </div>
              </div>
            </div>
            <div class="project-card add-project-card" @click="showCreateProject = true">
              <div class="add-project-content">
                <i class="pi pi-plus"></i>
                <span>New Project</span>
              </div>
            </div>
          </div>
        </template>
      </Card>

      <!-- Generation Queue Section -->
      <Card class="dashboard-section queue-section">
        <template #title>
          <div class="section-header">
            <i class="pi pi-list"></i>
            <span>Generation Queue</span>
            <Tag
              v-if="activeJobs.length > 0"
              :value="activeJobs.length"
              severity="info"
              class="queue-count"
            />
          </div>
        </template>
        <template #content>
          <div class="generation-queue">
            <div
              v-for="job in activeJobs"
              :key="job.id"
              class="queue-item"
              :class="job.status"
            >
              <div class="job-info">
                <div class="job-header">
                  <span class="job-id">#{{ job.id }}</span>
                  <Tag
                    :value="job.status"
                    :severity="getJobSeverity(job.status)"
                    class="job-status"
                  />
                </div>
                <p class="job-prompt">{{ truncate(job.prompt, 60) }}</p>
                <div class="job-details">
                  <span class="job-type">{{ job.type }}</span>
                  <span class="job-time">{{ formatTime(job.startTime) }}</span>
                </div>
              </div>
              <div class="job-progress">
                <div class="progress-bar">
                  <div
                    class="progress-fill"
                    :style="{ width: `${getJobProgress(job.id)}%` }"
                  ></div>
                </div>
                <span class="progress-text">
                  {{ getJobProgress(job.id) }}%
                  <span v-if="getJobETA(job.id)" class="eta">
                    ({{ getJobETA(job.id) }})
                  </span>
                </span>
              </div>
            </div>
            <div v-if="activeJobs.length === 0" class="empty-queue">
              <i class="pi pi-clock"></i>
              <span>No active generations</span>
            </div>
          </div>
        </template>
      </Card>

      <!-- Character Library Section -->
      <Card class="dashboard-section characters-section">
        <template #title>
          <div class="section-header">
            <i class="pi pi-users"></i>
            <span>Character Library</span>
            <Button
              icon="pi pi-plus"
              size="small"
              class="add-button"
              @click="showCreateCharacter = true"
            />
          </div>
        </template>
        <template #content>
          <div class="characters-grid">
            <div
              v-for="character in characters"
              :key="character.id"
              class="character-card"
              @click="selectCharacter(character)"
            >
              <div class="character-thumbnail">
                <img
                  v-if="character.thumbnail"
                  :src="character.thumbnail"
                  :alt="character.name"
                />
                <div v-else class="placeholder-thumbnail">
                  <i class="pi pi-user"></i>
                </div>
              </div>
              <div class="character-info">
                <h5>{{ character.name }}</h5>
                <p class="character-role">{{ character.role || 'Character' }}</p>
                <div class="consistency-score" v-if="character.consistencyScore">
                  <i class="pi pi-check-circle" :class="getConsistencyClass(character.consistencyScore)"></i>
                  <span>{{ (character.consistencyScore * 100).toFixed(0) }}%</span>
                </div>
              </div>
            </div>
          </div>
        </template>
      </Card>

      <!-- Recent Generations Section -->
      <Card class="dashboard-section recent-section">
        <template #title>
          <div class="section-header">
            <i class="pi pi-history"></i>
            <span>Recent Generations</span>
            <Button
              icon="pi pi-refresh"
              size="small"
              class="refresh-button"
              @click="refreshRecentGenerations"
            />
          </div>
        </template>
        <template #content>
          <div class="recent-grid">
            <div
              v-for="generation in recentGenerations"
              :key="generation.id"
              class="generation-card"
              @click="viewGeneration(generation)"
            >
              <div class="generation-thumbnail">
                <img
                  v-if="generation.outputPath"
                  :src="getImageUrl(generation.outputPath)"
                  :alt="`Generation ${generation.id}`"
                  @error="handleImageError"
                />
                <div v-else class="placeholder-thumbnail">
                  <i class="pi pi-image"></i>
                </div>
              </div>
              <div class="generation-info">
                <p class="generation-prompt">{{ truncate(generation.prompt, 40) }}</p>
                <div class="generation-meta">
                  <span class="generation-time">{{ formatTime(generation.createdAt) }}</span>
                  <Tag
                    :value="generation.status"
                    :severity="getJobSeverity(generation.status)"
                    size="small"
                  />
                </div>
              </div>
            </div>
          </div>
        </template>
      </Card>

      <!-- Quick Actions Panel -->
      <Card class="dashboard-section actions-section">
        <template #title>
          <div class="section-header">
            <i class="pi pi-bolt"></i>
            <span>Quick Actions</span>
          </div>
        </template>
        <template #content>
          <div class="quick-actions">
            <Button
              label="Generate Image"
              icon="pi pi-image"
              class="action-button primary"
              @click="showGenerateDialog = true"
            />
            <Button
              label="Generate Video"
              icon="pi pi-video"
              class="action-button secondary"
              @click="showGenerateVideoDialog = true"
            />
            <Button
              label="Character Studio"
              icon="pi pi-user-edit"
              class="action-button tertiary"
              @click="openCharacterStudio"
            />
            <Button
              label="Browse Files"
              icon="pi pi-folder-open"
              class="action-button tertiary"
              @click="openFileOrganizer"
            />
          </div>
        </template>
      </Card>
    </div>

    <!-- Generation Dialog -->
    <Dialog
      v-model:visible="showGenerateDialog"
      header="Generate Image"
      modal
      :style="{ width: '500px' }"
    >
      <div class="generate-form">
        <div class="field">
          <label for="prompt">Prompt</label>
          <Textarea
            id="prompt"
            v-model="generateForm.prompt"
            rows="4"
            placeholder="Describe your anime scene..."
            class="w-full"
          />
        </div>
        <div class="field">
          <label for="character">Character (Optional)</label>
          <Dropdown
            id="character"
            v-model="generateForm.character"
            :options="characters"
            optionLabel="name"
            optionValue="name"
            placeholder="Select character"
            class="w-full"
          />
        </div>
        <div class="field">
          <label for="style">Style</label>
          <Dropdown
            id="style"
            v-model="generateForm.style"
            :options="styleOptions"
            placeholder="Select style"
            class="w-full"
          />
        </div>
      </div>
      <template #footer>
        <Button
          label="Cancel"
          icon="pi pi-times"
          text
          @click="showGenerateDialog = false"
        />
        <Button
          label="Generate"
          icon="pi pi-check"
          @click="submitGeneration"
          :loading="generating"
        />
      </template>
    </Dialog>

    <!-- Performance Stats Overlay -->
    <div v-if="showPerformanceStats" class="performance-overlay">
      <Card class="performance-card">
        <template #title>Performance Statistics</template>
        <template #content>
          <div class="performance-stats">
            <div class="stat-item">
              <span class="stat-label">Total Generations:</span>
              <span class="stat-value">{{ totalGenerations }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Success Rate:</span>
              <span class="stat-value success">{{ successRate }}%</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Average Time:</span>
              <span class="stat-value">{{ avgGenerationTime }}s</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Queue Length:</span>
              <span class="stat-value">{{ activeJobs.length }}</span>
            </div>
          </div>
        </template>
      </Card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useEnhancedAnimeStore } from '../stores/enhancedAnimeStore.js'

// Store
const animeStore = useEnhancedAnimeStore()

// Reactive state
const apiHealthy = ref(false)
const showGenerateDialog = ref(false)
const showGenerateVideoDialog = ref(false)
const showCreateProject = ref(false)
const showCreateCharacter = ref(false)
const showPerformanceStats = ref(false)
const generating = ref(false)

// Forms
const generateForm = ref({
  prompt: '',
  character: null,
  style: 'anime'
})

// Style options
const styleOptions = ref([
  'anime',
  'photorealistic',
  'cartoon',
  'artistic',
  'manga'
])

// Computed properties
const projects = computed(() => animeStore.projects)
const characters = computed(() => animeStore.characters)
const selectedProject = computed(() => animeStore.selectedProject)
const activeJobs = computed(() => animeStore.activeJobs)
const recentGenerations = computed(() => animeStore.recentGenerations.slice(0, 8))
const wsConnected = computed(() => animeStore.wsConnected)

// Performance metrics
const avgGenerationTime = computed(() => {
  const completed = animeStore.generationHistory.filter(g =>
    g.status === 'completed' && g.duration
  )
  if (completed.length === 0) return '3.0'
  const avg = completed.reduce((sum, g) => sum + g.duration, 0) / completed.length
  return avg.toFixed(1)
})

const totalGenerations = computed(() => animeStore.generationHistory.length)

const successRate = computed(() => {
  if (totalGenerations.value === 0) return 100
  const successful = animeStore.generationHistory.filter(g => g.status === 'completed').length
  return ((successful / totalGenerations.value) * 100).toFixed(1)
})

// WebSocket management (now handled by store)
// Remove local WebSocket functions as they're handled by the enhanced store

// API health check
const checkApiHealth = async () => {
  apiHealthy.value = await animeStore.checkApiHealth()
}

// Utility functions
const getJobProgress = (jobId) => {
  return animeStore.getJobProgress(jobId)
}

const getJobETA = (jobId) => {
  return animeStore.getJobETA(jobId)
}

const getJobSeverity = (status) => {
  const severityMap = {
    'pending': 'info',
    'running': 'warning',
    'processing': 'warning',
    'completed': 'success',
    'failed': 'danger'
  }
  return severityMap[status] || 'info'
}

const getConsistencyClass = (score) => {
  if (score >= 0.8) return 'high-consistency'
  if (score >= 0.6) return 'medium-consistency'
  return 'low-consistency'
}

const truncate = (text, length) => {
  if (!text) return ''
  return text.length > length ? text.substring(0, length) + '...' : text
}

const formatTime = (timestamp) => {
  if (!timestamp) return 'N/A'
  const date = new Date(timestamp)
  return date.toLocaleTimeString()
}

const getImageUrl = (path) => {
  // Convert file path to accessible URL
  if (path && path.includes('/mnt/1TB-storage/')) {
    return path.replace('/mnt/1TB-storage/', 'http://localhost:8328/files/')
  }
  return path
}

const handleImageError = (event) => {
  event.target.style.display = 'none'
}

// Actions
const selectProject = (project) => {
  animeStore.selectProject(project)
}

const selectCharacter = (character) => {
  animeStore.selectCharacter(character)
}

const submitGeneration = async () => {
  if (!generateForm.value.prompt.trim()) return

  try {
    generating.value = true
    const generationRequest = {
      prompt: generateForm.value.prompt,
      type: 'image',
      character: generateForm.value.character,
      style: generateForm.value.style,
      project_id: selectedProject.value?.id
    }

    await animeStore.startGeneration(generationRequest)
    showGenerateDialog.value = false
    generateForm.value = { prompt: '', character: null, style: 'anime' }
  } catch (error) {
    console.error('Generation failed:', error)
  } finally {
    generating.value = false
  }
}

const refreshRecentGenerations = async () => {
  await animeStore.loadGenerationHistory()
}

const viewGeneration = (generation) => {
  // Open generation in larger view or navigate to detail page
  console.log('Viewing generation:', generation)
}

const openCharacterStudio = () => {
  animeStore.setActiveView('studio')
}

const openFileOrganizer = () => {
  // Navigate to file organizer view
  console.log('Opening file organizer')
}

// Lifecycle
onMounted(async () => {
  // Initial data load
  await Promise.all([
    animeStore.loadProjects(),
    animeStore.loadGenerationHistory(),
    checkApiHealth(),
    animeStore.connectToEcho()
  ])

  // Connect WebSocket through store
  animeStore.connectWebSocket()

  // Set up health check interval
  setInterval(checkApiHealth, 30000)
})

onUnmounted(() => {
  animeStore.disconnectWebSocket()
})
</script>

<style scoped>
.anime-dashboard {
  min-height: 100vh;
  background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
  color: #ffffff;
  padding: 20px;
  font-family: 'Arial', sans-serif;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  padding-bottom: 20px;
  border-bottom: 1px solid #3a3a3a;
}

.dashboard-title {
  margin: 0;
  font-size: 2.5rem;
  font-weight: 700;
  color: #7B68EE;
  text-shadow: 0 0 10px rgba(123, 104, 238, 0.3);
}

.status-indicators {
  display: flex;
  gap: 20px;
  align-items: center;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 20px;
  background: #2d2d2d;
  border: 1px solid #4a4a4a;
  transition: all 0.3s ease;
}

.status-item.connected {
  border-color: #00FF00;
}

.status-item .pi-circle-fill {
  color: #FF0000;
  font-size: 0.8rem;
}

.status-item.connected .pi-circle-fill {
  color: #00FF00;
}

.performance-metric {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #FFD700;
  font-weight: 600;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: auto auto auto;
  gap: 25px;
  max-width: 1400px;
  margin: 0 auto;
}

.dashboard-section {
  background: rgba(45, 45, 45, 0.8) !important;
  border: 1px solid #4a4a4a !important;
  border-radius: 12px !important;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.dashboard-section:hover {
  transform: translateY(-5px);
  box-shadow: 0 10px 30px rgba(123, 104, 238, 0.2);
}

.section-header {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #7B68EE !important;
}

.section-header i {
  color: #7B68EE;
  font-size: 1.2rem;
}

.add-button, .refresh-button {
  margin-left: auto !important;
  background: #7B68EE !important;
  border: none !important;
  color: white !important;
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 15px;
}

.project-card {
  background: #3a3a3a;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  border: 2px solid transparent;
}

.project-card:hover {
  transform: scale(1.05);
  box-shadow: 0 5px 20px rgba(123, 104, 238, 0.3);
}

.project-card.selected {
  border-color: #7B68EE;
  box-shadow: 0 0 20px rgba(123, 104, 238, 0.4);
}

.project-thumbnail {
  height: 120px;
  background: #4a4a4a;
  display: flex;
  align-items: center;
  justify-content: center;
}

.project-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.placeholder-thumbnail {
  color: #7B68EE;
  font-size: 2rem;
}

.project-info {
  padding: 15px;
}

.project-info h4 {
  margin: 0 0 8px 0;
  color: #ffffff;
  font-weight: 600;
}

.project-description {
  color: #cccccc;
  font-size: 0.9rem;
  margin: 0 0 12px 0;
  line-height: 1.4;
}

.project-stats {
  display: flex;
  gap: 10px;
}

.stat {
  background: #2d2d2d;
  padding: 4px 8px;
  border-radius: 12px;
  font-size: 0.8rem;
  color: #7B68EE;
}

.add-project-card {
  background: #2d2d2d;
  border: 2px dashed #7B68EE;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 180px;
}

.add-project-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  color: #7B68EE;
}

.add-project-content i {
  font-size: 2rem;
}

.generation-queue {
  max-height: 400px;
  overflow-y: auto;
}

.queue-item {
  background: #3a3a3a;
  border-radius: 8px;
  padding: 15px;
  margin-bottom: 10px;
  border-left: 4px solid #7B68EE;
}

.queue-item.running {
  border-left-color: #FFD700;
}

.queue-item.completed {
  border-left-color: #00FF00;
}

.queue-item.failed {
  border-left-color: #FF0000;
}

.job-info {
  margin-bottom: 10px;
}

.job-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.job-id {
  font-weight: 600;
  color: #7B68EE;
}

.job-prompt {
  color: #ffffff;
  margin: 0 0 8px 0;
  font-size: 0.9rem;
  line-height: 1.4;
}

.job-details {
  display: flex;
  gap: 15px;
  color: #cccccc;
  font-size: 0.8rem;
}

.job-progress {
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-bar {
  flex: 1;
  height: 8px;
  background: #2d2d2d;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #7B68EE, #9b59b6);
  transition: width 0.3s ease;
  border-radius: 4px;
}

.progress-text {
  color: #ffffff;
  font-size: 0.8rem;
  font-weight: 600;
  white-space: nowrap;
}

.eta {
  color: #FFD700;
}

.empty-queue {
  text-align: center;
  color: #888;
  padding: 40px;
}

.empty-queue i {
  font-size: 2rem;
  margin-bottom: 10px;
  display: block;
}

.characters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 15px;
}

.character-card {
  background: #3a3a3a;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.3s ease;
  text-align: center;
}

.character-card:hover {
  transform: scale(1.05);
}

.character-thumbnail {
  height: 100px;
  background: #4a4a4a;
  display: flex;
  align-items: center;
  justify-content: center;
}

.character-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.character-info {
  padding: 12px;
}

.character-info h5 {
  margin: 0 0 5px 0;
  color: #ffffff;
  font-size: 0.9rem;
}

.character-role {
  color: #cccccc;
  font-size: 0.8rem;
  margin: 0 0 8px 0;
}

.consistency-score {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  font-size: 0.8rem;
}

.consistency-score .high-consistency {
  color: #00FF00;
}

.consistency-score .medium-consistency {
  color: #FFD700;
}

.consistency-score .low-consistency {
  color: #FF0000;
}

.recent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 15px;
}

.generation-card {
  background: #3a3a3a;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.3s ease;
}

.generation-card:hover {
  transform: scale(1.05);
}

.generation-thumbnail {
  height: 80px;
  background: #4a4a4a;
  display: flex;
  align-items: center;
  justify-content: center;
}

.generation-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.generation-info {
  padding: 10px;
}

.generation-prompt {
  color: #ffffff;
  font-size: 0.8rem;
  margin: 0 0 8px 0;
  line-height: 1.3;
}

.generation-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.generation-time {
  color: #cccccc;
  font-size: 0.7rem;
}

.quick-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 15px;
}

.action-button {
  width: 100%;
  height: 60px;
  border-radius: 8px !important;
  font-weight: 600 !important;
  transition: all 0.3s ease !important;
}

.action-button.primary {
  background: linear-gradient(135deg, #7B68EE, #9b59b6) !important;
  border: none !important;
  color: white !important;
}

.action-button.secondary {
  background: linear-gradient(135deg, #FFD700, #FFA500) !important;
  border: none !important;
  color: #1a1a1a !important;
}

.action-button.tertiary {
  background: #3a3a3a !important;
  border: 1px solid #7B68EE !important;
  color: #7B68EE !important;
}

.action-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
}

.generate-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field label {
  color: #ffffff;
  font-weight: 600;
}

.performance-overlay {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 1000;
}

.performance-card {
  background: rgba(45, 45, 45, 0.95) !important;
  border: 1px solid #7B68EE !important;
}

.performance-stats {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-label {
  color: #cccccc;
}

.stat-value {
  color: #ffffff;
  font-weight: 600;
}

.stat-value.success {
  color: #00FF00;
}

.queue-count {
  margin-left: auto;
}

/* PrimeVue component overrides for dark theme */
:deep(.p-card) {
  background: #2d2d2d !important;
  color: #ffffff !important;
}

:deep(.p-card-title) {
  color: #7B68EE !important;
}

:deep(.p-card-content) {
  color: #ffffff !important;
}

:deep(.p-dialog) {
  background: #2d2d2d !important;
}

:deep(.p-dialog .p-dialog-header) {
  background: #2d2d2d !important;
  color: #7B68EE !important;
  border-bottom: 1px solid #4a4a4a !important;
}

:deep(.p-dialog .p-dialog-content) {
  background: #2d2d2d !important;
  color: #ffffff !important;
}

:deep(.p-inputtext) {
  background: #3a3a3a !important;
  border: 1px solid #4a4a4a !important;
  color: #ffffff !important;
}

:deep(.p-inputtext:focus) {
  border-color: #7B68EE !important;
  box-shadow: 0 0 0 1px #7B68EE !important;
}

:deep(.p-dropdown) {
  background: #3a3a3a !important;
  border: 1px solid #4a4a4a !important;
  color: #ffffff !important;
}

:deep(.p-dropdown:focus) {
  border-color: #7B68EE !important;
  box-shadow: 0 0 0 1px #7B68EE !important;
}

/* Responsive design */
@media (max-width: 1200px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .projects-grid {
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  }
}

@media (max-width: 768px) {
  .anime-dashboard {
    padding: 15px;
  }

  .dashboard-header {
    flex-direction: column;
    gap: 20px;
    align-items: flex-start;
  }

  .dashboard-title {
    font-size: 2rem;
  }

  .projects-grid {
    grid-template-columns: 1fr 1fr;
  }

  .quick-actions {
    grid-template-columns: 1fr;
  }

  .action-button {
    height: 50px;
  }
}
</style>