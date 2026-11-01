import type { EngineInterface, SessionMessage, TurnCompleteInput } from 'claude-code'
import { NOTHING_TO_FORK, boundedText, usageOf } from './bridge-btw'
import { capped, message, state } from './bridge-state'
import type { Answer, OpenAsk, ResponseMark } from './bridge-state'
import { emit, emitOwed } from './bridge-stream'

/**
 * The owner's manager asking a session a question (`ask`, an extension of
 * DX5; design docs/doperpowers/specs/2026-10-31-session-manager-design.md,
 * §Queries): a fork agent spawned inside the session (`$.agent.spawn` with
 * `subagentType: 'fork'`), which inherits its conversation and model, so its
 * requests read the session's prompt cache; it may use read-only tools, runs
 * beside the session's turn, and its answer comes back here through its own
 * turn.complete, never into the session's conversation.
 *
 * Spawned from the command listener, outside every hook frame, the fork
 * bypasses every hook of this plugin: what holds it read-only is
 * doperpowers' fork guard (hooks/mods/fork-guard.tsx there), and the op is
 * refused `no-guard` unless that guard answers, now, the presence query
 * below. Its shape is the side question's (bridge-btw.tsx): answered at once,
 * `started`; its start and end follow on the stream after the answer; each
 * open one kept in `$.state` until the child took its end, so the module that
 * loads after a reload ends those it finds there, `aborted`; an end the child
 * has not taken goes again after the next resync. One at a time.
 */

/**
 * What the question is put under (copied verbatim as FORK_FRAME in
 * sminos_fork.py for the headless path): a fork carries the session's whole
 * task in its context and goes on with it when not told otherwise.
 */
export const ASK_FRAME =
  "You are a read-only fork of this session, started by the owner's manager session to answer one question. The session itself never sees this exchange, and nothing you do here reaches it. Do not continue the session's task. You may use read-only tools (reading and searching files, read-only shell commands such as git log, git status or gh pr view) to check facts; anything that would change a file or any state is refused. Answer the question directly, then stop."
/** What the fork is described as in the session's agent strip, `/tasks` and `$.agent.list()`. */
export const ASK_DESCRIPTION = 'manager query'
/** The tail a mid-turn fork is given at most, in UTF-8 bytes: the newest kept. */
export const TAIL_MAX = 32 * 1024
/** A tool call's input and a tool result in the tail, in characters at most. */
export const TAIL_RESULT_MAX = 2_000
/**
 * The guard's presence query (doperpowers' hooks/mods/fork-guard.tsx spells
 * both strings the same): a `$.tool.check` for a Read of this path, which no
 * file can have, runs nothing; the guard, loaded now, answers it `deny` with
 * FORK_GUARD_PRESENT, and without it core answers whatever it would.
 */
export const FORK_GUARD_PROBE = '/dev/null/sminos-fork-guard-probe'
export const FORK_GUARD_PRESENT = 'The read-only fork guard (doperpowers) is loaded.'
export const NO_GUARD = "no read-only guard is loaded in this session (doperpowers' fork guard): a fork agent would run with the session's own permissions"
export const ASK_BUSY = 'this session is already answering another manager query'
/**
 * The grace a fork whose end this module heard gets when the list still calls
 * it pending or running (the list lags a turn's end): read again every
 * ASK_GRACE_POLL_MS, ASK_GRACE_POLLS times (about 3 s), then busy.
 */
export const ASK_GRACE_POLL_MS = 250
export const ASK_GRACE_POLLS = 12

/** The session's open asks, by id with their fork's agent, as `$.state` keeps them for a module that loads after this one (types/sminos.d.ts). */
const OPEN = { plugin: 'sminos', key: 'bridgeAsk' } as const

/** The fork's prompt: the frame, what followed the request it continues from (mid-turn), then the question as asked. */
export function askPrompt(tail: string, question: string): string {
  const since = tail === '' ? '' : `\n\nSince the last request this fork continues from, the session's conversation went on as follows (oldest first):\n\n${tail}`
  return `${ASK_FRAME}${since}\n\nThe question:\n\n${question}`
}

/** A text held to TAIL_RESULT_MAX characters, saying how much was cut. */
function cut(text: string): string {
  const held = capped(text, TAIL_RESULT_MAX)
  return held.cut ? `${String(held.value)} [… ${text.length - String(held.value).length} more characters]` : text
}

const bytesOf = (cp: number) => (cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4)
const CUT_MARK = '[earlier messages cut]\n'

/** The newest TAIL_MAX UTF-8 bytes of a text, cut between code points, the cut said at the top. */
function newest(text: string): string {
  let bytes = 0
  for (const ch of text) {
    bytes += bytesOf(ch.codePointAt(0)!)
  }
  if (bytes <= TAIL_MAX) {
    return text
  }
  const budget = TAIL_MAX - CUT_MARK.length
  let kept = 0
  let at = text.length
  while (at > 0) {
    const low = text.charCodeAt(at - 1)
    const high = at >= 2 ? text.charCodeAt(at - 2) : 0
    const width = low >= 0xdc00 && low <= 0xdfff && high >= 0xd800 && high <= 0xdbff ? 2 : 1
    const size = bytesOf(text.codePointAt(at - width)!)
    if (kept + size > budget) {
      break
    }
    kept += size
    at -= width
  }
  return CUT_MARK + text.slice(at)
}

/**
 * Whether a row holds the response `mark` names: one of its tool calls, or
 * its text (a block, or the blocks joined, as a row holding several reads).
 * The rows carry no id of their own (`$.session.messages()`), so a response
 * with no tool call is found by its text; the search runs from the newest
 * row back, and only rows newer than the response could repeat it.
 */
function holds(row: SessionMessage, mark: ResponseMark): boolean {
  if (row.role !== 'assistant') {
    return false
  }
  if ((row.toolUses ?? []).some((use) => mark.toolUseIds.includes(use.tool_use_id))) {
    return true
  }
  const text = typeof row.text === 'string' ? row.text.trim() : ''
  if (text === '') {
    return false
  }
  return mark.texts.some((t) => t.trim() === text) || (mark.texts.length > 1 && [mark.texts.join('\n'), mark.texts.join('')].some((t) => t.trim() === text))
}

/**
 * What followed the main loop's last completed request, as text: from the
 * response that request got (the newest row holding it, with the assistant
 * rows of the same response before it) to now, each assistant text, each
 * tool call as `name(input)` with its result under it, input and result cut
 * to TAIL_RESULT_MAX; the user rows are left out, a result riding on its
 * call. The newest TAIL_MAX bytes are kept. Nothing when no row holds the
 * response (it said nothing visible, or the rows moved on).
 */
export function renderTail(rows: readonly SessionMessage[], mark: ResponseMark): string {
  let at = -1
  for (let i = rows.length - 1; i >= 0; i--) {
    if (holds(rows[i]!, mark)) {
      at = i
      break
    }
  }
  if (at === -1) {
    return ''
  }
  // A response the transcript keeps as several rows: the text before its calls is in the rows before.
  while (at > 0 && rows[at - 1]!.role === 'assistant') {
    at--
  }
  const lines: string[] = []
  for (const row of rows.slice(at)) {
    if (row.role !== 'assistant') {
      continue
    }
    if (typeof row.text === 'string' && row.text.trim() !== '') {
      lines.push(`assistant: ${row.text}`)
    }
    for (const use of row.toolUses ?? []) {
      lines.push(`tool call: ${use.tool}(${cut(JSON.stringify(use.input ?? {}))})`)
      lines.push(typeof use.text === 'string' ? `  ${use.isError === true ? 'error' : 'result'}: ${cut(use.text)}` : '  (no result yet)')
    }
  }
  return newest(lines.join('\n'))
}

/**
 * An end's fields from the fork's turn.complete: its answer (bounded as a
 * side question's, `truncated` when cut), or why there is none (`empty-reply`,
 * `aborted`, `failed` with the reason its turn ended), with the whole fork's
 * cost wherever the engine counted one.
 */
export function askEnd(e: TurnCompleteInput): Record<string, unknown> {
  const usage = e.usage === undefined ? {} : { usage: usageOf(e.usage) }
  if (e.reason === 'answer') {
    if (e.answer.trim() === '') {
      return { reason: 'empty-reply', ...usage }
    }
    const bounded = boundedText(e.answer)
    return { text: bounded.text, ...(bounded.truncated && { truncated: true }), ...usage }
  }
  if (e.reason === 'aborted') {
    return { reason: 'aborted', ...usage }
  }
  return { reason: 'failed', error: `the fork's turn ended: ${e.reason}`, ...usage }
}

/** Writes the open asks as they stand now, after any write before it. */
function keepOpen($: EngineInterface): Promise<void> {
  const open = [...state.askOpen].map(([id, a]) => ({ id, agentId: a.agentId }))
  state.askWrites = state.askWrites.then(
    () => $.state.set(OPEN, open).then(() => undefined),
    () => undefined,
  ).catch((error: unknown) => state.log?.(`bridge: the open manager queries are not kept for a reload: ${message(error)}`))
  return state.askWrites
}

/** An open ask, its end not come yet. */
function opened(agentId: string): OpenAsk {
  let resolve: (end: Record<string, unknown>) => void = () => undefined
  const ended = new Promise<Record<string, unknown>>((r) => (resolve = r))
  const open: OpenAsk = {
    agentId,
    ended,
    settle: (end) => {
      if (open.end === undefined) {
        open.end = end
        resolve(end)
      }
    },
  }
  return open
}

/** Its end posted and taken by the child: no module after this one ends it again. */
async function finished($: EngineInterface, id: string, open: OpenAsk) {
  const end = await open.ended
  await emitOwed({ type: 'ask', phase: 'end', id, agentId: open.agentId, ...end })
  state.askOpen.delete(id)
  await keepOpen($)
}

/** Whether doperpowers' fork guard is registered in this session now: its answer to the presence query. */
async function isGuardLoaded($: EngineInterface): Promise<boolean> {
  try {
    const verdict = await $.tool.check({ tool: 'Read', input: { file_path: FORK_GUARD_PROBE } })
    return verdict.decision === 'deny' && verdict.reason === FORK_GUARD_PRESENT
  } catch (error) {
    state.log?.(`bridge: the fork guard's presence was not read: ${message(error)}`)
    return false
  }
}

/**
 * At the module's session start: the asks a module before this one left open
 * end, `aborted`, each once under its own id and agent, and are let go once
 * the child took the end. Its own are never among them.
 */
export async function endOrphanedAsks($: EngineInterface) {
  let kept: unknown
  try {
    kept = (await $.state.get(OPEN)).value
  } catch (error) {
    state.log?.(`bridge: the open manager queries could not be read: ${message(error)}`)
    return
  }
  for (const entry of Array.isArray(kept) ? kept : []) {
    const { id, agentId } = (entry ?? {}) as { id?: unknown; agentId?: unknown }
    if (typeof id !== 'string' || typeof agentId !== 'string' || state.askOpen.has(id)) {
      continue
    }
    const open = opened(agentId)
    open.settle({ reason: 'aborted' })
    state.askOpen.set(id, open)
    void finished($, id, open)
  }
}

/** The fork's own turn.complete: its open ask's end. Any other loop's end is no ask's. */
export function askTurnEnded(e: TurnCompleteInput) {
  if (e.agentId === undefined) {
    return
  }
  for (const open of state.askOpen.values()) {
    if (open.agentId === e.agentId) {
      state.askEndedAgents.add(e.agentId)
      open.settle(askEnd(e))
    }
  }
}

/**
 * The main loop's response completed (a stop chunk carrying usage passed up
 * through the bridge's turn.step): a mid-turn fork's tail starts at it.
 */
export function noteMainResponse(mark: ResponseMark) {
  state.lastResponse = { toolUseIds: [...mark.toolUseIds], texts: [...mark.texts] }
}

/** An agent's status in `$.agent.list()` while its loop may still act. */
const LIVE_STATUSES = new Set(['pending', 'running', 'waiting'])

/**
 * The manager queries' forks the list calls live now (any `type: 'fork'`
 * agent `spawnedBy: 'sminos'`, pending, running or waiting), or undefined when
 * the list cannot be read.
 */
async function liveForks($: EngineInterface): Promise<{ id: string; status: string }[] | undefined> {
  let agents: unknown
  try {
    agents = await $.agent.list()
  } catch (error) {
    state.log?.(`bridge: the agent list was not read for a manager query: ${message(error)}`)
    return undefined
  }
  if (!Array.isArray(agents)) {
    return undefined
  }
  return agents
    .filter((a) => a?.type === 'fork' && a.spawnedBy === 'sminos' && LIVE_STATUSES.has(String(a.status)))
    .map((a) => ({ id: String(a.id), status: String(a.status) }))
}

/**
 * Whether a manager query's fork may still be running in this session: the
 * agent list is authoritative, read now, so one at a time holds across any
 * number of reloads (a fork may outlive the module that spawned it). A list
 * that cannot be read says nothing is known: busy. The one grace: when every
 * live fork is one whose turn.complete this module heard and the list still
 * calls it pending or running, the list is read again for about 3 s
 * (ASK_GRACE_POLLS), since it lags an end. `waiting` gets none: a fork with
 * background work of its own may resume its turn.
 */
async function isForkRunning($: EngineInterface): Promise<boolean> {
  for (let poll = 0; ; poll++) {
    const live = await liveForks($)
    if (live === undefined) {
      return true
    }
    if (live.length === 0) {
      return false
    }
    const isGraced = live.every((f) => state.askEndedAgents.has(f.id) && f.status !== 'waiting')
    if (!isGraced || poll >= ASK_GRACE_POLLS) {
      return true
    }
    await $.clock.sleep(ASK_GRACE_POLL_MS)
  }
}

/**
 * `ask {prompt}`: refused `bad-prompt` for no text, `busy` while another
 * ask's fork runs, `no-guard` unless the guard answers now, and
 * `nothing-to-fork` before the session's first message; otherwise the fork is
 * spawned under the frame, with the tail while the main turn runs, and the op
 * is answered `{started, id, agentId}`, the start and the end following on the
 * stream after the answer (`after`).
 */
export async function forkQuestion($: EngineInterface, id: string, prompt: unknown): Promise<Answer & { after?: () => void }> {
  if (typeof prompt !== 'string' || prompt.trim() === '') {
    return { ok: false, error: 'a manager query is its question', code: 'bad-prompt' }
  }
  if (state.isAskStarting || [...state.askOpen.values()].some((a) => a.end === undefined)) {
    return { ok: false, error: ASK_BUSY, code: 'busy' }
  }
  state.isAskStarting = true
  try {
    // A fork a reload left behind may still be running: the agent list, not this module's memory, says.
    if (await isForkRunning($)) {
      return { ok: false, error: ASK_BUSY, code: 'busy' }
    }
    if (!(await isGuardLoaded($))) {
      return { ok: false, error: NO_GUARD, code: 'no-guard' }
    }
    const rows = await $.session.messages()
    if (rows.length === 0) {
      return { ok: false, error: NOTHING_TO_FORK, code: 'nothing-to-fork' }
    }
    const tail = state.mainTurn !== undefined ? renderTail(rows, state.lastResponse) : ''
    const spawned = await $.agent.spawn({ subagentType: 'fork', description: ASK_DESCRIPTION, prompt: askPrompt(tail, prompt) })
    const agentId = 'agentId' in spawned ? spawned.agentId : undefined
    if (agentId === undefined) {
      return { ok: false, error: `the fork was not spawned: ${'deny' in spawned && typeof spawned.deny === 'string' ? spawned.deny : 'the engine started no agent'}` }
    }
    const open = opened(agentId)
    // Kept before it is answered started: a reload from here on finds it.
    state.askOpen.set(id, open)
    await keepOpen($)
    return {
      ok: true,
      result: { started: true, id, agentId },
      after: () => {
        emit({ type: 'ask', phase: 'start', id, agentId })
        void finished($, id, open)
      },
    }
  } finally {
    state.isAskStarting = false
  }
}
