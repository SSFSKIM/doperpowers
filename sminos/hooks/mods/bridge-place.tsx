/**
 * The bridge's place among the secrets guards (the sminos plugin design,
 * §4). The bridge posts what the session showed, so it must sit outside every
 * guard: devcloud's, and cua's vendored copy where devcloud's is not loaded.
 * Inside one, its `tool.call` hook is handed a call's input after the guard
 * restored the secret bytes into it, and the result before the guard scrubbed
 * it. This rule is the backstop that turns a misplaced bridge off instead of
 * streaming those bytes; one outside every loaded guard stays on.
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
 *
 * How the guards are read depends on the bridge's seat (Seat): whose plugin
 * sminos is, and in which tier. A person's sminos is placed by the person's
 * `prependPlugins`, outside devcloud and cua, and reads both as a person's
 * plugin does. The organization's (its managed settings seat sminos) cannot
 * hear a person's devcloud answer its marker, since a person's hooks do not
 * hear an organization's mod's calls; the engine's tier order places it
 * instead. Not covered: a sminos the organization requires in `user` (taken
 * for a person's), a copy whose hash does not match, a seat that changes
 * while the module lives on (the seat is read once per module instance), and
 * guards the managed settings enable for a person's sminos.
 */

export type Place = 'safe' | 'off'

/** A secrets guard, named as the plugin whose module holds it is named in a trace. */
export type Guard = 'devcloud' | 'cua'

/** Said, as a toast and in the debug log, when the bridge turns itself off. */
export const OFF_LINE =
  'sminos: the bridge is off — sminos must load outside devcloud and cua; set prependPlugins in ~/.claude/settings.json to ["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"]'

/**
 * Said instead of OFF_LINE where the managed settings seat sminos: on such a
 * machine the engine ignores the user settings' `prependPlugins`.
 */
export const MANAGED_OFF_LINE =
  'sminos: the bridge is off — sminos must load outside devcloud and cua; the managed settings seat it, so list sminos@doperpowers in their prependPlugins, ahead of devcloud and cua'

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
 * Whether the managed settings seat cua as the organization's: they enable
 * `cua@cua` and declare its marketplace, ids matched case-folded, as the
 * engine matches them. A cua they enable without declaring its marketplace
 * loads in `user`, beneath a bridge they seat in `prepend`.
 */
export function isManagedCua(managed: unknown): boolean {
  if (!isRecord(managed) || !isRecord(managed.enabledPlugins) || !isRecord(managed.extraKnownMarketplaces)) {
    return false
  }
  const enabled = Object.entries(managed.enabledPlugins).some(([id, on]) => on === true && id.toLowerCase() === 'cua@cua')
  return enabled && Object.keys(managed.extraKnownMarketplaces).some((name) => name.toLowerCase() === 'cua')
}

/**
 * Whose the bridge's seat is, and where:
 * - `person`: a plugin a person installs, in any tier. The guards a person
 *   installs hear its reads, and the user settings name cua's copy.
 * - `outer`: the organization's, in `prepend`. Every plugin a person
 *   installs loads in `user` there, beneath it by the engine's tier order,
 *   so no guard of a person's can be outside it, read or not. A guard the
 *   organization seats can be (listed ahead of sminos): its devcloud hears
 *   the marker read, and the managed settings seat its cua (isManagedCua).
 *   A `cua` link beneath it is a guard beneath it. A dispatch an
 *   organization's mod raised runs none of a person's hooks, so cua's link
 *   missing from its trace proves nothing there.
 * - `inner`: the organization's in any other tier. It is inside every plugin
 *   a person installs and cannot hear a person's devcloud.
 */
export type Seat = 'person' | 'outer' | 'inner'

/**
 * The seat, from the tier the bridge sits in (what its own hook hears its own
 * call raised from) and the managed settings, read only outside `user`. A
 * machine with managed settings takes both tier lists from them alone and
 * loads every plugin a person enables in `user`, so a tier outside `user` is
 * the organization's exactly where the managed settings hold anything; with
 * none, `prepend` and `append` are the person's own lists.
 */
export async function seatOf(tier: string, policy: () => Promise<unknown>): Promise<Seat> {
  if (tier === 'user') {
    return 'person'
  }
  const managed = await policy()
  if (!isRecord(managed) || Object.keys(managed).length === 0) {
    return 'person'
  }
  return tier === 'prepend' ? 'outer' : 'inner'
}

/**
 * What one dispatch says of the bridge's place:
 * - `guarded`: a guard the reads report loaded has its link beneath, or both
 *   guards' links are;
 * - `unguarded`: the reads report no guard loaded;
 * - `off`: the loaded guard is outside the bridge;
 * - `unsettled`: the dispatch cannot tell where a loaded guard is, and what
 *   it would post is its own to drop; the place stays as it was.
 *
 * Either of the first two settles the first verdict as safe. Only `guarded`
 * turns an off bridge back on: cua's leg reads the settings' intent, not
 * the modules loaded, so cua disabled in the settings without a reload
 * leaves its module outside the bridge while the reads say no guard.
 */
export type Verdict = 'guarded' | 'unguarded' | 'off' | 'unsettled'

/**
 * One settled dispatch's verdict. `trace` is the dispatch's `next.trace`,
 * `raisedBy` who `next.origin` names, `seat` reads the bridge's seat,
 * and `loaded` which guard is loaded now, as a bridge in that seat can read
 * it. The reads are skipped when the links beneath name both guards, which
 * leaves no guard outside. An `inner` seat is `off` with no more read: a guard
 * a person installs is outside it whenever one is enabled, now or later in
 * the session, and the bridge cannot read devcloud's.
 *
 * `guarded` and `unguarded` need no more than that, whether or not the trace
 * reaches the engine. `off` needs proof that the loaded guard is outside, and
 * two kinds of dispatch that lack its link give none, and so no verdict:
 * - a trace cut short of the engine's entry, by a link that answered the
 *   call itself (a plugin's own tool, a refused row), lists nothing beneath
 *   that link;
 * - a guard's hooks do not run on a dispatch its own plugin raised (cua's
 *   `/secret` appending its note);
 * - for an `outer` seat, a person's hooks do not run on a dispatch an
 *   organization's mod raised (`prepend` or `append`), and a cua the
 *   managed settings enable may load in `user`. A devcloud whose marker
 *   such a bridge reads is the organization's, whose hooks run there.
 *   Such a dispatch is `unsettled`: its own payload is dropped.
 */
export async function verdictOf(
  trace: readonly { plugin: string }[],
  raisedBy: { readonly plugin: string; readonly tier: string },
  seat: () => Promise<Seat>,
  loaded: (seat: Seat) => Promise<Guard | undefined>,
): Promise<Verdict | undefined> {
  const beneath = new Set(trace.map((link) => link.plugin))
  if (beneath.has('devcloud') && beneath.has('cua')) {
    return 'guarded'
  }
  const at = await seat()
  if (at === 'inner') {
    return 'off'
  }
  const guard = await loaded(at)
  if (guard === undefined) {
    return at === 'outer' && beneath.has('cua') ? 'guarded' : 'unguarded'
  }
  if (beneath.has(guard)) {
    return 'guarded'
  }
  if (!beneath.has('engine') || raisedBy.plugin === guard) {
    return undefined
  }
  return at === 'outer' && guard === 'cua' && (raisedBy.tier === 'prepend' || raisedBy.tier === 'append') ? 'unsettled' : 'off'
}
