<template>
  <div>
    <!-- Project selector + actions -->
    <div style="display: flex; gap: 16px; margin-bottom: 24px; align-items: flex-end; flex-wrap: wrap;">
      <div style="min-width: 260px;">
        <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Project</label>
        <select v-model="selectedProjectId" style="width: 100%; padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 6px; color: var(--text-primary); font-size: 14px;">
          <option :value="0">Select a project...</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </div>
      <button
        v-if="selectedProjectId && scenes.length > 0"
        class="btn"
        style="font-size: 12px; color: var(--accent-primary);"
        :disabled="generatingAllDialogue"
        @click="generateAllDialogue"
      >
        {{ generatingAllDialogue ? 'Writing...' : 'Auto-Write All Dialogue' }}
      </button>
      <button
        v-if="selectedProjectId && scenes.length > 0"
        class="btn"
        style="font-size: 12px;"
        @click="exportScript"
      >
        Export as Text
      </button>
    </div>

    <div v-if="loading" style="text-align: center; padding: 40px 0; color: var(--text-muted);">Loading scenes...</div>

    <div v-else-if="!selectedProjectId" style="text-align: center; padding: 60px 0; color: var(--text-muted);">
      Select a project to view the screenplay.
    </div>

    <div v-else-if="scenes.length === 0" style="text-align: center; padding: 60px 0; color: var(--text-muted);">
      <p style="font-size: 14px; margin-bottom: 8px;">No scenes yet.</p>
      <p style="font-size: 13px;">Go to the <strong>Scenes</strong> tab and use "Generate from Story" to create scenes.</p>
    </div>

    <!-- Screenplay body -->
    <div v-else class="screenplay">
      <div v-for="scene in scenesWithShots" :key="scene.id" class="scene-block">
        <!-- Scene header -->
        <div class="scene-header">
          <span class="scene-label">SCENE {{ scene.scene_number }}</span>
          <span class="scene-title">{{ scene.title || 'Untitled' }}</span>
          <span v-if="scene.location" class="scene-meta"> — {{ scene.location }}</span>
          <span v-if="scene.time_of_day" class="scene-meta"> ({{ scene.time_of_day }})</span>
          <span v-if="scene.mood" class="scene-mood">{{ scene.mood }}</span>
        </div>
        <div v-if="scene.description" class="scene-description">{{ scene.description }}</div>

        <div class="scene-divider"></div>

        <!-- Shots -->
        <div v-for="shot in scene.shots" :key="shot.id" class="shot-block">
          <!-- Shot direction -->
          <div class="shot-direction">
            [Shot {{ shot.shot_number }}: {{ shot.shot_type || 'medium' }}
            <template v-if="shot.camera_angle && shot.camera_angle !== 'eye-level'">, {{ shot.camera_angle }}</template>
            <template v-if="shot.motion_prompt"> — {{ truncate(shot.motion_prompt, 80) }}</template>]
          </div>

          <!-- Dialogue line (inline editable) -->
          <div v-if="shot.dialogue_character_slug" class="dialogue-block">
            <div class="dialogue-character">{{ characterName(shot.dialogue_character_slug) }}</div>
            <div
              class="dialogue-text"
              :contenteditable="true"
              @blur="onDialogueEdit(scene.id, shot.id, ($event.target as HTMLElement).textContent || '')"
              @keydown.enter.prevent="($event.target as HTMLElement).blur()"
              v-text="shot.dialogue_text || ''"
            ></div>
          </div>
        </div>

        <!-- Scene audio -->
        <div v-if="scene.audio?.track_name" class="scene-audio">
          &#9835; Music: "{{ scene.audio.track_name }}"
          <span v-if="scene.audio.track_artist"> by {{ scene.audio.track_artist }}</span>
          <span v-if="scene.mood"> ({{ scene.mood }} mood)</span>
        </div>

        <div class="scene-end-divider"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { storyApi } from '@/api/story'
import { scenesApi } from '@/api/scenes'
import type { BuilderScene } from '@/types'

interface ProjectInfo {
  id: number
  name: string
}

interface SceneWithShots extends BuilderScene {
  shots: Array<{
    id: string
    shot_number: number
    shot_type: string
    camera_angle: string
    motion_prompt: string
    dialogue_character_slug: string | null
    dialogue_text: string | null
    characters_present: string[]
    [key: string]: unknown
  }>
  audio?: {
    track_name?: string
    track_artist?: string
  }
}

const selectedProjectId = ref(0)
const projects = ref<ProjectInfo[]>([])
const scenes = ref<BuilderScene[]>([])
const scenesWithShots = ref<SceneWithShots[]>([])
const loading = ref(false)
const generatingAllDialogue = ref(false)
const characters = ref<{ slug: string; name: string }[]>([])

// Load projects
;(async () => {
  try {
    const resp = await storyApi.getProjects()
    projects.value = (resp.projects || []).map((p: any) => ({ id: p.id, name: p.name }))
  } catch (e) {
    console.error('Failed to load projects:', e)
  }
})()

// Load scenes + shots when project changes
watch(selectedProjectId, async (pid) => {
  if (!pid) { scenes.value = []; scenesWithShots.value = []; return }
  loading.value = true
  try {
    // Load characters for this project
    const charResp = await storyApi.getCharacters()
    const projDetail = projects.value.find(p => p.id === pid)
    if (charResp.characters && projDetail) {
      characters.value = charResp.characters
        .filter((c: any) => c.project_name === projDetail.name)
        .map((c: any) => ({ slug: c.slug, name: c.name }))
    }

    const data = await scenesApi.listScenes(pid)
    scenes.value = data.scenes || []

    // Fetch full details for each scene (includes shots)
    const detailed: SceneWithShots[] = []
    for (const scene of scenes.value) {
      try {
        const full = await scenesApi.getScene(scene.id) as SceneWithShots
        detailed.push(full)
      } catch {
        detailed.push({ ...scene, shots: [] } as SceneWithShots)
      }
    }
    // Sort by scene_number
    detailed.sort((a, b) => (a.scene_number || 0) - (b.scene_number || 0))
    scenesWithShots.value = detailed
  } catch (e) {
    console.error('Failed to load scenes:', e)
    scenes.value = []
    scenesWithShots.value = []
  } finally {
    loading.value = false
  }
}, { immediate: true })

function characterName(slug: string): string {
  const c = characters.value.find(ch => ch.slug === slug)
  return c?.name?.toUpperCase() || slug.toUpperCase().replace(/_/g, ' ')
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + '...' : text
}

async function onDialogueEdit(sceneId: string, shotId: string, newText: string) {
  try {
    await scenesApi.updateShot(sceneId, shotId, { dialogue_text: newText } as any)
  } catch (e) {
    console.error('Failed to save dialogue:', e)
  }
}

async function generateAllDialogue() {
  if (!selectedProjectId.value) return
  generatingAllDialogue.value = true
  try {
    for (const scene of scenesWithShots.value) {
      try {
        const resp = await fetch(`/api/scenes/${scene.id}/generate-dialogue`, { method: 'POST' })
        if (resp.ok) {
          // Refresh scene data
          const full = await scenesApi.getScene(scene.id) as SceneWithShots
          const idx = scenesWithShots.value.findIndex(s => s.id === scene.id)
          if (idx >= 0) scenesWithShots.value[idx] = full
        }
      } catch { /* continue to next scene */ }
    }
  } finally {
    generatingAllDialogue.value = false
  }
}

function exportScript() {
  const lines: string[] = []
  for (const scene of scenesWithShots.value) {
    lines.push(`SCENE ${scene.scene_number}: ${scene.title || 'Untitled'}${scene.location ? ` — ${scene.location}` : ''}${scene.time_of_day ? ` (${scene.time_of_day})` : ''}${scene.mood ? ` [${scene.mood}]` : ''}`)
    lines.push('─'.repeat(50))
    if (scene.description) lines.push(scene.description)
    lines.push('')
    for (const shot of scene.shots || []) {
      let shotLine = `[Shot ${shot.shot_number}: ${shot.shot_type || 'medium'}`
      if (shot.motion_prompt) shotLine += ` — ${shot.motion_prompt}`
      shotLine += ']'
      lines.push(shotLine)
      if (shot.dialogue_character_slug && shot.dialogue_text) {
        lines.push(`  ${characterName(shot.dialogue_character_slug)}: "${shot.dialogue_text}"`)
      }
      lines.push('')
    }
    if (scene.audio?.track_name) {
      lines.push(`♫ Music: "${scene.audio.track_name}"${scene.audio.track_artist ? ` by ${scene.audio.track_artist}` : ''}`)
    }
    lines.push('─'.repeat(50))
    lines.push('')
  }

  const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const projName = projects.value.find(p => p.id === selectedProjectId.value)?.name || 'screenplay'
  a.download = `${projName.replace(/\s+/g, '_').toLowerCase()}_screenplay.txt`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.screenplay {
  max-width: 700px;
  margin: 0 auto;
  font-family: 'Courier New', Courier, monospace;
  line-height: 1.6;
}
.scene-block {
  margin-bottom: 32px;
}
.scene-header {
  font-size: 14px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-primary);
  margin-bottom: 4px;
}
.scene-label {
  color: var(--accent-primary);
}
.scene-title {
  margin-left: 4px;
}
.scene-meta {
  font-weight: 400;
  color: var(--text-secondary);
}
.scene-mood {
  margin-left: 8px;
  font-size: 11px;
  font-weight: 400;
  padding: 1px 8px;
  border-radius: 10px;
  background: rgba(122, 162, 247, 0.15);
  color: var(--accent-primary);
}
.scene-description {
  font-size: 12px;
  color: var(--text-secondary);
  font-style: italic;
  margin-bottom: 8px;
  font-family: var(--font-primary);
}
.scene-divider {
  border-top: 1px solid var(--border-primary);
  margin-bottom: 12px;
}
.scene-end-divider {
  border-top: 2px solid var(--border-primary);
  margin-top: 8px;
}
.shot-block {
  margin-bottom: 12px;
}
.shot-direction {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.dialogue-block {
  margin-left: 40px;
  margin-bottom: 4px;
}
.dialogue-character {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 2px;
}
.dialogue-text {
  font-size: 13px;
  color: var(--text-primary);
  padding: 4px 8px;
  border-radius: 3px;
  border: 1px solid transparent;
  cursor: text;
  min-height: 20px;
  transition: border-color 150ms ease;
}
.dialogue-text:hover {
  border-color: var(--border-primary);
}
.dialogue-text:focus {
  border-color: var(--accent-primary);
  outline: none;
  background: var(--bg-primary);
}
.scene-audio {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
  margin-top: 12px;
  padding: 6px 10px;
  background: rgba(122, 162, 247, 0.06);
  border-radius: 4px;
  font-family: var(--font-primary);
}
</style>
