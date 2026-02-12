<template>
  <div class="project-bible-interface">
    <!-- Header -->
    <div class="bible-header">
      <h3>Project Bible</h3>
      <div class="bible-controls">
        <button @click="showCharacterDialog = true" class="control-button primary">
          <i class="pi pi-plus"></i>
          Add Character
        </button>
        <button @click="exportBible" class="control-button secondary">
          <i class="pi pi-download"></i>
          Export
        </button>
        <button @click="importBible" class="control-button secondary">
          <i class="pi pi-upload"></i>
          Import
        </button>
      </div>
    </div>

    <!-- Tab Navigation -->
    <div class="bible-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        @click="activeTab = tab.id"
        :class="['tab-button', { active: activeTab === tab.id }]"
      >
        <i :class="tab.icon"></i>
        {{ tab.label }}
      </button>
    </div>

    <!-- Characters Tab -->
    <div v-if="activeTab === 'characters'" class="tab-content">
      <div class="characters-section">
        <!-- Search and Filters -->
        <div class="search-controls">
          <input
            v-model="characterSearch"
            placeholder="Search characters..."
            class="search-input"
          />
          <select v-model="characterFilter" class="filter-select">
            <option value="">All Types</option>
            <option value="protagonist">Protagonist</option>
            <option value="antagonist">Antagonist</option>
            <option value="supporting">Supporting</option>
            <option value="background">Background</option>
          </select>
          <button @click="refreshCharacters" class="refresh-button">
            <i class="pi pi-refresh"></i>
          </button>
        </div>

        <!-- Characters Table -->
        <div class="characters-table">
          <div class="table-header">
            <div class="table-cell">Name</div>
            <div class="table-cell">Type</div>
            <div class="table-cell">Age</div>
            <div class="table-cell">Status</div>
            <div class="table-cell">Consistency</div>
            <div class="table-cell">Actions</div>
          </div>

          <div
            v-for="character in filteredCharacters"
            :key="character.id"
            :class="['table-row', { selected: selectedCharacter?.id === character.id }]"
            @click="selectCharacter(character)"
          >
            <div class="table-cell">
              <div class="character-name">
                <img
                  v-if="character.avatar_url"
                  :src="character.avatar_url"
                  class="character-avatar"
                  @error="character.avatar_url = null"
                />
                <div class="character-placeholder" v-else>
                  {{ character.name.charAt(0) }}
                </div>
                {{ character.name }}
              </div>
            </div>
            <div class="table-cell">
              <span :class="['type-badge', character.type]">
                {{ character.type }}
              </span>
            </div>
            <div class="table-cell">{{ character.age || 'Unknown' }}</div>
            <div class="table-cell">
              <span :class="['status-indicator', character.status]">
                {{ character.status }}
              </span>
            </div>
            <div class="table-cell">
              <div class="consistency-meter">
                <div
                  class="consistency-fill"
                  :style="{ width: (character.consistency_score || 0) + '%' }"
                ></div>
                <span class="consistency-text">{{ character.consistency_score || 0 }}%</span>
              </div>
            </div>
            <div class="table-cell">
              <button @click.stop="editCharacter(character)" class="action-button">
                <i class="pi pi-pencil"></i>
              </button>
              <button @click.stop="generateCharacterVariant(character)" class="action-button">
                <i class="pi pi-palette"></i>
              </button>
              <button @click.stop="deleteCharacter(character)" class="action-button danger">
                <i class="pi pi-trash"></i>
              </button>
            </div>
          </div>
        </div>

        <!-- Character Details Panel -->
        <div v-if="selectedCharacter" class="character-details">
          <div class="details-header">
            <h4>{{ selectedCharacter.name }}</h4>
            <span :class="['type-badge', selectedCharacter.type]">
              {{ selectedCharacter.type }}
            </span>
          </div>

          <div class="details-grid">
            <div class="detail-section">
              <label>Physical Description</label>
              <textarea
                v-model="selectedCharacter.physical_description"
                rows="3"
                class="detail-textarea"
              ></textarea>
            </div>

            <div class="detail-section">
              <label>Personality</label>
              <textarea
                v-model="selectedCharacter.personality"
                rows="3"
                class="detail-textarea"
              ></textarea>
            </div>

            <div class="detail-section">
              <label>Background</label>
              <textarea
                v-model="selectedCharacter.background"
                rows="3"
                class="detail-textarea"
              ></textarea>
            </div>

            <div class="detail-section">
              <label>Relationships</label>
              <textarea
                v-model="selectedCharacter.relationships"
                rows="3"
                class="detail-textarea"
              ></textarea>
            </div>
          </div>

          <button @click="saveCharacterDetails" class="save-button">
            <i class="pi pi-save"></i>
            Save Changes
          </button>
        </div>
      </div>
    </div>

    <!-- World Building Tab -->
    <div v-if="activeTab === 'world'" class="tab-content">
      <div class="world-section">
        <div class="world-categories">
          <button
            v-for="category in worldCategories"
            :key="category.id"
            @click="activeWorldCategory = category.id"
            :class="['category-button', { active: activeWorldCategory === category.id }]"
          >
            <i :class="category.icon"></i>
            {{ category.label }}
          </button>
        </div>

        <div class="world-content">
          <div class="world-editor">
            <div class="editor-toolbar">
              <button @click="formatText('bold')" class="format-button">
                <i class="pi pi-bold"></i>
              </button>
              <button @click="formatText('italic')" class="format-button">
                <i class="pi pi-italic"></i>
              </button>
              <button @click="insertTemplate" class="format-button">
                <i class="pi pi-file"></i>
                Template
              </button>
            </div>

            <textarea
              ref="worldEditor"
              v-model="worldContent[activeWorldCategory]"
              class="world-textarea"
              placeholder="Start writing your world-building notes..."
            ></textarea>

            <div class="word-count">
              Words: {{ getWordCount(worldContent[activeWorldCategory]) }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Consistency Tab -->
    <div v-if="activeTab === 'consistency'" class="tab-content">
      <div class="consistency-section">
        <div class="consistency-controls">
          <button @click="runConsistencyCheck" class="control-button primary" :disabled="checkingConsistency">
            <i class="pi pi-search"></i>
            {{ checkingConsistency ? 'Checking...' : 'Run Consistency Check' }}
          </button>
          <button @click="fixInconsistencies" class="control-button secondary" :disabled="!hasInconsistencies">
            <i class="pi pi-wrench"></i>
            Auto-Fix Issues
          </button>
        </div>

        <div class="consistency-results">
          <div v-for="issue in consistencyIssues" :key="issue.id" class="consistency-issue">
            <div class="issue-header">
              <span :class="['issue-severity', issue.severity]">
                {{ issue.severity.toUpperCase() }}
              </span>
              <span class="issue-type">{{ issue.type }}</span>
              <span class="issue-character">{{ issue.character_name }}</span>
            </div>
            <div class="issue-description">{{ issue.description }}</div>
            <div class="issue-suggestion" v-if="issue.suggestion">
              <strong>Suggestion:</strong> {{ issue.suggestion }}
            </div>
            <div class="issue-actions">
              <button @click="applyFix(issue)" class="fix-button">Apply Fix</button>
              <button @click="ignoreIssue(issue)" class="ignore-button">Ignore</button>
            </div>
          </div>

          <div v-if="consistencyIssues.length === 0 && hasRunCheck" class="no-issues">
            <i class="pi pi-check-circle"></i>
            No consistency issues found!
          </div>
        </div>
      </div>
    </div>

    <!-- Character Dialog -->
    <div v-if="showCharacterDialog" class="dialog-overlay" @click="showCharacterDialog = false">
      <div class="character-dialog" @click.stop>
        <div class="dialog-header">
          <h4>{{ editingCharacter ? 'Edit Character' : 'Add New Character' }}</h4>
          <button @click="showCharacterDialog = false" class="close-button">
            <i class="pi pi-times"></i>
          </button>
        </div>

        <div class="dialog-content">
          <div class="form-group">
            <label>Name</label>
            <input v-model="characterForm.name" class="form-input" />
          </div>

          <div class="form-group">
            <label>Type</label>
            <select v-model="characterForm.type" class="form-select">
              <option value="protagonist">Protagonist</option>
              <option value="antagonist">Antagonist</option>
              <option value="supporting">Supporting</option>
              <option value="background">Background</option>
            </select>
          </div>

          <div class="form-group">
            <label>Age</label>
            <input v-model="characterForm.age" type="number" class="form-input" />
          </div>

          <div class="form-group">
            <label>Physical Description</label>
            <textarea v-model="characterForm.physical_description" rows="3" class="form-textarea"></textarea>
          </div>
        </div>

        <div class="dialog-actions">
          <button @click="showCharacterDialog = false" class="dialog-button secondary">Cancel</button>
          <button @click="saveCharacter" class="dialog-button primary">Save</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive, computed, onMounted } from 'vue'

export default {
  name: 'ProjectBibleInterface',
  props: {
    projectId: {
      type: [String, Number],
      required: true
    }
  },
  setup(props) {
    const activeTab = ref('characters')
    const activeWorldCategory = ref('setting')
    const characters = ref([])
    const selectedCharacter = ref(null)
    const characterSearch = ref('')
    const characterFilter = ref('')
    const showCharacterDialog = ref(false)
    const editingCharacter = ref(false)
    const checkingConsistency = ref(false)
    const consistencyIssues = ref([])
    const hasRunCheck = ref(false)

    const tabs = [
      { id: 'characters', label: 'Characters', icon: 'pi pi-users' },
      { id: 'world', label: 'World Building', icon: 'pi pi-globe' },
      { id: 'consistency', label: 'Consistency', icon: 'pi pi-check-circle' }
    ]

    const worldCategories = [
      { id: 'setting', label: 'Setting', icon: 'pi pi-map' },
      { id: 'history', label: 'History', icon: 'pi pi-clock' },
      { id: 'culture', label: 'Culture', icon: 'pi pi-flag' },
      { id: 'technology', label: 'Technology', icon: 'pi pi-cog' },
      { id: 'magic', label: 'Magic/Powers', icon: 'pi pi-star' },
      { id: 'politics', label: 'Politics', icon: 'pi pi-sitemap' }
    ]

    const worldContent = reactive({
      setting: '',
      history: '',
      culture: '',
      technology: '',
      magic: '',
      politics: ''
    })

    const characterForm = reactive({
      name: '',
      type: 'supporting',
      age: null,
      physical_description: '',
      personality: '',
      background: '',
      relationships: ''
    })

    // Computed properties
    const filteredCharacters = computed(() => {
      let filtered = characters.value

      if (characterSearch.value) {
        filtered = filtered.filter(char =>
          char.name.toLowerCase().includes(characterSearch.value.toLowerCase()) ||
          char.physical_description?.toLowerCase().includes(characterSearch.value.toLowerCase())
        )
      }

      if (characterFilter.value) {
        filtered = filtered.filter(char => char.type === characterFilter.value)
      }

      return filtered
    })

    const hasInconsistencies = computed(() => {
      return consistencyIssues.value.length > 0
    })

    // Methods
    const loadCharacters = async () => {
      try {
        const response = await fetch(`/api/anime/projects/${props.projectId}/bible/characters`)
        characters.value = await response.json()
      } catch (error) {
        console.error('Failed to load characters:', error)
      }
    }

    const loadWorldContent = async () => {
      try {
        const response = await fetch(`/api/anime/projects/${props.projectId}/bible/world`)
        const data = await response.json()
        Object.assign(worldContent, data)
      } catch (error) {
        console.error('Failed to load world content:', error)
      }
    }

    const selectCharacter = (character) => {
      selectedCharacter.value = character
    }

    const editCharacter = (character) => {
      Object.assign(characterForm, character)
      editingCharacter.value = true
      showCharacterDialog.value = true
    }

    const deleteCharacter = async (character) => {
      if (!confirm(`Delete ${character.name}?`)) return

      try {
        await fetch(`/api/anime/projects/${props.projectId}/bible/characters/${character.id}`, {
          method: 'DELETE'
        })
        await loadCharacters()
        if (selectedCharacter.value?.id === character.id) {
          selectedCharacter.value = null
        }
      } catch (error) {
        console.error('Failed to delete character:', error)
      }
    }

    const saveCharacter = async () => {
      try {
        const method = editingCharacter.value ? 'PUT' : 'POST'
        const url = editingCharacter.value
          ? `/api/anime/projects/${props.projectId}/bible/characters/${characterForm.id}`
          : `/api/anime/projects/${props.projectId}/bible/characters`

        await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(characterForm)
        })

        showCharacterDialog.value = false
        editingCharacter.value = false
        Object.assign(characterForm, {
          name: '',
          type: 'supporting',
          age: null,
          physical_description: '',
          personality: '',
          background: '',
          relationships: ''
        })
        await loadCharacters()
      } catch (error) {
        console.error('Failed to save character:', error)
      }
    }

    const saveCharacterDetails = async () => {
      try {
        await fetch(`/api/anime/projects/${props.projectId}/bible/characters/${selectedCharacter.value.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(selectedCharacter.value)
        })
      } catch (error) {
        console.error('Failed to save character details:', error)
      }
    }

    const saveWorldContent = async () => {
      try {
        await fetch(`/api/anime/projects/${props.projectId}/bible/world`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(worldContent)
        })
      } catch (error) {
        console.error('Failed to save world content:', error)
      }
    }

    const runConsistencyCheck = async () => {
      checkingConsistency.value = true
      try {
        const response = await fetch(`/api/anime/projects/${props.projectId}/bible/consistency-check`, {
          method: 'POST'
        })
        consistencyIssues.value = await response.json()
        hasRunCheck.value = true
      } catch (error) {
        console.error('Failed to run consistency check:', error)
      } finally {
        checkingConsistency.value = false
      }
    }

    const generateCharacterVariant = async (character) => {
      try {
        const response = await fetch(`/api/anime/projects/${props.projectId}/bible/characters/${character.id}/generate-variant`, {
          method: 'POST'
        })
        const result = await response.json()
        // Handle generation result
        console.log('Character variant generated:', result)
      } catch (error) {
        console.error('Failed to generate character variant:', error)
      }
    }

    const refreshCharacters = () => {
      loadCharacters()
    }

    const formatText = (format) => {
      // Basic text formatting for world editor
      const textarea = document.querySelector('.world-textarea')
      if (textarea) {
        const start = textarea.selectionStart
        const end = textarea.selectionEnd
        const selectedText = textarea.value.substring(start, end)

        let formattedText = selectedText
        if (format === 'bold') {
          formattedText = `**${selectedText}**`
        } else if (format === 'italic') {
          formattedText = `*${selectedText}*`
        }

        textarea.setRangeText(formattedText)
      }
    }

    const insertTemplate = () => {
      const templates = {
        setting: 'Location: \nDescription: \nAtmosphere: \nKey Features: ',
        character: 'Name: \nAge: \nRole: \nPersonality: \nAppearance: \nBackground: '
      }

      const template = templates[activeWorldCategory.value] || templates.setting
      worldContent[activeWorldCategory.value] += '\n\n' + template
    }

    const getWordCount = (text) => {
      if (!text) return 0
      return text.trim().split(/\s+/).filter(word => word.length > 0).length
    }

    const exportBible = () => {
      const data = {
        characters: characters.value,
        world: worldContent,
        exported_at: new Date().toISOString()
      }

      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `project-bible-${props.projectId}.json`
      a.click()
      URL.revokeObjectURL(url)
    }

    const importBible = () => {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.json'
      input.onchange = (e) => {
        const file = e.target.files[0]
        if (file) {
          const reader = new FileReader()
          reader.onload = (e) => {
            try {
              const data = JSON.parse(e.target.result)
              if (data.characters) characters.value = data.characters
              if (data.world) Object.assign(worldContent, data.world)
            } catch (error) {
              console.error('Failed to import bible:', error)
            }
          }
          reader.readAsText(file)
        }
      }
      input.click()
    }

    const applyFix = async (issue) => {
      try {
        await fetch(`/api/anime/projects/${props.projectId}/bible/consistency-fix`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ issue_id: issue.id })
        })
        await runConsistencyCheck()
      } catch (error) {
        console.error('Failed to apply fix:', error)
      }
    }

    const ignoreIssue = (issue) => {
      consistencyIssues.value = consistencyIssues.value.filter(i => i.id !== issue.id)
    }

    const fixInconsistencies = async () => {
      try {
        await fetch(`/api/anime/projects/${props.projectId}/bible/auto-fix`, {
          method: 'POST'
        })
        await runConsistencyCheck()
      } catch (error) {
        console.error('Failed to auto-fix inconsistencies:', error)
      }
    }

    // Auto-save world content
    const autoSaveWorldContent = () => {
      setInterval(() => {
        saveWorldContent()
      }, 30000) // Save every 30 seconds
    }

    // Lifecycle
    onMounted(() => {
      loadCharacters()
      loadWorldContent()
      autoSaveWorldContent()
    })

    return {
      activeTab,
      activeWorldCategory,
      characters,
      selectedCharacter,
      characterSearch,
      characterFilter,
      showCharacterDialog,
      editingCharacter,
      checkingConsistency,
      consistencyIssues,
      hasRunCheck,
      tabs,
      worldCategories,
      worldContent,
      characterForm,
      filteredCharacters,
      hasInconsistencies,
      selectCharacter,
      editCharacter,
      deleteCharacter,
      saveCharacter,
      saveCharacterDetails,
      runConsistencyCheck,
      generateCharacterVariant,
      refreshCharacters,
      formatText,
      insertTemplate,
      getWordCount,
      exportBible,
      importBible,
      applyFix,
      ignoreIssue,
      fixInconsistencies
    }
  }
}
</script>

<style scoped>
.project-bible-interface {
  background: #0f0f0f;
  border: 1px solid #333;
  border-radius: 8px;
  color: #e0e0e0;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.bible-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid #333;
}

.bible-header h3 {
  margin: 0;
  color: #3b82f6;
  font-size: 1.2rem;
}

.bible-controls {
  display: flex;
  gap: 0.5rem;
}

.control-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border: 1px solid #333;
  border-radius: 4px;
  font-family: inherit;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.control-button.primary {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.control-button.primary:hover {
  background: #2563eb;
}

.control-button.secondary {
  background: #1a1a1a;
  color: #e0e0e0;
}

.control-button.secondary:hover {
  background: #333;
}

.bible-tabs {
  display: flex;
  border-bottom: 1px solid #333;
}

.tab-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1rem;
  background: none;
  border: none;
  color: #ccc;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.9rem;
  transition: all 0.2s ease;
}

.tab-button:hover {
  background: #1a1a1a;
  color: #e0e0e0;
}

.tab-button.active {
  background: #1a1a1a;
  color: #3b82f6;
  border-bottom: 2px solid #3b82f6;
}

.tab-content {
  flex: 1;
  padding: 1rem;
  overflow-y: auto;
}

.search-controls {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.search-input, .filter-select {
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  font-family: inherit;
}

.search-input {
  flex: 1;
}

.refresh-button {
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
}

.characters-table {
  border: 1px solid #333;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 1rem;
}

.table-header, .table-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr 1.5fr 1fr;
  border-bottom: 1px solid #333;
}

.table-header {
  background: #1a1a1a;
  font-weight: 600;
  color: #3b82f6;
}

.table-row {
  cursor: pointer;
  transition: background 0.2s ease;
}

.table-row:hover {
  background: #1a1a1a;
}

.table-row.selected {
  background: #1a1a1a;
  border-left: 3px solid #3b82f6;
}

.table-cell {
  padding: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.character-name {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.character-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  object-fit: cover;
}

.character-placeholder {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #333;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  color: #3b82f6;
}

.type-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 12px;
  font-size: 0.8rem;
  font-weight: 500;
}

.type-badge.protagonist {
  background: #3b82f6;
  color: white;
}

.type-badge.antagonist {
  background: #ef4444;
  color: white;
}

.type-badge.supporting {
  background: #10b981;
  color: white;
}

.type-badge.background {
  background: #6b7280;
  color: white;
}

.status-indicator {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
}

.consistency-meter {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
}

.consistency-fill {
  height: 4px;
  background: #3b82f6;
  border-radius: 2px;
  transition: width 0.3s ease;
}

.consistency-text {
  font-size: 0.8rem;
  min-width: 35px;
}

.action-button {
  padding: 0.25rem;
  background: none;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
  margin-right: 0.25rem;
}

.action-button:hover {
  background: #333;
}

.action-button.danger:hover {
  background: #ef4444;
  border-color: #ef4444;
}

.character-details {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  padding: 1rem;
}

.details-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.details-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1rem;
}

.detail-section label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 600;
  color: #3b82f6;
}

.detail-textarea {
  width: 100%;
  padding: 0.5rem;
  background: #0f0f0f;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  font-family: inherit;
  resize: vertical;
}

.save-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
}

.world-categories {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.category-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.9rem;
}

.category-button:hover {
  background: #333;
}

.category-button.active {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.world-editor {
  height: 400px;
  display: flex;
  flex-direction: column;
}

.editor-toolbar {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.format-button {
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  cursor: pointer;
}

.world-textarea {
  flex: 1;
  padding: 1rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  font-family: inherit;
  resize: none;
}

.word-count {
  text-align: right;
  font-size: 0.8rem;
  color: #999;
  margin-top: 0.5rem;
}

.consistency-controls {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.consistency-issue {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  padding: 1rem;
  margin-bottom: 1rem;
}

.issue-header {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.issue-severity {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 600;
}

.issue-severity.high {
  background: #ef4444;
  color: white;
}

.issue-severity.medium {
  background: #f59e0b;
  color: white;
}

.issue-severity.low {
  background: #10b981;
  color: white;
}

.issue-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.fix-button, .ignore-button {
  padding: 0.5rem 1rem;
  border: 1px solid #333;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.9rem;
}

.fix-button {
  background: #3b82f6;
  color: white;
}

.ignore-button {
  background: #1a1a1a;
  color: #e0e0e0;
}

.no-issues {
  text-align: center;
  padding: 2rem;
  color: #10b981;
  font-size: 1.1rem;
}

.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.character-dialog {
  background: #0f0f0f;
  border: 1px solid #333;
  border-radius: 8px;
  width: 500px;
  max-width: 90vw;
  max-height: 90vh;
  overflow-y: auto;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid #333;
}

.dialog-header h4 {
  margin: 0;
  color: #3b82f6;
}

.close-button {
  padding: 0.5rem;
  background: none;
  border: none;
  color: #e0e0e0;
  cursor: pointer;
}

.dialog-content {
  padding: 1rem;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 600;
  color: #3b82f6;
}

.form-input, .form-select, .form-textarea {
  width: 100%;
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  font-family: inherit;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem;
  border-top: 1px solid #333;
}

.dialog-button {
  padding: 0.75rem 1rem;
  border: 1px solid #333;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
}

.dialog-button.primary {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.dialog-button.secondary {
  background: #1a1a1a;
  color: #e0e0e0;
}
</style>