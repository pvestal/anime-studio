import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  interactiveApi,
  type InteractiveScene,
  type InteractiveImageStatus,
  type InteractiveSession,
} from '@/api/interactive'

export const useInteractiveStore = defineStore('interactive', () => {
  // Session state
  const sessionId = ref<string | null>(null)
  const projectId = ref<number | null>(null)
  const projectName = ref('')
  const isEnded = ref(false)
  const relationships = ref<Record<string, number>>({})
  const variables = ref<Record<string, string | number | boolean>>({})

  // Scene state
  const currentScene = ref<InteractiveScene | null>(null)
  const sceneHistory = ref<InteractiveScene[]>([])
  const imageStatus = ref<InteractiveImageStatus>({ status: 'pending', progress: 0, url: null })

  // UI state
  const loading = ref(false)
  const choosing = ref(false)
  const error = ref<string | null>(null)
  const imagePollingTimer = ref<ReturnType<typeof setInterval> | null>(null)

  // Active sessions
  const activeSessions = ref<InteractiveSession[]>([])

  const isPlaying = computed(() => sessionId.value !== null && !isEnded.value)
  const sceneCount = computed(() => sceneHistory.value.length)

  async function startSession(pid: number, characterSlugs?: string[]) {
    loading.value = true
    error.value = null
    try {
      const resp = await interactiveApi.startSession(pid, characterSlugs)
      sessionId.value = resp.session_id
      projectId.value = pid
      currentScene.value = resp.scene
      imageStatus.value = resp.image
      sceneHistory.value = [resp.scene]
      isEnded.value = false
      relationships.value = {}
      variables.value = {}

      // Start polling for image
      startImagePolling(resp.scene.scene_index)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to start session'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function submitChoice(choiceIndex: number) {
    if (!sessionId.value || choosing.value) return
    choosing.value = true
    error.value = null
    stopImagePolling()
    try {
      const resp = await interactiveApi.submitChoice(sessionId.value, choiceIndex)
      currentScene.value = resp.scene
      imageStatus.value = resp.image
      sceneHistory.value.push(resp.scene)
      isEnded.value = resp.session_ended

      if (resp.session_ended) {
        // Fetch final relationships
        const session = await interactiveApi.getSession(sessionId.value)
        relationships.value = session.relationships || {}
        variables.value = session.variables || {}
      } else {
        startImagePolling(resp.scene.scene_index)
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to submit choice'
    } finally {
      choosing.value = false
    }
  }

  function startImagePolling(sceneIdx: number) {
    stopImagePolling()
    if (!sessionId.value) return
    // Don't poll if already ready
    if (imageStatus.value.status === 'ready') return

    const sid = sessionId.value
    imagePollingTimer.value = setInterval(async () => {
      try {
        const status = await interactiveApi.getImageStatus(sid, sceneIdx)
        imageStatus.value = status
        if (status.status === 'ready' || status.status === 'failed') {
          stopImagePolling()
        }
      } catch {
        stopImagePolling()
      }
    }, 2000)
  }

  function stopImagePolling() {
    if (imagePollingTimer.value) {
      clearInterval(imagePollingTimer.value)
      imagePollingTimer.value = null
    }
  }

  async function endSession() {
    if (sessionId.value) {
      try {
        await interactiveApi.deleteSession(sessionId.value)
      } catch { /* ignore */ }
    }
    resetState()
  }

  async function fetchActiveSessions() {
    try {
      const resp = await interactiveApi.listSessions()
      activeSessions.value = resp.sessions
    } catch { /* ignore */ }
  }

  async function resumeSession(sid: string) {
    loading.value = true
    error.value = null
    try {
      const [session, sceneResp, history] = await Promise.all([
        interactiveApi.getSession(sid),
        interactiveApi.getCurrentScene(sid),
        interactiveApi.getHistory(sid),
      ])
      sessionId.value = sid
      projectId.value = session.project_id
      projectName.value = session.project_name
      isEnded.value = session.is_ended
      relationships.value = history.relationships
      variables.value = history.variables
      currentScene.value = sceneResp.scene
      imageStatus.value = sceneResp.image
      sceneHistory.value = history.scenes

      if (!isEnded.value && sceneResp.image.status !== 'ready') {
        startImagePolling(sceneResp.scene.scene_index)
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to resume session'
    } finally {
      loading.value = false
    }
  }

  function resetState() {
    stopImagePolling()
    sessionId.value = null
    projectId.value = null
    projectName.value = ''
    isEnded.value = false
    currentScene.value = null
    sceneHistory.value = []
    imageStatus.value = { status: 'pending', progress: 0, url: null }
    relationships.value = {}
    variables.value = {}
    error.value = null
  }

  return {
    sessionId, projectId, projectName, isEnded,
    currentScene, sceneHistory, imageStatus,
    relationships, variables,
    loading, choosing, error, activeSessions,
    isPlaying, sceneCount,
    startSession, submitChoice, endSession,
    fetchActiveSessions, resumeSession, resetState,
  }
})
