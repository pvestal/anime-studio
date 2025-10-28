<template>
  <TowerLayout title="Anime Director Studio">
    <template #actions>
      <TowerButton @click="toggleNewProject">
        {{ showNewProject ? 'Cancel' : 'New Project' }}
      </TowerButton>
    </template>

    <TowerNotification />

    <div class="p-4">
      <!-- New Project Form -->
      <TowerCard v-if="showNewProject" class="p-6 mb-4">
        <h3 class="text-lg font-semibold mb-4">Create New Project</h3>
        <div class="space-y-4">
          <div>
            <label class="block mb-2">Project Name</label>
            <TowerInput v-model="newProject.name" placeholder="My Anime Project" />
          </div>
          <div>
            <label class="block mb-2">Description</label>
            <textarea v-model="newProject.description" 
                      class="w-full p-2 bg-gray-800 rounded" 
                      rows="3" 
                      placeholder="Brief description"></textarea>
          </div>
          <div class="flex gap-2">
            <TowerButton @click="createProject">Create Project</TowerButton>
            <TowerButton @click="showNewProject = false">Cancel</TowerButton>
          </div>
        </div>
      </TowerCard>

      <div class="grid grid-cols-12 gap-4">
        <!-- Left: Projects -->
        <div class="col-span-3">
          <TowerCard class="p-4">
            <h3 class="text-lg font-semibold mb-4">Projects</h3>
            
            <div v-if="projectsLoading" class="text-center py-4">Loading...</div>
            
            <div v-else-if="projects && projects.length > 0" class="space-y-2">
              <div v-for="project in projects" :key="project.id" 
                   class="p-3 rounded cursor-pointer hover:bg-gray-800 transition"
                   :class="{ 'bg-blue-900': selectedProject?.id === project.id }"
                   @click="selectProject(project)">
                <h4 class="font-semibold text-sm">{{ project.name }}</h4>
                <p class="text-xs text-gray-400 mt-1 truncate">{{ project.description }}</p>
              </div>
            </div>
            
            <div v-else class="text-center text-gray-400 py-4 text-sm">
              No projects yet
            </div>
          </TowerCard>
        </div>

        <!-- Center: Scenes -->
        <div class="col-span-6">
          <TowerCard class="p-4">
            <div class="flex justify-between items-center mb-4">
              <h3 class="text-lg font-semibold">
                {{ selectedProject ? selectedProject.name + ' - Scenes' : 'Select a project' }}
              </h3>
              <TowerButton v-if="selectedProject && !showNewScene" @click="showNewScene = true">
                Add Scene
              </TowerButton>
            </div>

            <!-- New Scene Form -->
            <div v-if="showNewScene" class="mb-4 p-4 bg-gray-800 rounded">
              <h4 class="font-semibold mb-3">New Scene</h4>
              <div class="space-y-3">
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="block text-sm mb-1">Scene #</label>
                    <TowerInput v-model.number="newScene.scene_number" type="number" />
                  </div>
                  <div>
                    <label class="block text-sm mb-1">Characters</label>
                    <TowerInput v-model="newScene.characters" placeholder="hero, villain" />
                  </div>
                </div>
                <div>
                  <label class="block text-sm mb-1">Description</label>
                  <textarea v-model="newScene.description" 
                            class="w-full p-2 bg-gray-900 rounded text-sm" 
                            rows="2" 
                            placeholder="Scene description"></textarea>
                </div>
                <div class="flex gap-2">
                  <TowerButton @click="createScene">Add Scene</TowerButton>
                  <TowerButton @click="showNewScene = false">Cancel</TowerButton>
                </div>
              </div>
            </div>

            <!-- Scenes List -->
            <div v-if="!selectedProject" class="text-center text-gray-400 py-8">
              Select a project to view scenes
            </div>
            
            <div v-else-if="scenesLoading" class="text-center py-4">Loading scenes...</div>
            
            <div v-else-if="scenes && scenes.length > 0" class="space-y-2">
              <div v-for="scene in scenes" :key="scene.id"
                   class="p-3 bg-gray-800 rounded cursor-pointer hover:bg-gray-750 transition"
                   :class="{ 'border-2 border-blue-500': selectedScene?.id === scene.id }"
                   @click="selectScene(scene)">
                <div class="flex justify-between items-start">
                  <div class="flex-1">
                    <div class="flex gap-2 items-center mb-1">
                      <span class="text-xs font-mono text-gray-400">Scene {{ scene.scene_number }}</span>
                      <span class="text-xs px-2 py-0.5 rounded" :class="getStatusClass(scene.status)">
                        {{ scene.status }}
                      </span>
                    </div>
                    <p class="text-sm">{{ scene.description || 'No description' }}</p>
                    <p class="text-xs text-gray-400 mt-1">{{ scene.characters || 'No characters' }}</p>
                  </div>
                  <div class="flex gap-2">
                    <TowerButton v-if="scene.status === 'pending'" 
                                 @click.stop="generateScene(scene)" 
                                 class="text-xs">
                      Generate
                    </TowerButton>
                    <a v-if="scene.video_path" 
                       :href="scene.video_path" 
                       class="text-blue-400 hover:underline text-xs"
                       @click.stop>
                      Video
                    </a>
                  </div>
                </div>
              </div>
            </div>
            
            <div v-else class="text-center text-gray-400 py-8 text-sm">
              No scenes yet
            </div>
          </TowerCard>
        </div>

        <!-- Right: Properties -->
        <div class="col-span-3">
          <TowerCard class="p-4">
            <h3 class="text-lg font-semibold mb-4">Properties</h3>
            
            <div v-if="selectedScene" class="space-y-3">
              <div>
                <label class="block text-sm mb-1">Scene #</label>
                <TowerInput v-model.number="selectedScene.scene_number" type="number" disabled />
              </div>
              <div>
                <label class="block text-sm mb-1">Description</label>
                <textarea v-model="selectedScene.description" 
                          class="w-full p-2 bg-gray-800 rounded text-sm" 
                          rows="3"></textarea>
              </div>
              <div>
                <label class="block text-sm mb-1">Characters</label>
                <TowerInput v-model="selectedScene.characters" />
              </div>
              <div>
                <label class="block text-sm mb-1">Status</label>
                <select v-model="selectedScene.status" class="w-full p-2 bg-gray-800 rounded text-sm">
                  <option value="pending">Pending</option>
                  <option value="processing">Processing</option>
                  <option value="completed">Completed</option>
                  <option value="failed">Failed</option>
                </select>
              </div>
              <TowerButton @click="updateScene" class="w-full">Save</TowerButton>
            </div>
            
            <div v-else-if="selectedProject" class="space-y-3">
              <div>
                <label class="block text-sm mb-1">Project Name</label>
                <TowerInput v-model="selectedProject.name" />
              </div>
              <div>
                <label class="block text-sm mb-1">Description</label>
                <textarea v-model="selectedProject.description" 
                          class="w-full p-2 bg-gray-800 rounded text-sm" 
                          rows="3"></textarea>
              </div>
              <TowerButton @click="updateProject" class="w-full">Save Project</TowerButton>
            </div>
            
            <div v-else class="text-center text-gray-400 py-8 text-sm">
              Select a project or scene
            </div>
          </TowerCard>
        </div>
      </div>
    </div>
  </TowerLayout>
</template>

<script setup>
import { ref, watch } from 'vue'
import { 
  TowerLayout, TowerCard, TowerButton, TowerInput,
  TowerNotification, usePolling, useApi, useNotifications 
} from '@tower/ui-components'

const { success, error } = useNotifications()

// State
const selectedProject = ref(null)
const selectedScene = ref(null)
const showNewProject = ref(false)
const showNewScene = ref(false)

const newProject = ref({ name: '', description: '' })
const newScene = ref({ scene_number: 1, description: '', characters: '' })

// API Integration
const { data: projects, loading: projectsLoading, refetch: refetchProjects } = 
  usePolling('/api/anime/projects', { interval: 5000 })

const scenes = ref([])
const scenesLoading = ref(false)

// Watch for project selection to load scenes
watch(selectedProject, async (project) => {
  if (project) {
    scenesLoading.value = true
    try {
      const { execute } = useApi(`/api/anime/scenes?project_id=${project.id}`)
      const result = await execute()
      scenes.value = result.data || []
    } catch (e) {
      console.error('Failed to load scenes:', e)
      scenes.value = []
    } finally {
      scenesLoading.value = false
    }
  } else {
    scenes.value = []
  }
})

// Actions
const toggleNewProject = () => {
  showNewProject.value = !showNewProject.value
}

const selectProject = (project) => {
  selectedProject.value = project
  selectedScene.value = null
  showNewScene.value = false
}

const selectScene = (scene) => {
  selectedScene.value = scene
}

const createProject = async () => {
  try {
    const { execute } = useApi('/api/anime/projects', { method: 'POST' })
    await execute({ body: JSON.stringify(newProject.value) })
    success('Project created!')
    showNewProject.value = false
    newProject.value = { name: '', description: '' }
    refetchProjects()
  } catch (e) {
    error(`Failed: ${e.message}`)
  }
}

const createScene = async () => {
  try {
    const { execute } = useApi('/api/anime/scenes', { method: 'POST' })
    await execute({ 
      body: JSON.stringify({
        ...newScene.value,
        project_id: selectedProject.value.id
      })
    })
    success('Scene added!')
    showNewScene.value = false
    newScene.value = { scene_number: (scenes.value?.length || 0) + 1, description: '', characters: '' }
    // Reload scenes
    selectProject(selectedProject.value)
  } catch (e) {
    error(`Failed: ${e.message}`)
  }
}

const updateScene = async () => {
  try {
    const { execute } = useApi(`/api/anime/scenes/${selectedScene.value.id}`, { method: 'PUT' })
    await execute({ body: JSON.stringify(selectedScene.value) })
    success('Scene updated!')
    selectProject(selectedProject.value)
  } catch (e) {
    error(`Failed: ${e.message}`)
  }
}

const updateProject = async () => {
  try {
    const { execute } = useApi(`/api/anime/projects/${selectedProject.value.id}`, { method: 'PUT' })
    await execute({ body: JSON.stringify(selectedProject.value) })
    success('Project updated!')
    refetchProjects()
  } catch (e) {
    error(`Failed: ${e.message}`)
  }
}

const generateScene = async (scene) => {
  try {
    success(`Starting generation for Scene ${scene.scene_number}...`)

    // Update scene status to processing
    scene.status = 'processing'
    await updateScene()

    // Generate the video using the anime service
    const { execute } = useApi('/api/anime/generate', { method: 'POST' })
    const result = await execute({
      body: JSON.stringify({
        prompt: scene.description || 'anime scene',
        character: scene.characters || 'anime character',
        duration: 5,
        frames: 120,
        use_apple_music: false
      })
    })

    if (result.data?.generation_id) {
      // Create git commit for this scene generation
      await createSceneCommit(scene, 'Generated video for scene')

      // Poll for completion
      pollGenerationStatus(result.data.generation_id, scene)
      success(`Generation started! ID: ${result.data.generation_id}`)
    }
  } catch (e) {
    error(`Generation failed: ${e.message}`)
    scene.status = 'failed'
    await updateScene()
  }
}

const pollGenerationStatus = async (generationId, scene) => {
  const checkStatus = async () => {
    try {
      const { execute } = useApi(`/api/anime/status/${generationId}`)
      const result = await execute()
      const status = result.data

      if (status.status === 'completed') {
        scene.status = 'completed'
        scene.video_path = status.output_file
        await updateScene()
        success(`Scene ${scene.scene_number} generation complete!`)

        // Create completion commit
        await createSceneCommit(scene, `Completed scene ${scene.scene_number} - ${status.message}`)
      } else if (status.status === 'failed') {
        scene.status = 'failed'
        await updateScene()
        error(`Scene ${scene.scene_number} generation failed: ${status.message}`)
      } else if (status.status === 'generating') {
        // Still processing, check again in 5 seconds
        setTimeout(checkStatus, 5000)
      }
    } catch (e) {
      console.error('Status check failed:', e)
      setTimeout(checkStatus, 10000) // Retry in 10 seconds
    }
  }

  // Start checking
  setTimeout(checkStatus, 2000)
}

const createSceneCommit = async (scene, message) => {
  try {
    const { execute } = useApi('/api/anime/git/commits', { method: 'POST' })
    await execute({
      body: JSON.stringify({
        project_id: selectedProject.value.id,
        branch_name: 'main',
        message: message,
        author: 'director_studio',
        scene_data: {
          scene_id: scene.id,
          scene_number: scene.scene_number,
          description: scene.description,
          characters: scene.characters,
          status: scene.status,
          video_path: scene.video_path,
          timestamp: new Date().toISOString()
        }
      })
    })
  } catch (e) {
    console.warn('Failed to create git commit:', e)
  }
}

const getStatusClass = (status) => {
  return {
    'pending': 'bg-gray-700 text-gray-300',
    'processing': 'bg-blue-900 text-blue-300',
    'completed': 'bg-green-900 text-green-300',
    'failed': 'bg-red-900 text-red-300'
  }[status] || 'bg-gray-700'
}
</script>

<style scoped>
textarea {
  font-family: inherit;
}
</style>
