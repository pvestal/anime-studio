<template>
  <div class="kv-editor">
    <div v-for="(key, i) in keys" :key="i" class="kv-row">
      <input
        :value="key"
        class="kv-input"
        :placeholder="keyPlaceholder"
        @input="updateKey(i, ($event.target as HTMLInputElement).value)"
      />
      <input
        :value="modelValue[key]"
        class="kv-input"
        :placeholder="valuePlaceholder"
        @input="updateValue(key, ($event.target as HTMLInputElement).value)"
      />
      <button class="btn kv-remove" @click="removeEntry(key)">&times;</button>
    </div>
    <button class="btn" style="font-size: 10px; padding: 1px 6px; margin-top: 4px;" @click="addEntry">+ Add</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: Record<string, string>
  keyPlaceholder?: string
  valuePlaceholder?: string
}>(), {
  keyPlaceholder: 'Key',
  valuePlaceholder: 'Value',
})

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, string>]
}>()

const keys = computed(() => Object.keys(props.modelValue))

function addEntry() {
  const next = { ...props.modelValue }
  let newKey = ''
  let n = 1
  while (newKey in next || newKey === '') {
    newKey = `key${n}`
    n++
  }
  next[newKey] = ''
  emit('update:modelValue', next)
}

function removeEntry(key: string) {
  const next = { ...props.modelValue }
  delete next[key]
  emit('update:modelValue', next)
}

function updateKey(index: number, newKey: string) {
  const oldKey = keys.value[index]
  if (newKey === oldKey) return
  const entries = Object.entries(props.modelValue)
  const next: Record<string, string> = {}
  for (const [k, v] of entries) {
    next[k === oldKey ? newKey : k] = v
  }
  emit('update:modelValue', next)
}

function updateValue(key: string, val: string) {
  emit('update:modelValue', { ...props.modelValue, [key]: val })
}
</script>

<style scoped>
.kv-editor {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.kv-row {
  display: flex;
  gap: 4px;
  align-items: center;
}
.kv-input {
  flex: 1;
  padding: 4px 8px;
  font-size: 12px;
  font-family: var(--font-primary);
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
}
.kv-input:focus {
  border-color: var(--accent-primary);
  outline: none;
}
.kv-remove {
  font-size: 10px;
  padding: 2px 6px;
  color: var(--status-error);
}
</style>
