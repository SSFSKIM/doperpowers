import type { EngineInterface, HttpResponse, On, PermissionRequestDecision, SessionStartInput } from 'claude-code'

import { ASK_TOOL, PLUGIN, observeAsks } from './ask'
import { EFFORTS, RESPAWN_FIRST_MS, capped, isEffort, loopKey, message, parsed, state } from './bridge-state'
import type { Answer, Command, Decision, Override, Request, Steer, Stops } from './bridge-state'
import { adoptKept, adoptSeed, emit, endStep, forgetLive, poster, pump, releaseStepEnd, requeue, resyncEvent, stopChild } from './bridge-stream'
import {
  CHECKS_KEPT,
  askCallFor,
  answerFromOutside,
  claimCheck,
  decisionRecorded,
  engineDecision,
  firstQuestion,
  isBackground,
  onAskNote,
  raise,
  settle,
  withdrawAll,
} from './bridge-requests'
import { announceRow, compacted, enteredRow, exportRow, noticeRow, observeRow } from './bridge-rows'
import { refreshAgents, watchAgents } from './bridge-agents'

export { TEXT_CAP, capped, resetBridge } from './bridge-state'
export { STEP_END_WAIT_MS } from './bridge-stream'
export { RECORD_WAIT_MS, TRANSCRIPT_RETRY_MS, onAskNote } from './bridge-requests'
export { ROWS_POLLS, ROWS_POLL_MS, compacted } from './bridge-rows'
export { AGENTS_REFRESH_MS } from './bridge-agents'

/**
 * The bridge (DC2): this session's live events go out, and commands come in,
 * through the session's endpoint, which a child process serves for the
 * session's life (`sminos bridge --session <id>`,
 * skills/sminos/scripts/sminos_bridge.py; the protocol is DX5).
 *
 * The child's stdout is the command channel: its first line is `hello`, naming
 * the socket it serves, and each line after it is one command, which the mod
 * answers with a `result` event. Events go to the socket as `POST /events`,
 * one request in flight at a time, so they arrive in the order they happened
 * and batch themselves under load. A module reload kills the child and runs
 * `session.start` again, which spawns the next. Each post carries the nonce
 * its child's hello named, so the child turns away (409) what an older module
 * instance still has in flight after a reload, and a module whose post is
 * turned away stops for good.
 *
 * Control (DC2 M2): `steer` appends a user row the loop reads at its next
 * request; `interrupt` aborts the main turn and stops each Bash call the abort
 * moved to the background, and the turn's end appends a user row saying so;
 * `model` rewrites the main loop's requests;
 * `compact` runs between turns; `deliver` submits a log event as the human's
 * words, once per key. What must outlive a module reload (the model chosen,
 * the keys delivered) the child keeps on disk: its hello hands it back.
 *
 * Code that takes `$` stays in this file: the hooks, the session start, the
 * child and the session it serves, control, and the wait for a decision. The
 * modules beside it take none, and reach the engine only through the calls
 * the session start keeps in the state (`post`, `read`, `log`, `after`).
 * Each imports only those listed before it:
 * - bridge-state.tsx: the one state object, its types, and `resetBridge`;
 * - bridge-stream.tsx: the mod's copy of the session's live state, which
 *   every resync carries, and the poster;
 * - bridge-requests.tsx: requests from outside, and their settlement;
 * - bridge-rows.tsx: row order (each kept row's notice, a compaction's rows
 *   read from the transcript), the rows exported as messages to the host,
 *   and the row a delivered prompt became;
 * - bridge-agents.tsx: the agents the module did not see spawn, learned from
 *   the engine's list.
 */

export const HEARTBEAT_MS = 5_000
const RESPAWN_MAX_MS = 60_000
/** A child that lived this long ended for a reason of its own: start again quickly. */
const STABLE_MS = 30_000
/** After a /clear: how often, and how many times, the new session's id is looked for. */
export const CLEAR_POLL_MS = 100
const CLEAR_POLL_TRIES = 50
/** How many polls the old session's last events may take to reach its child before it is stopped. */
const DRAIN_TRIES = 10
/**
 * The prompt that wakes a session whose turn answered before any model request
 * read a steer: the steer's row is already in the conversation, so this names
 * it rather than repeating it.
 */
export const STEER_WAKE = 'I added a note to the conversation while you were finishing your answer. Read it and act on it.'
/** Deliveries whose prompt row is awaited, at most (the oldest is let go). */
const SUBMISSIONS_KEPT = 100
/** After an abort, how long the Bash calls it ended have to report where they went. */
export const INTERRUPT_WAIT_MS = 3_000
/** How long a Bash call of an interrupted turn waits for the interrupt's record, at most (a TaskStop that never answers). */
export const INTERRUPT_HOLD_MS = 10_000
/**
 * A family alias's model as the engine resolves it first, before its own
 * table: ANTHROPIC_DEFAULT_<FAMILY>_MODEL. Each name is spelled out, as the
 * module validator lists the variables a module reads. Undefined for a model
 * that is no family alias.
 */
function familyModel($: EngineInterface, family: string): Promise<string | undefined> | undefined {
  switch (family) {
    case 'haiku':
      return $.env.get('ANTHROPIC_DEFAULT_HAIKU_MODEL')
    case 'sonnet':
      return $.env.get('ANTHROPIC_DEFAULT_SONNET_MODEL')
    case 'opus':
      return $.env.get('ANTHROPIC_DEFAULT_OPUS_MODEL')
    case 'fable':
      return $.env.get('ANTHROPIC_DEFAULT_FABLE_MODEL')
    default:
      return undefined
  }
}
/** What an aborted Bash call's result says when the abort moved it to the background (DC1 item 4). */
const BACKGROUNDED = /running in background with ID: ([A-Za-z0-9_-]+)/
/**
 * A background subagent's prompt waits for the hooks before its dialog is
 * drawn (DC1 item 10): outside answers get this long, then it is the terminal's.
 */
export const BACKGROUND_WINDOW_MS = 3_000
/** The child holds a poll this long at most, under `$.http.fetch`'s 30-second bound. */
const POLL_HOLD_MS = 20_000
/** With no child answering (one restarting), the hook waits this long, so many times, out of its own budget. */
const POLL_RETRY_MS = 250
const POLL_RETRIES = 16

/** Cuts `pending + text` into whole lines, keeping the unfinished rest. */
export function splitLines(pending: string, text: string): { lines: string[]; rest: string } {
  const parts = (pending + text).split('\n')
  const rest = parts.pop() ?? ''
  return { lines: parts.filter((l) => l.trim() !== ''), rest }
}

/** Where the session stands, for a command's answer and the heartbeat. */
function turnState() {
  return {
    mainTurn: state.mainTurn ?? null,
    ...(state.isTurnUnknown && { isTurnUnknown: true }),
    isStreaming: state.steps > 0,
    tools: [...state.calls.values()].map((c) => c.tool),
  }
}

/**
 * A main turn this module saw no `turn.start` of (it was reloaded while the
 * turn ran), taken from the turn's next request: a main-loop `turn.step`
 * fires only inside a turn, under the id `turn.start`, `turn.complete` and
 * `$.turn.abort` use (2.1.300). From here interrupt, steer and compact act on
 * it as on a live turn, and the stream gets its start, marked `recovered`.
 */
function recoverMainTurn(turnId: string) {
  state.mainTurn = turnId
  state.isTurnUnknown = false
  state.loopTurns.set(loopKey(undefined), turnId)
  emit({ type: 'turn', phase: 'start', turnId, agentId: null, text: null, recovered: true })
}

/** Answers one command line with a `result` event. M3 adds its ops here. */
/** What a verb that needs the main turn's state says while it is unknown. */
export const TURN_UNKNOWN = 'turn state unknown since the bridge reloaded; retry after the next model request'
const TURN_OPS = new Set(['steer', 'interrupt', 'compact'])

/**
 * Whether the main turn's state is still unknown, the session's engine record
 * read first: a record of this session saying `idle` makes it known idle.
 */
async function isTurnStillUnknown(): Promise<boolean> {
  if (state.isTurnUnknown && state.record !== undefined && state.read !== undefined) {
    try {
      const record = JSON.parse(await state.read(state.record)) as { sessionId?: unknown; status?: unknown }
      if (state.isTurnUnknown && record.sessionId === state.session && record.status === 'idle' && state.mainTurn === undefined) {
        state.isTurnUnknown = false
      }
    } catch {
      // No record to read (yet): still unknown.
    }
  }
  return state.isTurnUnknown
}

async function runCommand($: EngineInterface, command: Command) {
  let answer: Answer
  try {
    // A false idle would be a lie: interrupt saying there is nothing to stop,
    // a compaction run at once, while a turn the module did not see runs.
    answer = TURN_OPS.has(command.op) && (await isTurnStillUnknown()) ? { ok: false, error: TURN_UNKNOWN } : await commandAnswer($, command)
  } catch (error) {
    answer = { ok: false, error: message(error) }
  }
  emit({ type: 'result', id: command.id, op: command.op, ...answer })
}

function commandAnswer($: EngineInterface, command: Command): Answer | Promise<Answer> {
  switch (command.op) {
    case 'ping':
      return { ok: true, result: { pong: true, state: turnState() } }
    case 'steer':
      return steer($, command.text)
    case 'interrupt':
      return interrupt($, command.from)
    case 'model':
      return chooseModel($, command.model, command.effort)
    case 'compact':
      return compact($, command)
    case 'deliver':
      return deliver($, command.key, command.text)
    case 'answer':
      return answerFromOutside(command)
    default:
      return { ok: false, error: `unknown op: ${command.op}` }
  }
}

/**
 * A user row in the running turn, read at the loop's next model request; the
 * running tool goes on. The terminal does not draw an appended row, so a
 * transcript line mirrors it. Idle, there is no next request to read it: a
 * send is how an idle session is reached.
 */
async function steer($: EngineInterface, text: unknown): Promise<Answer> {
  if (typeof text !== 'string' || text.trim() === '') {
    return { ok: false, error: 'steer needs text' }
  }
  if (state.mainTurn === undefined) {
    return { ok: false, error: 'no turn is running to steer: send it instead' }
  }
  // Bound to its turn before the append: the turn may end while it is pending.
  const pending: Steer = { turnId: state.mainTurn, isAppended: false, isRead: false }
  state.steers.push(pending)
  let stored: Awaited<ReturnType<EngineInterface['session']['append']>>
  try {
    stored = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text }] } })
  } catch (error) {
    state.steers = state.steers.filter((s) => s !== pending)
    settleSteers($, pending.turnId)
    throw error
  }
  if (stored.deny !== undefined) {
    state.steers = state.steers.filter((s) => s !== pending)
    settleSteers($, pending.turnId)
    return { ok: false, error: `the row was refused: ${stored.deny}` }
  }
  pending.isAppended = true
  // The hook does not see the plugin's own append: named once it is in.
  noticeRow({ type: 'row-seen', uuid: stored.uuid, agentId: null, door: 'note' })
  $.ui.log(`steer: ${text}`)
  settleSteers($, pending.turnId)
  return { ok: true, result: { row: stored.uuid } }
}

/**
 * The one wake a turn owes for its steers: once the turn has ended and every
 * append given in it has settled (in, refused, or failed), its steers are let
 * go, and if it answered while a row of them was in and unread, the session
 * is woken once. Called at the turn's end and as each pending append settles.
 */
function settleSteers($: EngineInterface, turnId: string) {
  const mine = state.steers.filter((s) => s.turnId === turnId)
  const ended = mine[0]?.ended
  if (ended === undefined || mine.some((s) => !s.isAppended)) {
    return
  }
  state.steers = state.steers.filter((s) => s.turnId !== turnId)
  if (ended === 'answer' && mine.some((s) => !s.isRead)) {
    wakeForSteer($)
  }
}

/**
 * Wakes the session for a steer its turn answered before reading: the row is
 * already in the conversation, so the prompt points to it rather than
 * repeating it, and the next request reads both.
 */
function wakeForSteer($: EngineInterface) {
  void $.prompt
    .submit({ text: STEER_WAKE, asUser: true })
    .catch((error: unknown) => $.ui.log(`bridge: the wake for an unread steer was not submitted: ${message(error)}`, { to: 'debug' }))
}

/**
 * Esc's effect: the main turn aborted, then each Bash call it moved to the
 * background (the abort backgrounds a running Bash rather than killing it)
 * stopped with TaskStop. Only that turn's calls count: the main loop's, and
 * those of a foreground subagent spawned in it, which the abort ends with it;
 * a background subagent's calls are its own. Each says where it went in its
 * result. A task TaskStop could not stop is named in `running`.
 *
 * Then the model is told (recordInterrupt) before the turn can end: the
 * turn's Bash calls, whose results the engine waits for after an abort, are
 * held in their hook until the record is in, since the next turn takes its
 * messages before it waits for any hook. `from` says where the interrupt came
 * from (`desk`: the desk's RPC). A second interrupt of the same turn leaves
 * the first's in place; the engine refuses its abort.
 */
async function interrupt($: EngineInterface, from: unknown): Promise<Answer> {
  const turnId = state.mainTurn
  if (turnId === undefined) {
    return { ok: true, result: { turnId: null, stopped: [], running: [] } }
  }
  const ours = [...state.calls.values()].filter((c) => c.tool === 'Bash' && c.owner === turnId)
  // A dialog the abort closes was answered by nobody: its request is withdrawn.
  for (const r of state.requests.values()) {
    if (!r.isAsync && (r.agentId === null ? r.turnId === turnId : state.foreground.get(r.agentId) === turnId)) {
      r.isAborted = true
    }
  }
  // Kept before the abort: the calls it ends return as it resolves.
  let recorded: () => void = () => undefined
  const pending = { recorded: new Promise<void>((resolve) => (recorded = resolve)) }
  if (!state.interrupts.has(turnId)) {
    state.interrupts.set(turnId, pending)
  }
  try {
    try {
      await $.turn.abort({ turnId })
    } catch (error) {
      if (state.interrupts.get(turnId) === pending) {
        state.interrupts.delete(turnId)
      }
      throw error
    }
    const stops: Stops = { stopped: [], running: [] }
    const bound = new Promise<undefined>((resolve) => void $.clock.after(INTERRUPT_WAIT_MS, () => resolve(undefined)))
    const texts = await Promise.all(ours.map((c) => Promise.race([c.done, bound])))
    for (const text of texts) {
      const task = BACKGROUNDED.exec(text ?? '')?.[1]
      if (task === undefined) {
        continue
      }
      let failure: string | undefined
      try {
        const r = await $.tool.call({ tool: 'TaskStop', task_id: task })
        failure = r.isError === true ? (r.text ?? 'TaskStop failed') : undefined
      } catch (error) {
        failure = message(error)
      }
      if (failure === undefined) {
        stops.stopped.push(task)
      } else {
        $.ui.log(`bridge: TaskStop ${task} failed: ${failure}`, { to: 'debug' })
        stops.running.push(task)
      }
    }
    await recordInterrupt($, from, stops)
    return { ok: true, result: { turnId, ...stops } }
  } finally {
    recorded()
  }
}

/**
 * What an interrupt tells the model: the engine's own marker for Esc, with
 * where it came from, and each Bash call it moved to the background, whose
 * result says the command runs on there.
 */
function interruptText(from: unknown, stops: Stops): string {
  return [
    `[Request interrupted by user from ${from === 'desk' ? 'the desk' : 'outside the terminal'}]`,
    ...stops.stopped.map((task) => `Task ${task}, the Bash command the interrupt moved to the background, was then stopped: it is not running, and no notification will come for it.`),
    ...stops.running.map((task) => `Task ${task}, the Bash command the interrupt moved to the background, could not be stopped: it may still be running.`),
  ].join('\n')
}

/**
 * The interrupt's record: Esc leaves the model `[Request interrupted by
 * user]`, a plugin's abort no marker at all, so a user row says it, read at
 * the next request. The terminal does not draw an appended row, so a
 * transcript line mirrors it.
 */
async function recordInterrupt($: EngineInterface, from: unknown, stops: Stops) {
  const text = interruptText(from, stops)
  try {
    const stored = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text }] } })
    if (stored.deny !== undefined) {
      $.ui.log(`bridge: the interrupt's record was refused: ${stored.deny}`, { to: 'debug' })
      return
    }
    // The hook does not see the plugin's own append: named once it is in.
    noticeRow({ type: 'row-seen', uuid: stored.uuid, agentId: null, door: 'note' })
    // One line: the transcript line draws a newline as U+FFFD (live, 2.1.302).
    $.ui.log(`interrupt: ${text.replaceAll('\n', ' ')}`)
  } catch (error) {
    $.ui.log(`bridge: the interrupt's record was not appended: ${message(error)}`, { to: 'debug' })
  }
}

/**
 * The model and effort of the main loop's requests from now on, this session
 * only: rewritten in turn.step. `$.config.set` is not used: it also saves the
 * model as the user's default. A model of null (or `default`) keeps the
 * session's own; so does an effort of null.
 *
 * A rewrite names the model sent on the wire, so an alias is resolved here:
 * a family alias as the engine resolves it first, through the session's
 * ANTHROPIC_DEFAULT_<FAMILY>_MODEL. The engine's own alias table is not open
 * to a plugin, so an alias with no such variable is refused, asking for the id.
 */
async function chooseModel($: EngineInterface, model: unknown, effort: unknown): Promise<Answer> {
  const asked = model === undefined || model === null || model === 'default' ? null : model
  if (asked !== null && (typeof asked !== 'string' || asked.trim() === '')) {
    return { ok: false, error: 'a model is a name (an alias such as sonnet, or a full id)' }
  }
  let chosenModel = asked as string | null
  const chosenEffort = effort === undefined || effort === null ? null : effort
  if (chosenEffort !== null && !isEffort(chosenEffort)) {
    return { ok: false, error: `an effort is one of ${EFFORTS.join(', ')}` }
  }
  const family = chosenModel === null ? undefined : familyModel($, chosenModel.toLowerCase())
  if (chosenModel !== null && family !== undefined) {
    const mapped = await family
    if (mapped === undefined || mapped.trim() === '') {
      const variable = `ANTHROPIC_DEFAULT_${chosenModel.toUpperCase()}_MODEL`
      return { ok: false, error: `${chosenModel} is an alias this session's ${variable} does not map: name the model by its id (as claude-${chosenModel.toLowerCase()}-…)` }
    }
    chosenModel = mapped.trim()
  }
  const next: Override = { model: chosenModel, effort: chosenEffort }
  state.override = next.model === null && next.effort === null ? undefined : next
  emit({ type: 'model', ...next })
  return { ok: true, result: next }
}

/** The engine compacts between turns only: asked during the main turn, it is held for its end. */
function compact($: EngineInterface, command: Command): Answer {
  const instructions = typeof command.instructions === 'string' && command.instructions !== '' ? command.instructions : undefined
  const request = { id: command.id, ...(instructions !== undefined && { instructions }) }
  if (state.mainTurn !== undefined) {
    state.compact ??= request
    return { ok: true, result: { queued: true, turnId: state.mainTurn } }
  }
  void runCompaction($, request)
  return { ok: true, result: { started: true } }
}

/** One compaction, said on the stream as it starts and as it ends: its counts, its skip, or its error. */
async function runCompaction($: EngineInterface, request: { id: string; instructions?: string }) {
  emit({ type: 'compact', phase: 'start', id: request.id })
  try {
    const outcome = await $.session.compact(request.instructions === undefined ? {} : { instructions: request.instructions })
    // Its rows pass no hook: named from the transcript, before its end.
    if (outcome.skip === undefined) {
      compacted(null, outcome.messages)
    }
    emit({
      type: 'compact',
      phase: 'end',
      id: request.id,
      ...(outcome.skip !== undefined ? { skip: outcome.skip } : { tokensBefore: outcome.tokensBefore ?? null, tokensAfter: outcome.tokensAfter ?? null }),
    })
  } catch (error) {
    emit({ type: 'compact', phase: 'end', id: request.id, error: message(error) })
  }
}

/**
 * A log event for this session, submitted as the human's words: queued until
 * the session is idle. Delivery is at least once and goes in seq order per
 * writer, so a key at or below the writer's last submitted is a repeat, and
 * dropped.
 */
function deliver($: EngineInterface, key: unknown, text: unknown): Answer {
  const { writer, seq } = (typeof key === 'object' && key !== null ? key : {}) as { writer?: unknown; seq?: unknown }
  if (typeof writer !== 'string' || writer === '' || !Number.isInteger(seq) || typeof text !== 'string') {
    return { ok: false, error: 'deliver needs key {writer, seq} and text' }
  }
  const delivery = { writer, seq: seq as number }
  if (delivery.seq <= (state.delivered.get(writer) ?? 0)) {
    emit({ type: 'delivered', key: delivery, outcome: 'duplicate' })
    return { ok: true, result: { duplicate: true } }
  }
  state.delivered.set(writer, delivery.seq)
  emit({ type: 'delivered', key: delivery, outcome: 'submitted' })
  // Its row, once kept, is named `entered` (bridge-rows.tsx, enteredRow).
  const submission = { key: delivery, text }
  state.submissions.push(submission)
  if (state.submissions.length > SUBMISSIONS_KEPT) {
    state.submissions.shift()
  }
  const refused = (reason: string) => {
    state.submissions = state.submissions.filter((s) => s !== submission)
    $.ui.log(`bridge: the delivery ${writer}:${delivery.seq} did not enter: ${reason}`, { to: 'debug' })
    emit({ type: 'delivered', key: delivery, outcome: 'refused', reason })
  }
  // Not awaited: it resolves when the prompt's turn starts, after any running turn.
  void $.prompt.submit({ text, asUser: true }).then(
    (entered) => {
      if (entered.drop !== undefined) {
        refused(entered.drop)
      }
    },
    (error: unknown) => refused(message(error)),
  )
  return { ok: true, result: { submitted: true } }
}

/**
 * Polls the child for a decision while the dialog is up, in holds under the
 * fetch bound, until one is handed out, the terminal answered, the request
 * settled, or a background window's deadline passed. Past the deadline (or
 * with no child answering) the dialog is the terminal's; the engine's record
 * of what it decided settles the request.
 */
async function awaitDecision($: EngineInterface, r: Request, signal: AbortSignal): Promise<PermissionRequestDecision | undefined> {
  let retries = 0
  while (state.requests.get(r.id) === r && !signal.aborted) {
    const hold = r.deadline === undefined ? POLL_HOLD_MS : Math.min(POLL_HOLD_MS, r.deadline - (await $.clock.now()))
    if (hold <= 0) {
      return undefined
    }
    const socketPath = state.socket
    let res: HttpResponse | undefined
    if (socketPath !== undefined) {
      res = await $.http.fetch(`http://bridge/requests/${encodeURIComponent(r.id)}/wait?ms=${hold}`, { socketPath }).catch(() => undefined)
    }
    if (res === undefined) {
      if (++retries > POLL_RETRIES) {
        return undefined
      }
      await $.clock.sleep(POLL_RETRY_MS)
      continue
    }
    if (res.status === 200) {
      const handed = parsed(res.text)
      const decision = handed?.decision as Decision | undefined
      if (decision !== undefined && (decision.behavior === 'allow' || decision.behavior === 'deny') && typeof handed?.by === 'string') {
        r.decided = { decision, by: handed.by }
        return engineDecision(r, decision)
      }
    } else if (res.status === 410) {
      // The terminal answered it, or it settled: nothing to answer.
      return undefined
    }
  }
  return undefined
}

/**
 * The end of the main turn: a compaction held for it, then the turn's steers
 * settled (settleSteers): when it answered before any request read one, one
 * wake (the row is in the conversation already), as a prompt typed mid-turn
 * would start the next turn — at once, or once the last of its pending
 * appends settles. An interrupted or failed turn wakes nothing.
 */
async function mainTurnEnded($: EngineInterface, turnId: string, reason: string) {
  state.interrupts.delete(turnId)
  for (const s of state.steers) {
    if (s.turnId === turnId) {
      s.ended = reason
    }
  }
  const request = state.compact
  state.compact = undefined
  if (request !== undefined) {
    await runCompaction($, request)
  }
  settleSteers($, turnId)
}

function onLine($: EngineInterface, generation: number, line: string) {
  let parsed: unknown
  try {
    parsed = JSON.parse(line)
  } catch {
    $.ui.log(`bridge: a line from the child that is not JSON: ${line.slice(0, 200)}`, { to: 'debug' })
    return
  }
  if (generation !== state.generation || typeof parsed !== 'object' || parsed === null) {
    return
  }
  const msg = parsed as Record<string, unknown>
  if (msg.op === 'hello' && typeof msg.socket === 'string') {
    state.socket = msg.socket
    state.nonce = typeof msg.nonce === 'string' ? msg.nonce : undefined
    if (typeof msg.presence === 'string') {
      state.record = msg.presence
    }
    // What the child kept on disk is this module's only after a reload; a
    // module that holds its own hands it to the child in the resync. So is
    // the seed: a later child's tail may hold rows whose notices are still
    // to come, beside blocks this module streams.
    if (!state.isSeeded) {
      adoptKept(msg.kept)
      adoptSeed(msg.seed)
      state.isSeeded = true
    }
    // A new child knows nothing of the session: what it started as, then
    // where it stands. What was queued for no child is in that state.
    requeue([{ type: 'session', phase: 'start', session: state.session, ...state.info, t: Date.now() }, resyncEvent()])
    pump()
    return
  }
  if (typeof msg.id === 'string' && typeof msg.op === 'string') {
    void runCommand($, msg as Command)
  }
}

/**
 * Starts the session's child and reads its lines until it ends; one that
 * ended on its own is started again, after a second, doubling while it keeps
 * ending at once, up to a minute.
 */
function startChild($: EngineInterface, session: string) {
  const generation = ++state.generation
  state.session = session
  state.socket = undefined
  state.nonce = undefined
  const startedAt = Date.now()
  void (async () => {
    let pending = ''
    try {
      const child = $.process.spawn({ argv: [`${$.plugin.root}/skills/sminos/scripts/sminos`, 'bridge', '--session', session] })
      state.child = child
      for await (const piece of child) {
        if (piece.stream === 'stderr') {
          $.ui.log(`bridge: ${piece.text.trimEnd()}`, { to: 'debug' })
          continue
        }
        const { lines, rest } = splitLines(pending, piece.text)
        pending = rest
        for (const line of lines) {
          onLine($, generation, line)
        }
      }
      const ended = await child.result
      $.ui.log(`bridge: the child ended (${ended.signal ?? ended.code})`, { to: 'debug' })
    } catch (error) {
      $.ui.log(`bridge: the child failed: ${message(error)}`, { to: 'debug' })
    }
    if (generation !== state.generation) {
      return
    }
    state.socket = undefined
    state.nonce = undefined
    state.child = undefined
    if (Date.now() - startedAt >= STABLE_MS) {
      state.respawnMs = RESPAWN_FIRST_MS
    }
    const delay = state.respawnMs
    state.respawnMs = Math.min(delay * 2, RESPAWN_MAX_MS)
    $.clock.after(delay, () => {
      if (generation === state.generation) {
        startChild($, session)
      }
    })
  })()
}

/**
 * Moves the bridge to the session that took this one's place: once the old
 * child has its last events (or after DRAIN_TRIES polls), it is stopped and a
 * child for the new session started, whose hello resyncs what happened since.
 */
function switchSession(session: string, tries = 0) {
  if ((state.queue.length > 0 || state.isPosting) && tries < DRAIN_TRIES && state.after !== undefined) {
    state.after(CLEAR_POLL_MS, () => switchSession(session, tries + 1))
    return
  }
  if (session === state.session) {
    return
  }
  if (!state.isEnding) {
    // Found by the heartbeat, with no session.end before it.
    forgetLive()
  }
  state.isEnding = false
  state.queue = []
  state.restart?.(session)
}

/**
 * After a /clear's session.end: the new session's id, looked for every
 * CLEAR_POLL_MS (the heartbeat is the fallback). If the id never changes, this
 * session goes on, resynced.
 */
function awaitNextSession(tries = 0) {
  if (!state.isEnding || state.readId === undefined) {
    return
  }
  const old = state.session
  void state.readId().then(
    (session) => {
      if (!state.isEnding) {
        return
      }
      if (session !== old) {
        switchSession(session)
      } else if (tries < CLEAR_POLL_TRIES) {
        state.after?.(CLEAR_POLL_MS, () => awaitNextSession(tries + 1))
      } else {
        state.isEnding = false
        state.queue.push(resyncEvent())
        pump()
      }
    },
    (error: unknown) => state.log?.(`bridge: the session id could not be read: ${message(error)}`),
  )
}

/** The heartbeat; and the session's id read again, the fallback for a change of session missed. */
async function beat($: EngineInterface) {
  try {
    const session = await $.session.id()
    if (session !== state.session) {
      switchSession(session)
    }
  } catch (error) {
    $.ui.log(`bridge: the session id could not be read: ${message(error)}`, { to: 'debug' })
  }
  await isTurnStillUnknown()
  emit({ type: 'heartbeat', state: turnState() })
  await refreshAgents()
}

export async function bridgeStart($: EngineInterface, e: SessionStartInput) {
  // derive's headless fork of a session is never a member, and needs no bridge.
  if ((await $.env.get('SMNS_INTERNAL')) !== undefined) {
    return
  }
  state.post = (socketPath, nonce, body) =>
    $.http.fetch('http://bridge/events', {
      method: 'POST',
      socketPath,
      headers: { 'content-type': 'application/json', ...(nonce !== undefined && { 'x-bridge-nonce': nonce }) },
      body,
    })
  state.read = (path) => $.fs.read(path)
  state.rowsAfter = async (loop, after) => {
    const socketPath = state.socket
    if (socketPath === undefined) {
      return undefined
    }
    const res = await $.http.fetch(`http://bridge/rows?loop=${encodeURIComponent(loop)}&after=${encodeURIComponent(after)}`, { socketPath })
    const rows = res.status === 200 ? parsed(res.text)?.rows : undefined
    return Array.isArray(rows) ? rows.filter((u): u is string => typeof u === 'string') : undefined
  }
  state.log = (text) => $.ui.log(text, { to: 'debug' })
  state.after = (ms, fn) => void $.clock.after(ms, fn)
  state.readId = () => $.session.id()
  state.restart = (session) => {
    stopChild()
    startChild($, session)
  }
  state.listAgents = () => $.agent.list()
  // A session with no message yet when the module loads (a start, not a
  // reload or a resume): its main loop is seen from its first row.
  if (!state.isSeeded && (await $.session.messages().then((m) => Array.isArray(m) && m.length === 0, () => false))) {
    state.freshLoops.add('main')
  }
  // Loaded into a session with its conversation (a reload, a resume), the
  // module cannot know whether a main turn is running until it sees one.
  if (!state.isSeeded) {
    state.isTurnUnknown = !state.freshLoops.has('main')
  }
  state.info = {
    cwd: e.cwd,
    surface: e.surface,
    isInteractive: e.isInteractive,
    model: await $.session.model(),
    version: (await $.session.version()).version,
  }
  // The agents running already, or over, learned before the first hello: its resync carries them.
  await refreshAgents()
  stopChild()
  startChild($, await $.session.id())
  if (!state.isPosterRunning) {
    state.isPosterRunning = true
    void poster()
  }
  state.heartbeat?.cancel()
  state.heartbeat = $.clock.every(HEARTBEAT_MS, () => void beat($))
}

const RESERVED = new Set(['tool', 'tool_use_id', 'consent', 'agentId', 'requestMeta'])

/** A tool call's own arguments, every string in them held to TEXT_CAP. */
function toolInput(e: Record<string, unknown>): { value: unknown; cut: boolean } {
  return capped(Object.fromEntries(Object.entries(e).filter(([k]) => !RESERVED.has(k))))
}

/**
 * Registered first in register.tsx, so its hooks are the outermost of the
 * plugin's: what they report is what the session showed and recorded. Each
 * event is taken with a matcher that matches every input, since the other
 * mods hold the unmatched registrations and the engine admits one per event
 * per module.
 */
export function registerBridge(on: On) {
  observeAsks(onAskNote)

  on('session.start', { cwd: /^/ }, async ($, e, next) => {
    const started = await next(e)
    try {
      await bridgeStart($, e)
    } catch (error) {
      $.ui.log(`bridge: not started: ${message(error)}`, { to: 'debug' })
    }
    return started
  })

  // A /clear ends the conversation and goes on under a new id with no
  // session.start: the old child gets this end and nothing after it.
  on('session.end', async (_, e, next) => {
    withdrawAll()
    emit({ type: 'session', phase: 'end', reason: e.reason })
    if (e.reason === 'clear' && state.post !== undefined) {
      state.isEnding = true
      forgetLive()
      awaitNextSession()
    }
    return next(e)
  })

  on('turn.start', { turnId: /^/ }, (_, e, next) => {
    if (e.agentId === undefined) {
      state.mainTurn = e.turnId
      state.isTurnUnknown = false
    }
    state.loopTurns.set(loopKey(e.agentId), e.turnId)
    // A loop whose spawn the bridge did not see (a forked skill): the list names it.
    if (e.agentId !== undefined && !state.agents.has(e.agentId)) {
      void refreshAgents()
    }
    const text = capped(e.text)
    emit({ type: 'turn', phase: 'start', turnId: e.turnId, agentId: e.agentId ?? null, text: text.value, ...(text.cut && { truncated: true }) })
    return next(e)
  })

  on('turn.complete', { turnId: /^/ }, async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined && state.mainTurn === e.turnId) {
      state.mainTurn = undefined
    }
    if (e.agentId === undefined && state.mainTurn === undefined) {
      state.isTurnUnknown = false
    }
    if (state.loopTurns.get(loopKey(e.agentId)) === e.turnId) {
      state.loopTurns.delete(loopKey(e.agentId))
    }
    // A dialog its turn ended with was answered by nobody.
    for (const r of [...state.requests.values()]) {
      if (!r.isAsync && r.turnId === e.turnId) {
        settle(r, 'withdrawn', 'bridge')
      }
    }
    releaseStepEnd(loopKey(e.agentId))
    emit({ type: 'turn', phase: 'complete', turnId: e.turnId, agentId: e.agentId ?? null, reason: e.reason, usage: e.usage ?? null })
    if (e.agentId === undefined) {
      try {
        const usage = await $.session.usage()
        emit({ type: 'usage', context: usage.context, cost: usage.cost ?? null })
      } catch (error) {
        $.ui.log(`bridge: usage not read: ${message(error)}`, { to: 'debug' })
      }
      await mainTurnEnded($, e.turnId, e.reason)
    }
    return result
  })

  // Every model request of the main loop and of every subagent: each chunk
  // as the engine streamed it, tagged with its message (turn, agent, step) and
  // its index there; the engine's own opaque items are left out.
  on('turn.step', { turnId: /^/ }, async function* (_, e, next) {
    const tag = { turnId: e.turnId, agentId: e.agentId ?? null, step: e.index }
    // A request of a loop older than the module, begun before the seed, may
    // have rows at or before it: it streams to nobody, and its rows reach a
    // reader through the transcript.
    const isShown = state.isSeeded || state.freshLoops.has(e.agentId ?? 'main')
    const isMain = e.agentId === undefined
    if (isMain && state.mainTurn === undefined) {
      recoverMainTurn(e.turnId)
    }
    releaseStepEnd(loopKey(e.agentId))
    // The model chosen through the bridge is the main loop's: a subagent runs
    // on what its definition or its caller chose.
    const o = isMain ? state.override : undefined
    const input = o === undefined ? e : { ...e, ...(o.model !== null && { model: o.model }), ...(o.effort !== null && { effort: o.effort }) }
    if (isShown) {
      emit({ type: 'step', phase: 'start', ...tag, model: input.model, effort: input.effort ?? null, messageCount: e.messageCount })
    }
    if (isMain) {
      state.steps++
      // This request carries every row of its turn appended before it.
      for (const s of state.steers) {
        if (s.isAppended && s.turnId === e.turnId) {
          s.isRead = true
        }
      }
    }
    let chunkIndex = 0
    let stopReason: unknown = null
    let usage: unknown = null
    try {
      const stream = next(input)
      for await (const chunk of stream) {
        if (isShown && chunk.kind !== 'engine') {
          emit({ type: 'chunk', ...tag, chunkIndex: chunkIndex++, chunk })
        }
        yield chunk
      }
      const result = await stream.result
      stopReason = result.stopReason
      usage = result.usage
      return result
    } finally {
      if (isMain) {
        state.steps--
      }
      if (isShown) {
        endStep(loopKey(e.agentId), { type: 'step', phase: 'end', ...tag, stopReason, usage })
      }
    }
  })

  on('tool.call', { tool: /^/ }, async ($, e, next) => {
    const call = `${e.tool_use_id ?? ''}#${++state.toolCalls}`
    const base = { toolUseId: e.tool_use_id || null, tool: e.tool, agentId: e.agentId ?? null }
    const input = toolInput(e as Record<string, unknown>)
    const first = firstQuestion((e as Record<string, unknown>).questions)
    // The dialog the ask mod opens inside its own call: this plugin's only
    // AskUserQuestion (the ask mod refuses any other). No transcript row
    // names it, so its call and result are not posted; its request carries
    // the call it opened inside.
    const isDialog = e.tool === 'AskUserQuestion' && (next as { origin?: { plugin?: string } }).origin?.plugin === PLUGIN
    if (isDialog && base.toolUseId !== null) {
      state.dialogCalls.set(base.toolUseId, askCallFor(first))
    }
    if (!isDialog) {
      emit({ type: 'tool', phase: 'call', ...base, input: input.value, ...(input.cut && { truncated: true }) })
    }
    let settle: (text: string | undefined) => void = () => undefined
    const done = new Promise<string | undefined>((resolve) => (settle = resolve))
    const owner = e.agentId === undefined ? state.mainTurn : state.foreground.get(e.agentId)
    state.calls.set(call, {
      tool: String(e.tool),
      owner,
      done,
      settle,
      ...(base.toolUseId !== null && { toolUseId: base.toolUseId }),
      ...(e.tool === ASK_TOOL && { question: first }),
    })
    let resultText: string | undefined
    try {
      const result = await next(e)
      resultText = typeof result.text === 'string' ? result.text : undefined
      // A Bash call of a turn being interrupted: its result, which the record
      // names, goes back once the record is in, so the turn ends after it.
      const interrupted = e.tool === 'Bash' && owner !== undefined ? state.interrupts.get(owner) : undefined
      if (interrupted !== undefined) {
        state.calls.get(call)?.settle(resultText)
        let held: { cancel: () => void } | undefined
        await Promise.race([interrupted.recorded, new Promise<void>((resolve) => (held = $.clock.after(INTERRUPT_HOLD_MS, resolve)))])
        held?.cancel()
      }
      const text = capped(result.text)
      const denied = capped(result.deny)
      if (isDialog) {
        return result
      }
      emit({
        type: 'tool',
        phase: 'result',
        ...base,
        isError: result.isError === true,
        ...(result.deny !== undefined && { denied: denied.value }),
        ...(typeof result.text === 'string' && { text: text.value }),
        ...((text.cut || denied.cut) && { truncated: true }),
      })
      return result
    } finally {
      state.calls.get(call)?.settle(resultText)
      state.calls.delete(call)
      if (isDialog && base.toolUseId !== null) {
        state.dialogCalls.delete(base.toolUseId)
      }
    }
  }).catch((_, e, next) => next(e))

  // A call the engine puts to the dialog: its PermissionRequest, next, names
  // no call, so the check's id is kept for it.
  on('tool.check', { tool: /^/ }, async (_, e, next) => {
    const verdict = await next(e)
    if (verdict.decision === 'ask' && typeof e.tool_use_id === 'string' && e.tool_use_id !== '' && state.post !== undefined) {
      state.checks.push({ toolUseId: e.tool_use_id, tool: e.tool, agentId: e.agentId ?? null, input: e.input })
      if (state.checks.length > CHECKS_KEPT) {
        state.checks.shift()
      }
    }
    return verdict
  }).catch((_, e, next) => next(e))

  // A prompt the dialog shows (a permission, a native question): raised, and
  // answerable from outside while the dialog stays up. The settings hooks
  // beneath decide first; one that did, or the person answering meanwhile,
  // leaves nothing to raise.
  on('classic.PermissionRequest', { hook_event_name: 'PermissionRequest' }, async ($, e, next) => {
    if (state.post === undefined) {
      return next(e)
    }
    const agentId = e.agent_id ?? null
    const claimed = claimCheck(e.tool_name, agentId, e.tool_input)
    if (claimed?.isDecided) {
      return next(e)
    }
    const id = claimed?.toolUseId ?? `request-${Date.now().toString(36)}-${++state.minted}`
    const beneath = await next(e)
    const now = await $.clock.now()
    // Decided after the last await, so a record that came meanwhile is seen:
    // a call already decided is never raised.
    if (beneath.decision !== undefined || state.records.has(id) || state.isEnding) {
      return beneath
    }
    const input = capped(e.tool_input)
    const r: Request = {
      id,
      tool: e.tool_name,
      input: input.value,
      rawInput: e.tool_input,
      isTruncated: input.cut,
      agentId,
      // A background subagent's dialog waits for this hook: bounded, and said so.
      ...(agentId !== null && isBackground(agentId) && { deadline: now + BACKGROUND_WINDOW_MS }),
      isAsync: false,
      isQuestion: e.tool_name === 'AskUserQuestion',
      t: now,
      turnId: state.loopTurns.get(loopKey(agentId)),
      isAborted: false,
      transcript: typeof e.transcript_path === 'string' && e.transcript_path !== '' ? e.transcript_path : undefined,
    }
    const outer = state.dialogCalls.get(id)
    if (outer !== undefined && outer !== id) {
      r.toolUseId = outer
    }
    raise(r)
    const decision = await awaitDecision($, r, next.signal)
    return decision === undefined ? beneath : { ...beneath, decision }
  }).catch((_, e, next) => next(e))

  // The engine's record of each permission decision, by call: who decided
  // it, the evidence a request's settlement names.
  on('telemetry.log', { to: 'collector' }, async (_, e, next) => {
    if (state.post !== undefined && e.to === 'collector' && e.event === 'tool_decision') {
      const { tool_use_id: id, source, decision } = e.attributes
      if (typeof id === 'string' && typeof source === 'string') {
        decisionRecorded(id, source, decision === 'accept')
      }
    }
    return next(e)
  }).catch((_, e, next) => next(e))

  // Every row the session keeps, once it is written: named (row order: the
  // engine's appends may resolve in another order than they began, and the
  // file holds them in the order they resolve), then a call's result, a
  // main-loop row that may hold a message to the host. A row refused beneath
  // is never written, and never named.
  on('session.append', { door: /^/ }, async (_, e, next) => {
    const isLive = state.post !== undefined
    const agentId = e.agentId ?? null
    const stored = await next(e)
    if (isLive && stored.deny === undefined) {
      announceRow(e.door, e.door === 'note' ? stored.message : e.message, stored.uuid, agentId)
      observeRow(e.door, e.message, stored.uuid)
      if (agentId === null) {
        exportRow(e.door, stored.message, stored.uuid, e.origin)
        enteredRow(e.door, stored.message, stored.uuid, e.origin)
      }
    }
    return stored
  }).catch((_, e, next) => next(e))

  // Every compaction this plugin did not start (the person's /compact, a
  // command run, the engine's own); this plugin's own pass no hook of its
  // (runCompaction and the compact tool name theirs). One that stood writes
  // its rows once the hooks are through: named from the transcript. A
  // precompute installs nothing.
  // A failure here leaves the compaction as it settled: `next` in the catch
  // replays it, nothing beneath running again.
  on('session.compact', { trigger: /^/ }, async (_, e, next) => {
    const result = await next(e)
    if (state.post !== undefined && e.trigger !== 'precompute' && result.skip === undefined) {
      compacted(e.agentId ?? null, result.messages)
    }
    return result
  }).catch((_, e, next) => next(e))

  on('agent.spawn', { tool_use_id: /^/ }, async (_, e, next) => {
    // The list may name the agent before this hook has said so: it is this hook's.
    state.spawning++
    let result: Awaited<ReturnType<typeof next>>
    try {
      result = await next(e)
    } finally {
      state.spawning--
    }
    if (result.agentId !== undefined) {
      state.freshLoops.add(result.agentId)
      // A foreground subagent's calls belong to the main turn it runs in (an
      // interrupt of that turn ends it); a nested one's, to its parent's.
      const owner = e.parentAgentId === undefined ? state.mainTurn : state.foreground.get(e.parentAgentId)
      if (!e.background && owner !== undefined) {
        state.foreground.set(result.agentId, owner)
      }
      emit({
        type: 'agent',
        phase: 'spawn',
        agentId: result.agentId,
        parentAgentId: e.parentAgentId ?? null,
        subagentType: e.subagentType,
        description: e.description,
        name: e.name ?? null,
        background: e.background,
        model: result.model,
        toolUseId: e.tool_use_id || null,
      })
      watchAgents()
    }
    return result
  })

  on('classic.SubagentStop', { hook_event_name: 'SubagentStop' }, async (_, e, next) => {
    state.foreground.delete(e.agent_id)
    // Said already when the engine's list showed it over.
    if (state.agents.get(e.agent_id)?.running !== false) {
      emit({ type: 'agent', phase: 'stop', agentId: e.agent_id, agentType: e.agent_type })
    }
    return next(e)
  })
}
