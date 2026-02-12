<template>
  <Dialog
    v-model:visible="visible"
    modal
    :header="`Render Cost Confirmation - ${scene.name}`"
    :style="{ width: '50rem' }"
    class="cost-dialog"
  >
    <div class="cost-breakdown">
      <!-- Scene Info -->
      <div class="scene-info mb-4 p-4 border-l-4 border-blue-500 bg-gray-50">
        <h3 class="font-bold text-lg">{{ scene.name }}</h3>
        <div class="grid grid-cols-2 gap-4 mt-2 text-sm">
          <div><strong>Frames:</strong> {{ scene.frames }}</div>
          <div><strong>Duration:</strong> {{ scene.duration }}s</div>
          <div><strong>Resolution:</strong> {{ scene.resolution }}</div>
          <div><strong>Quality:</strong> {{ scene.quality }}</div>
        </div>
      </div>

      <!-- Budget Status -->
      <div class="budget-status mb-4">
        <div class="flex justify-between items-center mb-2">
          <span class="font-semibold">Daily Budget ($150.00)</span>
          <span class="text-sm text-gray-600">${{ budgetUsed.toFixed(2) }} used</span>
        </div>
        <ProgressBar
          :value="budgetUsedPercent"
          :class="{
            'budget-safe': budgetUsedPercent < 70,
            'budget-warning': budgetUsedPercent >= 70 && budgetUsedPercent < 90,
            'budget-danger': budgetUsedPercent >= 90
          }"
        />
        <div class="text-xs text-gray-500 mt-1">
          ${{ budgetRemaining.toFixed(2) }} remaining today
        </div>
      </div>

      <!-- Cost Comparison -->
      <div class="cost-comparison grid grid-cols-2 gap-4 mb-4">
        <!-- Firebase Cloud Option -->
        <Card class="firebase-option" :class="{ 'selected': selectedOption === 'firebase' }">
          <template #header>
            <div class="flex items-center gap-2 p-3 bg-orange-100">
              <i class="pi pi-cloud text-orange-600"></i>
              <span class="font-bold">Firebase Cloud</span>
            </div>
          </template>
          <template #content>
            <div class="cost-details">
              <div class="cost-item">
                <span>GPU Time ({{ estimatedRenderTime }}min):</span>
                <span class="font-mono">${{ costs.firebase.gpu.toFixed(2) }}</span>
              </div>
              <div class="cost-item">
                <span>Storage ({{ estimatedFileSize }}MB):</span>
                <span class="font-mono">${{ costs.firebase.storage.toFixed(2) }}</span>
              </div>
              <div class="cost-item">
                <span>Network Transfer:</span>
                <span class="font-mono">${{ costs.firebase.network.toFixed(2) }}</span>
              </div>
              <div class="cost-item">
                <span>Function Overhead:</span>
                <span class="font-mono">${{ costs.firebase.functions.toFixed(2) }}</span>
              </div>
              <hr class="my-2">
              <div class="cost-total">
                <span class="font-bold">Total:</span>
                <span class="font-bold text-lg">${{ costs.firebase.total.toFixed(2) }}</span>
              </div>
              <div class="benefits mt-3">
                <div class="text-sm text-green-600">✓ No local GPU usage</div>
                <div class="text-sm text-green-600">✓ Faster completion (~{{ estimatedRenderTime }}min)</div>
                <div class="text-sm text-green-600">✓ Continue other work</div>
              </div>
            </div>
          </template>
        </Card>

        <!-- Local GPU Option -->
        <Card class="local-option" :class="{ 'selected': selectedOption === 'local' }">
          <template #header>
            <div class="flex items-center gap-2 p-3 bg-blue-100">
              <i class="pi pi-desktop text-blue-600"></i>
              <span class="font-bold">Local GPU</span>
            </div>
          </template>
          <template #content>
            <div class="cost-details">
              <div class="cost-item">
                <span>GPU Cost:</span>
                <span class="font-mono text-green-600">$0.00</span>
              </div>
              <div class="cost-item">
                <span>Electricity (~$0.12/kWh):</span>
                <span class="font-mono">${{ costs.local.electricity.toFixed(2) }}</span>
              </div>
              <hr class="my-2">
              <div class="cost-total">
                <span class="font-bold">Total:</span>
                <span class="font-bold text-lg">${{ costs.local.total.toFixed(2) }}</span>
              </div>
              <div class="status mt-3">
                <div class="text-sm" :class="localGpuStatus.busy ? 'text-red-600' : 'text-green-600'">
                  {{ localGpuStatus.busy ? '⚠️ GPU Busy' : '✓ GPU Available' }}
                </div>
                <div class="text-sm">VRAM: {{ localGpuStatus.vramUsed }}GB / {{ localGpuStatus.vramTotal }}GB</div>
                <div class="text-sm">Queue: {{ localGpuStatus.queueLength }} jobs</div>
                <div class="text-sm">ETA: ~{{ localGpuStatus.estimatedWait }}min</div>
              </div>
            </div>
          </template>
        </Card>
      </div>

      <!-- Warning Messages -->
      <div v-if="budgetExceeded" class="budget-warning mb-4 p-3 bg-red-100 border border-red-300 rounded">
        <div class="flex items-center gap-2 text-red-700">
          <i class="pi pi-exclamation-triangle"></i>
          <span class="font-bold">Budget Exceeded!</span>
        </div>
        <p class="text-sm text-red-600 mt-1">
          This render would exceed your daily $150 budget. Consider using local GPU or reducing quality.
        </p>
      </div>

      <div v-if="recommendLocal" class="recommendation mb-4 p-3 bg-yellow-100 border border-yellow-300 rounded">
        <div class="flex items-center gap-2 text-yellow-700">
          <i class="pi pi-info-circle"></i>
          <span class="font-bold">Recommendation: Use Local GPU</span>
        </div>
        <p class="text-sm text-yellow-600 mt-1">
          {{ localRecommendationReason }}
        </p>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-between items-center">
        <div class="text-sm text-gray-500">
          Auto-approval threshold: ${{ autoApprovalThreshold }}
        </div>
        <div class="flex gap-2">
          <Button
            label="Cancel"
            icon="pi pi-times"
            @click="handleCancel"
            severity="secondary"
          />
          <Button
            v-if="!budgetExceeded"
            label="Use Local"
            icon="pi pi-desktop"
            @click="handleUseLocal"
            :disabled="localGpuStatus.busy && localGpuStatus.queueLength > 3"
            severity="info"
          />
          <Button
            v-if="selectedOption === 'firebase' && !budgetExceeded"
            :label="`Approve $${costs.firebase.total.toFixed(2)}`"
            icon="pi pi-check"
            @click="handleApprove"
            severity="success"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import Dialog from 'primevue/dialog'
import Card from 'primevue/card'
import Button from 'primevue/button'
import ProgressBar from 'primevue/progressbar'

const props = defineProps({
  visible: Boolean,
  scene: {
    type: Object,
    required: true,
    default: () => ({
      name: 'Unknown Scene',
      frames: 120,
      duration: 5,
      resolution: '1024x1024',
      quality: 'high'
    })
  }
})

const emit = defineEmits(['update:visible', 'approve', 'useLocal', 'cancel'])

// Budget tracking
const dailyBudgetLimit = 150.00
const budgetUsed = ref(0)
const autoApprovalThreshold = ref(5.00)

// Cost calculations
const costs = ref({
  firebase: {
    gpu: 0,
    storage: 0,
    network: 0,
    functions: 0,
    total: 0
  },
  local: {
    electricity: 0,
    total: 0
  }
})

// Local GPU status
const localGpuStatus = ref({
  busy: false,
  vramUsed: 4.1,
  vramTotal: 12.0,
  queueLength: 0,
  estimatedWait: 5
})

const selectedOption = ref('firebase')
const estimatedRenderTime = ref(0)
const estimatedFileSize = ref(0)

// Computed properties
const budgetRemaining = computed(() => dailyBudgetLimit - budgetUsed.value)
const budgetUsedPercent = computed(() => (budgetUsed.value / dailyBudgetLimit) * 100)
const budgetExceeded = computed(() => (budgetUsed.value + costs.value.firebase.total) > dailyBudgetLimit)
const recommendLocal = computed(() => {
  return !localGpuStatus.value.busy &&
         costs.value.firebase.total > 10.00 &&
         budgetUsedPercent.value > 50
})
const localRecommendationReason = computed(() => {
  if (budgetUsedPercent.value > 80) return "Budget usage is high - save costs with local rendering"
  if (costs.value.firebase.total > 20) return "High render cost - local GPU would be free"
  if (!localGpuStatus.value.busy) return "Local GPU is available with no queue"
  return "Consider local rendering to preserve cloud budget"
})

// Methods
const calculateCosts = () => {
  const frames = props.scene.frames || 120
  const duration = props.scene.duration || 5
  const resolution = props.scene.resolution || '1024x1024'
  const quality = props.scene.quality || 'high'

  // Estimate render time based on complexity
  const baseTimePerFrame = quality === 'high' ? 3 : quality === 'medium' ? 2 : 1
  estimatedRenderTime.value = Math.ceil((frames * baseTimePerFrame) / 60) // Convert to minutes

  // Estimate file size (MB)
  const resolutionMultiplier = resolution.includes('1024') ? 1 : resolution.includes('512') ? 0.5 : 1.5
  estimatedFileSize.value = Math.ceil(frames * 2 * resolutionMultiplier) // ~2MB per 1024x1024 frame

  // Firebase costs (based on actual Firebase pricing)
  costs.value.firebase.gpu = estimatedRenderTime.value * 0.74 // V100 GPU per minute
  costs.value.firebase.storage = (estimatedFileSize.value / 1024) * 0.026 * (1/30) // Per day storage
  costs.value.firebase.network = estimatedFileSize.value > 1000 ? (estimatedFileSize.value / 1024) * 0.12 : 0
  costs.value.firebase.functions = 0.0000025 * estimatedRenderTime.value * 60 * 8 // 8GB memory
  costs.value.firebase.total = Object.values(costs.value.firebase).reduce((sum, cost) => sum + cost, 0)

  // Local costs (electricity only)
  const gpuWatts = 170 // RTX 3060 power draw
  const electricityRate = 0.12 // $0.12 per kWh
  const renderTimeHours = estimatedRenderTime.value / 60
  costs.value.local.electricity = (gpuWatts / 1000) * renderTimeHours * electricityRate
  costs.value.local.total = costs.value.local.electricity

  // Auto-select cheaper option
  selectedOption.value = costs.value.local.total < costs.value.firebase.total ? 'local' : 'firebase'
}

const loadBudgetStatus = async () => {
  try {
    const response = await fetch('/api/anime/budget/daily')
    if (response.ok) {
      const data = await response.json()
      budgetUsed.value = data.used || 0
      autoApprovalThreshold.value = data.autoApprovalThreshold || 5.00
    }
  } catch (error) {
    console.warn('Could not load budget status:', error)
  }
}

const loadGpuStatus = async () => {
  try {
    const response = await fetch('http://192.168.50.135:8188/system_stats')
    if (response.ok) {
      const data = await response.json()
      const device = data.devices[0]
      localGpuStatus.value = {
        busy: (device.vram_free / device.vram_total) < 0.3, // Less than 30% free = busy
        vramUsed: ((device.vram_total - device.vram_free) / 1024 / 1024 / 1024).toFixed(1),
        vramTotal: (device.vram_total / 1024 / 1024 / 1024).toFixed(1),
        queueLength: 0, // Would need to query actual queue
        estimatedWait: Math.ceil(estimatedRenderTime.value * 1.5) // Rough estimate
      }
    }
  } catch (error) {
    console.warn('Could not load GPU status:', error)
  }
}

const handleApprove = () => {
  emit('approve', {
    option: 'firebase',
    cost: costs.value.firebase.total,
    estimatedTime: estimatedRenderTime.value
  })
  emit('update:visible', false)
}

const handleUseLocal = () => {
  emit('useLocal', {
    option: 'local',
    cost: costs.value.local.total,
    estimatedTime: localGpuStatus.value.estimatedWait
  })
  emit('update:visible', false)
}

const handleCancel = () => {
  emit('cancel')
  emit('update:visible', false)
}

onMounted(() => {
  calculateCosts()
  loadBudgetStatus()
  loadGpuStatus()
})
</script>

<style scoped>
.cost-dialog {
  font-family: 'Inter', sans-serif;
}

.cost-item {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.cost-total {
  display: flex;
  justify-content: space-between;
  font-size: 1.1rem;
}

.selected {
  border: 2px solid #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.budget-safe :deep(.p-progressbar-value) {
  background: linear-gradient(to right, #10b981, #34d399);
}

.budget-warning :deep(.p-progressbar-value) {
  background: linear-gradient(to right, #f59e0b, #fbbf24);
}

.budget-danger :deep(.p-progressbar-value) {
  background: linear-gradient(to right, #ef4444, #f87171);
}

.benefits div, .status div {
  line-height: 1.4;
}
</style>