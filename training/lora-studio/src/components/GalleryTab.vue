<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <div>
        <h2 style="font-size: 18px; font-weight: 500;">Gallery</h2>
        <p style="font-size: 13px; color: var(--text-muted);">
          Recent ComfyUI output images. Click to view full size.
        </p>
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <select v-model.number="limit" @change="fetchGallery" style="width: 80px;">
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
        <button class="btn" @click="fetchGallery" :disabled="loading">
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <!-- Stats bar -->
    <div v-if="images.length" style="font-size: 12px; color: var(--text-muted); margin-bottom: 16px;">
      Showing {{ images.length }} images
    </div>

    <!-- Image grid -->
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px;">
      <div
        v-for="img in images"
        :key="img.filename"
        class="card"
        style="padding: 0; overflow: hidden; cursor: pointer; position: relative;"
        @click="openFullSize(img.filename)"
      >
        <img
          :src="imageUrl(img.filename)"
          :alt="img.filename"
          style="width: 100%; display: block; aspect-ratio: 1; object-fit: cover;"
          loading="lazy"
        />
        <div style="padding: 8px; font-size: 11px;">
          <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-secondary);">
            {{ img.filename }}
          </div>
          <div style="display: flex; justify-content: space-between; color: var(--text-muted); margin-top: 2px;">
            <span>{{ formatDate(img.created_at) }}</span>
            <span>{{ img.size_kb }}KB</span>
          </div>
        </div>

        <!-- Assign to character button -->
        <button
          class="btn"
          style="position: absolute; top: 6px; right: 6px; font-size: 10px; padding: 2px 8px; background: rgba(26,26,26,0.85);"
          @click.stop="showAssign(img.filename)"
        >Assign</button>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!loading && images.length === 0" style="text-align: center; padding: 48px; color: var(--text-muted);">
      No images found in ComfyUI output directory.
    </div>

    <!-- Assign modal -->
    <div
      v-if="assignImage"
      style="position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 1000;"
      @click.self="assignImage = ''"
    >
      <div class="card" style="width: 400px; max-width: 90vw;">
        <h3 style="font-size: 15px; margin-bottom: 12px;">Assign to Character Dataset</h3>
        <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">{{ assignImage }}</p>
        <select v-model="assignTarget" style="width: 100%; margin-bottom: 16px;">
          <option value="">Select character...</option>
          <option v-for="c in characters" :key="c.slug" :value="c.slug">
            {{ c.name }} ({{ c.project_name }})
          </option>
        </select>
        <div style="display: flex; gap: 8px; justify-content: flex-end;">
          <button class="btn" @click="assignImage = ''">Cancel</button>
          <button
            class="btn btn-active"
            @click="assignToCharacter"
            :disabled="!assignTarget || assigning"
          >{{ assigning ? 'Scanning...' : 'Assign via ComfyUI Scan' }}</button>
        </div>
      </div>
    </div>

    <!-- Fullscreen viewer -->
    <div
      v-if="viewerImage"
      style="position: fixed; inset: 0; background: rgba(0,0,0,0.9); display: flex; align-items: center; justify-content: center; z-index: 1000; cursor: pointer;"
      @click="viewerImage = ''"
    >
      <img
        :src="imageUrl(viewerImage)"
        style="max-width: 95vw; max-height: 95vh; object-fit: contain;"
        @click.stop
      />
      <button
        class="btn"
        style="position: absolute; top: 16px; right: 16px; font-size: 14px; padding: 6px 16px;"
        @click="viewerImage = ''"
      >Close</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useCharactersStore } from '@/stores/characters'
import { api } from '@/api/client'
import type { GalleryImage } from '@/types'

const charactersStore = useCharactersStore()
const characters = computed(() => charactersStore.characters)

const images = ref<GalleryImage[]>([])
const loading = ref(false)
const limit = ref(50)
const viewerImage = ref('')
const assignImage = ref('')
const assignTarget = ref('')
const assigning = ref(false)

onMounted(() => {
  fetchGallery()
})

async function fetchGallery() {
  loading.value = true
  try {
    const result = await api.getGallery(limit.value)
    images.value = result.images
  } catch (err) {
    console.error('Failed to fetch gallery:', err)
  } finally {
    loading.value = false
  }
}

function imageUrl(filename: string) {
  return api.galleryImageUrl(filename)
}

function openFullSize(filename: string) {
  viewerImage.value = filename
}

function showAssign(filename: string) {
  assignImage.value = filename
  assignTarget.value = ''
}

async function assignToCharacter() {
  if (!assignTarget.value) return
  assigning.value = true
  try {
    // Use the scan-comfyui endpoint which will pick up the image
    await api.scanComfyUI()
    assignImage.value = ''
    // Refresh gallery counts
    charactersStore.fetchCharacters()
  } catch (err) {
    console.error('Scan failed:', err)
  } finally {
    assigning.value = false
  }
}

function formatDate(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) +
    ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}
</script>
