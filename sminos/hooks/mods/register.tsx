import type { On } from 'claude-code'

import { registerAddress } from './address'
import { registerAsk, registerAskBand } from './ask'
import { registerBackticks } from './backticks'
import { registerBridge } from './bridge'
import { registerName } from './name'
import { registerSheet, registerSheetBand } from './sheet'

/**
 * The plugin's one hooks module: each mod registers its own hooks. The engine
 * loads this only where function hooks are enabled; the shell hooks beside
 * it run everywhere.
 *
 * Across plugins the order is the owner's settings': `prependPlugins` names
 * to-human, sminos and doperpowers in that order, which seats this module
 * outside doperpowers' and outside every user-tier plugin's — devcloud's
 * secrets guard and cua's among them (hooks/mods/README.md, the bridge).
 */
export function register(on: On) {
  // First: the bridge's hooks are the module's outermost, so it reports what
  // the session showed and recorded, after the ask and the address had their say.
  registerBridge(on)
  // Inside the bridge, so the bridge reports a refused call as the session saw it.
  registerBackticks(on)
  // The sheet's line above the prompt, outside today's (which yields under the sheet).
  registerSheetBand(on)
  registerAskBand(on)
  // Before the ask, so the sheet's hooks are the outer ones of each event: the
  // sheet handles what is its own and passes the rest on (sheet.tsx, I11).
  registerSheet(on)
  registerAsk(on)
  registerAddress(on)
  registerName(on)
}
