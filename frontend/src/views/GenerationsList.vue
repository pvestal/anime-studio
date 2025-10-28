<template>
  <TowerCard class="p-6">
    <h3 class="text-lg font-semibold mb-4">Generations</h3>
    
    <div v-if="loading" class="text-center py-8">Loading...</div>
    
    <div v-else-if="generations && generations.length > 0" class="space-y-3">
      <div v-for="gen in generations" :key="gen.id" class="generation-item p-4 bg-gray-800 rounded">
        <div class="flex justify-between items-start">
          <div class="flex-1">
            <h4 class="font-semibold">{{ gen.prompt || 'No prompt' }}</h4>
            <p class="text-sm text-gray-400 mt-1">ID: {{ gen.id }}</p>
            <p class="text-sm mt-1">Character: {{ gen.character || 'N/A' }}</p>
          </div>
          <div class="text-right">
            <span :class="getStatusClass(gen.status)" class="text-sm px-2 py-1 rounded">
              {{ gen.status }}
            </span>
            <div v-if="gen.progress !== undefined" class="text-sm text-gray-400 mt-2">
              {{ gen.progress }}%
            </div>
          </div>
        </div>
        
        <!-- Progress bar -->
        <div v-if="gen.status !== 'completed' && gen.status !== 'failed'" class="mt-3">
          <div class="w-full bg-gray-700 rounded-full h-2">
            <div class="bg-blue-500 h-2 rounded-full transition-all" :style="{ width: (gen.progress || 0) + '%' }"></div>
          </div>
        </div>
        
        <!-- Video link if completed -->
        <div v-if="gen.status === 'completed' && gen.video_path" class="mt-3">
          <a :href="gen.video_path" class="text-blue-400 hover:underline text-sm">
            Download Video
          </a>
        </div>
        
        <!-- Error message if failed -->
        <div v-if="gen.status === 'failed' && gen.error" class="mt-2 text-red-400 text-sm">
          Error: {{ gen.error }}
        </div>
      </div>
    </div>
    
    <div v-else class="text-center text-gray-400 py-8">
      No generations yet
    </div>
  </TowerCard>
</template>

<script setup>
import { TowerCard, usePolling } from '@tower/ui-components'

const { data: generations, loading } = usePolling('/api/generations', { interval: 3000 })

const getStatusClass = (status) => {
  const classes = {
    'pending': 'bg-gray-700 text-gray-300',
    'processing': 'bg-blue-900 text-blue-300',
    'completed': 'bg-green-900 text-green-300',
    'failed': 'bg-red-900 text-red-300'
  }
  return classes[status] || 'bg-gray-700'
}
</script>

<style scoped>
.generation-item {
  border: 1px solid rgba(255, 255, 255, 0.1);
}
</style>
