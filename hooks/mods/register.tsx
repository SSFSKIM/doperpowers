import type { On } from 'claude-code'

import { registerAppeal } from './appeal'
import { registerCompact } from './compact'
import { registerInterim } from './interim'
import { registerKairos } from './kairos'
import { registerReload } from './reload'

/**
 * The plugin's one hooks module: each mod registers its own hooks. The engine
 * loads this only where function hooks are enabled; the shell hooks beside
 * it run everywhere. The bridge, the ask and the address are the sminos
 * plugin's, whose module sits outside this one (the owner's
 * `prependPlugins`), so its outer hooks see the appeal's notice on a block's
 * result and its allow on a passed re-run as the session showed them, and
 * interim runs inside the ask's prompt.submit hook, which puts back what it
 * attached to a prompt dropped beneath it.
 */
export function register(on: On) {
  registerAppeal(on)
  registerKairos(on)
  // Before compact: the reload's turn.complete wraps compact's, so the turn
  // it waits on lasts until the compaction the model asked for at its end
  // has run, and no reload lands in the middle of it.
  registerReload(on)
  registerCompact(on)
  registerInterim(on)
}
