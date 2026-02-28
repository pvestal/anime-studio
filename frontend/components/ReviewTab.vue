<template>
  <div>
    <!-- Sub-tab navigation -->
    <div style="display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border-primary);">
      <RouterLink to="/review/images" class="review-subtab" active-class="" exact-active-class="active">
        Pending Images
        <span v-if="pendingCount > 0" class="review-badge">{{ pendingCount }}</span>
      </RouterLink>
      <RouterLink to="/review/videos" class="review-subtab" active-class="" exact-active-class="active">
        Pending Videos
        <span v-if="videoCount > 0" class="review-badge review-badge-video">{{ videoCount }}</span>
      </RouterLink>
      <RouterLink to="/review/library" class="review-subtab" active-class="" exact-active-class="active">
        Library
      </RouterLink>
    </div>

    <RouterView />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useApprovalStore } from '@/stores/approval'
import { useVideoReviewStore } from '@/stores/videoReview'

const approvalStore = useApprovalStore()
const videoReviewStore = useVideoReviewStore()
const pendingCount = computed(() => approvalStore.pendingImages.length)
const videoCount = computed(() => videoReviewStore.pendingCount)

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
  text-decoration: none;
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
