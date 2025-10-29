<template>
  <div class="git-interface">
    <!-- Command Input -->
    <div class="command-section mb-6">
      <div class="flex items-center gap-3 mb-3">
        <i class="pi pi-git text-2xl text-gray-600"></i>
        <h2 class="text-xl font-bold">Project Git Control</h2>
        <Tag :value="currentProject.name" severity="info" />
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- Quick Actions -->
        <Card class="quick-actions">
          <template #title>Quick Actions</template>
          <template #content>
            <div class="grid grid-cols-2 gap-2">
              <Button
                label="Commit Scene"
                icon="pi pi-save"
                @click="openCommitDialog"
                :disabled="!hasChanges"
                class="w-full"
              />
              <Button
                label="New Branch"
                icon="pi pi-plus"
                @click="openBranchDialog"
                severity="info"
                class="w-full"
              />
              <Button
                label="Merge Branch"
                icon="pi pi-arrow-right"
                @click="openMergeDialog"
                :disabled="availableBranches.length < 2"
                severity="success"
                class="w-full"
              />
              <Button
                label="View History"
                icon="pi pi-history"
                @click="showHistory = true"
                severity="secondary"
                class="w-full"
              />
            </div>
          </template>
        </Card>

        <!-- Current Status -->
        <Card class="status-card">
          <template #title>Current Status</template>
          <template #content>
            <div class="status-info space-y-2">
              <div class="flex justify-between">
                <span>Branch:</span>
                <Tag :value="currentBranch" severity="info" />
              </div>
              <div class="flex justify-between">
                <span>Last Commit:</span>
                <span class="text-sm font-mono">{{ lastCommit.hash.substring(0, 8) }}</span>
              </div>
              <div class="flex justify-between">
                <span>Changes:</span>
                <Tag
                  :value="hasChanges ? 'Modified' : 'Clean'"
                  :severity="hasChanges ? 'warning' : 'success'"
                />
              </div>
              <div class="flex justify-between">
                <span>Queue:</span>
                <span class="text-sm">{{ renderQueue.length }} pending</span>
              </div>
            </div>
          </template>
        </Card>
      </div>
    </div>

    <!-- Branch Visualization -->
    <Card class="branch-viz mb-6">
      <template #title>Project Branches</template>
      <template #content>
        <div class="branch-tree">
          <div
            v-for="branch in availableBranches"
            :key="branch.name"
            class="branch-item"
            :class="{ 'current': branch.name === currentBranch }"
          >
            <div class="flex items-center justify-between p-3 border rounded-lg">
              <div class="flex items-center gap-3">
                <i class="pi pi-code-branch" :class="branch.name === currentBranch ? 'text-blue-600' : 'text-gray-400'"></i>
                <div>
                  <span class="font-semibold">{{ branch.name }}</span>
                  <div class="text-sm text-gray-500">{{ branch.description }}</div>
                  <div class="text-xs text-gray-400">
                    {{ formatDate(branch.lastCommit) }} • {{ branch.commits }} commits
                  </div>
                </div>
              </div>
              <div class="flex gap-2">
                <Button
                  v-if="branch.name !== currentBranch"
                  icon="pi pi-arrow-right"
                  @click="switchBranch(branch.name)"
                  size="small"
                  severity="secondary"
                  v-tooltip="'Switch to branch'"
                />
                <Button
                  v-if="branch.name !== 'main'"
                  icon="pi pi-trash"
                  @click="deleteBranch(branch.name)"
                  size="small"
                  severity="danger"
                  v-tooltip="'Delete branch'"
                />
              </div>
            </div>
          </div>
        </div>
      </template>
    </Card>

    <!-- Command History -->
    <Card v-if="showHistory" class="history-card mb-6">
      <template #title>
        <div class="flex justify-between items-center">
          <span>Commit History</span>
          <Button
            icon="pi pi-times"
            @click="showHistory = false"
            size="small"
            severity="secondary"
            text
          />
        </div>
      </template>
      <template #content>
        <div class="commit-history">
          <div
            v-for="commit in commitHistory"
            :key="commit.hash"
            class="commit-item p-3 border-l-4 border-gray-300 mb-3"
          >
            <div class="flex justify-between items-start">
              <div>
                <div class="font-semibold">{{ commit.message }}</div>
                <div class="text-sm text-gray-600">
                  by {{ commit.author }} • {{ formatDate(commit.timestamp) }}
                </div>
                <div class="text-xs font-mono text-gray-400">{{ commit.hash }}</div>
              </div>
              <div class="flex gap-2">
                <Button
                  label="Revert"
                  icon="pi pi-undo"
                  @click="revertToCommit(commit.hash)"
                  size="small"
                  severity="warning"
                />
                <Button
                  label="View"
                  icon="pi pi-eye"
                  @click="viewCommit(commit.hash)"
                  size="small"
                  severity="secondary"
                />
              </div>
            </div>
          </div>
        </div>
      </template>
    </Card>

    <!-- Dialogs -->
    <CommitDialog
      v-model:visible="showCommitDialog"
      :scene-data="currentSceneData"
      @commit="handleCommit"
    />

    <BranchDialog
      v-model:visible="showBranchDialog"
      :current-branch="currentBranch"
      @create="handleCreateBranch"
    />

    <MergeDialog
      v-model:visible="showMergeDialog"
      :available-branches="availableBranches.filter(b => b.name !== currentBranch)"
      :current-branch="currentBranch"
      @merge="handleMerge"
    />

    <!-- Toast for notifications -->
    <Toast />
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import Card from 'primevue/card'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'

// Child components (will create these next)
import CommitDialog from './CommitDialog.vue'
import BranchDialog from './BranchDialog.vue'
import MergeDialog from './MergeDialog.vue'

const toast = useToast()

// Project state
const currentProject = ref({ name: 'My Anime Project' })
const currentBranch = ref('main')
const hasChanges = ref(false)
const renderQueue = ref([])

const availableBranches = ref([
  {
    name: 'main',
    description: 'Main storyline',
    lastCommit: new Date(),
    commits: 15,
    scenes: 8
  },
  {
    name: 'dark-ending',
    description: 'Alternative darker conclusion',
    lastCommit: new Date(Date.now() - 86400000),
    commits: 5,
    scenes: 3
  },
  {
    name: 'comedy-route',
    description: 'Lighter comedic version',
    lastCommit: new Date(Date.now() - 172800000),
    commits: 8,
    scenes: 6
  }
])

const commitHistory = ref([
  {
    hash: 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0',
    message: 'Add epic battle scene with synchronized music',
    author: 'Patrick',
    timestamp: new Date(),
    branch: 'main',
    cost: 12.45
  },
  {
    hash: 'b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0a1',
    message: 'Enhance character animations for emotional scene',
    author: 'Patrick',
    timestamp: new Date(Date.now() - 3600000),
    branch: 'main',
    cost: 8.20
  },
  {
    hash: 'c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0a1b2',
    message: 'Create alternative dark ending branch',
    author: 'Patrick',
    timestamp: new Date(Date.now() - 86400000),
    branch: 'dark-ending',
    cost: 15.60
  }
])

const lastCommit = computed(() => commitHistory.value[0] || { hash: 'initial' })
const currentSceneData = ref({})

// Dialog states
const showCommitDialog = ref(false)
const showBranchDialog = ref(false)
const showMergeDialog = ref(false)
const showHistory = ref(false)

// Methods
const openCommitDialog = () => {
  loadCurrentSceneData()
  showCommitDialog.value = true
}

const openBranchDialog = () => {
  showBranchDialog.value = true
}

const openMergeDialog = () => {
  showMergeDialog.value = true
}

const loadCurrentSceneData = async () => {
  try {
    const response = await fetch(`/api/anime/projects/${currentProject.value.id}/current-scene`)
    if (response.ok) {
      currentSceneData.value = await response.json()
    }
  } catch (error) {
    console.error('Failed to load scene data:', error)
  }
}

const handleCommit = async (commitData) => {
  try {
    const response = await fetch('/api/anime/git/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        projectId: currentProject.value.id,
        branch: currentBranch.value,
        message: commitData.message,
        sceneData: currentSceneData.value,
        renderConfig: commitData.renderConfig
      })
    })

    if (response.ok) {
      const result = await response.json()

      // Add to history
      commitHistory.value.unshift({
        hash: result.commitHash,
        message: commitData.message,
        author: 'Patrick',
        timestamp: new Date(),
        branch: currentBranch.value,
        cost: result.estimatedCost || 0
      })

      hasChanges.value = false
      toast.add({
        severity: 'success',
        summary: 'Scene Committed',
        detail: `Committed to ${currentBranch.value}: ${commitData.message}`,
        life: 3000
      })

      // If render approved, start the process
      if (commitData.shouldRender) {
        startRender(result.commitHash, commitData.renderConfig)
      }
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Commit Failed',
      detail: error.message,
      life: 5000
    })
  }
}

const handleCreateBranch = async (branchData) => {
  try {
    const response = await fetch('/api/anime/git/branch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        projectId: currentProject.value.id,
        name: branchData.name,
        description: branchData.description,
        baseBranch: currentBranch.value
      })
    })

    if (response.ok) {
      availableBranches.value.push({
        name: branchData.name,
        description: branchData.description,
        lastCommit: new Date(),
        commits: 0,
        scenes: 0
      })

      if (branchData.switchTo) {
        currentBranch.value = branchData.name
      }

      toast.add({
        severity: 'success',
        summary: 'Branch Created',
        detail: `New branch "${branchData.name}" created`,
        life: 3000
      })
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Branch Creation Failed',
      detail: error.message,
      life: 5000
    })
  }
}

const handleMerge = async (mergeData) => {
  try {
    const response = await fetch('/api/anime/git/merge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        projectId: currentProject.value.id,
        targetBranch: currentBranch.value,
        sourceBranch: mergeData.sourceBranch,
        strategy: mergeData.strategy
      })
    })

    if (response.ok) {
      const result = await response.json()

      if (result.conflicts) {
        // Handle conflicts (will integrate with MergeConflictResolver)
        toast.add({
          severity: 'warn',
          summary: 'Merge Conflicts',
          detail: `${result.conflicts.length} conflicts need resolution`,
          life: 5000
        })
      } else {
        toast.add({
          severity: 'success',
          summary: 'Merge Complete',
          detail: `Successfully merged ${mergeData.sourceBranch} into ${currentBranch.value}`,
          life: 3000
        })
      }
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Merge Failed',
      detail: error.message,
      life: 5000
    })
  }
}

const switchBranch = async (branchName) => {
  try {
    const response = await fetch('/api/anime/git/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        projectId: currentProject.value.id,
        branch: branchName
      })
    })

    if (response.ok) {
      currentBranch.value = branchName
      toast.add({
        severity: 'info',
        summary: 'Branch Switched',
        detail: `Now on branch: ${branchName}`,
        life: 3000
      })

      // Reload data for new branch
      loadProjectData()
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Branch Switch Failed',
      detail: error.message,
      life: 5000
    })
  }
}

const deleteBranch = async (branchName) => {
  if (confirm(`Are you sure you want to delete branch "${branchName}"? This cannot be undone.`)) {
    try {
      const response = await fetch(`/api/anime/git/branch/${branchName}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          projectId: currentProject.value.id
        })
      })

      if (response.ok) {
        availableBranches.value = availableBranches.value.filter(b => b.name !== branchName)
        toast.add({
          severity: 'success',
          summary: 'Branch Deleted',
          detail: `Branch "${branchName}" has been deleted`,
          life: 3000
        })
      }
    } catch (error) {
      toast.add({
        severity: 'error',
        summary: 'Delete Failed',
        detail: error.message,
        life: 5000
      })
    }
  }
}

const revertToCommit = async (commitHash) => {
  if (confirm(`Revert to commit ${commitHash.substring(0, 8)}? This will undo all changes after this commit.`)) {
    try {
      const response = await fetch('/api/anime/git/revert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          projectId: currentProject.value.id,
          branch: currentBranch.value,
          commitHash
        })
      })

      if (response.ok) {
        toast.add({
          severity: 'success',
          summary: 'Reverted',
          detail: `Reverted to commit ${commitHash.substring(0, 8)}`,
          life: 3000
        })
        loadProjectData()
      }
    } catch (error) {
      toast.add({
        severity: 'error',
        summary: 'Revert Failed',
        detail: error.message,
        life: 5000
      })
    }
  }
}

const viewCommit = (commitHash) => {
  // Open commit detail view
  window.open(`/commit/${commitHash}`, '_blank')
}

const startRender = async (commitHash, renderConfig) => {
  renderQueue.value.push({
    commitHash,
    config: renderConfig,
    status: 'pending',
    startTime: new Date()
  })

  // This would integrate with your existing render system
  toast.add({
    severity: 'info',
    summary: 'Render Started',
    detail: 'Scene render added to queue',
    life: 3000
  })
}

const loadProjectData = async () => {
  // Load project data, branches, commits, etc.
  try {
    const response = await fetch(`/api/anime/projects/${currentProject.value.id}/git-status`)
    if (response.ok) {
      const data = await response.json()
      currentBranch.value = data.currentBranch
      hasChanges.value = data.hasChanges
      availableBranches.value = data.branches
      commitHistory.value = data.commits
    }
  } catch (error) {
    console.error('Failed to load project data:', error)
  }
}

const formatDate = (date) => {
  return new Intl.RelativeTimeFormatter('en', { numeric: 'auto' }).format(
    Math.ceil((date - new Date()) / (1000 * 60 * 60 * 24)),
    'day'
  )
}

onMounted(() => {
  loadProjectData()

  // Simulate some changes for demo
  setTimeout(() => {
    hasChanges.value = true
  }, 2000)
})
</script>

<style scoped>
.git-interface {
  max-width: 1200px;
  margin: 0 auto;
  padding: 1rem;
}

.branch-item.current {
  background: linear-gradient(to right, #eff6ff, #dbeafe);
  border-color: #3b82f6;
}

.commit-item {
  transition: all 0.2s ease;
}

.commit-item:hover {
  background: #f9fafb;
  border-left-color: #3b82f6;
}

.status-info > div {
  padding: 0.25rem 0;
}

.branch-tree {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

@media (max-width: 768px) {
  .grid-cols-2 {
    grid-template-columns: 1fr;
  }
}
</style>