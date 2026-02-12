<template>
  <div class="echo-assistant-panel">
    <!-- Header -->
    <div class="assistant-header">
      <h3>Echo Assistant</h3>
      <div class="assistant-controls">
        <div class="echo-status" :class="{ connected: echoConnected, thinking: echoThinking }">
          <span class="status-dot"></span>
          {{ getEchoStatus() }}
        </div>
        <button @click="refreshSuggestions" class="control-button secondary" :disabled="loading">
          <i :class="loading ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'"></i>
          Refresh
        </button>
        <button @click="showSettingsDialog = true" class="control-button secondary">
          <i class="pi pi-cog"></i>
          Settings
        </button>
      </div>
    </div>

    <!-- Quick Actions -->
    <div class="assistant-section">
      <div class="section-header">
        <h4>Quick Actions</h4>
      </div>

      <div class="quick-actions">
        <button @click="optimizeParameters" class="action-button primary" :disabled="!echoConnected">
          <i class="pi pi-magic-wand"></i>
          Optimize Parameters
        </button>
        <button @click="analyzeProject" class="action-button secondary" :disabled="!echoConnected">
          <i class="pi pi-search"></i>
          Analyze Project
        </button>
        <button @click="generateIdeas" class="action-button secondary" :disabled="!echoConnected">
          <i class="pi pi-lightbulb"></i>
          Generate Ideas
        </button>
        <button @click="checkConsistency" class="action-button secondary" :disabled="!echoConnected">
          <i class="pi pi-check-circle"></i>
          Check Consistency
        </button>
      </div>
    </div>

    <!-- AI Suggestions -->
    <div class="assistant-section">
      <div class="section-header">
        <h4>AI Suggestions</h4>
        <div class="suggestion-filters">
          <select v-model="selectedCategory" class="filter-select">
            <option value="">All Categories</option>
            <option value="parameters">Parameters</option>
            <option value="workflow">Workflow</option>
            <option value="quality">Quality</option>
            <option value="performance">Performance</option>
            <option value="creative">Creative</option>
          </select>
          <select v-model="selectedPriority" class="filter-select">
            <option value="">All Priorities</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>
      </div>

      <div class="suggestions-container">
        <div
          v-for="suggestion in filteredSuggestions"
          :key="suggestion.id"
          :class="['suggestion-item', suggestion.priority, { applied: suggestion.applied }]"
        >
          <div class="suggestion-header">
            <div class="suggestion-title">
              <i :class="getSuggestionIcon(suggestion.category)"></i>
              {{ suggestion.title }}
            </div>
            <div class="suggestion-meta">
              <span :class="['priority-badge', suggestion.priority]">{{ suggestion.priority.toUpperCase() }}</span>
              <span class="category-badge">{{ suggestion.category }}</span>
            </div>
          </div>

          <div class="suggestion-content">
            <p class="suggestion-description">{{ suggestion.description }}</p>

            <div v-if="suggestion.reasoning" class="suggestion-reasoning">
              <strong>Reasoning:</strong> {{ suggestion.reasoning }}
            </div>

            <div v-if="suggestion.impact" class="suggestion-impact">
              <div class="impact-metrics">
                <div v-if="suggestion.impact.quality" class="impact-item">
                  <span class="impact-label">Quality:</span>
                  <span :class="['impact-value', getImpactClass(suggestion.impact.quality)]">
                    {{ formatImpact(suggestion.impact.quality) }}
                  </span>
                </div>
                <div v-if="suggestion.impact.performance" class="impact-item">
                  <span class="impact-label">Performance:</span>
                  <span :class="['impact-value', getImpactClass(suggestion.impact.performance)]">
                    {{ formatImpact(suggestion.impact.performance) }}
                  </span>
                </div>
                <div v-if="suggestion.impact.time" class="impact-item">
                  <span class="impact-label">Time:</span>
                  <span :class="['impact-value', getImpactClass(suggestion.impact.time)]">
                    {{ formatImpact(suggestion.impact.time) }}
                  </span>
                </div>
              </div>
            </div>

            <div v-if="suggestion.parameters" class="suggestion-parameters">
              <strong>Suggested Changes:</strong>
              <div class="parameter-changes">
                <div v-for="param in suggestion.parameters" :key="param.name" class="parameter-change">
                  <span class="param-name">{{ param.name }}:</span>
                  <span class="param-current">{{ param.current }}</span>
                  <i class="pi pi-arrow-right"></i>
                  <span class="param-suggested">{{ param.suggested }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="suggestion-actions">
            <button
              @click="applySuggestion(suggestion)"
              class="suggestion-button apply"
              :disabled="suggestion.applied || applyingIds.includes(suggestion.id)"
            >
              <i :class="applyingIds.includes(suggestion.id) ? 'pi pi-spin pi-spinner' : 'pi pi-check'"></i>
              {{ suggestion.applied ? 'Applied' : 'Apply' }}
            </button>
            <button @click="dismissSuggestion(suggestion)" class="suggestion-button dismiss">
              <i class="pi pi-times"></i>
              Dismiss
            </button>
            <button @click="explainSuggestion(suggestion)" class="suggestion-button explain">
              <i class="pi pi-question-circle"></i>
              Explain
            </button>
          </div>
        </div>

        <div v-if="filteredSuggestions.length === 0" class="no-suggestions">
          <i class="pi pi-lightbulb"></i>
          <span>{{ loading ? 'Loading suggestions...' : 'No suggestions available' }}</span>
        </div>
      </div>
    </div>

    <!-- Chat Interface -->
    <div class="assistant-section">
      <div class="section-header">
        <h4>Chat with Echo</h4>
        <button @click="clearChat" class="control-button secondary">
          <i class="pi pi-trash"></i>
          Clear
        </button>
      </div>

      <div class="chat-container">
        <div class="chat-messages" ref="chatMessages">
          <div
            v-for="message in chatHistory"
            :key="message.id"
            :class="['chat-message', message.role]"
          >
            <div class="message-avatar">
              <i :class="message.role === 'user' ? 'pi pi-user' : 'pi pi-robot'"></i>
            </div>
            <div class="message-content">
              <div class="message-text" v-html="formatMessage(message.content)"></div>
              <div class="message-time">{{ formatTime(message.timestamp) }}</div>
            </div>
          </div>

          <div v-if="echoThinking" class="chat-message echo thinking">
            <div class="message-avatar">
              <i class="pi pi-robot"></i>
            </div>
            <div class="message-content">
              <div class="thinking-indicator">
                <span class="thinking-dots">
                  <span></span>
                  <span></span>
                  <span></span>
                </span>
                Echo is thinking...
              </div>
            </div>
          </div>
        </div>

        <div class="chat-input">
          <input
            v-model="chatInput"
            @keyup.enter="sendMessage"
            placeholder="Ask Echo about your project, parameters, or workflow..."
            class="chat-input-field"
            :disabled="!echoConnected || echoThinking"
          />
          <button
            @click="sendMessage"
            class="send-button"
            :disabled="!echoConnected || !chatInput.trim() || echoThinking"
          >
            <i :class="echoThinking ? 'pi pi-spin pi-spinner' : 'pi pi-send'"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Performance Insights -->
    <div class="assistant-section">
      <div class="section-header">
        <h4>Performance Insights</h4>
        <button @click="analyzePerformance" class="control-button secondary" :disabled="!echoConnected">
          <i class="pi pi-chart-line"></i>
          Analyze
        </button>
      </div>

      <div class="insights-container">
        <div v-for="insight in performanceInsights" :key="insight.id" class="insight-item">
          <div class="insight-header">
            <span class="insight-title">{{ insight.title }}</span>
            <span :class="['insight-score', getScoreClass(insight.score)]">
              {{ insight.score }}/10
            </span>
          </div>
          <div class="insight-description">{{ insight.description }}</div>
          <div v-if="insight.recommendations.length > 0" class="insight-recommendations">
            <strong>Recommendations:</strong>
            <ul>
              <li v-for="rec in insight.recommendations" :key="rec">{{ rec }}</li>
            </ul>
          </div>
        </div>

        <div v-if="performanceInsights.length === 0" class="no-insights">
          <i class="pi pi-chart-line"></i>
          <span>Run analysis to see performance insights</span>
        </div>
      </div>
    </div>

    <!-- Settings Dialog -->
    <div v-if="showSettingsDialog" class="dialog-overlay" @click="showSettingsDialog = false">
      <div class="settings-dialog" @click.stop>
        <div class="dialog-header">
          <h4>Echo Assistant Settings</h4>
          <button @click="showSettingsDialog = false" class="close-button">
            <i class="pi pi-times"></i>
          </button>
        </div>

        <div class="dialog-content">
          <div class="setting-group">
            <label>Suggestion Frequency</label>
            <select v-model="settings.suggestionFrequency" class="setting-select">
              <option value="aggressive">Aggressive (Every 30s)</option>
              <option value="normal">Normal (Every 2 minutes)</option>
              <option value="conservative">Conservative (Every 5 minutes)</option>
              <option value="manual">Manual Only</option>
            </select>
          </div>

          <div class="setting-group">
            <label>Auto-apply Low-risk Suggestions</label>
            <input type="checkbox" v-model="settings.autoApplyLowRisk" class="setting-checkbox" />
          </div>

          <div class="setting-group">
            <label>Show Reasoning by Default</label>
            <input type="checkbox" v-model="settings.showReasoning" class="setting-checkbox" />
          </div>

          <div class="setting-group">
            <label>Echo Personality</label>
            <select v-model="settings.personality" class="setting-select">
              <option value="professional">Professional</option>
              <option value="friendly">Friendly</option>
              <option value="technical">Technical</option>
              <option value="creative">Creative</option>
            </select>
          </div>

          <div class="setting-group">
            <label>Minimum Suggestion Priority</label>
            <select v-model="settings.minPriority" class="setting-select">
              <option value="low">Low and above</option>
              <option value="medium">Medium and above</option>
              <option value="high">High only</option>
            </select>
          </div>
        </div>

        <div class="dialog-actions">
          <button @click="showSettingsDialog = false" class="dialog-button secondary">Cancel</button>
          <button @click="saveSettings" class="dialog-button primary">Save Settings</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'

export default {
  name: 'EchoAssistantPanel',
  setup() {
    const loading = ref(false)
    const echoConnected = ref(false)
    const echoThinking = ref(false)
    const showSettingsDialog = ref(false)
    const selectedCategory = ref('')
    const selectedPriority = ref('')
    const chatInput = ref('')
    const chatMessages = ref(null)
    const applyingIds = ref([])

    // Data
    const suggestions = ref([])
    const chatHistory = ref([])
    const performanceInsights = ref([])

    const settings = reactive({
      suggestionFrequency: 'normal',
      autoApplyLowRisk: false,
      showReasoning: true,
      personality: 'professional',
      minPriority: 'low'
    })

    // Computed properties
    const filteredSuggestions = computed(() => {
      let filtered = suggestions.value

      if (selectedCategory.value) {
        filtered = filtered.filter(s => s.category === selectedCategory.value)
      }

      if (selectedPriority.value) {
        filtered = filtered.filter(s => s.priority === selectedPriority.value)
      }

      // Filter by minimum priority setting
      const priorityOrder = { low: 1, medium: 2, high: 3 }
      const minLevel = priorityOrder[settings.minPriority]
      filtered = filtered.filter(s => priorityOrder[s.priority] >= minLevel)

      return filtered.sort((a, b) => {
        // Sort by priority (high first) then by timestamp
        const priorityDiff = priorityOrder[b.priority] - priorityOrder[a.priority]
        if (priorityDiff !== 0) return priorityDiff
        return new Date(b.timestamp) - new Date(a.timestamp)
      })
    })

    // Methods
    const checkEchoConnection = async () => {
      try {
        const response = await fetch('/api/echo/health')
        echoConnected.value = response.ok
      } catch (error) {
        echoConnected.value = false
      }
    }

    const loadSuggestions = async () => {
      try {
        const response = await fetch('/api/echo/suggestions')
        if (response.ok) {
          suggestions.value = await response.json()
        }
      } catch (error) {
        console.error('Failed to load suggestions:', error)
      }
    }

    const refreshSuggestions = async () => {
      loading.value = true
      try {
        await Promise.all([
          checkEchoConnection(),
          loadSuggestions()
        ])
      } finally {
        loading.value = false
      }
    }

    const optimizeParameters = async () => {
      try {
        echoThinking.value = true
        const response = await fetch('/api/echo/optimize-parameters', {
          method: 'POST'
        })

        if (response.ok) {
          const result = await response.json()
          addChatMessage('echo', `I've analyzed your current parameters and suggest the following optimizations:\n\n${result.summary}`)
          await loadSuggestions()
        }
      } catch (error) {
        addChatMessage('echo', 'Sorry, I encountered an error while optimizing parameters.')
      } finally {
        echoThinking.value = false
      }
    }

    const analyzeProject = async () => {
      try {
        echoThinking.value = true
        const response = await fetch('/api/echo/analyze-project', {
          method: 'POST'
        })

        if (response.ok) {
          const result = await response.json()
          addChatMessage('echo', `Project Analysis Complete:\n\n**Strengths:**\n${result.strengths.join('\n')}\n\n**Areas for Improvement:**\n${result.improvements.join('\n')}`)
        }
      } catch (error) {
        addChatMessage('echo', 'Sorry, I encountered an error during project analysis.')
      } finally {
        echoThinking.value = false
      }
    }

    const generateIdeas = async () => {
      try {
        echoThinking.value = true
        const response = await fetch('/api/echo/generate-ideas', {
          method: 'POST'
        })

        if (response.ok) {
          const result = await response.json()
          addChatMessage('echo', `Here are some creative ideas for your project:\n\n${result.ideas.map((idea, i) => `${i + 1}. ${idea}`).join('\n')}`)
        }
      } catch (error) {
        addChatMessage('echo', 'Sorry, I encountered an error while generating ideas.')
      } finally {
        echoThinking.value = false
      }
    }

    const checkConsistency = async () => {
      try {
        echoThinking.value = true
        const response = await fetch('/api/echo/check-consistency', {
          method: 'POST'
        })

        if (response.ok) {
          const result = await response.json()
          const issueCount = result.issues.length
          const message = issueCount > 0
            ? `Found ${issueCount} consistency issues:\n\n${result.issues.map(issue => `• ${issue}`).join('\n')}`
            : 'No consistency issues found! Your project looks great.'
          addChatMessage('echo', message)
        }
      } catch (error) {
        addChatMessage('echo', 'Sorry, I encountered an error during consistency check.')
      } finally {
        echoThinking.value = false
      }
    }

    const applySuggestion = async (suggestion) => {
      applyingIds.value.push(suggestion.id)
      try {
        const response = await fetch(`/api/echo/suggestions/${suggestion.id}/apply`, {
          method: 'POST'
        })

        if (response.ok) {
          suggestion.applied = true
          addChatMessage('echo', `Applied suggestion: "${suggestion.title}". Your settings have been updated.`)
        } else {
          addChatMessage('echo', `Failed to apply suggestion: "${suggestion.title}". Please try again.`)
        }
      } catch (error) {
        addChatMessage('echo', `Error applying suggestion: ${error.message}`)
      } finally {
        applyingIds.value = applyingIds.value.filter(id => id !== suggestion.id)
      }
    }

    const dismissSuggestion = (suggestion) => {
      suggestions.value = suggestions.value.filter(s => s.id !== suggestion.id)
    }

    const explainSuggestion = async (suggestion) => {
      try {
        echoThinking.value = true
        const response = await fetch(`/api/echo/suggestions/${suggestion.id}/explain`, {
          method: 'POST'
        })

        if (response.ok) {
          const result = await response.json()
          addChatMessage('echo', `**Explanation for "${suggestion.title}":**\n\n${result.explanation}`)
        }
      } catch (error) {
        addChatMessage('echo', 'Sorry, I couldn\'t provide an explanation for that suggestion.')
      } finally {
        echoThinking.value = false
      }
    }

    const sendMessage = async () => {
      if (!chatInput.value.trim()) return

      const userMessage = chatInput.value
      chatInput.value = ''

      addChatMessage('user', userMessage)
      echoThinking.value = true

      try {
        const response = await fetch('/api/echo/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: userMessage,
            context: 'anime_production'
          })
        })

        if (response.ok) {
          const result = await response.json()
          addChatMessage('echo', result.response)
        } else {
          addChatMessage('echo', 'Sorry, I encountered an error processing your message.')
        }
      } catch (error) {
        addChatMessage('echo', 'Sorry, I\'m having trouble connecting right now.')
      } finally {
        echoThinking.value = false
      }
    }

    const addChatMessage = (role, content) => {
      chatHistory.value.push({
        id: Date.now(),
        role,
        content,
        timestamp: new Date()
      })

      // Auto-scroll to bottom
      nextTick(() => {
        if (chatMessages.value) {
          chatMessages.value.scrollTop = chatMessages.value.scrollHeight
        }
      })
    }

    const clearChat = () => {
      chatHistory.value = []
    }

    const analyzePerformance = async () => {
      try {
        const response = await fetch('/api/echo/analyze-performance', {
          method: 'POST'
        })

        if (response.ok) {
          performanceInsights.value = await response.json()
        }
      } catch (error) {
        console.error('Failed to analyze performance:', error)
      }
    }

    const saveSettings = () => {
      localStorage.setItem('echo-assistant-settings', JSON.stringify(settings))
      showSettingsDialog.value = false
    }

    const loadSettings = () => {
      const saved = localStorage.getItem('echo-assistant-settings')
      if (saved) {
        try {
          Object.assign(settings, JSON.parse(saved))
        } catch (error) {
          console.warn('Failed to load settings:', error)
        }
      }
    }

    // Utility functions
    const getEchoStatus = () => {
      if (echoThinking.value) return 'THINKING'
      if (echoConnected.value) return 'CONNECTED'
      return 'DISCONNECTED'
    }

    const getSuggestionIcon = (category) => {
      const icons = {
        parameters: 'pi pi-sliders-h',
        workflow: 'pi pi-sitemap',
        quality: 'pi pi-star',
        performance: 'pi pi-tachometer-alt',
        creative: 'pi pi-palette'
      }
      return icons[category] || 'pi pi-lightbulb'
    }

    const getImpactClass = (impact) => {
      if (impact > 0) return 'positive'
      if (impact < 0) return 'negative'
      return 'neutral'
    }

    const formatImpact = (impact) => {
      const sign = impact > 0 ? '+' : ''
      return `${sign}${impact}%`
    }

    const getScoreClass = (score) => {
      if (score >= 8) return 'excellent'
      if (score >= 6) return 'good'
      if (score >= 4) return 'average'
      return 'poor'
    }

    const formatMessage = (content) => {
      // Basic markdown formatting
      return content
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>')
    }

    const formatTime = (timestamp) => {
      return new Date(timestamp).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit'
      })
    }

    // Auto-refresh setup
    const setupAutoRefresh = () => {
      const intervals = {
        aggressive: 30000,
        normal: 120000,
        conservative: 300000,
        manual: 0
      }

      const interval = intervals[settings.suggestionFrequency]
      if (interval > 0) {
        setInterval(refreshSuggestions, interval)
      }
    }

    // Lifecycle
    onMounted(() => {
      loadSettings()
      refreshSuggestions()
      setupAutoRefresh()

      // Welcome message
      addChatMessage('echo', 'Hello! I\'m Echo, your AI assistant for anime production. I can help optimize your parameters, suggest improvements, and answer questions about your workflow. How can I help you today?')
    })

    return {
      loading,
      echoConnected,
      echoThinking,
      showSettingsDialog,
      selectedCategory,
      selectedPriority,
      chatInput,
      chatMessages,
      applyingIds,
      suggestions,
      chatHistory,
      performanceInsights,
      settings,
      filteredSuggestions,
      refreshSuggestions,
      optimizeParameters,
      analyzeProject,
      generateIdeas,
      checkConsistency,
      applySuggestion,
      dismissSuggestion,
      explainSuggestion,
      sendMessage,
      clearChat,
      analyzePerformance,
      saveSettings,
      getEchoStatus,
      getSuggestionIcon,
      getImpactClass,
      formatImpact,
      getScoreClass,
      formatMessage,
      formatTime
    }
  }
}
</script>

<style scoped>
.echo-assistant-panel {
  background: #0f0f0f;
  border: 1px solid #333;
  border-radius: 8px;
  color: #e0e0e0;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.assistant-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid #333;
}

.assistant-header h3 {
  margin: 0;
  color: #3b82f6;
  font-size: 1.2rem;
}

.assistant-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.echo-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 20px;
  font-size: 0.9rem;
  font-weight: 600;
  background: #1a1a1a;
  border: 1px solid #333;
}

.echo-status.connected {
  background: rgba(16, 185, 129, 0.2);
  color: #10b981;
  border-color: #10b981;
}

.echo-status.thinking {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
  border-color: #3b82f6;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.echo-status.thinking .status-dot {
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
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

.control-button.secondary {
  background: #1a1a1a;
  color: #e0e0e0;
}

.control-button.secondary:hover {
  background: #333;
}

.control-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.assistant-section {
  padding: 1rem;
  border-bottom: 1px solid #222;
}

.assistant-section:last-child {
  border-bottom: none;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.section-header h4 {
  margin: 0;
  color: #3b82f6;
  font-size: 1.1rem;
}

.suggestion-filters {
  display: flex;
  gap: 0.5rem;
}

.filter-select {
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  font-family: inherit;
  font-size: 0.9rem;
}

.quick-actions {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.75rem;
}

.action-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border: 1px solid #333;
  border-radius: 4px;
  font-family: inherit;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-button.primary {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.action-button.primary:hover:not(:disabled) {
  background: #2563eb;
}

.action-button.secondary {
  background: #1a1a1a;
  color: #e0e0e0;
}

.action-button.secondary:hover:not(:disabled) {
  background: #333;
}

.action-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.suggestions-container {
  max-height: 400px;
  overflow-y: auto;
}

.suggestion-item {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
  transition: all 0.2s ease;
}

.suggestion-item.high {
  border-left: 4px solid #ef4444;
}

.suggestion-item.medium {
  border-left: 4px solid #f59e0b;
}

.suggestion-item.low {
  border-left: 4px solid #10b981;
}

.suggestion-item.applied {
  opacity: 0.7;
  background: rgba(16, 185, 129, 0.1);
}

.suggestion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.suggestion-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  color: #e0e0e0;
}

.suggestion-meta {
  display: flex;
  gap: 0.5rem;
}

.priority-badge, .category-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 600;
}

.priority-badge.high {
  background: #ef4444;
  color: white;
}

.priority-badge.medium {
  background: #f59e0b;
  color: white;
}

.priority-badge.low {
  background: #10b981;
  color: white;
}

.category-badge {
  background: #6b7280;
  color: white;
}

.suggestion-content {
  margin-bottom: 1rem;
}

.suggestion-description {
  margin-bottom: 0.75rem;
  line-height: 1.5;
}

.suggestion-reasoning, .suggestion-impact {
  margin-bottom: 0.75rem;
  font-size: 0.9rem;
}

.impact-metrics {
  display: flex;
  gap: 1rem;
  margin-top: 0.5rem;
}

.impact-item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.impact-label {
  color: #999;
}

.impact-value.positive {
  color: #10b981;
}

.impact-value.negative {
  color: #ef4444;
}

.impact-value.neutral {
  color: #6b7280;
}

.suggestion-parameters {
  margin-bottom: 0.75rem;
}

.parameter-changes {
  margin-top: 0.5rem;
}

.parameter-change {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
  font-family: monospace;
  font-size: 0.9rem;
}

.param-name {
  color: #3b82f6;
  font-weight: 600;
}

.param-current {
  color: #ef4444;
}

.param-suggested {
  color: #10b981;
}

.suggestion-actions {
  display: flex;
  gap: 0.5rem;
}

.suggestion-button {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.5rem 1rem;
  border: 1px solid #333;
  border-radius: 4px;
  font-family: inherit;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.suggestion-button.apply {
  background: #10b981;
  color: white;
  border-color: #10b981;
}

.suggestion-button.apply:hover:not(:disabled) {
  background: #059669;
}

.suggestion-button.dismiss {
  background: #ef4444;
  color: white;
  border-color: #ef4444;
}

.suggestion-button.dismiss:hover {
  background: #dc2626;
}

.suggestion-button.explain {
  background: #1a1a1a;
  color: #e0e0e0;
}

.suggestion-button.explain:hover {
  background: #333;
}

.suggestion-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.no-suggestions, .no-insights {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  color: #999;
  font-style: italic;
}

.chat-container {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 8px;
  height: 300px;
  display: flex;
  flex-direction: column;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
}

.chat-message {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.chat-message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #333;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.chat-message.user .message-avatar {
  background: #3b82f6;
}

.chat-message.echo .message-avatar {
  background: #10b981;
}

.message-content {
  flex: 1;
  min-width: 0;
}

.chat-message.user .message-content {
  text-align: right;
}

.message-text {
  background: #333;
  padding: 0.75rem;
  border-radius: 12px;
  line-height: 1.4;
  margin-bottom: 0.25rem;
}

.chat-message.user .message-text {
  background: #3b82f6;
}

.chat-message.echo .message-text {
  background: #1a1a1a;
  border: 1px solid #333;
}

.message-time {
  font-size: 0.8rem;
  color: #999;
}

.thinking-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-style: italic;
  color: #999;
}

.thinking-dots {
  display: flex;
  gap: 0.25rem;
}

.thinking-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #3b82f6;
  animation: thinking 1.4s ease-in-out infinite;
}

.thinking-dots span:nth-child(1) { animation-delay: -0.32s; }
.thinking-dots span:nth-child(2) { animation-delay: -0.16s; }

@keyframes thinking {
  0%, 80%, 100% {
    transform: scale(0);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.chat-input {
  display: flex;
  gap: 0.5rem;
  padding: 1rem;
  border-top: 1px solid #333;
}

.chat-input-field {
  flex: 1;
  padding: 0.75rem;
  background: #0f0f0f;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  font-family: inherit;
}

.chat-input-field:focus {
  outline: none;
  border-color: #3b82f6;
}

.send-button {
  padding: 0.75rem;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.send-button:hover:not(:disabled) {
  background: #2563eb;
}

.send-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.insights-container {
  max-height: 300px;
  overflow-y: auto;
}

.insight-item {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
}

.insight-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.insight-title {
  font-weight: 600;
  color: #e0e0e0;
}

.insight-score {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-weight: 600;
  font-size: 0.9rem;
}

.insight-score.excellent {
  background: #10b981;
  color: white;
}

.insight-score.good {
  background: #3b82f6;
  color: white;
}

.insight-score.average {
  background: #f59e0b;
  color: white;
}

.insight-score.poor {
  background: #ef4444;
  color: white;
}

.insight-description {
  margin-bottom: 0.75rem;
  line-height: 1.4;
}

.insight-recommendations ul {
  margin: 0.5rem 0 0 1rem;
  color: #ccc;
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

.settings-dialog {
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

.setting-group {
  margin-bottom: 1rem;
}

.setting-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 600;
  color: #3b82f6;
}

.setting-select {
  width: 100%;
  padding: 0.5rem;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  font-family: inherit;
}

.setting-checkbox {
  width: 16px;
  height: 16px;
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