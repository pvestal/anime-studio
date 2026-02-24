<template>
  <div>
    <h2 style="font-size: 18px; font-weight: 500; margin-bottom: 8px;">Voice Pipeline</h2>
    <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 24px;">
      Give each character their own voice: extract audio from reference clips, identify who's speaking,
      review samples, train voice clones, and test synthesis.
    </p>

    <!-- Project selector -->
    <div style="display: flex; gap: 16px; margin-bottom: 24px; align-items: flex-end;">
      <div style="min-width: 260px;">
        <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">
          Project
        </label>
        <select v-model="selectedProjectId" style="width: 100%; padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 6px; color: var(--text-primary); font-size: 14px;">
          <option :value="0">Select a project...</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">
            {{ p.name }}
          </option>
        </select>
      </div>
    </div>

    <!-- Sub-view navigation -->
    <div v-if="selectedProjectId" style="display: flex; gap: 0; border-bottom: 1px solid var(--border-primary); margin-bottom: 24px;">
      <button
        v-for="view in subViews"
        :key="view.id"
        @click="currentView = view.id"
        :style="{
          padding: '10px 20px',
          background: 'transparent',
          border: 'none',
          borderBottom: currentView === view.id ? '2px solid var(--accent-primary)' : '2px solid transparent',
          color: currentView === view.id ? 'var(--accent-primary)' : 'var(--text-secondary)',
          cursor: 'pointer',
          fontSize: '13px',
          fontWeight: currentView === view.id ? '500' : '400',
        }"
      >
        {{ view.label }}
      </button>
    </div>

    <!-- Sub-views -->
    <div v-if="selectedProjectId">
      <VoiceIngestView
        v-if="currentView === 'ingest'"
        :project-name="selectedProjectName"
        @diarized="onDiarized"
      />
      <SpeakerClusterView
        v-if="currentView === 'speakers'"
        :project-name="selectedProjectName"
        :characters="projectCharacters"
        @assigned="onSpeakerAssigned"
      />
      <VoiceReviewView
        v-if="currentView === 'review'"
        :project-name="selectedProjectName"
        :characters="projectCharacters"
      />
      <VoiceTrainView
        v-if="currentView === 'train'"
        :project-name="selectedProjectName"
        :characters="projectCharacters"
      />
      <VoiceSynthesizeView
        v-if="currentView === 'synthesize'"
        :project-name="selectedProjectName"
        :characters="projectCharacters"
      />
    </div>

    <div v-else style="text-align: center; padding: 60px 0; color: var(--text-muted);">
      Select a project to manage character voices.
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useCharactersStore } from '@/stores/characters'
import { storyApi } from '@/api/story'
import VoiceIngestView from '@/components/voice/VoiceIngestView.vue'
import SpeakerClusterView from '@/components/voice/SpeakerClusterView.vue'
import VoiceReviewView from '@/components/voice/VoiceReviewView.vue'
import VoiceTrainView from '@/components/voice/VoiceTrainView.vue'
import VoiceSynthesizeView from '@/components/voice/VoiceSynthesizeView.vue'

interface ProjectInfo {
  id: number
  name: string
}

const charactersStore = useCharactersStore()
const selectedProjectId = ref(0)
const currentView = ref<'ingest' | 'speakers' | 'review' | 'train' | 'synthesize'>('ingest')
const projects = ref<ProjectInfo[]>([])

const subViews = [
  { id: 'ingest' as const, label: 'Ingest' },
  { id: 'speakers' as const, label: 'Speakers' },
  { id: 'review' as const, label: 'Review' },
  { id: 'train' as const, label: 'Train' },
  { id: 'synthesize' as const, label: 'Synthesize' },
]

const selectedProjectName = computed(() => {
  const p = projects.value.find(p => p.id === selectedProjectId.value)
  return p?.name || ''
})

const projectCharacters = computed(() => {
  if (!selectedProjectName.value) return []
  return charactersStore.characters.filter(c => c.project_name === selectedProjectName.value)
})

// Load projects
;(async () => {
  try {
    const resp = await storyApi.getProjects()
    projects.value = (resp.projects || resp).map((p: any) => ({ id: p.id, name: p.name }))
  } catch {
    // fallback: derive from characters
    const names = new Set(charactersStore.characters.map(c => c.project_name))
    projects.value = [...names].map((n, i) => ({ id: i + 1, name: n }))
  }
})()

function onDiarized() {
  currentView.value = 'speakers'
}

function onSpeakerAssigned() {
  currentView.value = 'review'
}
</script>
