import type { On } from 'claude-code'

import { registerToHuman } from './to-human'

/**
 * The plugin's one hooks module. The view is a plugin of its own, not one of
 * sminos' or doperpowers' mods: the engine runs none of a plugin's render
 * hooks on a row that plugin submitted, and sminos submits prompts (the
 * bridge's deliveries from other sessions, the ask's answers) as doperpowers
 * submits the compact mod's resume prompt, all of which the view folds. It
 * lists sminos under `dependencies`, which installs and enables sminos with
 * it; its place outside sminos' hooks, where it sees the ask's rows before the
 * ask draws them, comes from the owner's `prependPlugins` (to-human, sminos,
 * doperpowers, in that order), not from the dependency.
 */
export function register(on: On) {
  registerToHuman(on)
}
