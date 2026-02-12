/**
 * Tests for the API client (src/api/client.ts).
 * Mocks global fetch to verify request URLs, methods, and bodies.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetch before importing the module
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

// Helper to create a mock Response
function mockResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  } as unknown as Response
}

// Import after mocking fetch
import { api } from '@/api/client'

beforeEach(() => {
  mockFetch.mockReset()
})

describe('generateForCharacter', () => {
  it('POSTs to /api/lora/generate/{slug} with JSON body', async () => {
    const responseData = {
      prompt_id: 'abc-123',
      character: 'mario',
      generation_type: 'image',
      prompt_used: 'Mario in a field',
      checkpoint: 'realcartoonPixar_v12.safetensors',
      seed: 42,
    }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.generateForCharacter('mario', {
      generation_type: 'image',
      prompt_override: 'Mario in a field',
    })

    expect(mockFetch).toHaveBeenCalledOnce()
    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/lora/generate/mario')
    expect(options.method).toBe('POST')
    const body = JSON.parse(options.body)
    expect(body.generation_type).toBe('image')
    expect(body.prompt_override).toBe('Mario in a field')
    expect(result.prompt_id).toBe('abc-123')
  })
})

describe('getGenerationStatus', () => {
  it('GETs /api/lora/generate/{promptId}/status', async () => {
    const responseData = { status: 'completed', progress: 1.0, images: ['out.png'] }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.getGenerationStatus('abc-123')

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/lora/generate/abc-123/status')
    expect(options.method).toBeUndefined() // GET is default
    expect(result.status).toBe('completed')
  })
})

describe('getGallery', () => {
  it('passes limit param', async () => {
    const responseData = { images: [{ filename: 'img.png', created_at: '2026-01-01', size_kb: 100 }] }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    await api.getGallery(10)

    const [url] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/lora/gallery?limit=10')
  })
})

describe('galleryImageUrl', () => {
  it('returns correct URL string', () => {
    const url = api.galleryImageUrl('test_image.png')
    expect(url).toBe('/api/lora/gallery/image/test_image.png')
  })

  it('encodes special characters', () => {
    const url = api.galleryImageUrl('image with spaces.png')
    expect(url).toContain('image%20with%20spaces.png')
  })
})

describe('echoChat', () => {
  it('sends message and optional character_slug', async () => {
    const responseData = { response: 'Echo reply', context_used: true, character_context: 'Mario context' }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    await api.echoChat('Tell me about Mario', 'mario')

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/lora/echo/chat')
    expect(options.method).toBe('POST')
    const body = JSON.parse(options.body)
    expect(body.message).toBe('Tell me about Mario')
    expect(body.character_slug).toBe('mario')
  })

  it('sends without character_slug when omitted', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ response: 'reply', context_used: false }))

    await api.echoChat('general question')

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.character_slug).toBeUndefined()
  })
})

describe('echoEnhancePrompt', () => {
  it('sends prompt and optional slug', async () => {
    const responseData = {
      original_prompt: 'Mario standing',
      echo_brain_context: ['memory 1'],
      suggestion: 'improved prompt',
    }
    mockFetch.mockResolvedValueOnce(mockResponse(responseData))

    const result = await api.echoEnhancePrompt('Mario standing', 'mario')

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.prompt).toBe('Mario standing')
    expect(body.character_slug).toBe('mario')
    expect(result.echo_brain_context).toEqual(['memory 1'])
  })
})

describe('error handling', () => {
  it('throws ApiError with correct status on 404', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ detail: 'Not found' }, 404))

    await expect(api.getGenerationStatus('bad-id')).rejects.toThrow()

    try {
      mockFetch.mockResolvedValueOnce(mockResponse({ detail: 'Not found' }, 404))
      await api.getGenerationStatus('bad-id')
    } catch (err: unknown) {
      expect((err as { name: string }).name).toBe('ApiError')
      expect((err as { status: number }).status).toBe(404)
    }
  })
})

describe('clearStuckGenerations', () => {
  it('POSTs to /api/lora/generate/clear-stuck', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ message: 'Cleared 0', cancelled: 0 }))

    const result = await api.clearStuckGenerations()

    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/lora/generate/clear-stuck')
    expect(options.method).toBe('POST')
    expect(result.cancelled).toBe(0)
  })
})
