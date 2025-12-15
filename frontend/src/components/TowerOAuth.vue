<template>
  <div class="tower-oauth">
    <div class="auth-header">
      <h2>Tower Authentication</h2>
      <p class="subtitle">Sign in with your preferred service</p>
    </div>

    <div class="auth-providers">
      <!-- OAuth Providers -->
      <div
        v-for="provider in oauthProviders"
        :key="provider.name"
        class="auth-provider"
        :class="{ disabled: !provider.configured }"
      >
        <button
          @click="loginWithProvider(provider)"
          :disabled="!provider.configured || loading[provider.name]"
          class="provider-button"
        >
          <i :class="getProviderIcon(provider.name)"></i>
          <span>{{ getProviderLabel(provider.name) }}</span>
          <span v-if="loading[provider.name]" class="loading-spinner"></span>
        </button>
        <span v-if="!provider.configured" class="not-configured">Not configured</span>
      </div>

      <!-- Apple Music (special case) -->
      <div
        v-if="appleMusicProvider"
        class="auth-provider apple-music"
        :class="{ disabled: !appleMusicProvider.configured }"
      >
        <button
          @click="connectAppleMusic"
          :disabled="!appleMusicProvider.configured || loading['apple-music']"
          class="provider-button"
        >
          <i class="pi pi-apple"></i>
          <span>Connect Apple Music</span>
          <span v-if="loading['apple-music']" class="loading-spinner"></span>
        </button>
      </div>
    </div>

    <!-- Current Session Info -->
    <div v-if="currentSession" class="session-info">
      <h3>Current Session</h3>
      <div class="session-details">
        <p><strong>Provider:</strong> {{ currentSession.provider }}</p>
        <p><strong>Email:</strong> {{ currentSession.email || 'N/A' }}</p>
        <p><strong>Name:</strong> {{ currentSession.name || 'N/A' }}</p>
        <button @click="logout" class="logout-button">
          <i class="pi pi-sign-out"></i> Sign Out
        </button>
      </div>
    </div>

    <!-- Apple Music Status -->
    <div v-if="appleMusicConnected" class="apple-music-status">
      <i class="pi pi-check-circle text-green-500"></i>
      <span>Apple Music Connected</span>
      <button @click="refreshAppleMusicPlaylists" class="refresh-button">
        <i class="pi pi-refresh"></i> Refresh Playlists
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const oauthProviders = ref([])
const appleMusicProvider = ref(null)
const currentSession = ref(null)
const appleMusicConnected = ref(false)
const loading = ref({})

// Check authentication status on mount
onMounted(async () => {
  await loadProviders()
  await checkSession()
  await checkAppleMusicStatus()
})

// Load available OAuth providers
const loadProviders = async () => {
  try {
    const response = await fetch('http://localhost:8088/api/auth/providers')
    const data = await response.json()

    oauthProviders.value = data.providers.filter(p => p.type !== 'music-service')
    appleMusicProvider.value = data.providers.find(p => p.name === 'apple-music')
  } catch (error) {
    console.error('Failed to load providers:', error)
  }
}

// Check current session
const checkSession = async () => {
  const token = localStorage.getItem('tower_auth_token')
  if (!token) return

  try {
    const response = await fetch('http://localhost:8088/api/auth/session/validate', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })

    if (response.ok) {
      const data = await response.json()
      if (data.valid) {
        currentSession.value = data.session
      }
    }
  } catch (error) {
    console.error('Failed to validate session:', error)
  }
}

// Check Apple Music connection
const checkAppleMusicStatus = async () => {
  const sessionId = sessionStorage.getItem('tower_session_id')
  if (!sessionId) return

  try {
    const response = await fetch('http://localhost:8088/api/auth/apple-music/status', {
      headers: {
        'X-Session-Id': sessionId
      }
    })

    const data = await response.json()
    appleMusicConnected.value = data.authenticated
  } catch (error) {
    console.error('Failed to check Apple Music status:', error)
  }
}

// Login with OAuth provider
const loginWithProvider = (provider) => {
  if (!provider.configured || !provider.auth_url) return

  loading.value[provider.name] = true

  // Open OAuth flow in popup or redirect
  const width = 600
  const height = 700
  const left = window.screenX + (window.outerWidth - width) / 2
  const top = window.screenY + (window.outerHeight - height) / 2

  const authWindow = window.open(
    `http://localhost:8088${provider.auth_url}`,
    `${provider.name}-auth`,
    `width=${width},height=${height},left=${left},top=${top}`
  )

  // Listen for callback
  const checkInterval = setInterval(() => {
    if (authWindow.closed) {
      clearInterval(checkInterval)
      loading.value[provider.name] = false
      checkSession()
    }
  }, 500)
}

// Connect Apple Music
const connectAppleMusic = async () => {
  loading.value['apple-music'] = true

  try {
    // Load MusicKit.js
    if (!window.MusicKit) {
      await loadMusicKitScript()
    }

    // Get developer token
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

    const music = window.MusicKit.getInstance()

    // Authorize user
    const musicUserToken = await music.authorize()

    if (musicUserToken) {
      // Store token in Tower auth
      const storeResponse = await fetch('http://localhost:8088/api/auth/apple-music/store-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          musicUserToken: musicUserToken,
          provider: 'apple_music'
        })
      })

      const storeData = await storeResponse.json()
      if (storeData.session_id) {
        sessionStorage.setItem('tower_session_id', storeData.session_id)
        appleMusicConnected.value = true

        // Emit event for other components
        emit('apple-music-connected', {
          musicUserToken,
          sessionId: storeData.session_id
        })
      }
    }
  } catch (error) {
    console.error('Apple Music auth error:', error)
  } finally {
    loading.value['apple-music'] = false
  }
}

// Load MusicKit script
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

// Refresh Apple Music playlists
const refreshAppleMusicPlaylists = async () => {
  emit('refresh-apple-music')
}

// Logout
const logout = () => {
  localStorage.removeItem('tower_auth_token')
  sessionStorage.removeItem('tower_session_id')
  currentSession.value = null
  appleMusicConnected.value = false
  emit('logout')
}

// Get provider icon
const getProviderIcon = (name) => {
  const icons = {
    google: 'pi pi-google',
    github: 'pi pi-github',
    apple: 'pi pi-apple'
  }
  return icons[name] || 'pi pi-sign-in'
}

// Get provider label
const getProviderLabel = (name) => {
  const labels = {
    google: 'Sign in with Google',
    github: 'Sign in with GitHub',
    apple: 'Sign in with Apple'
  }
  return labels[name] || `Sign in with ${name}`
}

const emit = defineEmits(['apple-music-connected', 'refresh-apple-music', 'logout'])
</script>

<style scoped>
.tower-oauth {
  padding: 2rem;
  max-width: 600px;
  margin: 0 auto;
}

.auth-header {
  text-align: center;
  margin-bottom: 2rem;
}

.auth-header h2 {
  margin: 0;
  font-size: 1.8rem;
}

.subtitle {
  color: #666;
  margin-top: 0.5rem;
}

.auth-providers {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 2rem;
}

.auth-provider {
  position: relative;
}

.provider-button {
  width: 100%;
  padding: 1rem;
  font-size: 1rem;
  border: 1px solid #ddd;
  border-radius: 0.5rem;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.provider-button:hover:not(:disabled) {
  background: #f5f5f5;
  border-color: #999;
}

.provider-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.provider-button i {
  font-size: 1.2rem;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #f3f3f3;
  border-top: 2px solid #333;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.not-configured {
  position: absolute;
  top: 50%;
  right: 1rem;
  transform: translateY(-50%);
  color: #999;
  font-size: 0.9rem;
}

.session-info {
  padding: 1rem;
  background: #f0f9ff;
  border-radius: 0.5rem;
  margin-bottom: 1rem;
}

.session-info h3 {
  margin: 0 0 1rem;
  font-size: 1.2rem;
}

.session-details p {
  margin: 0.5rem 0;
}

.logout-button {
  margin-top: 1rem;
  padding: 0.5rem 1rem;
  background: #dc3545;
  color: white;
  border: none;
  border-radius: 0.25rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.logout-button:hover {
  background: #c82333;
}

.apple-music-status {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: #e8f5e9;
  border-radius: 0.5rem;
}

.refresh-button {
  margin-left: auto;
  padding: 0.5rem 1rem;
  background: #4caf50;
  color: white;
  border: none;
  border-radius: 0.25rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.refresh-button:hover {
  background: #45a049;
}
</style>