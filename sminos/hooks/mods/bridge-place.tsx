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
 * outside a bridge that lives on, or inside it. `off` lasts until a dispatch
 * that began after it sees a loaded guard beneath the bridge (`guarded`;
 * bridge.tsx, judgePlace): the trace and the reads are taken at different
 * moments, and cua's leg reads the settings' intent, so a verdict can be off
 * for a while and then right again. A guard truly removed leaves the bridge
 * off until sminos itself reloads.
 */

export type Place = 'safe' | 'off'

/** A secrets guard, named as the plugin whose module holds it is named in a trace. */
export type Guard = 'devcloud' | 'cua'

/** Said, as a toast and in the debug log, when the bridge turns itself off. */
export const OFF_LINE =
  'sminos: the bridge is off — sminos must load outside devcloud and cua; set prependPlugins in ~/.claude/settings.json to ["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"]'

/** Said, as a toast and in the debug log, when an off bridge finds itself outside the guards again. */
export const ON_LINE = 'sminos: the bridge is on again — sminos loads outside devcloud and cua now'

const isRecord =(value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)

/**
 * Whether devcloud's guard is loaded now. devcloud's loaded module answers a
 * read of its marker itself, at state version 0, and stores nothing. A value
 * at version 1 or more is one a devcloud before 0.5.0 stored, which outlives
 * its module (board #101), so it does not count. The value is exactly the two
 * keys devcloud answers, as cua's own check reads it (`isDevcloudMarker`), so
 * the bridge and cua's copy never disagree on whether devcloud's guard acts.
 */
export function isLiveMarker(read: { value: unknown; version: number }): boolean {
  const marker = read.value
  return read.version === 0 && isRecord(marker) && Object.keys(marker).length === 2 && marker.owner === 'devcloud' && marker.version === 1
}

/** Whether the user settings enable `cua@cua`, whose copy of the guard acts when devcloud's is not loaded. */
export function isCuaEnabled(settings: unknown): boolean {
  return isRecord(settings) && isRecord(settings.enabledPlugins) && settings.enabledPlugins['cua@cua'] === true
}

/**
 * What one dispatch says of the bridge's place:
 * - `guarded`: a guard the reads report loaded has its link beneath, or both
 *   guards' links are;
 * - `unguarded`: the reads report no guard loaded;
 * - `off`: the loaded guard is outside the bridge.
 *
 * Either of the first two settles the first verdict as safe. Only `guarded`
 * turns an off bridge back on: cua's leg reads the settings' intent, not
 * the modules loaded, so cua disabled in the settings without a reload
 * leaves its module outside the bridge while the reads say no guard.
 */
export type Verdict = 'guarded' | 'unguarded' | 'off'

/**
 * One settled dispatch's verdict. `trace` is the dispatch's `next.trace`,
 * `raisedBy` the plugin `next.origin` names, and `loaded` reads which guard
 * is loaded now. The reads are skipped when the links beneath name both
 * guards, which leaves no guard outside.
 *
 * `guarded` and `unguarded` need no more than that, whether or not the trace
 * reaches the engine. `off` needs proof that the loaded guard is outside, and
 * two kinds of dispatch that lack its link give none, and so no verdict:
 * - a trace cut short of the engine's entry, by a link that answered the
 *   call itself (a plugin's own tool, a refused row), lists nothing beneath
 *   that link;
 * - a guard's hooks do not run on a dispatch its own plugin raised (cua's
 *   `/secret` appending its note).
 */
export async function verdictOf(trace: readonly { plugin: string }[], raisedBy: string | undefined, loaded: () => Promise<Guard | undefined>): Promise<Verdict | undefined> {
  const beneath = new Set(trace.map((link) => link.plugin))
  if (beneath.has('devcloud') && beneath.has('cua')) {
    return 'guarded'
  }
  const guard = await loaded()
  if (guard === undefined) {
    return 'unguarded'
  }
  if (beneath.has(guard)) {
    return 'guarded'
  }
  return beneath.has('engine') && raisedBy !== guard ? 'off' : undefined
}
