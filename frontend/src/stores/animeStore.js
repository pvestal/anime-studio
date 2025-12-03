import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * Anime Production Store - Centralized state management for anime production workflows
 * Manages projects, characters, scenes, generation history, and Echo coordination
 */
export const useAnimeStore = defineStore('anime', () => {
  // ==================== STATE ====================

  // Project Management
  const projects = ref([])
  const selectedProject = ref(null)
  const projectBibles = ref({}) // Map of project_id -> bible data

  // Character Management
  const characters = ref([])
  const selectedCharacter = ref(null)
  const characterSheets = ref({}) // Map of character_name -> sheet data
  const characterConsistencyScores = ref({})

  // Scene Management
  const scenes = ref([])
  const selectedScene = ref(null)
  const sceneTemplates = ref([])

  // Generation Management
  const generationHistory = ref([])
  const currentGeneration = ref(null)
  const generationQueue = ref([])

  // WebSocket Management
  const wsConnection = ref(null)
  const wsConnected = ref(false)
  const jobProgress = ref({})
  const jobETAs = ref({})

  // Echo Coordination
  const echoCoordination = ref(null)
  const echoStatus = ref('disconnected')
  const echoMessages = ref([])

  // UI State
  const loading = ref(false)
  const error = ref(null)
  const notifications = ref([])
  const activeView = ref('console') // console, studio, timeline

  // ==================== COMPUTED ====================

  const currentProjectBible = computed(() => {
    return selectedProject.value
      ? projectBibles.value[selectedProject.value.id]
      : null
  })

  const currentProjectCharacters = computed(() => {
    return selectedProject.value
      ? characters.value.filter(char => char.project_id === selectedProject.value.id)
      : []
  })

  const currentProjectScenes = computed(() => {
    return selectedProject.value
      ? scenes.value.filter(scene => scene.project_id === selectedProject.value.id)
      : []
  })

  const recentGenerations = computed(() => {
    return generationHistory.value
      .filter(gen => selectedProject.value ? gen.project_id === selectedProject.value.id : true)
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      .slice(0, 10)
  })

  const generationStats = computed(() => {
    const total = generationHistory.value.length
    const successful = generationHistory.value.filter(gen => gen.status === 'completed').length
    const failed = generationHistory.value.filter(gen => gen.status === 'failed').length
    const pending = generationHistory.value.filter(gen => gen.status === 'pending').length

    return {
      total,
      successful,
      failed,
      pending,
      successRate: total > 0 ? (successful / total * 100).toFixed(1) : 0
    }
  })

  // ==================== ACTIONS ====================

  // Project Actions
  async function loadProjects() {
    try {
      loading.value = true
      error.value = null

      const response = await fetch('/api/anime/projects')
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

      const data = await response.json()
      projects.value = data

      addNotification('Projects loaded successfully', 'success')
    } catch (err) {
      error.value = `Failed to load projects: ${err.message}`
      addNotification(error.value, 'error')
    } finally {
      loading.value = false
    }
  }

  async function createProject(projectData) {
    try {
      loading.value = true
      error.value = null

      const response = await fetch('/api/anime/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(projectData)
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

      const newProject = await response.json()
      projects.value.push(newProject)
      selectedProject.value = newProject

      addNotification(`Project "${newProject.name}" created successfully`, 'success')
      return newProject
    } catch (err) {
      error.value = `Failed to create project: ${err.message}`
      addNotification(error.value, 'error')
      throw err
    } finally {
      loading.value = false
    }
  }

  async function updateProject(projectId, updates) {
    try {
      const response = await fetch(`/api/anime/projects/${projectId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

      const updatedProject = await response.json()
      const index = projects.value.findIndex(p => p.id === projectId)
      if (index !== -1) {
        projects.value[index] = updatedProject
        if (selectedProject.value?.id === projectId) {
          selectedProject.value = updatedProject
        }
      }

      addNotification('Project updated successfully', 'success')
      return updatedProject
    } catch (err) {
      error.value = `Failed to update project: ${err.message}`
      addNotification(error.value, 'error')
      throw err
    }
  }

  function selectProject(project) {
    selectedProject.value = project
    // Load associated data
    if (project) {
      loadProjectBible(project.id)
      loadProjectCharacters(project.id)
      loadProjectScenes(project.id)
    }
  }

  // Project Bible Actions
  async function loadProjectBible(projectId) {
    try {
      const response = await fetch(`/api/anime/projects/${projectId}/bible`)
      if (response.ok) {
        const bible = await response.json()
        projectBibles.value[projectId] = bible
      } else if (response.status !== 404) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
    } catch (err) {
      console.error(`Failed to load project bible: ${err.message}`)
    }
  }

  async function createProjectBible(projectId, bibleData) {
    try {
      const response = await fetch(`/api/anime/projects/${projectId}/bible`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bibleData)
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

      const bible = await response.json()
      projectBibles.value[projectId] = bible

      addNotification('Project bible created successfully', 'success')
      return bible
    } catch (err) {
      error.value = `Failed to create project bible: ${err.message}`
      addNotification(error.value, 'error')
      throw err
    }
  }

  async function updateProjectBible(projectId, updates) {
    try {
      const response = await fetch(`/api/anime/projects/${projectId}/bible`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

      const updatedBible = await response.json()
      projectBibles.value[projectId] = updatedBible

      addNotification('Project bible updated successfully', 'success')
      return updatedBible
    } catch (err) {
      error.value = `Failed to update project bible: ${err.message}`
      addNotification(error.value, 'error')
      throw err
    }
  }

  // Character Actions
  async function loadProjectCharacters(projectId) {
    try {
      const response = await fetch(`/api/anime/projects/${projectId}/bible/characters`)
      if (response.ok) {
        const projectCharacters = await response.json()
        // Update characters array with project characters
        characters.value = characters.value.filter(char => char.project_id !== projectId)
        characters.value.push(...projectCharacters.map(char => ({ ...char, project_id: projectId })))
      }
    } catch (err) {
      console.error(`Failed to load project characters: ${err.message}`)
    }
  }

  async function addCharacterToBible(projectId, characterData) {
    try {
      const response = await fetch(`/api/anime/projects/${projectId}/bible/characters`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(characterData)
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

      const newCharacter = await response.json()
      characters.value.push({ ...newCharacter, project_id: projectId })

      addNotification(`Character "${characterData.name}" added to project bible`, 'success')
      return newCharacter
    } catch (err) {
      error.value = `Failed to add character: ${err.message}`
      addNotification(error.value, 'error')
      throw err
    }
  }

  async function generateCharacterSheet(characterName, projectId) {
    try {
      loading.value = true

      // Call Character Consistency Engine
      const response = await fetch('/api/anime/character-consistency/generate-sheet', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character_name: characterName, project_id: projectId })
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

      const characterSheet = await response.json()
      characterSheets.value[characterName] = characterSheet

      addNotification(`Character sheet generated for ${characterName}`, 'success')
      return characterSheet
    } catch (err) {
      error.value = `Failed to generate character sheet: ${err.message}`
      addNotification(error.value, 'error')
      throw err
    } finally {
      loading.value = false
    }
  }

  async function validateCharacterConsistency(characterName, imagePath) {
    try {
      const response = await fetch('/api/anime/character-consistency/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character_name: characterName, image_path: imagePath })
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

      const validation = await response.json()
      characterConsistencyScores.value[characterName] = validation.consistency_score

      const status = validation.status === 'approved' ? 'success' : 'warning'\n      addNotification(\n        `Character validation: ${validation.consistency_score.toFixed(3)} - ${validation.status}`,\n        status\n      )\n      \n      return validation\n    } catch (err) {\n      error.value = `Failed to validate character: ${err.message}`\n      addNotification(error.value, 'error')\n      throw err\n    }\n  }\n  \n  function selectCharacter(character) {\n    selectedCharacter.value = character\n  }\n  \n  // Scene Actions\n  async function loadProjectScenes(projectId) {\n    try {\n      const response = await fetch(`/api/anime/projects/${projectId}/scenes`)\n      if (response.ok) {\n        const projectScenes = await response.json()\n        scenes.value = scenes.value.filter(scene => scene.project_id !== projectId)\n        scenes.value.push(...projectScenes)\n      }\n    } catch (err) {\n      console.error(`Failed to load project scenes: ${err.message}`)\n    }\n  }\n  \n  function selectScene(scene) {\n    selectedScene.value = scene\n  }\n  \n  // Generation Actions\n  async function startGeneration(generationRequest) {\n    try {\n      loading.value = true\n      \n      const response = await fetch('/api/anime/generate', {\n        method: 'POST',\n        headers: { 'Content-Type': 'application/json' },\n        body: JSON.stringify(generationRequest)\n      })\n      \n      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)\n      \n      const generation = await response.json()\n      generationHistory.value.unshift(generation)\n      currentGeneration.value = generation\n      \n      addNotification('Generation started successfully', 'success')\n      return generation\n    } catch (err) {\n      error.value = `Failed to start generation: ${err.message}`\n      addNotification(error.value, 'error')\n      throw err\n    } finally {\n      loading.value = false\n    }\n  }\n  \n  async function loadGenerationHistory() {\n    try {\n      const response = await fetch('/api/anime/generations')\n      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)\n      \n      const history = await response.json()\n      generationHistory.value = history\n    } catch (err) {\n      console.error(`Failed to load generation history: ${err.message}`)\n    }\n  }\n  \n  // Echo Brain Coordination\n  async function connectToEcho() {\n    try {\n      const response = await fetch('/api/echo/health')\n      if (response.ok) {\n        echoStatus.value = 'connected'\n        addNotification('Connected to Echo Brain', 'success')\n        return true\n      } else {\n        throw new Error('Echo Brain not available')\n      }\n    } catch (err) {\n      echoStatus.value = 'disconnected'\n      console.error(`Failed to connect to Echo: ${err.message}`)\n      return false\n    }\n  }\n  \n  async function sendEchoMessage(message, context = 'anime_production') {\n    try {\n      const response = await fetch('/api/echo/query', {\n        method: 'POST',\n        headers: { 'Content-Type': 'application/json' },\n        body: JSON.stringify({\n          query: message,\n          context: context,\n          model: 'qwen2.5-coder:32b'\n        })\n      })\n      \n      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)\n      \n      const echoResponse = await response.json()\n      \n      // Add to message history\n      echoMessages.value.push({\n        type: 'user',\n        content: message,\n        timestamp: new Date().toISOString()\n      })\n      \n      echoMessages.value.push({\n        type: 'echo',\n        content: echoResponse.response || echoResponse.result,\n        timestamp: new Date().toISOString()\n      })\n      \n      return echoResponse\n    } catch (err) {\n      error.value = `Failed to send Echo message: ${err.message}`\n      addNotification(error.value, 'error')\n      throw err\n    }\n  }\n  \n  async function requestEchoCharacterGeneration(characterName, projectId, additionalInstructions = '') {\n    const message = `Generate character ${characterName} for project ${selectedProject.value?.name || projectId}.\n    \nProject context: ${currentProjectBible.value?.description || 'No project bible available'}\nCharacter requirements: Use project bible specifications\nAdditional instructions: ${additionalInstructions}`\n    \n    return await sendEchoMessage(message, 'character_generation')\n  }\n  \n  async function requestEchoSceneGeneration(sceneDescription, characters = []) {\n    const message = `Generate scene: ${sceneDescription}\n    \nProject: ${selectedProject.value?.name || 'Unknown'}\nCharacters involved: ${characters.join(', ')}\nProject context: ${currentProjectBible.value?.description || 'No project bible available'}`\n    \n    return await sendEchoMessage(message, 'scene_generation')\n  }\n  \n  // Utility Actions\n  function addNotification(message, type = 'info', duration = 5000) {\n    const notification = {\n      id: Date.now() + Math.random(),\n      message,\n      type,\n      timestamp: new Date().toISOString()\n    }\n    \n    notifications.value.push(notification)\n    \n    // Auto-remove after duration\n    setTimeout(() => {\n      removeNotification(notification.id)\n    }, duration)\n    \n    return notification\n  }\n  \n  function removeNotification(id) {\n    const index = notifications.value.findIndex(n => n.id === id)\n    if (index !== -1) {\n      notifications.value.splice(index, 1)\n    }\n  }\n  \n  function clearError() {\n    error.value = null\n  }\n  \n  function setActiveView(view) {\n    activeView.value = view\n  }\n  \n  // Reset Functions\n  function resetStore() {\n    projects.value = []\n    selectedProject.value = null\n    projectBibles.value = {}\n    characters.value = []\n    selectedCharacter.value = null\n    characterSheets.value = {}\n    characterConsistencyScores.value = {}\n    scenes.value = []\n    selectedScene.value = null\n    generationHistory.value = []\n    currentGeneration.value = null\n    echoMessages.value = []\n    notifications.value = []\n    error.value = null\n  }\n  \n  // ==================== RETURN STORE ====================\n  \n  return {\n    // State\n    projects,\n    selectedProject,\n    projectBibles,\n    characters,\n    selectedCharacter,\n    characterSheets,\n    characterConsistencyScores,\n    scenes,\n    selectedScene,\n    sceneTemplates,\n    generationHistory,\n    currentGeneration,\n    generationQueue,\n    echoCoordination,\n    echoStatus,\n    echoMessages,\n    loading,\n    error,\n    notifications,\n    activeView,\n    \n    // Computed\n    currentProjectBible,\n    currentProjectCharacters,\n    currentProjectScenes,\n    recentGenerations,\n    generationStats,\n    \n    // Actions\n    loadProjects,\n    createProject,\n    updateProject,\n    selectProject,\n    loadProjectBible,\n    createProjectBible,\n    updateProjectBible,\n    loadProjectCharacters,\n    addCharacterToBible,\n    generateCharacterSheet,\n    validateCharacterConsistency,\n    selectCharacter,\n    loadProjectScenes,\n    selectScene,\n    startGeneration,\n    loadGenerationHistory,\n    connectToEcho,\n    sendEchoMessage,\n    requestEchoCharacterGeneration,\n    requestEchoSceneGeneration,\n    addNotification,\n    removeNotification,\n    clearError,\n    setActiveView,\n    resetStore\n  }\n})