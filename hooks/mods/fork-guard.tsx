import type { EngineInterface, On } from 'claude-code'

/**
 * The read-only guard over sminos's fork agents (the session manager's
 * `manager query`, design docs/doperpowers/specs/2026-10-31-session-manager-design.md):
 * the bridge spawns a fork of the session from its command listener, outside
 * every hook frame, so the fork's calls bypass all of sminos's own hooks; this
 * plugin's hooks see them, and here a managed fork is held to reading.
 *
 * A *managed fork* is an agent `$.agent.list()` lists as `type: 'fork'`,
 * `spawnedBy: 'sminos'`. Its calls are held two ways: at `tool.call`, to a
 * fixed surface (FORK_TOOLS), decided by name ahead of any user-tier plugin
 * that serves its tool inside its own `tool.call` hook and never reaches
 * `tool.check` (and ahead of `Agent`, which the engine marks read-only, so a
 * fork cannot delegate to an unguarded child); at `tool.check`, the read
 * tools allowed and Bash allowed only when the engine holds its input
 * read-only, so a fork never raises a permission prompt in the session and
 * never runs a write. Every other agent, and the main loop, is untouched.
 *
 * It fails closed: a registration whose hook throws or overruns is answered by
 * its `.catch`, which refuses a call not yet passed on, and a subagent's call
 * is refused while the agent list cannot be read.
 */

/** The tools a managed fork may call; any other is refused at `tool.call`. */
export const FORK_TOOLS: readonly string[] = ['Read', 'Grep', 'Glob', 'Bash']
/** What a managed fork reads when a call is refused. */
export const FORK_GUARD_REASON = 'This is a read-only fork (manager query): calls that change files or state are refused.'
/**
 * The guard's presence, as the sminos bridge asks for it before it spawns a
 * fork (sminos/hooks/mods/bridge-ask.tsx, which spells both strings the same):
 * a `$.tool.check` query from sminos for a Read of this path, which no file
 * can have, is answered `deny` with FORK_GUARD_PRESENT. Only a guard loaded
 * now answers it, so a reload that drops the guard turns the bridge's `ask`
 * into `no-guard`.
 */
export const FORK_GUARD_PROBE = '/dev/null/sminos-fork-guard-probe'
export const FORK_GUARD_PRESENT = 'The read-only fork guard (doperpowers) is loaded.'

/** The tools a managed fork's permission check allows outright: they only read. */
const READ_TOOLS = new Set(['Read', 'Grep', 'Glob'])

/**
 * Each agent's verdict once the list has named it: whether it is a managed
 * fork. An agent's type and spawner are fixed at its spawn and ids are not
 * reused, so a verdict never goes stale. An id the list does not name is not
 * remembered: it is looked for again at its next call.
 */
const verdicts = new Map<string, boolean>()

/** Forgets every verdict; for tests, which share this module. */
export function resetForkGuard() {
  verdicts.clear()
}

/** Thrown when the guard cannot tell whose a call is: the call is refused. */
class Unresolved extends Error {}

/**
 * Whether the agent is a managed fork. An id the list does not name (a
 * workflow's agent, the engine's own forks, which no list names) is not one:
 * a fork the bridge spawned is listed from its spawn on. Throws Unresolved
 * when the list cannot be read.
 */
async function isManagedFork($: EngineInterface, agentId: string): Promise<boolean> {
  const known = verdicts.get(agentId)
  if (known !== undefined) {
    return known
  }
  let agents: unknown
  try {
    agents = await $.agent.list()
  } catch (error) {
    throw new Unresolved(`the agent list could not be read: ${error instanceof Error ? error.message : String(error)}`)
  }
  if (!Array.isArray(agents)) {
    throw new Unresolved('the agent list is not a list')
  }
  const listed = agents.find((a) => a?.id === agentId)
  if (listed === undefined) {
    return false
  }
  const isManaged = listed.type === 'fork' && listed.spawnedBy === 'sminos'
  verdicts.set(agentId, isManaged)
  return isManaged
}

/** Whether a check is the bridge's presence query: sminos's own, for the probe path, deciding no call. */
function isPresenceProbe(e: { tool: string; input: unknown; tool_use_id?: string; agentId?: string }, origin: { plugin: string }): boolean {
  const input = e.input as { file_path?: unknown } | null
  return origin.plugin === 'sminos' && e.tool === 'Read' && e.tool_use_id === undefined && e.agentId === undefined && input?.file_path === FORK_GUARD_PROBE
}

/** A managed fork's check refused. */
const refusedCheck = () => ({ decision: 'deny', reason: FORK_GUARD_REASON }) as const

/**
 * Registered first in register.tsx, so its hooks are the plugin's outermost
 * (outer to the appeal's, whose pass can never apply to a fork's call), and
 * the plugin sits outside every user-tier plugin (the owner's
 * `prependPlugins`).
 */
export function registerForkGuard(on: On) {
  on('tool.call', { tool: /^/ }, async ($, e, next) => {
    if (e.agentId === undefined || !(await isManagedFork($, e.agentId)) || FORK_TOOLS.includes(e.tool)) {
      return next(e)
    }
    return { deny: FORK_GUARD_REASON }
  }).catch((_, e, next) => (next.called ? next(e) : { deny: FORK_GUARD_REASON }))

  on('tool.check', { tool: /^/ }, async ($, e, next) => {
    if (isPresenceProbe(e, next.origin)) {
      return { decision: 'deny', reason: FORK_GUARD_PRESENT }
    }
    if (e.agentId === undefined || !(await isManagedFork($, e.agentId))) {
      return next(e)
    }
    if (READ_TOOLS.has(e.tool) || (e.tool === 'Bash' && e.isReadOnly === true)) {
      return { decision: 'allow' }
    }
    return refusedCheck()
  }).catch((_, e, next) => (next.called ? next(e) : refusedCheck()))
}
