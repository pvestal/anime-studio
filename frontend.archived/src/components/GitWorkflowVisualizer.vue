<template>
  <div class="git-workflow-visualizer">
    <!-- Header -->
    <div class="git-header">
      <h3>Git Workflow</h3>
      <div class="git-controls">
        <button @click="refreshData" class="control-button secondary" :disabled="loading">
          <i :class="loading ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'"></i>
          Refresh
        </button>
        <button @click="showNewBranchDialog = true" class="control-button primary">
          <i class="pi pi-plus"></i>
          New Branch
        </button>
        <button @click="performPull" class="control-button secondary" :disabled="pulling">
          <i :class="pulling ? 'pi pi-spin pi-spinner' : 'pi pi-download'"></i>
          Pull
        </button>
        <button @click="performPush" class="control-button secondary" :disabled="pushing || !hasUnpushedCommits">
          <i :class="pushing ? 'pi pi-spin pi-spinner' : 'pi pi-upload'"></i>
          Push
        </button>
      </div>
    </div>

    <!-- Branch Timeline View -->
    <div class="git-section">
      <div class="section-header">
        <h4>Branch Timeline</h4>
        <div class="view-toggle">
          <button @click="timelineView = 'visual'" :class="{ active: timelineView === 'visual' }" class="toggle-button">
            <i class="pi pi-sitemap"></i> Visual
          </button>
          <button @click="timelineView = 'list'" :class="{ active: timelineView === 'list' }" class="toggle-button">
            <i class="pi pi-list"></i> List
          </button>
        </div>
      </div>

      <!-- Visual Timeline -->
      <div v-if="timelineView === 'visual'" class="timeline-visual">
        <div class="branch-graph">
          <div
            v-for="branch in branches"
            :key="branch.name"
            :class="['branch-line', { active: branch.name === currentBranch, ahead: branch.ahead > 0, behind: branch.behind > 0 }]"
            @click="selectBranch(branch)"
          >
            <div class="branch-header">
              <div class="branch-info">
                <span class="branch-name">{{ branch.name }}</span>
                <span v-if="branch.name === currentBranch" class="current-indicator">CURRENT</span>
                <span v-if="branch.ahead > 0" class="ahead-indicator">+{{ branch.ahead }}</span>
                <span v-if="branch.behind > 0" class="behind-indicator">-{{ branch.behind }}</span>
              </div>
              <div class="branch-actions">
                <button @click.stop="checkoutBranch(branch)" class="mini-button" v-if="branch.name !== currentBranch">
                  <i class="pi pi-arrow-right"></i>
                </button>
                <button @click.stop="deleteBranch(branch)" class="mini-button danger" v-if="branch.name !== currentBranch && !branch.isRemote">
                  <i class="pi pi-trash"></i>
                </button>
              </div>
            </div>

            <!-- Commit nodes on branch -->
            <div class="commit-nodes">
              <div
                v-for="commit in branch.recentCommits"
                :key="commit.hash"
                :class="['commit-node', { merge: commit.isMerge, unpushed: !commit.isPushed }]"
                :title="`${commit.message} - ${commit.author} (${formatDate(commit.date)})`"
                @click.stop="selectCommit(commit)"
              >
                <div class="commit-dot"></div>
                <div class="commit-info">
                  <span class="commit-hash">{{ commit.hash.substring(0, 7) }}</span>
                  <span class="commit-message">{{ truncateMessage(commit.message) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- List Timeline -->
      <div v-if="timelineView === 'list'" class="timeline-list">
        <div class="branch-list">
          <div
            v-for="branch in branches"
            :key="branch.name"
            :class="['branch-item', { active: branch.name === currentBranch, selected: selectedBranch?.name === branch.name }]"
            @click="selectBranch(branch)"
          >
            <div class="branch-summary">
              <div class="branch-title">
                <i :class="branch.name === currentBranch ? 'pi pi-arrow-right' : 'pi pi-code-branch'"></i>
                {{ branch.name }}
                <span v-if="branch.isRemote" class="remote-badge">REMOTE</span>
              </div>
              <div class="branch-stats">
                <span class="commit-count">{{ branch.totalCommits }} commits</span>
                <span class="last-commit">{{ formatRelativeTime(branch.lastCommitDate) }}</span>
              </div>
            </div>
            <div class="branch-indicators">
              <span v-if="branch.ahead > 0" class="indicator ahead">↑{{ branch.ahead }}</span>
              <span v-if="branch.behind > 0" class="indicator behind">↓{{ branch.behind }}</span>
              <span v-if="branch.hasConflicts" class="indicator conflict">!</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Commit History -->
    <div class="git-section">
      <div class="section-header">
        <h4>Commit History</h4>
        <div class="history-controls">
          <select v-model="selectedBranchForHistory" class="branch-select">
            <option value="">All Branches</option>
            <option v-for="branch in branches" :key="branch.name" :value="branch.name">
              {{ branch.name }}
            </option>
          </select>
          <input
            v-model="commitSearch"
            placeholder="Search commits..."
            class="search-input"
          />
        </div>
      </div>

      <div class="commit-history">
        <div
          v-for="commit in filteredCommits"
          :key="commit.hash"
          :class="['commit-entry', { selected: selectedCommit?.hash === commit.hash, unpushed: !commit.isPushed }]"
          @click="selectCommit(commit)"
        >
          <div class="commit-avatar">
            <img v-if="commit.authorAvatar" :src="commit.authorAvatar" class="avatar-img" />
            <div v-else class="avatar-placeholder">{{ commit.author.charAt(0) }}</div>
          </div>

          <div class="commit-details">
            <div class="commit-title">
              <span class="commit-message">{{ commit.message }}</span>
              <span class="commit-hash">{{ commit.hash.substring(0, 7) }}</span>
            </div>
            <div class="commit-meta">
              <span class="commit-author">{{ commit.author }}</span>
              <span class="commit-date">{{ formatRelativeTime(commit.date) }}</span>
              <span v-if="commit.branch" class="commit-branch">{{ commit.branch }}</span>
            </div>
          </div>

          <div class="commit-stats">
            <span class="file-changes">
              <i class="pi pi-file"></i>
              {{ commit.filesChanged || 0 }}
            </span>
            <span class="additions">+{{ commit.additions || 0 }}</span>
            <span class="deletions">-{{ commit.deletions || 0 }}</span>
          </div>

          <div class="commit-actions">
            <button @click.stop="viewCommitDiff(commit)" class="action-button">
              <i class="pi pi-eye"></i>
            </button>
            <button @click.stop="revertCommit(commit)" class="action-button danger" v-if="commit.canRevert">
              <i class="pi pi-undo"></i>
            </button>
            <button @click.stop="cherryPickCommit(commit)" class="action-button" v-if="commit.branch !== currentBranch">
              <i class="pi pi-copy"></i>
            </button>
          </div>
        </div>

        <div v-if="filteredCommits.length === 0" class="no-commits">
          <i class="pi pi-info-circle"></i>
          No commits found matching your criteria
        </div>
      </div>
    </div>

    <!-- Merge Conflict Resolution -->
    <div v-if="mergeConflicts.length > 0" class="git-section">
      <div class="section-header">
        <h4>Merge Conflicts</h4>
        <div class="conflict-actions">
          <button @click="autoResolveConflicts" class="control-button secondary">
            <i class="pi pi-magic-wand"></i>
            Auto Resolve
          </button>
          <button @click="abortMerge" class="control-button danger">
            <i class="pi pi-times"></i>
            Abort Merge
          </button>
        </div>
      </div>

      <div class="conflict-list">
        <div v-for="conflict in mergeConflicts" :key="conflict.file" class="conflict-item">
          <div class="conflict-header">
            <span class="conflict-file">{{ conflict.file }}</span>
            <span class="conflict-type">{{ conflict.type }}</span>
          </div>
          <div class="conflict-preview">
            <div class="conflict-section">
              <span class="section-label">OURS:</span>
              <code class="conflict-code">{{ conflict.oursContent }}</code>
            </div>
            <div class="conflict-section">
              <span class="section-label">THEIRS:</span>
              <code class="conflict-code">{{ conflict.theirsContent }}</code>
            </div>
          </div>
          <div class="conflict-actions">
            <button @click="resolveConflict(conflict, 'ours')" class="resolve-button">
              Accept Ours
            </button>
            <button @click="resolveConflict(conflict, 'theirs')" class="resolve-button">
              Accept Theirs
            </button>
            <button @click="editConflict(conflict)" class="resolve-button">
              Manual Edit
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- New Branch Dialog -->
    <div v-if="showNewBranchDialog" class="dialog-overlay" @click="showNewBranchDialog = false">
      <div class="branch-dialog" @click.stop>
        <div class="dialog-header">
          <h4>Create New Branch</h4>
          <button @click="showNewBranchDialog = false" class="close-button">
            <i class="pi pi-times"></i>
          </button>
        </div>

        <div class="dialog-content">
          <div class="form-group">
            <label>Branch Name</label>
            <input v-model="newBranchName" class="form-input" placeholder="feature/new-feature" />
          </div>

          <div class="form-group">
            <label>Branch From</label>
            <select v-model="branchFrom" class="form-select">
              <option v-for="branch in branches" :key="branch.name" :value="branch.name">
                {{ branch.name }}
              </option>
            </select>
          </div>
        </div>

        <div class="dialog-actions">
          <button @click="showNewBranchDialog = false" class="dialog-button secondary">Cancel</button>
          <button @click="createNewBranch" class="dialog-button primary" :disabled="!newBranchName">Create</button>
        </div>
      </div>
    </div>

    <!-- Commit Diff Modal -->
    <div v-if="showCommitDiff" class="dialog-overlay" @click="showCommitDiff = false">
      <div class="diff-dialog" @click.stop>
        <div class="dialog-header">
          <h4>Commit {{ selectedCommit?.hash?.substring(0, 7) }}</h4>
          <button @click="showCommitDiff = false" class="close-button">
            <i class="pi pi-times"></i>
          </button>
        </div>

        <div class="dialog-content">
          <div class="commit-diff-content">
            <pre v-if="commitDiff" class="diff-text">{{ commitDiff }}</pre>
            <div v-else class="loading-diff">
              <i class="pi pi-spin pi-spinner"></i>
              Loading diff...
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive, computed, onMounted, watch } from 'vue'

export default {
  name: 'GitWorkflowVisualizer',
  setup() {
    const loading = ref(false)
    const pulling = ref(false)
    const pushing = ref(false)
    const timelineView = ref('visual')
    const branches = ref([])
    const commits = ref([])
    const currentBranch = ref('')
    const selectedBranch = ref(null)
    const selectedCommit = ref(null)
    const selectedBranchForHistory = ref('')
    const commitSearch = ref('')
    const mergeConflicts = ref([])
    const showNewBranchDialog = ref(false)
    const showCommitDiff = ref(false)
    const commitDiff = ref('')
    const newBranchName = ref('')
    const branchFrom = ref('main')

    // Computed properties
    const filteredCommits = computed(() => {
      let filtered = commits.value

      if (selectedBranchForHistory.value) {
        filtered = filtered.filter(commit => commit.branch === selectedBranchForHistory.value)
      }

      if (commitSearch.value) {
        const search = commitSearch.value.toLowerCase()
        filtered = filtered.filter(commit =>
          commit.message.toLowerCase().includes(search) ||
          commit.author.toLowerCase().includes(search) ||
          commit.hash.toLowerCase().includes(search)
        )
      }

      return filtered.sort((a, b) => new Date(b.date) - new Date(a.date))
    })

    const hasUnpushedCommits = computed(() => {
      return commits.value.some(commit => !commit.isPushed)
    })

    // Methods
    const loadBranches = async () => {
      try {
        const response = await fetch('/api/git/branches')
        if (response.ok) {
          branches.value = await response.json()
        }
      } catch (error) {
        console.error('Failed to load branches:', error)
      }
    }

    const loadCommits = async () => {
      try {
        const response = await fetch('/api/git/commits')
        if (response.ok) {
          commits.value = await response.json()
        }
      } catch (error) {
        console.error('Failed to load commits:', error)
      }
    }

    const loadCurrentBranch = async () => {
      try {
        const response = await fetch('/api/git/current-branch')
        if (response.ok) {
          const data = await response.json()
          currentBranch.value = data.branch
        }
      } catch (error) {
        console.error('Failed to load current branch:', error)
      }
    }

    const loadMergeConflicts = async () => {
      try {
        const response = await fetch('/api/git/conflicts')
        if (response.ok) {
          mergeConflicts.value = await response.json()
        }
      } catch (error) {
        console.error('Failed to load merge conflicts:', error)
      }
    }

    const refreshData = async () => {
      loading.value = true
      try {
        await Promise.all([
          loadBranches(),
          loadCommits(),
          loadCurrentBranch(),
          loadMergeConflicts()
        ])
      } finally {
        loading.value = false
      }
    }

    const selectBranch = (branch) => {
      selectedBranch.value = branch
    }

    const selectCommit = (commit) => {
      selectedCommit.value = commit
    }

    const checkoutBranch = async (branch) => {
      try {
        const response = await fetch('/api/git/checkout', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ branch: branch.name })
        })

        if (response.ok) {
          await refreshData()
        } else {
          const error = await response.json()
          console.error('Failed to checkout branch:', error.message)
        }
      } catch (error) {
        console.error('Failed to checkout branch:', error)
      }
    }

    const deleteBranch = async (branch) => {
      if (!confirm(`Delete branch "${branch.name}"?`)) return

      try {
        const response = await fetch(`/api/git/branches/${branch.name}`, {
          method: 'DELETE'
        })

        if (response.ok) {
          await refreshData()
        } else {
          const error = await response.json()
          console.error('Failed to delete branch:', error.message)
        }
      } catch (error) {
        console.error('Failed to delete branch:', error)
      }
    }

    const createNewBranch = async () => {
      try {
        const response = await fetch('/api/git/branches', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: newBranchName.value,
            from: branchFrom.value
          })
        })

        if (response.ok) {
          showNewBranchDialog.value = false
          newBranchName.value = ''
          await refreshData()
        } else {
          const error = await response.json()
          console.error('Failed to create branch:', error.message)
        }
      } catch (error) {
        console.error('Failed to create branch:', error)
      }
    }

    const performPull = async () => {
      pulling.value = true
      try {
        const response = await fetch('/api/git/pull', {
          method: 'POST'
        })

        if (response.ok) {
          await refreshData()
        } else {
          const error = await response.json()
          console.error('Failed to pull:', error.message)
        }
      } catch (error) {
        console.error('Failed to pull:', error)
      } finally {
        pulling.value = false
      }
    }

    const performPush = async () => {
      pushing.value = true
      try {
        const response = await fetch('/api/git/push', {
          method: 'POST'
        })

        if (response.ok) {
          await refreshData()
        } else {
          const error = await response.json()
          console.error('Failed to push:', error.message)
        }
      } catch (error) {
        console.error('Failed to push:', error)
      } finally {
        pushing.value = false
      }
    }

    const viewCommitDiff = async (commit) => {
      selectedCommit.value = commit
      showCommitDiff.value = true
      commitDiff.value = ''

      try {
        const response = await fetch(`/api/git/commits/${commit.hash}/diff`)
        if (response.ok) {
          commitDiff.value = await response.text()
        }
      } catch (error) {
        console.error('Failed to load commit diff:', error)
        commitDiff.value = 'Failed to load diff'
      }
    }

    const revertCommit = async (commit) => {
      if (!confirm(`Revert commit "${commit.message}"?`)) return

      try {
        const response = await fetch(`/api/git/commits/${commit.hash}/revert`, {
          method: 'POST'
        })

        if (response.ok) {
          await refreshData()
        } else {
          const error = await response.json()
          console.error('Failed to revert commit:', error.message)
        }
      } catch (error) {
        console.error('Failed to revert commit:', error)
      }
    }

    const cherryPickCommit = async (commit) => {
      try {
        const response = await fetch(`/api/git/commits/${commit.hash}/cherry-pick`, {
          method: 'POST'
        })

        if (response.ok) {
          await refreshData()
        } else {
          const error = await response.json()
          console.error('Failed to cherry-pick commit:', error.message)
        }
      } catch (error) {
        console.error('Failed to cherry-pick commit:', error)
      }
    }

    const resolveConflict = async (conflict, resolution) => {
      try {
        const response = await fetch('/api/git/resolve-conflict', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file: conflict.file,
            resolution
          })
        })

        if (response.ok) {
          await loadMergeConflicts()
        } else {
          const error = await response.json()
          console.error('Failed to resolve conflict:', error.message)
        }
      } catch (error) {
        console.error('Failed to resolve conflict:', error)
      }
    }

    const autoResolveConflicts = async () => {
      try {
        const response = await fetch('/api/git/auto-resolve-conflicts', {
          method: 'POST'
        })

        if (response.ok) {
          await loadMergeConflicts()
        } else {
          const error = await response.json()
          console.error('Failed to auto-resolve conflicts:', error.message)
        }
      } catch (error) {
        console.error('Failed to auto-resolve conflicts:', error)
      }
    }

    const abortMerge = async () => {
      if (!confirm('Abort the current merge? This will reset to the previous state.')) return

      try {
        const response = await fetch('/api/git/abort-merge', {
          method: 'POST'
        })

        if (response.ok) {
          await refreshData()
        } else {
          const error = await response.json()
          console.error('Failed to abort merge:', error.message)
        }
      } catch (error) {
        console.error('Failed to abort merge:', error)
      }
    }

    const editConflict = (conflict) => {
      // This would open an external editor or in-app editor
      console.log('Edit conflict:', conflict.file)
    }

    // Utility functions
    const formatDate = (dateString) => {
      return new Date(dateString).toLocaleDateString()
    }

    const formatRelativeTime = (dateString) => {
      const date = new Date(dateString)
      const now = new Date()
      const diffMs = now - date
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

      if (diffDays === 0) return 'Today'
      if (diffDays === 1) return 'Yesterday'
      if (diffDays < 7) return `${diffDays} days ago`
      if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`
      return formatDate(dateString)
    }

    const truncateMessage = (message) => {
      return message.length > 50 ? message.substring(0, 47) + '...' : message
    }

    // Lifecycle
    onMounted(() => {
      refreshData()

      // Auto-refresh every 30 seconds
      setInterval(refreshData, 30000)
    })

    return {
      loading,
      pulling,
      pushing,
      timelineView,
      branches,
      commits,
      currentBranch,
      selectedBranch,
      selectedCommit,
      selectedBranchForHistory,
      commitSearch,
      mergeConflicts,
      showNewBranchDialog,
      showCommitDiff,
      commitDiff,
      newBranchName,
      branchFrom,
      filteredCommits,
      hasUnpushedCommits,
      refreshData,
      selectBranch,
      selectCommit,
      checkoutBranch,
      deleteBranch,
      createNewBranch,
      performPull,
      performPush,
      viewCommitDiff,
      revertCommit,
      cherryPickCommit,
      resolveConflict,
      autoResolveConflicts,
      abortMerge,
      editConflict,
      formatDate,
      formatRelativeTime,
      truncateMessage
    }
  }
}
</script>

<style scoped>
.git-workflow-visualizer {
  background: #0f0f0f;
  border: 1px solid #333;
  border-radius: 8px;
  color: #e0e0e0;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.git-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid #333;
}

.git-header h3 {
  margin: 0;
  color: #3b82f6;
  font-size: 1.2rem;
}

.git-controls {
  display: flex;
  gap: 0.5rem;
}

.control-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border: 1px solid #333;
  border-radius: 4px;
  font-family: inherit;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.control-button.primary {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.control-button.primary:hover {
  background: #2563eb;
}

.control-button.secondary {
  background: #1a1a1a;
  color: #e0e0e0;
}

.control-button.secondary:hover {
  background: #333;
}

.control-button.danger {
  background: #ef4444;
  color: white;
  border-color: #ef4444;
}

.control-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.git-section {
  margin-bottom: 1.5rem;
  border-bottom: 1px solid #222;
  padding-bottom: 1rem;
}

.git-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding: 0 1rem;
}

.section-header h4 {
  margin: 0;
  color: #3b82f6;
  font-size: 1.1rem;
}

.view-toggle {
  display: flex;
  gap: 0.25rem;
}

.toggle-button {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.8rem;
}

.toggle-button:hover {
  background: #333;
}

.toggle-button.active {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.timeline-visual {
  padding: 0 1rem;
}

.branch-graph {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.branch-line {
  border: 1px solid #333;
  border-radius: 4px;
  padding: 0.75rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.branch-line:hover {
  background: #1a1a1a;
}

.branch-line.active {
  border-color: #3b82f6;
  background: rgba(59, 130, 246, 0.1);
}

.branch-line.ahead {
  border-left: 3px solid #10b981;
}

.branch-line.behind {
  border-left: 3px solid #f59e0b;
}

.branch-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.branch-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.branch-name {
  font-weight: 600;
  color: #e0e0e0;
}

.current-indicator {
  padding: 0.125rem 0.5rem;
  background: #3b82f6;
  color: white;
  border-radius: 12px;
  font-size: 0.75rem;
}

.ahead-indicator {
  padding: 0.125rem 0.5rem;
  background: #10b981;
  color: white;
  border-radius: 12px;
  font-size: 0.75rem;
}

.behind-indicator {
  padding: 0.125rem 0.5rem;
  background: #f59e0b;
  color: white;
  border-radius: 12px;
  font-size: 0.75rem;
}

.branch-actions {
  display: flex;
  gap: 0.25rem;
}

.mini-button {
  padding: 0.25rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
}

.mini-button:hover {
  background: #333;
}

.mini-button.danger:hover {
  background: #ef4444;
  border-color: #ef4444;
}

.commit-nodes {
  display: flex;
  gap: 0.75rem;
  overflow-x: auto;
  padding: 0.5rem 0;
}

.commit-node {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 200px;
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  cursor: pointer;
}

.commit-node:hover {
  background: #333;
}

.commit-node.merge {
  border-color: #8b5cf6;
}

.commit-node.unpushed {
  border-color: #f59e0b;
}

.commit-dot {
  width: 8px;
  height: 8px;
  background: #3b82f6;
  border-radius: 50%;
  flex-shrink: 0;
}

.commit-info {
  flex: 1;
  min-width: 0;
}

.commit-hash {
  font-family: monospace;
  color: #999;
  font-size: 0.8rem;
}

.commit-message {
  display: block;
  font-size: 0.9rem;
  color: #e0e0e0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.timeline-list {
  padding: 0 1rem;
}

.branch-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.branch-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.branch-item:hover {
  background: #333;
}

.branch-item.active {
  border-color: #3b82f6;
  background: rgba(59, 130, 246, 0.1);
}

.branch-item.selected {
  background: #333;
}

.branch-summary {
  flex: 1;
}

.branch-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  color: #e0e0e0;
  margin-bottom: 0.25rem;
}

.remote-badge {
  padding: 0.125rem 0.5rem;
  background: #6b7280;
  color: white;
  border-radius: 12px;
  font-size: 0.75rem;
}

.branch-stats {
  display: flex;
  gap: 1rem;
  font-size: 0.8rem;
  color: #999;
}

.branch-indicators {
  display: flex;
  gap: 0.5rem;
}

.indicator {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 600;
}

.indicator.ahead {
  background: #10b981;
  color: white;
}

.indicator.behind {
  background: #f59e0b;
  color: white;
}

.indicator.conflict {
  background: #ef4444;
  color: white;
}

.history-controls {
  display: flex;
  gap: 0.75rem;
}

.branch-select, .search-input {
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  font-family: inherit;
}

.search-input {
  width: 200px;
}

.commit-history {
  max-height: 400px;
  overflow-y: auto;
  padding: 0 1rem;
}

.commit-entry {
  display: flex;
  gap: 0.75rem;
  padding: 0.75rem;
  border: 1px solid #333;
  border-radius: 4px;
  margin-bottom: 0.5rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.commit-entry:hover {
  background: #1a1a1a;
}

.commit-entry.selected {
  background: #1a1a1a;
  border-color: #3b82f6;
}

.commit-entry.unpushed {
  border-left: 3px solid #f59e0b;
}

.commit-avatar {
  flex-shrink: 0;
}

.avatar-img {
  width: 32px;
  height: 32px;
  border-radius: 50%;
}

.avatar-placeholder {
  width: 32px;
  height: 32px;
  background: #333;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  color: #3b82f6;
}

.commit-details {
  flex: 1;
  min-width: 0;
}

.commit-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.25rem;
}

.commit-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.8rem;
  color: #999;
}

.commit-stats {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8rem;
}

.file-changes {
  color: #3b82f6;
}

.additions {
  color: #10b981;
}

.deletions {
  color: #ef4444;
}

.commit-actions {
  display: flex;
  gap: 0.25rem;
}

.action-button {
  padding: 0.25rem;
  background: none;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
}

.action-button:hover {
  background: #333;
}

.action-button.danger:hover {
  background: #ef4444;
  border-color: #ef4444;
}

.no-commits {
  text-align: center;
  padding: 2rem;
  color: #999;
  font-style: italic;
}

.conflict-list {
  padding: 0 1rem;
}

.conflict-item {
  background: #1a1a1a;
  border: 1px solid #ef4444;
  border-radius: 4px;
  padding: 1rem;
  margin-bottom: 1rem;
}

.conflict-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.conflict-file {
  font-weight: 600;
  color: #e0e0e0;
}

.conflict-type {
  padding: 0.25rem 0.5rem;
  background: #ef4444;
  color: white;
  border-radius: 4px;
  font-size: 0.8rem;
}

.conflict-preview {
  margin-bottom: 0.75rem;
}

.conflict-section {
  margin-bottom: 0.5rem;
}

.section-label {
  display: block;
  font-weight: 600;
  color: #3b82f6;
  margin-bottom: 0.25rem;
}

.conflict-code {
  display: block;
  background: #0f0f0f;
  padding: 0.5rem;
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.9rem;
  color: #e0e0e0;
  white-space: pre-wrap;
}

.conflict-actions {
  display: flex;
  gap: 0.5rem;
}

.resolve-button {
  padding: 0.5rem 1rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
  font-family: inherit;
}

.resolve-button:hover {
  background: #333;
}

.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.branch-dialog, .diff-dialog {
  background: #0f0f0f;
  border: 1px solid #333;
  border-radius: 8px;
  width: 500px;
  max-width: 90vw;
  max-height: 90vh;
  overflow-y: auto;
}

.diff-dialog {
  width: 80vw;
  height: 80vh;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid #333;
}

.dialog-header h4 {
  margin: 0;
  color: #3b82f6;
}

.close-button {
  padding: 0.5rem;
  background: none;
  border: none;
  color: #e0e0e0;
  cursor: pointer;
}

.dialog-content {
  padding: 1rem;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 600;
  color: #3b82f6;
}

.form-input, .form-select {
  width: 100%;
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  font-family: inherit;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem;
  border-top: 1px solid #333;
}

.dialog-button {
  padding: 0.75rem 1rem;
  border: 1px solid #333;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
}

.dialog-button.primary {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.dialog-button.secondary {
  background: #1a1a1a;
  color: #e0e0e0;
}

.dialog-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.commit-diff-content {
  height: 60vh;
  overflow-y: auto;
}

.diff-text {
  font-family: monospace;
  font-size: 0.9rem;
  line-height: 1.4;
  white-space: pre-wrap;
  color: #e0e0e0;
}

.loading-diff {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: #999;
}
</style>