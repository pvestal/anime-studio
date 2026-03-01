<template>
  <div class="play-dialogue">
    <div v-if="narration" class="narration" :class="{ revealed: narrationRevealed }">
      <span class="narration-text">{{ displayedNarration }}</span>
      <span v-if="!narrationRevealed" class="typing-cursor">|</span>
    </div>

    <div v-for="(line, i) in dialogue" :key="i" class="dialogue-line" :class="{ visible: i <= currentDialogueIndex }">
      <span class="character-name" :class="`emotion-${line.emotion}`">{{ line.character }}</span>
      <span class="dialogue-text">"{{ line.text }}"</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import type { InteractiveDialogue } from '@/api/interactive'

const props = defineProps<{
  narration: string
  dialogue: InteractiveDialogue[]
}>()

const emit = defineEmits<{
  done: []
}>()

const displayedNarration = ref('')
const narrationRevealed = ref(false)
const currentDialogueIndex = ref(-1)
let typeTimer: ReturnType<typeof setTimeout> | null = null
let charIndex = 0

function startTypewriter() {
  // Reset
  displayedNarration.value = ''
  narrationRevealed.value = false
  currentDialogueIndex.value = -1
  charIndex = 0

  typeNextChar()
}

function typeNextChar() {
  if (charIndex < props.narration.length) {
    displayedNarration.value = props.narration.slice(0, charIndex + 1)
    charIndex++
    typeTimer = setTimeout(typeNextChar, 25)
  } else {
    narrationRevealed.value = true
    // Reveal dialogue lines one at a time
    revealDialogue(0)
  }
}

function revealDialogue(idx: number) {
  if (idx < props.dialogue.length) {
    currentDialogueIndex.value = idx
    typeTimer = setTimeout(() => revealDialogue(idx + 1), 800)
  } else {
    emit('done')
  }
}

function skipToEnd() {
  if (typeTimer) clearTimeout(typeTimer)
  typeTimer = null
  displayedNarration.value = props.narration
  narrationRevealed.value = true
  currentDialogueIndex.value = props.dialogue.length - 1
  emit('done')
}

// Expose skip method for parent
defineExpose({ skipToEnd })

watch(() => props.narration, () => {
  if (typeTimer) clearTimeout(typeTimer)
  startTypewriter()
}, { immediate: true })

onUnmounted(() => {
  if (typeTimer) clearTimeout(typeTimer)
})
</script>

<style scoped>
.play-dialogue {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.narration {
  font-size: 16px;
  line-height: 1.6;
  color: var(--text-primary);
  font-style: italic;
}

.typing-cursor {
  animation: blink 0.7s step-end infinite;
  color: var(--accent-primary);
}

@keyframes blink {
  50% { opacity: 0; }
}

.dialogue-line {
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 0.4s ease, transform 0.4s ease;
  font-size: 15px;
  line-height: 1.5;
}

.dialogue-line.visible {
  opacity: 1;
  transform: translateY(0);
}

.character-name {
  font-weight: 600;
  margin-right: 8px;
}

.emotion-happy { color: #f0c040; }
.emotion-sad { color: #6090d0; }
.emotion-angry { color: #e05050; }
.emotion-surprised { color: #e0a030; }
.emotion-scared { color: #a070c0; }
.emotion-romantic { color: #e070a0; }
.emotion-neutral { color: var(--accent-primary); }

.dialogue-text {
  color: var(--text-secondary);
}
</style>
