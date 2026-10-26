import type { EngineInterface } from 'claude-code'
import { INTERRUPT_HOLD_MS, message, state } from './bridge-state'
import type { AgentStop, Answer, ListedAgent } from './bridge-state'
import { noticeRow } from './bridge-rows'

/**
 * One subagent stopped or told from the desk (DX5 `stop-agent` and `tell`,
 * the desk control surface spec's §9; MW4). Both name the agent as the
 * engine's own resolver does, by its id or by the Agent call's `name` (a
 * name may hold a space), never by its description, and check it against
 * the engine's list (`$.agent.list()`) first: an agent that is not running
 * is refused `unknown-agent`, since a stop would have nothing to stop and a
 * message would revive an agent that ended.
 *
 * Both answer once the engine has: TaskStop answers at once (spike 2: 8 to
 * 22 ms) and a send once the message is in the recipient's queue, so neither
 * has an outcome to follow on the stream, and a reload has none to lose. The
 * agent's end reaches the desk as every agent's does, in the subagent tree.
 *
 * A caller that resolved the agent itself (the daemon, against the tree it
 * is fed) passes the id it found as `resolvedAgentId`: that agent alone is
 * acted on, and refused once it no longer runs, so an agent that took its
 * name since is never stopped or told in its place.
 *
 * A stop leaves the agent's parent a note, in the parent's own loop (main,
 * or the subagent that spawned it): the engine credits a stopped background
 * agent's end to Claude, and a stopped foreground agent reads to its parent
 * as an interrupted tool call, which the parent re-spawned at once (S2). The
 * note is appended once TaskStop has stopped the agent, and what the stop
 * hands the parent waits for it, so its next request carries the note: a
 * foreground agent's Agent call result (bridge.tsx's tool.call hook) and a
 * background agent's task notification (its session.append hook), each at
 * most INTERRUPT_HOLD_MS. A note the session did not keep is in the answer
 * (`noteError`): the agent is stopped, its parent was not told.
 */

/** The longest agent id or name an op takes (DX6 `stop-agent`'s). */
export const AGENT_REF_MAX = 128
const CONTROL = /[\u0000-\u001f\u007f]/
/** The list's words for an agent whose loop is over (AgentStatus); every other is a loop alive. */
const ENDED = new Set(['completed', 'failed', 'killed'])

const isAgentRef = (ref: unknown): ref is string => typeof ref === 'string' && ref.trim() !== '' && ref.length <= AGENT_REF_MAX && !CONTROL.test(ref)
/**
 * A caller's resolved id: text as an agent ref is, then checked against the
 * list alone (resolvedAgent), never a shape of its own, since the engine's
 * ids are not one shape (a subagent's hex, a teammate's `<name>@<team>`).
 */
const isResolved = (id: unknown): id is string | undefined => id === undefined || isAgentRef(id)

/** A running agent the engine lists, by its id first, then by its name; else the refusal. */
export function resolveAgent(listed: readonly ListedAgent[], ref: string): { agent: ListedAgent } | { refusal: Answer } {
  const running = listed.filter((a) => !ENDED.has(a.status))
  const byId = listed.find((a) => a.id === ref)
  if (byId !== undefined) {
    return ENDED.has(byId.status) ? { refusal: notRunning(`agent ${ref} is not running (status: ${byId.status})`) } : { agent: byId }
  }
  const named = running.filter((a) => a.name === ref)
  if (named.length === 1) {
    return { agent: named[0]! }
  }
  if (named.length > 1) {
    return { refusal: { ok: false, error: `${named.length} running agents are named ${ref} (${named.map((a) => a.id).join(', ')}): name one by its id`, code: 'ambiguous-agent' } }
  }
  return { refusal: notRunning(`no running agent has the id or name ${ref}`) }
}

const notRunning = (error: string): Answer => ({ ok: false, error, code: 'unknown-agent' })

/** The agent a caller resolved, by that id alone, while it runs; or the refusal. */
function resolvedAgent(listed: readonly ListedAgent[], id: string, ref: string): { agent: ListedAgent } | { refusal: Answer } {
  const agent = listed.find((a) => a.id === id)
  if (agent === undefined || ENDED.has(agent.status)) {
    return { refusal: notRunning(`agent ${id}${id === ref ? '' : ` (asked as ${ref})`} is not running${agent === undefined ? '' : ` (status: ${agent.status})`}`) }
  }
  return { agent }
}

/** The agent an op names: the caller's resolved id when it gave one, else the spelling asked. */
async function opAgent($: EngineInterface, ref: string, resolvedId: string | undefined) {
  const listed = await $.agent.list()
  return resolvedId === undefined ? resolveAgent(listed, ref) : resolvedAgent(listed, resolvedId, ref)
}

/**
 * Waits for the notes of these stops, at most INTERRUPT_HOLD_MS (a note
 * whose append never answers).
 */
export async function forNotes($: EngineInterface, stops: readonly AgentStop[]): Promise<void> {
  if (stops.length === 0) {
    return
  }
  let held: { cancel: () => void } | undefined
  await Promise.race([Promise.all(stops.map((s) => s.noted)), new Promise<void>((resolve) => (held = $.clock.after(INTERRUPT_HOLD_MS, resolve)))])
  held?.cancel()
}

/** The stops whose agent a row is the task notification of (`<task-id>`), any door but the queue's record. */
export function notifiedStops(row: unknown): AgentStop[] {
  if (state.agentStops.size === 0) {
    return []
  }
  const text = JSON.stringify(row) ?? ''
  return text.includes('<task-notification>') ? [...state.agentStops].filter((s) => text.includes(`<task-id>${s.agentId}</task-id>`)) : []
}

/** A tool's error text without the engine's `<tool_use_error>` wrapping. */
export function engineError(text: string | undefined): string {
  const t = (text ?? '').replace(/^\s*<tool_use_error>([\s\S]*)<\/tool_use_error>\s*$/, '$1').trim()
  return t === '' ? 'TaskStop failed' : t
}

/** The note a stopped agent's parent reads (§9), naming the agent as the person did. */
export function agentStopNote(ref: string, from: unknown): string {
  return `Agent ${ref} was stopped by the person ${from === 'desk' ? 'from the desk' : 'from outside the terminal'}: it is not running. Do not start it again or redo its task unless the person asks.`
}

/**
 * DX5 `stop-agent`: the agent stopped with TaskStop by the id the list
 * resolved (or the caller did), then the parent's note. The answer is the
 * spelling asked, with the id it resolved to when that differs, and
 * `noteError` when the note was not kept.
 */
export async function stopAgent($: EngineInterface, ref: unknown, from: unknown, resolvedId?: unknown): Promise<Answer> {
  if (!isAgentRef(ref) || !isResolved(resolvedId)) {
    return { ok: false, error: 'stop-agent needs an agent id or name' }
  }
  const found = await opAgent($, ref, resolvedId)
  if ('refusal' in found) {
    return found.refusal
  }
  const id = found.agent.id
  // Held from before the stop: what it hands the parent may come while TaskStop's answer is on its way.
  let noted: () => void = () => undefined
  const stop: AgentStop = { agentId: id, noted: new Promise<void>((resolve) => (noted = resolve)) }
  state.agentStops.add(stop)
  let noteError: string | undefined
  try {
    const r = await $.tool.call({ tool: 'TaskStop', task_id: id })
    if (r.deny !== undefined) {
      return { ok: false, error: `TaskStop was refused: ${r.deny}` }
    }
    if (r.isError === true) {
      return { ok: false, error: engineError(r.text) }
    }
    noteError = await recordAgentStop($, ref, from, found.agent.parentId)
  } finally {
    state.agentStops.delete(stop)
    noted()
  }
  return { ok: true, result: { agentId: ref, accepted: true, ...(id !== ref && { resolvedAgentId: id }), ...(noteError !== undefined && { noteError }) } }
}

/**
 * The stop's note in the parent's loop (`parentId`, main when none), kept as
 * a job stop's is (isMeta, from the plugin) and named as the row it became;
 * why it was not kept, if it was not.
 */
async function recordAgentStop($: EngineInterface, ref: string, from: unknown, parentId: string | undefined): Promise<string | undefined> {
  const text = agentStopNote(ref, from)
  try {
    const stored = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text }] }, ...(parentId !== undefined && { agentId: parentId }) })
    if (stored.deny !== undefined) {
      $.ui.log(`bridge: the agent stop's note was refused: ${stored.deny}`, { to: 'debug' })
      return stored.deny
    }
    noticeRow({ type: 'row-seen', uuid: stored.uuid, agentId: parentId ?? null, door: 'note' })
    $.ui.log(`stop-agent: ${text}`)
    return undefined
  } catch (error) {
    $.ui.log(`bridge: the agent stop's note was not appended: ${message(error)}`, { to: 'debug' })
    return message(error)
  }
}

/**
 * The first line of a message the desk sends an agent. The engine's envelope
 * credits a plugin's send to the agent's coordinator ("The coordinator sent a
 * message while you were working", 2.1.310), so the message says who wrote it.
 */
export const TELL_LINE = 'From the person at the desk, not from your coordinator:'

/**
 * DX5 `tell`: the text to the running agent through the engine's own send
 * (`$.session.send`, SendMessage's delivery), addressed by the id the list
 * (or the caller) resolved, under TELL_LINE; the agent reads it at its next step, inside the
 * engine's envelope. `sent` means the message is in its queue, not that it
 * was read.
 */
export async function tellAgent($: EngineInterface, ref: unknown, text: unknown, resolvedId?: unknown): Promise<Answer> {
  if (!isAgentRef(ref) || !isResolved(resolvedId) || typeof text !== 'string' || text.trim() === '') {
    return { ok: false, error: 'tell needs an agent id or name, and the text' }
  }
  const found = await opAgent($, ref, resolvedId)
  if ('refusal' in found) {
    return found.refusal
  }
  const r = await $.session.send({ to: { agentId: found.agent.id }, text: `${TELL_LINE}\n${text}` })
  return r.isDelivered ? { ok: true, result: { sent: true } } : { ok: false, error: r.reason }
}
