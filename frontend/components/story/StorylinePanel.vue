<template>
  <div class="column">
    <h3 class="column-title">Storyline</h3>

    <!-- Title -->
    <div class="field-group">
      <label class="field-label">Title</label>
      <input v-model="sl.title" type="text" placeholder="Story title" class="field-input" />
    </div>

    <!-- Summary + Echo -->
    <div class="field-group">
      <div class="label-row">
        <label class="field-label" style="margin-bottom: 0;">Summary</label>
        <EchoAssistButton
          context-type="storyline"
          :context-payload="storylineEchoPayload"
          :current-value="sl.summary"
          compact
          @accept="applyEchoSuggestion($event)"
        />
      </div>
      <textarea v-model="sl.summary" rows="4" placeholder="Story summary..." class="field-input field-textarea"></textarea>
    </div>

    <!-- Theme, Target Audience -->
    <div class="field-group">
      <label class="field-label">Theme</label>
      <input v-model="sl.theme" type="text" placeholder="friendship, heroism..." class="field-input" />
    </div>

    <div class="field-group">
      <label class="field-label">Target Audience</label>
      <input v-model="sl.target_audience" type="text" placeholder="kids, teens, all ages..." class="field-input" />
    </div>

    <!-- Tone -->
    <div class="field-group">
      <label class="field-label">Tone</label>
      <input v-model="sl.tone" type="text" placeholder="lighthearted, dark, satirical..." class="field-input" />
    </div>

    <!-- Humor Style -->
    <div class="field-group">
      <label class="field-label">Humor Style</label>
      <input v-model="sl.humor_style" type="text" placeholder="slapstick, dry wit, absurd..." class="field-input" />
    </div>

    <!-- Themes (tag chips) -->
    <div class="field-group">
      <label class="field-label">Themes</label>
      <div class="tag-input-wrapper">
        <span v-for="(tag, i) in sl.themes" :key="'theme-' + i" class="tag-chip">
          {{ tag }}
          <button class="tag-remove" @click="removeTag(sl.themes, i)">&times;</button>
        </span>
        <input
          v-model="themesInput"
          type="text"
          placeholder="Type + Enter to add"
          class="tag-inline-input"
          @keydown.enter.prevent="addTag(sl.themes, themesInput); themesInput = ''"
        />
      </div>
    </div>

    <!-- Story Arcs -->
    <div class="field-group">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
        <label class="field-label" style="margin-bottom: 0;">Story Arcs</label>
        <button class="btn" style="font-size: 10px; padding: 2px 8px;" @click="addArc">+ Add Arc</button>
      </div>
      <div v-if="!sl.story_arcs || sl.story_arcs.length === 0" style="font-size: 12px; color: var(--text-muted); padding: 8px;">
        No story arcs defined yet.
      </div>
      <div v-for="(arc, i) in sl.story_arcs" :key="'arc-' + i" class="arc-card">
        <div style="display: flex; gap: 8px; align-items: flex-start;">
          <div style="flex: 1;">
            <input
              :value="arcName(arc)"
              @input="updateArcField(i, 'arc_name', ($event.target as HTMLInputElement).value)"
              type="text"
              placeholder="Arc name"
              class="field-input"
              style="font-weight: 500; margin-bottom: 4px;"
            />
            <input
              :value="arcDescription(arc)"
              @input="updateArcField(i, 'description', ($event.target as HTMLInputElement).value)"
              type="text"
              placeholder="Brief description of this arc..."
              class="field-input"
              style="font-size: 12px;"
            />
          </div>
          <button class="tag-remove" style="margin-top: 4px; font-size: 16px;" @click="removeTag(sl.story_arcs, i)">&times;</button>
        </div>
      </div>
    </div>

    <!-- Save Storyline -->
    <div class="save-row">
      <button
        :class="['btn', saved ? 'btn-saved' : 'btn-primary']"
        class="save-btn"
        @click="$emit('save')"
        :disabled="saving || !dirty"
      >
        {{ saved ? 'Saved' : saving ? 'Saving...' : 'Save Storyline' }}
      </button>
      <span v-if="!dirty && !saved" class="no-changes">no changes</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import EchoAssistButton from '../EchoAssistButton.vue'

interface StoryArc {
  arc_name: string
  description?: string
  episodes?: string
}

interface StorylineForm {
  title: string
  summary: string
  theme: string
  genre: string
  target_audience: string
  tone: string
  humor_style: string
  themes: string[]
  story_arcs: (string | StoryArc)[]
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

const props = defineProps<{
  sl: StorylineForm
  storylineEchoPayload: EchoPayload
  dirty: boolean
  saved: boolean
  saving: boolean
}>()

defineEmits<{
  (e: 'save'): void
}>()

// Tag input temporaries
const themesInput = ref('')

// Apply Echo Brain structured suggestion — populates all matching fields
function applyEchoSuggestion(event: { suggestion: string; contextType: string; fields?: Record<string, any> }) {
  const f = event.fields
  if (f) {
    if (f.summary) props.sl.summary = f.summary
    if (f.theme) props.sl.theme = f.theme
    if (f.tone) props.sl.tone = f.tone
    if (f.target_audience) props.sl.target_audience = f.target_audience
    if (f.humor_style) props.sl.humor_style = f.humor_style
    if (Array.isArray(f.themes) && f.themes.length > 0) {
      props.sl.themes.splice(0, props.sl.themes.length, ...f.themes)
    }
    if (Array.isArray(f.story_arcs) && f.story_arcs.length > 0) {
      const arcs = f.story_arcs.map((a: any) =>
        typeof a === 'string' ? { arc_name: a, description: '' } : a
      )
      props.sl.story_arcs.splice(0, props.sl.story_arcs.length, ...arcs)
    }
  } else {
    // Fallback: plain text goes into summary
    props.sl.summary = event.suggestion
  }
}

function addTag(arr: string[], value: string) {
  const v = value.trim()
  if (v && !arr.includes(v)) {
    arr.push(v)
  }
}

function removeTag(arr: unknown[], index: number) {
  arr.splice(index, 1)
}

// Story arc helpers
function arcName(arc: string | StoryArc): string {
  return typeof arc === 'string' ? arc : arc.arc_name || ''
}

function arcDescription(arc: string | StoryArc): string {
  return typeof arc === 'string' ? '' : arc.description || ''
}

function addArc() {
  if (!props.sl.story_arcs) {
    (props.sl as any).story_arcs = []
  }
  props.sl.story_arcs.push({ arc_name: '', description: '' })
}

function updateArcField(index: number, field: string, value: string) {
  const arc = props.sl.story_arcs[index]
  if (typeof arc === 'string') {
    // Upgrade string to object
    const obj: StoryArc = { arc_name: arc, description: '' }
    ;(obj as any)[field] = value
    props.sl.story_arcs[index] = obj
  } else {
    ;(arc as any)[field] = value
  }
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

.arc-card {
  padding: 8px 10px;
  margin-bottom: 6px;
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-left: 3px solid var(--accent-primary);
  border-radius: 4px;
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
