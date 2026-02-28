<template>
  <div>
    <!-- Project selector -->
    <div style="display: flex; gap: 16px; margin-bottom: 24px; align-items: flex-end;">
      <div style="min-width: 260px;">
        <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Project</label>
        <select v-model="selectedProjectId" style="width: 100%; padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 6px; color: var(--text-primary); font-size: 14px;">
          <option :value="0">Select a project...</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </div>
    </div>

    <EpisodeView
      v-if="selectedProjectId"
      :project-id="selectedProjectId"
      :scenes="scenes"
      @play-episode="playEpisodeVideo"
    />
    <div v-else style="text-align: center; padding: 60px 0; color: var(--text-muted);">
      Select a project to manage episodes.
    </div>

    <!-- Video Player Modal -->
    <div v-if="showVideoPlayer" style="position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center;" @click.self="showVideoPlayer = false" @keydown.escape.window="showVideoPlayer = false">
      <div style="max-width: 90vw; max-height: 90vh;">
        <video :src="videoPlayerSrc" controls autoplay style="max-width: 100%; max-height: 85vh; border-radius: 4px;"></video>
        <div style="text-align: center; margin-top: 8px;">
          <button class="btn" @click="showVideoPlayer = false">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { storyApi } from '@/api/story'
import { scenesApi } from '@/api/scenes'
import type { BuilderScene, Episode } from '@/types'
import EpisodeView from '../scenes/EpisodeView.vue'

interface ProjectInfo {
  id: number
  name: string
}

const selectedProjectId = ref(0)
const projects = ref<ProjectInfo[]>([])
const scenes = ref<BuilderScene[]>([])
const showVideoPlayer = ref(false)
const videoPlayerSrc = ref('')

// Load projects
;(async () => {
  try {
    const resp = await storyApi.getProjects()
    projects.value = (resp.projects || []).map((p: any) => ({ id: p.id, name: p.name }))
  } catch (e) {
    console.error('Failed to load projects:', e)
  }
})()

// Load scenes when project changes
watch(selectedProjectId, async (pid) => {
  if (!pid) { scenes.value = []; return }
  try {
    const data = await scenesApi.listScenes(pid)
    scenes.value = data.scenes || []
  } catch (e) {
    console.error('Failed to load scenes:', e)
    scenes.value = []
  }
}, { immediate: true })

function playEpisodeVideo(ep: Episode) {
  if (ep.final_video_path) {
    videoPlayerSrc.value = `/api/episodes/${ep.id}/video`
    showVideoPlayer.value = true
  }
}
</script>
