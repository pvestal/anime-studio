/**
 * Shared API infrastructure: error class, request factory, and fetch helpers.
 *
 * Each domain module creates its own request function via createRequest():
 *   const request = createRequest('/api/story')
 *   request('/projects')  // → GET /api/story/projects
 */

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * Create a domain-specific JSON request function.
 * Prepends the given base path to every endpoint call.
 */
export function createRequest(base: string) {
  return async function<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const controller = new AbortController()
    const timeoutMs = 15000
    const timer = setTimeout(() => controller.abort(), timeoutMs)

    try {
      const response = await fetch(`${base}${endpoint}`, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
        ...options,
        signal: controller.signal,
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new ApiError(response.status, errorText)
      }

      return response.json()
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new ApiError(408, `Request timed out after ${timeoutMs / 1000}s — server may be busy`)
      }
      throw err
    } finally {
      clearTimeout(timer)
    }
  }
}
