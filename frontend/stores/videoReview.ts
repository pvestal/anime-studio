import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { PendingVideo, VideoReviewRequest, EngineStats, EngineBlacklistEntry } from '@/types'
import { scenesApi } from '@/api/scenes'

export const useVideoReviewStore = defineStore('videoReview', () => {
  const pendingVideos = ref<PendingVideo[]>([])
  const engineStats = ref<EngineStats[]>([])
  const blacklist = ref<EngineBlacklistEntry[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const filterProject = ref<number | null>(null)
  const filterEngine = ref<string>('')
  const filterCharacter = ref<string>('')
  const selectedIds = ref<Set<string>>(new Set())

  // Unique project names from pending videos
  const projectNames = computed(() => {
    const map = new Map<number, string>()
    for (const v of pendingVideos.value) {
      map.set(v.project_id, v.project_name)
    }
    return [...map.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  })

  // Unique engines with counts
  const engineCounts = computed(() => {
    const counts: Record<string, number> = {}
    for (const v of filteredByProjectAndCharacter.value) {
      const eng = v.video_engine || 'framepack'
      counts[eng] = (counts[eng] || 0) + 1
    }
    return counts
  })

  // Unique character slugs with counts
  const characterCounts = computed(() => {
    const counts: Record<string, number> = {}
    for (const v of pendingVideos.value) {
      if (filterProject.value && v.project_id !== filterProject.value) continue
      for (const c of v.characters_present) {
        counts[c] = (counts[c] || 0) + 1
      }
    }
    return counts
  })

  // Intermediate filter (project + character, before engine)
  const filteredByProjectAndCharacter = computed(() => {
    return pendingVideos.value.filter(v => {
      if (filterProject.value && v.project_id !== filterProject.value) return false
      if (filterCharacter.value && !(v.characters_present || []).includes(filterCharacter.value)) return false
      return true
    })
  })

  // Final filtered list
  const filteredVideos = computed(() => {
    return filteredByProjectAndCharacter.value.filter(v => {
      if (filterEngine.value && (v.video_engine || 'framepack') !== filterEngine.value) return false
      return true
    })
  })

  const pendingCount = computed(() => pendingVideos.value.length)

  async function fetchPendingVideos() {
    loading.value = true
    error.value = null
    try {
      const filters: { project_id?: number; video_engine?: string; character_slug?: string } = {}
      if (filterProject.value) filters.project_id = filterProject.value
      // We fetch all and filter client-side for engine/character chips
      const resp = await scenesApi.getPendingVideos(filters)
      pendingVideos.value = resp.pending_videos
      selectedIds.value.clear()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch pending videos'
    } finally {
      loading.value = false
    }
  }

  async function fetchEngineStats() {
    try {
      const filters: { project_id?: number; character_slug?: string } = {}
      if (filterProject.value) filters.project_id = filterProject.value
      if (filterCharacter.value) filters.character_slug = filterCharacter.value
      const resp = await scenesApi.getEngineStats(filters)
      engineStats.value = resp.engine_stats
      blacklist.value = resp.blacklist
    } catch (err) {
      // Non-fatal
    }
  }

  async function reviewVideo(shotId: string, approved: boolean, feedback?: string, rejectEngine = false) {
    try {
      const req: VideoReviewRequest = { shot_id: shotId, approved, feedback, reject_engine: rejectEngine }
      await scenesApi.reviewVideo(req)
      // Remove from pending list
      pendingVideos.value = pendingVideos.value.filter(v => v.id !== shotId)
      selectedIds.value.delete(shotId)
      // Refresh stats
      fetchEngineStats()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Review failed'
      throw err
    }
  }

  async function batchReview(approved: boolean, feedback?: string) {
    if (selectedIds.value.size === 0) return
    loading.value = true
    error.value = null
    try {
      const ids = [...selectedIds.value]
      await scenesApi.batchReviewVideo({ shot_ids: ids, approved, feedback })
      pendingVideos.value = pendingVideos.value.filter(v => !selectedIds.value.has(v.id))
      selectedIds.value.clear()
      fetchEngineStats()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Batch review failed'
    } finally {
      loading.value = false
    }
  }

  function toggleSelection(id: string) {
    if (selectedIds.value.has(id)) {
      selectedIds.value.delete(id)
    } else {
      selectedIds.value.add(id)
    }
  }

  function selectAll() {
    for (const v of filteredVideos.value) {
      selectedIds.value.add(v.id)
    }
  }

  function clearSelection() {
    selectedIds.value.clear()
  }

  function clearError() {
    error.value = null
  }

  return {
    pendingVideos,
    engineStats,
    blacklist,
    loading,
    error,
    filterProject,
    filterEngine,
    filterCharacter,
    selectedIds,
    projectNames,
    engineCounts,
    characterCounts,
    filteredVideos,
    pendingCount,
    fetchPendingVideos,
    fetchEngineStats,
    reviewVideo,
    batchReview,
    toggleSelection,
    selectAll,
    clearSelection,
    clearError,
  }
})
