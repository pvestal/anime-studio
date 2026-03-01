<template>
  <div class="pill-select">
    <input
      v-model="inputValue"
      class="pill-input"
      :placeholder="placeholder"
    />
    <div v-if="options.length" class="pill-row">
      <button
        v-for="opt in options"
        :key="opt"
        type="button"
        class="pill"
        :class="{ 'pill-active': modelValue === opt }"
        @click="toggle(opt)"
      >{{ opt }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  modelValue?: string
  options: string[]
  placeholder?: string
}>(), {
  modelValue: '',
  placeholder: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const inputValue = computed({
  get: () => props.modelValue || '',
  set: (v: string) => emit('update:modelValue', v),
})

function toggle(opt: string) {
  const next = props.modelValue === opt ? '' : opt
  emit('update:modelValue', next)
}
</script>

<style scoped>
.pill-select {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pill-input {
  width: 100%;
  padding: 5px 8px;
  font-size: 12px;
  font-family: var(--font-primary);
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
}
.pill-input:focus {
  border-color: var(--accent-primary);
  outline: none;
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
</style>
