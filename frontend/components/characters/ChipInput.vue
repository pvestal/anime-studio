<template>
  <div class="chip-input">
    <div class="chips">
      <span v-for="(chip, i) in modelValue" :key="i" class="chip">
        {{ chip }}
        <button class="chip-remove" @click="remove(i)">&times;</button>
      </span>
      <input
        ref="inputEl"
        v-model="inputText"
        class="chip-text-input"
        :placeholder="modelValue.length ? '' : placeholder"
        @keydown.enter.prevent="add"
        @keydown.comma.prevent="add"
        @keydown.backspace="onBackspace"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string[]
  placeholder?: string
}>(), {
  placeholder: 'Add...',
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const inputText = ref('')
const inputEl = ref<HTMLInputElement>() // eslint-disable-line @typescript-eslint/no-unused-vars -- template ref

function add() {
  const val = inputText.value.trim()
  if (val && !props.modelValue.includes(val)) {
    emit('update:modelValue', [...props.modelValue, val])
  }
  inputText.value = ''
}

function remove(index: number) {
  const next = [...props.modelValue]
  next.splice(index, 1)
  emit('update:modelValue', next)
}

function onBackspace() {
  if (!inputText.value && props.modelValue.length) {
    remove(props.modelValue.length - 1)
  }
}
</script>

<style scoped>
.chip-input {
  border: 1px solid var(--border-primary);
  border-radius: 3px;
  background: var(--bg-primary);
  padding: 3px 4px;
  min-height: 28px;
}
.chip-input:focus-within {
  border-color: var(--accent-primary);
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  font-size: 11px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 10px;
  color: var(--text-primary);
}
.chip-remove {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  padding: 0;
  line-height: 1;
}
.chip-remove:hover {
  color: var(--status-error);
}
.chip-text-input {
  flex: 1;
  min-width: 60px;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 12px;
  font-family: var(--font-primary);
  outline: none;
  padding: 2px 4px;
}
</style>
