<template>
  <div class="character-create-dialog">
    <div class="dialog-header">
      <h3>Create New Character</h3>
      <button class="close-button" @click="$emit('cancel')">
        <i class="pi pi-times"></i>
      </button>
    </div>

    <form @submit.prevent="createCharacter" class="create-form">
      <!-- Quick Setup Section -->
      <div class="form-section">
        <h4>Quick Setup</h4>

        <div class="quick-templates">
          <div
            v-for="template in characterTemplates"
            :key="template.id"
            :class="['template-card', { active: selectedTemplate === template.id }]"
            @click="selectTemplate(template)"
          >
            <div class="template-icon">
              <i :class="template.icon"></i>
            </div>
            <div class="template-info">
              <h5>{{ template.name }}</h5>
              <p>{{ template.description }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Basic Information -->
      <div class="form-section">
        <h4>Basic Information</h4>

        <div class="form-row">
          <div class="form-group">
            <label>Character Name *</label>
            <input
              v-model="newCharacter.character_name"
              type="text"
              class="form-input"
              placeholder="Enter character name"
              required
            />
          </div>

          <div class="form-group">
            <label>Source Franchise</label>
            <input
              v-model="newCharacter.source_franchise"
              type="text"
              class="form-input"
              placeholder="e.g., Tower Studio Original"
            />
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Age</label>
            <input
              v-model.number="newCharacter.age"
              type="number"
              class="form-input"
              min="1"
              max="1000"
              placeholder="Age"
            />
          </div>

          <div class="form-group">
            <label>Gender</label>
            <select v-model="newCharacter.gender" class="form-input">
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
            v-model="newCharacter.occupation"
            type="text"
            class="form-input"
            placeholder="e.g., Warrior, Mage, Student, Engineer"
          />
        </div>
      </div>

      <!-- Appearance -->
      <div class="form-section">
        <h4>Appearance</h4>

        <div class="form-row">
          <div class="form-group">
            <label>Hair Color</label>
            <input
              v-model="newCharacter.hair_color"
              type="text"
              class="form-input"
              placeholder="e.g., Silver-white, Black, Blue"
            />
          </div>

          <div class="form-group">
            <label>Hair Style</label>
            <select v-model="newCharacter.hair_style" class="form-input">
              <option value="">Select style</option>
              <option value="long">Long</option>
              <option value="short">Short</option>
              <option value="medium">Medium</option>
              <option value="spiky">Spiky</option>
              <option value="twin tails">Twin Tails</option>
              <option value="ponytail">Ponytail</option>
              <option value="braided">Braided</option>
              <option value="curly">Curly</option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Eye Color</label>
            <input
              v-model="newCharacter.eye_color"
              type="text"
              class="form-input"
              placeholder="e.g., Piercing green, Golden iris"
            />
          </div>

          <div class="form-group">
            <label>Build</label>
            <select v-model="newCharacter.build" class="form-input">
              <option value="">Select build</option>
              <option value="petite">Petite</option>
              <option value="slender">Slender</option>
              <option value="athletic">Athletic</option>
              <option value="average">Average</option>
              <option value="muscular">Muscular</option>
              <option value="stocky">Stocky</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label>Physical Description</label>
          <textarea
            v-model="newCharacter.physical_description"
            class="form-textarea"
            rows="3"
            placeholder="Brief description of physical appearance..."
          ></textarea>
        </div>
      </div>

      <!-- Style & Personality -->
      <div class="form-section">
        <h4>Style & Personality</h4>

        <div class="form-row">
          <div class="form-group">
            <label>Visual Style</label>
            <select v-model="newCharacter.visual_style" class="form-input">
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
            <select v-model="newCharacter.art_style" class="form-input">
              <option value="">Default</option>
              <option value="photorealistic">Photorealistic</option>
              <option value="cel_shaded">Cel Shaded</option>
              <option value="watercolor">Watercolor</option>
              <option value="digital_art">Digital Art</option>
              <option value="sketch">Sketch Style</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label>Personality Traits</label>
          <textarea
            v-model="newCharacter.personality_traits"
            class="form-textarea"
            rows="3"
            placeholder="Key personality traits and characteristics..."
          ></textarea>
        </div>

        <div class="form-group">
          <label>Custom Generation Prompts</label>
          <textarea
            v-model="newCharacter.generation_prompts"
            class="form-textarea"
            rows="2"
            placeholder="Special prompts for AI generation..."
          ></textarea>
        </div>
      </div>

      <!-- Form Actions -->
      <div class="form-actions">
        <button
          type="button"
          class="btn-cancel"
          @click="$emit('cancel')"
        >
          Cancel
        </button>
        <button
          type="submit"
          class="btn-create"
          :disabled="creating || !newCharacter.character_name"
        >
          <i class="pi pi-plus"></i>
          {{ creating ? 'Creating...' : 'Create Character' }}
        </button>
      </div>
    </form>
  </div>
</template>

<script>
export default {
  name: 'CharacterCreateDialog',

  data() {
    return {
      creating: false,
      selectedTemplate: null,
      newCharacter: {
        character_name: '',
        source_franchise: 'Tower Studio Original',
        character_type: 'original',
        age: null,
        gender: '',
        physical_description: '',
        height: '',
        build: '',
        hair_color: '',
        hair_style: '',
        eye_color: '',
        distinctive_features: '',
        personality_traits: '',
        background_story: '',
        occupation: '',
        skills_abilities: '',
        relationships: '',
        visual_style: '',
        art_style: '',
        generation_prompts: '',
        notes: ''
      },
      characterTemplates: [
        {
          id: 'warrior',
          name: 'Warrior',
          description: 'Strong fighter with combat skills',
          icon: 'pi pi-bolt',
          defaults: {
            occupation: 'Warrior',
            build: 'athletic',
            personality_traits: 'Brave, determined, protective',
            skills_abilities: 'Combat expertise, weapon mastery, leadership',
            visual_style: 'fantasy'
          }
        },
        {
          id: 'mage',
          name: 'Mage',
          description: 'Magic user with mystical powers',
          icon: 'pi pi-star',
          defaults: {
            occupation: 'Mage',
            build: 'slender',
            personality_traits: 'Intelligent, curious, mystical',
            skills_abilities: 'Magic spells, arcane knowledge, potion making',
            visual_style: 'fantasy'
          }
        },
        {
          id: 'cyberpunk',
          name: 'Cyberpunk',
          description: 'Tech-enhanced future character',
          icon: 'pi pi-cog',
          defaults: {
            occupation: 'Hacker',
            hair_color: 'neon blue',
            eye_color: 'cybernetic implants',
            personality_traits: 'Tech-savvy, rebellious, street-smart',
            skills_abilities: 'Hacking, cybernetic enhancement, urban survival',
            visual_style: 'cyberpunk',
            generation_prompts: 'cyberpunk aesthetic, neon lighting, tech implants'
          }
        },
        {
          id: 'student',
          name: 'Student',
          description: 'School or academy character',
          icon: 'pi pi-book',
          defaults: {
            occupation: 'Student',
            age: 16,
            build: 'average',
            personality_traits: 'Studious, energetic, curious',
            visual_style: 'traditional_anime'
          }
        },
        {
          id: 'noble',
          name: 'Noble',
          description: 'Royal or aristocratic character',
          icon: 'pi pi-crown',
          defaults: {
            occupation: 'Noble',
            build: 'elegant',
            personality_traits: 'Refined, dignified, charismatic',
            skills_abilities: 'Diplomacy, etiquette, leadership',
            visual_style: 'fantasy'
          }
        },
        {
          id: 'custom',
          name: 'Custom',
          description: 'Start with blank template',
          icon: 'pi pi-palette',
          defaults: {}
        }
      ]
    }
  },

  methods: {
    selectTemplate(template) {
      this.selectedTemplate = template.id

      // Reset character to defaults
      this.newCharacter = {
        character_name: '',
        source_franchise: 'Tower Studio Original',
        character_type: 'original',
        age: null,
        gender: '',
        physical_description: '',
        height: '',
        build: '',
        hair_color: '',
        hair_style: '',
        eye_color: '',
        distinctive_features: '',
        personality_traits: '',
        background_story: '',
        occupation: '',
        skills_abilities: '',
        relationships: '',
        visual_style: '',
        art_style: '',
        generation_prompts: '',
        notes: ''
      }

      // Apply template defaults
      Object.assign(this.newCharacter, template.defaults)
    },

    async createCharacter() {
      this.creating = true

      try {
        const response = await fetch('/api/anime/characters', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(this.newCharacter)
        })

        if (response.ok) {
          const createdCharacter = await response.json()
          this.$emit('created', createdCharacter)
        } else {
          const error = await response.text()
          throw new Error(error)
        }
      } catch (error) {
        this.$toast.error(`Failed to create character: ${error.message}`)
      } finally {
        this.creating = false
      }
    }
  }
}
</script>

<style scoped>
.character-create-dialog {
  max-height: 90vh;
  overflow-y: auto;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.dialog-header h3 {
  margin: 0;
  color: #00d4ff;
}

.close-button {
  background: none;
  border: none;
  color: #a0a0a0;
  font-size: 1.2em;
  cursor: pointer;
  padding: 5px;
  border-radius: 4px;
  transition: all 0.3s ease;
}

.close-button:hover {
  background: rgba(255, 255, 255, 0.1);
  color: white;
}

.create-form {
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

/* Quick Templates */
.quick-templates {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px;
}

.template-card {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 15px;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  gap: 12px;
}

.template-card:hover {
  background: rgba(255, 255, 255, 0.08);
  transform: translateY(-2px);
}

.template-card.active {
  border-color: #00d4ff;
  background: rgba(0, 212, 255, 0.1);
}

.template-icon {
  background: linear-gradient(45deg, #00d4ff, #ff00ff);
  border-radius: 50%;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 1.2em;
}

.template-info h5 {
  margin: 0 0 5px 0;
  color: white;
}

.template-info p {
  margin: 0;
  color: #a0a0a0;
  font-size: 0.9em;
}

/* Form Styles */
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

/* Form Actions */
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 15px;
  padding-top: 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.btn-cancel {
  background: rgba(255, 255, 255, 0.1);
  border: none;
  padding: 12px 24px;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  font-size: 0.9em;
  transition: all 0.3s ease;
}

.btn-cancel:hover {
  background: rgba(255, 255, 255, 0.2);
}

.btn-create {
  background: linear-gradient(45deg, #00d4ff, #0099cc);
  border: none;
  padding: 12px 24px;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  font-size: 0.9em;
  font-weight: 600;
  transition: all 0.3s ease;
}

.btn-create:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 212, 255, 0.3);
}

.btn-create:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

/* Responsive Design */
@media (max-width: 768px) {
  .form-row {
    grid-template-columns: 1fr;
  }

  .quick-templates {
    grid-template-columns: 1fr;
  }

  .form-actions {
    flex-direction: column;
  }

  .btn-cancel, .btn-create {
    width: 100%;
  }
}
</style>