<template>
  <div>
    <h2 style="font-size: 18px; font-weight: 500; margin-bottom: 16px;">Generate</h2>
    <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 24px;">
      Generate images or videos for characters using their SSOT profile from the database.
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

      <!-- Prompt -->
      <div style="margin-bottom: 12px;">
        <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">
          Prompt
          <span style="font-size: 11px; color: var(--text-muted);">(leave empty to use design_prompt from DB)</span>
        </label>
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

    <!-- Progress -->
    <div v-if="activePromptId" class="card" style="margin-bottom: 24px;">
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
        <span style="color: var(--text-muted);">seed={{ gen.seed }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useCharactersStore } from '@/stores/characters'
import { api } from '@/api/client'
import type { GenerateResponse } from '@/types'

const charactersStore = useCharactersStore()
const characters = computed(() => charactersStore.characters)

const selectedSlug = ref('')
const generationType = ref<'image' | 'video'>('image')
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

let pollTimer: ReturnType<typeof setInterval> | null = null

const selectedChar = computed(() =>
  characters.value.find(c => c.slug === selectedSlug.value)
)

function galleryImageUrl(filename: string) {
  return api.galleryImageUrl(filename)
}

function openImage(filename: string) {
  window.open(api.galleryImageUrl(filename), '_blank')
}

async function generate() {
  if (!selectedSlug.value) return
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

    // Start polling
    startPolling(result.prompt_id)
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
