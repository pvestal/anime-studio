<template>
  <div class="apple-music-video-sync">
    <!-- Step 1: Apple Music Connection -->
    <div v-if="!isConnected" class="connection-step">
      <h2>Step 1: Connect Apple Music</h2>
      <button @click="connectAppleMusic" class="connect-btn" :disabled="connecting">
        <i class="pi pi-apple"></i>
        {{ connecting ? 'Connecting...' : 'Sign in with Apple Music' }}
      </button>
    </div>

    <!-- Step 2: Select Playlist -->
    <div v-else-if="!selectedPlaylist" class="playlist-step">
      <h2>Step 2: Select a Playlist</h2>
      <div v-if="loadingPlaylists" class="loading">Loading your playlists...</div>
      <div v-else class="playlist-grid">
        <div
          v-for="playlist in playlists"
          :key="playlist.id"
          @click="selectPlaylist(playlist)"
          class="playlist-card"
        >
          <img v-if="playlist.artwork" :src="playlist.artwork" :alt="playlist.name" />
          <div class="playlist-info">
            <h3>{{ playlist.name }}</h3>
            <p>{{ playlist.trackCount }} tracks</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 3: Select Track and Generate Video -->
    <div v-else class="generation-step">
      <h2>Step 3: Generate Anime Video</h2>

      <div class="selected-playlist">
        <h3>{{ selectedPlaylist.name }}</h3>
        <button @click="selectedPlaylist = null" class="change-btn">Change Playlist</button>
      </div>

      <div v-if="loadingTracks" class="loading">Loading tracks...</div>

      <div v-else class="track-list">
        <div
          v-for="track in tracks"
          :key="track.id"
          class="track-item"
          :class="{ selected: selectedTrack?.id === track.id }"
          @click="selectedTrack = track"
        >
          <div class="track-info">
            <strong>{{ track.name }}</strong>
            <span>{{ track.artistName }} • {{ track.albumName }}</span>
            <span class="duration">{{ formatDuration(track.duration) }}</span>
          </div>
          <button
            v-if="selectedTrack?.id === track.id"
            @click.stop="generateVideo(track)"
            class="generate-btn"
            :disabled="generating"
          >
            {{ generating ? 'Generating...' : 'Generate Video' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Video Generation Progress -->
    <div v-if="generationJob" class="generation-progress">
      <h3>Generating Anime Video</h3>
      <div class="progress-info">
        <p><strong>Track:</strong> {{ generationJob.trackName }}</p>
        <p><strong>Status:</strong> {{ generationJob.status }}</p>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: generationJob.progress + '%' }"></div>
        </div>
        <p>{{ generationJob.progress }}% Complete</p>
      </div>
    </div>

    <!-- Generated Videos -->
    <div v-if="generatedVideos.length > 0" class="generated-videos">
      <h3>Generated Videos</h3>
      <div class="video-grid">
        <div v-for="video in generatedVideos" :key="video.id" class="video-card">
          <video :src="video.url" controls></video>
          <div class="video-info">
            <p><strong>{{ video.trackName }}</strong></p>
            <p>{{ video.artistName }}</p>
            <a :href="video.url" download class="download-btn">
              <i class="pi pi-download"></i> Download
            </a>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

// State
const isConnected = ref(false)
const connecting = ref(false)
const musicUserToken = ref(null)
const playlists = ref([])
const loadingPlaylists = ref(false)
const selectedPlaylist = ref(null)
const tracks = ref([])
const loadingTracks = ref(false)
const selectedTrack = ref(null)
const generating = ref(false)
const generationJob = ref(null)
const generatedVideos = ref([])
let music = null
let ws = null

// Connect to Apple Music
const connectAppleMusic = async () => {
  connecting.value = true

  try {
    // Load MusicKit if not loaded
    if (!window.MusicKit) {
      await loadMusicKitScript()
    }

    // Get developer token from Tower Auth
    const tokenResponse = await fetch('http://localhost:8088/api/auth/apple-music/developer-token')
    const { token } = await tokenResponse.json()

    // Configure MusicKit
    await window.MusicKit.configure({
      developerToken: token,
      app: {
        name: 'Tower Anime Production',
        build: '1.0.0'
      }
    })

    music = window.MusicKit.getInstance()

    // Authorize user
    musicUserToken.value = await music.authorize()

    if (musicUserToken.value) {
      // Store token in Tower Auth
      const storeResponse = await fetch('http://localhost:8088/api/auth/apple-music/authorize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_token: musicUserToken.value,
          user_id: 'patrick'
        })
      })

      if (storeResponse.ok) {
        isConnected.value = true
        await loadPlaylists()
      }
    }
  } catch (error) {
    console.error('Apple Music connection failed:', error)
    alert('Failed to connect to Apple Music: ' + error.message)
  } finally {
    connecting.value = false
  }
}

// Load MusicKit script
const loadMusicKitScript = () => {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://js-cdn.music.apple.com/musickit/v3/musickit.js'
    script.async = true
    script.onload = resolve
    script.onerror = reject
    document.head.appendChild(script)
  })
}

// Load user's playlists
const loadPlaylists = async () => {
  loadingPlaylists.value = true

  try {
    const response = await fetch('http://localhost:8315/api/apple-music/playlists', {
      headers: {
        'Music-User-Token': musicUserToken.value
      }
    })

    const data = await response.json()

    if (data.playlists) {
      playlists.value = data.playlists.map(p => ({
        id: p.id,
        name: p.attributes?.name || 'Untitled',
        trackCount: p.attributes?.trackCount || 0,
        artwork: p.attributes?.artwork?.url?.replace('{w}', '300').replace('{h}', '300')
      }))
    }
  } catch (error) {
    console.error('Failed to load playlists:', error)
    alert('Failed to load playlists')
  } finally {
    loadingPlaylists.value = false
  }
}

// Select a playlist
const selectPlaylist = async (playlist) => {
  selectedPlaylist.value = playlist
  loadingTracks.value = true

  try {
    const response = await fetch(`http://localhost:8315/api/apple-music/playlist/${playlist.id}/tracks`, {
      headers: {
        'Music-User-Token': musicUserToken.value
      }
    })

    const data = await response.json()

    if (data.tracks) {
      tracks.value = data.tracks.map(t => ({
        id: t.id,
        name: t.attributes?.name,
        artistName: t.attributes?.artistName,
        albumName: t.attributes?.albumName,
        duration: t.attributes?.durationInMillis,
        previewUrl: t.attributes?.previews?.[0]?.url
      }))
    }
  } catch (error) {
    console.error('Failed to load tracks:', error)
    alert('Failed to load tracks')
  } finally {
    loadingTracks.value = false
  }
}

// Generate video with selected track
const generateVideo = async (track) => {
  generating.value = true

  try {
    // Connect to WebSocket for progress updates
    connectWebSocket()

    // Create anime generation job
    const response = await fetch('http://localhost:8328/api/anime/generate-with-music', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        track: {
          id: track.id,
          name: track.name,
          artistName: track.artistName,
          duration: track.duration,
          previewUrl: track.previewUrl
        },
        settings: {
          style: 'anime',
          duration: Math.min(5, Math.floor(track.duration / 1000)), // Max 5 seconds
          resolution: '512x512',
          fps: 24
        },
        prompt: `Anime music video for "${track.name}" by ${track.artistName}, dynamic scenes, emotional, high quality anime style`
      })
    })

    if (!response.ok) {
      throw new Error('Failed to start generation')
    }

    const job = await response.json()

    generationJob.value = {
      id: job.job_id,
      trackName: track.name,
      artistName: track.artistName,
      status: 'starting',
      progress: 0
    }

    // Monitor progress via WebSocket
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ job_id: job.job_id }))
    }

  } catch (error) {
    console.error('Failed to generate video:', error)
    alert('Failed to start video generation: ' + error.message)
  } finally {
    generating.value = false
  }
}

// Connect to WebSocket for progress updates
const connectWebSocket = () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return
  }

  ws = new WebSocket('ws://localhost:8328/ws/progress')

  ws.onopen = () => {
    console.log('WebSocket connected')
  }

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)

    if (generationJob.value && data.job_id === generationJob.value.id) {
      generationJob.value.status = data.status
      generationJob.value.progress = data.progress || 0

      if (data.status === 'completed' && data.output_url) {
        // Add to generated videos
        generatedVideos.value.unshift({
          id: data.job_id,
          url: data.output_url,
          trackName: generationJob.value.trackName,
          artistName: generationJob.value.artistName,
          timestamp: new Date()
        })

        // Clear generation job
        setTimeout(() => {
          generationJob.value = null
        }, 3000)
      }

      if (data.status === 'failed') {
        alert('Video generation failed: ' + (data.error || 'Unknown error'))
        generationJob.value = null
      }
    }
  }

  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
  }
}

// Format duration from milliseconds
const formatDuration = (ms) => {
  if (!ms) return '0:00'
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
}

// Check for existing session on mount
onMounted(async () => {
  try {
    const response = await fetch('http://localhost:8088/api/auth/apple-music/status')
    const data = await response.json()

    if (data.authorized) {
      // Try to get stored token from vault
      const tokenResponse = await fetch('http://localhost:8088/api/auth/apple-music/token')
      if (tokenResponse.ok) {
        const tokenData = await tokenResponse.json()
        musicUserToken.value = tokenData.user_token
        isConnected.value = true
        await loadPlaylists()
      }
    }
  } catch (error) {
    console.log('No existing Apple Music session')
  }
})

// Cleanup on unmount
onUnmounted(() => {
  if (ws) {
    ws.close()
  }
})
</script>

<style scoped>
.apple-music-video-sync {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.connection-step, .playlist-step, .generation-step {
  min-height: 400px;
}

h2 {
  margin-bottom: 1.5rem;
  color: #333;
}

.connect-btn {
  padding: 1rem 2rem;
  font-size: 1.1rem;
  background: #000;
  color: white;
  border: none;
  border-radius: 0.5rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.connect-btn:hover:not(:disabled) {
  background: #333;
}

.connect-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading {
  text-align: center;
  padding: 2rem;
  color: #666;
}

.playlist-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1.5rem;
}

.playlist-card {
  cursor: pointer;
  transition: transform 0.2s;
  background: white;
  border-radius: 0.5rem;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.playlist-card:hover {
  transform: scale(1.05);
  box-shadow: 0 4px 16px rgba(0,0,0,0.2);
}

.playlist-card img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
}

.playlist-info {
  padding: 1rem;
}

.playlist-info h3 {
  margin: 0 0 0.5rem;
  font-size: 1rem;
}

.playlist-info p {
  margin: 0;
  color: #666;
  font-size: 0.9rem;
}

.selected-playlist {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem;
  background: #f5f5f5;
  border-radius: 0.5rem;
  margin-bottom: 1.5rem;
}

.change-btn {
  padding: 0.5rem 1rem;
  background: #666;
  color: white;
  border: none;
  border-radius: 0.25rem;
  cursor: pointer;
}

.change-btn:hover {
  background: #555;
}

.track-list {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #ddd;
  border-radius: 0.5rem;
}

.track-item {
  padding: 1rem;
  border-bottom: 1px solid #eee;
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  transition: background 0.2s;
}

.track-item:hover {
  background: #f9f9f9;
}

.track-item.selected {
  background: #e8f4fd;
}

.track-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.track-info strong {
  font-size: 1rem;
}

.track-info span {
  font-size: 0.9rem;
  color: #666;
}

.duration {
  font-size: 0.8rem;
  color: #999;
}

.generate-btn {
  padding: 0.5rem 1.5rem;
  background: #28a745;
  color: white;
  border: none;
  border-radius: 0.25rem;
  cursor: pointer;
}

.generate-btn:hover:not(:disabled) {
  background: #218838;
}

.generate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.generation-progress {
  margin-top: 2rem;
  padding: 1.5rem;
  background: #f0f8ff;
  border-radius: 0.5rem;
  border: 1px solid #b0d4ff;
}

.progress-info p {
  margin: 0.5rem 0;
}

.progress-bar {
  width: 100%;
  height: 30px;
  background: #e0e0e0;
  border-radius: 15px;
  overflow: hidden;
  margin: 1rem 0;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #4caf50, #8bc34a);
  transition: width 0.3s;
}

.generated-videos {
  margin-top: 2rem;
}

.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-top: 1rem;
}

.video-card {
  background: white;
  border-radius: 0.5rem;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.video-card video {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
}

.video-info {
  padding: 1rem;
}

.video-info p {
  margin: 0.25rem 0;
}

.download-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
  padding: 0.5rem 1rem;
  background: #007bff;
  color: white;
  text-decoration: none;
  border-radius: 0.25rem;
}

.download-btn:hover {
  background: #0056b3;
}
</style>