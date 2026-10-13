import type { On } from 'claude-code'

import { registerAgents } from './agents'
import { registerAsk, registerAskBand } from './ask'
import { registerCompact } from './compact'
import { registerKairos } from './kairos'
import { registerToHuman } from './to-human'

/**
 * The plugin's one hooks module: each mod registers its own hooks. The engine
 * loads this only where function hooks are enabled; the shell hooks beside
 * it run everywhere.
 */
export function register(on: On) {
  // Before to-human: its band above the prompt draws without calling on, so
  // the ask's line there must be the outer hook, drawing above it.
  registerAskBand(on)
  registerToHuman(on)
  // After to-human: hooks registered later sit inside its own, where the
  // ask's transcript rows must be.
  registerAsk(on)
  // Before kairos: both draw in the footer's mode slot, and the agents button
  // wraps what kairos drew there.
  registerAgents(on)
  registerKairos(on)
  registerCompact(on)
}
