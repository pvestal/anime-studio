<template>
  <div>
    <!-- Sub-tab toggle -->
    <div style="display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border-primary);">
      <button
        class="script-subtab"
        :class="{ active: subtab === 'scenes' }"
        @click="subtab = 'scenes'"
      >
        Scenes
      </button>
      <button
        class="script-subtab"
        :class="{ active: subtab === 'screenplay' }"
        @click="subtab = 'screenplay'"
      >
        Screenplay
      </button>
    </div>

    <SceneBuilderTab v-if="subtab === 'scenes'" :hide-episodes="true" />
    <ScreenplayView v-if="subtab === 'screenplay'" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import SceneBuilderTab from './SceneBuilderTab.vue'
import ScreenplayView from './script/ScreenplayView.vue'

const subtab = ref<'scenes' | 'screenplay'>('scenes')
</script>

<style scoped>
.script-subtab {
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
.script-subtab:hover {
  color: var(--accent-primary);
}
.script-subtab.active {
  border-bottom-color: var(--accent-primary);
  color: var(--accent-primary);
  font-weight: 500;
}
</style>
