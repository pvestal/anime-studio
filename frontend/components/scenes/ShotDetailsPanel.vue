<template>
  <div v-if="shot" class="card" style="flex: 1; min-width: 300px;">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
      <div style="font-size: 13px; font-weight: 500; color: var(--accent-primary);">
        Shot {{ shot.shot_number }} Details
      </div>
      <button class="btn btn-danger" style="font-size: 11px; padding: 2px 8px;" @click="$emit('remove')">Delete</button>
    </div>

    <!-- Source Image -->
    <div class="field-group">
      <label class="field-label">Source Image</label>
      <div style="display: flex; gap: 8px; align-items: center;">
        <input
          :value="shot.source_image_path"
          @input="updateField('source_image_path', ($event.target as HTMLInputElement).value)"
          type="text"
          placeholder="character_slug/images/filename.png"
          class="field-input"
          style="flex: 1;"
        />
        <button class="btn" style="font-size: 11px; padding: 4px 8px;" @click="$emit('browse-image')">Browse</button>
      </div>
      <div v-if="shot.source_image_path" style="display: flex; align-items: center; gap: 6px; margin-top: 6px;">
        <span
          v-if="shot.source_image_auto_assigned"
          class="source-badge source-badge--auto"
          title="Auto-assigned by recommender"
        >auto</span>
        <span
          v-else-if="shot.source_image_path"
          class="source-badge source-badge--manual"
          title="Manually selected"
        >manual</span>
        <span
          v-if="shot.quality_score != null"
          class="source-badge"
          :class="shot.quality_score >= 0.65 ? 'source-badge--good' : shot.quality_score >= 0.4 ? 'source-badge--ok' : 'source-badge--poor'"
          :title="`Video quality: ${(shot.quality_score * 100).toFixed(0)}%`"
        >{{ (shot.quality_score * 100).toFixed(0) }}% quality</span>
      </div>
      <div v-if="shot.source_image_path" style="margin-top: 8px;">
        <img
          :src="sourceImageUrl(shot.source_image_path || '')"
          style="max-width: 200px; max-height: 150px; border-radius: 4px; border: 1px solid var(--border-primary);"
          @error="($event.target as HTMLImageElement).style.display = 'none'"
        />
      </div>
    </div>

    <div class="field-row">
      <div class="field-group">
        <label class="field-label">Shot Type</label>
        <select :value="shot.shot_type" @change="updateField('shot_type', ($event.target as HTMLSelectElement).value)" class="field-input">
          <option v-for="t in shotTypes" :key="t" :value="t">{{ t }}</option>
        </select>
      </div>
      <div class="field-group">
        <label class="field-label">Camera Angle</label>
        <select :value="shot.camera_angle" @change="updateField('camera_angle', ($event.target as HTMLSelectElement).value)" class="field-input">
          <option v-for="a in cameraAngles" :key="a" :value="a">{{ a }}</option>
        </select>
      </div>
    </div>

    <div class="field-group">
      <label class="field-label">Duration: {{ shot.duration_seconds }}s</label>
      <input
        :value="shot.duration_seconds"
        @input="updateField('duration_seconds', Number(($event.target as HTMLInputElement).value))"
        type="range" min="2" max="10" step="1"
        style="width: 100%;"
      />
    </div>

    <div class="field-group">
      <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
        <label class="field-label" style="margin-bottom: 0;">Motion Prompt</label>
        <EchoAssistButton
          context-type="motion_prompt"
          :context-payload="{
            project_name: projectStore.currentProject?.name,
            shot_type: shot.shot_type,
            scene_description: shot.motion_prompt ?? undefined,
          }"
          :current-value="shot.motion_prompt || ''"
          compact
          @accept="updateField('motion_prompt', $event.suggestion)"
        />
      </div>
      <div v-if="motionPresets.length > 0" style="display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px;">
        <button
          v-for="preset in motionPresets"
          :key="preset"
          class="preset-chip"
          @click="updateField('motion_prompt', preset)"
        >{{ preset }}</button>
      </div>
      <textarea
        :value="shot.motion_prompt"
        @input="updateField('motion_prompt', ($event.target as HTMLTextAreaElement).value)"
        rows="4"
        :placeholder="motionPlaceholder"
        class="field-input field-textarea"
      ></textarea>
    </div>

    <div class="field-row">
      <div class="field-group">
        <label class="field-label">Seed</label>
        <input
          :value="shot.seed"
          @input="updateField('seed', ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : null)"
          type="number" placeholder="Random"
          class="field-input"
        />
      </div>
      <div class="field-group">
        <label class="field-label">Steps</label>
        <select
          :value="shot.steps"
          @change="updateField('steps', ($event.target as HTMLSelectElement).value ? Number(($event.target as HTMLSelectElement).value) : null)"
          class="field-input"
        >
          <option :value="null">Default (25)</option>
          <option :value="15">15</option>
          <option :value="20">20</option>
          <option :value="25">25</option>
          <option :value="30">30</option>
        </select>
      </div>
    </div>

    <div class="field-group">
      <label class="field-label">Video Engine</label>
      <select
        :value="shot.video_engine || 'framepack'"
        @change="updateField('video_engine', ($event.target as HTMLSelectElement).value)"
        class="field-input"
      >
        <option value="framepack">FramePack (I2V, highest quality)</option>
        <option value="framepack_f1">FramePack F1 (I2V, faster)</option>
        <option value="ltx">LTX-Video (I2V/T2V, LoRA support)</option>
        <option value="wan">Wan T2V (text-only, environments)</option>
      </select>
      <div v-if="shot.video_engine === 'wan'" style="font-size: 10px; color: var(--status-warning); margin-top: 3px;">
        No source image needed — generates from motion prompt text only
      </div>
    </div>

    <div class="field-row">
      <div class="field-group">
        <label class="field-label">Transition</label>
        <select
          :value="shot.transition_type || 'dissolve'"
          @change="updateField('transition_type', ($event.target as HTMLSelectElement).value)"
          class="field-input"
        >
          <option value="dissolve">Dissolve</option>
          <option value="fade">Fade</option>
          <option value="fadeblack">Fade Black</option>
          <option value="wipeleft">Wipe Left</option>
        </select>
      </div>
      <div class="field-group">
        <label class="field-label">Transition (s)</label>
        <input
          :value="shot.transition_duration ?? 0.3"
          @input="updateField('transition_duration', Number(($event.target as HTMLInputElement).value))"
          type="number" min="0.1" max="2" step="0.1"
          class="field-input"
        />
      </div>
    </div>

    <!-- Dialogue (promoted — always visible when characters present) -->
    <div class="dialogue-section">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
        <label class="field-label" style="margin-bottom: 0; font-weight: 500; color: var(--accent-primary);">Dialogue</label>
        <button
          v-if="characters.length > 0"
          class="btn"
          style="font-size: 10px; padding: 2px 8px; color: var(--accent-primary);"
          :disabled="autoDialogueBusy"
          @click="$emit('auto-dialogue')"
        >
          {{ autoDialogueBusy ? 'Writing...' : 'Auto-Write' }}
        </button>
      </div>
      <select
        :value="shot.dialogue_character_slug || ''"
        @change="updateField('dialogue_character_slug', ($event.target as HTMLSelectElement).value || null)"
        class="field-input"
        style="margin-bottom: 6px;"
      >
        <option value="">No dialogue</option>
        <option
          v-for="c in characters"
          :key="c.slug"
          :value="c.slug"
        >{{ c.name }}</option>
      </select>
      <textarea
        v-if="shot.dialogue_character_slug"
        :value="shot.dialogue_text"
        @input="updateField('dialogue_text', ($event.target as HTMLTextAreaElement).value)"
        rows="3"
        placeholder="What does this character say?"
        class="field-input field-textarea"
      ></textarea>
      <div v-if="shot.dialogue_character_slug && shot.dialogue_text" style="display: flex; align-items: center; gap: 8px; margin-top: 6px;">
        <button
          class="btn"
          style="font-size: 11px; padding: 3px 10px;"
          :disabled="synthBusy"
          @click="synthesizeAndPlay"
        >
          {{ synthBusy ? 'Generating...' : dialogueAudioUrl ? 'Re-generate' : 'Play Voice' }}
        </button>
        <span v-if="synthEngine" class="source-badge source-badge--auto" style="font-size: 10px;">{{ synthEngine }}</span>
        <span v-if="synthDuration" style="font-size: 10px; color: var(--text-secondary);">{{ synthDuration }}s</span>
        <audio v-if="dialogueAudioUrl" ref="audioPlayer" :src="dialogueAudioUrl" controls style="height: 28px; flex: 1;" />
      </div>
    </div>

    <!-- Character State (NSM) -->
    <div v-if="characterStates.length > 0" class="state-section">
      <div
        class="state-header"
        @click="stateExpanded = !stateExpanded"
      >
        <span class="field-label" style="margin-bottom: 0; font-weight: 500; cursor: pointer;">
          Character State {{ stateExpanded ? '▾' : '▸' }}
        </span>
        <span
          v-for="cs in characterStates"
          :key="cs.character_slug"
          class="source-badge"
          :class="cs.state_source === 'manual' ? 'source-badge--manual' : 'source-badge--auto'"
          style="font-size: 9px;"
        >{{ cs.state_source }}</span>
      </div>
      <div v-if="stateExpanded">
        <div v-for="cs in characterStates" :key="cs.character_slug" class="state-card">
          <div style="font-size: 11px; font-weight: 500; color: var(--accent-primary); margin-bottom: 4px;">{{ cs.character_slug }}</div>
          <div class="state-grid">
            <div v-if="cs.clothing" class="state-item">
              <span class="state-label">Clothing</span>
              <span class="state-value">{{ cs.clothing }}</span>
            </div>
            <div v-if="cs.emotional_state && cs.emotional_state !== 'calm'" class="state-item">
              <span class="state-label">Emotion</span>
              <span class="state-value">{{ cs.emotional_state }}</span>
            </div>
            <div v-if="cs.hair_state" class="state-item">
              <span class="state-label">Hair</span>
              <span class="state-value">{{ cs.hair_state }}</span>
            </div>
            <div v-if="cs.body_state && cs.body_state !== 'clean'" class="state-item">
              <span class="state-label">Body</span>
              <span class="state-value">{{ cs.body_state }}</span>
            </div>
            <div v-if="cs.energy_level && cs.energy_level !== 'normal'" class="state-item">
              <span class="state-label">Energy</span>
              <span class="state-value">{{ cs.energy_level }}</span>
            </div>
            <div v-if="cs.location_in_scene" class="state-item">
              <span class="state-label">Position</span>
              <span class="state-value">{{ cs.location_in_scene }}</span>
            </div>
            <div v-if="cs.accessories && cs.accessories.length" class="state-item">
              <span class="state-label">Accessories</span>
              <span class="state-value">{{ cs.accessories.join(', ') }}</span>
            </div>
            <div v-if="cs.carrying && cs.carrying.length" class="state-item">
              <span class="state-label">Carrying</span>
              <span class="state-value">{{ cs.carrying.join(', ') }}</span>
            </div>
          </div>
          <div v-if="cs.injuries && cs.injuries.length" style="margin-top: 4px;">
            <span class="state-label">Injuries</span>
            <span
              v-for="(inj, i) in cs.injuries"
              :key="i"
              class="source-badge source-badge--poor"
              style="font-size: 9px; margin-left: 4px;"
            >{{ inj.severity }} {{ inj.type }} ({{ inj.location }})</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="shot.error_message" style="margin-top: 8px; padding: 8px; background: rgba(160,80,80,0.15); border-radius: 4px; font-size: 12px; color: var(--status-error);">
      Error: {{ shot.error_message }}
    </div>

    <div v-if="shot.output_video_path" style="margin-top: 12px;">
      <video
        :src="shotVideoSrc"
        controls
        style="max-width: 100%; border-radius: 4px;"
      ></video>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { BuilderShot, CharacterSceneState } from '@/types'
import { scenesApi } from '@/api/scenes'
import { useProjectStore } from '@/stores/project'
import EchoAssistButton from '../EchoAssistButton.vue'

const projectStore = useProjectStore()

const props = defineProps<{
  shot: Partial<BuilderShot> | null
  shotVideoSrc: string
  sourceImageUrl: (path: string) => string
  characters: { slug: string; name: string }[]
  autoDialogueBusy?: boolean
}>()

const emit = defineEmits<{
  remove: []
  'browse-image': []
  'update-field': [field: string, value: unknown]
  'auto-dialogue': []
}>()

const shotTypes = ['establishing', 'wide', 'medium', 'close-up', 'extreme_close-up', 'action']
const cameraAngles = ['eye-level', 'high', 'low', 'dutch', 'pov']

const stateExpanded = ref(false)
const characterStates = ref<CharacterSceneState[]>([])

const synthBusy = ref(false)
const dialogueAudioUrl = ref<string | null>(null)
const synthEngine = ref<string | null>(null)
const synthDuration = ref<number | null>(null)
const audioPlayer = ref<HTMLAudioElement | null>(null)

async function synthesizeAndPlay() {
  const shotId = (props.shot as any)?.id
  if (!shotId || !props.shot?.dialogue_text || !props.shot?.dialogue_character_slug) return
  synthBusy.value = true
  try {
    const result = await scenesApi.synthesizeShotDialogue(shotId)
    synthEngine.value = result.engine_used
    synthDuration.value = result.duration_seconds
    dialogueAudioUrl.value = scenesApi.synthesisAudioUrl(result.job_id)
    // Auto-play after a tick to let the audio element mount
    await new Promise(r => setTimeout(r, 100))
    audioPlayer.value?.play()
  } catch (e: any) {
    console.error('Voice synthesis failed:', e)
    alert(`Voice synthesis failed: ${e.message || e}`)
  } finally {
    synthBusy.value = false
  }
}

// Reset audio and fetch character states when shot changes
watch(() => (props.shot as any)?.id, async () => {
  dialogueAudioUrl.value = null
  synthEngine.value = null
  synthDuration.value = null
  characterStates.value = []
  stateExpanded.value = false

  // Fetch narrative states for this shot's scene
  const shotAny = props.shot as any
  if (shotAny?.scene_id) {
    try {
      const baseUrl = (scenesApi as any).baseUrl || '/anime-studio/api'
      const resp = await fetch(`${baseUrl}/narrative/state/${shotAny.scene_id}`)
      if (resp.ok) {
        const data = await resp.json()
        const chars = shotAny.characters_present || []
        characterStates.value = (data.states || []).filter(
          (s: CharacterSceneState) => chars.length === 0 || chars.includes(s.character_slug)
        )
      }
    } catch {
      // NSM not available — silently skip
    }
  }
})

const motionPresets = ref<string[]>([])

const motionPlaceholder = computed(() => {
  const type = props.shot?.shot_type || 'medium'
  const hints: Record<string, string> = {
    'close-up': 'subtle breathing, eyes shifting, light flickering across face...',
    'extreme_close-up': 'pupil dilation, tear rolling down cheek, lips trembling...',
    'establishing': 'slow pan across cityscape, clouds drifting, lights flickering...',
    'wide': 'characters walking through scene, wind in environment...',
    'medium': 'character gesturing, shifting weight, looking around...',
    'action': 'running forward, sword swing, cape billowing in wind...',
  }
  return hints[type] || 'Describe the motion/action in this shot...'
})

async function loadPresets(shotType: string) {
  try {
    const data = await scenesApi.getMotionPresets(shotType)
    motionPresets.value = Array.isArray(data.presets) ? data.presets : []
  } catch {
    motionPresets.value = []
  }
}

watch(() => props.shot?.shot_type, (newType) => {
  if (newType) loadPresets(newType)
  else motionPresets.value = []
}, { immediate: true })

function updateField(field: string, value: unknown) {
  emit('update-field', field, value)
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
.preset-chip {
  padding: 2px 8px;
  font-size: 11px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
  cursor: pointer;
  font-family: var(--font-primary);
  white-space: nowrap;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}
.preset-chip:hover {
  background: rgba(122, 162, 247, 0.15);
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.source-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 500;
  line-height: 1.4;
}
.source-badge--auto {
  background: rgba(122, 162, 247, 0.15);
  color: var(--accent-primary);
  border: 1px solid rgba(122, 162, 247, 0.3);
}
.source-badge--manual {
  background: rgba(160, 160, 160, 0.1);
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
}
.source-badge--good {
  background: rgba(80, 200, 120, 0.15);
  color: #50c878;
  border: 1px solid rgba(80, 200, 120, 0.3);
}
.source-badge--ok {
  background: rgba(240, 180, 60, 0.15);
  color: #f0b43c;
  border: 1px solid rgba(240, 180, 60, 0.3);
}
.source-badge--poor {
  background: rgba(200, 80, 80, 0.15);
  color: #c85050;
  border: 1px solid rgba(200, 80, 80, 0.3);
}
.state-section {
  border-top: 1px solid var(--border-primary);
  padding-top: 8px;
  margin-top: 8px;
}
.state-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  cursor: pointer;
}
.state-card {
  background: rgba(122, 162, 247, 0.04);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  padding: 8px;
  margin-bottom: 6px;
}
.state-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3px 12px;
}
.state-item {
  display: flex;
  gap: 4px;
  font-size: 11px;
}
.state-label {
  color: var(--text-secondary);
  font-weight: 500;
  min-width: 60px;
}
.state-value {
  color: var(--text-primary);
  word-break: break-word;
}
.dialogue-section {
  border-top: 2px solid var(--accent-primary);
  padding-top: 10px;
  margin-top: 8px;
  background: rgba(122, 162, 247, 0.04);
  margin-left: -12px;
  margin-right: -12px;
  padding-left: 12px;
  padding-right: 12px;
  padding-bottom: 8px;
  border-radius: 0 0 4px 4px;
}
</style>
