<template>
  <div class="character-studio">
    <div class="studio-header">
      <h2>Character Studio</h2>
      <p class="subtitle">Manage anime characters with AI-powered generation</p>
    </div>

    <div class="studio-layout">
      <!-- Character List Panel -->
      <div class="character-list-panel">
        <div class="panel-header">
          <h3>Characters</h3>
          <button
            class="btn-create-character"
            @click="showCreateDialog = true"
          >
            <i class="pi pi-plus"></i> New Character
          </button>
        </div>

        <div class="character-list">
          <div
            v-for="character in characters"
            :key="character.id"
            :class="['character-card', { active: selectedCharacter?.id === character.id }]"
            @click="selectCharacter(character)"
          >
            <div class="character-avatar">
              <img
                v-if="character.reference_images?.length > 0"
                :src="character.reference_images[0].url"
                :alt="character.character_name"
                @error="handleImageError"
              />
              <div v-else class="avatar-placeholder">
                {{ character.character_name.charAt(0) }}
              </div>
            </div>

            <div class="character-info">
              <h4>{{ character.character_name }}</h4>
              <p class="character-meta">
                {{ character.age ? `${character.age} years old` : 'Age unknown' }} •
                {{ character.gender || 'Gender not specified' }}
              </p>
              <p class="generation-count">
                Generated {{ character.generation_count }} times
              </p>
            </div>

            <div class="character-actions">
              <button
                class="btn-generate"
                @click.stop="generateCharacterImage(character)"
                :disabled="generatingCharacter === character.id"
              >
                <i class="pi pi-image"></i>
              </button>
              <button
                class="btn-edit"
                @click.stop="editCharacter(character)"
              >
                <i class="pi pi-pencil"></i>
              </button>
            </div>
          </div>
        </div>

        <div v-if="loading" class="loading-characters">
          Loading characters...
        </div>

        <div v-else-if="characters.length === 0" class="no-characters">
          <p>No characters found</p>
          <button @click="showCreateDialog = true">Create your first character</button>
        </div>
      </div>

      <!-- Character Details Panel -->
      <div class="character-details-panel" v-if="selectedCharacter">
        <CharacterEditor
          :character="selectedCharacter"
          @updated="onCharacterUpdated"
          @generate="onGenerateRequest"
        />
      </div>

      <!-- Character Generation Panel -->
      <div class="generation-panel" v-if="selectedCharacter">
        <CharacterGenerationPanel
          :character="selectedCharacter"
          @generation-complete="onGenerationComplete"
        />
      </div>
    </div>

    <!-- Create Character Dialog -->
    <div v-if="showCreateDialog" class="modal-overlay" @click="showCreateDialog = false">
      <div class="modal-dialog" @click.stop>
        <CharacterCreateDialog
          @created="onCharacterCreated"
          @cancel="showCreateDialog = false"
        />
      </div>
    </div>

    <!-- Generation Results -->
    <div v-if="generationResults.length > 0" class="generation-results">
      <h3>Recent Generations</h3>
      <div class="results-grid">
        <div
          v-for="result in generationResults"
          :key="result.id"
          class="result-card"
        >
          <img :src="result.image_url" :alt="`${result.character_name} generation`" />
          <div class="result-info">
            <h4>{{ result.character_name }}</h4>
            <p>{{ result.prompt }}</p>
            <small>{{ formatDate(result.created_at) }}</small>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import CharacterEditor from './CharacterEditor.vue'
import CharacterGenerationPanel from './CharacterGenerationPanel.vue'
import CharacterCreateDialog from './CharacterCreateDialog.vue'

export default {
  name: 'CharacterStudio',
  components: {
    CharacterEditor,
    CharacterGenerationPanel,
    CharacterCreateDialog
  },

  data() {
    return {
      characters: [],
      selectedCharacter: null,
      loading: false,
      showCreateDialog: false,
      generatingCharacter: null,
      generationResults: [],
      error: null
    }
  },

  async mounted() {
    await this.loadCharacters()
  },

  methods: {
    async loadCharacters() {
      this.loading = true
      try {
        const response = await fetch('/api/anime/characters')
        if (response.ok) {
          this.characters = await response.json()
          if (this.characters.length > 0 && !this.selectedCharacter) {
            this.selectedCharacter = this.characters[0]
          }
        } else {
          this.error = 'Failed to load characters'
        }
      } catch (error) {
        this.error = `Error loading characters: ${error.message}`
        console.error('Error loading characters:', error)
      } finally {
        this.loading = false
      }
    },

    selectCharacter(character) {
      this.selectedCharacter = character
    },

    editCharacter(character) {
      // The CharacterEditor component handles editing
      this.selectedCharacter = character
    },

    async generateCharacterImage(character) {
      this.generatingCharacter = character.id

      try {
        const response = await fetch(`/api/anime/characters/${character.id}/generate`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            prompt: 'high quality portrait',
            scene_type: 'portrait',
            style: 'anime',
            quality: 'high'
          })
        })

        if (response.ok) {
          const result = await response.json()
          this.$toast.success(`Generation started for ${character.character_name}`)

          // Update character generation count
          character.generation_count = result.generation_count

          // Add to generation results (mock for now)
          this.generationResults.unshift({
            id: Date.now(),
            character_name: character.character_name,
            prompt: result.enhanced_prompt,
            image_url: '/placeholder-generation.jpg', // Would be actual generated image
            created_at: new Date().toISOString()
          })
        } else {
          throw new Error('Generation failed')
        }
      } catch (error) {
        this.$toast.error(`Generation failed: ${error.message}`)
      } finally {
        this.generatingCharacter = null
      }
    },

    async onCharacterCreated(newCharacter) {
      await this.loadCharacters()
      this.selectedCharacter = newCharacter
      this.showCreateDialog = false
      this.$toast.success(`Created character: ${newCharacter.character_name}`)
    },

    onCharacterUpdated(updatedCharacter) {
      // Update the character in our list
      const index = this.characters.findIndex(c => c.id === updatedCharacter.id)
      if (index >= 0) {
        this.characters.splice(index, 1, updatedCharacter)
      }
      this.selectedCharacter = updatedCharacter
    },

    onGenerateRequest(generationParams) {
      // Handle generation request from CharacterEditor
      this.generateCharacterImage(this.selectedCharacter)
    },

    onGenerationComplete(result) {
      // Handle completed generation
      this.generationResults.unshift(result)
    },

    handleImageError(event) {
      // Replace broken images with placeholder
      event.target.style.display = 'none'
    },

    formatDate(dateString) {
      return new Date(dateString).toLocaleDateString()
    }
  }
}
</script>

<style scoped>
.character-studio {
  min-height: 100vh;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  color: #e0e0e0;
  padding: 20px;
}

.studio-header {
  text-align: center;
  margin-bottom: 30px;
}

.studio-header h2 {
  font-size: 2.5em;
  background: linear-gradient(45deg, #00d4ff, #ff00ff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: 10px;
}

.subtitle {
  color: #a0a0a0;
  font-size: 1.1em;
}

.studio-layout {
  display: grid;
  grid-template-columns: 350px 1fr 300px;
  gap: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

/* Character List Panel */
.character-list-panel {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 20px;
  backdrop-filter: blur(10px);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.panel-header h3 {
  margin: 0;
  color: #00d4ff;
}

.btn-create-character {
  background: linear-gradient(45deg, #00d4ff, #0099cc);
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  font-size: 0.9em;
  transition: all 0.3s ease;
}

.btn-create-character:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 212, 255, 0.3);
}

.character-list {
  max-height: 600px;
  overflow-y: auto;
}

.character-card {
  display: flex;
  align-items: center;
  padding: 15px;
  margin-bottom: 10px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 1px solid transparent;
}

.character-card:hover {
  background: rgba(255, 255, 255, 0.08);
  transform: translateX(5px);
}

.character-card.active {
  border-color: #00d4ff;
  background: rgba(0, 212, 255, 0.1);
}

.character-avatar {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  margin-right: 15px;
  overflow: hidden;
}

.character-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-placeholder {
  width: 100%;
  height: 100%;
  background: linear-gradient(45deg, #00d4ff, #ff00ff);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 1.2em;
  color: white;
}

.character-info {
  flex: 1;
}

.character-info h4 {
  margin: 0 0 5px 0;
  color: white;
}

.character-meta {
  margin: 0 0 5px 0;
  color: #a0a0a0;
  font-size: 0.9em;
}

.generation-count {
  margin: 0;
  color: #00d4ff;
  font-size: 0.8em;
}

.character-actions {
  display: flex;
  gap: 8px;
}

.btn-generate, .btn-edit {
  background: rgba(255, 255, 255, 0.1);
  border: none;
  padding: 8px;
  border-radius: 4px;
  color: white;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn-generate:hover {
  background: rgba(0, 212, 255, 0.3);
}

.btn-edit:hover {
  background: rgba(255, 0, 255, 0.3);
}

.btn-generate:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Character Details Panel */
.character-details-panel {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 20px;
  backdrop-filter: blur(10px);
}

/* Generation Panel */
.generation-panel {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 20px;
  backdrop-filter: blur(10px);
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-dialog {
  background: rgba(26, 26, 46, 0.95);
  border-radius: 12px;
  padding: 30px;
  max-width: 600px;
  width: 90%;
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

/* Generation Results */
.generation-results {
  margin-top: 30px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 20px;
  backdrop-filter: blur(10px);
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 15px;
  margin-top: 15px;
}

.result-card {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  overflow: hidden;
  transition: transform 0.3s ease;
}

.result-card:hover {
  transform: scale(1.02);
}

.result-card img {
  width: 100%;
  height: 150px;
  object-fit: cover;
}

.result-info {
  padding: 10px;
}

.result-info h4 {
  margin: 0 0 5px 0;
  color: white;
}

.result-info p {
  margin: 0 0 5px 0;
  color: #a0a0a0;
  font-size: 0.9em;
}

.result-info small {
  color: #666;
}

/* Loading and Empty States */
.loading-characters {
  text-align: center;
  padding: 40px;
  color: #a0a0a0;
}

.no-characters {
  text-align: center;
  padding: 40px;
  color: #a0a0a0;
}

.no-characters button {
  background: linear-gradient(45deg, #00d4ff, #0099cc);
  border: none;
  padding: 10px 20px;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  margin-top: 10px;
}

/* Responsive Design */
@media (max-width: 1200px) {
  .studio-layout {
    grid-template-columns: 1fr;
    gap: 15px;
  }

  .character-list-panel {
    order: 1;
  }

  .character-details-panel {
    order: 2;
  }

  .generation-panel {
    order: 3;
  }
}
</style>