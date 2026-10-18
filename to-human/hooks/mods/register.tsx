import type { On } from 'claude-code'

import { registerToHuman } from './to-human'

/**
 * The plugin's one hooks module. The view is a plugin of its own, not one of
 * doperpowers' mods: the engine runs none of a plugin's render hooks on a row
 * that plugin submitted, and doperpowers submits prompts (the bridge's
 * deliveries from other sessions, the ask's answers, the compact mod's resume
 * prompt) that the view folds. It lists doperpowers under `dependencies`, so
 * its hooks sit outside doperpowers' on every event, where it sees the ask
 * mod's rows before the ask draws them.
 */
export function register(on: On) {
  registerToHuman(on)
}
