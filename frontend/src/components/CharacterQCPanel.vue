<template>
  <div class="character-qc-panel">
    <div class="qc-header">
      <h3>Quality Control Dashboard</h3>
      <div class="qc-status">
        <span :class="['status-indicator', qcStatus]"></span>
        <span>{{ qcStatusText }}</span>
      </div>
    </div>

    <!-- Consistency Metrics -->
    <div class="metrics-section" v-if="metrics">
      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-value">{{ metrics.approval_rate }}%</div>
          <div class="metric-label">Approval Rate</div>
        </div>
        <div class="metric-card">
          <div class="metric-value">{{ metrics.average_consistency }}</div>
          <div class="metric-label">Avg Consistency</div>
        </div>
        <div class="metric-card">
          <div class="metric-value">{{ metrics.total_generations }}</div>
          <div class="metric-label">Total Generated</div>
        </div>
        <div class="metric-card">
          <div class="metric-value">{{ metrics.approved }}</div>
          <div class="metric-label">Approved</div>
        </div>
      </div>

      <!-- Recommendations -->
      <div class="recommendations" v-if="recommendations.length > 0">
        <h4>QC Recommendations</h4>
        <ul>
          <li v-for="(rec, index) in recommendations" :key="index">
            <i class="pi pi-info-circle"></i> {{ rec }}
          </li>
        </ul>
      </div>
    </div>

    <!-- QC Queue -->
    <div class="qc-queue-section">
      <h4>Pending Approval ({{ qcQueue.length }})</h4>

      <div v-if="qcQueue.length === 0" class="empty-queue">
        <i class="pi pi-check-circle"></i>
        <p>No generations pending approval</p>
      </div>

      <div v-else class="qc-queue">
        <div
          v-for="item in qcQueue"
          :key="item.generation_id"
          class="qc-item"
        >
          <div class="qc-item-preview">
            <img
              :src="item.preview_url || '/placeholder.jpg'"
              :alt="`Generation ${item.generation_id}`"
              @click="showPreview(item)"
            />
          </div>

          <div class="qc-item-details">
            <div class="generation-prompt">{{ item.prompt }}</div>
            <div class="generation-meta">
              <span>Consistency: {{ (item.consistency * 100).toFixed(1) }}%</span>
              <span>{{ formatDate(item.created_at) }}</span>
            </div>
          </div>

          <div class="qc-actions">
            <button
              class="btn-approve"
              @click="approveGeneration(item)"
              :disabled="processing"
            >
              <i class="pi pi-check"></i>
              Approve
            </button>
            <button
              class="btn-reject"
              @click="showRejectDialog(item)"
              :disabled="processing"
            >
              <i class="pi pi-times"></i>
              Reject
            </button>
            <button
              class="btn-regenerate"
              @click="regenerate(item)"
              :disabled="processing"
            >
              <i class="pi pi-refresh"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Recent Approvals -->
    <div class="recent-approvals-section" v-if="recentApprovals.length > 0">
      <h4>Recent Approvals</h4>
      <div class="approval-list">
        <div
          v-for="approval in recentApprovals"
          :key="approval.generation_id"
          class="approval-item"
        >
          <div class="approval-thumb">
            <img :src="approval.thumbnail" :alt="approval.prompt" />
          </div>
          <div class="approval-info">
            <div class="approval-prompt">{{ approval.prompt }}</div>
            <div class="approval-feedback">{{ approval.feedback }}</div>
          </div>
          <div class="approval-score">
            {{ (approval.consistency * 100).toFixed(0) }}%
          </div>
        </div>
      </div>
    </div>

    <!-- Reject Dialog -->
    <div v-if="showReject" class="modal-overlay" @click="showReject = false">
      <div class="modal-dialog" @click.stop>
        <h3>Reject Generation</h3>
        <p>Please provide a reason for rejection:</p>
        <textarea
          v-model="rejectReason"
          placeholder="E.g., Face doesn't match, wrong pose, inconsistent style..."
          rows="4"
        ></textarea>
        <div class="modal-actions">
          <button @click="confirmReject" :disabled="!rejectReason">
            Reject
          </button>
          <button @click="showReject = false">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Preview Modal -->
    <div v-if="showPreviewModal" class="preview-modal" @click="showPreviewModal = false">
      <div class="preview-content" @click.stop>
        <img :src="previewImage" :alt="previewPrompt" />
        <div class="preview-info">
          <p>{{ previewPrompt }}</p>
          <div class="preview-actions">
            <button class="btn-approve-large" @click="approveFromPreview">
              <i class="pi pi-check"></i> Approve
            </button>
            <button class="btn-reject-large" @click="rejectFromPreview">
              <i class="pi pi-times"></i> Reject
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'CharacterQCPanel',

  props: {
    character: {
      type: Object,
      required: true
    }
  },

  data() {
    return {
      metrics: null,
      qcQueue: [],
      recentApprovals: [],
      recommendations: [],
      processing: false,
      showReject: false,
      rejectReason: '',
      currentItem: null,
      showPreviewModal: false,
      previewImage: '',
      previewPrompt: '',
      previewItem: null
    }
  },

  computed: {
    qcStatus() {
      if (!this.metrics) return 'unknown'
      if (this.metrics.approval_rate > 80) return 'good'
      if (this.metrics.approval_rate > 60) return 'warning'
      return 'needs-attention'
    },

    qcStatusText() {
      if (!this.metrics) return 'Loading...'
      if (this.metrics.approval_rate > 80) return 'Production Ready'
      if (this.metrics.approval_rate > 60) return 'Needs Improvement'
      return 'Quality Issues'
    }
  },

  mounted() {
    this.loadQCData()
    // Refresh every 30 seconds
    this.refreshInterval = setInterval(() => {
      this.loadQCData()
    }, 30000)
  },

  beforeUnmount() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval)
    }
  },

  methods: {
    async loadQCData() {
      try {
        // Load metrics
        const metricsRes = await fetch(
          `/api/anime/studio/qc/${this.character.id}/metrics`
        )
        if (metricsRes.ok) {
          const data = await metricsRes.json()
          this.metrics = data.metrics
          this.recommendations = data.recommendations || []
        }

        // Load QC queue
        const queueRes = await fetch(
          `/api/anime/studio/qc/queue?character_id=${this.character.id}`
        )
        if (queueRes.ok) {
          const data = await queueRes.json()
          this.qcQueue = data.queue || []
        }

        // Load recent approvals from character report
        const reportRes = await fetch(
          `http://localhost:8309/api/echo/anime/character/${this.character.id}/report`
        )
        if (reportRes.ok) {
          const report = await reportRes.json()
          this.recentApprovals = report.recent_generations
            .filter(g => g.approved)
            .slice(0, 5)
            .map(g => ({
              ...g,
              thumbnail: `/api/anime/image/${this.character.id}/generation/${g.date}`
            }))
        }
      } catch (error) {
        console.error('Error loading QC data:', error)
        this.$toast.add({
          severity: 'error',
          summary: 'QC Error',
          detail: 'Failed to load QC data',
          life: 3000
        })
      }
    },

    async approveGeneration(item) {
      this.processing = true
      try {
        const response = await fetch(
          `/api/anime/studio/qc/${this.character.id}/approve?generation_id=${item.generation_id}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ feedback: 'Approved via QC panel' })
          }
        )

        if (response.ok) {
          this.$toast.add({
            severity: 'success',
            summary: 'Approved',
            detail: 'Generation approved successfully',
            life: 3000
          })

          // Remove from queue
          this.qcQueue = this.qcQueue.filter(
            q => q.generation_id !== item.generation_id
          )

          // Reload data
          await this.loadQCData()

          // Emit event for parent
          this.$emit('generation-approved', item)
        }
      } catch (error) {
        console.error('Approval error:', error)
        this.$toast.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to approve generation',
          life: 3000
        })
      } finally {
        this.processing = false
      }
    },

    showRejectDialog(item) {
      this.currentItem = item
      this.rejectReason = ''
      this.showReject = true
    },

    async confirmReject() {
      if (!this.rejectReason || !this.currentItem) return

      this.processing = true
      try {
        const response = await fetch(
          `/api/anime/studio/qc/${this.character.id}/reject?generation_id=${this.currentItem.generation_id}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ reason: this.rejectReason })
          }
        )

        if (response.ok) {
          this.$toast.add({
            severity: 'info',
            summary: 'Rejected',
            detail: 'Generation rejected, Echo will learn from this',
            life: 3000
          })

          // Remove from queue
          this.qcQueue = this.qcQueue.filter(
            q => q.generation_id !== this.currentItem.generation_id
          )

          this.showReject = false
          this.currentItem = null

          // Reload data
          await this.loadQCData()

          // Emit event
          this.$emit('generation-rejected', this.currentItem)
        }
      } catch (error) {
        console.error('Rejection error:', error)
        this.$toast.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to reject generation',
          life: 3000
        })
      } finally {
        this.processing = false
      }
    },

    async regenerate(item) {
      this.$emit('regenerate-request', {
        prompt: item.prompt,
        adjustments: {
          denoise: 0.4, // Lower denoise for consistency
          seed: Math.floor(Math.random() * 1000000)
        }
      })
    },

    showPreview(item) {
      this.previewImage = item.preview_url
      this.previewPrompt = item.prompt
      this.previewItem = item
      this.showPreviewModal = true
    },

    approveFromPreview() {
      if (this.previewItem) {
        this.approveGeneration(this.previewItem)
        this.showPreviewModal = false
      }
    },

    rejectFromPreview() {
      if (this.previewItem) {
        this.showRejectDialog(this.previewItem)
        this.showPreviewModal = false
      }
    },

    formatDate(dateStr) {
      const date = new Date(dateStr)
      return date.toLocaleDateString() + ' ' + date.toLocaleTimeString()
    }
  }
}
</script>

<style scoped>
.character-qc-panel {
  background: #1a1a1a;
  border-radius: 8px;
  padding: 1.5rem;
}

.qc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.qc-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  animation: pulse 2s infinite;
}

.status-indicator.good { background: #4caf50; }
.status-indicator.warning { background: #ff9800; }
.status-indicator.needs-attention { background: #f44336; }

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.metric-card {
  background: #2a2a2a;
  padding: 1rem;
  border-radius: 6px;
  text-align: center;
}

.metric-value {
  font-size: 1.5rem;
  font-weight: bold;
  color: #00ff88;
}

.metric-label {
  color: #999;
  font-size: 0.875rem;
  margin-top: 0.25rem;
}

.recommendations {
  background: #2a2a2a;
  padding: 1rem;
  border-radius: 6px;
  margin-bottom: 1.5rem;
}

.recommendations ul {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0 0;
}

.recommendations li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #ccc;
  margin-bottom: 0.5rem;
}

.qc-queue-section h4 {
  margin-bottom: 1rem;
}

.empty-queue {
  text-align: center;
  padding: 2rem;
  color: #666;
}

.empty-queue i {
  font-size: 3rem;
  color: #4caf50;
  margin-bottom: 1rem;
}

.qc-item {
  display: flex;
  gap: 1rem;
  padding: 1rem;
  background: #2a2a2a;
  border-radius: 6px;
  margin-bottom: 1rem;
}

.qc-item-preview {
  width: 100px;
  height: 100px;
  flex-shrink: 0;
}

.qc-item-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 4px;
  cursor: pointer;
}

.qc-item-details {
  flex: 1;
}

.generation-prompt {
  color: #fff;
  margin-bottom: 0.5rem;
}

.generation-meta {
  display: flex;
  gap: 1rem;
  color: #999;
  font-size: 0.875rem;
}

.qc-actions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.qc-actions button {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s;
}

.btn-approve {
  background: #4caf50;
  color: white;
}

.btn-approve:hover { background: #45a049; }

.btn-reject {
  background: #f44336;
  color: white;
}

.btn-reject:hover { background: #da190b; }

.btn-regenerate {
  background: #2196f3;
  color: white;
}

.btn-regenerate:hover { background: #0b7dda; }

.modal-overlay {
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

.modal-dialog {
  background: #2a2a2a;
  padding: 2rem;
  border-radius: 8px;
  max-width: 500px;
  width: 100%;
}

.modal-dialog textarea {
  width: 100%;
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #444;
  color: white;
  border-radius: 4px;
  margin: 1rem 0;
}

.modal-actions {
  display: flex;
  gap: 1rem;
  justify-content: flex-end;
}

.preview-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.95);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1001;
}

.preview-content {
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.preview-content img {
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
}

.preview-info {
  background: #2a2a2a;
  padding: 1rem;
  border-radius: 8px;
}

.preview-actions {
  display: flex;
  gap: 1rem;
  margin-top: 1rem;
}

.btn-approve-large,
.btn-reject-large {
  flex: 1;
  padding: 1rem;
  font-size: 1.1rem;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.btn-approve-large {
  background: #4caf50;
  color: white;
}

.btn-reject-large {
  background: #f44336;
  color: white;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}
</style>