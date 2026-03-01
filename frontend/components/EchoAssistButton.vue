<template>
  <div ref="anchorEl" class="echo-assist" :class="{ compact }">
    <!-- Trigger button -->
    <button
      class="btn echo-assist-btn"
      :disabled="disabled || loading"
      @click="requestSuggestion"
    >
      <span class="echo-icon">E</span>
      <template v-if="loading">
        <span class="spinner" style="width: 12px; height: 12px;"></span>
      </template>
      <template v-else>{{ label }}</template>
    </button>

    <!-- Suggestion panel — teleported to body to avoid overflow clipping -->
    <Teleport to="body">
      <div
        v-if="showPanel"
        :style="{ ...panelStyle, minWidth: '320px', maxWidth: '480px', padding: '12px', background: 'var(--bg-secondary)', border: '1px solid var(--accent-primary)', borderRadius: '4px', boxShadow: '0 4px 16px rgba(0,0,0,0.4)' }"
      >
        <!-- Error state -->
        <div v-if="errorMsg" style="padding: 8px 10px; background: rgba(160,80,80,0.1); border: 1px solid var(--status-error); border-radius: 3px; color: var(--status-error);">
          <div style="font-size: 12px; margin-bottom: 8px;">{{ errorMsg }}</div>
          <button class="btn" style="font-size: 11px; padding: 3px 10px;" @click="requestSuggestion">Retry</button>
          <button class="btn" style="font-size: 11px; padding: 3px 10px; margin-left: 4px;" @click="dismiss">Close</button>
        </div>

        <!-- Suggestion state -->
        <template v-else>
          <div style="font-size: 12px; line-height: 1.5; color: var(--text-primary); max-height: 200px; overflow-y: auto; padding: 8px 10px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 3px; white-space: pre-wrap; word-wrap: break-word;">{{ suggestion }}</div>
          <div style="display: flex; gap: 6px; align-items: center; margin-top: 8px;">
            <button class="btn btn-primary" style="font-size: 12px; padding: 4px 14px;" @click="accept">Accept</button>
            <button class="btn" style="font-size: 12px; padding: 4px 10px;" @click="dismiss">Dismiss</button>
            <span v-if="executionTime" style="font-size: 10px; color: var(--text-muted); margin-left: auto;">{{ executionTime }}ms</span>
          </div>
        </template>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick } from 'vue'
import { api } from '@/api/client'
import type { NarrateRequest } from '@/types'

const props = withDefaults(defineProps<{
  contextType: NarrateRequest['context_type']
  contextPayload?: Partial<NarrateRequest>
  currentValue?: string
  label?: string
  compact?: boolean
  disabled?: boolean
}>(), {
  label: 'Suggest',
  compact: false,
  disabled: false,
})

const emit = defineEmits<{
  accept: [payload: { suggestion: string; contextType: string; fields?: Record<string, any> }]
  dismiss: []
  error: [payload: { message: string }]
}>()

const anchorEl = ref<HTMLElement>()
const loading = ref(false)
const showPanel = ref(false)
const panelStyle = reactive({ position: 'fixed' as const, top: '0px', left: '0px', zIndex: 9999 })

function updatePanelPosition() {
  if (!anchorEl.value) return
  const rect = anchorEl.value.getBoundingClientRect()
  panelStyle.top = `${rect.bottom + 6}px`
  panelStyle.left = `${rect.left}px`
}
const suggestion = ref('')
const fields = ref<Record<string, any> | undefined>(undefined)
const errorMsg = ref('')
const executionTime = ref(0)

async function requestSuggestion() {
  loading.value = true
  errorMsg.value = ''
  showPanel.value = false

  const payload: NarrateRequest = {
    context_type: props.contextType,
    current_value: props.currentValue,
    ...props.contextPayload,
  }

  try {
    const result = await api.echoNarrate(payload)
    suggestion.value = result.suggestion
    fields.value = result.fields
    executionTime.value = result.execution_time_ms
    updatePanelPosition()
    showPanel.value = true
  } catch (err: any) {
    errorMsg.value = err?.message || 'Echo Brain unavailable'
    updatePanelPosition()
    showPanel.value = true
    emit('error', { message: errorMsg.value })
  } finally {
    loading.value = false
  }
}

function accept() {
  emit('accept', { suggestion: suggestion.value, contextType: props.contextType, fields: fields.value })
  showPanel.value = false
  suggestion.value = ''
  fields.value = undefined
}

function dismiss() {
  showPanel.value = false
  suggestion.value = ''
  errorMsg.value = ''
  emit('dismiss')
}
</script>

<style scoped>
.echo-assist {
  position: relative;
  display: inline-block;
}

.echo-assist-btn {
  font-size: 11px;
  padding: 3px 10px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.echo-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 3px;
  background: var(--accent-primary);
  color: var(--bg-primary);
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
}

.echo-panel {
  min-width: 320px;
  max-width: 480px;
  padding: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--accent-primary);
  border-radius: 4px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}

.echo-suggestion {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-primary);
  max-height: 200px;
  overflow-y: auto;
  padding: 8px 10px;
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: 3px;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.echo-error {
  padding: 8px 10px;
  background: rgba(160, 80, 80, 0.1);
  border: 1px solid var(--status-error);
  border-radius: 3px;
  color: var(--status-error);
}

.compact .echo-assist-btn {
  padding: 2px 8px;
  font-size: 10px;
}

.compact .echo-icon {
  width: 14px;
  height: 14px;
  font-size: 9px;
}
</style>
