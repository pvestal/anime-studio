<template>
  <div>
    <h2 style="font-size: 18px; font-weight: 500; margin-bottom: 4px;">Generate</h2>
    <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 24px;">
      Test prompts, generate images, and produce video with FramePack. Manual/experimental workbench with prompt overrides and seed control.
    </p>

    <!-- Character selector + SSOT info -->
    <div style="display: flex; gap: 24px; margin-bottom: 24px; flex-wrap: wrap;">
      <div style="flex: 1; min-width: 300px;">
        <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Character</label>
        <select v-model="selectedSlug" style="width: 100%;">
          <option value="">Select a character...</option>
          <option v-for="c in characters" :key="c.slug" :value="c.slug">
            {{ c.name }} ({{ c.project_name }})
          </option>
        </select>
      </div>
      <div v-if="selectedChar" class="card" style="flex: 1; min-width: 280px;">
        <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">SSOT Profile</div>
        <div style="display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; font-size: 12px;">
          <span style="color: var(--text-muted);">Checkpoint:</span>
          <span>{{ selectedChar.checkpoint_model }}</span>
          <span style="color: var(--text-muted);">CFG:</span>
          <span>{{ selectedChar.cfg_scale ?? 'default' }}</span>
          <span style="color: var(--text-muted);">Steps:</span>
          <span>{{ selectedChar.steps ?? 'default' }}</span>
          <span style="color: var(--text-muted);">Resolution:</span>
          <span>{{ selectedChar.resolution || 'default' }}</span>
        </div>
      </div>
    </div>

    <!-- Generation form -->
    <div v-if="selectedSlug" class="card" style="margin-bottom: 24px;">
      <div style="display: flex; gap: 16px; margin-bottom: 16px; align-items: flex-end; flex-wrap: wrap;">
        <!-- Type toggle -->
        <div>
          <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Type</label>
          <div style="display: flex; gap: 4px;">
            <button
              :class="['btn', generationType === 'image' ? 'btn-active' : '']"
              style="font-size: 12px; padding: 4px 12px;"
              @click="generationType = 'image'"
            >Image</button>
            <button
              :class="['btn', generationType === 'video' ? 'btn-active' : '']"
              style="font-size: 12px; padding: 4px 12px;"
              @click="generationType = 'video'"
            >Video (16f)</button>
            <button
              :class="['btn', generationType === 'framepack' ? 'btn-active' : '']"
              style="font-size: 12px; padding: 4px 12px;"
              @click="generationType = 'framepack'"
            >Video (FramePack)</button>
          </div>
        </div>

        <!-- Seed -->
        <div>
          <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Seed (optional)</label>
          <input
            v-model.number="seed"
            type="number"
            placeholder="Random"
            style="width: 120px; padding: 4px 8px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
          />
        </div>
      </div>

      <!-- FramePack options panel -->
      <div v-if="generationType === 'framepack'" style="display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; padding: 12px; background: var(--bg-primary); border-radius: 4px; border: 1px solid var(--border-primary);">
        <!-- Duration slider -->
        <div style="min-width: 200px;">
          <label style="font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 4px;">
            Duration: {{ fpSeconds }}s
          </label>
          <input
            v-model.number="fpSeconds"
            type="range"
            min="1"
            max="10"
            step="0.5"
            style="width: 100%;"
          />
        </div>
        <!-- Steps -->
        <div>
          <label style="font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 4px;">Steps</label>
          <div style="display: flex; gap: 4px;">
            <button
              v-for="s in [15, 20, 25]"
              :key="s"
              :class="['btn', fpSteps === s ? 'btn-active' : '']"
              style="font-size: 11px; padding: 3px 10px;"
              @click="fpSteps = s"
            >{{ s }}</button>
          </div>
        </div>
        <!-- Model -->
        <div>
          <label style="font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 4px;">Model</label>
          <div style="display: flex; gap: 4px;">
            <button
              :class="['btn', !fpUseF1 ? 'btn-active' : '']"
              style="font-size: 11px; padding: 3px 10px;"
              @click="fpUseF1 = false"
            >I2V</button>
            <button
              :class="['btn', fpUseF1 ? 'btn-active' : '']"
              style="font-size: 11px; padding: 3px 10px;"
              @click="fpUseF1 = true"
            >F1</button>
          </div>
        </div>
        <!-- Estimate -->
        <div style="display: flex; align-items: flex-end;">
          <span style="font-size: 11px; color: var(--text-muted);">
            ~{{ fpEstSections }} sections, ~{{ fpEstMinutes }} min
          </span>
        </div>
      </div>

      <!-- Prompt -->
      <div style="margin-bottom: 12px;">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
          <label style="font-size: 13px; color: var(--text-secondary);">
            Prompt
            <span style="font-size: 11px; color: var(--text-muted);">(leave empty to use design_prompt from DB)</span>
          </label>
          <EchoAssistButton
            v-if="selectedChar"
            context-type="prompt_override"
            :context-payload="{
              project_name: selectedChar.project_name,
              character_name: selectedChar.name,
              character_slug: selectedChar.slug,
              checkpoint_model: selectedChar.checkpoint_model,
              design_prompt: selectedChar.design_prompt,
            }"
            :current-value="promptOverride"
            compact
            @accept="promptOverride = $event.suggestion"
          />
        </div>
        <textarea
          v-model="promptOverride"
          rows="3"
          :placeholder="selectedChar?.design_prompt || 'Enter prompt...'"
          style="width: 100%; padding: 8px 10px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; resize: vertical; font-family: var(--font-primary);"
        ></textarea>
      </div>

      <!-- Negative prompt -->
      <div style="margin-bottom: 16px;">
        <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">
          Negative Prompt
          <span style="font-size: 11px; color: var(--text-muted);">(optional)</span>
        </label>
        <input
          v-model="negativePrompt"
          type="text"
          placeholder="worst quality, low quality, blurry, deformed"
          style="width: 100%; padding: 6px 10px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
        />
      </div>

      <div style="display: flex; gap: 12px; align-items: center;">
        <button
          class="btn btn-active"
          @click="generate"
          :disabled="generating"
          style="padding: 8px 24px; font-size: 14px;"
        >
          {{ generating ? 'Generating...' : 'Generate' }}
        </button>
        <button
          class="btn"
          @click="clearStuck"
          style="font-size: 12px;"
        >Clear Stuck Jobs</button>
        <span v-if="statusMessage" style="font-size: 12px; color: var(--text-muted);">{{ statusMessage }}</span>
      </div>
    </div>

    <!-- Standard progress (image/video 16f) -->
    <div v-if="activePromptId && generationType !== 'framepack'" class="card" style="margin-bottom: 24px;">
      <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
        <span style="font-size: 13px; font-weight: 500;">Generation Progress</span>
        <span style="font-size: 12px; color: var(--text-muted);">{{ progressStatus }}</span>
      </div>
      <div style="height: 6px; background: var(--bg-primary); border-radius: 3px; overflow: hidden;">
        <div
          :style="{
            width: (progressPercent * 100) + '%',
            height: '100%',
            background: progressPercent >= 1 ? 'var(--status-success)' : 'var(--accent-primary)',
            transition: 'width 300ms ease',
          }"
        ></div>
      </div>
      <div v-if="progressPercent >= 1 && resultImages.length" style="margin-top: 16px;">
        <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">Output:</div>
        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
          <img
            v-for="img in resultImages"
            :key="img"
            :src="galleryImageUrl(img)"
            style="max-width: 256px; max-height: 256px; border-radius: 4px; cursor: pointer; border: 1px solid var(--border-primary);"
            @click="openImage(img)"
          />
        </div>
      </div>
    </div>

    <!-- FramePack progress card with WebSocket updates -->
    <div v-if="fpPromptId" class="card" style="margin-bottom: 24px;">
      <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
        <span style="font-size: 13px; font-weight: 500;">FramePack Video Progress</span>
        <span
          style="font-size: 11px; padding: 2px 8px; border-radius: 10px;"
          :style="{
            background: fpStatus === 'done' ? 'var(--status-success)' : fpStatus === 'error' ? 'var(--status-error)' : 'var(--accent-primary)',
            color: '#fff',
          }"
        >{{ fpStatus }}</span>
      </div>

      <!-- Phase label -->
      <div v-if="fpStatus !== 'idle' && fpStatus !== 'done'" style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
        {{ comfyProgress.phaseLabel.value || 'Initializing...' }}
      </div>

      <!-- Section/Step detail -->
      <div v-if="fpStatus === 'sampling'" style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
        Section {{ comfyProgress.currentSection.value + 1 }}/{{ fpTotalSections }}
        &mdash; Step {{ comfyProgress.currentStep.value }}/{{ comfyProgress.stepsPerSection.value }}
        ({{ comfyProgress.globalStep.value }}/{{ comfyProgress.totalGlobalSteps.value }} total)
      </div>

      <!-- Progress bar -->
      <div style="height: 8px; background: var(--bg-primary); border-radius: 4px; overflow: hidden; margin-bottom: 8px;">
        <div
          :style="{
            width: (fpProgressPercent * 100) + '%',
            height: '100%',
            background: fpStatus === 'done' ? 'var(--status-success)' : fpStatus === 'error' ? 'var(--status-error)' : 'var(--accent-primary)',
            transition: 'width 300ms ease',
          }"
        ></div>
      </div>

      <!-- Percentage + ETA -->
      <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted);">
        <span>{{ Math.round(fpProgressPercent * 100) }}%</span>
        <span>
          Elapsed: {{ formatTime(comfyProgress.elapsedSeconds.value) }}
          <template v-if="comfyProgress.etaSeconds.value !== null">
            &bull; ETA: ~{{ formatTime(comfyProgress.etaSeconds.value) }}
          </template>
        </span>
      </div>

      <!-- Error message -->
      <div v-if="fpStatus === 'error'" style="margin-top: 8px; font-size: 12px; color: var(--status-error);">
        {{ comfyProgress.errorMessage.value }}
      </div>

      <!-- Video output -->
      <div v-if="fpStatus === 'done' && comfyProgress.outputFiles.value.length" style="margin-top: 16px;">
        <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">Output:</div>
        <div v-for="file in comfyProgress.outputFiles.value" :key="file">
          <video
            v-if="isVideoFile(file)"
            :src="galleryImageUrl(file)"
            controls
            autoplay
            loop
            style="max-width: 512px; max-height: 384px; border-radius: 4px; border: 1px solid var(--border-primary);"
          ></video>
          <img
            v-else
            :src="galleryImageUrl(file)"
            style="max-width: 256px; max-height: 256px; border-radius: 4px; cursor: pointer; border: 1px solid var(--border-primary);"
            @click="openImage(file)"
          />
        </div>
      </div>
    </div>

    <!-- Recent generations log -->
    <div v-if="recentGenerations.length" class="card">
      <div style="font-size: 13px; font-weight: 500; margin-bottom: 12px;">Recent Generations</div>
      <div
        v-for="gen in recentGenerations"
        :key="gen.prompt_id"
        style="display: flex; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border-primary); font-size: 12px; align-items: center;"
      >
        <span style="color: var(--accent-primary); font-family: monospace;">{{ gen.prompt_id.slice(0, 8) }}</span>
        <span>{{ gen.character }}</span>
        <span style="color: var(--text-muted);">{{ gen.generation_type }}</span>
        <span v-if="gen.seed" style="color: var(--text-muted);">seed={{ gen.seed }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useCharactersStore } from '@/stores/characters'
import { api } from '@/api/client'
import type { GenerateResponse } from '@/types'
import EchoAssistButton from './EchoAssistButton.vue'
import { useComfyProgress } from '@/composables/useComfyProgress'

const charactersStore = useCharactersStore()
const characters = computed(() => charactersStore.characters)

const selectedSlug = ref('')
const generationType = ref<'image' | 'video' | 'framepack'>('image')
const promptOverride = ref('')
const negativePrompt = ref('')
const seed = ref<number | undefined>(undefined)
const generating = ref(false)
const statusMessage = ref('')
const activePromptId = ref('')
const progressStatus = ref('')
const progressPercent = ref(0)
const resultImages = ref<string[]>([])
const recentGenerations = ref<GenerateResponse[]>([])

// FramePack specific
const fpSeconds = ref(3)
const fpSteps = ref(25)
const fpUseF1 = ref(false)
const fpPromptId = ref('')
const fpSamplerNodeId = ref('')
const fpTotalSections = ref(0)

const comfyProgress = useComfyProgress(fpPromptId, fpSamplerNodeId, computed(() => fpTotalSections.value))

const fpStatus = computed(() => comfyProgress.status.value)
const fpProgressPercent = computed(() => {
  if (fpStatus.value === 'done') return 1
  if (fpStatus.value === 'loading') return 0.02
  if (fpStatus.value === 'decoding') return 0.95
  return comfyProgress.percent.value
})

const fpEstSections = computed(() => {
  const lws = 9
  if (fpUseF1.value) {
    const sd = (lws * 4 - 3) / 30
    return Math.max(Math.ceil(fpSeconds.value / sd), 1)
  }
  return Math.max(Math.round((fpSeconds.value * 30) / (lws * 4)), 1)
})

const fpEstMinutes = computed(() => {
  // ~7s per step at 3.5GB gpu_memory_preservation
  return Math.round(fpEstSections.value * fpSteps.value * 7 / 60)
})

let pollTimer: ReturnType<typeof setInterval> | null = null

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})

// Reset form fields when character changes
watch(selectedSlug, () => {
  promptOverride.value = ''
  negativePrompt.value = ''
  seed.value = undefined
  generationType.value = 'image'
  fpSeconds.value = 3
  fpSteps.value = 25
  fpUseF1.value = false
})

const selectedChar = computed(() =>
  characters.value.find(c => c.slug === selectedSlug.value)
)

function galleryImageUrl(filename: string) {
  return api.galleryImageUrl(filename)
}

function openImage(filename: string) {
  window.open(api.galleryImageUrl(filename), '_blank')
}

function isVideoFile(filename: string) {
  return /\.(mp4|webm|gif)$/i.test(filename)
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

async function generate() {
  if (!selectedSlug.value) return

  if (generationType.value === 'framepack') {
    await generateFramePack()
    return
  }

  generating.value = true
  statusMessage.value = ''
  activePromptId.value = ''
  progressPercent.value = 0
  progressStatus.value = ''
  resultImages.value = []

  try {
    const result = await api.generateForCharacter(selectedSlug.value, {
      generation_type: generationType.value,
      prompt_override: promptOverride.value || undefined,
      negative_prompt: negativePrompt.value || undefined,
      seed: seed.value || undefined,
    })

    activePromptId.value = result.prompt_id
    progressStatus.value = 'Submitted to ComfyUI'
    progressPercent.value = 0.05
    recentGenerations.value.unshift(result)
    if (recentGenerations.value.length > 10) recentGenerations.value.pop()

    startPolling(result.prompt_id)
  } catch (err: any) {
    statusMessage.value = `Error: ${err.message}`
  } finally {
    generating.value = false
  }
}

async function generateFramePack() {
  generating.value = true
  statusMessage.value = ''
  fpPromptId.value = ''

  try {
    const result = await api.generateFramePack(selectedSlug.value, {
      prompt_override: promptOverride.value || undefined,
      negative_prompt: negativePrompt.value || undefined,
      seconds: fpSeconds.value,
      steps: fpSteps.value,
      use_f1: fpUseF1.value,
      seed: seed.value || undefined,
    })

    fpPromptId.value = result.prompt_id
    fpSamplerNodeId.value = result.sampler_node_id
    fpTotalSections.value = result.total_sections

    recentGenerations.value.unshift({
      prompt_id: result.prompt_id,
      character: result.character,
      generation_type: `framepack-${result.model} ${result.seconds}s`,
      prompt_used: '',
      checkpoint: '',
      seed: 0,
    })
    if (recentGenerations.value.length > 10) recentGenerations.value.pop()

    // Connect WebSocket for live progress
    comfyProgress.connect()

    statusMessage.value = `FramePack submitted (${result.total_sections} sections, ~${result.total_steps} steps)`
  } catch (err: any) {
    statusMessage.value = `Error: ${err.message}`
  } finally {
    generating.value = false
  }
}

function startPolling(promptId: string) {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    try {
      const status = await api.getGenerationStatus(promptId)
      progressPercent.value = status.progress
      progressStatus.value = status.status
      if (status.status === 'completed') {
        if (pollTimer) clearInterval(pollTimer)
        pollTimer = null
        resultImages.value = status.images || []
        statusMessage.value = 'Generation complete'
      } else if (status.status === 'error') {
        if (pollTimer) clearInterval(pollTimer)
        pollTimer = null
        statusMessage.value = `Error: ${status.error || 'unknown'}`
      }
    } catch {
      // Ignore transient polling errors
    }
  }, 2000)
}

async function clearStuck() {
  try {
    const result = await api.clearStuckGenerations()
    statusMessage.value = result.message
  } catch (err: any) {
    statusMessage.value = `Error: ${err.message}`
  }
}
</script>
