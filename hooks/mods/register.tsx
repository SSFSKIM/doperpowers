import type { On } from 'claude-code'

import { registerAgents } from './agents'
import { registerKairos } from './kairos'
import { registerToHuman } from './to-human'

/**
 * The plugin's one hooks module: each mod registers its own hooks. The engine
 * loads this only where function hooks are enabled; the shell hooks beside
 * it run everywhere.
 */
export function register(on: On) {
  registerToHuman(on)
  // Before kairos: both draw in the footer's mode slot, and the agents button
  // wraps what kairos drew there.
  registerAgents(on)
  registerKairos(on)
}
