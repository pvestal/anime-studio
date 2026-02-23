import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/project',
  },
  {
    path: '/project',
    name: 'Project',
    component: () => import('@/components/ProjectTab.vue'),
  },
  {
    path: '/characters',
    name: 'Characters',
    component: () => import('@/components/CharactersTab.vue'),
  },
  {
    path: '/review',
    name: 'Review',
    component: () => import('@/components/ReviewTab.vue'),
  },
  {
    path: '/production',
    name: 'Production',
    component: () => import('@/components/ProductionTab.vue'),
  },
  {
    path: '/voice',
    name: 'Voice',
    component: () => import('@/components/VoiceTab.vue'),
  },
  {
    path: '/analytics',
    name: 'Analytics',
    component: () => import('@/components/AnalyticsTab.vue'),
  },
  // Legacy redirects
  { path: '/story', redirect: '/project' },
  { path: '/create', redirect: '/characters' },
  { path: '/generate', redirect: '/characters' },
  { path: '/approve', redirect: '/review' },
  { path: '/library', redirect: '/review' },
  { path: '/gallery', redirect: '/review' },
  { path: '/train', redirect: '/production' },
  { path: '/scenes', redirect: '/production' },
  { path: '/dashboard', redirect: '/analytics' },
  { path: '/echo', redirect: '/analytics' },
  { path: '/ingest', redirect: '/characters' },
  { path: '/voices', redirect: '/voice' },
]

export const router = createRouter({
  history: createWebHistory('/anime-studio/'),
  routes,
})
