/**
 * The bridge's place among the secrets guards (the sminos plugin design,
 * §4). The bridge posts what the session showed, so it must sit outside every
 * guard: devcloud's, and cua's vendored copy where devcloud's is not loaded.
 * Inside one, its `tool.call` hook is handed a call's input after the guard
 * restored the secret bytes into it, and the result before the guard scrubbed
 * it. The owner's `prependPlugins` places it there. This rule is the backstop
 * that turns a misplaced bridge off instead of streaming those bytes.
 *
 * It reads what settled beneath one of the bridge's hooks: `next.trace` names
 * the plugin of every link beneath it. Each settled `tool.call` and
 * `session.append` gives a verdict, since `/reload-plugins` re-instantiates
 * only the modules that changed, so a guard enabled mid-session can load
 * outside a bridge that lives on. `off` is terminal for the module instance.
 */

export type Place = 'safe' | 'off'

/** A secrets guard, named as the plugin whose module holds it is named in a trace. */
export type Guard = 'devcloud' | 'cua'

/** Said, as a toast and in the debug log, when the bridge turns itself off. */
export const OFF_LINE =
  'sminos: the bridge is off — sminos must load outside devcloud and cua; set prependPlugins in ~/.claude/settings.json to ["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"]'

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)

/**
 * Whether devcloud's guard is loaded now. devcloud's loaded module answers a
 * read of its marker itself, at state version 0, and stores nothing. A value
 * at version 1 or more is one a devcloud before 0.5.0 stored, which outlives
 * its module (board #101), so it does not count.
 */
export function isLiveMarker(read: { value: unknown; version: number }): boolean {
  return read.version === 0 && isRecord(read.value) && read.value.owner === 'devcloud' && read.value.version === 1
}

/** Whether the user settings enable `cua@cua`, whose copy of the guard acts when devcloud's is not loaded. */
export function isCuaEnabled(settings: unknown): boolean {
  return isRecord(settings) && isRecord(settings.enabledPlugins) && settings.enabledPlugins['cua@cua'] === true
}

/**
 * One settled dispatch's verdict on the bridge's place. `trace` is the
 * dispatch's `next.trace`, `raisedBy` the plugin `next.origin` names, and
 * `loaded` reads which guard is loaded now. The reads are skipped when the
 * links beneath name both guards, which leaves no guard outside.
 *
 * Off needs proof that the loaded guard is outside. Two kinds of dispatch
 * give none, and so no verdict:
 * - a trace cut short of the engine's entry, by a link that answered the
 *   call itself (a plugin's own tool, a refused row), lists nothing beneath
 *   that link;
 * - a guard's hooks do not run on a dispatch its own plugin raised (cua's
 *   `/secret` appending its note).
 */
export async function placeOf(trace: readonly { plugin: string }[], raisedBy: string | undefined, loaded: () => Promise<Guard | undefined>): Promise<Place | undefined> {
  const beneath = new Set(trace.map((link) => link.plugin))
  if (beneath.has('devcloud') && beneath.has('cua')) {
    return 'safe'
  }
  const guard = await loaded()
  if (guard === undefined || beneath.has(guard)) {
    return 'safe'
  }
  return beneath.has('engine') && raisedBy !== guard ? 'off' : undefined
}
