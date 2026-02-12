<template>
  <div class="character-editor">
    <div class="editor-header">
      <h3>Edit Character</h3>
      <div class="header-actions">
        <button
          class="btn-preview-prompt"
          @click="previewPrompt"
          :disabled="previewLoading"
        >
          <i class="pi pi-eye"></i> Preview Prompt
        </button>
        <button
          class="btn-save"
          @click="saveCharacter"
          :disabled="saving"
        >
          <i class="pi pi-save"></i> {{ saving ? 'Saving...' : 'Save' }}
        </button>
      </div>
    </div>

    <form @submit.prevent="saveCharacter" class="character-form">
      <!-- Basic Information -->
      <div class="form-section">
        <h4>Basic Information</h4>

        <div class="form-row">
          <div class="form-group">
            <label>Character Name</label>
            <input
              v-model="editedCharacter.character_name"
              type="text"
              class="form-input"
              required
            />
          </div>

          <div class="form-group">
            <label>Source Franchise</label>
            <input
              v-model="editedCharacter.source_franchise"
              type="text"
              class="form-input"
            />
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Age</label>
            <input
              v-model.number="editedCharacter.age"
              type="number"
              class="form-input"
              min="1"
              max="1000"
            />
          </div>

          <div class="form-group">
            <label>Gender</label>
            <select v-model="editedCharacter.gender" class="form-input">
              <option value="">Not specified</option>
              <option value="Female">Female</option>
              <option value="Male">Male</option>
              <option value="Non-binary">Non-binary</option>
              <option value="Other">Other</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label>Occupation</label>
          <input
            v-model="editedCharacter.occupation"
            type="text"
            class="form-input"
            placeholder="e.g., Warrior, Mage, Student, Engineer"
          />
        </div>
      </div>

      <!-- Physical Appearance -->
      <div class="form-section">
        <h4>Physical Appearance</h4>

        <div class="form-row">
          <div class="form-group">
            <label>Height</label>
            <input
              v-model="editedCharacter.height"
              type="text"
              class="form-input"
              placeholder="e.g., 5'6\", 170cm"
            />
          </div>

          <div class="form-group">
            <label>Build</label>
            <select v-model="editedCharacter.build" class="form-input">
              <option value="">Not specified</option>
              <option value="petite">Petite</option>
              <option value="slender">Slender</option>
              <option value="athletic">Athletic</option>
              <option value="average">Average</option>
              <option value="muscular">Muscular</option>
              <option value="stocky">Stocky</option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Hair Color</label>
            <input
              v-model="editedCharacter.hair_color"
              type="text"
              class="form-input"
              placeholder="e.g., Silver-white, Black, Blue"
            />
          </div>

          <div class="form-group">
            <label>Hair Style</label>
            <input
              v-model="editedCharacter.hair_style"
              type="text"
              class="form-input"
              placeholder="e.g., Long, Short spiky, Twin tails"
            />
          </div>
        </div>

        <div class="form-group">
          <label>Eye Color</label>
          <input
            v-model="editedCharacter.eye_color"
            type="text"
            class="form-input"
            placeholder="e.g., Piercing green, Golden iris"
          />
        </div>

        <div class="form-group">
          <label>Physical Description</label>
          <textarea
            v-model="editedCharacter.physical_description"
            class="form-textarea"
            rows="3"
            placeholder="Detailed physical description..."
          ></textarea>
        </div>

        <div class="form-group">
          <label>Distinctive Features</label>
          <textarea
            v-model="editedCharacter.distinctive_features"
            class="form-textarea"
            rows="2"
            placeholder="Scars, tattoos, unique features..."
          ></textarea>
        </div>
      </div>

      <!-- Character Development -->
      <div class="form-section">
        <h4>Character Development</h4>

        <div class="form-group">
          <label>Personality Traits</label>
          <textarea
            v-model="editedCharacter.personality_traits"
            class="form-textarea"
            rows="3"
            placeholder="Personality traits and characteristics..."
          ></textarea>
        </div>

        <div class="form-group">
          <label>Background Story</label>
          <textarea
            v-model="editedCharacter.background_story"
            class="form-textarea"
            rows="4"
            placeholder="Character's backstory and history..."
          ></textarea>
        </div>

        <div class="form-group">
          <label>Skills & Abilities</label>
          <textarea
            v-model="editedCharacter.skills_abilities"
            class="form-textarea"
            rows="3"
            placeholder="Special abilities, skills, powers..."
          ></textarea>
        </div>

        <div class="form-group">
          <label>Relationships</label>
          <textarea
            v-model="editedCharacter.relationships"
            class="form-textarea"
            rows="3"
            placeholder="Important relationships and connections..."
          ></textarea>
        </div>
      </div>

      <!-- Art & Style -->
      <div class="form-section">
        <h4>Art & Style</h4>

        <div class="form-row">
          <div class="form-group">
            <label>Visual Style</label>
            <select v-model="editedCharacter.visual_style" class="form-input">
              <option value="">Default</option>
              <option value="cyberpunk">Cyberpunk</option>
              <option value="traditional_anime">Traditional Anime</option>
              <option value="dark_fantasy">Dark Fantasy</option>
              <option value="steampunk">Steampunk</option>
              <option value="modern">Modern</option>
              <option value="fantasy">Fantasy</option>
              <option value="sci-fi">Sci-Fi</option>
            </select>
          </div>

          <div class="form-group">
            <label>Art Style</label>
            <select v-model="editedCharacter.art_style" class="form-input">
              <option value="">Default</option>
              <option value="photorealistic">Photorealistic</option>
              <option value="cel_shaded">Cel Shaded</option>
              <option value="watercolor">Watercolor</option>
              <option value="oil_painting">Oil Painting</option>
              <option value="digital_art">Digital Art</option>
              <option value="sketch">Sketch Style</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label>Custom Generation Prompts</label>
          <textarea
            v-model="editedCharacter.generation_prompts"
            class="form-textarea"
            rows="3"
            placeholder="Custom prompts to include in AI generation..."
          ></textarea>
        </div>
      </div>

      <!-- Notes -->
      <div class="form-section">
        <h4>Notes</h4>

        <div class="form-group">
          <label>Personal Notes</label>
          <textarea
            v-model="editedCharacter.notes"
            class="form-textarea"
            rows="3"
            placeholder="Personal notes and ideas..."
          ></textarea>
        </div>
      </div>

      <!-- Character Stats -->
      <div class="form-section" v-if="character.generation_count > 0">
        <h4>Character Stats</h4>

        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-label">Generations:</span>
            <span class="stat-value">{{ character.generation_count }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Consistency Score:</span>
            <span class="stat-value">{{ character.consistency_score }}/10</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Last Generated:</span>
            <span class="stat-value">{{ formatDate(character.last_generated) }}</span>
          </div>
        </div>
      </div>
    </form>

    <!-- Prompt Preview Modal -->
    <div v-if="showPromptPreview" class="modal-overlay" @click="showPromptPreview = false">
      <div class="modal-dialog" @click.stop>
        <div class="prompt-preview">
          <h3>Generated Prompt Preview</h3>
          <div class="prompt-display">
            <h4>Enhanced Prompt:</h4>
            <p class="prompt-text">{{ promptPreview?.enhanced_prompt }}</p>

            <h4>Prompt Components:</h4>
            <div class="prompt-parts">
              <div v-for="(value, key) in promptPreview?.prompt_parts" :key="key">
                <span class="part-label">{{ formatLabel(key) }}:</span>
                <span class="part-value">{{ value || 'Not specified' }}</span>
              </div>
            </div>
          </div>
          <div class="modal-actions">
            <button @click="showPromptPreview = false" class="btn-close">Close</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'CharacterEditor',
  props: {
    character: {
      type: Object,
      required: true
    }
  },

  data() {
    return {
      editedCharacter: {},
      saving: false,
      showPromptPreview: false,
      promptPreview: null,
      previewLoading: false
    }
  },

  watch: {
    character: {
      immediate: true,
      handler(newCharacter) {
        if (newCharacter) {
          this.editedCharacter = { ...newCharacter }
        }
      }
    }
  },

  methods: {
    async saveCharacter() {
      this.saving = true

      try {
        const response = await fetch(`/api/anime/characters/${this.character.id}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(this.editedCharacter)
        })

        if (response.ok) {
          const updatedCharacter = await response.json()
          this.$emit('updated', updatedCharacter)
          this.$toast.success('Character updated successfully!')
        } else {
          throw new Error('Failed to update character')
        }
      } catch (error) {
        this.$toast.error(`Failed to save character: ${error.message}`)
      } finally {
        this.saving = false
      }
    },

    async previewPrompt() {
      this.previewLoading = true

      try {
        const response = await fetch(
          `/api/anime/characters/${this.character.id}/prompt-preview?additional_prompt=high quality portrait`
        )

        if (response.ok) {
          this.promptPreview = await response.json()
          this.showPromptPreview = true
        } else {
          throw new Error('Failed to generate prompt preview')
        }
      } catch (error) {
        this.$toast.error(`Failed to preview prompt: ${error.message}`)
      } finally {
        this.previewLoading = false
      }
    },

    formatDate(dateString) {
      if (!dateString) return 'Never'
      return new Date(dateString).toLocaleDateString()
    },

    formatLabel(key) {
      return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
    }
  }
}
</script>

<style scoped>
.character-editor {
  height: 100%;
  overflow-y: auto;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.editor-header h3 {
  margin: 0;
  color: #00d4ff;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.btn-preview-prompt, .btn-save {
  background: linear-gradient(45deg, #00d4ff, #0099cc);
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  font-size: 0.9em;
  transition: all 0.3s ease;
}

.btn-preview-prompt:hover, .btn-save:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 212, 255, 0.3);
}

.btn-preview-prompt:disabled, .btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.character-form {
  display: flex;
  flex-direction: column;
  gap: 25px;
}

.form-section {
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
  padding: 20px;
}

.form-section h4 {
  margin: 0 0 15px 0;
  color: #ff00ff;
  font-size: 1.1em;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 15px;
  margin-bottom: 15px;
}

.form-group {
  display: flex;
  flex-direction: column;
  margin-bottom: 15px;
}

.form-group label {
  margin-bottom: 5px;
  color: #e0e0e0;
  font-weight: 500;
}

.form-input, .form-textarea {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  padding: 10px;
  color: white;
  font-size: 0.9em;
  transition: all 0.3s ease;
}

.form-input:focus, .form-textarea:focus {
  outline: none;
  border-color: #00d4ff;
  background: rgba(255, 255, 255, 0.08);
  box-shadow: 0 0 10px rgba(0, 212, 255, 0.2);
}

.form-textarea {
  resize: vertical;
  font-family: inherit;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 15px;
}

.stat-item {
  background: rgba(255, 255, 255, 0.05);
  padding: 10px 15px;
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-label {
  color: #a0a0a0;
}

.stat-value {
  color: #00d4ff;
  font-weight: bold;
}

/* Prompt Preview Modal */
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
  max-width: 700px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.prompt-preview h3 {
  margin: 0 0 20px 0;
  color: #00d4ff;
}

.prompt-display h4 {
  margin: 20px 0 10px 0;
  color: #ff00ff;
}

.prompt-text {
  background: rgba(255, 255, 255, 0.05);
  padding: 15px;
  border-radius: 6px;
  margin-bottom: 20px;
  line-height: 1.5;
  color: #e0e0e0;
  border-left: 3px solid #00d4ff;
}

.prompt-parts {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 10px;
  background: rgba(255, 255, 255, 0.03);
  padding: 15px;
  border-radius: 6px;
}

.part-label {
  color: #a0a0a0;
  font-weight: 500;
}

.part-value {
  color: #e0e0e0;
}

.modal-actions {
  margin-top: 20px;
  text-align: right;
}

.btn-close {
  background: rgba(255, 255, 255, 0.1);
  border: none;
  padding: 10px 20px;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn-close:hover {
  background: rgba(255, 255, 255, 0.2);
}

/* Responsive Design */
@media (max-width: 768px) {
  .form-row {
    grid-template-columns: 1fr;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .header-actions {
    flex-direction: column;
    gap: 5px;
  }
}
</style>