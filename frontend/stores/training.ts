import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { TrainingJob, TrainingRequest, LoraFile } from '@/types'
import { api } from '@/api/client'

export const useTrainingStore = defineStore('training', () => {
  // State
  const jobs = ref<TrainingJob[]>([])
  const loras = ref<LoraFile[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Actions
  async function fetchTrainingJobs(silent = false) {
    if (!silent) {
      loading.value = true
      error.value = null
    }

    try {
      const response = await api.getTrainingJobs()
      jobs.value = response.training_jobs
    } catch (err) {
      if (!silent) {
        error.value = err instanceof Error ? err.message : 'Failed to fetch training jobs'
      }
    } finally {
      if (!silent) {
        loading.value = false
      }
    }
  }

  async function startTraining(request: TrainingRequest) {
    loading.value = true
    error.value = null

    try {
      const response = await api.startTraining(request)
      await fetchTrainingJobs()
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to start training'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function cancelJob(jobId: string) {
    try {
      const response = await api.cancelTrainingJob(jobId)
      await fetchTrainingJobs()
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to cancel job'
      throw err
    }
  }

  async function deleteJob(jobId: string) {
    try {
      const response = await api.deleteTrainingJob(jobId)
      await fetchTrainingJobs()
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to delete job'
      throw err
    }
  }

  async function retryJob(jobId: string) {
    try {
      const response = await api.retryTrainingJob(jobId)
      await fetchTrainingJobs()
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to retry job'
      throw err
    }
  }

  async function invalidateJob(jobId: string, deleteLora: boolean = false) {
    try {
      const response = await api.invalidateTrainingJob(jobId, deleteLora)
      await fetchTrainingJobs()
      await fetchLoras()
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to invalidate job'
      throw err
    }
  }

  async function clearFinished(days: number = 7) {
    try {
      const response = await api.clearFinishedJobs(days)
      await fetchTrainingJobs()
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to clear finished jobs'
      throw err
    }
  }

  async function reconcileJobs() {
    try {
      const response = await api.reconcileJobs()
      await fetchTrainingJobs()
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to reconcile jobs'
      throw err
    }
  }

  async function fetchLoras(silent = false) {
    try {
      const response = await api.getTrainedLoras()
      loras.value = response.loras
    } catch (err) {
      if (!silent) {
        error.value = err instanceof Error ? err.message : 'Failed to fetch LoRAs'
      }
    }
  }

  async function deleteLora(slug: string) {
    try {
      const response = await api.deleteTrainedLora(slug)
      await fetchLoras()
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to delete LoRA'
      throw err
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    // State
    jobs,
    loras,
    loading,
    error,

    // Actions
    fetchTrainingJobs,
    startTraining,
    cancelJob,
    deleteJob,
    retryJob,
    invalidateJob,
    clearFinished,
    reconcileJobs,
    fetchLoras,
    deleteLora,
    clearError
  }
})
