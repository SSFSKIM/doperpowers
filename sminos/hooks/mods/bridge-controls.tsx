/**
 * The desk's per-control capability (DX5 `capabilities.controls`, the desk
 * control surface spec's Interfaces): one key per control, named as
 * remote-architecture's lane map names them, so a path-B daemon fills the
 * same keys and the web greys a control by its key, never by lane. A key says
 * whether the control works on this bridge, not whether a milestone touched
 * it: the controls the desk has had since M0 are available.
 */

/** One control's capability: whether this bridge can do it, and why not. */
export type Control = { available: boolean; reason?: string }

/** Every key of the lane map's `ControlCapabilities`, in its order. */
export const CONTROL_KEYS = [
  'read.usage', 'read.config', 'read.settings', 'read.mcp',
  'btw', 'compact', 'model',
  'mcp.enable', 'mcp.disable', 'mcp.reconnect',
  'decide', 'decide.scope', 'decide.interrupt',
  'decide.addDirectory', 'stop-agent', 'tell',
  'media', 'forget', 'rewind-files', 'elicitation.answer',
] as const
export type ControlKey = (typeof CONTROL_KEYS)[number]

/**
 * What this bridge does: the controls from before the wave, and those the
 * wave has built so far (MW1 the reads, MW2 the side question, MW3 the
 * scoped allows: `decide.addDirectory` is an `addDirectories` suggestion
 * through `decide.scope`, never a directory of the desk's own).
 */
const AVAILABLE: ReadonlySet<ControlKey> = new Set<ControlKey>([
  'read.usage', 'read.config', 'read.settings', 'read.mcp',
  'btw', 'compact', 'model', 'mcp.enable', 'mcp.disable', 'mcp.reconnect', 'decide',
  'decide.scope', 'decide.addDirectory',
])

/** What lane A cannot do, with the standing reason: no later sminos changes these, only the engine or another path. */
export const STANDING: Readonly<Partial<Record<ControlKey, string>>> = {
  'decide.interrupt': "a decision is answered once it is queued, so a deny cannot report what stopping the turn left running: deny, then Interrupt",
  forget: 'after --resume the engine brings back what a cut left out (2.1.310): it needs an engine fix or a supported cut',
  'rewind-files': "the mod API has no file rollback: /rewind in the terminal",
  'elicitation.answer': "a mod's answer carries no action or content, so it cannot answer an MCP server's form: answer it in the terminal",
}

/** What a control a later sminos adds says on this one. */
export const notInVersion = (sminos: string) => `not in sminos ${sminos}: a later version of the plugin adds it`

/** The whole map, every key present: the available ones, then each other with its reason. */
export function controlsOf(sminos: string): Record<ControlKey, Control> {
  const map = {} as Record<ControlKey, Control>
  for (const key of CONTROL_KEYS) {
    const standing = STANDING[key]
    map[key] = AVAILABLE.has(key) ? { available: true } : { available: false, reason: standing ?? notInVersion(sminos) }
  }
  return map
}
