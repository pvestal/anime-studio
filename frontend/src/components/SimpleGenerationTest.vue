<template>
  <div class="generation-test">
    <h3>🎭 Simple Anime Generation Test</h3>

    <!-- Generation Form -->
    <div class="generation-form">
      <div class="form-group">
        <label>Prompt:</label>
        <input
          v-model="prompt"
          type="text"
          placeholder="anime girl with blue hair"
          class="form-input"
        />
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>Width:</label>
          <input v-model="width" type="number" min="256" max="1024" class="form-input" />
        </div>
        <div class="form-group">
          <label>Height:</label>
          <input v-model="height" type="number" min="256" max="1024" class="form-input" />
        </div>
        <div class="form-group">
          <label>Steps:</label>
          <input v-model="steps" type="number" min="1" max="50" class="form-input" />
        </div>
      </div>

      <button @click="generateImage" :disabled="generating" class="generate-btn">
        {{ generating ? 'Generating...' : 'Generate Anime Image' }}
      </button>
    </div>

    <!-- Progress -->
    <div v-if="job" class="job-status">
      <h4>Job Status: {{ job.status }}</h4>
      <div v-if="job.progress" class="progress-bar">
        <div class="progress-fill" :style="{width: job.progress + '%'}"></div>
      </div>
      <p v-if="job.error" class="error">{{ job.error }}</p>
    </div>

    <!-- Result -->
    <div v-if="result && result.output_path" class="result">
      <h4>✅ Generation Complete!</h4>
      <p>Output: {{ result.output_path }}</p>
      <img
        v-if="imageUrl"
        :src="imageUrl"
        alt="Generated anime image"
        class="generated-image"
      />
    </div>

    <!-- Jobs List -->
    <div class="jobs-list">
      <h4>Recent Jobs</h4>
      <div v-for="job in jobs" :key="job.id" class="job-item">
        <span class="job-id">{{ job.id.slice(-8) }}</span>
        <span :class="['job-status', job.status]">{{ job.status }}</span>
        <span class="job-prompt">{{ job.prompt.slice(0, 30) }}...</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const prompt = ref('anime girl with blue hair')
const width = ref(512)
const height = ref(512)
const steps = ref(15)
const generating = ref(false)
const job = ref(null)
const result = ref(null)
const jobs = ref([])
const imageUrl = ref('')

const API_BASE = '/api/anime'

async function generateImage() {
  generating.value = true
  job.value = null
  result.value = null
  imageUrl.value = ''

  try {
    const response = await fetch(`${API_BASE}/api/anime/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: prompt.value,
        width: width.value,
        height: height.value,
        steps: steps.value
      })
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const data = await response.json()
    job.value = { ...data, progress: 0 }

    // Poll for status
    const jobId = data.job_id
    const pollInterval = setInterval(async () => {
      try {
        const statusResponse = await fetch(`${API_BASE}/api/anime/generation/${jobId}/status`)
        const statusData = await statusResponse.json()

        job.value = statusData

        if (statusData.status === 'completed') {
          clearInterval(pollInterval)
          result.value = statusData
          if (statusData.output_path) {
            // For demo, show file path (in real app would serve image)
            imageUrl.value = `/mnt/1TB-storage/ComfyUI/output/anime_${jobId}_00001_.png`
          }
          generating.value = false
          loadJobs() // Refresh jobs list
        } else if (statusData.status === 'failed') {
          clearInterval(pollInterval)
          generating.value = false
        }
      } catch (err) {
        console.error('Status check failed:', err)
      }
    }, 1000)

    // Timeout after 60 seconds
    setTimeout(() => {
      clearInterval(pollInterval)
      generating.value = false
    }, 60000)

  } catch (error) {
    console.error('Generation failed:', error)
    job.value = { status: 'failed', error: error.message }
    generating.value = false
  }
}

async function loadJobs() {
  try {
    const response = await fetch(`${API_BASE}/api/anime/jobs`)
    if (response.ok) {
      const data = await response.json()
      jobs.value = data.jobs || []
    }
  } catch (error) {
    console.error('Failed to load jobs:', error)
  }
}

onMounted(() => {
  loadJobs()
})
</script>

<style scoped>
.generation-test {
  max-width: 800px;
  margin: 0 auto;
  padding: 2rem;
  background: #1a1a1a;
  color: #e0e0e0;
  border-radius: 8px;
}

.generation-form {
  margin-bottom: 2rem;
}

.form-group {
  margin-bottom: 1rem;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 1rem;
}

.form-input {
  width: 100%;
  padding: 0.5rem;
  background: #2a2a2a;
  border: 1px solid #444;
  color: #e0e0e0;
  border-radius: 4px;
}

.generate-btn {
  background: #00d4aa;
  color: #000;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 4px;
  font-weight: 600;
  cursor: pointer;
  width: 100%;
}

.generate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.job-status {
  background: #2a2a2a;
  padding: 1rem;
  border-radius: 4px;
  margin-bottom: 1rem;
}

.progress-bar {
  width: 100%;
  height: 20px;
  background: #444;
  border-radius: 10px;
  overflow: hidden;
  margin: 0.5rem 0;
}

.progress-fill {
  height: 100%;
  background: #00d4aa;
  transition: width 0.3s ease;
}

.result {
  background: #0a4a3a;
  padding: 1rem;
  border-radius: 4px;
  margin-bottom: 1rem;
}

.generated-image {
  max-width: 100%;
  border-radius: 4px;
  margin-top: 0.5rem;
}

.jobs-list {
  background: #2a2a2a;
  padding: 1rem;
  border-radius: 4px;
}

.job-item {
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: 1rem;
  padding: 0.5rem;
  border-bottom: 1px solid #444;
}

.job-status.completed {
  color: #00d4aa;
}

.job-status.failed {
  color: #ff6b6b;
}

.job-status.processing {
  color: #ffd93d;
}

.error {
  color: #ff6b6b;
}
</style>