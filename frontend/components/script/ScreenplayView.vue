<template>
  <div>
    <!-- Actions bar -->
    <div v-if="projectId && scenes.length > 0" class="actions-bar">
      <button
        class="btn"
        style="font-size: 12px; color: var(--accent-primary);"
        :disabled="generatingAllDialogue"
        @click="generateAllDialogue"
      >
        {{ generatingAllDialogue ? 'Writing...' : 'Auto-Write All Dialogue' }}
      </button>
      <button class="btn" style="font-size: 12px;" @click="exportScript">
        Export as Text
      </button>
    </div>

    <div v-if="loading" style="text-align: center; padding: 40px 0; color: var(--text-muted);">Loading scenes...</div>

    <div v-else-if="!projectId" style="text-align: center; padding: 60px 0; color: var(--text-muted);">
      Select a project above to view the screenplay.
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

          <!-- Dialogue line (inline editable) + play button -->
          <div v-if="shot.dialogue_character_slug" class="dialogue-block">
            <div style="display: flex; align-items: center; gap: 6px;">
              <div class="dialogue-character">{{ characterName(shot.dialogue_character_slug) }}</div>
              <button
                v-if="shot.dialogue_text"
                class="play-btn"
                :disabled="shotSynthBusy[shot.id]"
                :title="shotSynthBusy[shot.id] ? 'Generating...' : 'Play this line'"
                @click="playShotDialogue(shot.id)"
              >
                <span v-if="shotSynthBusy[shot.id]" class="spin">&#8635;</span>
                <span v-else>&#9654;</span>
              </button>
            </div>
            <div
              class="dialogue-text"
              :contenteditable="true"
              @blur="onDialogueEdit(scene.id, shot.id, ($event.target as HTMLElement).textContent || '')"
              @keydown.enter.prevent="($event.target as HTMLElement).blur()"
              v-text="shot.dialogue_text || ''"
            ></div>
            <!-- Inline audio player for this shot -->
            <audio
              v-if="shotAudioUrls[shot.id]"
              :ref="(el) => { if (el) shotAudioEls[shot.id] = el as HTMLAudioElement }"
              :src="shotAudioUrls[shot.id]"
              controls
              preload="none"
              class="shot-audio-player"
            />
          </div>
        </div>

        <!-- Scene combined dialogue player -->
        <div v-if="sceneHasDialogue(scene)" class="scene-dialogue-player">
          <button
            class="play-scene-btn"
            :disabled="sceneSynthBusy[scene.id]"
            @click="playSceneDialogue(scene.id)"
          >
            <span v-if="sceneSynthBusy[scene.id]" class="spin">&#8635;</span>
            <span v-else>&#9654;</span>
            {{ sceneSynthBusy[scene.id] ? 'Synthesizing scene...' : 'Play Scene Dialogue' }}
          </button>
          <audio
            v-if="sceneAudioUrls[scene.id]"
            :ref="(el) => { if (el) sceneAudioEls[scene.id] = el as HTMLAudioElement }"
            :src="sceneAudioUrls[scene.id]"
            controls
            preload="none"
            class="scene-audio-player"
          />
        </div>

        <!-- Scene music -->
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
import { ref, reactive, watch } from 'vue'
import { storyApi } from '@/api/story'
import { scenesApi } from '@/api/scenes'
import type { BuilderScene } from '@/types'

const props = withDefaults(defineProps<{
  projectId?: number
}>(), {
  projectId: 0,
})

interface SceneWithShots extends Omit<BuilderScene, 'shots' | 'audio'> {
  scene_number?: number
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
  } | null
}

const scenes = ref<BuilderScene[]>([])
const scenesWithShots = ref<SceneWithShots[]>([])
const loading = ref(false)
const generatingAllDialogue = ref(false)
const characters = ref<{ slug: string; name: string }[]>([])
const projectName = ref('')

// --- Audio playback state ---
const shotSynthBusy = reactive<Record<string, boolean>>({})
const shotAudioUrls = reactive<Record<string, string>>({})
const shotAudioEls = reactive<Record<string, HTMLAudioElement>>({})
const sceneSynthBusy = reactive<Record<string, boolean>>({})
const sceneAudioUrls = reactive<Record<string, string>>({})
const sceneAudioEls = reactive<Record<string, HTMLAudioElement>>({})

function sceneHasDialogue(scene: SceneWithShots): boolean {
  return scene.shots?.some(s => s.dialogue_character_slug && s.dialogue_text) ?? false
}

async function playShotDialogue(shotId: string) {
  // If already loaded, just toggle play/pause
  if (shotAudioUrls[shotId] && shotAudioEls[shotId]) {
    const el = shotAudioEls[shotId]
    if (el.paused) { el.play() } else { el.pause() }
    return
  }
  shotSynthBusy[shotId] = true
  try {
    const result = await scenesApi.synthesizeShotDialogue(shotId)
    shotAudioUrls[shotId] = scenesApi.synthesisAudioUrl(result.job_id)
    // Auto-play after element mounts
    await new Promise(r => setTimeout(r, 150))
    shotAudioEls[shotId]?.play()
  } catch (e: any) {
    console.error('Shot synthesis failed:', e)
  } finally {
    shotSynthBusy[shotId] = false
  }
}

async function playSceneDialogue(sceneId: string) {
  // If already loaded, toggle play/pause
  if (sceneAudioUrls[sceneId] && sceneAudioEls[sceneId]) {
    const el = sceneAudioEls[sceneId]
    if (el.paused) { el.play() } else { el.pause() }
    return
  }
  sceneSynthBusy[sceneId] = true
  try {
    // Synthesize if needed, then load audio URL
    const resp = await fetch(`/api/scenes/${sceneId}/synthesize-dialogue`, { method: 'POST' })
    if (resp.ok) {
      sceneAudioUrls[sceneId] = scenesApi.sceneDialogueAudioUrl(sceneId)
    } else {
      console.error('Scene dialogue synthesis failed:', await resp.text())
      return
    }
    await new Promise(r => setTimeout(r, 150))
    sceneAudioEls[sceneId]?.play()
  } catch (e: any) {
    console.error('Scene dialogue playback failed:', e)
  } finally {
    sceneSynthBusy[sceneId] = false
  }
}

// Load scenes + shots when project changes
watch(() => props.projectId, async (pid) => {
  if (!pid) { scenes.value = []; scenesWithShots.value = []; return }
  loading.value = true
  try {
    // Load characters and project name
    const [charResp, projResp] = await Promise.all([
      storyApi.getCharacters(),
      storyApi.getProjects(),
    ])
    const proj = (projResp.projects || []).find((p: any) => p.id === pid)
    projectName.value = proj?.name || ''
    if (charResp.characters) {
      const projChars = charResp.characters.filter((c: any) => c.project_id === pid)
      characters.value = projChars.map((c: any) => ({ slug: c.slug, name: c.name }))
    }

    const data = await scenesApi.listScenes(pid)
    scenes.value = data.scenes || []

    // Fetch full details for each scene (includes shots)
    const detailed: SceneWithShots[] = []
    for (const scene of scenes.value) {
      try {
        const full = await scenesApi.getScene(scene.id) as unknown as SceneWithShots
        detailed.push(full)
      } catch {
        detailed.push({ ...scene, shots: [] } as unknown as SceneWithShots)
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
  if (!props.projectId) return
  generatingAllDialogue.value = true
  try {
    for (const scene of scenesWithShots.value) {
      try {
        const resp = await fetch(`/api/scenes/${scene.id}/generate-dialogue`, { method: 'POST' })
        if (resp.ok) {
          // Refresh scene data
          const full = await scenesApi.getScene(scene.id) as unknown as SceneWithShots
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
  const projName = projectName.value || 'screenplay'
  a.download = `${projName.replace(/\s+/g, '_').toLowerCase()}_screenplay.txt`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.actions-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 0 4px;
}

/* --- Screenplay --- */
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
.play-btn {
  background: none;
  border: 1px solid var(--border-primary);
  border-radius: 50%;
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--accent-primary);
  font-size: 10px;
  padding: 0;
  flex-shrink: 0;
  transition: background 150ms, border-color 150ms;
}
.play-btn:hover:not(:disabled) {
  background: rgba(122, 162, 247, 0.15);
  border-color: var(--accent-primary);
}
.play-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.shot-audio-player {
  margin-top: 4px;
  height: 28px;
  width: 100%;
  border-radius: 4px;
}
.scene-dialogue-player {
  margin-top: 8px;
  padding: 8px 10px;
  background: rgba(122, 162, 247, 0.06);
  border-radius: 4px;
  border: 1px solid var(--border-primary);
  font-family: var(--font-primary);
}
.play-scene-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: 1px solid var(--accent-primary);
  border-radius: 4px;
  padding: 4px 12px;
  font-size: 12px;
  color: var(--accent-primary);
  cursor: pointer;
  font-family: var(--font-primary);
  transition: background 150ms;
}
.play-scene-btn:hover:not(:disabled) {
  background: rgba(122, 162, 247, 0.15);
}
.play-scene-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.scene-audio-player {
  margin-top: 6px;
  height: 32px;
  width: 100%;
  border-radius: 4px;
}
@keyframes spin-anim {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.spin {
  display: inline-block;
  animation: spin-anim 1s linear infinite;
}
</style>
