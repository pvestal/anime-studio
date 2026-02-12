<template>
  <div>
    <h2 style="font-size: 18px; font-weight: 500; margin-bottom: 16px;">Content Ingestion</h2>
    <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 24px;">
      Bring in content from any source. Extracted frames go to the Pending tab for approval.
    </p>

    <!-- Target selector: Character or Project -->
    <div style="margin-bottom: 24px; display: flex; gap: 16px; align-items: flex-end;">
      <div>
        <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Target</label>
        <div style="display: flex; gap: 4px;">
          <button
            :class="['btn', targetMode === 'character' ? 'btn-active' : '']"
            style="font-size: 12px; padding: 4px 12px;"
            @click="targetMode = 'character'"
          >
            Single Character
          </button>
          <button
            :class="['btn', targetMode === 'project' ? 'btn-active' : '']"
            style="font-size: 12px; padding: 4px 12px;"
            @click="targetMode = 'project'"
          >
            Entire Project
          </button>
        </div>
      </div>
      <div v-if="targetMode === 'character'" style="flex: 1;">
        <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Character</label>
        <select v-model="selectedCharacter" style="min-width: 280px;">
          <option value="">Select a character...</option>
          <option v-for="c in characters" :key="c.slug" :value="c.slug">
            {{ c.name }} ({{ c.project_name }})
          </option>
        </select>
      </div>
      <div v-else style="flex: 1;">
        <label style="font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 6px;">Project <span style="font-size: 11px; color: var(--text-muted);">(frames distributed to all characters)</span></label>
        <select v-model="selectedProject" style="min-width: 280px;">
          <option value="">Select a project...</option>
          <option v-for="p in projects" :key="p.name" :value="p.name">
            {{ p.name }} ({{ p.character_count }} characters)
          </option>
        </select>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px;">

      <!-- YouTube URL -->
      <div class="card">
        <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 12px;">YouTube Video</h3>
        <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
          {{ targetMode === 'project'
            ? 'Extract frames and distribute to ALL characters in the project for individual approval.'
            : 'Paste a YouTube URL to extract frames from the video.' }}
        </p>
        <input
          v-model="youtubeUrl"
          type="url"
          placeholder="https://youtube.com/watch?v=..."
          style="width: 100%; padding: 6px 10px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px; margin-bottom: 8px;"
        />
        <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap;">
          <label style="font-size: 12px; color: var(--text-muted);">Max frames:</label>
          <input
            v-model.number="maxFrames"
            type="number"
            min="1"
            max="300"
            style="width: 70px; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
          />
          <label style="font-size: 12px; color: var(--text-muted);">FPS:</label>
          <input
            v-model.number="youtubeFps"
            type="number"
            min="0.5"
            max="10"
            step="0.5"
            style="width: 60px; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
          />
          <span style="font-size: 11px; color: var(--text-muted);">(higher = more frames)</span>
        </div>
        <button
          class="btn"
          style="width: 100%; color: var(--accent-primary);"
          @click="ingestYoutube"
          :disabled="!youtubeUrl || youtubeLoading || (targetMode === 'character' && !selectedCharacter) || (targetMode === 'project' && !selectedProject)"
        >
          {{ youtubeLoading ? 'Downloading & extracting...' : targetMode === 'project' ? 'Extract to All Characters' : 'Extract Frames' }}
        </button>
        <div v-if="youtubeResult" style="margin-top: 8px; font-size: 12px; color: var(--status-success);">
          <template v-if="youtubeResult.characters_seeded">
            Extracted {{ youtubeResult.frames_extracted }} frames to {{ youtubeResult.characters_seeded }} characters. Check the Pending tab.
          </template>
          <template v-else>
            Extracted {{ youtubeResult.frames_extracted }} frames. Check the Pending tab.
          </template>
        </div>
        <div v-if="youtubeResult?.per_character" style="margin-top: 4px; font-size: 11px; color: var(--text-secondary);">
          <div v-for="(count, slug) in youtubeResult.per_character" :key="slug">
            {{ slug }}: {{ count }} frames
          </div>
        </div>
      </div>

      <!-- Image Upload -->
      <div class="card">
        <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 12px;">Upload Image</h3>
        <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
          Upload a single image directly to a character's dataset.
        </p>
        <div
          class="drop-zone"
          @drop.prevent="onImageDrop"
          @dragover.prevent
          @click="imageFileInput?.click()"
        >
          <template v-if="imageFile">
            {{ imageFile.name }}
          </template>
          <template v-else>
            Drop an image here or click to browse
          </template>
        </div>
        <input ref="imageFileInput" type="file" accept="image/*" style="display: none;" @change="onImageSelect" />
        <button
          class="btn"
          style="width: 100%; margin-top: 8px; color: var(--accent-primary);"
          @click="ingestImage"
          :disabled="!imageFile || !selectedCharacter || imageLoading"
        >
          {{ imageLoading ? 'Uploading...' : 'Upload' }}
        </button>
        <div v-if="imageResult" style="margin-top: 8px; font-size: 12px; color: var(--status-success);">
          Uploaded {{ imageResult.image }}. Check the Pending tab.
        </div>
      </div>

      <!-- Video Upload -->
      <div class="card">
        <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 12px;">Upload Video</h3>
        <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
          Upload a video to extract frames at a specified rate.
        </p>
        <div
          class="drop-zone"
          @drop.prevent="onVideoDrop"
          @dragover.prevent
          @click="videoFileInput?.click()"
        >
          <template v-if="videoFile">
            {{ videoFile.name }}
          </template>
          <template v-else>
            Drop a video here or click to browse
          </template>
        </div>
        <input ref="videoFileInput" type="file" accept="video/*" style="display: none;" @change="onVideoSelect" />
        <div style="display: flex; gap: 8px; align-items: center; margin-top: 8px;">
          <label style="font-size: 12px; color: var(--text-muted);">FPS:</label>
          <input
            v-model.number="videoFps"
            type="number"
            min="0.1"
            max="5"
            step="0.1"
            style="width: 70px; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
          />
          <span style="font-size: 11px; color: var(--text-muted);">(0.5 = 1 frame every 2 sec)</span>
        </div>
        <button
          class="btn"
          style="width: 100%; margin-top: 8px; color: var(--accent-primary);"
          @click="ingestVideo"
          :disabled="!videoFile || !selectedCharacter || videoLoading"
        >
          {{ videoLoading ? 'Extracting frames...' : 'Extract & Upload' }}
        </button>
        <div v-if="videoResult" style="margin-top: 8px; font-size: 12px; color: var(--status-success);">
          Extracted {{ videoResult.frames_extracted }} frames. Check the Pending tab.
        </div>
      </div>

      <!-- ComfyUI Scan -->
      <div class="card">
        <h3 style="font-size: 15px; font-weight: 500; margin-bottom: 12px;">Scan ComfyUI Output</h3>
        <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
          Scan /opt/ComfyUI/output/ for new images and match them to characters.
        </p>
        <button
          class="btn"
          style="width: 100%; color: var(--accent-primary);"
          @click="scanComfyUI"
          :disabled="scanLoading"
        >
          {{ scanLoading ? 'Scanning...' : 'Scan for New Images' }}
        </button>
        <div v-if="scanResult" style="margin-top: 8px; font-size: 12px;">
          <div style="color: var(--status-success);">{{ scanResult.new_images }} new images found</div>
          <div v-if="Object.keys(scanResult.matched).length > 0" style="margin-top: 4px; color: var(--text-secondary);">
            <div v-for="(count, slug) in scanResult.matched" :key="slug">
              {{ slug }}: {{ count }} images
            </div>
          </div>
          <div v-if="scanResult.unmatched_count > 0" style="margin-top: 4px; color: var(--text-muted);">
            {{ scanResult.unmatched_count }} unmatched files
          </div>
        </div>
      </div>

    </div>

    <!-- Error display -->
    <div v-if="error" class="card" style="margin-top: 16px; background: rgba(160,80,80,0.1); border-color: var(--status-error);">
      <p style="color: var(--status-error); font-size: 13px;">{{ error }}</p>
      <button class="btn" @click="error = ''" style="margin-top: 8px;">Dismiss</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'
import type { Character } from '@/types'

const characters = ref<Character[]>([])
const projects = ref<Array<{ id: number; name: string; default_style: string; character_count: number }>>([])
const selectedCharacter = ref('')
const selectedProject = ref('')
const targetMode = ref<'character' | 'project'>('project')
const error = ref('')

// YouTube
const youtubeUrl = ref('')
const maxFrames = ref(60)
const youtubeFps = ref(4)
const youtubeLoading = ref(false)
const youtubeResult = ref<{ frames_extracted: number; characters_seeded?: number; per_character?: Record<string, number> } | null>(null)

// Image upload
const imageFile = ref<File | null>(null)
const imageFileInput = ref<HTMLInputElement | null>(null)
const imageLoading = ref(false)
const imageResult = ref<{ image: string } | null>(null)

// Video upload
const videoFile = ref<File | null>(null)
const videoFileInput = ref<HTMLInputElement | null>(null)
const videoFps = ref(0.5)
const videoLoading = ref(false)
const videoResult = ref<{ frames_extracted: number } | null>(null)

// ComfyUI scan
const scanLoading = ref(false)
const scanResult = ref<{ new_images: number; matched: Record<string, number>; unmatched_count: number } | null>(null)

onMounted(async () => {
  try {
    const [charResp, projResp] = await Promise.all([
      api.getCharacters(),
      api.getProjects(),
    ])
    characters.value = charResp.characters
    projects.value = projResp.projects
  } catch (e) {
    error.value = 'Failed to load characters/projects'
  }
})

async function ingestYoutube() {
  youtubeLoading.value = true
  youtubeResult.value = null
  error.value = ''
  try {
    if (targetMode.value === 'project') {
      youtubeResult.value = await api.ingestYoutubeProject(
        youtubeUrl.value, selectedProject.value, maxFrames.value, youtubeFps.value,
      )
    } else {
      youtubeResult.value = await api.ingestYoutube(
        youtubeUrl.value, selectedCharacter.value, maxFrames.value, youtubeFps.value,
      )
    }
    youtubeUrl.value = ''
  } catch (e: any) {
    error.value = e.message || 'YouTube ingestion failed'
  } finally {
    youtubeLoading.value = false
  }
}

function onImageDrop(e: DragEvent) {
  const file = e.dataTransfer?.files[0]
  if (file && file.type.startsWith('image/')) imageFile.value = file
}

function onImageSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) imageFile.value = file
}

async function ingestImage() {
  if (!imageFile.value) return
  imageLoading.value = true
  imageResult.value = null
  error.value = ''
  try {
    imageResult.value = await api.ingestImage(imageFile.value, selectedCharacter.value)
    imageFile.value = null
  } catch (e: any) {
    error.value = e.message || 'Image upload failed'
  } finally {
    imageLoading.value = false
  }
}

function onVideoDrop(e: DragEvent) {
  const file = e.dataTransfer?.files[0]
  if (file && file.type.startsWith('video/')) videoFile.value = file
}

function onVideoSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) videoFile.value = file
}

async function ingestVideo() {
  if (!videoFile.value) return
  videoLoading.value = true
  videoResult.value = null
  error.value = ''
  try {
    videoResult.value = await api.ingestVideo(videoFile.value, selectedCharacter.value, videoFps.value)
    videoFile.value = null
  } catch (e: any) {
    error.value = e.message || 'Video ingestion failed'
  } finally {
    videoLoading.value = false
  }
}

async function scanComfyUI() {
  scanLoading.value = true
  scanResult.value = null
  error.value = ''
  try {
    scanResult.value = await api.scanComfyUI()
  } catch (e: any) {
    error.value = e.message || 'ComfyUI scan failed'
  } finally {
    scanLoading.value = false
  }
}
</script>

<style scoped>
.drop-zone {
  border: 2px dashed var(--border-primary);
  border-radius: 4px;
  padding: 20px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
  transition: border-color 150ms ease;
}
.drop-zone:hover {
  border-color: var(--accent-primary);
}
.btn-active {
  background: rgba(80, 120, 200, 0.2) !important;
  border-color: var(--accent-primary) !important;
  color: var(--accent-primary) !important;
  font-weight: 500;
}
</style>
