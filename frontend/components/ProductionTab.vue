<template>
  <div>
    <!-- Sub-tab toggle -->
    <div style="display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border-primary);">
      <button
        class="prod-subtab"
        :class="{ active: subtab === 'training' }"
        @click="subtab = 'training'"
      >
        Training
      </button>
      <button
        class="prod-subtab"
        :class="{ active: subtab === 'scenes' }"
        @click="subtab = 'scenes'"
      >
        Scenes & Episodes
      </button>
    </div>

    <TrainingTab v-if="subtab === 'training'" />
    <SceneBuilderTab v-if="subtab === 'scenes'" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import TrainingTab from './TrainingTab.vue'
import SceneBuilderTab from './SceneBuilderTab.vue'

const subtab = ref<'training' | 'scenes'>('training')
</script>

<style scoped>
.prod-subtab {
  padding: 10px 20px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  font-family: var(--font-primary);
  transition: all 150ms ease;
}
.prod-subtab:hover {
  color: var(--accent-primary);
}
.prod-subtab.active {
  border-bottom-color: var(--accent-primary);
  color: var(--accent-primary);
  font-weight: 500;
}
</style>
