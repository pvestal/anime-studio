<template>
  <div>
    <!-- Sub-tab navigation -->
    <div style="display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border-primary);">
      <RouterLink to="/publish/episodes" class="publish-subtab" active-class="" exact-active-class="active">
        Episodes
      </RouterLink>
      <RouterLink to="/publish/library" class="publish-subtab" active-class="" exact-active-class="active">
        Library
      </RouterLink>
    </div>

    <RouterView />
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.publish-subtab {
  padding: 10px 20px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  font-family: var(--font-primary);
  transition: all 150ms ease;
  text-decoration: none;
}
.publish-subtab:hover {
  color: var(--accent-primary);
}
.publish-subtab.active {
  border-bottom-color: var(--accent-primary);
  color: var(--accent-primary);
  font-weight: 500;
}
</style>
