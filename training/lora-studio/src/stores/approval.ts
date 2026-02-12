import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { PendingImage, ApprovalRequest } from '@/types'
import { api } from '@/api/client'

export const useApprovalStore = defineStore('approval', () => {
  const pendingImages = ref<PendingImage[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const filterProject = ref<string>('')
  const filterCharacter = ref<string>('')

  // All unique project names
  const projectNames = computed(() => {
    const names = new Set<string>()
    for (const img of pendingImages.value) {
      if (img.project_name) names.add(img.project_name)
    }
    return [...names].sort()
  })

  // Character names filtered by selected project
  const characterNames = computed(() => {
    const names = new Set<string>()
    for (const img of pendingImages.value) {
      if (filterProject.value && img.project_name !== filterProject.value) continue
      names.add(img.character_name)
    }
    return [...names].sort()
  })

  // Group images by character (used for counts in dropdown)
  const groupedImages = computed(() => {
    const groups: Record<string, PendingImage[]> = {}
    for (const img of pendingImages.value) {
      if (!groups[img.character_name]) {
        groups[img.character_name] = []
      }
      groups[img.character_name].push(img)
    }
    return groups
  })

  // Filtered images by project + character
  const filteredImages = computed(() => {
    return pendingImages.value.filter(img => {
      if (filterProject.value && img.project_name !== filterProject.value) return false
      if (filterCharacter.value && img.character_name !== filterCharacter.value) return false
      return true
    })
  })

  async function fetchPendingImages() {
    loading.value = true
    error.value = null
    try {
      const response = await api.getPendingApprovals()
      pendingImages.value = response.pending_images
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch pending images'
    } finally {
      loading.value = false
    }
  }

  async function approveImage(image: PendingImage, approved: boolean, feedback = '', editedPrompt = '') {
    try {
      const request: ApprovalRequest = {
        character_name: image.character_name,
        character_slug: image.character_slug,
        image_name: image.name,
        approved,
        feedback: feedback || (approved ? 'Approved' : 'Rejected'),
        edited_prompt: editedPrompt || undefined,
      }
      await api.approveImage(request)
      // Remove from pending list
      pendingImages.value = pendingImages.value.filter(img => img.id !== image.id)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to approve image'
      throw err
    }
  }

  async function batchApprove(images: PendingImage[], approved: boolean) {
    loading.value = true
    error.value = null
    try {
      for (const image of images) {
        await approveImage(image, approved, `Batch ${approved ? 'approved' : 'rejected'}`)
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Batch operation failed'
    } finally {
      loading.value = false
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    pendingImages,
    loading,
    error,
    filterProject,
    filterCharacter,
    projectNames,
    groupedImages,
    characterNames,
    filteredImages,
    fetchPendingImages,
    approveImage,
    batchApprove,
    clearError,
  }
})
