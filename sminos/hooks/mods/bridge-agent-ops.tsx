import type { EngineInterface } from 'claude-code'
import { message, state } from './bridge-state'
import type { Answer, ListedAgent } from './bridge-state'
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
 * A stop leaves the parent a note: the engine credits a stopped background
 * agent's end to Claude, and a stopped foreground agent reads to its parent
 * as an interrupted tool call, which the parent re-spawned at once (S2). The
 * note is appended before the answer, and an Agent call's result waits for
 * it (bridge.tsx's tool.call hook), so the parent's next request carries it.
 */

/** The longest agent id or name an op takes (DX6 `stop-agent`'s). */
export const AGENT_REF_MAX = 128
const CONTROL = /[\u0000-\u001f\u007f]/
/** The list's words for an agent whose loop is over (AgentStatus); every other is a loop alive. */
const ENDED = new Set(['completed', 'failed', 'killed'])

const isAgentRef = (ref: unknown): ref is string => typeof ref === 'string' && ref.trim() !== '' && ref.length <= AGENT_REF_MAX && !CONTROL.test(ref)

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
 * resolved, then the parent's note. The answer is the spelling asked, with
 * the id it resolved to when that was a name.
 */
export async function stopAgent($: EngineInterface, ref: unknown, from: unknown): Promise<Answer> {
  if (!isAgentRef(ref)) {
    return { ok: false, error: 'stop-agent needs an agent id or name' }
  }
  const found = resolveAgent(await $.agent.list(), ref)
  if ('refusal' in found) {
    return found.refusal
  }
  const id = found.agent.id
  // Held from before the stop: the Agent call it ends may return while TaskStop's answer is on its way.
  let noted: () => void = () => undefined
  const note = new Promise<void>((resolve) => (noted = resolve))
  state.agentStops.add(note)
  try {
    const r = await $.tool.call({ tool: 'TaskStop', task_id: id })
    if (r.isError === true) {
      return { ok: false, error: engineError(r.text) }
    }
    await recordAgentStop($, ref, from)
  } finally {
    state.agentStops.delete(note)
    noted()
  }
  return { ok: true, result: { agentId: ref, accepted: true, ...(id !== ref && { resolvedAgentId: id }) } }
}

/** The stop's note, kept as a job stop's is (isMeta, from the plugin) and named as the row it became. */
async function recordAgentStop($: EngineInterface, ref: string, from: unknown) {
  const text = agentStopNote(ref, from)
  try {
    const stored = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text }] } })
    if (stored.deny !== undefined) {
      $.ui.log(`bridge: the agent stop's note was refused: ${stored.deny}`, { to: 'debug' })
      return
    }
    noticeRow({ type: 'row-seen', uuid: stored.uuid, agentId: null, door: 'note' })
    $.ui.log(`stop-agent: ${text}`)
  } catch (error) {
    $.ui.log(`bridge: the agent stop's note was not appended: ${message(error)}`, { to: 'debug' })
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
 * resolved, under TELL_LINE; the agent reads it at its next step, inside the
 * engine's envelope. `sent` means the message is in its queue, not that it
 * was read.
 */
export async function tellAgent($: EngineInterface, ref: unknown, text: unknown): Promise<Answer> {
  if (!isAgentRef(ref) || typeof text !== 'string' || text.trim() === '') {
    return { ok: false, error: 'tell needs an agent id or name, and the text' }
  }
  const found = resolveAgent(await $.agent.list(), ref)
  if ('refusal' in found) {
    return found.refusal
  }
  const r = await $.session.send({ to: { agentId: found.agent.id }, text: `${TELL_LINE}\n${text}` })
  return r.isDelivered ? { ok: true, result: { sent: true } } : { ok: false, error: r.reason }
}
