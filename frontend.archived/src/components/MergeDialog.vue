<template>
  <Dialog
    v-model:visible="visible"
    modal
    header="Merge Branches"
    :style="{ width: '45rem' }"
  >
    <div class="merge-form space-y-4">
      <!-- Merge Direction -->
      <div class="merge-direction p-4 bg-gray-50 rounded-lg">
        <div class="flex items-center justify-center gap-4">
          <div class="branch-info text-center">
            <div class="font-semibold text-lg">{{ selectedSourceBranch }}</div>
            <div class="text-sm text-gray-500">Source Branch</div>
          </div>
          <div class="arrow">
            <i class="pi pi-arrow-right text-2xl text-blue-600"></i>
          </div>
          <div class="branch-info text-center">
            <div class="font-semibold text-lg">{{ currentBranch }}</div>
            <div class="text-sm text-gray-500">Target Branch</div>
          </div>
        </div>
      </div>

      <!-- Source Branch Selection -->
      <div class="field">
        <label class="block text-sm font-medium mb-2">Source Branch</label>
        <Dropdown
          v-model="selectedSourceBranch"
          :options="availableBranches"
          optionLabel="name"
          optionValue="name"
          placeholder="Select branch to merge"
          class="w-full"
          @change="loadBranchComparison"
        />
        <small class="text-gray-500">Choose the branch you want to merge into {{ currentBranch }}</small>
      </div>

      <!-- Branch Comparison -->
      <div v-if="selectedSourceBranch && branchComparison" class="comparison">
        <h4 class="font-semibold mb-3">Branch Comparison</h4>

        <div class="grid grid-cols-2 gap-4 mb-4">
          <!-- Source Branch Stats -->
          <Card class="source-stats">
            <template #title>{{ selectedSourceBranch }}</template>
            <template #content>
              <div class="stats space-y-2">
                <div class="flex justify-between">
                  <span>Commits:</span>
                  <span class="font-mono">{{ branchComparison.source.commits }}</span>
                </div>
                <div class="flex justify-between">
                  <span>Scenes:</span>
                  <span class="font-mono">{{ branchComparison.source.scenes }}</span>
                </div>
                <div class="flex justify-between">
                  <span>Last Modified:</span>
                  <span class="text-sm">{{ formatDate(branchComparison.source.lastModified) }}</span>
                </div>
              </div>
            </template>
          </Card>

          <!-- Target Branch Stats -->
          <Card class="target-stats">
            <template #title>{{ currentBranch }}</template>
            <template #content>
              <div class="stats space-y-2">
                <div class="flex justify-between">
                  <span>Commits:</span>
                  <span class="font-mono">{{ branchComparison.target.commits }}</span>
                </div>
                <div class="flex justify-between">
                  <span>Scenes:</span>
                  <span class="font-mono">{{ branchComparison.target.scenes }}</span>
                </div>
                <div class="flex justify-between">
                  <span>Last Modified:</span>
                  <span class="text-sm">{{ formatDate(branchComparison.target.lastModified) }}</span>
                </div>
              </div>
            </template>
          </Card>
        </div>

        <!-- Changes Summary -->
        <div class="changes-summary p-3 border rounded-lg">
          <h5 class="font-semibold mb-2">Changes to be merged:</h5>
          <div class="changes space-y-1">
            <div v-for="change in branchComparison.changes" :key="change.id" class="change-item flex items-center gap-2 text-sm">
              <i :class="getChangeIcon(change.type)" :class="getChangeColor(change.type)"></i>
              <span>{{ change.description }}</span>
            </div>
          </div>
        </div>

        <!-- Potential Conflicts -->
        <div v-if="branchComparison.conflicts.length > 0" class="conflicts p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
          <h5 class="font-semibold text-yellow-800 mb-2">
            <i class="pi pi-exclamation-triangle mr-1"></i>
            Potential Conflicts ({{ branchComparison.conflicts.length }})
          </h5>
          <div class="conflicts-list space-y-1">
            <div v-for="conflict in branchComparison.conflicts" :key="conflict.id" class="conflict-item text-sm text-yellow-700">
              <div class="font-medium">{{ conflict.scene }}</div>
              <div class="text-xs">{{ conflict.description }}</div>
            </div>
          </div>
          <div class="text-sm text-yellow-600 mt-2">
            These conflicts will need to be resolved manually if they occur during merge.
          </div>
        </div>
      </div>

      <!-- Merge Strategy -->
      <div class="field">
        <label class="block text-sm font-medium mb-2">Merge Strategy</label>
        <div class="strategy-options space-y-2">
          <div
            v-for="strategy in mergeStrategies"
            :key="strategy.value"
            class="strategy-option p-3 border rounded-lg cursor-pointer"
            :class="{ 'selected': selectedStrategy === strategy.value }"
            @click="selectedStrategy = strategy.value"
          >
            <div class="flex items-start gap-3">
              <i :class="strategy.icon" class="text-lg mt-1"></i>
              <div>
                <div class="font-semibold">{{ strategy.label }}</div>
                <div class="text-sm text-gray-600">{{ strategy.description }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Merge Options -->
      <div class="options space-y-2">
        <div class="flex items-center gap-2">
          <Checkbox
            id="squash"
            v-model="mergeOptions.squash"
          />
          <label for="squash" class="text-sm">Squash commits into single commit</label>
        </div>

        <div class="flex items-center gap-2">
          <Checkbox
            id="delete-branch"
            v-model="mergeOptions.deleteBranch"
          />
          <label for="delete-branch" class="text-sm">Delete source branch after merge</label>
        </div>

        <div class="flex items-center gap-2">
          <Checkbox
            id="create-backup"
            v-model="mergeOptions.createBackup"
          />
          <label for="create-backup" class="text-sm">Create backup before merge</label>
        </div>
      </div>

      <!-- Merge Message -->
      <div class="field">
        <label for="message" class="block text-sm font-medium mb-2">Merge Commit Message</label>
        <Textarea
          id="message"
          v-model="mergeMessage"
          :placeholder="`Merge ${selectedSourceBranch} into ${currentBranch}`"
          rows="2"
          class="w-full"
        />
        <small class="text-gray-500">Optional custom message for the merge commit</small>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-between items-center">
        <div class="text-sm text-gray-500">
          <i class="pi pi-info-circle mr-1"></i>
          {{ branchComparison?.conflicts.length > 0 ? 'Conflicts may require manual resolution' : 'No conflicts detected' }}
        </div>
        <div class="flex gap-2">
          <Button
            label="Cancel"
            icon="pi pi-times"
            @click="handleCancel"
            severity="secondary"
          />
          <Button
            label="Start Merge"
            icon="pi pi-arrow-right"
            @click="handleMerge"
            :disabled="!canMerge"
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
import Dropdown from 'primevue/dropdown'
import Card from 'primevue/card'
import Checkbox from 'primevue/checkbox'
import Textarea from 'primevue/textarea'
import Button from 'primevue/button'

const props = defineProps({
  visible: Boolean,
  availableBranches: {
    type: Array,
    default: () => []
  },
  currentBranch: {
    type: String,
    default: 'main'
  }
})

const emit = defineEmits(['update:visible', 'merge'])

const selectedSourceBranch = ref('')
const selectedStrategy = ref('auto')
const mergeMessage = ref('')
const branchComparison = ref(null)

const mergeOptions = ref({
  squash: false,
  deleteBranch: false,
  createBackup: true
})

const mergeStrategies = [
  {
    value: 'auto',
    label: 'Auto Merge',
    description: 'Automatically resolve simple conflicts, prompt for complex ones',
    icon: 'pi pi-bolt'
  },
  {
    value: 'manual',
    label: 'Manual Resolution',
    description: 'Review all conflicts manually before merging',
    icon: 'pi pi-eye'
  },
  {
    value: 'prefer-target',
    label: 'Prefer Target',
    description: 'Keep current branch version when conflicts occur',
    icon: 'pi pi-arrow-left'
  },
  {
    value: 'prefer-source',
    label: 'Prefer Source',
    description: 'Use source branch version when conflicts occur',
    icon: 'pi pi-arrow-right'
  }
]

const canMerge = computed(() => {
  return selectedSourceBranch.value && selectedStrategy.value
})

const loadBranchComparison = async () => {
  if (!selectedSourceBranch.value) {
    branchComparison.value = null
    return
  }

  try {
    const response = await fetch('/api/anime/git/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sourceBranch: selectedSourceBranch.value,
        targetBranch: props.currentBranch
      })
    })

    if (response.ok) {
      branchComparison.value = await response.json()
    }
  } catch (error) {
    console.error('Failed to load branch comparison:', error)
    // Provide mock data for demo
    branchComparison.value = {
      source: {
        commits: 8,
        scenes: 5,
        lastModified: new Date(Date.now() - 86400000)
      },
      target: {
        commits: 15,
        scenes: 8,
        lastModified: new Date()
      },
      changes: [
        { id: 1, type: 'added', description: 'Added new character introduction scene' },
        { id: 2, type: 'modified', description: 'Enhanced battle sequence choreography' },
        { id: 3, type: 'added', description: 'New background music for emotional scenes' },
        { id: 4, type: 'modified', description: 'Updated character dialogue in finale' }
      ],
      conflicts: [
        {
          id: 1,
          scene: 'Scene 3: Battle Sequence',
          description: 'Both branches modified the same fight choreography'
        },
        {
          id: 2,
          scene: 'Scene 7: Character Dialogue',
          description: 'Different dialogue choices for the same character'
        }
      ]
    }
  }
}

const getChangeIcon = (type) => {
  switch (type) {
    case 'added': return 'pi pi-plus-circle'
    case 'modified': return 'pi pi-pencil'
    case 'deleted': return 'pi pi-minus-circle'
    default: return 'pi pi-circle'
  }
}

const getChangeColor = (type) => {
  switch (type) {
    case 'added': return 'text-green-600'
    case 'modified': return 'text-blue-600'
    case 'deleted': return 'text-red-600'
    default: return 'text-gray-600'
  }
}

const formatDate = (date) => {
  return new Intl.RelativeTimeFormatter('en', { numeric: 'auto' }).format(
    Math.ceil((date - new Date()) / (1000 * 60 * 60 * 24)),
    'day'
  )
}

const handleMerge = () => {
  if (canMerge.value) {
    const mergeData = {
      sourceBranch: selectedSourceBranch.value,
      targetBranch: props.currentBranch,
      strategy: selectedStrategy.value,
      message: mergeMessage.value || `Merge ${selectedSourceBranch.value} into ${props.currentBranch}`,
      options: mergeOptions.value
    }

    emit('merge', mergeData)
    resetForm()
  }
}

const handleCancel = () => {
  emit('update:visible', false)
  resetForm()
}

const resetForm = () => {
  selectedSourceBranch.value = ''
  selectedStrategy.value = 'auto'
  mergeMessage.value = ''
  branchComparison.value = null
  mergeOptions.value = {
    squash: false,
    deleteBranch: false,
    createBackup: true
  }
}

// Watch for source branch changes
watch(selectedSourceBranch, () => {
  if (selectedSourceBranch.value) {
    mergeMessage.value = `Merge ${selectedSourceBranch.value} into ${props.currentBranch}`
  }
})
</script>

<style scoped>
.merge-form .field {
  margin-bottom: 1rem;
}

.strategy-option {
  transition: all 0.2s ease;
}

.strategy-option:hover {
  background: #f3f4f6;
  border-color: #9ca3af;
}

.strategy-option.selected {
  background: #eff6ff;
  border-color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
}

.arrow {
  padding: 0 1rem;
}

.branch-info {
  min-width: 120px;
}

.changes-summary {
  background: #f8fafc;
  border-color: #e2e8f0;
}

.change-item {
  padding: 0.25rem 0;
}

.conflict-item {
  padding: 0.25rem 0;
  border-left: 3px solid #f59e0b;
  padding-left: 0.75rem;
}
</style>