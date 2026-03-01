<template>
  <div class="play-tab">
    <!-- Error banner -->
    <div v-if="store.error" class="error-banner">
      {{ store.error }}
      <button @click="store.error = null" class="error-dismiss">&times;</button>
    </div>

    <!-- Game active: show fullscreen scene -->
    <PlayScene
      v-if="store.currentScene && !store.isEnded"
      :scene="store.currentScene"
      :image="store.imageStatus"
      :choosing="store.choosing"
      @choose="store.submitChoice($event)"
      @quit="confirmQuit"
    />

    <!-- Ending screen -->
    <PlayEndingScreen
      v-else-if="store.isEnded && store.currentScene"
      :last-scene="store.currentScene"
      :scene-count="store.sceneCount"
      :relationships="store.relationships"
      :scenes="store.sceneHistory"
      @close="store.endSession()"
      @new-game="store.resetState()"
    />

    <!-- Launcher: no active game -->
    <PlayLauncher
      v-else
      :starting="store.loading"
      :active-sessions="store.activeSessions"
      @start="handleStart"
      @resume="handleResume"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useInteractiveStore } from '@/stores/interactive'
import PlayLauncher from './play/PlayLauncher.vue'
import PlayScene from './play/PlayScene.vue'
import PlayEndingScreen from './play/PlayEndingScreen.vue'

const store = useInteractiveStore()

onMounted(() => {
  store.fetchActiveSessions()
})

async function handleStart(projectId: number) {
  await store.startSession(projectId)
}

async function handleResume(sessionId: string) {
  await store.resumeSession(sessionId)
}

function confirmQuit() {
  if (window.confirm('End this session? Your progress will be lost.')) {
    store.endSession()
  }
}
</script>

<style scoped>
.play-tab {
  position: relative;
}

.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: rgba(220, 50, 50, 0.15);
  border: 1px solid rgba(220, 50, 50, 0.3);
  border-radius: 8px;
  color: #f07070;
  font-size: 14px;
  margin-bottom: 16px;
}

.error-dismiss {
  background: none;
  border: none;
  color: #f07070;
  font-size: 18px;
  cursor: pointer;
  padding: 0 4px;
}
</style>
