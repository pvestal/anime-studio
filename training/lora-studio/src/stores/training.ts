import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { TrainingJob, TrainingRequest } from '@/types'
import { api } from '@/api/client'

export const useTrainingStore = defineStore('training', () => {
  // State
  const jobs = ref<TrainingJob[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Actions
  async function fetchTrainingJobs() {
    loading.value = true
    error.value = null

    try {
      const response = await api.getTrainingJobs()
      jobs.value = response.training_jobs
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch training jobs'
    } finally {
      loading.value = false
    }
  }

  async function startTraining(request: TrainingRequest) {
    loading.value = true
    error.value = null

    try {
      const response = await api.startTraining(request)

      // Refresh the jobs list to include the new job
      await fetchTrainingJobs()

      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to start training'
      throw err
    } finally {
      loading.value = false
    }
  }

  function clearError() {
    error.value = null
  }

  // Initialize
  fetchTrainingJobs()

  return {
    // State
    jobs,
    loading,
    error,

    // Actions
    fetchTrainingJobs,
    startTraining,
    clearError
  }
})