<template>
  <div style="display: flex; gap: 16px; align-items: flex-start;">
    <!-- Left: Scene Details -->
    <div class="card" style="width: 280px; flex-shrink: 0;">
      <div style="font-size: 13px; font-weight: 500; margin-bottom: 12px; color: var(--accent-primary);">Scene Details</div>

      <div class="field-group">
        <label class="field-label">Title</label>
        <input v-model="localScene.title" type="text" class="field-input" />
      </div>
      <div class="field-group">
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
          <label class="field-label" style="margin-bottom: 0;">Description</label>
          <EchoAssistButton
            context-type="concept"
            :context-payload="echoScenePayload"
            :current-value="localScene.description || ''"
            compact
            @accept="localScene.description = $event.suggestion"
          />
        </div>
        <textarea v-model="localScene.description" rows="3" class="field-input field-textarea"></textarea>
      </div>
      <div class="field-group">
        <label class="field-label">Location</label>
        <input v-model="localScene.location" type="text" placeholder="dark alley, rooftop..." class="field-input" />
      </div>
      <div class="field-row">
        <div class="field-group">
          <label class="field-label">Time</label>
          <select v-model="localScene.time_of_day" class="field-input">
            <option value="">--</option>
            <option v-for="t in timeOptions" :key="t" :value="t">{{ t }}</option>
          </select>
        </div>
        <div class="field-group">
          <label class="field-label">Weather</label>
          <select v-model="localScene.weather" class="field-input">
            <option value="">--</option>
            <option v-for="w in weatherOptions" :key="w" :value="w">{{ w }}</option>
          </select>
        </div>
      </div>
      <div class="field-group">
        <label class="field-label">Mood</label>
        <input v-model="localScene.mood" type="text" placeholder="tense, peaceful..." class="field-input" />
      </div>
      <div class="field-group">
        <label class="field-label">Target Duration (s)</label>
        <input v-model.number="localScene.target_duration_seconds" type="number" min="5" max="300" class="field-input" />
      </div>

      <!-- Post-processing -->
      <div style="border-top: 1px solid var(--border-primary); padding-top: 8px; margin-top: 8px;">
        <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 6px;">Post-Processing</div>
        <div class="field-group">
          <label class="field-label">Frame Interpolation</label>
          <select v-model="localPostInterpolate" class="field-input">
            <option :value="null">Off</option>
            <option :value="60">30 → 60 fps</option>
          </select>
        </div>
        <div class="field-group">
          <label class="field-label">Upscale</label>
          <select v-model="localPostUpscale" class="field-input">
            <option :value="null">Off</option>
            <option :value="2">2x (max 1080p)</option>
          </select>
        </div>
      </div>

      <div style="font-size: 12px; color: var(--text-muted); margin-top: 12px;">
        {{ shots.length }} shots, est. {{ estimateMinutes(shots) }} min gen time
      </div>

      <!-- Training readiness warning -->
      <div v-if="unreadyCharacters.length > 0" style="border-left: 3px solid var(--status-warning); background: rgba(160, 128, 80, 0.1); padding: 8px 10px; margin-top: 10px; border-radius: 0 4px 4px 0;">
        <div style="font-size: 11px; font-weight: 500; color: var(--status-warning); margin-bottom: 4px;">Characters without LoRA</div>
        <div v-for="c in unreadyCharacters" :key="c.slug" style="font-size: 11px; color: var(--text-secondary); margin-bottom: 2px;">
          {{ c.name }} — {{ c.reason }}
        </div>
        <button
          class="btn"
          style="font-size: 11px; padding: 2px 8px; margin-top: 6px;"
          @click="emit('go-to-training')"
        >Go to Training tab</button>
      </div>

      <!-- Story Arc dropdown (optional tag) -->
      <div v-if="storyArcs.length > 0" class="field-group" style="margin-top: 10px;">
        <label class="field-label">Story Arc</label>
        <select v-model="localStoryArc" class="field-input">
          <option value="">None</option>
          <option v-for="arc in storyArcs" :key="arc" :value="arc">{{ arc }}</option>
        </select>
      </div>

      <div style="display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap;">
        <button class="btn btn-primary" @click="emit('save')" :disabled="saving">Save</button>
        <button
          class="btn btn-success"
          :disabled="shots.length === 0 || generating"
          @click="emit('confirm-generate')"
        >Generate</button>
        <button
          class="btn"
          :disabled="shots.length === 0 || allShotsHaveImages"
          @click="emit('auto-assign')"
          title="Auto-assign best source images to all unassigned shots"
        >Auto-assign Images</button>
        <button class="btn" @click="emit('back')">Back</button>
      </div>

      <!-- Audio Track Panel -->
      <SceneAudioPanel
        v-if="sceneId"
        :scene-id="sceneId"
        :audio="scene.audio ?? null"
        @audio-changed="(a: SceneAudio | null) => emit('audio-changed', a)"
      />

      <!-- Story Context (collapsible) -->
      <div v-if="hasStoryContext" style="margin-top: 16px; border-top: 1px solid var(--border-primary); padding-top: 12px;">
        <button
          style="display: flex; align-items: center; gap: 6px; background: none; border: none; cursor: pointer; color: var(--text-secondary); font-size: 12px; font-family: var(--font-primary); padding: 0;"
          @click="storyContextOpen = !storyContextOpen"
        >
          <span style="font-size: 10px;">{{ storyContextOpen ? '\u25BC' : '\u25B6' }}</span>
          Story Context
        </button>
        <div v-if="storyContextOpen" style="margin-top: 8px; font-size: 12px;">
          <div v-if="storyline?.summary" style="margin-bottom: 8px;">
            <div style="color: var(--text-muted); font-size: 10px; text-transform: uppercase; margin-bottom: 2px;">Summary</div>
            <div style="color: var(--text-secondary); line-height: 1.4;">{{ storyline.summary }}</div>
          </div>
          <div v-if="storyline?.theme" style="margin-bottom: 8px;">
            <div style="color: var(--text-muted); font-size: 10px; text-transform: uppercase; margin-bottom: 2px;">Theme</div>
            <div style="color: var(--text-secondary);">{{ storyline.theme }}</div>
          </div>
          <div v-if="storyline?.tone" style="margin-bottom: 8px;">
            <div style="color: var(--text-muted); font-size: 10px; text-transform: uppercase; margin-bottom: 2px;">Tone</div>
            <div style="color: var(--text-secondary);">{{ storyline.tone }}</div>
          </div>
          <div v-if="worldLocation" style="margin-bottom: 8px;">
            <div style="color: var(--text-muted); font-size: 10px; text-transform: uppercase; margin-bottom: 2px;">World</div>
            <div style="color: var(--text-secondary);">{{ worldLocation }}</div>
          </div>
          <div v-if="storyArcs.length > 0" style="margin-bottom: 8px;">
            <div style="color: var(--text-muted); font-size: 10px; text-transform: uppercase; margin-bottom: 2px;">Story Arcs</div>
            <div style="display: flex; flex-wrap: wrap; gap: 4px;">
              <span v-for="arc in storyArcs" :key="arc" style="padding: 1px 6px; background: var(--bg-primary); border-radius: 3px; font-size: 11px; color: var(--text-secondary);">{{ arc }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Middle: Shot Timeline -->
    <div style="width: 240px; flex-shrink: 0;">
      <div style="font-size: 13px; font-weight: 500; margin-bottom: 12px; color: var(--accent-primary);">Shot Timeline</div>
      <div style="display: flex; flex-direction: column; gap: 8px;">
        <div
          v-for="(shot, idx) in shots"
          :key="shot.id || idx"
          class="card"
          :style="{
            cursor: 'pointer',
            borderLeft: selectedShotIdx === idx ? '3px solid var(--accent-primary)' : '3px solid transparent',
            padding: '10px 12px',
          }"
          @click="emit('select-shot', idx)"
        >
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <span style="font-size: 13px; font-weight: 500;">Shot {{ shot.shot_number }}</span>
            <span :class="statusBadgeClass(shot.status || 'pending')" style="font-size: 10px; padding: 1px 6px; border-radius: 3px;">
              {{ shot.status || 'pending' }}
            </span>
          </div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <img
              v-if="shot.source_image_path"
              :src="sourceImageUrl(shot.source_image_path)"
              style="width: 48px; height: 48px; object-fit: cover; border-radius: 3px; flex-shrink: 0;"
              @error="($event.target as HTMLImageElement).style.display = 'none'"
            />
            <div v-else style="width: 48px; height: 48px; border-radius: 3px; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 10px; color: var(--status-warning);">
              no img
            </div>
            <div>
              <div style="font-size: 11px; color: var(--text-muted);">
                {{ shot.shot_type }}/{{ shot.camera_angle }} {{ shot.duration_seconds }}s
              </div>
              <div v-if="shot.motion_prompt" style="font-size: 11px; color: var(--text-secondary); margin-top: 2px; max-height: 30px; overflow: hidden;">
                {{ shot.motion_prompt }}
              </div>
            </div>
          </div>
        </div>

        <button class="btn" style="font-size: 12px; padding: 6px 12px; width: 100%;" @click="emit('add-shot')">
          + Add Shot
        </button>
      </div>
    </div>

    <!-- Right: Shot Details -->
    <ShotDetailsPanel
      v-if="selectedShotIdx >= 0 && shots[selectedShotIdx]"
      :shot="shots[selectedShotIdx]"
      :shot-video-src="shotVideoSrc"
      :source-image-url="sourceImageUrl"
      :characters="characters"
      @remove="emit('remove-shot', selectedShotIdx)"
      @browse-image="emit('browse-image')"
      @update-field="(field: string, value: unknown) => emit('update-shot-field', selectedShotIdx, field, value)"
    />
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watch } from 'vue'
import type { BuilderScene, BuilderShot, SceneAudio, GapAnalysisCharacter } from '@/types'
import { useProjectStore } from '@/stores/project'
import ShotDetailsPanel from './ShotDetailsPanel.vue'
import EchoAssistButton from '../EchoAssistButton.vue'
import SceneAudioPanel from './SceneAudioPanel.vue'

const projectStore = useProjectStore()

const props = defineProps<{
  scene: Partial<BuilderScene>
  sceneId: string | null
  shots: Partial<BuilderShot>[]
  selectedShotIdx: number
  saving: boolean
  generating: boolean
  shotVideoSrc: string
  sourceImageUrl: (path: string) => string
  characters: { slug: string; name: string }[]
  gapCharacters?: Record<string, GapAnalysisCharacter>
}>()

const emit = defineEmits<{
  save: []
  'confirm-generate': []
  back: []
  'select-shot': [idx: number]
  'add-shot': []
  'remove-shot': [idx: number]
  'browse-image': []
  'auto-assign': []
  'update-shot-field': [idx: number, field: string, value: unknown]
  'update-scene': [scene: Partial<BuilderScene>]
  'audio-changed': [audio: SceneAudio | null]
  'go-to-training': []
}>()

const allShotsHaveImages = computed(() =>
  props.shots.length > 0 && props.shots.every(s => !!s.source_image_path)
)

const unreadyCharacters = computed((): Array<{ slug: string; name: string; reason: string }> => {
  if (!props.gapCharacters) return []
  const slugsSeen = new Set<string>()
  const result: Array<{ slug: string; name: string; reason: string }> = []
  for (const shot of props.shots) {
    const chars = (shot.characters_present as string[]) || []
    for (const slug of chars) {
      if (slugsSeen.has(slug)) continue
      slugsSeen.add(slug)
      const gc = props.gapCharacters[slug]
      if (gc && !gc.has_lora) {
        const reason = gc.approved_count < 10
          ? `${gc.approved_count} images (need 10+)`
          : 'LoRA not yet trained'
        result.push({ slug, name: gc.name, reason })
      }
    }
  }
  return result
})

const timeOptions = ['dawn', 'morning', 'midday', 'afternoon', 'sunset', 'evening', 'night']
const weatherOptions = ['clear', 'cloudy', 'rain', 'snow', 'fog', 'storm']

// Story context
const storyContextOpen = ref(false)
const localStoryArc = ref('')

const storyline = computed(() => projectStore.currentProject?.storyline)
const worldSettings = computed(() => projectStore.worldSettings)

const worldLocation = computed(() => {
  const loc = worldSettings.value?.world_location
  if (!loc) return ''
  const parts = [loc.primary, loc.atmosphere].filter(Boolean)
  return parts.join(' — ')
})

const storyArcs = computed(() => storyline.value?.story_arcs || [])

const hasStoryContext = computed(() =>
  !!storyline.value?.summary || !!storyline.value?.theme || !!storyline.value?.tone || storyArcs.value.length > 0 || !!worldLocation.value
)

const echoScenePayload = computed(() => ({
  project_name: projectStore.currentProject?.name || undefined,
  project_genre: projectStore.currentProject?.genre || undefined,
  storyline_title: storyline.value?.title || undefined,
  storyline_summary: storyline.value?.summary || undefined,
  storyline_theme: storyline.value?.theme || undefined,
  concept_description: `Scene: ${localScene.title || ''}. Location: ${localScene.location || ''}. Mood: ${localScene.mood || ''}. Time: ${localScene.time_of_day || ''}.`,
}))

// Local reactive copy of scene data that syncs back to parent
const localScene = reactive<Partial<BuilderScene>>({ ...props.scene })
const localPostInterpolate = ref<number | null>(props.scene.post_interpolate_fps ?? null)
const localPostUpscale = ref<number | null>(props.scene.post_upscale_factor ?? null)

watch(() => props.scene, (newScene) => {
  Object.assign(localScene, newScene)
  localPostInterpolate.value = newScene.post_interpolate_fps ?? null
  localPostUpscale.value = newScene.post_upscale_factor ?? null
}, { deep: true })

watch(localScene, (val) => {
  emit('update-scene', { ...val })
}, { deep: true })

watch(localPostInterpolate, (val) => {
  localScene.post_interpolate_fps = val
})

watch(localPostUpscale, (val) => {
  localScene.post_upscale_factor = val
})

function statusBadgeClass(status: string): string {
  const map: Record<string, string> = {
    draft: 'badge-draft',
    pending: 'badge-draft',
    generating: 'badge-generating',
    completed: 'badge-completed',
    partial: 'badge-partial',
    failed: 'badge-failed',
  }
  return map[status] || 'badge-draft'
}

function estimateMinutes(shots: Partial<BuilderShot>[]): number {
  return shots.reduce((sum, s) => {
    const dur = s.duration_seconds || 3
    if (dur <= 2) return sum + 20
    if (dur <= 3) return sum + 13
    if (dur <= 5) return sum + 25
    return sum + 30
  }, 0)
}
</script>

<style scoped>
.field-group {
  margin-bottom: 10px;
}
.field-label {
  font-size: 12px;
  color: var(--text-secondary);
  display: block;
  margin-bottom: 4px;
}
.field-input {
  width: 100%;
  padding: 6px 8px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
  font-family: var(--font-primary);
}
.field-input:focus {
  border-color: var(--border-focus);
  outline: none;
}
.field-textarea {
  resize: vertical;
  min-height: 60px;
}
.field-row {
  display: flex;
  gap: 8px;
}
.field-row .field-group {
  flex: 1;
}

.badge-draft {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}
.badge-generating {
  background: rgba(122, 162, 247, 0.2);
  color: var(--accent-primary);
}
.badge-completed {
  background: rgba(80, 160, 80, 0.2);
  color: var(--status-success);
}
.badge-partial {
  background: rgba(160, 128, 80, 0.2);
  color: var(--status-warning);
}
.badge-failed {
  background: rgba(160, 80, 80, 0.2);
  color: var(--status-error);
}
</style>
