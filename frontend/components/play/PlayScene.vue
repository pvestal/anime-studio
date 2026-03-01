<template>
  <div class="play-scene" @click="handleSceneClick">
    <!-- Background image -->
    <div class="scene-bg" :class="{ loaded: imageLoaded }">
      <img
        v-if="imageUrl"
        :src="imageUrl"
        alt=""
        class="scene-image"
        @load="imageLoaded = true"
      />
      <div v-else class="scene-loading">
        <div class="loading-shimmer" />
        <p class="loading-text">
          {{ loadingMessage }}
        </p>
        <div v-if="imageProgress > 0" class="progress-bar">
          <div class="progress-fill" :style="{ width: (imageProgress * 100) + '%' }" />
        </div>
      </div>
    </div>

    <!-- Dark gradient overlay -->
    <div class="scene-overlay" />

    <!-- Scene number -->
    <div class="scene-number">Scene {{ sceneIndex + 1 }}</div>

    <!-- Content overlay -->
    <div class="scene-content">
      <PlayDialogue
        ref="dialogueRef"
        :narration="scene.narration"
        :dialogue="scene.dialogue"
        @done="dialogueDone = true"
      />

      <PlayChoices
        v-if="!scene.is_ending"
        :choices="scene.choices"
        :show="dialogueDone"
        :disabled="choosing"
        @choose="$emit('choose', $event)"
      />
    </div>

    <!-- Quit button -->
    <button class="quit-btn" @click.stop="$emit('quit')" title="Exit game">
      &times;
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import type { InteractiveScene, InteractiveImageStatus } from '@/api/interactive'
import PlayDialogue from './PlayDialogue.vue'
import PlayChoices from './PlayChoices.vue'

const props = defineProps<{
  scene: InteractiveScene
  image: InteractiveImageStatus
  choosing: boolean
}>()

defineEmits<{
  choose: [index: number]
  quit: []
}>()

const dialogueRef = ref<InstanceType<typeof PlayDialogue> | null>(null)
const dialogueDone = ref(false)
const imageLoaded = ref(false)

const sceneIndex = computed(() => props.scene.scene_index)

const imageUrl = computed(() => {
  if (props.image.status === 'ready' && props.image.url) {
    return props.image.url
  }
  return null
})

const imageProgress = computed(() => props.image.progress || 0)

const loadingMessage = computed(() => {
  switch (props.image.status) {
    case 'pending': return 'The story unfolds...'
    case 'generating': return 'Painting the scene...'
    case 'failed': return 'The scene remains in shadow...'
    default: return 'The story unfolds...'
  }
})

// Reset when scene changes
watch(() => props.scene.scene_index, () => {
  dialogueDone.value = false
  imageLoaded.value = false
})

function handleSceneClick() {
  if (!dialogueDone.value) {
    dialogueRef.value?.skipToEnd()
  }
}
</script>

<style scoped>
.play-scene {
  position: fixed;
  inset: 0;
  background: #0a0a0f;
  z-index: 50;
  cursor: default;
  overflow: hidden;
}

.scene-bg {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 1s ease;
}

.scene-bg.loaded {
  opacity: 1;
}

.scene-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.scene-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.loading-shimmer {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    -45deg,
    #0a0a1a 25%,
    #12122a 50%,
    #0a0a1a 75%
  );
  background-size: 400% 400%;
  animation: shimmer 3s ease infinite;
}

@keyframes shimmer {
  0% { background-position: 100% 50%; }
  50% { background-position: 0% 50%; }
  100% { background-position: 100% 50%; }
}

.loading-text {
  position: relative;
  z-index: 1;
  color: rgba(255, 255, 255, 0.5);
  font-size: 16px;
  font-style: italic;
}

.progress-bar {
  position: relative;
  z-index: 1;
  width: 200px;
  height: 3px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent-primary);
  transition: width 0.5s ease;
}

.scene-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to top,
    rgba(0, 0, 0, 0.9) 0%,
    rgba(0, 0, 0, 0.5) 35%,
    rgba(0, 0, 0, 0.1) 60%,
    transparent 100%
  );
  pointer-events: none;
}

.scene-number {
  position: absolute;
  top: 16px;
  left: 16px;
  padding: 4px 12px;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(8px);
  border-radius: 20px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
  z-index: 2;
}

.scene-content {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  max-height: 60vh;
  overflow-y: auto;
  z-index: 2;
}

.quit-btn {
  position: absolute;
  top: 12px;
  right: 16px;
  width: 36px;
  height: 36px;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 50%;
  color: rgba(255, 255, 255, 0.7);
  font-size: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3;
  transition: all 0.2s;
}

.quit-btn:hover {
  background: rgba(220, 50, 50, 0.3);
  border-color: rgba(220, 50, 50, 0.5);
  color: #fff;
}
</style>
