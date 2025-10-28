<template>
  <TowerLayout title="Anime Director Studio">
    <template #actions>
      <div class="flex gap-2 items-center">
        <div class="flex items-center gap-2 px-3 py-1 rounded text-xs"
             :class="{
               'bg-green-900 text-green-300': connectionStatus === 'connected',
               'bg-yellow-900 text-yellow-300': connectionStatus === 'connecting',
               'bg-red-900 text-red-300': connectionStatus === 'disconnected'
             }">
          <div class="w-2 h-2 rounded-full"
               :class="{
                 'bg-green-400': connectionStatus === 'connected',
                 'bg-yellow-400': connectionStatus === 'connecting',
                 'bg-red-400': connectionStatus === 'disconnected'
               }"></div>
          {{ connectionStatus === 'connected' ? 'Live' : connectionStatus }}
        </div>
        <TowerButton @click="showSoundtrackPanel = !showSoundtrackPanel">
          🎵 Soundtracks
        </TowerButton>
        <TowerButton @click="toggleNewProject">
          {{ showNewProject ? 'Cancel' : 'New Project' }}
        </TowerButton>
      </div>
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

      <!-- Soundtrack Panel -->
      <TowerCard v-if="showSoundtrackPanel" class="p-4 mt-4">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-semibold">🎵 Soundtrack Manager</h3>
          <TowerButton @click="showSoundtrackPanel = false">Close</TowerButton>
        </div>

        <div class="grid grid-cols-12 gap-4">
          <!-- Search & Controls -->
          <div class="col-span-4">
            <div class="space-y-3">
              <div>
                <label class="block text-sm mb-1">Search Soundtracks</label>
                <TowerInput v-model="soundtrackSearch" placeholder="anime cyberpunk epic" />
              </div>
              <div>
                <label class="block text-sm mb-1">Mood</label>
                <select v-model="soundtrackMood" class="w-full p-2 bg-gray-800 rounded text-sm">
                  <option value="cinematic">Cinematic</option>
                  <option value="epic">Epic</option>
                  <option value="emotional">Emotional</option>
                  <option value="romantic">Romantic</option>
                  <option value="mysterious">Mysterious</option>
                  <option value="energetic">Energetic</option>
                </select>
              </div>
              <TowerButton @click="searchSoundtracks" class="w-full">Search</TowerButton>
            </div>

            <!-- Current Selection -->
            <div v-if="selectedSoundtrack" class="mt-4 p-3 bg-gray-800 rounded">
              <h4 class="font-semibold text-sm mb-2">Selected Track</h4>
              <p class="text-sm">{{ selectedSoundtrack.name }}</p>
              <p class="text-xs text-gray-400">{{ selectedSoundtrack.artist }}</p>
            </div>
          </div>

          <!-- Search Results -->
          <div class="col-span-4">
            <h4 class="font-semibold mb-3">Search Results</h4>
            <div class="space-y-2 max-h-64 overflow-y-auto">
              <div v-for="track in soundtracks" :key="track.id"
                   class="p-2 bg-gray-800 rounded cursor-pointer hover:bg-gray-750"
                   @click="selectSoundtrack(track)">
                <p class="text-sm font-medium">{{ track.name }}</p>
                <p class="text-xs text-gray-400">{{ track.artist }}</p>
                <p class="text-xs text-blue-400" v-if="track.anime_relevance_score">
                  Match: {{ Math.round(track.anime_relevance_score * 100) }}%
                </p>
              </div>
              <div v-if="soundtracks.length === 0" class="text-center text-gray-400 py-4 text-sm">
                Search for soundtracks above
              </div>
            </div>
          </div>

          <!-- Playlists -->
          <div class="col-span-4">
            <h4 class="font-semibold mb-3">Your Playlists</h4>
            <div class="space-y-2 max-h-64 overflow-y-auto">
              <div v-for="playlist in playlists" :key="playlist.id"
                   class="p-2 bg-gray-800 rounded cursor-pointer hover:bg-gray-750"
                   :class="{ 'border border-green-500': playlist.anime_relevance }">
                <p class="text-sm font-medium">{{ playlist.name }}</p>
                <p class="text-xs text-gray-400">{{ playlist.track_count }} tracks</p>
                <span v-if="playlist.anime_relevance" class="text-xs px-2 py-0.5 bg-green-900 text-green-300 rounded">
                  Anime Related
                </span>
              </div>
              <div v-if="playlists.length === 0" class="text-center text-gray-400 py-4 text-sm">
                No playlists available
              </div>
            </div>
          </div>
        </div>
      </TowerCard>

      <!-- Real-time Updates Panel -->
      <TowerCard v-if="realTimeUpdates.length > 0" class="p-4 mt-4">
        <h3 class="text-lg font-semibold mb-4">🔴 Live Updates</h3>
        <div class="space-y-2 max-h-32 overflow-y-auto">
          <div v-for="update in realTimeUpdates.slice(0, 10)" :key="update.id"
               class="flex justify-between items-center p-2 bg-gray-800 rounded text-sm">
            <div>
              <span class="font-medium">{{ update.message }}</span>
              <span class="text-gray-400 ml-2">({{ update.progress }}%)</span>
            </div>
            <span class="text-xs text-gray-500">
              {{ new Date(update.timestamp).toLocaleTimeString() }}
            </span>
          </div>
        </div>
      </TowerCard>
    </div>
  </TowerLayout>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
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

// WebSocket and Real-time State
const websocket = ref(null)
const isConnected = ref(false)
const connectionStatus = ref('disconnected')
const realTimeUpdates = ref([])

// Apple Music Integration State
const soundtracks = ref([])
const playlists = ref([])
const selectedSoundtrack = ref(null)
const showSoundtrackPanel = ref(false)
const soundtrackSearch = ref('')
const soundtrackMood = ref('cinematic')

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

// WebSocket Management
const connectWebSocket = () => {
  const wsUrl = `ws://${window.location.hostname}:8328/ws/director-studio`
  websocket.value = new WebSocket(wsUrl)
  connectionStatus.value = 'connecting'

  websocket.value.onopen = () => {
    isConnected.value = true
    connectionStatus.value = 'connected'
    success('Real-time communication established')

    // Send ping to keep connection alive
    setInterval(() => {
      if (websocket.value?.readyState === WebSocket.OPEN) {
        websocket.value.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)
  }

  websocket.value.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data)
      handleWebSocketMessage(message)
    } catch (e) {
      console.error('WebSocket message parse error:', e)
    }
  }

  websocket.value.onclose = () => {
    isConnected.value = false
    connectionStatus.value = 'disconnected'
    error('Real-time communication lost')

    // Attempt to reconnect after 3 seconds
    setTimeout(() => {
      if (!isConnected.value) {
        connectWebSocket()
      }
    }, 3000)
  }

  websocket.value.onerror = (error) => {
    console.error('WebSocket error:', error)
    connectionStatus.value = 'error'
  }
}

const handleWebSocketMessage = (message) => {
  switch (message.type) {
    case 'generation_update':
      handleGenerationUpdate(message)
      break
    case 'project_update':
      handleProjectUpdate(message)
      break
    case 'pong':
      // Connection alive confirmation
      break
    case 'service_status':
      handleServiceStatus(message)
      break
    default:
      console.log('Unknown WebSocket message:', message)
  }
}

const handleGenerationUpdate = (message) => {
  const { generation_id, data } = message
  realTimeUpdates.value.unshift({
    id: generation_id,
    type: 'generation',
    ...data,
    timestamp: new Date().toISOString()
  })

  // Update scene status if it matches current generation
  if (scenes.value) {
    const scene = scenes.value.find(s => s.generation_id === generation_id)
    if (scene) {
      scene.status = data.status
      scene.progress = data.progress
      if (data.output_file) {
        scene.video_path = data.output_file
      }
    }
  }

  // Show real-time notification
  if (data.status === 'completed') {
    success(`Scene generation completed! ${data.message}`)
  } else if (data.status === 'failed') {
    error(`Scene generation failed: ${data.message}`)
  } else {
    success(`Generation update: ${data.message} (${data.progress}%)`)
  }
}

const handleProjectUpdate = (message) => {
  // Refresh projects list
  refetchProjects()
  success('Project updated in real-time')
}

const handleServiceStatus = (message) => {
  console.log('Service Status:', message)
}

const subscribeToGeneration = (generationId) => {
  if (websocket.value?.readyState === WebSocket.OPEN) {
    websocket.value.send(JSON.stringify({
      type: 'subscribe_generation',
      generation_id: generationId
    }))
  }
}

// Apple Music Integration
const searchSoundtracks = async () => {
  try {
    const { execute } = useApi('/api/soundtracks/search')
    const result = await execute({
      query: soundtrackSearch.value || 'anime soundtrack',
      mood: soundtrackMood.value,
      limit: 20
    })
    soundtracks.value = result.data?.results || []
    showSoundtrackPanel.value = true
    success(`Found ${soundtracks.value.length} soundtrack options`)
  } catch (e) {
    error(`Soundtrack search failed: ${e.message}`)
  }
}

const loadUserPlaylists = async () => {
  try {
    const { execute } = useApi('/api/soundtracks/playlists')
    const result = await execute()
    playlists.value = result.data?.playlists || []
    success(`Loaded ${playlists.value.length} playlists`)
  } catch (e) {
    error(`Failed to load playlists: ${e.message}`)
  }
}

const selectSoundtrack = (soundtrack) => {
  selectedSoundtrack.value = soundtrack
  success(`Selected: ${soundtrack.name} by ${soundtrack.artist}`)
}

// Lifecycle
onMounted(() => {
  connectWebSocket()
  loadUserPlaylists()
})

onUnmounted(() => {
  if (websocket.value) {
    websocket.value.close()
  }
})
</script>

<style scoped>
textarea {
  font-family: inherit;
}
</style>
