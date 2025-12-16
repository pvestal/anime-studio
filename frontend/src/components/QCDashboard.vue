<template>
  <div class="qc-dashboard">
    <!-- Dashboard Header -->
    <div class="dashboard-header">
      <div class="header-left">
        <h2>
          <i class="pi pi-shield"></i>
          Quality Control Dashboard
        </h2>
        <span class="qc-status" :class="overallStatusClass">
          <span class="status-indicator"></span>
          {{ overallStatus }}
        </span>
      </div>
      <div class="header-controls">
        <Button
          icon="pi pi-refresh"
          @click="refreshDashboard"
          :loading="refreshing"
          severity="secondary"
          text
          v-tooltip="'Refresh All Results'"
        />
        <Button
          icon="pi pi-cog"
          @click="showSettings = true"
          severity="secondary"
          text
          v-tooltip="'QC Settings'"
        />
        <Button
          icon="pi pi-download"
          @click="exportReport"
          severity="info"
          text
          v-tooltip="'Export QC Report'"
        />
      </div>
    </div>

    <!-- Quality Gates Overview -->
    <div class="gates-overview">
      <Card
        v-for="gate in qualityGates"
        :key="gate.id"
        :class="['gate-card', gate.status]"
      >
        <template #content>
          <div class="gate-header">
            <div class="gate-info">
              <span class="gate-number">Gate {{ gate.id }}</span>
              <h4 class="gate-title">{{ gate.name }}</h4>
            </div>
            <div class="gate-status-icon">
              <i :class="getGateIcon(gate.status)"></i>
            </div>
          </div>

          <div class="gate-metrics">
            <div class="metric">
              <span class="metric-label">Pass Rate</span>
              <span class="metric-value">{{ gate.passRate }}%</span>
            </div>
            <div class="metric">
              <span class="metric-label">Last Run</span>
              <span class="metric-value">{{ formatTime(gate.lastRun) }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">Total Tests</span>
              <span class="metric-value">{{ gate.totalTests }}</span>
            </div>
          </div>

          <ProgressBar
            :value="gate.passRate"
            :class="['gate-progress', gate.status]"
            :showValue="false"
          />

          <div class="gate-actions">
            <Button
              label="Details"
              @click="showGateDetails(gate)"
              size="small"
              severity="secondary"
              outlined
            />
            <Button
              label="Run Now"
              @click="runGate(gate)"
              :loading="gate.running"
              size="small"
              severity="primary"
            />
          </div>
        </template>
      </Card>
    </div>

    <!-- Recent QC Results -->
    <div class="recent-results">
      <div class="section-header">
        <h3>Recent Quality Assessments</h3>
        <div class="result-filters">
          <Dropdown
            v-model="resultFilter"
            :options="filterOptions"
            optionLabel="label"
            optionValue="value"
            placeholder="Filter Results"
            @change="filterResults"
          />
          <ToggleButton
            v-model="showFailuresOnly"
            onLabel="Failures Only"
            offLabel="All Results"
            @change="filterResults"
            severity="secondary"
          />
        </div>
      </div>

      <DataTable
        :value="filteredResults"
        :paginator="true"
        :rows="10"
        :loading="loadingResults"
        class="results-table"
        @rowSelect="viewResult"
        selectionMode="single"
      >
        <Column field="timestamp" header="Time" sortable style="width: 140px">
          <template #body="slotProps">
            {{ formatTimestamp(slotProps.data.timestamp) }}
          </template>
        </Column>

        <Column field="gate" header="Gate" sortable style="width: 100px">
          <template #body="slotProps">
            <Tag :value="`Gate ${slotProps.data.gate}`" severity="info" />
          </template>
        </Column>

        <Column field="asset_name" header="Asset" sortable>
          <template #body="slotProps">
            <div class="asset-cell">
              <img
                v-if="slotProps.data.thumbnail"
                :src="slotProps.data.thumbnail"
                class="asset-thumbnail"
              />
              <span class="asset-name">{{ slotProps.data.asset_name }}</span>
            </div>
          </template>
        </Column>

        <Column field="status" header="Status" sortable style="width: 100px">
          <template #body="slotProps">
            <Tag
              :value="slotProps.data.status"
              :severity="getStatusSeverity(slotProps.data.status)"
            />
          </template>
        </Column>

        <Column field="overall_score" header="Score" sortable style="width: 100px">
          <template #body="slotProps">
            <div class="score-cell">
              <span class="score-value">{{ (slotProps.data.overall_score * 100).toFixed(1) }}%</span>
              <ProgressBar
                :value="slotProps.data.overall_score * 100"
                :class="['score-bar', getScoreClass(slotProps.data.overall_score)]"
                :showValue="false"
              />
            </div>
          </template>
        </Column>

        <Column field="issues_count" header="Issues" style="width: 80px">
          <template #body="slotProps">
            <span
              :class="['issues-count', { 'has-issues': slotProps.data.issues_count > 0 }]"
            >
              {{ slotProps.data.issues_count }}
            </span>
          </template>
        </Column>

        <Column header="Actions" style="width: 150px">
          <template #body="slotProps">
            <Button
              icon="pi pi-eye"
              @click="viewResult(slotProps.data)"
              size="small"
              severity="info"
              text
              v-tooltip="'View Details'"
            />
            <Button
              v-if="slotProps.data.status === 'failed'"
              icon="pi pi-check"
              @click="overrideResult(slotProps.data)"
              size="small"
              severity="success"
              text
              v-tooltip="'Override (Approve)'"
            />
            <Button
              v-if="slotProps.data.status === 'passed'"
              icon="pi pi-times"
              @click="flagResult(slotProps.data)"
              size="small"
              severity="danger"
              text
              v-tooltip="'Flag as Problem'"
            />
            <Button
              icon="pi pi-refresh"
              @click="rerunAssessment(slotProps.data)"
              size="small"
              severity="secondary"
              text
              v-tooltip="'Rerun Assessment'"
            />
          </template>
        </Column>
      </DataTable>
    </div>

    <!-- Quality Trends -->
    <div class="quality-trends" v-if="showTrends">
      <h3>Quality Trends</h3>
      <Card class="trends-card">
        <template #content>
          <div class="trends-charts">
            <!-- Placeholder for charts - would integrate with Chart.js or similar -->
            <div class="chart-placeholder">
              <p>Quality trend charts would be displayed here</p>
              <small>Integration with Chart.js for pass rate trends over time</small>
            </div>
          </div>
        </template>
      </Card>
    </div>

    <!-- Result Details Dialog -->
    <Dialog
      v-model:visible="showResultDetails"
      header="Quality Assessment Details"
      :modal="true"
      :style="{ width: '800px' }"
      maximizable
    >
      <div v-if="selectedResult" class="result-details">
        <!-- Asset Preview -->
        <div class="asset-preview">
          <img
            v-if="selectedResult.asset_preview"
            :src="selectedResult.asset_preview"
            class="preview-image"
          />
          <div v-else class="preview-placeholder">
            <i class="pi pi-image"></i>
            <span>No preview available</span>
          </div>
        </div>

        <!-- Assessment Scores -->
        <div class="assessment-scores">
          <h4>Assessment Scores</h4>
          <div class="scores-grid">
            <div
              v-for="(score, metric) in selectedResult.detailed_scores"
              :key="metric"
              class="score-item"
            >
              <span class="score-label">{{ formatMetricName(metric) }}</span>
              <div class="score-progress">
                <ProgressBar
                  :value="score * 100"
                  :class="getScoreClass(score)"
                  :showValue="true"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- Issues List -->
        <div v-if="selectedResult.issues?.length > 0" class="issues-list">
          <h4>Identified Issues</h4>
          <div
            v-for="(issue, index) in selectedResult.issues"
            :key="index"
            class="issue-item"
          >
            <div class="issue-header">
              <Tag :value="issue.severity" :severity="getSeveritySeverity(issue.severity)" />
              <span class="issue-title">{{ issue.description }}</span>
            </div>
            <div v-if="issue.suggestion" class="issue-suggestion">
              <strong>Suggestion:</strong> {{ issue.suggestion }}
            </div>
            <div v-if="issue.auto_fix_available" class="issue-autofix">
              <Button
                label="Auto Fix"
                icon="pi pi-magic-wand"
                @click="applyAutoFix(issue)"
                size="small"
                severity="info"
              />
            </div>
          </div>
        </div>

        <!-- Raw Data -->
        <Accordion v-if="selectedResult.raw_data">
          <AccordionTab header="Raw Assessment Data">
            <pre class="raw-data">{{ JSON.stringify(selectedResult.raw_data, null, 2) }}</pre>
          </AccordionTab>
        </Accordion>
      </div>
    </Dialog>

    <!-- QC Settings Dialog -->
    <Dialog
      v-model:visible="showSettings"
      header="Quality Control Settings"
      :modal="true"
      :style="{ width: '600px' }"
    >
      <div class="settings-content">
        <div class="setting-section">
          <h4>Quality Thresholds</h4>
          <div class="threshold-controls">
            <div
              v-for="threshold in qcSettings.thresholds"
              :key="threshold.metric"
              class="threshold-item"
            >
              <label>{{ formatMetricName(threshold.metric) }}</label>
              <div class="threshold-control">
                <Slider
                  v-model="threshold.value"
                  :min="0"
                  :max="1"
                  :step="0.05"
                />
                <span class="threshold-value">{{ threshold.value.toFixed(2) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="setting-section">
          <h4>Auto-Actions</h4>
          <div class="auto-actions">
            <div class="setting-item">
              <Checkbox v-model="qcSettings.autoReject" binary />
              <label>Automatically reject assets below threshold</label>
            </div>
            <div class="setting-item">
              <Checkbox v-model="qcSettings.autoRetry" binary />
              <label>Automatically retry failed generations</label>
            </div>
            <div class="setting-item">
              <Checkbox v-model="qcSettings.notifyOnFailure" binary />
              <label>Send notifications on quality failures</label>
            </div>
          </div>
        </div>

        <div class="setting-section">
          <h4>Learning Mode</h4>
          <Dropdown
            v-model="qcSettings.learningMode"
            :options="learningModes"
            optionLabel="label"
            optionValue="value"
            placeholder="Select Learning Mode"
          />
        </div>
      </div>

      <template #footer>
        <Button label="Cancel" @click="showSettings = false" severity="secondary" />
        <Button label="Save Settings" @click="saveQCSettings" />
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useEchoApi } from '@/composables/useEchoApi'
import { useEnhancedAnimeStore } from '@/stores/enhancedAnimeStore'

// Composables
const toast = useToast()
const echoApi = useEchoApi()
const store = useEnhancedAnimeStore()

// Refs
const refreshing = ref(false)
const loadingResults = ref(false)
const showResultDetails = ref(false)
const showSettings = ref(false)
const showTrends = ref(true)
const showFailuresOnly = ref(false)
const selectedResult = ref(null)
const resultFilter = ref('all')
const qcResults = ref([])

// Quality Gates State
const qualityGates = ref([
  {
    id: 1,
    name: 'Asset Readiness & Style Consistency',
    status: 'passing',
    passRate: 94,
    lastRun: new Date(Date.now() - 1000 * 60 * 15), // 15 minutes ago
    totalTests: 156,
    running: false
  },
  {
    id: 2,
    name: 'Frame Generation Quality',
    status: 'warning',
    passRate: 78,
    lastRun: new Date(Date.now() - 1000 * 60 * 5), // 5 minutes ago
    totalTests: 89,
    running: false
  },
  {
    id: 3,
    name: 'Temporal Consistency & Motion',
    status: 'failing',
    passRate: 62,
    lastRun: new Date(Date.now() - 1000 * 60 * 30), // 30 minutes ago
    totalTests: 34,
    running: false
  },
  {
    id: 4,
    name: 'Final Video Quality & Sync',
    status: 'passing',
    passRate: 91,
    lastRun: new Date(Date.now() - 1000 * 60 * 45), // 45 minutes ago
    totalTests: 67,
    running: false
  }
])

// QC Settings
const qcSettings = ref({
  thresholds: [
    { metric: 'character_fidelity', value: 0.7 },
    { metric: 'artifact_detection', value: 0.8 },
    { metric: 'prompt_adherence', value: 0.6 },
    { metric: 'temporal_consistency', value: 0.75 },
    { metric: 'overall_quality', value: 0.7 }
  ],
  autoReject: true,
  autoRetry: false,
  notifyOnFailure: true,
  learningMode: 'incremental'
})

// Filter Options
const filterOptions = ref([
  { label: 'All Results', value: 'all' },
  { label: 'Last Hour', value: 'hour' },
  { label: 'Last 24 Hours', value: 'day' },
  { label: 'Last Week', value: 'week' },
  { label: 'Failed Only', value: 'failed' },
  { label: 'Passed Only', value: 'passed' }
])

const learningModes = ref([
  { label: 'Incremental Learning', value: 'incremental' },
  { label: 'Conservative', value: 'conservative' },
  { label: 'Aggressive', value: 'aggressive' },
  { label: 'Manual Only', value: 'manual' }
])

// Computed
const overallStatus = computed(() => {
  const failing = qualityGates.value.filter(g => g.status === 'failing').length
  const warning = qualityGates.value.filter(g => g.status === 'warning').length

  if (failing > 0) return 'Quality Issues Detected'
  if (warning > 0) return 'Minor Quality Concerns'
  return 'All Systems Nominal'
})

const overallStatusClass = computed(() => {
  const failing = qualityGates.value.filter(g => g.status === 'failing').length
  const warning = qualityGates.value.filter(g => g.status === 'warning').length

  if (failing > 0) return 'status-failing'
  if (warning > 0) return 'status-warning'
  return 'status-passing'
})

const filteredResults = computed(() => {
  let filtered = [...qcResults.value]

  // Filter by status
  if (showFailuresOnly.value) {
    filtered = filtered.filter(r => r.status === 'failed')
  }

  // Filter by time period
  const now = new Date()
  switch (resultFilter.value) {
    case 'hour':
      filtered = filtered.filter(r => (now - new Date(r.timestamp)) < 3600000)
      break
    case 'day':
      filtered = filtered.filter(r => (now - new Date(r.timestamp)) < 86400000)
      break
    case 'week':
      filtered = filtered.filter(r => (now - new Date(r.timestamp)) < 604800000)
      break
    case 'failed':
      filtered = filtered.filter(r => r.status === 'failed')
      break
    case 'passed':
      filtered = filtered.filter(r => r.status === 'passed')
      break
  }

  return filtered.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
})

// Methods
async function refreshDashboard() {
  refreshing.value = true
  try {
    await loadQCResults()
    await updateGateStatus()

    toast.add({
      severity: 'success',
      summary: 'Dashboard Refreshed',
      detail: 'All QC data has been updated',
      life: 3000
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Refresh Failed',
      detail: error.message,
      life: 5000
    })
  } finally {
    refreshing.value = false
  }
}

async function loadQCResults() {
  loadingResults.value = true
  try {
    // Load recent QC results from store or API
    const results = await store.getQCResults() || []

    // Mock data for demonstration
    qcResults.value = [
      {
        id: 1,
        timestamp: new Date(Date.now() - 1000 * 60 * 5),
        gate: 2,
        asset_name: 'Kai_Detective_Scene_001.png',
        status: 'passed',
        overall_score: 0.87,
        issues_count: 0,
        thumbnail: '/api/thumbnails/kai_001.jpg',
        detailed_scores: {
          character_fidelity: 0.85,
          artifact_detection: 0.92,
          prompt_adherence: 0.84
        },
        issues: [],
        raw_data: { /* Assessment details */ }
      },
      {
        id: 2,
        timestamp: new Date(Date.now() - 1000 * 60 * 15),
        gate: 3,
        asset_name: 'Yuki_Action_Sequence.mp4',
        status: 'failed',
        overall_score: 0.52,
        issues_count: 3,
        thumbnail: '/api/thumbnails/yuki_action.jpg',
        detailed_scores: {
          temporal_consistency: 0.45,
          motion_quality: 0.67,
          character_tracking: 0.44
        },
        issues: [
          {
            severity: 'high',
            description: 'Temporal flickering detected in frames 45-67',
            suggestion: 'Increase temporal consistency weight',
            auto_fix_available: true
          },
          {
            severity: 'medium',
            description: 'Character proportions inconsistent',
            suggestion: 'Regenerate with stricter character reference',
            auto_fix_available: false
          }
        ],
        raw_data: { /* Assessment details */ }
      }
      // More mock results...
    ]
  } finally {
    loadingResults.value = false
  }
}

async function updateGateStatus() {
  // Update gate pass rates based on recent results
  for (const gate of qualityGates.value) {
    const gateResults = qcResults.value.filter(r => r.gate === gate.id)
    if (gateResults.length > 0) {
      const passedCount = gateResults.filter(r => r.status === 'passed').length
      gate.passRate = Math.round((passedCount / gateResults.length) * 100)

      // Update status based on pass rate
      if (gate.passRate < 70) {
        gate.status = 'failing'
      } else if (gate.passRate < 85) {
        gate.status = 'warning'
      } else {
        gate.status = 'passing'
      }
    }
  }
}

async function runGate(gate) {
  gate.running = true
  try {
    toast.add({
      severity: 'info',
      summary: 'Running Quality Gate',
      detail: `Executing ${gate.name}...`,
      life: 3000
    })

    // Simulate gate execution
    await new Promise(resolve => setTimeout(resolve, 3000))

    gate.lastRun = new Date()
    gate.totalTests += Math.floor(Math.random() * 5) + 1

    toast.add({
      severity: 'success',
      summary: 'Gate Completed',
      detail: `${gate.name} execution finished`,
      life: 3000
    })

    await loadQCResults()
  } finally {
    gate.running = false
  }
}

function showGateDetails(gate) {
  toast.add({
    severity: 'info',
    summary: 'Gate Details',
    detail: `Viewing details for ${gate.name}`,
    life: 2000
  })
}

function viewResult(result) {
  selectedResult.value = result
  showResultDetails.value = true
}

async function overrideResult(result) {
  try {
    // Learn from user override
    await echoApi.learnPreference({
      result_id: result.id,
      user_override: 'approve',
      original_status: result.status,
      learning_category: 'quality_override'
    })

    result.status = 'passed'
    result.user_override = true

    toast.add({
      severity: 'success',
      summary: 'Result Overridden',
      detail: 'Quality assessment approved and learned',
      life: 3000
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Override Failed',
      detail: error.message,
      life: 3000
    })
  }
}

async function flagResult(result) {
  try {
    await echoApi.learnPreference({
      result_id: result.id,
      user_override: 'reject',
      original_status: result.status,
      learning_category: 'quality_override'
    })

    result.status = 'failed'
    result.user_flag = true

    toast.add({
      severity: 'warn',
      summary: 'Result Flagged',
      detail: 'Quality assessment flagged as problematic',
      life: 3000
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Flag Failed',
      detail: error.message,
      life: 3000
    })
  }
}

async function rerunAssessment(result) {
  try {
    toast.add({
      severity: 'info',
      summary: 'Rerunning Assessment',
      detail: 'Quality check in progress...',
      life: 3000
    })

    const newResult = await echoApi.assessQuality({
      asset_id: result.id,
      asset_path: result.asset_path
    })

    // Update result with new assessment
    Object.assign(result, newResult)

    toast.add({
      severity: 'success',
      summary: 'Assessment Complete',
      detail: `New score: ${(newResult.overall_score * 100).toFixed(1)}%`,
      life: 3000
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Assessment Failed',
      detail: error.message,
      life: 3000
    })
  }
}

function applyAutoFix(issue) {
  toast.add({
    severity: 'info',
    summary: 'Applying Auto Fix',
    detail: issue.description,
    life: 3000
  })
}

function filterResults() {
  // Filtering handled by computed property
}

async function saveQCSettings() {
  try {
    await store.updateQCSettings(qcSettings.value)
    showSettings.value = false

    toast.add({
      severity: 'success',
      summary: 'Settings Saved',
      detail: 'Quality control settings updated',
      life: 3000
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Save Failed',
      detail: error.message,
      life: 3000
    })
  }
}

function exportReport() {
  const reportData = {
    timestamp: new Date(),
    gates: qualityGates.value,
    results: qcResults.value,
    settings: qcSettings.value
  }

  const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `qc-report-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)

  toast.add({
    severity: 'success',
    summary: 'Report Exported',
    detail: 'Quality control report downloaded',
    life: 3000
  })
}

// Helper functions
function getGateIcon(status) {
  const icons = {
    'passing': 'pi pi-check-circle',
    'warning': 'pi pi-exclamation-triangle',
    'failing': 'pi pi-times-circle'
  }
  return icons[status] || 'pi pi-question-circle'
}

function getStatusSeverity(status) {
  const severities = {
    'passed': 'success',
    'failed': 'danger',
    'warning': 'warning',
    'pending': 'info'
  }
  return severities[status] || 'secondary'
}

function getSeveritySeverity(severity) {
  const severities = {
    'high': 'danger',
    'medium': 'warning',
    'low': 'info'
  }
  return severities[severity] || 'secondary'
}

function getScoreClass(score) {
  if (score >= 0.8) return 'score-excellent'
  if (score >= 0.7) return 'score-good'
  if (score >= 0.6) return 'score-fair'
  return 'score-poor'
}

function formatTime(date) {
  const diff = Date.now() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(minutes / 60)

  if (hours > 0) return `${hours}h ago`
  if (minutes > 0) return `${minutes}m ago`
  return 'Just now'
}

function formatTimestamp(date) {
  return new Date(date).toLocaleTimeString()
}

function formatMetricName(metric) {
  return metric.split('_').map(word =>
    word.charAt(0).toUpperCase() + word.slice(1)
  ).join(' ')
}

// Initialize
onMounted(async () => {
  await loadQCResults()
  await updateGateStatus()
})
</script>

<style scoped>
.qc-dashboard {
  background: #0a0a0a;
  color: #e0e0e0;
  padding: 1.5rem;
  min-height: 100vh;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #333;
}

.header-left h2 {
  margin: 0;
  color: #00d4ff;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.qc-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  margin-left: 1rem;
  font-weight: 600;
}

.status-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.status-passing .status-indicator {
  background: #51cf66;
}

.status-warning .status-indicator {
  background: #ffd43b;
}

.status-failing .status-indicator {
  background: #ff6b6b;
}

.header-controls {
  display: flex;
  gap: 0.5rem;
}

.gates-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.gate-card {
  background: #1a1a1a;
  border: 1px solid #333;
  transition: all 0.3s;
}

.gate-card.passing {
  border-left: 4px solid #51cf66;
}

.gate-card.warning {
  border-left: 4px solid #ffd43b;
}

.gate-card.failing {
  border-left: 4px solid #ff6b6b;
}

.gate-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1rem;
}

.gate-number {
  font-size: 0.75rem;
  color: #666;
  text-transform: uppercase;
}

.gate-title {
  margin: 0.25rem 0 0 0;
  font-size: 1rem;
  font-weight: 600;
  color: #e0e0e0;
}

.gate-status-icon {
  font-size: 1.5rem;
}

.gate-status-icon .pi-check-circle {
  color: #51cf66;
}

.gate-status-icon .pi-exclamation-triangle {
  color: #ffd43b;
}

.gate-status-icon .pi-times-circle {
  color: #ff6b6b;
}

.gate-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin-bottom: 1rem;
}

.metric {
  text-align: center;
}

.metric-label {
  display: block;
  font-size: 0.75rem;
  color: #999;
  margin-bottom: 0.25rem;
}

.metric-value {
  font-size: 1.1rem;
  font-weight: 600;
  color: #e0e0e0;
}

.gate-progress {
  margin-bottom: 1rem;
}

.gate-progress.passing {
  --p-progressbar-value-background: #51cf66;
}

.gate-progress.warning {
  --p-progressbar-value-background: #ffd43b;
}

.gate-progress.failing {
  --p-progressbar-value-background: #ff6b6b;
}

.gate-actions {
  display: flex;
  gap: 0.5rem;
}

.recent-results {
  margin-bottom: 2rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.section-header h3 {
  margin: 0;
  color: #e0e0e0;
}

.result-filters {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.results-table {
  background: #1a1a1a;
}

.asset-cell {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.asset-thumbnail {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 4px;
}

.asset-name {
  font-weight: 500;
}

.score-cell {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.score-value {
  font-weight: 600;
  font-family: monospace;
}

.score-bar {
  height: 6px;
}

.score-excellent {
  --p-progressbar-value-background: #51cf66;
}

.score-good {
  --p-progressbar-value-background: #69db7c;
}

.score-fair {
  --p-progressbar-value-background: #ffd43b;
}

.score-poor {
  --p-progressbar-value-background: #ff6b6b;
}

.issues-count {
  font-weight: 600;
  color: #51cf66;
}

.issues-count.has-issues {
  color: #ff6b6b;
}

.result-details {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.asset-preview {
  text-align: center;
}

.preview-image {
  max-width: 100%;
  max-height: 300px;
  border-radius: 4px;
  border: 1px solid #333;
}

.preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #666;
}

.scores-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
}

.score-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.score-label {
  font-weight: 600;
  color: #ccc;
}

.issues-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.issue-item {
  padding: 1rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
}

.issue-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.issue-title {
  font-weight: 600;
  color: #e0e0e0;
}

.issue-suggestion {
  color: #ccc;
  font-style: italic;
  margin-bottom: 0.5rem;
}

.raw-data {
  background: #0a0a0a;
  border: 1px solid #333;
  border-radius: 4px;
  padding: 1rem;
  color: #00d4ff;
  font-family: monospace;
  font-size: 0.875rem;
  max-height: 300px;
  overflow: auto;
}

.settings-content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.setting-section h4 {
  margin: 0 0 1rem 0;
  color: #00d4ff;
}

.threshold-controls {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.threshold-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.threshold-item label {
  font-weight: 600;
  color: #ccc;
}

.threshold-control {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.threshold-value {
  font-family: monospace;
  font-weight: 600;
  color: #00d4ff;
  min-width: 3rem;
}

.auto-actions {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.setting-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.setting-item label {
  color: #ccc;
}

.trends-card {
  background: #1a1a1a;
  border: 1px solid #333;
}

.chart-placeholder {
  text-align: center;
  padding: 3rem;
  color: #666;
}

.chart-placeholder p {
  margin: 0 0 0.5rem 0;
  font-size: 1.1rem;
}

.chart-placeholder small {
  font-style: italic;
}
</style>