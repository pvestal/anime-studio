import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/story',
  },
  // ===== Primary routes (creative pipeline order) =====
  {
    path: '/story',
    name: 'Story',
    component: () => import('@/components/ProjectTab.vue'),
  },
  {
    path: '/cast',
    name: 'Cast',
    component: () => import('@/components/CastTab.vue'),
  },
  {
    path: '/script',
    name: 'Script',
    component: () => import('@/components/ScriptTab.vue'),
  },
  {
    path: '/produce',
    name: 'Produce',
    component: () => import('@/components/ProduceTab.vue'),
  },
  {
    path: '/review',
    name: 'Review',
    component: () => import('@/components/ReviewTab.vue'),
  },
  {
    path: '/publish',
    name: 'Publish',
    component: () => import('@/components/PublishTab.vue'),
  },
  // ===== Legacy redirects =====
  { path: '/project', redirect: '/story' },
  { path: '/characters', redirect: '/cast' },
  { path: '/create', redirect: '/cast' },
  { path: '/generate', redirect: '/cast' },
  { path: '/ingest', redirect: '/cast' },
  { path: '/voice', redirect: '/cast' },
  { path: '/voices', redirect: '/cast' },
  { path: '/production', redirect: '/produce' },
  { path: '/train', redirect: '/produce' },
  { path: '/scenes', redirect: '/script' },
  { path: '/analytics', redirect: '/produce' },
  { path: '/dashboard', redirect: '/produce' },
  { path: '/echo', redirect: '/produce' },
  { path: '/approve', redirect: '/review' },
  { path: '/library', redirect: '/review' },
  { path: '/gallery', redirect: '/review' },
]

export const router = createRouter({
  history: createWebHistory('/anime-studio/'),
  routes,
})
