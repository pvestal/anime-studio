<template>
  <div class="apple-music-auth">
    <div v-if="!isAuthenticated" class="auth-section">
      <Button
        @click="initializeAppleMusic"
        icon="pi pi-apple"
        label="Connect Apple Music"
        class="p-button-primary"
        :loading="loading"
      />
      <p class="auth-status">{{ statusMessage }}</p>
    </div>

    <div v-else class="connected-section">
      <div class="connection-status">
        <i class="pi pi-check-circle text-green-500"></i>
        <span>Apple Music Connected</span>
      </div>

      <div v-if="playlists.length > 0" class="playlists-section">
        <h3>Your Playlists</h3>
        <div class="playlist-grid">
          <div
            v-for="playlist in playlists"
            :key="playlist.id"
            class="playlist-card"
            @click="selectPlaylist(playlist)"
          >
            <img v-if="playlist.artwork" :src="playlist.artwork" :alt="playlist.name" />
            <div v-else class="playlist-placeholder">
              <i class="pi pi-list"></i>
            </div>
            <p>{{ playlist.name }}</p>
            <span class="track-count">{{ playlist.trackCount }} tracks</span>
          </div>
        </div>
      </div>

      <Button
        @click="loadPlaylists"
        icon="pi pi-refresh"
        label="Refresh Playlists"
        class="p-button-secondary"
        :loading="loadingPlaylists"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const isAuthenticated = ref(false)
const loading = ref(false)
const loadingPlaylists = ref(false)
const statusMessage = ref('')
const playlists = ref([])
const musicUserToken = ref(null)
let music = null

// Initialize MusicKit
const initializeAppleMusic = async () => {
  loading.value = true
  statusMessage.value = 'Loading MusicKit...'

  try {
    // Get developer token from Tower auth service
    const tokenResponse = await fetch('http://localhost:8088/api/auth/apple-music/developer-token')
    const { token } = await tokenResponse.json()

    // Load MusicKit.js if not already loaded
    if (!window.MusicKit) {
      await loadMusicKitScript()
    }

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
    statusMessage.value = 'Authorizing with Apple Music...'
    musicUserToken.value = await music.authorize()

    if (musicUserToken.value) {
      isAuthenticated.value = true
      statusMessage.value = 'Successfully connected!'

      // Store token in Tower auth
      await fetch('http://localhost:8088/api/auth/apple-music/store-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          musicUserToken: musicUserToken.value,
          provider: 'apple_music'
        })
      })

      // Load playlists
      await loadPlaylists()
    }
  } catch (error) {
    console.error('Apple Music auth error:', error)
    statusMessage.value = `Failed to connect: ${error.message}`
  } finally {
    loading.value = false
  }
}

// Load MusicKit.js script
const loadMusicKitScript = () => {
  return new Promise((resolve, reject) => {
    if (document.querySelector('script[src*="musickit.js"]')) {
      resolve()
      return
    }

    const script = document.createElement('script')
    script.src = 'https://js-cdn.music.apple.com/musickit/v3/musickit.js'
    script.async = true
    script.onload = resolve
    script.onerror = reject
    document.head.appendChild(script)
  })
}

// Load user playlists
const loadPlaylists = async () => {
  if (!musicUserToken.value) return

  loadingPlaylists.value = true

  try {
    // Call our backend with the user token
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
        artwork: p.attributes?.artwork?.url?.replace('{w}', '200').replace('{h}', '200')
      }))
    }
  } catch (error) {
    console.error('Failed to load playlists:', error)
  } finally {
    loadingPlaylists.value = false
  }
}

// Select playlist for anime sync
const selectPlaylist = async (playlist) => {
  const tracks = await loadPlaylistTracks(playlist.id)

  // Emit event to parent component
  emit('playlist-selected', {
    playlist,
    tracks
  })
}

// Load tracks from playlist
const loadPlaylistTracks = async (playlistId) => {
  try {
    const response = await fetch(`http://localhost:8315/api/apple-music/playlist/${playlistId}/tracks`, {
      headers: {
        'Music-User-Token': musicUserToken.value
      }
    })

    const data = await response.json()
    return data.tracks || []
  } catch (error) {
    console.error('Failed to load tracks:', error)
    return []
  }
}

// Check existing authentication on mount
onMounted(async () => {
  // Check if user has existing token in Tower auth
  try {
    const response = await fetch('http://localhost:8088/api/auth/apple-music/status')
    const data = await response.json()

    if (data.authenticated && data.musicUserToken) {
      musicUserToken.value = data.musicUserToken
      isAuthenticated.value = true
      await loadPlaylists()
    }
  } catch (error) {
    console.log('No existing Apple Music session')
  }
})

const emit = defineEmits(['playlist-selected'])
</script>

<style scoped>
.apple-music-auth {
  padding: 1rem;
}

.auth-section {
  text-align: center;
  padding: 2rem;
}

.auth-status {
  margin-top: 1rem;
  color: #666;
}

.connected-section {
  padding: 1rem;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
  padding: 0.5rem;
  background: #f0f9ff;
  border-radius: 0.5rem;
}

.playlists-section {
  margin: 2rem 0;
}

.playlists-section h3 {
  margin-bottom: 1rem;
}

.playlist-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.playlist-card {
  cursor: pointer;
  transition: transform 0.2s;
  text-align: center;
}

.playlist-card:hover {
  transform: scale(1.05);
}

.playlist-card img {
  width: 100%;
  border-radius: 0.5rem;
  margin-bottom: 0.5rem;
}

.playlist-placeholder {
  width: 100%;
  aspect-ratio: 1;
  background: #f5f5f5;
  border-radius: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 0.5rem;
}

.playlist-placeholder i {
  font-size: 3rem;
  color: #999;
}

.playlist-card p {
  font-weight: 600;
  margin: 0.5rem 0 0.25rem;
  font-size: 0.9rem;
}

.track-count {
  font-size: 0.8rem;
  color: #666;
}
</style>