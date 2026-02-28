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
    component: () => import('@/components/CastTab.vue'),
    redirect: '/cast/characters',
    children: [
      {
        path: 'characters',
        name: 'CastCharacters',
        component: () => import('@/components/CharactersTab.vue'),
        props: { hideSubTabs: true, initialSubTab: 'characters' },
      },
      {
        path: 'ingest',
        name: 'CastIngest',
        component: () => import('@/components/CharactersTab.vue'),
        props: { hideSubTabs: true, initialSubTab: 'ingest' },
      },
      {
        path: 'voice',
        name: 'CastVoice',
        component: () => import('@/components/VoiceTab.vue'),
      },
    ],
  },
  {
    path: '/script',
    component: () => import('@/components/ScriptTab.vue'),
    redirect: '/script/scenes',
    children: [
      {
        path: 'scenes',
        name: 'ScriptScenes',
        component: () => import('@/components/SceneBuilderTab.vue'),
      },
      {
        path: 'screenplay',
        name: 'ScriptScreenplay',
        component: () => import('@/components/script/ScreenplayView.vue'),
      },
    ],
  },
  {
    path: '/produce',
    name: 'Produce',
    component: () => import('@/components/ProduceTab.vue'),
  },
  {
    path: '/review',
    component: () => import('@/components/ReviewTab.vue'),
    redirect: '/review/images',
    children: [
      {
        path: 'images',
        name: 'ReviewImages',
        component: () => import('@/components/PendingTab.vue'),
      },
      {
        path: 'videos',
        name: 'ReviewVideos',
        component: () => import('@/components/PendingVideosTab.vue'),
      },
      {
        path: 'library',
        name: 'ReviewLibrary',
        component: () => import('@/components/LibraryTab.vue'),
      },
    ],
  },
  {
    path: '/publish',
    component: () => import('@/components/PublishTab.vue'),
    redirect: '/publish/episodes',
    children: [
      {
        path: 'episodes',
        name: 'PublishEpisodes',
        component: () => import('@/components/publish/PublishEpisodesView.vue'),
      },
      {
        path: 'library',
        name: 'PublishLibrary',
        component: () => import('@/components/publish/PublishedLibrary.vue'),
      },
    ],
  },
  {
    path: '/play',
    name: 'Play',
    component: () => import('@/components/PlayTab.vue'),
  },
  // ===== Legacy redirects =====
  { path: '/project', redirect: '/story' },
  { path: '/characters', redirect: '/cast/characters' },
  { path: '/create', redirect: '/cast/characters' },
  { path: '/generate', redirect: '/cast/characters' },
  { path: '/ingest', redirect: '/cast/ingest' },
  { path: '/voice', redirect: '/cast/voice' },
  { path: '/voices', redirect: '/cast/voice' },
  { path: '/production', redirect: '/produce' },
  { path: '/train', redirect: '/produce' },
  { path: '/scenes', redirect: '/script/scenes' },
  { path: '/analytics', redirect: '/produce' },
  { path: '/dashboard', redirect: '/produce' },
  { path: '/echo', redirect: '/produce' },
  { path: '/approve', redirect: '/review/images' },
  { path: '/library', redirect: '/review/library' },
  { path: '/gallery', redirect: '/review/library' },
  { path: '/interactive', redirect: '/play' },
]

export const router = createRouter({
  history: createWebHistory('/anime-studio/'),
  routes,
})
