<template>
  <div id="app" style="min-height: 100vh; background: var(--bg-primary); color: var(--text-primary);">
    <header style="background: var(--bg-secondary); border-bottom: 1px solid var(--border-primary); padding: 16px 24px;">
      <div style="max-width: 1400px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center;">
        <div>
          <h1 style="font-size: 20px; font-weight: 500; color: var(--text-primary);">Anime Studio</h1>
          <p style="font-size: 13px; color: var(--text-muted);">Anime production: project, characters, review, production, voice, analytics</p>
        </div>
        <EchoFloatingPanel />
      </div>
    </header>

    <nav style="background: var(--bg-secondary); border-bottom: 1px solid var(--border-primary);">
      <div style="max-width: 1400px; margin: 0 auto; padding: 0 24px; display: flex; gap: 0;">
        <RouterLink
          v-for="link in navLinks"
          :key="link.to"
          :to="link.to"
          class="nav-link"
        >
          {{ link.label }}
          <span v-if="link.count !== undefined && link.count > 0" style="margin-left: 6px; font-size: 11px; padding: 1px 6px; border-radius: 10px; background: var(--accent-primary); color: #fff;">
            {{ link.count }}
          </span>
        </RouterLink>
      </div>
    </nav>

    <main style="max-width: 1400px; margin: 0 auto; padding: 24px;">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useApprovalStore } from '@/stores/approval'
import { useCharactersStore } from '@/stores/characters'
import EchoFloatingPanel from '@/components/EchoFloatingPanel.vue'

const approvalStore = useApprovalStore()
const charactersStore = useCharactersStore()

onMounted(() => {
  approvalStore.fetchPendingImages()
  charactersStore.fetchCharacters()
})

const navLinks = computed(() => [
  { to: '/project', label: '1. Project' },
  { to: '/characters', label: '2. Characters' },
  { to: '/review', label: '3. Review', count: approvalStore.pendingImages.length },
  { to: '/production', label: '4. Production' },
  { to: '/voice', label: '5. Voice' },
  { to: '/analytics', label: '6. Analytics' },
])
</script>

<style scoped>
.nav-link {
  padding: 12px 16px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
  font-family: var(--font-primary);
  transition: color 150ms ease;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}

.nav-link.router-link-active {
  border-bottom-color: var(--accent-primary);
  color: var(--accent-primary);
}
</style>
