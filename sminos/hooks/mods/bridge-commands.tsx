import { ROUTE_TABLES } from './bridge-routes'
import type { Route, RouteEntry, RouteTable } from './bridge-routes'

/**
 * Which slash commands the desk may run, and how (the desk control surface's
 * route table, spec 2026-10-22, §2): every (command, form) is in one class,
 * and only enabled `run` and `run-prompt` routes are ever run. A bare panel
 * form is never run: `$.command.run` of one holds the session's whole input
 * queue until someone presses keys in the terminal (H-panel).
 *
 * The tables are measured per engine release (bridge-routes.tsx, written
 * from the fixture both repositories test against); a session uses the
 * newest table measured at or below its engine, and the capability says
 * which (`routes.measured`). An engine older than every table has none: each
 * built-in is then refused as not measured. A built-in no table lists is
 * refused the same way, never tried. A command that is no built-in
 * (`$.command.list()`'s `source`) takes the route its plugin exception names,
 * else `run-prompt` (enabled from M1); one this plugin serves is refused
 * (`self`): a plugin's own `$.command.run` skips its own `command.run` hooks.
 *
 * Nothing here takes `$`: the bridge reads the listing and runs the route.
 */

/** Why a command is not run (DX5's `command` op refusal codes, but `stopped`, which the engine's own refusal is). */
export type RefusalCode = 'unknown-builtin' | 'panel' | 'routed' | 'follow' | 'drop' | 'local' | 'bad-args' | 'disabled' | 'self'
export type Refusal = { code: RefusalCode; reason: string }
/** A command as `$.command.list()` lists it: the fields the route reads. */
export type Listed = { name: string; source: string; plugin?: string }

/** The refusals' words, in the reasons' voice the desk's capabilities use: what cannot be done, and why. */
export const PANEL_REASON = "opens a panel in the terminal; it would hold the session's queue"
export const FOLLOW_REASON = 'changes the session id; following comes with M4'
export const UNKNOWN_REASON = 'not a command this session knows'
export const UNMEASURED_REASON = 'not measured on this engine'
export const SELF_REASON = 'the sminos plugin serves it, and a plugin cannot run its own command: run it from the terminal'
const LOCAL_REASON = "the desk's own: the browser does it"
/** A command no table lists that is no built-in: a turn's prompt, run from M1. */
const RUN_PROMPT: Route = { class: 'run-prompt', enabled: true, measured: 'M' }

/** An engine release's numbers (`2.1.307`, from a version or a base such as `2.1.307-dev`), or undefined. */
function release(engine: string): number[] | undefined {
  const m = /^(\d+)\.(\d+)\.(\d+)/.exec(engine)
  return m === null ? undefined : [Number(m[1]), Number(m[2]), Number(m[3])]
}

function atOrBelow(a: readonly number[], b: readonly number[]): boolean {
  for (let i = 0; i < 3; i++) {
    if (a[i]! !== b[i]!) {
      return a[i]! < b[i]!
    }
  }
  return true
}

/** The newest table measured at or below the engine, or undefined. */
export function tableFor(engine: string, tables: readonly RouteTable[] = ROUTE_TABLES): RouteTable | undefined {
  const at = release(engine)
  if (at === undefined) {
    return undefined
  }
  let best: RouteTable | undefined
  for (const t of tables) {
    const r = release(t.engine)
    if (r !== undefined && atOrBelow(r, at) && (best === undefined || atOrBelow(release(best.engine)!, r))) {
      best = t
    }
  }
  return best
}

/** Which table a session of this engine routes by, as the capability names it (`none` when no table applies). */
export function measuredFor(engine: string): string {
  return tableFor(engine)?.engine ?? 'none'
}

/** Whether the trimmed args fit the form: a reason when they do not, a pattern miss told apart. */
function formMiss(name: string, route: Route, args: string): { reason: string; isPatternMiss: boolean } | undefined {
  const forms = route.forms
  if (forms === undefined) {
    return undefined
  }
  if (forms.args === 'none' && args !== '') {
    return { reason: `/${name} takes no arguments`, isPatternMiss: false }
  }
  if (forms.args === 'required' && args === '') {
    return { reason: forms.hint ?? `/${name} needs arguments`, isPatternMiss: false }
  }
  if (forms.pattern !== undefined && args !== '' && !new RegExp(`^(?:${forms.pattern})$`).test(args)) {
    return { reason: `/${name} does not take these arguments: ${args}`, isPatternMiss: true }
  }
  return undefined
}

/**
 * A route's refusal, or undefined for one the bridge runs. The forms are
 * checked first, whatever the class: arguments a command does not take are
 * `bad-args` (a pattern's miss takes `otherwise` when the route has one),
 * and only a well-formed command is refused for its class.
 */
function refusalOf(name: string, route: Route, args: string): Refusal | undefined {
  const miss = formMiss(name, route, args)
  if (miss !== undefined) {
    if (miss.isPatternMiss && route.otherwise !== undefined) {
      return refusalOf(name, route.otherwise, args)
    }
    return { code: 'bad-args', reason: miss.reason }
  }
  switch (route.class) {
    case 'panel':
      return { code: 'panel', reason: PANEL_REASON }
    case 'routed':
      return { code: 'routed', reason: route.reason ?? `the desk does this with its own control (${route.to ?? 'its panel'}), not as a command` }
    case 'drop':
      return { code: 'drop', reason: `not from the desk: ${route.reason ?? 'the terminal does it'}` }
    case 'local':
      return { code: 'local', reason: LOCAL_REASON }
    case 'follow':
      return { code: 'follow', reason: FOLLOW_REASON }
  }
  return route.enabled ? undefined : { code: 'disabled', reason: route.reason ?? 'not offered from the desk yet' }
}

/** The route the args take, through `otherwise` on a pattern miss. */
function taken(name: string, route: Route, args: string): Route {
  const miss = formMiss(name, route, args)
  return miss?.isPatternMiss === true && route.otherwise !== undefined ? taken(name, route.otherwise, args) : route
}

/** Plugin-owned panels stay terminal-only even when this engine has no measured table. */
function pluginException(table: RouteTable | undefined, listed: Listed): RouteEntry | undefined {
  const matches = (entry: RouteEntry) => entry.name === listed.name && entry.plugin === listed.plugin
  if (table !== undefined) {
    return table.pluginExceptions.find(matches)
  }
  const knownPanel = ROUTE_TABLES.flatMap((t) => t.pluginExceptions).find((entry) => matches(entry) && entry.bare.class === 'panel')
  // With no engine table we offer no argument-specific escape from a known panel.
  return knownPanel === undefined ? undefined : { name: knownPanel.name, bare: knownPanel.bare }
}

/**
 * The route of `/name args` in a session of this engine, or its refusal.
 * `listed` is the session's own listing of the name (`$.command.list()`),
 * undefined when it lists none; `self` the bridge's plugin.
 */
export function routeOf(engine: string, listed: Listed | undefined, name: string, args: string, self: string): { route: Route } | { refusal: Refusal } {
  const trimmed = args.trim()
  if (listed !== undefined && listed.plugin === self) {
    return { refusal: { code: 'self', reason: SELF_REASON } }
  }
  const table = tableFor(engine)
  let entry: RouteEntry | undefined
  if (listed !== undefined && listed.source !== 'builtin') {
    entry = pluginException(table, listed) ?? { name, bare: RUN_PROMPT }
  } else {
    entry = table?.entries.find((e) => e.name === name)
    if (entry === undefined) {
      return { refusal: listed === undefined ? { code: 'unknown-builtin', reason: UNKNOWN_REASON } : { code: 'unknown-builtin', reason: UNMEASURED_REASON } }
    }
  }
  const route = trimmed !== '' && entry.withArgs !== undefined ? entry.withArgs : entry.bare
  const refusal = refusalOf(name, route, trimmed)
  return refusal === undefined ? { route: taken(name, route, trimmed) } : { refusal }
}

/** Both forms for the palette; the bridge still checks each op with routeOf. */
export function catalogRoutes(engine: string, listed: Listed, self: string): { route: Route; withArgs?: Route } {
  const drop = (reason: string): { route: Route } => ({ route: { class: 'drop', reason, enabled: true, measured: 'I' } })
  if (listed.plugin === self) {
    return drop(SELF_REASON)
  }
  const table = tableFor(engine)
  const entry = listed.source === 'builtin'
    ? table?.entries.find((e) => e.name === listed.name)
    : pluginException(table, listed)
  if (entry === undefined) {
    return listed.source === 'builtin' ? drop(UNMEASURED_REASON) : { route: RUN_PROMPT }
  }
  return { route: entry.bare, ...(entry.withArgs !== undefined && { withArgs: entry.withArgs }) }
}
