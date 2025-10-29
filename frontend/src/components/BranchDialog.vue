<template>
  <Dialog
    v-model:visible="visible"
    modal
    header="Create New Branch"
    :style="{ width: '35rem' }"
  >
    <div class="branch-form space-y-4">
      <!-- Branch Name -->
      <div class="field">
        <label for="name" class="block text-sm font-medium mb-2">Branch Name</label>
        <InputText
          id="name"
          v-model="form.name"
          placeholder="e.g., dark-ending, comedy-route, action-sequence"
          class="w-full"
          :invalid="!isValidBranchName"
          @input="validateBranchName"
        />
        <small v-if="!isValidBranchName && form.name" class="text-red-500">
          Use lowercase letters, numbers, and dashes only
        </small>
        <small v-else class="text-gray-500">
          Use descriptive names like "alternative-ending" or "character-focus"
        </small>
      </div>

      <!-- Description -->
      <div class="field">
        <label for="description" class="block text-sm font-medium mb-2">Description</label>
        <Textarea
          id="description"
          v-model="form.description"
          placeholder="Describe the creative direction for this branch..."
          rows="3"
          class="w-full"
        />
        <small class="text-gray-500">Explain how this branch differs from the main storyline</small>
      </div>

      <!-- Branch Type -->
      <div class="field">
        <label class="block text-sm font-medium mb-2">Branch Type</label>
        <div class="branch-types grid grid-cols-2 gap-2">
          <div
            v-for="type in branchTypes"
            :key="type.value"
            class="type-option p-3 border rounded-lg cursor-pointer"
            :class="{ 'selected': form.type === type.value }"
            @click="form.type = type.value"
          >
            <div class="flex items-center gap-2">
              <i :class="type.icon" class="text-lg"></i>
              <div>
                <div class="font-semibold">{{ type.label }}</div>
                <div class="text-xs text-gray-500">{{ type.description }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Base Branch -->
      <div class="field">
        <label class="block text-sm font-medium mb-2">Base Branch</label>
        <Dropdown
          v-model="form.baseBranch"
          :options="baseBranchOptions"
          optionLabel="label"
          optionValue="value"
          placeholder="Select base branch"
          class="w-full"
        />
        <small class="text-gray-500">The branch to create this new branch from</small>
      </div>

      <!-- Options -->
      <div class="options space-y-2">
        <div class="flex items-center gap-2">
          <Checkbox
            id="switch"
            v-model="form.switchTo"
          />
          <label for="switch" class="text-sm">Switch to new branch immediately</label>
        </div>

        <div class="flex items-center gap-2">
          <Checkbox
            id="copy-scenes"
            v-model="form.copyScenes"
          />
          <label for="copy-scenes" class="text-sm">Copy all scenes from base branch</label>
        </div>
      </div>

      <!-- Preview -->
      <div v-if="form.name && form.description" class="preview p-3 bg-blue-50 border border-blue-200 rounded-lg">
        <h4 class="font-semibold text-blue-800 mb-2">Branch Preview</h4>
        <div class="text-sm">
          <div class="flex items-center gap-2 mb-1">
            <i class="pi pi-code-branch text-blue-600"></i>
            <span class="font-mono">{{ form.name }}</span>
          </div>
          <div class="text-gray-600">{{ form.description }}</div>
          <div class="text-xs text-gray-500 mt-1">
            Based on: {{ form.baseBranch }} • Type: {{ selectedType?.label }}
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-between items-center">
        <div class="text-sm text-gray-500">
          <i class="pi pi-info-circle mr-1"></i>
          You can merge branches later to combine storylines
        </div>
        <div class="flex gap-2">
          <Button
            label="Cancel"
            icon="pi pi-times"
            @click="handleCancel"
            severity="secondary"
          />
          <Button
            label="Create Branch"
            icon="pi pi-plus"
            @click="handleCreate"
            :disabled="!canCreate"
            severity="success"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Dropdown from 'primevue/dropdown'
import Checkbox from 'primevue/checkbox'
import Button from 'primevue/button'

const props = defineProps({
  visible: Boolean,
  currentBranch: {
    type: String,
    default: 'main'
  },
  availableBranches: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:visible', 'create'])

const form = ref({
  name: '',
  description: '',
  type: 'feature',
  baseBranch: props.currentBranch,
  switchTo: true,
  copyScenes: true
})

const isValidBranchName = ref(true)

const branchTypes = [
  {
    value: 'feature',
    label: 'Feature',
    description: 'New scenes or storylines',
    icon: 'pi pi-plus-circle'
  },
  {
    value: 'alternative',
    label: 'Alternative',
    description: 'Different story direction',
    icon: 'pi pi-arrow-right-arrow-left'
  },
  {
    value: 'experiment',
    label: 'Experiment',
    description: 'Testing new techniques',
    icon: 'pi pi-bolt'
  },
  {
    value: 'fix',
    label: 'Fix',
    description: 'Corrections or improvements',
    icon: 'pi pi-wrench'
  }
]

const baseBranchOptions = computed(() => [
  { label: 'main', value: 'main' },
  { label: 'dark-ending', value: 'dark-ending' },
  { label: 'comedy-route', value: 'comedy-route' },
  // Add more from props.availableBranches if needed
])

const selectedType = computed(() => {
  return branchTypes.find(type => type.value === form.value.type)
})

const canCreate = computed(() => {
  return form.value.name &&
         form.value.description &&
         isValidBranchName.value &&
         form.value.baseBranch
})

const validateBranchName = () => {
  const name = form.value.name
  // Valid branch name: lowercase letters, numbers, dashes, underscores
  const validPattern = /^[a-z0-9-_]+$/
  isValidBranchName.value = !name || validPattern.test(name)
}

const handleCreate = () => {
  if (canCreate.value) {
    const branchData = {
      name: form.value.name,
      description: form.value.description,
      type: form.value.type,
      baseBranch: form.value.baseBranch,
      switchTo: form.value.switchTo,
      copyScenes: form.value.copyScenes
    }

    emit('create', branchData)
    resetForm()
  }
}

const handleCancel = () => {
  emit('update:visible', false)
  resetForm()
}

const resetForm = () => {
  form.value = {
    name: '',
    description: '',
    type: 'feature',
    baseBranch: props.currentBranch,
    switchTo: true,
    copyScenes: true
  }
  isValidBranchName.value = true
}
</script>

<style scoped>
.branch-form .field {
  margin-bottom: 1rem;
}

.type-option {
  transition: all 0.2s ease;
}

.type-option:hover {
  background: #f3f4f6;
  border-color: #9ca3af;
}

.type-option.selected {
  background: #eff6ff;
  border-color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
}

.preview {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>