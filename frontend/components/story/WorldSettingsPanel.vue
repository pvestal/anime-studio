<template>
  <div class="column">
    <h3 class="column-title">World Settings</h3>

    <!-- Style Preamble (THE key field) -->
    <div class="field-group style-preamble-group">
      <div class="label-row">
        <label class="field-label" style="margin-bottom: 0; font-weight: 600; color: var(--accent-primary);">Style Preamble</label>
        <EchoAssistButton
          context-type="positive_template"
          :context-payload="preambleEchoPayload"
          :current-value="ws.style_preamble"
          compact
          @accept="ws.style_preamble = $event.suggestion"
        />
      </div>
      <p class="preamble-hint">This text auto-prepends to every character's design prompt at generation time.</p>
      <textarea v-model="ws.style_preamble" rows="4" placeholder="e.g. masterpiece, best quality, highly detailed, anime style..." class="field-input field-textarea preamble-textarea"></textarea>
    </div>

    <!-- Art Style + Aesthetic -->
    <div class="field-row">
      <div class="field-group">
        <label class="field-label">Art Style</label>
        <input v-model="ws.art_style" type="text" placeholder="anime, realistic, watercolor..." class="field-input" />
      </div>
      <div class="field-group">
        <label class="field-label">Aesthetic</label>
        <input v-model="ws.aesthetic" type="text" placeholder="cyberpunk, pastoral, retro..." class="field-input" />
      </div>
    </div>

    <!-- Color Palette -->
    <div class="field-group">
      <label class="field-label section-label">Color Palette</label>
      <div class="sub-field">
        <label class="field-label">Primary</label>
        <div class="tag-input-wrapper">
          <span v-for="(tag, i) in ws.color_palette.primary" :key="'cp-' + i" class="tag-chip">
            {{ tag }}
            <button class="tag-remove" @click="removeTag(ws.color_palette.primary, i)">&times;</button>
          </span>
          <input
            v-model="cpPrimaryInput"
            type="text"
            placeholder="Type + Enter"
            class="tag-inline-input"
            @keydown.enter.prevent="addTag(ws.color_palette.primary, cpPrimaryInput); cpPrimaryInput = ''"
          />
        </div>
      </div>
      <div class="sub-field">
        <label class="field-label">Secondary</label>
        <div class="tag-input-wrapper">
          <span v-for="(tag, i) in ws.color_palette.secondary" :key="'cs-' + i" class="tag-chip">
            {{ tag }}
            <button class="tag-remove" @click="removeTag(ws.color_palette.secondary, i)">&times;</button>
          </span>
          <input
            v-model="cpSecondaryInput"
            type="text"
            placeholder="Type + Enter"
            class="tag-inline-input"
            @keydown.enter.prevent="addTag(ws.color_palette.secondary, cpSecondaryInput); cpSecondaryInput = ''"
          />
        </div>
      </div>
      <div class="sub-field">
        <label class="field-label">Environmental</label>
        <div class="tag-input-wrapper">
          <span v-for="(tag, i) in ws.color_palette.environmental" :key="'ce-' + i" class="tag-chip">
            {{ tag }}
            <button class="tag-remove" @click="removeTag(ws.color_palette.environmental, i)">&times;</button>
          </span>
          <input
            v-model="cpEnvInput"
            type="text"
            placeholder="Type + Enter"
            class="tag-inline-input"
            @keydown.enter.prevent="addTag(ws.color_palette.environmental, cpEnvInput); cpEnvInput = ''"
          />
        </div>
      </div>
    </div>

    <!-- Cinematography -->
    <div class="field-group">
      <label class="field-label section-label">Cinematography</label>
      <div class="sub-field">
        <label class="field-label">Shot Types</label>
        <div class="tag-input-wrapper">
          <span v-for="(tag, i) in ws.cinematography.shot_types" :key="'st-' + i" class="tag-chip">
            {{ tag }}
            <button class="tag-remove" @click="removeTag(ws.cinematography.shot_types, i)">&times;</button>
          </span>
          <input
            v-model="shotTypesInput"
            type="text"
            placeholder="Type + Enter"
            class="tag-inline-input"
            @keydown.enter.prevent="addTag(ws.cinematography.shot_types, shotTypesInput); shotTypesInput = ''"
          />
        </div>
      </div>
      <div class="sub-field">
        <label class="field-label">Camera Angles</label>
        <div class="tag-input-wrapper">
          <span v-for="(tag, i) in ws.cinematography.camera_angles" :key="'ca-' + i" class="tag-chip">
            {{ tag }}
            <button class="tag-remove" @click="removeTag(ws.cinematography.camera_angles, i)">&times;</button>
          </span>
          <input
            v-model="cameraAnglesInput"
            type="text"
            placeholder="Type + Enter"
            class="tag-inline-input"
            @keydown.enter.prevent="addTag(ws.cinematography.camera_angles, cameraAnglesInput); cameraAnglesInput = ''"
          />
        </div>
      </div>
      <div class="sub-field">
        <label class="field-label">Lighting</label>
        <textarea v-model="ws.cinematography.lighting" rows="2" placeholder="Lighting description..." class="field-input field-textarea"></textarea>
      </div>
    </div>

    <!-- World Location -->
    <div class="field-group">
      <label class="field-label section-label">World Location</label>
      <div class="sub-field">
        <label class="field-label">Primary</label>
        <input v-model="ws.world_location.primary" type="text" placeholder="Main setting location..." class="field-input" />
      </div>
      <div class="sub-field">
        <label class="field-label">Areas</label>
        <div class="tag-input-wrapper">
          <span v-for="(tag, i) in ws.world_location.areas" :key="'area-' + i" class="tag-chip">
            {{ tag }}
            <button class="tag-remove" @click="removeTag(ws.world_location.areas, i)">&times;</button>
          </span>
          <input
            v-model="areasInput"
            type="text"
            placeholder="Type + Enter"
            class="tag-inline-input"
            @keydown.enter.prevent="addTag(ws.world_location.areas, areasInput); areasInput = ''"
          />
        </div>
      </div>
      <div class="sub-field">
        <label class="field-label">Atmosphere</label>
        <textarea v-model="ws.world_location.atmosphere" rows="2" placeholder="Environmental atmosphere..." class="field-input field-textarea"></textarea>
      </div>
    </div>

    <!-- Time Period -->
    <div class="field-group">
      <label class="field-label">Time Period</label>
      <input v-model="ws.time_period" type="text" placeholder="modern, medieval, far future..." class="field-input" />
    </div>

    <!-- Production Notes + Echo -->
    <div class="field-group">
      <div class="label-row">
        <label class="field-label" style="margin-bottom: 0;">Production Notes</label>
        <EchoAssistButton
          context-type="production_notes"
          :context-payload="productionNotesEchoPayload"
          :current-value="ws.production_notes"
          compact
          @accept="ws.production_notes = $event.suggestion"
        />
      </div>
      <textarea v-model="ws.production_notes" rows="3" placeholder="Notes for the production team..." class="field-input field-textarea"></textarea>
    </div>

    <!-- Known Issues (tag chips) -->
    <div class="field-group">
      <label class="field-label">Known Issues</label>
      <div class="tag-input-wrapper">
        <span v-for="(tag, i) in ws.known_issues" :key="'ki-' + i" class="tag-chip tag-chip-warning">
          {{ tag }}
          <button class="tag-remove" @click="removeTag(ws.known_issues, i)">&times;</button>
        </span>
        <input
          v-model="knownIssuesInput"
          type="text"
          placeholder="Type + Enter to add"
          class="tag-inline-input"
          @keydown.enter.prevent="addTag(ws.known_issues, knownIssuesInput); knownIssuesInput = ''"
        />
      </div>
    </div>

    <!-- Negative Prompt Guidance -->
    <div class="field-group">
      <label class="field-label">Negative Prompt Guidance</label>
      <textarea v-model="ws.negative_prompt_guidance" rows="3" placeholder="Guidance for negative prompts..." class="field-input field-textarea"></textarea>
    </div>

    <!-- Save World Settings -->
    <div class="save-row">
      <button
        :class="['btn', saved ? 'btn-saved' : 'btn-primary']"
        class="save-btn"
        @click="$emit('save')"
        :disabled="saving || !dirty"
      >
        {{ saved ? 'Saved' : saving ? 'Saving...' : 'Save World Settings' }}
      </button>
      <span v-if="!dirty && !saved" class="no-changes">no changes</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import EchoAssistButton from '../EchoAssistButton.vue'

interface WorldSettingsForm {
  style_preamble: string
  art_style: string
  aesthetic: string
  color_palette: { primary: string[]; secondary: string[]; environmental: string[] }
  cinematography: { shot_types: string[]; camera_angles: string[]; lighting: string }
  world_location: { primary: string; areas: string[]; atmosphere: string }
  time_period: string
  production_notes: string
  known_issues: string[]
  negative_prompt_guidance: string
}

interface EchoPayload {
  project_name?: string
  project_genre?: string
  project_description?: string
  project_premise?: string
  checkpoint_model?: string
  storyline_title?: string
  storyline_summary?: string
  storyline_theme?: string
}

interface PreambleEchoPayload {
  project_name?: string
  project_genre?: string
  project_premise?: string
  checkpoint_model?: string
}

defineProps<{
  ws: WorldSettingsForm
  preambleEchoPayload: PreambleEchoPayload
  productionNotesEchoPayload: EchoPayload
  dirty: boolean
  saved: boolean
  saving: boolean
}>()

defineEmits<{
  (e: 'save'): void
}>()

// Tag input temporaries
const cpPrimaryInput = ref('')
const cpSecondaryInput = ref('')
const cpEnvInput = ref('')
const shotTypesInput = ref('')
const cameraAnglesInput = ref('')
const areasInput = ref('')
const knownIssuesInput = ref('')

function addTag(arr: string[], value: string) {
  const v = value.trim()
  if (v && !arr.includes(v)) {
    arr.push(v)
  }
}

function removeTag(arr: string[], index: number) {
  arr.splice(index, 1)
}
</script>

<style scoped>
.column {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  padding: 20px;
}

.column-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 16px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-primary);
}

.field-group {
  margin-bottom: 14px;
}

.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.field-label {
  font-size: 11px;
  color: var(--text-muted);
  display: block;
  margin-bottom: 4px;
}

.section-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-bottom: 8px;
}

.field-input {
  padding: 5px 8px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
  font-family: inherit;
  width: 100%;
  box-sizing: border-box;
}

.field-input:focus {
  border-color: var(--border-focus);
  outline: none;
}

.field-textarea {
  resize: vertical;
  line-height: 1.5;
}

.label-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.sub-field {
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 2px solid var(--border-primary);
}

/* Style Preamble prominence */
.style-preamble-group {
  padding: 12px;
  border: 2px solid var(--accent-primary);
  border-radius: 6px;
  border-left: 5px solid var(--accent-primary);
  background: var(--bg-tertiary);
}

.preamble-hint {
  font-size: 11px;
  color: var(--accent-primary);
  margin: 2px 0 8px 0;
  opacity: 0.85;
}

.preamble-textarea {
  border-color: var(--accent-primary);
}

.preamble-textarea:focus {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 1px var(--accent-primary);
}

/* Tag chip input */
.tag-input-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 4px 6px;
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
  min-height: 32px;
  align-items: center;
}

.tag-input-wrapper:focus-within {
  border-color: var(--border-focus);
}

.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
  font-size: 11px;
  color: var(--text-primary);
  white-space: nowrap;
}

.tag-chip-warning {
  border-color: var(--status-warning);
  color: var(--status-warning);
}

.tag-remove {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  padding: 0 2px;
  display: inline-flex;
  align-items: center;
}

.tag-remove:hover {
  color: var(--text-primary);
}

.tag-inline-input {
  flex: 1;
  min-width: 80px;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 12px;
  padding: 2px 4px;
  font-family: inherit;
}

/* Save row */
.save-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border-primary);
}

.save-btn {
  font-size: 12px;
  padding: 5px 14px;
  transition: all 200ms ease;
}

.no-changes {
  font-size: 11px;
  color: var(--text-muted);
}

.btn-saved {
  background: var(--status-success) !important;
  color: var(--bg-primary) !important;
  border-color: var(--status-success) !important;
}
</style>
