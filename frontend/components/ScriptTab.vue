<template>
  <div>
    <!-- Project carousel (shared across sub-tabs) -->
    <div class="project-carousel">
      <button
        class="carousel-arrow"
        :disabled="carouselOffset <= 0"
        @click="scrollCarousel(-1)"
      >&#8249;</button>
      <div class="carousel-track-wrapper" ref="carouselTrackEl">
        <div class="carousel-pills">
          <button
            v-for="p in projects"
            :key="p.id"
            :class="['project-pill', { active: selectedProjectId === p.id }]"
            @click="selectedProjectId = p.id"
          >
            <span class="pill-name">{{ p.name }}</span>
            <span v-if="p.scene_count" class="pill-count">{{ p.scene_count }}</span>
          </button>
        </div>
      </div>
      <button
        class="carousel-arrow"
        :disabled="carouselOffset >= maxCarouselOffset"
        @click="scrollCarousel(1)"
      >&#8250;</button>
    </div>

    <!-- Sub-tab navigation -->
    <div style="display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border-primary);">
      <RouterLink to="/script/scenes" class="script-subtab" active-class="" exact-active-class="active">
        Scenes
      </RouterLink>
      <RouterLink to="/script/screenplay" class="script-subtab" active-class="" exact-active-class="active">
        Screenplay
      </RouterLink>
    </div>

    <RouterView v-slot="{ Component }">
      <component :is="Component" :project-id="selectedProjectId" :hide-episodes="true" />
    </RouterView>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { storyApi } from '@/api/story'
import { scenesApi } from '@/api/scenes'

interface ProjectInfo {
  id: number
  name: string
  scene_count: number
}

const selectedProjectId = ref(0)
const projects = ref<ProjectInfo[]>([])

// --- Carousel ---
const carouselTrackEl = ref<HTMLElement | null>(null)
const carouselOffset = ref(0)
const maxCarouselOffset = computed(() => {
  if (!carouselTrackEl.value) return 0
  const inner = carouselTrackEl.value.querySelector('.carousel-pills') as HTMLElement
  if (!inner) return 0
  return Math.max(0, inner.scrollWidth - carouselTrackEl.value.clientWidth)
})

function scrollCarousel(dir: number) {
  const step = 200
  carouselOffset.value = Math.max(0, Math.min(carouselOffset.value + dir * step, maxCarouselOffset.value))
  if (carouselTrackEl.value) {
    const inner = carouselTrackEl.value.querySelector('.carousel-pills') as HTMLElement
    if (inner) inner.style.transform = `translateX(-${carouselOffset.value}px)`
  }
}

// Load projects with scene counts
;(async () => {
  try {
    const resp = await storyApi.getProjects()
    const projs: ProjectInfo[] = (resp.projects || []).map((p: any) => ({ id: p.id, name: p.name, scene_count: 0 }))
    projects.value = projs
    // Fetch scene counts in background
    for (const p of projs) {
      try {
        const s = await scenesApi.listScenes(p.id)
        p.scene_count = s.scenes?.length || 0
      } catch { /* ignore */ }
    }
    projects.value = [...projs]
    await nextTick()
    carouselOffset.value = 0
  } catch (e) {
    console.error('Failed to load projects:', e)
  }
})()
</script>

<style scoped>
/* --- Project Carousel --- */
.project-carousel {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 12px;
  padding: 0 4px;
}
.carousel-arrow {
  background: none;
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 18px;
  flex-shrink: 0;
  transition: background 150ms, border-color 150ms;
}
.carousel-arrow:hover:not(:disabled) {
  background: var(--bg-secondary);
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.carousel-arrow:disabled {
  opacity: 0.3;
  cursor: default;
}
.carousel-track-wrapper {
  flex: 1;
  overflow: hidden;
}
.carousel-pills {
  display: flex;
  gap: 6px;
  transition: transform 200ms ease;
  white-space: nowrap;
}
.project-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  border-radius: 20px;
  border: 1px solid var(--border-primary);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 13px;
  font-family: var(--font-primary);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 150ms ease;
}
.project-pill:hover {
  border-color: var(--accent-primary);
  color: var(--text-primary);
  background: rgba(122, 162, 247, 0.08);
}
.project-pill.active {
  border-color: var(--accent-primary);
  background: rgba(122, 162, 247, 0.15);
  color: var(--accent-primary);
  font-weight: 600;
}
.pill-name {
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}
.pill-count {
  font-size: 10px;
  min-width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  background: rgba(122, 162, 247, 0.2);
  color: var(--accent-primary);
  font-weight: 600;
}

/* --- Sub-tabs --- */
.script-subtab {
  padding: 10px 20px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  font-family: var(--font-primary);
  transition: all 150ms ease;
  text-decoration: none;
}
.script-subtab:hover {
  color: var(--accent-primary);
}
.script-subtab.active {
  border-bottom-color: var(--accent-primary);
  color: var(--accent-primary);
  font-weight: 500;
}
</style>
