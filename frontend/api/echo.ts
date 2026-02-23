/**
 * Echo Brain domain: chat, prompt enhancement, narrator assist, status.
 * Backend: /api/echo/* (echo_router mounted at /api with /echo prefix in decorators)
 */
import type {
  EchoChatResponse,
  EchoEnhanceResponse,
  NarrateRequest,
  NarrateResponse,
} from '@/types'
import { createRequest } from './base'

const request = createRequest('/api')

export const echoApi = {
  async echoChat(message: string, characterSlug?: string): Promise<EchoChatResponse> {
    return request('/echo/chat', {
      method: 'POST',
      body: JSON.stringify({ message, character_slug: characterSlug }),
    })
  },

  async echoEnhancePrompt(prompt: string, characterSlug?: string): Promise<EchoEnhanceResponse> {
    return request('/echo/enhance-prompt', {
      method: 'POST',
      body: JSON.stringify({ prompt, character_slug: characterSlug }),
    })
  },

  async echoNarrate(payload: NarrateRequest): Promise<NarrateResponse> {
    return request('/echo/narrate', {
      method: 'POST',
      body: JSON.stringify(payload),
      timeoutMs: 60000,
    })
  },

  async echoStatus(): Promise<{ status: string }> {
    return request('/echo/status')
  },
}
