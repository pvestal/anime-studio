<template>
  <div style="border-top: 1px solid var(--border-primary); padding-top: 12px; margin-top: 12px;">
    <button
      style="display: flex; align-items: center; gap: 6px; background: none; border: none; cursor: pointer; color: var(--text-secondary); font-size: 12px; font-family: var(--font-primary); padding: 0; width: 100%;"
      @click="panelOpen = !panelOpen"
    >
      <span style="font-size: 10px;">{{ panelOpen ? '\u25BC' : '\u25B6' }}</span>
      <span>Audio Track</span>
      <span v-if="currentAudio" style="margin-left: auto; font-size: 10px; padding: 1px 6px; border-radius: 3px; background: rgba(80, 160, 80, 0.2); color: var(--status-success);">assigned</span>
      <span v-else-if="musicAuthorized" style="margin-left: auto; font-size: 10px; padding: 1px 6px; border-radius: 3px; background: rgba(122, 162, 247, 0.15); color: var(--accent-primary);">ready</span>
    </button>

    <div v-if="panelOpen" style="margin-top: 10px;">

      <!-- Currently assigned track -->
      <div v-if="currentAudio" class="assigned-track">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
          <div style="font-size: 20px; line-height: 1;">&#9835;</div>
          <div style="min-width: 0; flex: 1;">
            <div style="font-size: 12px; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ currentAudio.track_name }}</div>
            <div style="font-size: 11px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ currentAudio.track_artist }}</div>
          </div>
        </div>
        <!-- Preview player -->
        <audio
          :src="currentAudio.preview_url"
          controls
          preload="none"
          style="width: 100%; height: 28px; margin-bottom: 6px;"
        ></audio>
        <!-- Fade controls -->
        <div style="display: flex; gap: 6px; margin-bottom: 6px;">
          <div style="flex: 1;">
            <label style="font-size: 10px; color: var(--text-muted); display: block;">Fade In (s)</label>
            <input
              type="number" min="0" max="10" step="0.5"
              :value="currentAudio.fade_in"
              @change="updateFade('fade_in', +($event.target as HTMLInputElement).value)"
              style="width: 100%; padding: 3px 6px; font-size: 11px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
            />
          </div>
          <div style="flex: 1;">
            <label style="font-size: 10px; color: var(--text-muted); display: block;">Fade Out (s)</label>
            <input
              type="number" min="0" max="10" step="0.5"
              :value="currentAudio.fade_out"
              @change="updateFade('fade_out', +($event.target as HTMLInputElement).value)"
              style="width: 100%; padding: 3px 6px; font-size: 11px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
            />
          </div>
          <div style="flex: 1;">
            <label style="font-size: 10px; color: var(--text-muted); display: block;">Offset (s)</label>
            <input
              type="number" min="0" max="30" step="1"
              :value="currentAudio.start_offset"
              @change="updateFade('start_offset', +($event.target as HTMLInputElement).value)"
              style="width: 100%; padding: 3px 6px; font-size: 11px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
            />
          </div>
        </div>
        <!-- Auto-duck toggle -->
        <div v-if="hasDialogue" style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
          <label style="font-size: 11px; color: var(--text-secondary); display: flex; align-items: center; gap: 4px; cursor: pointer;">
            <input
              type="checkbox"
              :checked="currentAudio.auto_duck ?? false"
              @change="updateAutoDuck(($event.target as HTMLInputElement).checked)"
              style="margin: 0;"
            />
            Auto-duck dialogue
          </label>
          <span style="font-size: 10px; color: var(--text-muted);">(lower music during speech)</span>
        </div>
        <button class="btn-small btn-danger" @click="removeAudio" :disabled="removing">
          {{ removing ? 'Removing...' : 'Remove Track' }}
        </button>
      </div>

      <!-- Auth status check -->
      <div v-else-if="checkingAuth" style="font-size: 12px; color: var(--text-muted);">Checking Apple Music...</div>

      <!-- Not authorized -->
      <div v-else-if="!musicAuthorized" style="font-size: 12px;">
        <div style="color: var(--text-secondary); margin-bottom: 8px;">
          Connect Apple Music to assign tracks to scenes.
        </div>
        <a
          href="/apple-music-auth"
          target="_blank"
          class="btn-small btn-primary"
          style="display: inline-block; text-decoration: none;"
          @click="scheduleRecheck"
        >Connect Apple Music</a>
      </div>

      <!-- Authorized: source tabs -->
      <div v-else>
        <!-- Source tabs (4 tabs) -->
        <div style="display: flex; gap: 0; margin-bottom: 10px; border-bottom: 1px solid var(--border-primary);">
          <button class="audio-tab" :class="{ active: audioSource === 'suggest' }" @click="audioSource = 'suggest'">Suggest</button>
          <button class="audio-tab" :class="{ active: audioSource === 'apple' }" @click="audioSource = 'apple'">Apple Music</button>
          <button class="audio-tab" :class="{ active: audioSource === 'generate' }" @click="audioSource = 'generate'">Generate</button>
          <button class="audio-tab" :class="{ active: audioSource === 'library' }" @click="audioSource = 'library'; loadLibraryTab()">Library</button>
        </div>

        <!-- ============================================================ -->
        <!-- Tab 1: Suggest (Echo Brain AI) -->
        <!-- ============================================================ -->
        <div v-if="audioSource === 'suggest'" style="display: flex; flex-direction: column; gap: 8px;">
          <div style="font-size: 11px; color: var(--text-muted);">
            Echo Brain analyzes this scene and suggests music parameters.
          </div>
          <div v-if="sceneMood" style="font-size: 11px; color: var(--text-secondary);">
            Scene mood: <strong>{{ sceneMood }}</strong>
            <span v-if="timeOfDay"> &middot; {{ timeOfDay }}</span>
          </div>
          <button class="btn-small btn-primary" @click="suggestMusic" :disabled="suggesting">
            {{ suggesting ? 'Analyzing...' : 'Auto-Suggest' }}
          </button>

          <div v-if="suggestion" class="suggestion-card">
            <div style="font-size: 12px; font-weight: 500; color: var(--text-primary); margin-bottom: 4px;">Suggestion</div>
            <div class="suggestion-row">
              <span class="suggestion-label">Mood:</span>
              <span class="suggestion-value">{{ suggestion.suggested_mood }}</span>
            </div>
            <div class="suggestion-row">
              <span class="suggestion-label">Genre:</span>
              <span class="suggestion-value">{{ suggestion.suggested_genre }}</span>
            </div>
            <div class="suggestion-row">
              <span class="suggestion-label">BPM:</span>
              <span class="suggestion-value">{{ suggestion.suggested_bpm }}</span>
            </div>
            <div class="suggestion-row">
              <span class="suggestion-label">Duration:</span>
              <span class="suggestion-value">{{ suggestion.suggested_duration }}s</span>
            </div>
            <div v-if="suggestion.reasoning" style="font-size: 10px; color: var(--text-muted); margin-top: 6px; font-style: italic;">
              {{ suggestion.reasoning }}
            </div>
            <div style="display: flex; gap: 6px; margin-top: 8px;">
              <button class="btn-small btn-primary" @click="generateFromSuggestion">Generate with These</button>
              <button class="btn-small btn-secondary" @click="tweakSuggestion">Tweak</button>
            </div>
          </div>
        </div>

        <!-- ============================================================ -->
        <!-- Tab 2: Apple Music (with Generate Inspired) -->
        <!-- ============================================================ -->
        <div v-else-if="audioSource === 'apple'">
          <!-- Playlist selector -->
          <div style="margin-bottom: 8px;">
            <label style="font-size: 10px; color: var(--text-muted); display: block; margin-bottom: 3px;">Playlist</label>
            <select
              v-model="selectedPlaylistId"
              @change="loadTracks"
              style="width: 100%; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
            >
              <option value="">Select playlist...</option>
              <option v-for="pl in playlists" :key="pl.id" :value="pl.id">{{ pl.name }}</option>
            </select>
          </div>

          <!-- Generate Inspired section (when playlist selected) -->
          <div v-if="selectedPlaylistId" style="margin-bottom: 8px; padding: 8px; background: var(--bg-secondary); border-radius: 4px; border: 1px solid var(--border-primary);">
            <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
              <span style="font-size: 11px; font-weight: 500; color: var(--text-primary);">Generate Inspired</span>
            </div>
            <!-- Playlist profile summary -->
            <div v-if="playlistProfile" style="font-size: 10px; color: var(--text-muted); margin-bottom: 6px;">
              {{ playlistProfile.dominant_genres.join(', ') }} &middot; {{ playlistProfile.avg_bpm }} BPM &middot; {{ playlistProfile.dominant_mood }}
            </div>
            <div style="display: flex; gap: 6px; margin-bottom: 6px;">
              <select v-model="inspiredMode" style="flex: 1; padding: 3px 6px; font-size: 11px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;">
                <option value="style_matched">Style Matched</option>
                <option value="cinematic">Cinematic</option>
                <option value="vocal_beats">Vocal Beats</option>
              </select>
              <input v-model.number="inspiredDuration" type="number" min="10" max="120" step="5" style="width: 60px; padding: 3px 6px; font-size: 11px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" placeholder="60s" />
            </div>
            <button class="btn-small btn-primary" @click="generateInspired" :disabled="generatingInspired">
              {{ generatingInspired ? 'Generating...' : 'Generate Inspired' }}
            </button>
            <div v-if="inspiredTaskId" style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">
              Task: {{ inspiredTaskId }} — {{ inspiredTaskStatus }}
            </div>
            <div v-if="inspiredTrackUrl" style="margin-top: 4px;">
              <audio :src="inspiredTrackUrl" controls preload="none" style="width: 100%; height: 28px; margin-bottom: 4px;"></audio>
              <button class="btn-small btn-primary" @click="assignInspiredTrack" :disabled="assigning">Use This Track</button>
            </div>
          </div>

          <!-- Loading -->
          <div v-if="loadingTracks" style="font-size: 11px; color: var(--text-muted); padding: 8px 0;">Loading tracks...</div>

          <!-- Track list -->
          <div v-else-if="tracks.length > 0" style="max-height: 200px; overflow-y: auto; border: 1px solid var(--border-primary); border-radius: 3px;">
            <div
              v-for="track in tracks"
              :key="track.catalog_id || track.library_id"
              class="track-row"
              @click="assignTrack(track)"
            >
              <div style="min-width: 0; flex: 1;">
                <div style="font-size: 11px; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                  {{ track.name }}
                </div>
                <div style="font-size: 10px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                  {{ track.artist }}
                  <span v-if="track.duration_ms"> &middot; {{ formatDuration(track.duration_ms) }}</span>
                </div>
              </div>
              <span v-if="track.preview_url" style="font-size: 10px; color: var(--accent-primary); flex-shrink: 0;">assign</span>
              <span v-else style="font-size: 10px; color: var(--text-muted); flex-shrink: 0;">no preview</span>
            </div>
          </div>

          <!-- Assigning indicator -->
          <div v-if="assigning" style="font-size: 11px; color: var(--accent-primary); margin-top: 6px;">Assigning track...</div>
        </div>

        <!-- ============================================================ -->
        <!-- Tab 3: Generate (ACE-Step) -->
        <!-- ============================================================ -->
        <div v-else-if="audioSource === 'generate'" style="display: flex; flex-direction: column; gap: 8px;">
          <div>
            <label style="font-size: 10px; color: var(--text-muted); display: block; margin-bottom: 3px;">Mood</label>
            <div style="display: flex; gap: 4px;">
              <select v-model="genMood" style="flex: 1; padding: 4px 6px; font-size: 12px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;">
                <option v-for="m in moods" :key="m" :value="m">{{ m }}</option>
              </select>
              <button v-if="sceneMood" class="btn-small btn-secondary" @click="genMood = sceneMood" title="Fill from scene mood" style="white-space: nowrap;">
                From scene
              </button>
            </div>
          </div>
          <div style="display: flex; gap: 6px;">
            <div style="flex: 1;">
              <label style="font-size: 10px; color: var(--text-muted); display: block; margin-bottom: 3px;">Genre</label>
              <input v-model="genGenre" type="text" placeholder="anime, orchestral..." style="width: 100%; padding: 3px 6px; font-size: 11px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
            </div>
            <div style="width: 60px;">
              <label style="font-size: 10px; color: var(--text-muted); display: block; margin-bottom: 3px;">BPM</label>
              <input v-model.number="genBpm" type="number" min="60" max="200" step="5" placeholder="120" style="width: 100%; padding: 3px 6px; font-size: 11px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
            </div>
            <div style="width: 60px;">
              <label style="font-size: 10px; color: var(--text-muted); display: block; margin-bottom: 3px;">Duration</label>
              <input v-model.number="genDuration" type="number" min="10" max="120" step="5" style="width: 100%; padding: 3px 6px; font-size: 11px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;" />
            </div>
          </div>
          <button class="btn-small btn-primary" @click="generateMusic" :disabled="generating">
            {{ generating ? 'Generating...' : 'Generate Track' }}
          </button>
          <div v-if="genTaskId" style="font-size: 11px; color: var(--text-muted);">
            Task: {{ genTaskId }} — {{ genTaskStatus }}
            <span v-if="genTaskStatus === 'completed'" style="color: var(--status-success);">Done!</span>
          </div>
          <div v-if="generatedTrackUrl" style="margin-top: 4px;">
            <audio :src="generatedTrackUrl" controls preload="none" style="width: 100%; height: 28px; margin-bottom: 4px;"></audio>
            <button class="btn-small btn-primary" @click="assignGeneratedTrack" :disabled="assigning">Use This Track</button>
          </div>
        </div>

        <!-- ============================================================ -->
        <!-- Tab 4: Library (Curated Playlists + All Generated) -->
        <!-- ============================================================ -->
        <div v-else-if="audioSource === 'library'">
          <!-- Curated Playlists Section -->
          <div style="margin-bottom: 10px;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
              <span style="font-size: 11px; font-weight: 500; color: var(--text-primary);">Curated Playlists</span>
              <button class="btn-small btn-secondary" @click="showNewPlaylistInput = !showNewPlaylistInput" style="font-size: 10px; padding: 2px 8px;">
                {{ showNewPlaylistInput ? 'Cancel' : '+ New' }}
              </button>
            </div>

            <!-- New playlist input -->
            <div v-if="showNewPlaylistInput" style="display: flex; gap: 4px; margin-bottom: 6px;">
              <input
                v-model="newPlaylistName"
                type="text"
                placeholder="Playlist name..."
                style="flex: 1; padding: 3px 6px; font-size: 11px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); border-radius: 3px;"
                @keyup.enter="createPlaylist"
              />
              <button class="btn-small btn-primary" @click="createPlaylist" :disabled="!newPlaylistName.trim()">Create</button>
            </div>

            <!-- Playlist list -->
            <div v-if="curatedPlaylists.length > 0" style="border: 1px solid var(--border-primary); border-radius: 3px; margin-bottom: 6px;">
              <div v-for="pl in curatedPlaylists" :key="pl.id">
                <div
                  class="track-row"
                  style="justify-content: space-between;"
                  @click="toggleCuratedPlaylist(pl.id)"
                >
                  <div style="display: flex; align-items: center; gap: 4px; min-width: 0; flex: 1;">
                    <span style="font-size: 10px;">{{ expandedPlaylistId === pl.id ? '\u25BC' : '\u25B6' }}</span>
                    <span style="font-size: 11px; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ pl.name }}</span>
                    <span style="font-size: 10px; color: var(--text-muted);">({{ pl.track_count || 0 }})</span>
                  </div>
                  <button
                    class="btn-small btn-danger"
                    style="font-size: 9px; padding: 1px 6px;"
                    @click.stop="deleteCuratedPlaylist(pl.id)"
                  >x</button>
                </div>
                <!-- Expanded tracks -->
                <div v-if="expandedPlaylistId === pl.id" style="padding: 0 4px 4px 16px;">
                  <div v-if="loadingCuratedTracks" style="font-size: 10px; color: var(--text-muted); padding: 4px;">Loading...</div>
                  <div v-else-if="curatedTracks.length === 0" style="font-size: 10px; color: var(--text-muted); padding: 4px;">No tracks yet</div>
                  <div v-for="ct in curatedTracks" :key="ct.track_id" class="track-row" style="padding: 4px 6px;">
                    <div style="min-width: 0; flex: 1;">
                      <div style="font-size: 10px; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ ct.track_name }}</div>
                      <div style="font-size: 9px; color: var(--text-muted);">{{ ct.track_artist }} &middot; {{ ct.source }}</div>
                    </div>
                    <div style="display: flex; gap: 4px; flex-shrink: 0;">
                      <button class="btn-tiny" @click.stop="assignCuratedTrack(ct)" title="Assign to scene">use</button>
                      <button class="btn-tiny btn-danger" @click.stop="removeFromPlaylist(pl.id, ct.track_id)" title="Remove">x</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px;">No curated playlists yet.</div>
          </div>

          <!-- All Generated Section -->
          <div>
            <div style="font-size: 11px; font-weight: 500; color: var(--text-primary); margin-bottom: 6px;">All Generated</div>
            <div v-if="loadingLibrary" style="font-size: 11px; color: var(--text-muted); padding: 8px 0;">Loading library...</div>
            <div v-else-if="generatedLibrary.length > 0" style="max-height: 200px; overflow-y: auto; border: 1px solid var(--border-primary); border-radius: 3px;">
              <div v-for="t in generatedLibrary" :key="t.filename" class="track-row">
                <div style="min-width: 0; flex: 1;" @click="assignLibraryTrack(t)">
                  <div style="font-size: 11px; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ t.mood }} — {{ t.genre || 'mixed' }}</div>
                  <div style="font-size: 10px; color: var(--text-muted);">{{ t.duration }}s &middot; {{ t.filename }}</div>
                </div>
                <div style="display: flex; gap: 4px; flex-shrink: 0;">
                  <span style="font-size: 10px; color: var(--accent-primary); cursor: pointer;" @click="assignLibraryTrack(t)">assign</span>
                  <div v-if="curatedPlaylists.length > 0" style="position: relative;">
                    <select
                      style="font-size: 10px; padding: 1px 4px; background: var(--bg-primary); color: var(--text-muted); border: 1px solid var(--border-primary); border-radius: 2px; cursor: pointer;"
                      @change="addToPlaylistFromLibrary(t, $event)"
                    >
                      <option value="">+ playlist</option>
                      <option v-for="pl in curatedPlaylists" :key="pl.id" :value="pl.id">{{ pl.name }}</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
            <div v-else style="font-size: 12px; color: var(--text-muted);">No generated tracks yet. Use the Generate tab to create music.</div>
          </div>
        </div>

        <!-- Error -->
        <div v-if="error" style="font-size: 11px; color: var(--status-error); margin-top: 6px;">{{ error }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onUnmounted } from 'vue'
import type { SceneAudio, AppleMusicTrack, AppleMusicPlaylist, MusicTrack, MusicSuggestion, CuratedPlaylist, CuratedPlaylistTrack } from '@/types'
import { scenesApi } from '@/api/scenes'

const props = defineProps<{
  sceneId: string | null
  audio: SceneAudio | null | undefined
  sceneMood: string
  sceneDescription: string
  timeOfDay: string
  hasDialogue: boolean
}>()

const emit = defineEmits<{
  'audio-changed': [audio: SceneAudio | null]
}>()

const panelOpen = ref(false)
const checkingAuth = ref(false)
const musicAuthorized = ref(false)
const playlists = ref<AppleMusicPlaylist[]>([])
const selectedPlaylistId = ref('')
const tracks = ref<AppleMusicTrack[]>([])
const loadingTracks = ref(false)
const assigning = ref(false)
const removing = ref(false)
const error = ref('')

const audioSource = ref<'suggest' | 'apple' | 'generate' | 'library'>('suggest')
const genMood = ref('tense')
const genGenre = ref('')
const genBpm = ref<number | null>(null)
const genDuration = ref(30)
const generating = ref(false)
const genTaskId = ref('')
const genTaskStatus = ref('')
const generatedTrackUrl = ref('')
const generatedFilename = ref('')
const generatedLibrary = ref<MusicTrack[]>([])
const loadingLibrary = ref(false)
let genPollTimer: ReturnType<typeof setInterval> | null = null

// Suggest tab state
const suggesting = ref(false)
const suggestion = ref<MusicSuggestion | null>(null)

// Apple Music inspired generation
const inspiredMode = ref('style_matched')
const inspiredDuration = ref(60)
const generatingInspired = ref(false)
const inspiredTaskId = ref('')
const inspiredTaskStatus = ref('')
const inspiredTrackUrl = ref('')
const inspiredFilename = ref('')
const playlistProfile = ref<{ dominant_genres: string[]; avg_bpm: number; dominant_mood: string } | null>(null)
let inspiredPollTimer: ReturnType<typeof setInterval> | null = null

// Library tab state
const curatedPlaylists = ref<CuratedPlaylist[]>([])
const expandedPlaylistId = ref<number | null>(null)
const curatedTracks = ref<CuratedPlaylistTrack[]>([])
const loadingCuratedTracks = ref(false)
const showNewPlaylistInput = ref(false)
const newPlaylistName = ref('')

const moods = ['tense', 'romantic', 'seductive', 'intimate', 'action', 'melancholy', 'comedic', 'threatening', 'powerful', 'desperate', 'vulnerable', 'peaceful', 'dominant', 'provocative', 'ambient']

const currentAudio = ref<SceneAudio | null>(props.audio ?? null)

watch(() => props.audio, (val) => {
  currentAudio.value = val ?? null
})

onMounted(() => {
  checkAuth()
})

async function checkAuth() {
  checkingAuth.value = true
  try {
    const status = await scenesApi.getAppleMusicStatus()
    musicAuthorized.value = status.authorized
    if (status.authorized) {
      await loadPlaylists()
    }
  } catch {
    musicAuthorized.value = false
  } finally {
    checkingAuth.value = false
  }
}

function scheduleRecheck() {
  const interval = setInterval(async () => {
    try {
      const status = await scenesApi.getAppleMusicStatus()
      if (status.authorized) {
        musicAuthorized.value = true
        await loadPlaylists()
        clearInterval(interval)
      }
    } catch { /* ignore */ }
  }, 5000)
  setTimeout(() => clearInterval(interval), 120000)
}

async function loadPlaylists() {
  try {
    const result = await scenesApi.getAppleMusicPlaylists()
    const rawData = result.data || []
    playlists.value = rawData.map((pl) => ({
      id: pl.id,
      name: pl.name || 'Untitled',
    }))
  } catch (e) {
    error.value = `Failed to load playlists: ${(e as Error).message}`
  }
}

async function loadTracks() {
  if (!selectedPlaylistId.value) {
    tracks.value = []
    playlistProfile.value = null
    return
  }
  loadingTracks.value = true
  error.value = ''
  playlistProfile.value = null
  try {
    const result = await scenesApi.getPlaylistTracks(selectedPlaylistId.value)
    tracks.value = result.tracks
    // Also analyze the playlist in background
    scenesApi.analyzePlaylist(selectedPlaylistId.value).then(profile => {
      playlistProfile.value = profile
    }).catch(() => {})
  } catch (e) {
    error.value = `Failed to load tracks: ${(e as Error).message}`
    tracks.value = []
  } finally {
    loadingTracks.value = false
  }
}

// --- Suggest Tab ---

async function suggestMusic() {
  suggesting.value = true
  suggestion.value = null
  error.value = ''
  try {
    suggestion.value = await scenesApi.suggestMusicForScene(
      props.sceneMood || 'dramatic',
      props.sceneDescription,
      props.timeOfDay,
    )
  } catch (e) {
    error.value = `Suggestion failed: ${(e as Error).message}`
  } finally {
    suggesting.value = false
  }
}

function generateFromSuggestion() {
  if (!suggestion.value) return
  genMood.value = suggestion.value.suggested_mood
  genGenre.value = suggestion.value.suggested_genre
  genBpm.value = suggestion.value.suggested_bpm
  genDuration.value = suggestion.value.suggested_duration
  audioSource.value = 'generate'
  // Auto-submit
  generateMusic()
}

function tweakSuggestion() {
  if (!suggestion.value) return
  genMood.value = suggestion.value.suggested_mood
  genGenre.value = suggestion.value.suggested_genre
  genBpm.value = suggestion.value.suggested_bpm
  genDuration.value = suggestion.value.suggested_duration
  audioSource.value = 'generate'
}

// --- Apple Music Inspired Generation ---

async function generateInspired() {
  if (!selectedPlaylistId.value) return
  generatingInspired.value = true
  inspiredTaskId.value = ''
  inspiredTaskStatus.value = ''
  inspiredTrackUrl.value = ''
  error.value = ''
  try {
    const result = await scenesApi.generateFromPlaylist(
      selectedPlaylistId.value,
      inspiredMode.value,
      inspiredDuration.value,
    )
    inspiredTaskId.value = result.task_id
    inspiredTaskStatus.value = 'queued'
    if (result.profile) {
      playlistProfile.value = result.profile
    }
    // Poll for completion
    inspiredPollTimer = setInterval(async () => {
      try {
        const status = await scenesApi.getMusicTaskStatus(inspiredTaskId.value)
        inspiredTaskStatus.value = status.status
        if (status.status === 'completed' && (status.output_path || status.cached_path)) {
          const outPath = status.cached_path || status.output_path || ''
          inspiredFilename.value = outPath.split('/').pop() || outPath
          inspiredTrackUrl.value = scenesApi.generatedMusicUrl(inspiredFilename.value)
          generatingInspired.value = false
          if (inspiredPollTimer) clearInterval(inspiredPollTimer)
        } else if (status.status === 'failed') {
          error.value = `Generation failed: ${status.error || 'unknown'}`
          generatingInspired.value = false
          if (inspiredPollTimer) clearInterval(inspiredPollTimer)
        }
      } catch { /* keep polling */ }
    }, 3000)
  } catch (e) {
    error.value = `Generate failed: ${(e as Error).message}`
    generatingInspired.value = false
  }
}

async function assignInspiredTrack() {
  if (!props.sceneId || !inspiredTrackUrl.value) return
  assigning.value = true
  error.value = ''
  try {
    const trackName = `${inspiredMode.value} inspired`
    await scenesApi.setSceneAudio(props.sceneId, {
      track_id: `ace-step:${inspiredFilename.value}`,
      preview_url: inspiredTrackUrl.value,
      track_name: trackName,
      track_artist: 'ACE-Step AI',
    })
    const newAudio: SceneAudio = {
      track_id: `ace-step:${inspiredFilename.value}`,
      track_name: trackName,
      track_artist: 'ACE-Step AI',
      preview_url: inspiredTrackUrl.value,
      fade_in: 1.0,
      fade_out: 2.0,
      start_offset: 0,
      generation_mode: inspiredMode.value,
      source_playlist_id: selectedPlaylistId.value,
    }
    currentAudio.value = newAudio
    emit('audio-changed', newAudio)
  } catch (e) {
    error.value = `Assign failed: ${(e as Error).message}`
  } finally {
    assigning.value = false
  }
}

// --- Track Assignment ---

async function assignTrack(track: AppleMusicTrack) {
  if (!track.preview_url || !props.sceneId) return
  assigning.value = true
  error.value = ''
  try {
    await scenesApi.setSceneAudio(props.sceneId, {
      track_id: track.catalog_id || track.library_id || '',
      preview_url: track.preview_url,
      track_name: track.name,
      track_artist: track.artist,
    })
    const newAudio: SceneAudio = {
      track_id: track.catalog_id || track.library_id || '',
      track_name: track.name,
      track_artist: track.artist,
      preview_url: track.preview_url,
      fade_in: 1.0,
      fade_out: 2.0,
      start_offset: 0,
    }
    currentAudio.value = newAudio
    emit('audio-changed', newAudio)
  } catch (e) {
    error.value = `Assign failed: ${(e as Error).message}`
  } finally {
    assigning.value = false
  }
}

async function removeAudio() {
  if (!props.sceneId) return
  removing.value = true
  try {
    await scenesApi.removeSceneAudio(props.sceneId)
    currentAudio.value = null
    emit('audio-changed', null)
  } catch (e) {
    error.value = `Remove failed: ${(e as Error).message}`
  } finally {
    removing.value = false
  }
}

async function updateFade(field: 'fade_in' | 'fade_out' | 'start_offset', value: number) {
  if (!props.sceneId || !currentAudio.value) return
  const updated = { ...currentAudio.value, [field]: value }
  try {
    await scenesApi.setSceneAudio(props.sceneId, {
      track_id: updated.track_id,
      preview_url: updated.preview_url,
      track_name: updated.track_name,
      track_artist: updated.track_artist,
      fade_in: updated.fade_in,
      fade_out: updated.fade_out,
      start_offset: updated.start_offset,
    })
    currentAudio.value = updated
    emit('audio-changed', updated)
  } catch { /* silent — user can retry */ }
}

async function updateAutoDuck(enabled: boolean) {
  if (!props.sceneId || !currentAudio.value) return
  const updated = { ...currentAudio.value, auto_duck: enabled }
  try {
    await scenesApi.setSceneAudio(props.sceneId, {
      track_id: updated.track_id,
      preview_url: updated.preview_url,
      track_name: updated.track_name,
      track_artist: updated.track_artist,
      fade_in: updated.fade_in,
      fade_out: updated.fade_out,
      start_offset: updated.start_offset,
    })
    currentAudio.value = updated
    emit('audio-changed', updated)
  } catch { /* silent */ }
}

// --- ACE-Step Direct Generation ---

async function generateMusic() {
  generating.value = true
  genTaskId.value = ''
  genTaskStatus.value = ''
  generatedTrackUrl.value = ''
  error.value = ''
  try {
    const result = await scenesApi.generateMusic({
      mood: genMood.value,
      genre: genGenre.value || undefined,
      duration: genDuration.value,
      bpm: genBpm.value || undefined,
    })
    genTaskId.value = result.task_id
    genTaskStatus.value = 'queued'
    genPollTimer = setInterval(async () => {
      try {
        const status = await scenesApi.getMusicTaskStatus(genTaskId.value)
        genTaskStatus.value = status.status
        if (status.status === 'completed' && (status.output_path || status.cached_path)) {
          const outPath = status.cached_path || status.output_path || ''
          generatedFilename.value = outPath.split('/').pop() || outPath
          generatedTrackUrl.value = scenesApi.generatedMusicUrl(generatedFilename.value)
          generating.value = false
          if (genPollTimer) clearInterval(genPollTimer)
        } else if (status.status === 'failed') {
          error.value = `Generation failed: ${status.error || 'unknown'}`
          generating.value = false
          if (genPollTimer) clearInterval(genPollTimer)
        }
      } catch { /* keep polling */ }
    }, 3000)
  } catch (e) {
    error.value = `Generate failed: ${(e as Error).message}`
    generating.value = false
  }
}

async function assignGeneratedTrack() {
  if (!props.sceneId || !generatedTrackUrl.value) return
  assigning.value = true
  error.value = ''
  try {
    await scenesApi.setSceneAudio(props.sceneId, {
      track_id: `ace-step:${generatedFilename.value}`,
      preview_url: generatedTrackUrl.value,
      track_name: `${genMood.value} ${genGenre.value || 'track'}`,
      track_artist: 'ACE-Step AI',
    })
    const newAudio: SceneAudio = {
      track_id: `ace-step:${generatedFilename.value}`,
      track_name: `${genMood.value} ${genGenre.value || 'track'}`,
      track_artist: 'ACE-Step AI',
      preview_url: generatedTrackUrl.value,
      fade_in: 1.0,
      fade_out: 2.0,
      start_offset: 0,
      generation_mode: 'manual',
    }
    currentAudio.value = newAudio
    emit('audio-changed', newAudio)
  } catch (e) {
    error.value = `Assign failed: ${(e as Error).message}`
  } finally {
    assigning.value = false
  }
}

// --- Library Tab ---

async function loadLibraryTab() {
  loadGeneratedLibrary()
  loadCuratedPlaylists()
}

async function loadGeneratedLibrary() {
  loadingLibrary.value = true
  try {
    const result = await scenesApi.listGeneratedMusic()
    generatedLibrary.value = result.tracks
  } catch {
    generatedLibrary.value = []
  } finally {
    loadingLibrary.value = false
  }
}

async function loadCuratedPlaylists() {
  try {
    const result = await scenesApi.listCuratedPlaylists()
    curatedPlaylists.value = result.playlists
  } catch {
    curatedPlaylists.value = []
  }
}

async function createPlaylist() {
  if (!newPlaylistName.value.trim()) return
  try {
    await scenesApi.createCuratedPlaylist(newPlaylistName.value.trim())
    newPlaylistName.value = ''
    showNewPlaylistInput.value = false
    await loadCuratedPlaylists()
  } catch (e) {
    error.value = `Create failed: ${(e as Error).message}`
  }
}

async function deleteCuratedPlaylist(id: number) {
  try {
    await scenesApi.deleteCuratedPlaylist(id)
    if (expandedPlaylistId.value === id) {
      expandedPlaylistId.value = null
      curatedTracks.value = []
    }
    await loadCuratedPlaylists()
  } catch (e) {
    error.value = `Delete failed: ${(e as Error).message}`
  }
}

async function toggleCuratedPlaylist(id: number) {
  if (expandedPlaylistId.value === id) {
    expandedPlaylistId.value = null
    curatedTracks.value = []
    return
  }
  expandedPlaylistId.value = id
  loadingCuratedTracks.value = true
  try {
    const result = await scenesApi.getCuratedPlaylistTracks(id)
    curatedTracks.value = result.tracks
  } catch {
    curatedTracks.value = []
  } finally {
    loadingCuratedTracks.value = false
  }
}

async function assignCuratedTrack(ct: CuratedPlaylistTrack) {
  if (!props.sceneId) return
  assigning.value = true
  error.value = ''
  try {
    await scenesApi.setSceneAudio(props.sceneId, {
      track_id: ct.track_id,
      preview_url: ct.preview_url,
      track_name: ct.track_name,
      track_artist: ct.track_artist,
    })
    const newAudio: SceneAudio = {
      track_id: ct.track_id,
      track_name: ct.track_name,
      track_artist: ct.track_artist,
      preview_url: ct.preview_url,
      fade_in: 1.0,
      fade_out: 2.0,
      start_offset: 0,
    }
    currentAudio.value = newAudio
    emit('audio-changed', newAudio)
  } catch (e) {
    error.value = `Assign failed: ${(e as Error).message}`
  } finally {
    assigning.value = false
  }
}

async function removeFromPlaylist(playlistId: number, trackId: string) {
  try {
    await scenesApi.removeFromCuratedPlaylist(playlistId, trackId)
    // Refresh tracks
    if (expandedPlaylistId.value === playlistId) {
      const result = await scenesApi.getCuratedPlaylistTracks(playlistId)
      curatedTracks.value = result.tracks
    }
    await loadCuratedPlaylists()
  } catch (e) {
    error.value = `Remove failed: ${(e as Error).message}`
  }
}

async function addToPlaylistFromLibrary(track: MusicTrack, event: Event) {
  const select = event.target as HTMLSelectElement
  const playlistId = parseInt(select.value)
  select.value = ''
  if (!playlistId) return
  try {
    const url = scenesApi.generatedMusicUrl(track.filename)
    await scenesApi.addToCuratedPlaylist(playlistId, {
      track_id: `ace-step:${track.filename}`,
      name: `${track.mood || 'generated'} ${track.genre || 'track'}`,
      artist: 'ACE-Step AI',
      preview_url: url,
      source: 'ace-step',
    })
    // Refresh if this playlist is expanded
    if (expandedPlaylistId.value === playlistId) {
      const result = await scenesApi.getCuratedPlaylistTracks(playlistId)
      curatedTracks.value = result.tracks
    }
    await loadCuratedPlaylists()
  } catch (e) {
    error.value = `Add failed: ${(e as Error).message}`
  }
}

async function assignLibraryTrack(track: MusicTrack) {
  if (!props.sceneId) return
  assigning.value = true
  error.value = ''
  const url = scenesApi.generatedMusicUrl(track.filename)
  try {
    await scenesApi.setSceneAudio(props.sceneId, {
      track_id: `ace-step:${track.filename}`,
      preview_url: url,
      track_name: `${track.mood} ${track.genre || 'track'}`,
      track_artist: 'ACE-Step AI',
    })
    const newAudio: SceneAudio = {
      track_id: `ace-step:${track.filename}`,
      track_name: `${track.mood} ${track.genre || 'track'}`,
      track_artist: 'ACE-Step AI',
      preview_url: url,
      fade_in: 1.0,
      fade_out: 2.0,
      start_offset: 0,
    }
    currentAudio.value = newAudio
    emit('audio-changed', newAudio)
  } catch (e) {
    error.value = `Assign failed: ${(e as Error).message}`
  } finally {
    assigning.value = false
  }
}

onUnmounted(() => {
  if (genPollTimer) clearInterval(genPollTimer)
  if (inspiredPollTimer) clearInterval(inspiredPollTimer)
})

function formatDuration(ms: number): string {
  const totalSec = Math.floor(ms / 1000)
  const min = Math.floor(totalSec / 60)
  const sec = totalSec % 60
  return `${min}:${String(sec).padStart(2, '0')}`
}
</script>

<style scoped>
.assigned-track {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  padding: 8px;
}
.track-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-primary);
}
.track-row:last-child {
  border-bottom: none;
}
.track-row:hover {
  background: var(--bg-tertiary);
}
.btn-small {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 3px;
  border: none;
  cursor: pointer;
  font-family: var(--font-primary);
}
.btn-tiny {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 2px;
  border: none;
  cursor: pointer;
  font-family: var(--font-primary);
  background: var(--accent-primary);
  color: white;
}
.btn-primary {
  background: var(--accent-primary);
  color: white;
}
.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
}
.btn-danger {
  background: rgba(160, 80, 80, 0.8);
  color: white;
}
.btn-danger:hover {
  background: rgba(180, 60, 60, 0.9);
}
.btn-small:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.audio-tab {
  padding: 4px 10px;
  font-size: 11px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-family: var(--font-primary);
}
.audio-tab:hover {
  color: var(--text-primary);
}
.audio-tab.active {
  color: var(--accent-primary);
  border-bottom-color: var(--accent-primary);
}
.suggestion-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 4px;
  padding: 8px;
}
.suggestion-row {
  display: flex;
  gap: 6px;
  font-size: 11px;
  padding: 2px 0;
}
.suggestion-label {
  color: var(--text-muted);
  min-width: 60px;
}
.suggestion-value {
  color: var(--text-primary);
  font-weight: 500;
}
</style>
