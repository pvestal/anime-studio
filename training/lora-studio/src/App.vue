<template>
  <div id="app" style="min-height: 100vh; background: var(--bg-primary); color: var(--text-primary);">
    <header style="background: var(--bg-secondary); border-bottom: 1px solid var(--border-primary); padding: 16px 24px;">
      <div style="max-width: 1400px; margin: 0 auto;">
        <h1 style="font-size: 20px; font-weight: 500; color: var(--text-primary);">LoRA Studio</h1>
        <p style="font-size: 13px; color: var(--text-muted);">Anime production: ingest, approve, train, generate</p>
      </div>
    </header>

    <nav style="background: var(--bg-secondary); border-bottom: 1px solid var(--border-primary);">
      <div style="max-width: 1400px; margin: 0 auto; padding: 0 24px; display: flex; gap: 0;">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          :style="{
            padding: '12px 16px',
            border: 'none',
            borderBottom: activeTab === tab.id ? '2px solid var(--accent-primary)' : '2px solid transparent',
            background: 'transparent',
            color: activeTab === tab.id ? 'var(--accent-primary)' : 'var(--text-secondary)',
            cursor: 'pointer',
            fontSize: '14px',
            fontFamily: 'var(--font-primary)',
            transition: 'color 150ms ease',
          }"
        >
          {{ tab.label }}
          <span v-if="tab.count !== undefined" style="margin-left: 6px; font-size: 12px; color: var(--text-muted);">
            ({{ tab.count }})
          </span>
        </button>
      </div>
    </nav>

    <main style="max-width: 1400px; margin: 0 auto; padding: 24px;">
      <component :is="currentComponent" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { TabType } from '@/types'
import { useApprovalStore } from '@/stores/approval'
import { useCharactersStore } from '@/stores/characters'
import CharactersTab from '@/components/CharactersTab.vue'
import PendingTab from '@/components/PendingTab.vue'
import TrainingTab from '@/components/TrainingTab.vue'
import IngestTab from '@/components/IngestTab.vue'
import GenerateTab from '@/components/GenerateTab.vue'
import GalleryTab from '@/components/GalleryTab.vue'
import EchoTab from '@/components/EchoTab.vue'

const approvalStore = useApprovalStore()
const charactersStore = useCharactersStore()
const activeTab = ref<TabType>('characters')

// Fetch data at app level so tab counts are always available
onMounted(() => {
  approvalStore.fetchPendingImages()
  charactersStore.fetchCharacters()
})

const componentMap = {
  characters: CharactersTab,
  pending: PendingTab,
  training: TrainingTab,
  ingest: IngestTab,
  generate: GenerateTab,
  gallery: GalleryTab,
  echo: EchoTab,
} as const

const currentComponent = computed(() => componentMap[activeTab.value])

const tabs = computed(() => [
  { id: 'ingest' as TabType, label: '1. Ingest' },
  { id: 'pending' as TabType, label: '2. Approve', count: approvalStore.pendingImages.length },
  { id: 'characters' as TabType, label: '3. Characters' },
  { id: 'training' as TabType, label: '4. Train' },
  { id: 'generate' as TabType, label: '5. Generate' },
  { id: 'gallery' as TabType, label: '6. Gallery' },
  { id: 'echo' as TabType, label: '7. Echo Brain' },
])
</script>
