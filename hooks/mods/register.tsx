import type { On } from 'claude-code'

import { registerAgents } from './agents'
import { registerAppeal } from './appeal'
import { registerAsk, registerAskBand } from './ask'
import { registerBridge } from './bridge'
import { registerCompact } from './compact'
import { registerInterim } from './interim'
import { registerKairos } from './kairos'

/**
 * The plugin's one hooks module: each mod registers its own hooks. The engine
 * loads this only where function hooks are enabled; the shell hooks beside
 * it run everywhere.
 */
export function register(on: On) {
  // First: the bridge's hooks are the outermost, so it reports what the
  // session showed and recorded, after every other mod had its say.
  registerBridge(on)
  // After the bridge: its outer hooks see the appeal's notice on a block's
  // result and its allow on a passed re-run, as the session showed them.
  registerAppeal(on)
  registerAskBand(on)
  registerAsk(on)
  // Before kairos: both draw in the footer's mode slot, and the agents button
  // wraps what kairos drew there.
  registerAgents(on)
  registerKairos(on)
  registerCompact(on)
  // Inside the ask's prompt.submit hook, which puts back what it attached
  // to a prompt dropped beneath it.
  registerInterim(on)
}
