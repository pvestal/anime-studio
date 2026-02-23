<template>
  <div>
    <!-- Sub-tab toggle -->
    <div style="display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border-primary);">
      <button
        class="review-subtab"
        :class="{ active: subtab === 'pending' }"
        @click="subtab = 'pending'"
      >
        Pending Images
        <span v-if="pendingCount > 0" class="review-badge">{{ pendingCount }}</span>
      </button>
      <button
        class="review-subtab"
        :class="{ active: subtab === 'videos' }"
        @click="onVideosTab"
      >
        Pending Videos
        <span v-if="videoCount > 0" class="review-badge review-badge-video">{{ videoCount }}</span>
      </button>
      <button
        class="review-subtab"
        :class="{ active: subtab === 'library' }"
        @click="subtab = 'library'"
      >
        Library
      </button>
    </div>

    <!-- Pending Images sub-tab -->
    <PendingTab v-if="subtab === 'pending'" />

    <!-- Pending Videos sub-tab -->
    <PendingVideosTab v-if="subtab === 'videos'" />

    <!-- Library sub-tab -->
    <LibraryTab v-if="subtab === 'library'" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useApprovalStore } from '@/stores/approval'
import { useVideoReviewStore } from '@/stores/videoReview'
import PendingTab from './PendingTab.vue'
import PendingVideosTab from './PendingVideosTab.vue'
import LibraryTab from './LibraryTab.vue'

const approvalStore = useApprovalStore()
const videoReviewStore = useVideoReviewStore()
const subtab = ref<'pending' | 'videos' | 'library'>('pending')
const pendingCount = computed(() => approvalStore.pendingImages.length)
const videoCount = computed(() => videoReviewStore.pendingCount)

function onVideosTab() {
  subtab.value = 'videos'
  // Fetch if not already loaded
  if (videoReviewStore.pendingVideos.length === 0 && !videoReviewStore.loading) {
    videoReviewStore.fetchPendingVideos()
    videoReviewStore.fetchEngineStats()
  }
}

onMounted(() => {
  // Prefetch video count for the badge
  videoReviewStore.fetchPendingVideos()
})
</script>

<style scoped>
.review-subtab {
  padding: 10px 20px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
  font-family: var(--font-primary);
  transition: color 150ms ease;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.review-subtab.active {
  border-bottom-color: var(--accent-primary);
  color: var(--accent-primary);
}

.review-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--accent-primary);
  color: #fff;
  min-width: 18px;
  text-align: center;
}

.review-badge-video {
  background: #4e7dd4;
}
</style>
