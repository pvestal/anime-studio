<template>
  <div>
    <!-- Sub-tab navigation -->
    <div style="display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border-primary);">
      <RouterLink to="/cast/characters" class="cast-subtab" active-class="" exact-active-class="active">
        Characters
      </RouterLink>
      <RouterLink to="/cast/ingest" class="cast-subtab" active-class="" exact-active-class="active">
        Ingest
      </RouterLink>
      <RouterLink to="/cast/voice" class="cast-subtab" active-class="" exact-active-class="active">
        Voice
      </RouterLink>
    </div>

    <RouterView :key="$route.path" />
  </div>
</template>

<script setup lang="ts">
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
  text-decoration: none;
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
