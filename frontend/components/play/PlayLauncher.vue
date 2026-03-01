<template>
  <div class="play-launcher">
    <div class="launcher-header">
      <h2>Interactive Visual Novel</h2>
      <p class="launcher-desc">
        Choose a project and step into an AI-driven branching narrative.
        Every playthrough is unique — your choices shape the story.
      </p>
    </div>

    <!-- Active Sessions -->
    <div v-if="activeSessions.length > 0" class="section">
      <h3>Active Sessions</h3>
      <div class="session-list">
        <div
          v-for="s in activeSessions"
          :key="s.session_id"
          class="session-card"
          @click="$emit('resume', s.session_id)"
        >
          <div class="session-info">
            <span class="session-project">{{ s.project_name }}</span>
            <span class="session-progress">Scene {{ s.scene_count }}</span>
          </div>
          <button
            class="session-delete"
            @click.stop="deleteSession(s.session_id)"
            title="End session"
          >
            &times;
          </button>
        </div>
      </div>
    </div>

    <!-- New Game -->
    <div class="section">
      <h3>New Game</h3>
      <div class="project-selector">
        <label class="field-label">Project</label>
        <select v-model="selectedProjectId" class="field-select">
          <option :value="0">Select a project...</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">
            {{ p.name }} ({{ p.character_count }} characters)
          </option>
        </select>
      </div>

      <button
        class="start-btn"
        :disabled="!selectedProjectId || starting"
        @click="$emit('start', selectedProjectId)"
      >
        {{ starting ? 'Starting...' : 'Begin Story' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { storyApi } from '@/api/story'
import { interactiveApi } from '@/api/interactive'
import type { InteractiveSession } from '@/api/interactive'

defineProps<{
  starting: boolean
  activeSessions: InteractiveSession[]
}>()

defineEmits<{
  start: [projectId: number]
  resume: [sessionId: string]
}>()

const selectedProjectId = ref(0)

interface ProjectInfo { id: number; name: string; character_count: number }
const projects = ref<ProjectInfo[]>([])

onMounted(async () => {
  try {
    const resp = await storyApi.getProjects()
    projects.value = (resp.projects || []).map((p: any) => ({
      id: p.id,
      name: p.name,
      character_count: p.character_count || 0,
    }))
  } catch (e) {
    console.error('Failed to load projects:', e)
  }
})

async function deleteSession(sessionId: string) {
  try {
    await interactiveApi.deleteSession(sessionId)
    // Parent will re-fetch
  } catch (e) {
    console.error('Failed to delete session:', e)
  }
}
</script>

<style scoped>
.play-launcher {
  max-width: 600px;
  margin: 0 auto;
}

.launcher-header {
  text-align: center;
  margin-bottom: 32px;
}

.launcher-header h2 {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.launcher-desc {
  color: var(--text-muted);
  font-size: 14px;
  line-height: 1.5;
}

.section {
  margin-bottom: 32px;
}

.section h3 {
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin: 0 0 12px;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.session-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.session-card:hover {
  border-color: var(--accent-primary);
}

.session-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.session-project {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.session-progress {
  font-size: 12px;
  color: var(--text-muted);
}

.session-delete {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 18px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: color 0.2s;
}

.session-delete:hover {
  color: #e05050;
}

.project-selector {
  margin-bottom: 16px;
}

.field-label {
  display: block;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.field-select {
  width: 100%;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: var(--font-primary);
}

.start-btn {
  width: 100%;
  padding: 14px;
  background: var(--accent-primary);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  font-family: var(--font-primary);
  transition: opacity 0.2s;
}

.start-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.start-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
