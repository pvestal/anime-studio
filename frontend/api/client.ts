/**
 * Unified API client — re-exports from domain-specific modules.
 *
 * All existing `import { api } from '@/api/client'` calls continue to work.
 * New code can also import from domain files directly:
 *   import { storyApi }    from '@/api/story'
 *   import { trainingApi } from '@/api/training'
 *   import { visualApi }   from '@/api/visual'
 *   import { scenesApi }   from '@/api/scenes'
 *   import { echoApi }     from '@/api/echo'
 *
 * Shared helpers:
 *   import { ApiError, createRequest } from '@/api/base'
 */

import { storyApi } from './story'
import { trainingApi } from './training'
import { visualApi } from './visual'
import { scenesApi } from './scenes'
import { echoApi } from './echo'
import { learningApi } from './learning'
import { voiceApi } from './voice'
import { episodesApi } from './episodes'
import { interactiveApi } from './interactive'

// Re-export shared infrastructure
export { ApiError, createRequest } from './base'

// Re-export domain APIs for granular imports
export { storyApi } from './story'
export { trainingApi } from './training'
export { visualApi } from './visual'
export { scenesApi } from './scenes'
export { echoApi } from './echo'
export { learningApi } from './learning'
export { voiceApi } from './voice'
export { episodesApi } from './episodes'
export { interactiveApi } from './interactive'

/**
 * Composed api object — merges every domain API into a single namespace.
 * This preserves backward compatibility: `api.getCharacters()`, `api.echoChat()`, etc.
 */
export const api = {
  ...storyApi,
  ...trainingApi,
  ...visualApi,
  ...scenesApi,
  ...echoApi,
  ...learningApi,
  ...voiceApi,
  ...episodesApi,
  ...interactiveApi,
}
