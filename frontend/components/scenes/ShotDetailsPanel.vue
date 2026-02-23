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

    <!-- Dialogue -->
    <div class="field-group" style="border-top: 1px solid var(--border-primary); padding-top: 10px; margin-top: 6px;">
      <label class="field-label">Dialogue</label>
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
        rows="2"
        placeholder="What does this character say?"
        class="field-input field-textarea"
      ></textarea>
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
import type { BuilderShot } from '@/types'
import { scenesApi } from '@/api/scenes'
import { useProjectStore } from '@/stores/project'
import EchoAssistButton from '../EchoAssistButton.vue'

const projectStore = useProjectStore()

const props = defineProps<{
  shot: Partial<BuilderShot> | null
  shotVideoSrc: string
  sourceImageUrl: (path: string) => string
  characters: { slug: string; name: string }[]
}>()

const emit = defineEmits<{
  remove: []
  'browse-image': []
  'update-field': [field: string, value: unknown]
}>()

const shotTypes = ['establishing', 'wide', 'medium', 'close-up', 'extreme_close-up', 'action']
const cameraAngles = ['eye-level', 'high', 'low', 'dutch', 'pov']

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
</style>
