<template>
  <div class="play-choices" :class="{ visible: show }">
    <button
      v-for="(choice, i) in choices"
      :key="i"
      class="choice-btn"
      :class="[`tone-${choice.tone}`, { selected: selectedIndex === i }]"
      :disabled="disabled"
      @click="$emit('choose', i)"
    >
      <span class="choice-marker">{{ i + 1 }}</span>
      <span class="choice-text">{{ choice.text }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import type { InteractiveChoice } from '@/api/interactive'

defineProps<{
  choices: InteractiveChoice[]
  show: boolean
  disabled: boolean
  selectedIndex?: number
}>()

defineEmits<{
  choose: [index: number]
}>()
</script>

<style scoped>
.play-choices {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px 24px;
  opacity: 0;
  transform: translateY(12px);
  transition: opacity 0.5s ease, transform 0.5s ease;
}

.play-choices.visible {
  opacity: 1;
  transform: translateY(0);
}

.choice-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(8px);
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: left;
  font-family: var(--font-primary);
}

.choice-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.3);
  transform: translateX(4px);
}

.choice-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.choice-btn.selected {
  border-color: var(--accent-primary);
  background: rgba(99, 102, 241, 0.2);
}

.choice-marker {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
}

/* Tone-specific styling */
.tone-bold .choice-marker { background: rgba(220, 50, 50, 0.3); color: #f07070; }
.tone-bold { border-color: rgba(220, 50, 50, 0.25); }

.tone-cautious .choice-marker { background: rgba(60, 130, 220, 0.3); color: #70a0f0; }
.tone-cautious { border-color: rgba(60, 130, 220, 0.25); }

.tone-romantic .choice-marker { background: rgba(220, 80, 150, 0.3); color: #f080b0; }
.tone-romantic { border-color: rgba(220, 80, 150, 0.25); }

.tone-dramatic .choice-marker { background: rgba(180, 80, 220, 0.3); color: #c080f0; }
.tone-dramatic { border-color: rgba(180, 80, 220, 0.25); }

.tone-humorous .choice-marker { background: rgba(220, 180, 40, 0.3); color: #e0c050; }
.tone-humorous { border-color: rgba(220, 180, 40, 0.25); }

.tone-neutral .choice-marker { background: rgba(255, 255, 255, 0.1); color: var(--text-secondary); }

.choice-text {
  flex: 1;
}
</style>
