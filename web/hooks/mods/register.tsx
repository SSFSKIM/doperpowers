import type { On } from 'claude-code'

import { registerFetch } from './fetch'

/** The plugin's one hooks module: the fetch tool, `mcp__web__fetch`, and the cache's prune. */
export function register(on: On) {
  registerFetch(on)
}
