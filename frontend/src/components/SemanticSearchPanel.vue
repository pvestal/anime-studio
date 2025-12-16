<template>
  <div class="semantic-search-panel">
    <!-- Search Header -->
    <div class="search-header">
      <h3>
        <i class="pi pi-search"></i>
        Semantic Search
      </h3>
      <div class="search-controls">
        <Dropdown
          v-model="searchScope"
          :options="searchScopes"
          optionLabel="label"
          optionValue="value"
          placeholder="Search Scope"
          class="scope-dropdown"
        />
        <Button
          icon="pi pi-filter"
          @click="showFilters = !showFilters"
          :severity="showFilters ? 'primary' : 'secondary'"
          text
          v-tooltip="'Advanced Filters'"
        />
      </div>
    </div>

    <!-- Search Input -->
    <div class="search-input-wrapper">
      <IconField iconPosition="left">
        <InputIcon class="pi pi-search" />
        <InputText
          v-model="searchQuery"
          @keyup.enter="performSearch"
          @input="onSearchInput"
          placeholder="Search for scenes, characters, or emotions... (e.g., 'Find all somber night scenes with Yuki')"
          class="search-input"
          ref="searchInput"
        />
      </IconField>
      <Button
        icon="pi pi-play"
        @click="performSearch"
        :loading="searching"
        :disabled="!searchQuery.trim()"
        severity="primary"
      />
    </div>

    <!-- Search Suggestions -->
    <div class="search-suggestions" v-if="suggestions.length > 0 && !searching && !hasResults">
      <span class="suggestions-label">Suggestions:</span>
      <div class="suggestion-chips">
        <Chip
          v-for="suggestion in suggestions"
          :key="suggestion"
          :label="suggestion"
          @click="searchQuery = suggestion; performSearch()"
          class="suggestion-chip"
        />
      </div>
    </div>

    <!-- Advanced Filters -->
    <Card v-if="showFilters" class="filters-panel">
      <template #content>
        <div class="filters-grid">
          <div class="filter-group">
            <label>Content Type</label>
            <MultiSelect
              v-model="filters.contentTypes"
              :options="contentTypes"
              optionLabel="label"
              optionValue="value"
              placeholder="Select Types"
              class="filter-input"
            />
          </div>

          <div class="filter-group">
            <label>Characters</label>
            <MultiSelect
              v-model="filters.characters"
              :options="availableCharacters"
              optionLabel="name"
              optionValue="id"
              placeholder="Select Characters"
              class="filter-input"
            />
          </div>

          <div class="filter-group">
            <label>Mood/Emotion</label>
            <Dropdown
              v-model="filters.mood"
              :options="moodOptions"
              optionLabel="label"
              optionValue="value"
              placeholder="Any Mood"
              class="filter-input"
              showClear
            />
          </div>

          <div class="filter-group">
            <label>Similarity Threshold</label>
            <div class="similarity-control">
              <Slider
                v-model="filters.similarityThreshold"
                :min="0.1"
                :max="1.0"
                :step="0.05"
                class="similarity-slider"
              />
              <span class="similarity-value">{{ filters.similarityThreshold.toFixed(2) }}</span>
            </div>
          </div>

          <div class="filter-actions">
            <Button
              label="Reset"
              @click="resetFilters"
              severity="secondary"
              outlined
              size="small"
            />
            <Button
              label="Apply"
              @click="performSearch"
              severity="primary"
              size="small"
            />
          </div>
        </div>
      </template>
    </Card>

    <!-- Search Results -->
    <div class="search-results" v-if="hasResults">
      <div class="results-header">
        <span class="results-count">
          {{ searchResults.length }} results in {{ searchDuration }}ms
        </span>
        <div class="results-controls">
          <Dropdown
            v-model="sortBy"
            :options="sortOptions"
            optionLabel="label"
            optionValue="value"
            placeholder="Sort by"
            @change="sortResults"
            class="sort-dropdown"
          />
          <ToggleButton
            v-model="gridView"
            onIcon="pi pi-th-large"
            offIcon="pi pi-list"
            onLabel=""
            offLabel=""
            @change="toggleView"
            severity="secondary"
          />
        </div>
      </div>

      <!-- Results Grid View -->
      <div v-if="gridView" class="results-grid">
        <Card
          v-for="result in sortedResults"
          :key="result.id"
          :class="['result-card', { 'selected': selectedResults.includes(result.id) }]"
          @click="selectResult(result)"
        >
          <template #header>
            <div class="result-thumbnail">
              <img v-if="result.thumbnail" :src="result.thumbnail" :alt="result.title" />
              <div v-else class="thumbnail-placeholder">
                <i :class="getContentIcon(result.content_type)"></i>
              </div>
              <div class="similarity-badge">
                {{ Math.round(result.similarity_score * 100) }}%
              </div>
            </div>
          </template>
          <template #content>
            <div class="result-content">
              <h4 class="result-title">{{ result.title || 'Untitled' }}</h4>
              <p class="result-description">{{ result.description || result.content }}</p>
              <div class="result-meta">
                <Tag :value="result.content_type" severity="secondary" />
                <span class="result-timestamp">{{ formatDate(result.created_at) }}</span>
              </div>
            </div>
          </template>
        </Card>
      </div>

      <!-- Results List View -->
      <div v-else class="results-list">
        <DataTable
          v-model:selection="selectedResultsObjects"
          :value="sortedResults"
          selectionMode="multiple"
          :metaKeySelection="false"
          @rowSelect="onRowSelect"
          @rowUnselect="onRowUnselect"
          class="results-table"
        >
          <Column selectionMode="multiple" headerStyle="width: 3rem" />

          <Column field="thumbnail" header="" style="width: 100px">
            <template #body="slotProps">
              <div class="list-thumbnail">
                <img v-if="slotProps.data.thumbnail" :src="slotProps.data.thumbnail" />
                <i v-else :class="getContentIcon(slotProps.data.content_type)"></i>
              </div>
            </template>
          </Column>

          <Column field="title" header="Title" sortable>
            <template #body="slotProps">
              <div class="title-cell">
                <span class="title">{{ slotProps.data.title || 'Untitled' }}</span>
                <span class="similarity">{{ Math.round(slotProps.data.similarity_score * 100) }}% match</span>
              </div>
            </template>
          </Column>

          <Column field="content_type" header="Type" sortable>
            <template #body="slotProps">
              <Tag :value="slotProps.data.content_type" severity="secondary" />
            </template>
          </Column>

          <Column field="description" header="Description" style="max-width: 300px">
            <template #body="slotProps">
              <span class="description-truncate">
                {{ slotProps.data.description || slotProps.data.content }}
              </span>
            </template>
          </Column>

          <Column field="created_at" header="Date" sortable>
            <template #body="slotProps">
              {{ formatDate(slotProps.data.created_at) }}
            </template>
          </Column>

          <Column header="Actions" style="width: 150px">
            <template #body="slotProps">
              <Button
                icon="pi pi-eye"
                @click="previewResult(slotProps.data)"
                size="small"
                severity="secondary"
                text
                v-tooltip="'Preview'"
              />
              <Button
                icon="pi pi-plus"
                @click="addToProject(slotProps.data)"
                size="small"
                severity="success"
                text
                v-tooltip="'Add to Project'"
              />
              <Button
                icon="pi pi-external-link"
                @click="openResult(slotProps.data)"
                size="small"
                severity="info"
                text
                v-tooltip="'Open'"
              />
            </template>
          </Column>
        </DataTable>
      </div>

      <!-- Bulk Actions -->
      <div class="bulk-actions" v-if="selectedResults.length > 0">
        <span class="bulk-count">{{ selectedResults.length }} selected</span>
        <Button
          label="Add All to Project"
          icon="pi pi-plus"
          @click="addSelectedToProject"
          severity="success"
          size="small"
        />
        <Button
          label="Create Compilation"
          icon="pi pi-file"
          @click="createCompilation"
          severity="info"
          size="small"
        />
        <Button
          label="Export Results"
          icon="pi pi-download"
          @click="exportResults"
          severity="secondary"
          size="small"
        />
      </div>
    </div>

    <!-- Empty State -->
    <div class="empty-state" v-if="!hasResults && !searching">
      <div class="empty-content">
        <i class="pi pi-search" style="font-size: 4rem; color: #666; margin-bottom: 1rem;"></i>
        <h3>Semantic Search</h3>
        <p>Search your project assets using natural language. Echo Brain will find semantically similar content even if the exact words don't match.</p>
        <div class="example-searches">
          <strong>Try searching for:</strong>
          <ul>
            <li>"Emotional scenes with rain"</li>
            <li>"Character interactions at night"</li>
            <li>"Action sequences with movement"</li>
            <li>"Dialogue scenes indoors"</li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div class="loading-state" v-if="searching">
      <ProgressSpinner />
      <p>Echo Brain is analyzing semantic similarity...</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useEchoApi } from '@/composables/useEchoApi'
import { useEnhancedAnimeStore } from '@/stores/enhancedAnimeStore'

// Composables
const toast = useToast()
const echoApi = useEchoApi()
const store = useEnhancedAnimeStore()

// Refs
const searchQuery = ref('')
const searching = ref(false)
const searchResults = ref([])
const searchDuration = ref(0)
const selectedResults = ref([])
const selectedResultsObjects = ref([])
const showFilters = ref(false)
const gridView = ref(true)
const sortBy = ref('similarity')
const searchInput = ref(null)

// Search configuration
const searchScope = ref('project')
const searchScopes = ref([
  { label: 'Current Project', value: 'project' },
  { label: 'All Projects', value: 'all' },
  { label: 'Character Library', value: 'characters' },
  { label: 'Scene Library', value: 'scenes' },
  { label: 'Assets Only', value: 'assets' }
])

// Filters
const filters = ref({
  contentTypes: [],
  characters: [],
  mood: null,
  similarityThreshold: 0.7
})

const contentTypes = ref([
  { label: 'Scenes', value: 'scene' },
  { label: 'Characters', value: 'character' },
  { label: 'Images', value: 'image' },
  { label: 'Videos', value: 'video' },
  { label: 'Audio', value: 'audio' },
  { label: 'Text', value: 'text' }
])

const moodOptions = ref([
  { label: 'Happy/Joyful', value: 'happy' },
  { label: 'Sad/Melancholy', value: 'sad' },
  { label: 'Angry/Intense', value: 'angry' },
  { label: 'Peaceful/Calm', value: 'peaceful' },
  { label: 'Mysterious/Dark', value: 'mysterious' },
  { label: 'Romantic', value: 'romantic' },
  { label: 'Action/Exciting', value: 'action' }
])

const sortOptions = ref([
  { label: 'Similarity', value: 'similarity' },
  { label: 'Date (Newest)', value: 'date_desc' },
  { label: 'Date (Oldest)', value: 'date_asc' },
  { label: 'Name A-Z', value: 'name_asc' },
  { label: 'Name Z-A', value: 'name_desc' }
])

// Suggestions based on common search patterns
const suggestions = ref([
  'Find emotional night scenes',
  'Character close-ups',
  'Action sequences',
  'Dialogue scenes',
  'Outdoor backgrounds',
  'Character interactions'
])

// Computed
const hasResults = computed(() => searchResults.value.length > 0)
const availableCharacters = computed(() => store.characters || [])

const sortedResults = computed(() => {
  if (!searchResults.value.length) return []

  return [...searchResults.value].sort((a, b) => {
    switch (sortBy.value) {
      case 'similarity':
        return b.similarity_score - a.similarity_score
      case 'date_desc':
        return new Date(b.created_at) - new Date(a.created_at)
      case 'date_asc':
        return new Date(a.created_at) - new Date(b.created_at)
      case 'name_asc':
        return (a.title || '').localeCompare(b.title || '')
      case 'name_desc':
        return (b.title || '').localeCompare(a.title || '')
      default:
        return 0
    }
  })
})

// Methods
async function performSearch() {
  if (!searchQuery.value.trim()) return

  searching.value = true
  const startTime = Date.now()

  try {
    const searchParams = {
      query: searchQuery.value,
      scope: searchScope.value,
      filters: {
        ...filters.value,
        project_id: searchScope.value === 'project' ? store.selectedProject?.id : null
      },
      top_k: 50
    }

    const results = await echoApi.semanticSearch(
      searchQuery.value,
      searchParams.filters.project_id,
      searchParams.top_k
    )

    searchResults.value = results.results || []
    searchDuration.value = Date.now() - startTime

    // Filter by similarity threshold
    searchResults.value = searchResults.value.filter(
      result => result.similarity_score >= filters.value.similarityThreshold
    )

    // Apply content type filters
    if (filters.value.contentTypes.length > 0) {
      searchResults.value = searchResults.value.filter(
        result => filters.value.contentTypes.includes(result.content_type)
      )
    }

    toast.add({
      severity: 'success',
      summary: 'Search Complete',
      detail: `Found ${searchResults.value.length} results`,
      life: 3000
    })

    // Learn from search patterns
    await echoApi.learnPreference({
      search_query: searchQuery.value,
      search_scope: searchScope.value,
      results_count: searchResults.value.length,
      learning_category: 'search_patterns'
    })

  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Search Failed',
      detail: error.message,
      life: 5000
    })
  } finally {
    searching.value = false
  }
}

function onSearchInput() {
  // Could implement live search or suggestions here
  if (searchQuery.value.length > 2) {
    // Debounced suggestions could be implemented
  }
}

function selectResult(result) {
  const index = selectedResults.value.indexOf(result.id)
  if (index > -1) {
    selectedResults.value.splice(index, 1)
    selectedResultsObjects.value = selectedResultsObjects.value.filter(r => r.id !== result.id)
  } else {
    selectedResults.value.push(result.id)
    selectedResultsObjects.value.push(result)
  }
}

function onRowSelect(event) {
  selectedResults.value.push(event.data.id)
}

function onRowUnselect(event) {
  const index = selectedResults.value.indexOf(event.data.id)
  if (index > -1) {
    selectedResults.value.splice(index, 1)
  }
}

function previewResult(result) {
  // Emit event or open preview modal
  toast.add({
    severity: 'info',
    summary: 'Preview',
    detail: `Preview: ${result.title || 'Content'}`,
    life: 2000
  })
}

function addToProject(result) {
  // Add single result to current project
  store.addAssetToProject(result)

  toast.add({
    severity: 'success',
    summary: 'Added to Project',
    detail: `"${result.title || 'Content'}" added to current project`,
    life: 3000
  })
}

function addSelectedToProject() {
  selectedResultsObjects.value.forEach(result => {
    store.addAssetToProject(result)
  })

  toast.add({
    severity: 'success',
    summary: 'Added to Project',
    detail: `${selectedResults.value.length} items added to project`,
    life: 3000
  })

  // Clear selection
  selectedResults.value = []
  selectedResultsObjects.value = []
}

function createCompilation() {
  // Create a compilation/collection from selected results
  toast.add({
    severity: 'info',
    summary: 'Compilation',
    detail: 'Creating compilation from selected items...',
    life: 3000
  })
}

function exportResults() {
  // Export search results as JSON/CSV
  const data = selectedResultsObjects.value.length > 0
    ? selectedResultsObjects.value
    : searchResults.value

  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `search-results-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)

  toast.add({
    severity: 'success',
    summary: 'Exported',
    detail: `Exported ${data.length} results`,
    life: 3000
  })
}

function openResult(result) {
  // Open result in appropriate viewer/editor
  toast.add({
    severity: 'info',
    summary: 'Opening',
    detail: `Opening: ${result.title || 'Content'}`,
    life: 2000
  })
}

function resetFilters() {
  filters.value = {
    contentTypes: [],
    characters: [],
    mood: null,
    similarityThreshold: 0.7
  }
}

function sortResults() {
  // Trigger reactivity
  searchResults.value = [...searchResults.value]
}

function toggleView() {
  // Grid/List view toggle handled by reactive gridView
}

function getContentIcon(contentType) {
  const icons = {
    'scene': 'pi pi-video',
    'character': 'pi pi-user',
    'image': 'pi pi-image',
    'video': 'pi pi-play',
    'audio': 'pi pi-volume-up',
    'text': 'pi pi-file-text'
  }
  return icons[contentType] || 'pi pi-file'
}

function formatDate(dateString) {
  if (!dateString) return ''
  return new Date(dateString).toLocaleDateString()
}

// Initialize
onMounted(() => {
  // Focus search input
  searchInput.value?.$el?.focus()
})
</script>

<style scoped>
.semantic-search-panel {
  background: #0a0a0a;
  color: #e0e0e0;
  padding: 1.5rem;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.search-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.search-header h3 {
  margin: 0;
  color: #00d4ff;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.search-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.scope-dropdown {
  min-width: 150px;
}

.search-input-wrapper {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.search-input {
  flex: 1;
}

.search-suggestions {
  margin-bottom: 1rem;
}

.suggestions-label {
  font-size: 0.875rem;
  color: #999;
  margin-right: 0.5rem;
}

.suggestion-chips {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-top: 0.5rem;
}

.suggestion-chip {
  cursor: pointer;
  transition: all 0.2s;
}

.suggestion-chip:hover {
  background: #333 !important;
}

.filters-panel {
  background: #1a1a1a;
  border: 1px solid #333;
  margin-bottom: 1rem;
}

.filters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  align-items: end;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.filter-group label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #ccc;
}

.filter-input {
  width: 100%;
}

.similarity-control {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.similarity-slider {
  flex: 1;
}

.similarity-value {
  font-family: monospace;
  font-weight: 600;
  color: #00d4ff;
  min-width: 3rem;
}

.filter-actions {
  display: flex;
  gap: 0.5rem;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid #333;
}

.results-count {
  color: #ccc;
  font-size: 0.875rem;
}

.results-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.sort-dropdown {
  min-width: 120px;
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
  flex: 1;
  overflow-y: auto;
}

.result-card {
  background: #1a1a1a;
  border: 1px solid #333;
  cursor: pointer;
  transition: all 0.2s;
  height: fit-content;
}

.result-card:hover {
  border-color: #00d4ff;
}

.result-card.selected {
  border-color: #51cf66;
  background: #1a2e1a;
}

.result-thumbnail {
  position: relative;
  height: 200px;
  overflow: hidden;
}

.result-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumbnail-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0a0a0a;
  color: #666;
  font-size: 3rem;
}

.similarity-badge {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  background: rgba(0, 212, 255, 0.9);
  color: white;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

.result-content {
  padding: 1rem;
}

.result-title {
  margin: 0 0 0.5rem 0;
  color: #e0e0e0;
  font-size: 1rem;
  font-weight: 600;
}

.result-description {
  margin: 0 0 1rem 0;
  color: #ccc;
  font-size: 0.875rem;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.result-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.result-timestamp {
  font-size: 0.75rem;
  color: #666;
}

.results-list {
  flex: 1;
  overflow-y: auto;
}

.results-table {
  background: #1a1a1a;
}

.list-thumbnail {
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0a0a0a;
  border-radius: 4px;
  overflow: hidden;
}

.list-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.title-cell {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.title {
  font-weight: 600;
  color: #e0e0e0;
}

.similarity {
  font-size: 0.75rem;
  color: #00d4ff;
}

.description-truncate {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 250px;
}

.bulk-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  margin-top: 1rem;
}

.bulk-count {
  font-weight: 600;
  color: #51cf66;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-content {
  text-align: center;
  max-width: 500px;
}

.empty-content h3 {
  color: #ccc;
  margin: 0 0 1rem 0;
}

.empty-content p {
  color: #999;
  line-height: 1.6;
  margin-bottom: 1.5rem;
}

.example-searches {
  text-align: left;
  background: #1a1a1a;
  padding: 1rem;
  border-radius: 4px;
  border: 1px solid #333;
}

.example-searches strong {
  color: #00d4ff;
  display: block;
  margin-bottom: 0.5rem;
}

.example-searches ul {
  margin: 0;
  padding-left: 1.5rem;
  color: #ccc;
}

.example-searches li {
  margin-bottom: 0.25rem;
}

.loading-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
}

.loading-state p {
  color: #ccc;
  font-style: italic;
}
</style>