import type { On } from 'claude-code'

import { registerKairos } from './kairos'
import { registerToHuman } from './to-human'

/**
 * The plugin's one hooks module: each mod registers its own hooks. The engine
 * loads this only where function hooks are enabled; the shell hooks beside
 * it run everywhere.
 */
export function register(on: On) {
  registerToHuman(on)
  registerKairos(on)
}
