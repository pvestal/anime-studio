<template>
  <Dialog
    v-model:visible="visible"
    modal
    header="Commit Scene Changes"
    :style="{ width: '40rem' }"
  >
    <div class="commit-form space-y-4">
      <!-- Commit Message -->
      <div class="field">
        <label for="message" class="block text-sm font-medium mb-2">Commit Message</label>
        <Textarea
          id="message"
          v-model="form.message"
          placeholder="Describe your scene changes..."
          rows="3"
          class="w-full"
          :invalid="!form.message.trim()"
        />
        <small class="text-gray-500">Describe what changed in this scene version</small>
      </div>

      <!-- Scene Summary -->
      <div class="scene-summary p-3 bg-gray-50 rounded-lg">
        <h4 class="font-semibold mb-2">Scene Changes</h4>
        <div class="grid grid-cols-2 gap-2 text-sm">
          <div><strong>Frames:</strong> {{ sceneData.frames || 120 }}</div>
          <div><strong>Duration:</strong> {{ sceneData.duration || 5 }}s</div>
          <div><strong>Music Track:</strong> {{ sceneData.musicTrack || 'None' }}</div>
          <div><strong>Style:</strong> {{ sceneData.style || 'Default' }}</div>
        </div>
      </div>

      <!-- Render Options -->
      <div class="render-options">
        <div class="flex items-center justify-between mb-3">
          <label class="text-sm font-medium">Render After Commit</label>
          <ToggleButton
            v-model="form.shouldRender"
            onLabel="Yes"
            offLabel="No"
            onIcon="pi pi-play"
            offIcon="pi pi-pause"
          />
        </div>

        <div v-if="form.shouldRender" class="render-config space-y-3">
          <div class="field">
            <label class="block text-sm font-medium mb-1">Quality</label>
            <SelectButton
              v-model="form.renderConfig.quality"
              :options="qualityOptions"
              optionLabel="label"
              optionValue="value"
              class="w-full"
            />
          </div>

          <div class="field">
            <label class="block text-sm font-medium mb-1">Priority</label>
            <Dropdown
              v-model="form.renderConfig.priority"
              :options="priorityOptions"
              optionLabel="label"
              optionValue="value"
              placeholder="Select priority"
              class="w-full"
            />
          </div>

          <!-- Cost Preview -->
          <div class="cost-preview p-3 border rounded-lg">
            <div class="flex justify-between items-center">
              <span class="text-sm font-medium">Estimated Cost:</span>
              <span class="font-mono text-lg">${{ estimatedCost.toFixed(2) }}</span>
            </div>
            <div class="text-xs text-gray-500 mt-1">
              {{ form.renderConfig.quality }} quality • {{ estimatedRenderTime }}min render
            </div>
          </div>
        </div>
      </div>

      <!-- Tags -->
      <div class="field">
        <label class="block text-sm font-medium mb-2">Tags (optional)</label>
        <Chips
          v-model="form.tags"
          placeholder="Add tags..."
          class="w-full"
        />
        <small class="text-gray-500">Tags help organize and find commits later</small>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-between items-center">
        <div class="text-sm text-gray-500">
          Commit will be saved to branch: <strong>{{ currentBranch }}</strong>
        </div>
        <div class="flex gap-2">
          <Button
            label="Cancel"
            icon="pi pi-times"
            @click="handleCancel"
            severity="secondary"
          />
          <Button
            :label="form.shouldRender ? 'Commit & Render' : 'Commit'"
            :icon="form.shouldRender ? 'pi pi-play' : 'pi pi-save'"
            @click="handleCommit"
            :disabled="!form.message.trim()"
            severity="success"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import Dialog from 'primevue/dialog'
import Textarea from 'primevue/textarea'
import ToggleButton from 'primevue/togglebutton'
import SelectButton from 'primevue/selectbutton'
import Dropdown from 'primevue/dropdown'
import Button from 'primevue/button'
import Chips from 'primevue/chips'

const props = defineProps({
  visible: Boolean,
  sceneData: {
    type: Object,
    default: () => ({})
  },
  currentBranch: {
    type: String,
    default: 'main'
  }
})

const emit = defineEmits(['update:visible', 'commit'])

const form = ref({
  message: '',
  shouldRender: false,
  renderConfig: {
    quality: 'medium',
    priority: 'normal'
  },
  tags: []
})

const qualityOptions = [
  { label: 'Draft', value: 'draft' },
  { label: 'Medium', value: 'medium' },
  { label: 'High', value: 'high' },
  { label: 'Ultra', value: 'ultra' }
]

const priorityOptions = [
  { label: 'Low', value: 'low' },
  { label: 'Normal', value: 'normal' },
  { label: 'High', value: 'high' },
  { label: 'Urgent', value: 'urgent' }
]

const estimatedCost = computed(() => {
  const frames = props.sceneData.frames || 120
  const qualityMultiplier = {
    draft: 0.5,
    medium: 1.0,
    high: 1.5,
    ultra: 2.5
  }[form.value.renderConfig.quality] || 1.0

  const baseCost = (frames / 120) * 8.50 // Base cost for 120 frames
  return baseCost * qualityMultiplier
})

const estimatedRenderTime = computed(() => {
  const frames = props.sceneData.frames || 120
  const qualityTimeMultiplier = {
    draft: 0.5,
    medium: 1.0,
    high: 2.0,
    ultra: 4.0
  }[form.value.renderConfig.quality] || 1.0

  const baseTime = Math.ceil((frames / 120) * 6) // 6 minutes for 120 frames
  return Math.ceil(baseTime * qualityTimeMultiplier)
})

const handleCommit = () => {
  const commitData = {
    message: form.value.message,
    shouldRender: form.value.shouldRender,
    renderConfig: form.value.renderConfig,
    tags: form.value.tags,
    estimatedCost: estimatedCost.value,
    estimatedTime: estimatedRenderTime.value
  }

  emit('commit', commitData)
  resetForm()
}

const handleCancel = () => {
  emit('update:visible', false)
  resetForm()
}

const resetForm = () => {
  form.value = {
    message: '',
    shouldRender: false,
    renderConfig: {
      quality: 'medium',
      priority: 'normal'
    },
    tags: []
  }
}

// Auto-generate commit message suggestions
watch(() => props.sceneData, (newData) => {
  if (newData && Object.keys(newData).length > 0) {
    const suggestions = []

    if (newData.musicTrack) suggestions.push(`sync with ${newData.musicTrack}`)
    if (newData.style) suggestions.push(`${newData.style} style`)
    if (newData.duration) suggestions.push(`${newData.duration}s scene`)

    if (suggestions.length > 0) {
      form.value.message = `Update scene: ${suggestions.join(', ')}`
    }
  }
}, { immediate: true })
</script>

<style scoped>
.commit-form .field {
  margin-bottom: 1rem;
}

.render-config {
  border-left: 3px solid #3b82f6;
  padding-left: 1rem;
  margin-left: 0.5rem;
}

.cost-preview {
  background: linear-gradient(to right, #f0f9ff, #e0f2fe);
  border-color: #0ea5e9;
}
</style>