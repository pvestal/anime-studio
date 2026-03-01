<template>
  <div class="ending-overlay" @click.self="$emit('close')">
    <div class="ending-card">
      <div class="ending-type" :class="`ending-${endingType || 'neutral'}`">
        {{ endingLabel }}
      </div>

      <h2 class="ending-title">Story Complete</h2>

      <p v-if="lastScene?.narration" class="ending-narration">
        {{ lastScene.narration }}
      </p>

      <div class="stats-grid">
        <div class="stat">
          <span class="stat-value">{{ sceneCount }}</span>
          <span class="stat-label">Scenes</span>
        </div>
        <div class="stat">
          <span class="stat-value">{{ choiceCount }}</span>
          <span class="stat-label">Choices Made</span>
        </div>
      </div>

      <div v-if="Object.keys(relationships).length > 0" class="relationships">
        <h3>Relationships</h3>
        <div v-for="(val, name) in relationships" :key="name" class="rel-row">
          <span class="rel-name">{{ name }}</span>
          <div class="rel-bar-track">
            <div
              class="rel-bar-fill"
              :class="{ negative: (val as number) < 0 }"
              :style="{ width: Math.min(Math.abs(val as number) * 5, 100) + '%' }"
            />
          </div>
          <span class="rel-value" :class="{ negative: (val as number) < 0 }">
            {{ (val as number) > 0 ? '+' : '' }}{{ val }}
          </span>
        </div>
      </div>

      <div class="ending-actions">
        <button class="btn-primary" @click="$emit('new-game')">Play Again</button>
        <button class="btn-secondary" @click="$emit('close')">Return to Launcher</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { InteractiveScene } from '@/api/interactive'

const props = defineProps<{
  lastScene: InteractiveScene | null
  sceneCount: number
  relationships: Record<string, number>
  scenes: InteractiveScene[]
}>()

defineEmits<{
  close: []
  'new-game': []
}>()

const endingType = computed(() => props.lastScene?.ending_type || 'neutral')
const endingLabel = computed(() => {
  switch (endingType.value) {
    case 'good': return 'Good Ending'
    case 'bad': return 'Bad Ending'
    case 'secret': return 'Secret Ending'
    default: return 'Ending'
  }
})
const choiceCount = computed(() =>
  props.scenes.filter(s => s.chosen_text).length
)
</script>

<style scoped>
.ending-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  animation: fadeIn 0.5s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.ending-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 16px;
  padding: 40px;
  max-width: 500px;
  width: 90%;
  text-align: center;
}

.ending-type {
  display: inline-block;
  padding: 4px 16px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 16px;
}

.ending-good { background: rgba(50, 180, 80, 0.2); color: #50d070; }
.ending-bad { background: rgba(220, 50, 50, 0.2); color: #f07070; }
.ending-secret { background: rgba(180, 80, 220, 0.2); color: #c080f0; }
.ending-neutral { background: rgba(255, 255, 255, 0.1); color: var(--text-secondary); }

.ending-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 16px;
}

.ending-narration {
  font-style: italic;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 24px;
}

.stats-grid {
  display: flex;
  justify-content: center;
  gap: 32px;
  margin-bottom: 24px;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--accent-primary);
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.relationships {
  text-align: left;
  margin-bottom: 24px;
}

.relationships h3 {
  font-size: 14px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 12px;
}

.rel-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.rel-name {
  width: 100px;
  font-size: 14px;
  color: var(--text-primary);
}

.rel-bar-track {
  flex: 1;
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  overflow: hidden;
}

.rel-bar-fill {
  height: 100%;
  background: var(--accent-primary);
  border-radius: 3px;
  transition: width 0.5s ease;
}

.rel-bar-fill.negative {
  background: #e05050;
}

.rel-value {
  width: 40px;
  text-align: right;
  font-size: 14px;
  font-weight: 600;
  color: var(--accent-primary);
}

.rel-value.negative {
  color: #e05050;
}

.ending-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.btn-primary, .btn-secondary {
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  font-family: var(--font-primary);
  transition: opacity 0.2s;
}

.btn-primary {
  background: var(--accent-primary);
  color: #fff;
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
}

.btn-primary:hover, .btn-secondary:hover {
  opacity: 0.85;
}
</style>
