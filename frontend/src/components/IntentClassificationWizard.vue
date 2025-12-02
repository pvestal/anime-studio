<template>
  <div class="intent-classification-wizard">
    <!-- Header -->
    <div class="wizard-header">
      <h2 class="text-2xl font-bold text-white mb-4">
        {{ currentStep === 'input' ? 'Describe Your Anime Request' :
           currentStep === 'classification' ? 'Analyzing Your Request...' :
           currentStep === 'clarification' ? 'Need More Details' :
           currentStep === 'review' ? 'Review & Generate' : 'Results' }}
      </h2>

      <!-- Progress bar -->
      <div class="progress-bar mb-6">
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: progressPercentage + '%' }"></div>
        </div>
        <div class="progress-steps">
          <div v-for="(step, index) in steps" :key="step.id"
               :class="['progress-step', {
                 active: currentStepIndex === index,
                 completed: currentStepIndex > index
               }]">
            <div class="step-circle">
              <i :class="step.icon" v-if="currentStepIndex < index || currentStepIndex === index"></i>
              <i class="fas fa-check" v-else></i>
            </div>
            <span class="step-label">{{ step.label }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 1: Input -->
    <div v-if="currentStep === 'input'" class="wizard-step">
      <div class="input-section">
        <!-- Quick templates -->
        <div class="quick-templates mb-6" v-if="quickTemplates.length > 0">
          <h3 class="text-lg font-semibold text-white mb-3">Quick Start Templates</h3>
          <div class="templates-grid">
            <div v-for="template in quickTemplates" :key="template.template_name"
                 @click="selectQuickTemplate(template)"
                 class="template-card">
              <div class="template-icon">
                <i :class="getTemplateIcon(template.classification.content_type)"></i>
              </div>
              <div class="template-content">
                <h4>{{ template.template_name }}</h4>
                <p>{{ template.description }}</p>
                <div class="template-stats">
                  <span class="usage-count">{{ template.usage_count }} uses</span>
                  <span class="success-rate">{{ Math.round(template.success_rate * 100) }}% success</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Custom input -->
        <div class="custom-input">
          <h3 class="text-lg font-semibold text-white mb-3">Describe Your Request</h3>

          <!-- Explicit Generation Type Selection -->
          <div class="generation-type-selector mb-4">
            <label class="block text-sm font-medium text-gray-300 mb-2">Generation Type</label>
            <div class="type-buttons">
              <button
                @click="explicitGenerationType = 'image'"
                :class="['type-btn', { 'active': explicitGenerationType === 'image' }]">
                <i class="fas fa-image"></i>
                Generate Image
              </button>
              <button
                @click="explicitGenerationType = 'video'"
                :class="['type-btn', { 'active': explicitGenerationType === 'video' }]">
                <i class="fas fa-video"></i>
                Generate Video
              </button>
            </div>
          </div>

          <div class="input-container">
            <textarea
              v-model="userPrompt"
              @input="handlePromptChange"
              :placeholder="getPlaceholderText()"
              class="prompt-textarea"
              rows="6"
            ></textarea>

            <!-- Input hints and validation -->
            <div class="input-hints" v-if="inputHints.length > 0">
              <div v-for="hint in inputHints" :key="hint.type" :class="['hint', hint.type]">
                <i :class="hint.icon"></i>
                <span>{{ hint.message }}</span>
              </div>
            </div>
          </div>

          <!-- Advanced options -->
          <div class="advanced-options" v-if="showAdvancedOptions">
            <div class="options-grid">
              <div class="option-group">
                <label>Preferred Style</label>
                <select v-model="preferredStyle" class="option-select">
                  <option value="">Auto-detect</option>
                  <option value="traditional_anime">Traditional Anime</option>
                  <option value="photorealistic_anime">Photorealistic Anime</option>
                  <option value="cartoon">Cartoon Style</option>
                  <option value="artistic">Artistic/Experimental</option>
                  <option value="cinematic">Cinematic</option>
                </select>
              </div>

              <div class="option-group">
                <label>Quality Level</label>
                <select v-model="qualityPreference" class="option-select">
                  <option value="">Standard</option>
                  <option value="draft">Draft (Fast)</option>
                  <option value="high">High Quality</option>
                  <option value="maximum">Maximum Quality</option>
                </select>
              </div>

              <div class="option-group">
                <label>Urgency</label>
                <select v-model="urgencyHint" class="option-select">
                  <option value="">Standard</option>
                  <option value="immediate">Need it now</option>
                  <option value="urgent">Within 1 hour</option>
                  <option value="scheduled">Can wait/schedule</option>
                </select>
              </div>
            </div>
          </div>

          <div class="input-actions">
            <button @click="showAdvancedOptions = !showAdvancedOptions"
                    class="btn-secondary">
              <i class="fas fa-cog"></i>
              {{ showAdvancedOptions ? 'Hide' : 'Show' }} Advanced Options
            </button>

            <button @click="classifyIntent"
                    :disabled="!userPrompt.trim() || !explicitGenerationType || isProcessing"
                    class="btn-primary">
              <i class="fas fa-magic" v-if="!isProcessing"></i>
              <i class="fas fa-spinner fa-spin" v-else></i>
              {{ isProcessing ? 'Analyzing...' : 'Analyze Request' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 2: Classification Processing -->
    <div v-if="currentStep === 'classification'" class="wizard-step">
      <div class="processing-section">
        <div class="processing-animation">
          <div class="spinner-container">
            <div class="processing-spinner"></div>
          </div>
          <h3 class="processing-text">{{ processingMessage }}</h3>
          <div class="processing-steps">
            <div v-for="step in processingSteps" :key="step.id"
                 :class="['processing-step', {
                   active: step.status === 'active',
                   completed: step.status === 'completed'
                 }]">
              <i :class="step.icon" v-if="step.status !== 'completed'"></i>
              <i class="fas fa-check" v-else></i>
              <span>{{ step.label }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 3: Clarification -->
    <div v-if="currentStep === 'clarification'" class="wizard-step">
      <div class="clarification-section">
        <div class="clarification-intro">
          <p class="text-gray-300 mb-6">
            I need a bit more information to give you the best results:
          </p>
        </div>

        <div class="clarification-questions">
          <div v-for="question in clarificationQuestions" :key="question.id"
               class="clarification-question">
            <h4 class="question-title">
              {{ question.question }}
              <span v-if="question.priority === 'high'" class="priority-badge high">Required</span>
              <span v-else-if="question.priority === 'medium'" class="priority-badge medium">Recommended</span>
            </h4>

            <div v-if="question.explanation" class="question-explanation">
              {{ question.explanation }}
            </div>

            <!-- Multiple choice options -->
            <div v-if="question.options && question.options.length > 0" class="question-options">
              <div v-for="option in question.options" :key="option"
                   @click="setClarificationAnswer(question.id, option)"
                   :class="['option-card', {
                     selected: clarificationAnswers[question.id] === option
                   }]">
                <i class="fas fa-check option-check" v-if="clarificationAnswers[question.id] === option"></i>
                {{ option }}
              </div>
            </div>

            <!-- Text input -->
            <div v-else class="question-input">
              <input
                v-model="clarificationAnswers[question.id]"
                :placeholder="question.default_answer || 'Enter your answer...'"
                class="clarification-input"
              >
            </div>
          </div>
        </div>

        <div class="clarification-actions">
          <button @click="skipClarification" class="btn-secondary">
            Use Defaults & Continue
          </button>
          <button @click="submitClarifications"
                  :disabled="!hasRequiredClarifications"
                  class="btn-primary">
            Continue with Details
          </button>
        </div>
      </div>
    </div>

    <!-- Step 4: Review -->
    <div v-if="currentStep === 'review'" class="wizard-step">
      <div class="review-section">
        <div class="classification-result">
          <div class="result-header">
            <h3 class="text-xl font-semibold text-white mb-4">Classification Results</h3>
            <div class="confidence-indicator">
              <span class="confidence-label">Confidence:</span>
              <div class="confidence-bar">
                <div class="confidence-fill"
                     :style="{ width: (classificationResult?.confidence_score || 0) * 100 + '%' }"></div>
              </div>
              <span class="confidence-value">
                {{ Math.round((classificationResult?.confidence_score || 0) * 100) }}%
              </span>
            </div>
          </div>

          <div class="result-details">
            <div class="detail-grid">
              <div class="detail-item">
                <label>Content Type</label>
                <div class="detail-value">
                  <i :class="getContentTypeIcon(classificationResult?.content_type)"></i>
                  {{ formatValue(classificationResult?.content_type) }}
                </div>
              </div>

              <div class="detail-item">
                <label>Generation Scope</label>
                <div class="detail-value">
                  {{ formatValue(classificationResult?.generation_scope) }}
                </div>
              </div>

              <div class="detail-item">
                <label>Style Preference</label>
                <div class="detail-value">
                  {{ formatValue(classificationResult?.style_preference) }}
                </div>
              </div>

              <div class="detail-item">
                <label>Quality Level</label>
                <div class="detail-value">
                  {{ formatValue(classificationResult?.quality_level) }}
                </div>
              </div>

              <div class="detail-item" v-if="classificationResult?.duration_seconds">
                <label>Duration</label>
                <div class="detail-value">
                  {{ classificationResult.duration_seconds }} seconds
                </div>
              </div>

              <div class="detail-item">
                <label>Resolution</label>
                <div class="detail-value">
                  {{ classificationResult?.resolution }}
                </div>
              </div>
            </div>

            <div class="characters-section" v-if="classificationResult?.character_names?.length > 0">
              <label>Characters</label>
              <div class="character-tags">
                <span v-for="character in classificationResult.character_names"
                      :key="character" class="character-tag">
                  {{ character }}
                </span>
              </div>
            </div>

            <div class="prompt-section">
              <label>Optimized Prompt</label>
              <div class="prompt-display">
                {{ classificationResult?.processed_prompt || userPrompt }}
              </div>
            </div>
          </div>

          <!-- Technical details -->
          <div class="technical-details">
            <h4 class="text-lg font-semibold text-white mb-3">Technical Specifications</h4>
            <div class="tech-grid">
              <div class="tech-item">
                <label>Target Service</label>
                <span>{{ formatValue(classificationResult?.target_service) }}</span>
              </div>
              <div class="tech-item">
                <label>Estimated Time</label>
                <span>{{ classificationResult?.estimated_time_minutes || 'N/A' }} minutes</span>
              </div>
              <div class="tech-item">
                <label>VRAM Required</label>
                <span>{{ classificationResult?.estimated_vram_gb || 'N/A' }} GB</span>
              </div>
              <div class="tech-item">
                <label>Output Format</label>
                <span>{{ formatValue(classificationResult?.output_format) }}</span>
              </div>
            </div>
          </div>

          <!-- Ambiguity warnings -->
          <div v-if="classificationResult?.ambiguity_flags?.length > 0" class="ambiguity-warnings">
            <h4 class="text-lg font-semibold text-yellow-400 mb-2">
              <i class="fas fa-exclamation-triangle"></i>
              Potential Issues
            </h4>
            <div class="warning-list">
              <div v-for="flag in classificationResult.ambiguity_flags" :key="flag" class="warning-item">
                {{ formatAmbiguityFlag(flag) }}
              </div>
            </div>
          </div>
        </div>

        <div class="review-actions">
          <button @click="goBack" class="btn-secondary">
            <i class="fas fa-arrow-left"></i>
            Modify Request
          </button>

          <button @click="startGeneration" class="btn-primary">
            <i class="fas fa-play"></i>
            Start Generation
          </button>
        </div>
      </div>
    </div>

    <!-- Step 5: Results -->
    <div v-if="currentStep === 'results'" class="wizard-step">
      <div class="results-section">
        <div v-if="generationStatus === 'success'" class="success-message">
          <i class="fas fa-check-circle text-green-400 text-4xl mb-4"></i>
          <h3 class="text-xl font-semibold text-white mb-2">Generation Started Successfully!</h3>
          <p class="text-gray-300">Your request has been routed to the appropriate generation service.</p>
        </div>

        <div v-else-if="generationStatus === 'error'" class="error-message">
          <i class="fas fa-exclamation-circle text-red-400 text-4xl mb-4"></i>
          <h3 class="text-xl font-semibold text-white mb-2">Generation Failed</h3>
          <p class="text-gray-300">{{ generationError || 'An unexpected error occurred.' }}</p>
        </div>

        <div class="results-actions">
          <button @click="startOver" class="btn-secondary">
            <i class="fas fa-redo"></i>
            Start Over
          </button>

          <button @click="viewProgress" class="btn-primary" v-if="generationStatus === 'success'">
            <i class="fas fa-eye"></i>
            View Progress
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'

export default {
  name: 'IntentClassificationWizard',
  setup() {
    // Reactive state
    const currentStep = ref('input')
    const userPrompt = ref('')
    const explicitGenerationType = ref('')
    const preferredStyle = ref('')
    const qualityPreference = ref('')
    const urgencyHint = ref('')
    const showAdvancedOptions = ref(false)
    const isProcessing = ref(false)
    const processingMessage = ref('')

    // Classification results
    const classificationResult = ref(null)
    const clarificationQuestions = ref([])
    const clarificationAnswers = ref({})

    // Templates and hints
    const quickTemplates = ref([])
    const inputHints = ref([])

    // Generation status
    const generationStatus = ref(null)
    const generationError = ref('')

    // Wizard configuration
    const steps = ref([
      { id: 'input', label: 'Describe', icon: 'fas fa-edit' },
      { id: 'classification', label: 'Analyze', icon: 'fas fa-brain' },
      { id: 'clarification', label: 'Clarify', icon: 'fas fa-question-circle' },
      { id: 'review', label: 'Review', icon: 'fas fa-eye' },
      { id: 'results', label: 'Generate', icon: 'fas fa-play' }
    ])

    const processingSteps = ref([
      { id: 'parsing', label: 'Parsing request...', icon: 'fas fa-search', status: 'pending' },
      { id: 'echo', label: 'Consulting AI...', icon: 'fas fa-robot', status: 'pending' },
      { id: 'classification', label: 'Classifying intent...', icon: 'fas fa-tags', status: 'pending' },
      { id: 'optimization', label: 'Optimizing prompt...', icon: 'fas fa-magic', status: 'pending' }
    ])

    // Computed properties
    const currentStepIndex = computed(() => {
      return steps.value.findIndex(step => step.id === currentStep.value)
    })

    const progressPercentage = computed(() => {
      return ((currentStepIndex.value + 1) / steps.value.length) * 100
    })

    const hasRequiredClarifications = computed(() => {
      const requiredQuestions = clarificationQuestions.value.filter(q => q.priority === 'high')
      return requiredQuestions.every(q => clarificationAnswers.value[q.id])
    })

    // Methods
    const loadQuickTemplates = async () => {
      try {
        const response = await fetch('/api/templates/quick')
        if (response.ok) {
          quickTemplates.value = await response.json()
        }
      } catch (error) {
        console.error('Failed to load quick templates:', error)
      }
    }

    const selectQuickTemplate = (template) => {
      const classification = template.classification
      userPrompt.value = `Create a ${classification.generation_scope.replace('_', ' ')} in ${classification.style_preference.replace('_', ' ')} style`

      // Set advanced options based on template
      preferredStyle.value = classification.style_preference
      qualityPreference.value = classification.quality_level

      // Immediately classify
      classifyIntent()
    }

    const getPlaceholderText = () => {
      if (explicitGenerationType.value === 'image') {
        return `Describe the image you want to create...

Examples:
• Character portrait of Kai with silver hair and blue eyes
• Photorealistic anime portrait of a cyberpunk girl
• Background art for a fantasy forest at sunset`
      } else if (explicitGenerationType.value === 'video') {
        return `Describe the video/animation you want to create...

Examples:
• 5-second action scene with robots fighting
• Character walking through a futuristic city
• Magical transformation sequence lasting 10 seconds`
      } else {
        return 'Please select generation type first (Image or Video)'
      }
    }

    const handlePromptChange = () => {
      inputHints.value = []

      // Validate generation type selection
      if (!explicitGenerationType.value) {
        inputHints.value.push({
          type: 'error',
          icon: 'fas fa-exclamation-triangle',
          message: 'Please select generation type (Image or Video) first'
        })
        return
      }

      // Generate helpful hints based on input and type
      if (userPrompt.value.trim()) {
        if (!/\b(character|person|girl|boy|man|woman)\b/i.test(userPrompt.value)) {
          inputHints.value.push({
            type: 'suggestion',
            icon: 'fas fa-lightbulb',
            message: 'Consider specifying character details for better results'
          })
        }

        if (!/\b(anime|realistic|cartoon|artistic)\b/i.test(userPrompt.value) && !preferredStyle.value) {
          inputHints.value.push({
            type: 'suggestion',
            icon: 'fas fa-palette',
            message: 'Specify an art style or use advanced options'
          })
        }

        if (explicitGenerationType.value === 'video' && !/\d+\s*(second|minute)/i.test(userPrompt.value)) {
          inputHints.value.push({
            type: 'suggestion',
            icon: 'fas fa-clock',
            message: 'For videos, specify duration (e.g., "5 seconds", "30 seconds")'
          })
        }
      }
    }

    const classifyIntent = async () => {
      if (!userPrompt.value.trim() || !explicitGenerationType.value) return

      isProcessing.value = true
      currentStep.value = 'classification'

      // Simulate processing steps
      const stepDurations = [500, 1000, 800, 700]
      for (let i = 0; i < processingSteps.value.length; i++) {
        processingSteps.value[i].status = 'active'
        processingMessage.value = processingSteps.value[i].label

        await new Promise(resolve => setTimeout(resolve, stepDurations[i]))

        processingSteps.value[i].status = 'completed'
      }

      try {
        const requestData = {
          user_prompt: userPrompt.value,
          explicit_type: explicitGenerationType.value,
          preferred_style: preferredStyle.value || null,
          quality_preference: qualityPreference.value || null,
          urgency_hint: urgencyHint.value || null,
          context: {}
        }

        const response = await fetch('/api/intent/classify', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(requestData)
        })

        if (response.ok) {
          classificationResult.value = await response.json()

          // Check if clarification is needed
          if (classificationResult.value.suggested_clarifications?.length > 0) {
            clarificationQuestions.value = classificationResult.value.suggested_clarifications
            currentStep.value = 'clarification'
          } else {
            currentStep.value = 'review'
          }
        } else {
          throw new Error('Classification failed')
        }
      } catch (error) {
        console.error('Classification error:', error)
        // Handle error - could show error message or fallback
        currentStep.value = 'input'
        inputHints.value.push({
          type: 'error',
          icon: 'fas fa-exclamation-circle',
          message: 'Classification failed. Please try again.'
        })
      } finally {
        isProcessing.value = false
      }
    }

    const setClarificationAnswer = (questionId, answer) => {
      clarificationAnswers.value[questionId] = answer
    }

    const submitClarifications = async () => {
      try {
        const response = await fetch('/api/intent/clarify', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            request_id: classificationResult.value.request_id,
            clarification_responses: clarificationAnswers.value
          })
        })

        if (response.ok) {
          // Updated classification would be returned
          currentStep.value = 'review'
        }
      } catch (error) {
        console.error('Clarification error:', error)
      }
    }

    const skipClarification = () => {
      currentStep.value = 'review'
    }

    const startGeneration = async () => {
      try {
        const response = await fetch('/api/workflow/route', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            classification: classificationResult.value
          })
        })

        if (response.ok) {
          const routingResult = await response.json()
          if (routingResult.success) {
            generationStatus.value = 'success'
          } else {
            generationStatus.value = 'error'
            generationError.value = 'Prerequisites not met: ' + routingResult.prerequisites_missing.join(', ')
          }
        } else {
          throw new Error('Routing failed')
        }
      } catch (error) {
        generationStatus.value = 'error'
        generationError.value = error.message
      } finally {
        currentStep.value = 'results'
      }
    }

    const goBack = () => {
      currentStep.value = 'input'
    }

    const startOver = () => {
      currentStep.value = 'input'
      userPrompt.value = ''
      classificationResult.value = null
      clarificationQuestions.value = []
      clarificationAnswers.value = {}
      generationStatus.value = null
      generationError.value = ''

      // Reset processing steps
      processingSteps.value.forEach(step => {
        step.status = 'pending'
      })
    }

    const viewProgress = () => {
      // Navigate to progress view or emit event
      console.log('Navigate to progress view')
    }

    // Utility methods
    const getTemplateIcon = (contentType) => {
      const icons = {
        image: 'fas fa-image',
        video: 'fas fa-video',
        audio: 'fas fa-music'
      }
      return icons[contentType] || 'fas fa-file'
    }

    const getContentTypeIcon = (contentType) => {
      const icons = {
        image: 'fas fa-image',
        video: 'fas fa-video',
        audio: 'fas fa-music',
        mixed_media: 'fas fa-layer-group'
      }
      return icons[contentType] || 'fas fa-file'
    }

    const formatValue = (value) => {
      if (!value) return 'N/A'
      return value.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
    }

    const formatAmbiguityFlag = (flag) => {
      const descriptions = {
        content_type_conflict: 'Conflicting content type indicators detected',
        character_name_missing: 'Character name not clearly specified',
        duration_not_specified: 'Video duration not specified',
        style_not_specified: 'Art style preference unclear'
      }
      return descriptions[flag] || flag.replace(/_/g, ' ')
    }

    // Lifecycle
    onMounted(() => {
      loadQuickTemplates()
    })

    return {
      // State
      currentStep,
      userPrompt,
      explicitGenerationType,
      preferredStyle,
      qualityPreference,
      urgencyHint,
      showAdvancedOptions,
      isProcessing,
      processingMessage,
      classificationResult,
      clarificationQuestions,
      clarificationAnswers,
      quickTemplates,
      inputHints,
      generationStatus,
      generationError,

      // Configuration
      steps,
      processingSteps,

      // Computed
      currentStepIndex,
      progressPercentage,
      hasRequiredClarifications,

      // Methods
      selectQuickTemplate,
      getPlaceholderText,
      handlePromptChange,
      classifyIntent,
      setClarificationAnswer,
      submitClarifications,
      skipClarification,
      startGeneration,
      goBack,
      startOver,
      viewProgress,
      getTemplateIcon,
      getContentTypeIcon,
      formatValue,
      formatAmbiguityFlag
    }
  }
}
</script>

<style scoped>
.intent-classification-wizard {
  max-width: 900px;
  margin: 0 auto;
  padding: 2rem;
  background: linear-gradient(135deg, #1a1a1a 0%, #2d1b1b 100%);
  border-radius: 12px;
  color: white;
}

/* Progress Bar */
.progress-bar {
  margin-bottom: 2rem;
}

.progress-track {
  height: 4px;
  background: #333;
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 1rem;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #ff6b6b, #feca57);
  transition: width 0.3s ease;
}

.progress-steps {
  display: flex;
  justify-content: space-between;
}

.progress-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
}

.step-circle {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #333;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 0.5rem;
  color: #666;
  transition: all 0.3s ease;
}

.progress-step.active .step-circle {
  background: #ff6b6b;
  color: white;
}

.progress-step.completed .step-circle {
  background: #48bb78;
  color: white;
}

.step-label {
  font-size: 0.875rem;
  color: #666;
  text-align: center;
}

.progress-step.active .step-label,
.progress-step.completed .step-label {
  color: white;
}

/* Quick Templates */
.templates-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.template-card {
  background: #2d2d2d;
  border-radius: 8px;
  padding: 1.5rem;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 2px solid transparent;
  display: flex;
  align-items: flex-start;
  gap: 1rem;
}

.template-card:hover {
  background: #3d3d3d;
  border-color: #ff6b6b;
  transform: translateY(-2px);
}

.template-icon {
  width: 48px;
  height: 48px;
  background: #ff6b6b;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 1.5rem;
  flex-shrink: 0;
}

.template-content h4 {
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: white;
}

.template-content p {
  color: #ccc;
  font-size: 0.875rem;
  margin-bottom: 0.5rem;
}

.template-stats {
  display: flex;
  gap: 1rem;
  font-size: 0.75rem;
  color: #999;
}

/* Input Section */
.prompt-textarea {
  width: 100%;
  min-height: 150px;
  background: #2d2d2d;
  border: 2px solid #444;
  border-radius: 8px;
  padding: 1rem;
  color: white;
  resize: vertical;
  font-family: inherit;
  transition: border-color 0.3s ease;
}

.prompt-textarea:focus {
  outline: none;
  border-color: #ff6b6b;
}

.prompt-textarea::placeholder {
  color: #999;
}

.input-hints {
  margin-top: 1rem;
}

.hint {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  border-radius: 6px;
  margin-bottom: 0.5rem;
}

.hint.suggestion {
  background: #2d4a4a;
  border-left: 4px solid #48bb78;
}

.hint.error {
  background: #4a2d2d;
  border-left: 4px solid #f56565;
}

/* Advanced Options */
.advanced-options {
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid #444;
}

.options-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.option-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #ccc;
}

.option-select {
  width: 100%;
  background: #2d2d2d;
  border: 1px solid #444;
  border-radius: 6px;
  padding: 0.75rem;
  color: white;
}

.option-select:focus {
  outline: none;
  border-color: #ff6b6b;
}

/* Processing Animation */
.processing-section {
  text-align: center;
  padding: 3rem 2rem;
}

.processing-spinner {
  width: 80px;
  height: 80px;
  border: 4px solid #333;
  border-top: 4px solid #ff6b6b;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 2rem;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.processing-text {
  color: #ccc;
  margin-bottom: 2rem;
}

.processing-steps {
  max-width: 400px;
  margin: 0 auto;
}

.processing-step {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  margin-bottom: 0.5rem;
  border-radius: 6px;
  color: #666;
}

.processing-step.active {
  background: #2d2d2d;
  color: #ff6b6b;
}

.processing-step.completed {
  color: #48bb78;
}

.processing-step i {
  width: 20px;
  text-align: center;
}

/* Clarification Section */
.clarification-question {
  background: #2d2d2d;
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.question-title {
  font-weight: 600;
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.priority-badge {
  font-size: 0.75rem;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-weight: 500;
}

.priority-badge.high {
  background: #f56565;
  color: white;
}

.priority-badge.medium {
  background: #feca57;
  color: black;
}

.question-explanation {
  color: #ccc;
  font-size: 0.875rem;
  margin-bottom: 1rem;
}

.question-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.75rem;
}

.option-card {
  background: #3d3d3d;
  border: 2px solid #444;
  border-radius: 6px;
  padding: 1rem;
  cursor: pointer;
  transition: all 0.3s ease;
  text-align: center;
  position: relative;
}

.option-card:hover {
  border-color: #ff6b6b;
}

.option-card.selected {
  background: #4a3737;
  border-color: #ff6b6b;
  color: #ff6b6b;
}

.option-check {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  color: #48bb78;
}

.clarification-input {
  width: 100%;
  background: #3d3d3d;
  border: 1px solid #444;
  border-radius: 6px;
  padding: 0.75rem;
  color: white;
}

.clarification-input:focus {
  outline: none;
  border-color: #ff6b6b;
}

/* Review Section */
.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.confidence-indicator {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.confidence-bar {
  width: 100px;
  height: 8px;
  background: #333;
  border-radius: 4px;
  overflow: hidden;
}

.confidence-fill {
  height: 100%;
  background: linear-gradient(90deg, #f56565, #feca57, #48bb78);
  transition: width 0.3s ease;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.detail-item label {
  display: block;
  font-weight: 500;
  color: #ccc;
  margin-bottom: 0.25rem;
}

.detail-value {
  color: white;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.characters-section {
  margin: 1.5rem 0;
}

.character-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.character-tag {
  background: #ff6b6b;
  color: white;
  padding: 0.25rem 0.75rem;
  border-radius: 20px;
  font-size: 0.875rem;
}

.prompt-section {
  margin: 1.5rem 0;
}

.prompt-display {
  background: #2d2d2d;
  border-radius: 6px;
  padding: 1rem;
  margin-top: 0.5rem;
  font-family: monospace;
  color: #ccc;
}

.technical-details {
  background: #2d2d2d;
  border-radius: 8px;
  padding: 1.5rem;
  margin: 1.5rem 0;
}

.tech-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
}

.tech-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.tech-item label {
  font-size: 0.875rem;
  color: #999;
}

.tech-item span {
  color: white;
  font-weight: 500;
}

.ambiguity-warnings {
  background: #4a3d2d;
  border-left: 4px solid #feca57;
  border-radius: 6px;
  padding: 1.5rem;
  margin: 1.5rem 0;
}

.warning-list {
  margin-top: 1rem;
}

.warning-item {
  color: #feca57;
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.warning-item::before {
  content: '⚠';
  color: #feca57;
}

/* Action buttons */
.input-actions,
.clarification-actions,
.review-actions,
.results-actions {
  display: flex;
  gap: 1rem;
  justify-content: flex-end;
  margin-top: 2rem;
}

.btn-primary,
.btn-secondary {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-primary {
  background: linear-gradient(135deg, #ff6b6b, #feca57);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(255, 107, 107, 0.4);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: #3d3d3d;
  color: #ccc;
  border: 1px solid #555;
}

.btn-secondary:hover {
  background: #4d4d4d;
  color: white;
}

/* Results Section */
.results-section {
  text-align: center;
  padding: 3rem 2rem;
}

.success-message,
.error-message {
  margin-bottom: 2rem;
}

.success-message h3 {
  color: #48bb78;
}

.error-message h3 {
  color: #f56565;
}

/* Generation Type Selector */
.generation-type-selector {
  margin-bottom: 1.5rem;
}

.type-buttons {
  display: flex;
  gap: 1rem;
}

.type-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 1rem;
  background: #2d2d2d;
  border: 2px solid #444;
  border-radius: 8px;
  color: #ccc;
  cursor: pointer;
  transition: all 0.3s ease;
  font-family: inherit;
  font-size: 0.9rem;
  font-weight: 500;
}

.type-btn:hover {
  background: #3d3d3d;
  border-color: #ff6b6b;
  color: #fff;
}

.type-btn.active {
  background: #4a3737;
  border-color: #ff6b6b;
  color: #ff6b6b;
  box-shadow: 0 0 0 2px rgba(255, 107, 107, 0.2);
}

.type-btn i {
  font-size: 1.1rem;
}

/* Responsive Design */
@media (max-width: 768px) {
  .intent-classification-wizard {
    padding: 1rem;
  }

  .progress-steps {
    display: none; /* Hide step labels on mobile */
  }

  .templates-grid {
    grid-template-columns: 1fr;
  }

  .type-buttons {
    flex-direction: column;
  }

  .options-grid {
    grid-template-columns: 1fr;
  }

  .detail-grid,
  .tech-grid {
    grid-template-columns: 1fr;
  }

  .result-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 1rem;
  }

  .input-actions,
  .clarification-actions,
  .review-actions {
    flex-direction: column;
  }
}
</style>