import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Character, DatasetImage } from '@/types'
import { api } from '@/api/client'

export const useCharactersStore = defineStore('characters', () => {
  const characters = ref<Character[]>([])
  const datasets = ref<Map<string, DatasetImage[]>>(new Map())
  const loading = ref(false)
  const error = ref<string | null>(null)

  const totalImages = computed(() => {
    return characters.value.reduce((sum, c) => sum + c.image_count, 0)
  })

  const getCharacterStats = computed(() => (characterName: string) => {
    const images = datasets.value.get(characterName) || []
    const approved = images.filter(img => img.status === 'approved').length
    const pending = images.filter(img => img.status === 'pending').length
    return {
      total: images.length,
      approved,
      pending,
      canTrain: approved >= 10,
    }
  })

  async function fetchCharacters() {
    loading.value = true
    error.value = null
    try {
      const response = await api.getCharacters()
      characters.value = response.characters
      // Fetch dataset details for each character (use slug for reliable URL)
      for (const character of characters.value) {
        await fetchCharacterDataset(character.slug || character.name)
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch characters'
    } finally {
      loading.value = false
    }
  }

  async function fetchCharacterDataset(characterName: string) {
    try {
      const response = await api.getCharacterDataset(characterName)
      datasets.value.set(characterName, response.images)
    } catch (err) {
      console.warn(`Failed to fetch dataset for ${characterName}:`, err)
      datasets.value.set(characterName, [])
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    characters,
    datasets,
    loading,
    error,
    totalImages,
    getCharacterStats,
    fetchCharacters,
    fetchCharacterDataset,
    clearError,
  }
})
