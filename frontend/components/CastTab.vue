<template>
  <div>
    <!-- Sub-tab toggle -->
    <div style="display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border-primary);">
      <button
        class="cast-subtab"
        :class="{ active: subtab === 'characters' }"
        @click="subtab = 'characters'"
      >
        Characters
      </button>
      <button
        class="cast-subtab"
        :class="{ active: subtab === 'ingest' }"
        @click="subtab = 'ingest'"
      >
        Ingest
      </button>
      <button
        class="cast-subtab"
        :class="{ active: subtab === 'voice' }"
        @click="subtab = 'voice'"
      >
        Voice
      </button>
    </div>

    <CharactersTab v-if="subtab === 'characters'" :hide-sub-tabs="true" initial-sub-tab="characters" />
    <CharactersTab v-if="subtab === 'ingest'" :hide-sub-tabs="true" initial-sub-tab="ingest" />
    <VoiceTab v-if="subtab === 'voice'" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import CharactersTab from './CharactersTab.vue'
import VoiceTab from './VoiceTab.vue'

const subtab = ref<'characters' | 'ingest' | 'voice'>('characters')
</script>

<style scoped>
.cast-subtab {
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
.cast-subtab:hover {
  color: var(--accent-primary);
}
.cast-subtab.active {
  border-bottom-color: var(--accent-primary);
  color: var(--accent-primary);
  font-weight: 500;
}
</style>
