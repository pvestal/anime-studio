<template>
  <div>
    <!-- Sub-tab toggle -->
    <div style="display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border-primary);">
      <button
        class="produce-subtab"
        :class="{ active: subtab === 'status' }"
        @click="subtab = 'status'"
      >
        Status
      </button>
      <button
        class="produce-subtab"
        :class="{ active: subtab === 'training' }"
        @click="subtab = 'training'"
      >
        Training
      </button>
      <button
        class="produce-subtab"
        :class="{ active: subtab === 'analytics' }"
        @click="subtab = 'analytics'"
      >
        Analytics
      </button>
    </div>

    <ProductionStatusTab v-if="subtab === 'status'" />
    <TrainingTab v-if="subtab === 'training'" />
    <AnalyticsTab v-if="subtab === 'analytics'" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ProductionStatusTab from './ProductionStatusTab.vue'
import AnalyticsTab from './AnalyticsTab.vue'
import TrainingTab from './TrainingTab.vue'

const subtab = ref<'status' | 'training' | 'analytics'>('status')
</script>

<style scoped>
.produce-subtab {
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
.produce-subtab:hover {
  color: var(--accent-primary);
}
.produce-subtab.active {
  border-bottom-color: var(--accent-primary);
  color: var(--accent-primary);
  font-weight: 500;
}
</style>
