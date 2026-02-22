<template>
  <div>
    <div v-if="!hasProject" style="color: var(--text-muted); font-size: 13px;">
      Select a project to view scenes.
    </div>

    <!-- Generate from story button -->
    <div v-if="hasProject && scenes.length === 0 && !loading" style="margin-bottom: 16px;">
      <button
        class="btn btn-primary"
        style="font-size: 12px; padding: 6px 14px;"
        :disabled="generatingFromStory"
        @click="$emit('generate-from-story')"
      >
        {{ generatingFromStory ? 'Generating...' : 'Generate Scenes from Story' }}
      </button>
      <span style="font-size: 11px; color: var(--text-muted); margin-left: 8px;">
        Uses AI to break your storyline into production-ready scenes
      </span>
    </div>
    <div v-else-if="loading" style="color: var(--text-muted); font-size: 13px;">Loading scenes...</div>
    <div v-else-if="scenes.length === 0" style="color: var(--text-muted); font-size: 13px;">
      No scenes yet. Click "+ New Scene" to create one.
    </div>
    <div v-else style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px;">
      <div
        v-for="scene in scenes"
        :key="scene.id"
        class="card"
        style="cursor: pointer;"
        @click="$emit('edit', scene)"
      >
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
          <div style="font-size: 14px; font-weight: 500;">{{ scene.title }}</div>
          <span :class="statusBadgeClass(scene.generation_status)" style="font-size: 11px; padding: 2px 8px; border-radius: 3px;">
            {{ scene.generation_status }}
          </span>
        </div>
        <div v-if="scene.description" style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px; max-height: 40px; overflow: hidden;">
          {{ scene.description }}
        </div>
        <!-- Training readiness -->
        <div v-if="gapBySceneId?.[scene.id]" style="display: flex; align-items: center; gap: 6px; margin-bottom: 8px; flex-wrap: wrap;">
          <span
            :class="gapBySceneId[scene.id].production_ready ? 'readiness-ready' : 'readiness-not-ready'"
            style="font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 3px; text-transform: uppercase;"
          >{{ gapBySceneId[scene.id].production_ready ? 'Ready' : 'Not Ready' }}</span>
          <span
            v-for="ch in gapBySceneId[scene.id].characters"
            :key="ch.slug"
            :class="ch.has_lora ? 'char-pill-ready' : 'char-pill-unready'"
            style="font-size: 10px; padding: 1px 6px; border-radius: 10px;"
          >{{ ch.name }}</span>
        </div>
        <div style="display: flex; gap: 12px; font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
          <span v-if="scene.location">{{ scene.location }}</span>
          <span>{{ scene.total_shots }} shot{{ scene.total_shots !== 1 ? 's' : '' }}</span>
          <span v-if="scene.actual_duration_seconds">{{ scene.actual_duration_seconds.toFixed(1) }}s</span>
          <span v-else-if="scene.target_duration_seconds">~{{ scene.target_duration_seconds }}s target</span>
        </div>
        <div style="display: flex; gap: 8px;">
          <button class="btn" style="font-size: 12px; padding: 4px 12px;" @click.stop="$emit('edit', scene)">Edit</button>
          <button
            v-if="scene.generation_status === 'generating'"
            class="btn btn-primary" style="font-size: 12px; padding: 4px 12px;"
            @click.stop="$emit('monitor', scene)"
          >Monitor</button>
          <button
            v-if="scene.final_video_path"
            class="btn btn-success" style="font-size: 12px; padding: 4px 12px;"
            @click.stop="$emit('play', scene)"
          >Play</button>
          <button
            class="btn btn-danger" style="font-size: 12px; padding: 4px 12px;"
            @click.stop="$emit('delete', scene)"
          >Delete</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { BuilderScene, GapAnalysisScene } from '@/types'

defineProps<{
  scenes: BuilderScene[]
  loading: boolean
  hasProject: boolean
  generatingFromStory?: boolean
  gapBySceneId?: Record<string, GapAnalysisScene>
}>()

defineEmits<{
  edit: [scene: BuilderScene]
  monitor: [scene: BuilderScene]
  play: [scene: BuilderScene]
  delete: [scene: BuilderScene]
  'generate-from-story': []
}>()

function statusBadgeClass(status: string): string {
  const map: Record<string, string> = {
    draft: 'badge-draft',
    pending: 'badge-draft',
    generating: 'badge-generating',
    completed: 'badge-completed',
    partial: 'badge-partial',
    failed: 'badge-failed',
  }
  return map[status] || 'badge-draft'
}
</script>

<style scoped>
.badge-draft {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}
.badge-generating {
  background: rgba(122, 162, 247, 0.2);
  color: var(--accent-primary);
}
.badge-completed {
  background: rgba(80, 160, 80, 0.2);
  color: var(--status-success);
}
.badge-partial {
  background: rgba(160, 128, 80, 0.2);
  color: var(--status-warning);
}
.badge-failed {
  background: rgba(160, 80, 80, 0.2);
  color: var(--status-error);
}
.readiness-ready {
  background: rgba(80, 160, 80, 0.2);
  color: var(--status-success);
}
.readiness-not-ready {
  background: rgba(160, 80, 80, 0.2);
  color: var(--status-error);
}
.char-pill-ready {
  background: rgba(80, 160, 80, 0.15);
  color: var(--status-success);
}
.char-pill-unready {
  background: transparent;
  outline: 1px solid var(--status-error);
  color: var(--status-error);
}
</style>
