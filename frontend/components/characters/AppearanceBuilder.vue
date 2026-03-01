<template>
  <div class="appearance-builder">
    <div class="ab-row">
      <label class="ab-label">Gender</label>
      <div class="pill-row">
        <button
          v-for="opt in genderOpts"
          :key="opt"
          type="button"
          class="pill"
          :class="{ 'pill-active': fields.gender === opt }"
          @click="toggleField('gender', opt)"
        >{{ opt }}</button>
      </div>
    </div>

    <div class="ab-row">
      <label class="ab-label">Species</label>
      <div class="pill-row">
        <button
          v-for="opt in speciesOpts"
          :key="opt"
          type="button"
          class="pill"
          :class="{ 'pill-active': fields.species === opt }"
          @click="toggleField('species', opt)"
        >{{ opt }}</button>
      </div>
    </div>

    <div class="ab-row">
      <label class="ab-label">Hair Color</label>
      <div class="pill-row">
        <button
          v-for="opt in hairColorOpts"
          :key="opt"
          type="button"
          class="pill"
          :class="{ 'pill-active': fields.hairColor === opt }"
          @click="toggleField('hairColor', opt)"
        >{{ opt }}</button>
      </div>
    </div>

    <div class="ab-row">
      <label class="ab-label">Hair Style</label>
      <div class="pill-row">
        <button
          v-for="opt in hairStyleOpts"
          :key="opt"
          type="button"
          class="pill"
          :class="{ 'pill-active': fields.hairStyle === opt }"
          @click="toggleField('hairStyle', opt)"
        >{{ opt }}</button>
      </div>
    </div>

    <div class="ab-row">
      <label class="ab-label">Eye Color</label>
      <div class="pill-row">
        <button
          v-for="opt in eyeColorOpts"
          :key="opt"
          type="button"
          class="pill"
          :class="{ 'pill-active': fields.eyeColor === opt }"
          @click="toggleField('eyeColor', opt)"
        >{{ opt }}</button>
      </div>
    </div>

    <div class="ab-row">
      <label class="ab-label">Body</label>
      <div class="pill-row">
        <button
          v-for="opt in bodyOpts"
          :key="opt"
          type="button"
          class="pill"
          :class="{ 'pill-active': fields.body === opt }"
          @click="toggleField('body', opt)"
        >{{ opt }}</button>
      </div>
    </div>

    <div class="ab-row">
      <label class="ab-label">Clothing</label>
      <div class="pill-row">
        <button
          v-for="opt in clothingOpts"
          :key="opt"
          type="button"
          class="pill"
          :class="{ 'pill-active': fields.clothing === opt }"
          @click="toggleField('clothing', opt)"
        >{{ opt }}</button>
      </div>
    </div>

    <div class="ab-row">
      <label class="ab-label">Expression</label>
      <div class="pill-row">
        <button
          v-for="opt in expressionOpts"
          :key="opt"
          type="button"
          class="pill"
          :class="{ 'pill-active': fields.expression === opt }"
          @click="toggleField('expression', opt)"
        >{{ opt }}</button>
      </div>
    </div>

    <div class="ab-row">
      <label class="ab-label">Extra Tags</label>
      <ChipInput v-model="extras" placeholder="Add custom tag..." />
    </div>

    <div v-if="assembled" class="ab-preview">{{ assembled }}</div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watch } from 'vue'
import ChipInput from './ChipInput.vue'

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const genderOpts = ['1girl', '1boy', '1woman', '1man']
const speciesOpts = ['human', 'elf', 'android', 'demon', 'catgirl', 'vampire']
const hairColorOpts = ['black', 'brown', 'blonde', 'red', 'silver', 'white', 'pink', 'blue', 'purple', 'green']
const hairStyleOpts = ['long', 'short', 'medium', 'ponytail', 'twin tails', 'braids', 'bob', 'spiky', 'wavy', 'messy']
const eyeColorOpts = ['brown', 'blue', 'green', 'red', 'purple', 'gold', 'amber', 'heterochromia']
const bodyOpts = ['slim', 'athletic', 'muscular', 'curvy', 'petite', 'tall']
const clothingOpts = ['school uniform', 'armor', 'kimono', 'leather jacket', 'dress', 'suit', 'casual', 'military', 'maid', 'hoodie']
const expressionOpts = ['smile', 'serious', 'fierce', 'shy', 'confident', 'sad', 'angry', 'smirk']

type FieldKey = 'gender' | 'species' | 'hairColor' | 'hairStyle' | 'eyeColor' | 'body' | 'clothing' | 'expression'

const fields = reactive<Record<FieldKey, string>>({
  gender: '',
  species: '',
  hairColor: '',
  hairStyle: '',
  eyeColor: '',
  body: '',
  clothing: '',
  expression: '',
})

const extras = ref<string[]>([])

// Parse incoming modelValue into fields on mount
function parsePrompt(prompt: string) {
  if (!prompt) return
  const tags = prompt.split(',').map(t => t.trim()).filter(Boolean)
  for (const tag of tags) {
    const lower = tag.toLowerCase()
    if (genderOpts.includes(lower)) { fields.gender = lower; continue }
    if (speciesOpts.includes(lower)) { fields.species = lower; continue }

    const hairColorMatch = hairColorOpts.find(c => lower === `${c} hair`)
    if (hairColorMatch) { fields.hairColor = hairColorMatch; continue }

    const hairStyleMatch = hairStyleOpts.find(s => lower === `${s} hair`)
    if (hairStyleMatch) { fields.hairStyle = hairStyleMatch; continue }

    const eyeMatch = eyeColorOpts.find(c => lower === `${c} eyes`)
    if (eyeMatch) { fields.eyeColor = eyeMatch; continue }

    if (bodyOpts.includes(lower)) { fields.body = lower; continue }
    if (clothingOpts.includes(lower)) { fields.clothing = lower; continue }

    const exprMatch = expressionOpts.find(e => lower === `${e} expression`)
    if (exprMatch) { fields.expression = exprMatch; continue }

    if (lower === 'full body') continue
    // Unrecognized tag → extras
    extras.value.push(tag)
  }
}

parsePrompt(props.modelValue)

const assembled = computed(() => {
  const parts: string[] = []
  if (fields.gender) parts.push(fields.gender)
  if (fields.species && fields.species !== 'human') parts.push(fields.species)
  if (fields.hairColor) parts.push(`${fields.hairColor} hair`)
  if (fields.hairStyle) parts.push(`${fields.hairStyle} hair`)
  if (fields.eyeColor) parts.push(`${fields.eyeColor} eyes`)
  if (fields.body) parts.push(`${fields.body} body`)
  if (fields.clothing) parts.push(fields.clothing)
  if (fields.expression) parts.push(`${fields.expression} expression`)
  if (extras.value.length) parts.push(...extras.value)
  if (parts.length) parts.push('full body')
  return parts.join(', ')
})

function toggleField(key: FieldKey, value: string) {
  fields[key] = fields[key] === value ? '' : value
}

// Sync assembled → modelValue
let skipWatch = false
watch(assembled, (val) => {
  if (skipWatch) return
  emit('update:modelValue', val)
})

// Sync modelValue → fields when externally overridden (e.g. Echo Assist)
watch(() => props.modelValue, (val) => {
  if (val === assembled.value) return
  // External override — reset and reparse
  for (const key of Object.keys(fields) as FieldKey[]) fields[key] = ''
  extras.value = []
  skipWatch = true
  parsePrompt(val)
  skipWatch = false
})
</script>

<style scoped>
.appearance-builder {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ab-row {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.ab-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}
.pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.pill {
  padding: 2px 8px;
  font-size: 11px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 10px;
  cursor: pointer;
  font-family: var(--font-primary);
  transition: border-color 100ms ease, color 100ms ease, background 100ms ease;
}
.pill:hover {
  color: var(--text-primary);
  border-color: var(--text-muted);
}
.pill-active {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  background: rgba(122, 162, 247, 0.1);
}
.ab-preview {
  margin-top: 4px;
  padding: 6px 8px;
  font-size: 12px;
  font-family: var(--font-primary);
  background: var(--bg-primary);
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
