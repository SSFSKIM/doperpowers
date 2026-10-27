import type { EngineInterface, HttpResponse, On, PermissionRequestDecision, SessionStartInput } from 'claude-code'
// devcloud's contract, for the read of its guard's marker (erased at run time).
import type {} from '../../../devcloud/types/devcloud'

import { ASK_TOOL, PLUGIN, asyncAsks, observeAsks } from './ask'
import { OFF_LINE, ON_LINE, isCuaEnabled, isLiveMarker, verdictOf } from './bridge-place'
import type { Guard, Place, Verdict } from './bridge-place'
import { EFFORTS, INTERRUPT_HOLD_MS, RESPAWN_FIRST_MS, RESPAWN_STEP_MS, WAKE_LINE, capped, isEffort, isLaneVerdict, isObserver, loopKey, message, parsed, state } from './bridge-state'
import type { Answer, Capabilities, Command, Decision, DeliveryKey, DeskRun, Override, Readback, Request, Steer, Stops, Wake } from './bridge-state'
import { adoptKept, adoptSeed, emit, emitOwed, emitTaken, endStep, forgetLive, poster, pump, releaseStepEnd, requeue, resyncEvents, stopChild } from './bridge-stream'
import {
  CHECKS_KEPT,
  askCallFor,
  answerFromOutside,
  boundedSuggestions,
  claimCheck,
  decisionRecorded,
  engineDecision,
  firstQuestion,
  isBackground,
  onAskNote,
  raise,
  settle,
  shownCall,
  withdrawAll,
} from './bridge-requests'
import { announceRow, commandRow, compacted, enteredRow, exportRow, noticeRow, observeRow, readBack } from './bridge-rows'
import { claimAgent, forgetAgents, refreshAgents, watchAgents } from './bridge-agents'
import { measuredFor, routeOf } from './bridge-commands'
import { catalogNow } from './bridge-catalog'
import { OBSERVER_REASON, controlsOf } from './bridge-controls'
import { READ_KINDS, readKind } from './bridge-reads'
import { endOrphanedSideQuestions, sideQuestion } from './bridge-btw'
import { engineError, forNotes, notifiedStops, stopAgent, tellAgent } from './bridge-agent-ops'
import { acceptMedia, claimMedia, mediaLoaded, mediaPassedOn, mediaTurnEnded, mediaTurnStarted, observeMediaResult } from './bridge-media'

export { OFF_LINE, ON_LINE } from './bridge-place'
export { BLOCK_TAIL, INTERRUPT_HOLD_MS, TEXT_CAP, WAKE_LINE, capped, resetBridge } from './bridge-state'
export { RESYNC_INPUT_CAP, RESYNC_MAX, STEP_END_WAIT_MS } from './bridge-stream'
export { RECORD_WAIT_MS, TRANSCRIPT_RETRY_MS, onAskNote } from './bridge-requests'
export { READBACK_WAIT_MS, READBACK_WINDOW_MS, ROWS_POLLS, ROWS_POLL_MS, compacted } from './bridge-rows'
export { AGENTS_REFRESH_MS } from './bridge-agents'
export { FOLLOW_REASON, PANEL_REASON, SELF_REASON, UNKNOWN_REASON, UNMEASURED_REASON, measuredFor, routeOf, tableFor } from './bridge-commands'

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
 * `session.start` again, which spawns the next; a child that ends on its own
 * is started again at once, with a backoff only while successors keep ending
 * at once (`startChild`). Each post carries the nonce
 * its child's hello named, so the child turns away (409) what an older module
 * instance still has in flight after a reload, and a module whose post is
 * turned away stops for good.
 *
 * Control (DC2 M2): `steer` appends a user row the loop reads at its next
 * request, the owner's words under STEER_LINE; `interrupt` aborts the main
 * turn and stops each Bash call the abort moved to the background, and before
 * the turn ends appends Esc's marker and a note saying so;
 * `model` rewrites the main loop's requests;
 * `compact` runs between turns; `deliver` gives the owner's log event as the
 * human's words, once per key: into the running turn as a row, as a steer,
 * else as a prompt of its own (a peer's goes to the session's inbox, and the
 * bridge refuses one written by a session). A message to the session wakes
 * it, though the engine refuses a plugin's prompt after an Esc: such a
 * delivery goes in as a row, and a delivered row the session has not read
 * while stopped wakes it through its inbox (the child's `inbox` event), which
 * carries only the wake, never the human's words. A row an Esc rewound past
 * is given again. What must outlive a module reload (the model chosen, the keys
 * delivered) the child keeps on disk: its hello hands it back.
 *
 * The bridge must sit outside every secrets guard, and checks that it does on
 * each settled `tool.call` and `session.append`. Until the first check a tool
 * event waits, and no permission's input is raised (a native question is). A
 * bridge that finds a guard outside it turns itself off, stopping its child,
 * until a later dispatch sees the loaded guard beneath it (`judgePlace`).
 *
 * In a MAWS lane B session (O12 M3: MAWS_LANE=B, its parent the pid
 * SMNS_MEMBER names) MAWS is the controller, and the bridge only observes:
 * every control op is refused `lane-b`, nothing is raised, `turn.step`
 * rewrites nothing, and the stream goes on. The mod reads the marker at its
 * session start and observes until its child's verdict on the parent check
 * (its hello's `lane`, or a later `lane` line) says `mismatch`.
 *
 * Code that takes `$` stays in this file: the hooks, the session start, the
 * child and the session it serves, control, the wait for a decision, and the
 * reads of which guard is loaded. The modules beside it take none, and reach
 * the engine only through the calls the session start keeps in the state
 * (`post`, `read`, `log`, `after`). Each imports only those listed before it:
 * - bridge-place.tsx: the rule that judges the bridge's place among the
 *   guards from what settled beneath its hook;
 * - bridge-state.tsx: the one state object, its types, and `resetBridge`;
 * - bridge-stream.tsx: the mod's copy of the session's live state, which
 *   every resync carries, and the poster;
 * - bridge-requests.tsx: requests from outside, and their settlement;
 * - bridge-rows.tsx: row order (each kept row's notice, a compaction's rows
 *   read from the transcript), the rows exported as messages to the host,
 *   and the row a delivered prompt became;
 * - bridge-agents.tsx: the agents the module did not see spawn, learned from
 *   the engine's list;
 * - bridge-routes.tsx, bridge-commands.tsx: the desk's route table, written
 *   from its fixture, and the rule that routes a command by it;
 * - bridge-controls.tsx: the desk's per-control capability map;
 * - bridge-reads.tsx (which takes `$`, as bridge-catalog.tsx does): the
 *   desk's reads of usage, config, settings and MCP servers, cut to what the
 *   desk shows;
 * - bridge-btw.tsx, bridge-agent-ops.tsx and bridge-media.tsx (which take
 *   `$`): the desk's side question, one subagent stopped or told, and the
 *   desk's images and PDFs read into the conversation.
 *
 * The desk's ops (spec 2026-10-22-desk-control-surface-design.md): `read`
 * answers from `$` at once (`status`, `catalog`, and bridge-reads.tsx's
 * kinds); `command` runs one slash command the
 * route table allows, answering `queued` at once and its outcome on the
 * stream (`run` start and end, the end carrying what the command printed,
 * read back from its rows), one desk command at a time. What the bridge can
 * do (`capabilities`) every resync carries to the child.
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
/** A line sminos opens every event it pushes with, naming the event (sminos.py, compose_chat_frame and compose_frame). */
const FRAME_LINE = /^\[sminos [^\n]*\]$/

/** A delivered text's frame line, when it opens with one that text follows; never a line of the human's words. */
function frameOf(text: string): string | undefined {
  const at = text.indexOf('\n')
  const first = at === -1 ? undefined : text.slice(0, at)
  return first !== undefined && FRAME_LINE.test(first) ? first : undefined
}

/** When the rows a wake points at went in: as the turn answered, in a turn then stopped, or after a stop. */
export type WakeWhen = 'answer' | 'aborted' | 'stopped'

/**
 * A wake's text. The row it points at is already in the conversation, so the
 * wake names it rather than repeating it: what is unread (the human's
 * messages, the notes steered in, or both, each named as what it is, so the
 * model does not take the wake itself for the note and find it empty), when
 * it went in, and what it looks like where it sits: a user message, and, for
 * a turn that answered past it, one just before that answer, which came too
 * late for it. A steer given during the final answer sits there, before the
 * answer's text, so the model takes it for a request it saw and missed, and,
 * told of an unread "note" somewhere above the wake, found none (live,
 * `steer-wake`). Then, for each message whose text opens with a sminos frame
 * line, that line (`Unread:`). The engine drops a peer message identical to
 * its sender's previous one within 30 s (2.1.300 peer guard,
 * `dedupWindowMs`, live: "identical to the previous message from this
 * sender"), and every inbox wake is the child's: the frame lines keep two
 * wakes in that window apart.
 */
export function wakeText(when: WakeWhen, rows: readonly { isDelivery?: boolean; frame?: string }[]): string {
  const messages = rows.filter((r) => r.isDelivery === true).length
  const notes = rows.length - messages
  const named = [
    ...(messages === 0 ? [] : [messages === 1 ? 'a message for you' : `${messages} messages for you`]),
    ...(notes === 0 ? [] : [notes === 1 ? 'a note' : `${notes} notes`]),
  ].join(' and ')
  const isOne = rows.length === 1
  const it = isOne ? 'it' : 'them'
  const added = `${named.charAt(0).toUpperCase()}${named.slice(1)} ${isOne ? 'was' : 'were'} added to the conversation`
  const at =
    when === 'answer'
      ? `while you were finishing your answer, too late for that answer to take ${it} in`
      : when === 'aborted'
        ? `during your turn, which was stopped before you read ${it}`
        : 'after your turn was stopped'
  const frames = rows.flatMap((r) => (r.frame === undefined ? [] : [r.frame]))
  const unread = frames.length === 0 ? '' : `\nUnread: ${frames.join(' ')}`
  const what = isOne ? 'It is the user message' : 'They are the user messages'
  const where = when === 'answer' ? 'just before your last answer' : 'before this message'
  return `${WAKE_LINE}\n${added} ${at}. ${what} ${where}: read ${it} and act on ${it} now.${unread}`
}
/** Deliveries whose prompt row is awaited, at most (the oldest is let go). */
const SUBMISSIONS_KEPT = 100
/** After an abort, how long the Bash calls it ended have to report where they went. */
export const INTERRUPT_WAIT_MS = 3_000
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

/** What a verb that needs the main turn's state says while it is unknown. */
export const TURN_UNKNOWN = 'turn state unknown since the bridge reloaded; retry after the next model request'
const TURN_OPS = new Set(['steer', 'interrupt', 'compact'])
/** The ops this bridge answers (DX5 `capabilities.ops`), and the reads (`read`'s kinds). */
export const OPS = ['ping', 'steer', 'interrupt', 'stop', 'model', 'compact', 'deliver', 'answer', 'read', 'command', 'btw', 'stop-agent', 'tell', 'media']
export const READS = ['status', 'catalog', ...READ_KINDS]
/**
 * The ops an observer refuses (O12 M3): every op that acts on the session.
 * `ping` and `read` only look, and go on answering.
 */
const CONTROL_OPS = new Set(OPS.filter((op) => op !== 'ping' && op !== 'read'))
/** An observer's refusal: MAWS controls this session (its lane B), and two controllers on one session is what observing prevents. */
export const LANE_B = 'lane-b'
/** The lane verdict kept for a module reload (types/sminos.d.ts): the process's, so a reload never re-opens the provisional window. */
const LANE = { plugin: 'sminos', key: 'lane' } as const
/** The DX5 protocol the capabilities speak: 2 is the desk's control surface (capabilities, `read`, `command`). */
export const CAPABILITIES_PROTOCOL = 2
/**
 * How long a desk command's answer waits for the engine to refuse it at once:
 * after an Esc the engine rejects `$.command.run` until the person types in
 * the terminal (H-esc), and that refusal is the op's answer (`stopped`).
 * Anything else, even a settle this soon, is answered `queued`.
 */
export const STOPPED_WAIT_MS = 250
/** The engine's refusal of a plugin's run or prompt after an Esc, until the person sends input (2.1.300 `k_e`). */
const STOPPED_REFUSAL = 'the session was stopped and nobody has sent input since'
/** The command that replaces this module: nothing of the desk's runs through it after one. */
const RELOAD = 'reload-plugins'
/** A desk command sent while a reload is queued or running: the module it would run in is going. */
export const RELOADING_REASON = 'the plugins are reloading: send it again once the session answers from its reloaded bridge'
/** How long a reload this module outlived holds the desk's commands back (the daemon's own bound on it). */
export const RELOAD_HOLD_MS = 60_000
/** How long a reload waits for its start to reach the child before it is not run (the daemon waits as long for the answer). */
export const RELOAD_TAKEN_WAIT_MS = 10_000

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

/** An op's answer, and what it leaves for after the answer is posted (a desk command's run, whose events follow its answer). */
type Answered = Answer & { after?: () => void }

/** Catalog data belongs to a bridge session and child, even while the engine has moved ahead. */
type CatalogOwner = { session: string | undefined; generation: number }
const CATALOG_MOVED = 'the session or bridge child changed while its catalog was read'
async function catalogStillOwned($: EngineInterface, owner: CatalogOwner): Promise<boolean> {
  const session = await $.session.id()
  return owner.session !== undefined && session === owner.session && state.session === owner.session && state.generation === owner.generation
}

/** Answers one command line with a `result` event, then does what the answer left for after it. */
async function runCommand($: EngineInterface, command: Command) {
  const catalogOwner = command.op === 'read' && command.what === 'catalog' ? { session: state.session, generation: state.generation } : undefined
  let answer: Answered
  try {
    // A false idle would be a lie: interrupt saying there is nothing to stop,
    // a compaction run at once, while a turn the module did not see runs.
    answer =
      isObserver() && CONTROL_OPS.has(command.op)
        ? { ok: false, error: OBSERVER_REASON, code: LANE_B }
        : TURN_OPS.has(command.op) && (await isTurnStillUnknown())
          ? { ok: false, error: TURN_UNKNOWN, code: 'turn-unknown' }
          : await commandAnswer($, command)
    if (catalogOwner !== undefined && !await catalogStillOwned($, catalogOwner)) {
      answer = { ok: false, error: CATALOG_MOVED }
    }
  } catch (error) {
    answer = { ok: false, error: message(error) }
  }
  // A replaced child cannot take this answer. Never send its read id through
  // the successor's socket, even when the successor serves the same session.
  if (catalogOwner !== undefined && (catalogOwner.session !== state.session || catalogOwner.generation !== state.generation)) {
    return
  }
  const { after, ...result } = answer
  emit({ type: 'result', id: command.id, op: command.op, ...result })
  after?.()
}

function commandAnswer($: EngineInterface, command: Command): Answered | Promise<Answered> {
  switch (command.op) {
    case 'ping':
      return { ok: true, result: { pong: true, state: turnState() } }
    case 'steer':
      return steer($, command.text)
    case 'interrupt':
      return interrupt($, command.from)
    case 'stop':
      return stopTask($, command.taskId, command.from)
    case 'model':
      return chooseModel($, command.model, command.effort)
    case 'compact':
      return compact($, command)
    case 'deliver':
      return deliver($, command.key, command.text)
    case 'answer':
      return answerFromOutside(command)
    case 'read':
      return read($, command.what, command.args)
    case 'command':
      return deskCommand($, command)
    case 'btw':
      return sideQuestion($, command.id, command.prompt)
    case 'stop-agent':
      return stopAgent($, command.agentId, command.from, command.resolvedAgentId)
    case 'tell':
      return tellAgent($, command.agentId, command.text, command.resolvedAgentId)
    case 'media':
      return acceptMedia($, command)
    default:
      return { ok: false, error: `unknown op: ${command.op}` }
  }
}

/** A remote's URL with any userinfo (`https://user:token@host/...`) taken out: a read leaves the machine uncoded. */
export function withoutUserinfo(url: string): string {
  return url.replace(/^([A-Za-z][A-Za-z0-9+.-]*:\/\/)[^@/]*@/, '$1')
}

/** The engine's release this session runs, as the route tables are keyed: its base, else its version. */
const engineOf = (v: { version: string; base?: string }) => v.base ?? v.version

/**
 * What this module can do (DX5 `capabilities`): its own plugin's version
 * (a session keeps the module it loaded, so a session that loaded before an
 * update is told from a machine still behind), the engine and the table its
 * commands route by.
 */
async function capabilitiesOf($: EngineInterface, engine: string): Promise<Capabilities> {
  let sminos = 'unknown'
  try {
    const version = parsed(await $.fs.read(`${$.plugin.root}/.claude-plugin/plugin.json`))?.version
    if (typeof version === 'string' && version !== '') {
      sminos = version
    }
  } catch (error) {
    $.ui.log(`bridge: the plugin's version was not read: ${message(error)}`, { to: 'debug' })
  }
  return laneCapabilities({ sminos, protocol: CAPABILITIES_PROTOCOL, engine, ops: [...OPS], reads: [...READS], routes: { measured: measuredFor(engine) }, controls: controlsOf(sminos) })
}

/** The capabilities as the lane leaves them: an observer has no ops and no control (O12 M3); its reads stay. */
function laneCapabilities(c: Capabilities): Capabilities {
  const isObserving = isObserver()
  return { ...c, ops: isObserving ? [] : [...OPS], controls: controlsOf(c.sminos, isObserving) }
}

/**
 * The child's verdict on the lane (O12 M3), taken for a marked session while
 * none is resolved: a resolved one is the process's (its parent is what it
 * was launched under) and stands, kept in `$.state` for a reload. True when
 * it changed whether the bridge observes, its capabilities changed with it.
 */
function adoptVerdict($: EngineInterface, verdict: unknown): boolean {
  if (!state.isLaneMarked || !isLaneVerdict(verdict) || (state.laneVerdict !== undefined && state.laneVerdict !== 'unresolved')) {
    return false
  }
  const wasObserver = isObserver()
  state.laneVerdict = verdict
  if (verdict !== 'unresolved') {
    $.state.set(LANE, verdict).catch((error: unknown) => $.ui.log(`bridge: the lane verdict is not kept for a reload: ${message(error)}`, { to: 'debug' }))
  }
  if (wasObserver === isObserver()) {
    return false
  }
  $.ui.log(`bridge: lane verdict ${verdict}: ${isObserver() ? 'observing' : 'controlling'}`, { to: 'debug' })
  if (state.capabilities !== undefined) {
    state.capabilities = laneCapabilities(state.capabilities)
  }
  return true
}

/** DX5 `read`: what the desk shows of the session, answered from `$` (spec §5; `usage`, `config`, `settings` and `mcp` in bridge-reads.tsx). */
async function read($: EngineInterface, what: unknown, args: unknown): Promise<Answer> {
  if (what === 'catalog') {
    return { ok: true, result: await state.refreshCatalog!() }
  }
  const kind = readKind($, what, args)
  if (kind !== undefined) {
    return kind
  }
  if (what !== 'status') {
    return { ok: false, error: `no read ${String(what)}` }
  }
  const [version, model, cwd, root, repo, surfaces] = await Promise.all([
    $.session.version(),
    $.session.model(),
    $.session.cwd(),
    $.session.root(),
    $.session.repo(),
    $.session.surfaces(),
  ])
  return {
    ok: true,
    result: {
      version: { version: version.version, ...(version.base !== undefined && { base: version.base }), ...(version.builtAt !== undefined && { builtAt: version.builtAt }) },
      model,
      cwd,
      root,
      repo: repo === null ? null : { ...(repo.remote !== null && { remote: withoutUserinfo(repo.remote) }) },
      surfaces: [...surfaces],
      override: state.override ?? null,
    },
  }
}

/** What a desk command's promise settled to, as its `run` end carries it; an Esc's refusal is `stopped`. */
type Settled = { ok: true; text?: string; context?: string[] } | { ok: false; error: string; code?: 'stopped' }

/**
 * DX5 `command`: one slash command from the desk, routed by the table (an
 * older or wrong client cannot run a panel: the route is checked here, on
 * every op), then run with `$.command.run`, never awaited past the call: the
 * answer is `queued` at once (mid-turn the engine queues even an `immediate`
 * command, H-queue), and the outcome follows on the stream as `run` start and
 * end. Desk commands run one at a time: the next is called once the last is
 * read back (§6), so the rows of two are never confused. An Esc's refusal,
 * which the engine gives at once, is the answer instead (`stopped`): nothing
 * ran.
 */
async function deskCommand($: EngineInterface, command: Command): Promise<Answered> {
  const { name, args } = command
  if (typeof name !== 'string' || name === '' || (args !== undefined && typeof args !== 'string')) {
    return { ok: false, error: 'a command is its name, and its args as text' }
  }
  const engine = state.capabilities?.engine ?? engineOf(await $.session.version())
  const listed = (await $.command.list()).find((c) => c.name === name)
  const routed = routeOf(engine, listed, name, args ?? '', $.plugin.name)
  if ('refusal' in routed) {
    return { ok: false, error: routed.refusal.reason, code: routed.refusal.code }
  }
  const run: DeskRun = { id: command.id, name, args: (args ?? '').trim(), prompt: routed.route.class === 'run-prompt' }
  const queued: Answered = { ok: true, result: { queued: true, route: routed.route.class, id: command.id } }
  if (state.deskRun?.name === RELOAD || state.deskQueue.some((r) => r.name === RELOAD)) {
    return { ok: false, error: RELOADING_REASON }
  }
  if (state.deskRun !== undefined) {
    state.deskQueue.push(run)
    return queued
  }
  state.deskRun = run
  if (run.name === RELOAD) {
    return { ...queued, after: () => void reloadPlugins($, run) }
  }
  const settled = callRun($, run)
  let waited: { cancel: () => void } | undefined
  const early = await Promise.race([settled, new Promise<undefined>((resolve) => (waited = $.clock.after(STOPPED_WAIT_MS, () => resolve(undefined))))])
  waited?.cancel()
  if (early !== undefined && !early.ok && early.code === 'stopped') {
    releaseDeskRun($, run)
    return { ok: false, error: early.error, code: 'stopped' }
  }
  return { ...queued, after: () => void followRun($, run, settled) }
}

/** The run of a desk command, settled as its `run` end carries it: never rejected. */
function callRun($: EngineInterface, run: DeskRun): Promise<Settled> {
  return $.command.run({ command: run.name, args: run.args }).then(
    (r): Settled => ({
      ok: true,
      ...(r.text !== undefined && { text: capped(r.text).value as string }),
      ...(r.context !== undefined && { context: capped([...r.context]).value as string[] }),
    }),
    (error: unknown): Settled => {
      const why = message(error)
      return { ok: false, error: why, ...(why.includes(STOPPED_REFUSAL) && { code: 'stopped' as const }) }
    },
  )
}

/**
 * A desk command's run on the stream, after its answer: `run` start, then,
 * once it settled and was read back, its end.
 */
async function followRun($: EngineInterface, run: DeskRun, settled: Promise<Settled>) {
  emit({ type: 'run', phase: 'start', id: run.id, name: run.name, args: run.args })
  const outcome = await settled
  const readback: Readback = !outcome.ok ? { how: 'none' } : outcome.text !== undefined ? { how: 'text', text: outcome.text } : run.prompt ? { how: 'none' } : await readBack(run.name, run.args)
  void emitOwed({ type: 'run', phase: 'end', id: run.id, name: run.name, args: run.args, settled: outcome, readback })
  releaseDeskRun($, run)
}

/**
 * A `/reload-plugins` may replace this module, fencing its posts: call it
 * only once its answer and start reached the child. The daemon confirms a
 * replacement by another child answering. If this module survives, report
 * the returned text like reload-skills and free the desk; without text the
 * daemon's effect check still owns the outcome. Commands sent meanwhile are
 * refused (RELOADING_REASON).
 */
async function reloadPlugins($: EngineInterface, run: DeskRun) {
  const end = (settled: Settled, readback: Readback = { how: 'none' }) => void emitOwed({ type: 'run', phase: 'end', id: run.id, name: run.name, args: run.args, settled, readback })
  let waited: { cancel: () => void } | undefined
  const isTaken = await Promise.race([
    emitTaken({ type: 'run', phase: 'start', id: run.id, name: run.name, args: run.args }),
    new Promise<boolean>((resolve) => (waited = $.clock.after(RELOAD_TAKEN_WAIT_MS, () => resolve(false)))),
  ])
  waited?.cancel()
  if (!isTaken) {
    end({ ok: false, error: 'its start did not reach the bridge: it was not run' })
    releaseDeskRun($, run)
    return
  }
  const outcome = await callRun($, run)
  if (!outcome.ok) {
    end(outcome)
    releaseDeskRun($, run)
    return
  }
  if (outcome.text !== undefined) {
    end(outcome, { how: 'text', text: outcome.text })
    releaseDeskRun($, run)
    return
  }
  $.clock.after(RELOAD_HOLD_MS, () => releaseDeskRun($, run))
}

/** A desk command done with: the next waiting is called. */
function releaseDeskRun($: EngineInterface, run: DeskRun) {
  if (state.deskRun !== run) {
    return
  }
  const next = state.deskQueue.shift()
  state.deskRun = next
  if (next?.name === RELOAD) {
    void reloadPlugins($, next)
  } else if (next !== undefined) {
    void followRun($, next, callRun($, next))
  }
}

/**
 * The first line of a steer's row, the owner's words after it. The engine
 * keeps every row this plugin appends alike (a user row, isMeta, the plugin's
 * origin) and takes nothing from `$.session.append` but text blocks, so the
 * row's own text is the only place a reader of the transcript (the desk among
 * them) can tell a steer from the bridge's other rows. The line is the one
 * `sminos steer` opens its inbox fallback with (sminos_control.py), and no
 * delivery's: the model reads the owner's words framed as a delivery's are.
 */
export const STEER_LINE = '[sminos steer from human]'

/**
 * A user row in the running turn, read at the loop's next model request; the
 * running tool goes on. The row is the owner's words under STEER_LINE, so no
 * text, the interrupt's marker or a note quoted whole included, reads as
 * another of the bridge's rows. The terminal does not draw an appended row,
 * so a transcript line mirrors the words. Idle, there is no next request to
 * read it: a send is how an idle session is reached.
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
    stored = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text: `${STEER_LINE}\n${text}` }] } })
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
  const unread = mine.filter((s) => !s.isRead)
  const isDeliveryUnread = unread.some((s) => s.isDelivery === true)
  if (ended === 'answer' && unread.length > 0) {
    wakeForSteer($, unread)
  } else if (ended === 'aborted' && isDeliveryUnread) {
    // A stopped turn: the engine would refuse the prompt, not the inbox frame.
    void wakeAfterStop($, turnId, unread)
  }
}

/**
 * The wake for a stopped turn that left a delivered row unread. An Esc before
 * the model answered rewinds the conversation past the turn's prompt, and the
 * rows given after it with it, as the turn ends (2.1.300 restoreMessageSync):
 * a wake then points at a row the conversation no longer holds, and its turn
 * finds nothing (live, `restore`: "no such message appears in my context").
 * So the turn's delivered rows are checked first, as the next turn's start
 * checks them (recheckDeliveries): each the conversation lacks goes in again
 * now, woken as a row given after a stop is (appendDelivery); those it holds
 * stay for that check, and the unread among them are named in one wake, with
 * the turn's unread steers (which wake nothing of their own). An unreadable
 * conversation leaves every row for that check, and the wake names them all.
 */
async function wakeAfterStop($: EngineInterface, turnId: string, unread: readonly Steer[]) {
  const conversationAt = state.conversation
  const compactionsAt = state.compactions
  // Taken out of the next turn's check while this one runs, so no row is given twice.
  const rows = state.deliveredRows.filter((r) => r.turnId === turnId)
  state.deliveredRows = state.deliveredRows.filter((r) => r.turnId !== turnId)
  let conversation: unknown
  try {
    conversation = await $.session.messages({ as: 'api' })
  } catch (error) {
    conversation = message(error)
  }
  if (conversationAt !== state.conversation) {
    return
  }
  // Compacted meanwhile: the rows are in its summary, and none is given again.
  if (compactionsAt !== state.compactions) {
    emit({ type: 'inbox', text: wakeText('aborted', unread) })
    return
  }
  const texts = Array.isArray(conversation) ? userTexts(conversation) : undefined
  if (texts === undefined) {
    $.ui.log(`bridge: the conversation was not read to check a stopped turn's delivered rows: ${JSON.stringify(conversation)}`, { to: 'debug' })
  }
  const missing = texts === undefined ? [] : rows.filter((r) => !texts.some((t) => t.includes(r.text)))
  state.deliveredRows.push(...rows.filter((r) => !missing.includes(r)))
  const named = unread.filter((s) => s.isDelivery !== true || !missing.some((r) => r.text === s.text))
  if (named.some((s) => s.isDelivery === true)) {
    emit({ type: 'inbox', text: wakeText('aborted', named) })
  }
  for (const r of missing) {
    if (conversationAt !== state.conversation || compactionsAt !== state.compactions) {
      return
    }
    $.ui.log(`bridge: the delivery ${r.key.writer}:${r.key.seq} is not in the conversation after the stop (an Esc rewound past it): delivered again`, { to: 'debug' })
    await appendDelivery($, r.key, r.text, state.mainTurn)
  }
}

/**
 * Wakes the session for the rows its turn answered before reading (steers,
 * delivered messages): they are already in the conversation, so the prompt
 * names them rather than repeating them (wakeText), and the next request
 * reads them. When a delivery's row is
 * among them and the engine refuses the prompt because the human stopped the
 * session, the wake goes as an inbox frame instead, decided as the drop
 * settles: not when a request has read the rows since (a human's prompt the
 * wake queued behind, then an Esc that emptied the queue), nor after a /clear
 * (forgetLive lets the wake go).
 */
function wakeForSteer($: EngineInterface, unread: readonly Steer[]) {
  const text = wakeText('answer', unread)
  // Marked read by the main loop's requests meanwhile (turn.step).
  const wake: Wake | undefined = unread.some((s) => s.isDelivery === true) ? { isRead: false, ...(state.mainTurn !== undefined && { turnAt: state.mainTurn }) } : undefined
  if (wake !== undefined) {
    state.wakes.push(wake)
  }
  const isOwed = () => {
    const owed = wake !== undefined && state.wakes.includes(wake) && !wake.isRead
    state.wakes = state.wakes.filter((w) => w !== wake)
    return owed
  }
  void $.prompt.submit({ text, asUser: true }).then(
    (entered) => {
      const owed = isOwed()
      if (entered.drop === undefined) {
        return
      }
      $.ui.log(`bridge: the wake for an unread steer was dropped: ${entered.drop}`, { to: 'debug' })
      if (owed && STOPPED_DROPS.has(entered.drop)) {
        emit({ type: 'inbox', text })
      }
    },
    (error: unknown) => {
      isOwed()
      $.ui.log(`bridge: the wake for an unread steer was not submitted: ${message(error)}`, { to: 'debug' })
    },
  )
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

/** The tool that runs a subagent: `Agent` (`Task` on an older engine). */
const AGENT_TOOLS: ReadonlySet<string> = new Set(['Agent', 'Task'])

/** A task id as the engine spells one (DX6 `stop`). */
const TASK_ID = /^[A-Za-z0-9_-]{1,64}$/

/**
 * One background shell or monitor stopped, the main loop's or a subagent's,
 * as TaskStop stops it in the terminal. TaskStop also ends an agent, named by
 * its id or its name, so an id the engine's agent list names is refused before
 * the call. The engine's refusal (a task that already ended, one it does not
 * know) is the answer's error, in its words.
 *
 * A plugin's TaskStop writes no row, and for a task of the main loop's the
 * engine queues no notification (a subagent's own is told at its next tool
 * batch): so, as an interrupt does, the stop leaves the model a note, which is
 * also the rows' record that the task stopped (DX4 reads it). The note is in
 * whether a turn runs or not: an idle session reads it at its next request.
 */
async function stopTask($: EngineInterface, taskId: unknown, from: unknown): Promise<Answer> {
  if (typeof taskId !== 'string' || !TASK_ID.test(taskId)) {
    return { ok: false, error: 'stop needs a task id' }
  }
  const agents = await $.agent.list()
  if (agents.some((a) => a.id === taskId || a.name === taskId)) {
    return { ok: false, error: `${taskId} is an agent, not a background shell or monitor` }
  }
  const r = await $.tool.call({ tool: 'TaskStop', task_id: taskId })
  if (r.isError === true) {
    return { ok: false, error: engineError(r.text) }
  }
  await recordStop($, taskId, from)
  return { ok: true, result: { taskId } }
}

/** The line a stop leaves the model, and DX4 reads as the row's whole text (sminos_jobs.STOP_NOTE). */
export function stopNote(taskId: string, from: unknown): string {
  return `Task ${taskId}, a background task, was stopped from ${from === 'desk' ? 'the desk' : 'outside the terminal'}: it is not running.`
}

/** The stop's note, kept as the interrupt's is (isMeta, from the plugin) and mirrored in the transcript. */
async function recordStop($: EngineInterface, taskId: string, from: unknown) {
  const text = stopNote(taskId, from)
  try {
    const stored = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text }] } })
    if (stored.deny !== undefined) {
      $.ui.log(`bridge: the stop's note was refused: ${stored.deny}`, { to: 'debug' })
      return
    }
    noticeRow({ type: 'row-seen', uuid: stored.uuid, agentId: null, door: 'note' })
    $.ui.log(`stop: ${text}`)
  } catch (error) {
    $.ui.log(`bridge: the stop's note was not appended: ${message(error)}`, { to: 'debug' })
  }
}

/** Esc's own marker, whole: the one text a transcript's reader knows a turn's interrupt by. */
const INTERRUPT_MARKER = '[Request interrupted by user]'

/**
 * What an interrupt tells the model beyond Esc's marker: where it came from,
 * and each Bash call it moved to the background, whose result says the
 * command runs on there.
 */
function interruptOrigin(from: unknown): string {
  return `The interrupt came from ${from === 'desk' ? 'the desk' : 'outside the terminal'}.`
}

function interruptNote(from: unknown, stops: Stops): string {
  return [
    interruptOrigin(from),
    ...stops.stopped.map((task) => `Task ${task}, the Bash command the interrupt moved to the background, was then stopped: it is not running, and no notification will come for it.`),
    ...stops.running.map((task) => `Task ${task}, the Bash command the interrupt moved to the background, could not be stopped: it may still be running.`),
  ].join('\n')
}

/**
 * The interrupt's record: Esc leaves the model `[Request interrupted by
 * user]`, a plugin's abort no marker at all, so user rows say it, read at the
 * next request. Two rows: the marker alone, since a transcript's reader knows
 * an interrupt only by a row whose whole text is the marker, then the note. A
 * plugin's user row is kept `isMeta` (2.1.300 `m6r`): the model reads both,
 * and no reader takes the note for a prompt. The terminal does not draw an
 * appended row, so a transcript line mirrors them.
 */
async function recordInterrupt($: EngineInterface, from: unknown, stops: Stops) {
  const kept: string[] = []
  for (const text of [INTERRUPT_MARKER, interruptNote(from, stops)]) {
    try {
      const stored = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text }] } })
      if (stored.deny !== undefined) {
        $.ui.log(`bridge: the interrupt's record was refused: ${stored.deny}`, { to: 'debug' })
        break
      }
      // The hook does not see the plugin's own append: named once it is in.
      noticeRow({ type: 'row-seen', uuid: stored.uuid, agentId: null, door: 'note' })
      kept.push(text)
    } catch (error) {
      $.ui.log(`bridge: the interrupt's record was not appended: ${message(error)}`, { to: 'debug' })
      break
    }
  }
  if (kept.length > 0) {
    // One line: the transcript line draws a newline as U+FFFD (live, 2.1.302).
    $.ui.log(`interrupt: ${kept.join(' ').replaceAll('\n', ' ')}`)
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

/** A session's writer, `<machine>/<session id>`: its events are a peer's words. */
const SESSION_WRITER = /\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

/**
 * Why the engine drops a plugin's prompt when the human stopped the session
 * (2.1.300 `zBt`, `k_e`): Esc, or the stop-agents chord, empties the queue of
 * plugin prompts, and refuses each new one until the human sends input. Any
 * other drop is a hook's or the engine's own decision.
 */
const STOPPED_DROPS = new Set(['the prompt was removed from the queue before it ran', 'the session was stopped and nobody has sent input since'])

/**
 * The owner's log event for this session, as the human's words (sminos sends
 * only the owner's here; one a session wrote is refused whoever sends it, so
 * its sender falls back to the session's inbox, where the engine delivers it
 * as a peer's). While the main turn
 * runs it goes in as a user row, read at the loop's next request (its next
 * tool round), as a steer does; idle, it is submitted as a prompt, a turn of
 * its own. Either way `entered` names its row once it is kept, and `refused`
 * follows `submitted` when nothing could be.
 *
 * A message to the session is meant to wake it, and after an Esc the engine
 * refuses a plugin's prompt until the human sends input (at once, or, for a
 * prompt queued behind a turn, as the Esc empties the queue). Such a delivery
 * goes in as the running turn's row would (appendDelivery): the human's words
 * as a user row, and, with no turn running, only a wake through the inbox,
 * which the engine takes after a stop. The inbox delivers what it carries as
 * another session's message, so the human's words never go through it.
 *
 * Delivery is at least once and goes in seq order per writer within a
 * project, so a key at or below its mark (the last submitted for that writer
 * in that project) is a repeat, and dropped. Every project numbers a writer's
 * events on its own, so the mark is `<project>/<writer>`; a key naming no
 * project (a CLI older than the project in the key) is held to the writer's
 * bare mark, which is all such a CLI ever raised.
 */
async function deliver($: EngineInterface, key: unknown, text: unknown): Promise<Answer> {
  const { project, writer, seq } = (typeof key === 'object' && key !== null ? key : {}) as { project?: unknown; writer?: unknown; seq?: unknown }
  if (
    typeof writer !== 'string' ||
    writer === '' ||
    !Number.isInteger(seq) ||
    typeof text !== 'string' ||
    (project !== undefined && (typeof project !== 'string' || project === ''))
  ) {
    return { ok: false, error: 'deliver needs key {project?, writer, seq} and text' }
  }
  if (SESSION_WRITER.test(writer)) {
    return { ok: false, error: "a session's event is a peer's, not the human's words: it goes to the session's inbox" }
  }
  const delivery: DeliveryKey = { ...(project !== undefined && { project: project as string }), writer, seq: seq as number }
  const mark = project === undefined ? writer : `${project}/${writer}`
  const before = state.delivered.get(mark)
  if (delivery.seq <= (before ?? 0)) {
    emit({ type: 'delivered', key: delivery, outcome: 'duplicate' })
    return { ok: true, result: { duplicate: true } }
  }
  state.delivered.set(mark, delivery.seq)
  emit({ type: 'delivered', key: delivery, outcome: 'submitted' })
  if (state.mainTurn !== undefined) {
    void appendDelivery($, delivery, text, state.mainTurn)
    return { ok: true, result: { submitted: true } }
  }
  // Its row, once kept, is named `entered` (bridge-rows.tsx, enteredRow).
  const submission = { key: delivery, text }
  state.submissions.push(submission)
  if (state.submissions.length > SUBMISSIONS_KEPT) {
    state.submissions.shift()
  }
  const forget = () => (state.submissions = state.submissions.filter((s) => s !== submission))
  // A prompt taken resolves when its turn starts, after any running turn.
  void $.prompt.submit({ text, asUser: true }).then(
    (entered) => {
      if (entered.drop === undefined) {
        return
      }
      forget()
      if (!STOPPED_DROPS.has(entered.drop)) {
        refuseDelivery($, delivery, entered.drop)
        return
      }
      $.ui.log(`bridge: the delivery ${mark}:${delivery.seq} was refused as a prompt (${entered.drop}): it goes in as a row`, { to: 'debug' })
      // Bound to a main turn running by now (one the Esc is still ending), whose end wakes the session if it is unread.
      void appendDelivery($, delivery, text, state.mainTurn)
    },
    (error: unknown) => {
      forget()
      refuseDelivery($, delivery, message(error))
    },
  )
  return { ok: true, result: { submitted: true } }
}

/** A delivery that could not enter: `refused`, after its `submitted`, with the engine's reason. */
function refuseDelivery($: EngineInterface, delivery: DeliveryKey, reason: string) {
  const mark = delivery.project === undefined ? delivery.writer : `${delivery.project}/${delivery.writer}`
  $.ui.log(`bridge: the delivery ${mark}:${delivery.seq} did not enter: ${reason}`, { to: 'debug' })
  emit({ type: 'delivered', key: delivery, outcome: 'refused', reason })
}

/**
 * A delivery put in the conversation as a user row, read at the loop's next
 * request, and named `entered` once it is in. The terminal does not draw an
 * appended row, so a transcript line mirrors it. It is bound to the running
 * main turn (`turnId`) as a steer is (settleSteers): a turn that ends before
 * any request read it wakes the session once. With no turn running (a stop
 * refused its prompt), the session is woken through its inbox once the row is
 * in, unless a main turn started while the append was pending: the row is
 * then that turn's, as a busy delivery's is. It is held until the
 * conversation is known to keep it (recheckDeliveries). `bound`: the steer a
 * re-check bound before its first await, so its turn's end already counts it.
 */
async function appendDelivery($: EngineInterface, delivery: DeliveryKey, text: string, given: string | undefined, bound?: Steer) {
  let turnId = given
  let pending = bound ?? (turnId === undefined ? undefined : bindSteer(turnId, text))
  // A /clear while the append is pending (state.conversation moves): the row
  // is the old conversation's, so the new one's check never holds it.
  const conversationAt = state.conversation
  const settled = (isIn: boolean) => {
    if (pending === undefined) {
      // A row of the old conversation wakes nothing in the new one.
      if (isIn && conversationAt === state.conversation) {
        emit({ type: 'inbox', text: wakeText('stopped', [{ isDelivery: true, frame: frameOf(text) }]) })
      }
      return
    }
    if (isIn) {
      pending.isAppended = true
    } else {
      state.steers = state.steers.filter((s) => s !== pending)
    }
    settleSteers($, pending.turnId)
  }
  let stored: Awaited<ReturnType<EngineInterface['session']['append']>>
  try {
    stored = await $.session.append({ message: { type: 'user', content: [{ type: 'text', text }] } })
  } catch (error) {
    settled(false)
    refuseDelivery($, delivery, message(error))
    return
  }
  if (stored.deny !== undefined) {
    settled(false)
    refuseDelivery($, delivery, stored.deny)
    return
  }
  // Given idle, in while a main turn runs (one started meanwhile): that turn
  // reads it from its next request, and its end wakes the session if none did.
  if (pending === undefined && state.mainTurn !== undefined && conversationAt === state.conversation) {
    turnId = state.mainTurn
    pending = bindSteer(turnId, text)
  }
  if (conversationAt === state.conversation) {
    state.deliveredRows.push({ key: delivery, text, ...(turnId !== undefined && { turnId }) })
  }
  // The hook does not see the plugin's own append: named once it is in.
  noticeRow({ type: 'row-seen', uuid: stored.uuid, agentId: null, door: 'note' })
  emit({ type: 'delivered', key: delivery, outcome: 'entered', uuid: stored.uuid })
  // One line: the transcript line draws a newline as U+FFFD.
  $.ui.log(`delivered: ${text.replaceAll('\n', ' ')}`)
  settled(true)
}

/** A delivery's row bound to its main turn as a steer is, its append still to come. */
function bindSteer(turnId: string, text: string): Steer {
  const frame = frameOf(text)
  const pending: Steer = { turnId, isAppended: false, isRead: false, isDelivery: true, text, ...(frame !== undefined && { frame }) }
  state.steers.push(pending)
  return pending
}

/**
 * The delivered rows that a main turn which did not answer left behind, and
 * those given with no turn running, checked as the next main turn starts
 * against the conversation its requests read. An Esc before the model
 * answered hands the human's prompt back to the input box, and the prompt
 * sent next goes in where that one stood: a row given after it is left on a
 * branch no request reads. One the conversation lacks is appended again, in this turn (read
 * from its second request, or by the wake when it answers in one); one it
 * holds is let go. A row of a turn that answered is in the conversation for
 * good, so its turn's end lets it go (mainTurnEnded), as a compaction lets
 * every row go (bridge-rows.tsx, compacted).
 *
 * Every row's steer is bound to this turn before the first await: the turn
 * may end while the check runs, and its end settles only the steers it has
 * (settleSteers), so a replay bound after it would never wake. Each is let
 * go as its row proves held, or settled as its append does. A /clear while
 * the check runs ends it: nothing is appended to, or kept for, a
 * conversation that is gone.
 */
async function recheckDeliveries($: EngineInterface, turnId: string) {
  const due = state.deliveredRows.filter((r) => r.turnId !== turnId)
  if (due.length === 0) {
    return
  }
  const conversationAt = state.conversation
  const compactionsAt = state.compactions
  const steers = due.map((r) => bindSteer(turnId, r.text))
  // Taken out while the check runs, so another (a stopped turn's, wakeAfterStop) never gives them too.
  state.deliveredRows = state.deliveredRows.filter((r) => !due.includes(r))
  const release = (released: readonly Steer[]) => {
    state.steers = state.steers.filter((s) => !released.includes(s))
    settleSteers($, turnId)
  }
  // The old conversation's turn wakes nothing in the new one: its steers go
  // unsettled. After a compaction the rows are in its summary: none is given
  // again, and the steers are let go.
  const isGone = () => {
    if (conversationAt !== state.conversation) {
      state.steers = state.steers.filter((s) => s.turnId !== turnId)
      return true
    }
    if (compactionsAt !== state.compactions) {
      release(steers)
      return true
    }
    return false
  }
  let conversation: unknown
  try {
    conversation = await $.session.messages({ as: 'api' })
  } catch (error) {
    conversation = message(error)
  }
  if (isGone()) {
    return
  }
  // Unread, the rows wait for the next turn's check.
  if (!Array.isArray(conversation)) {
    $.ui.log(`bridge: the conversation was not read to check ${due.length} delivered rows: ${JSON.stringify(conversation)}`, { to: 'debug' })
    state.deliveredRows.push(...due)
    release(steers)
    return
  }
  const texts = userTexts(conversation)
  const isHeld = due.map((r) => texts.some((t) => t.includes(r.text)))
  release(steers.filter((_, i) => isHeld[i]))
  for (const [i, r] of due.entries()) {
    if (isHeld[i]) {
      continue
    }
    if (isGone()) {
      return
    }
    $.ui.log(`bridge: the delivery ${r.key.writer}:${r.key.seq} is not in the conversation this turn reads (an Esc rewound past it): delivered again`, { to: 'debug' })
    await appendDelivery($, r.key, r.text, turnId, steers[i])
  }
}

/** The text blocks of a conversation's user messages, as `$.session.messages({ as: "api" })` answers it. */
function userTexts(messages: readonly { role?: unknown; content?: unknown }[]): string[] {
  return messages.flatMap((m) =>
    m?.role !== 'user'
      ? []
      : typeof m.content === 'string'
        ? [m.content]
        : Array.isArray(m.content)
          ? m.content.flatMap((b: { type?: unknown; text?: unknown }) => (b?.type === 'text' && typeof b.text === 'string' ? [b.text] : []))
          : [],
  )
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
 * and delivered rows settled (settleSteers): when it answered before any
 * request read one, one wake (the row is in the conversation already), as a
 * prompt typed mid-turn would start the next turn — at once, or once the
 * last of its pending appends settles. An interrupted turn that left a
 * delivered row unread wakes the session through its inbox; a steer it left
 * wakes nothing, nor does a failed turn. Its delivered rows are checked when
 * the next turn starts (recheckDeliveries).
 */
async function mainTurnEnded($: EngineInterface, turnId: string, reason: string) {
  state.interrupts.delete(turnId)
  if (reason === 'answer') {
    state.deliveredRows = state.deliveredRows.filter((r) => r.turnId !== turnId)
  }
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
    // Before the resync below, which carries the capabilities it settles.
    adoptVerdict($, msg.lane)
    // A new child knows nothing of the session: what it started as, then
    // where it stands. What was queued for no child is in that state.
    requeue([{ type: 'session', phase: 'start', session: state.session, ...state.info, t: Date.now() }, ...resyncEvents()])
    pump()
    return
  }
  if (msg.op === 'lane') {
    // A verdict the child resolved after its hello: a change of what the
    // bridge may do reaches the child as a resync, which carries it.
    if (adoptVerdict($, msg.lane) && state.socket !== undefined) {
      state.queue.push(...resyncEvents())
      pump()
    }
    return
  }
  if (typeof msg.id === 'string' && typeof msg.op === 'string') {
    void runCommand($, msg as Command)
  }
}

/**
 * Starts the session's child and reads its lines until it ends; one that
 * ended on its own is started again at once (a crash's successor serves
 * within a fraction of a second), then after a second if that one ends at
 * once too, doubling while they keep doing so, up to a minute. A child that
 * ran STABLE_MS (by the engine's clock) is followed at once again.
 */
function startChild($: EngineInterface, session: string) {
  if (state.session !== session) {
    state.catalog = undefined
  }
  state.session = session
  // An off bridge has no child: only a safe dispatch starts one again
  // (judgePlace), never a /clear's restart, a respawn or a session start.
  if (state.place === 'off') {
    return
  }
  const generation = ++state.generation
  state.socket = undefined
  state.nonce = undefined
  const startedAt = $.clock.now()
  void (async () => {
    let pending = ''
    try {
      // A verdict this process holds goes to every child it starts: a
      // replacement after the engine host exited would find the engine
      // re-parented, and its own parent check would say mismatch.
      const lane = state.isLaneMarked && (state.laneVerdict === 'match' || state.laneVerdict === 'mismatch') ? ['--lane', state.laneVerdict] : []
      const child = $.process.spawn({ argv: [`${$.plugin.root}/skills/sminos/scripts/sminos`, 'bridge', '--session', session, ...lane] })
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
      // A child this module stopped (`stopChild`: a /clear, going off, a
      // retirement) reports no exit: the engine settles the result with
      // nothing, where its types say it rejects.
      const ended = await child.result.catch(() => undefined)
      $.ui.log(ended ? `bridge: the child ended (${ended.signal ?? ended.code})` : 'bridge: the child was stopped', { to: 'debug' })
    } catch (error) {
      $.ui.log(`bridge: the child failed: ${message(error)}`, { to: 'debug' })
    }
    const ran = (await $.clock.now()) - (await startedAt)
    if (generation !== state.generation) {
      return
    }
    state.socket = undefined
    state.nonce = undefined
    state.child = undefined
    if (ran >= STABLE_MS) {
      state.respawnMs = RESPAWN_FIRST_MS
    }
    const delay = state.respawnMs
    state.respawnMs = delay < RESPAWN_STEP_MS ? RESPAWN_STEP_MS : Math.min(delay * 2, RESPAWN_MAX_MS)
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
    forgetAgents()
    forgetLive()
  }
  state.isEnding = false
  state.queue = []
  state.catalog = undefined
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
        state.queue.push(...resyncEvents())
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
  await state.refreshCatalog?.().catch((error: unknown) => $.ui.log(`bridge: catalog refresh failed: ${message(error)}`, { to: 'debug' }))
}

/**
 * Which secrets guard is loaded now: devcloud's when its marker is live, else
 * cua's copy when the user settings enable cua. The same reads appeal makes,
 * of another plugin's state and of the user settings.
 */
async function loadedGuard($: EngineInterface): Promise<Guard | undefined> {
  if (isLiveMarker(await $.state.get({ plugin: 'devcloud', key: 'secrets-guard' }))) {
    return 'devcloud'
  }
  return isCuaEnabled(await $.settings.read({ source: 'user' })) ? 'cua' : undefined
}

/**
 * The bridge's place, judged again from what settled beneath one of its hooks
 * (bridge-place.tsx); `transitionsAt` is how many times it had turned off or
 * on when that dispatch began. Answers `off` when this dispatch read the
 * bridge inside a guard: what it would post is its own to drop.
 *
 * - The first `guarded` or `unguarded` settles the place as safe and posts
 *   the tool events that waited for it.
 * - `off` turns the bridge off, unless the dispatch began before the last
 *   transition: its chain may no longer stand, and the next dispatch decides.
 * - An off bridge turns back on only at `guarded`, read by a dispatch that
 *   began after the off: a guard seen loaded and beneath, never the reads'
 *   "no guard" alone.
 * - A dispatch that cannot tell (a trace cut short, a read that failed)
 *   changes nothing; a read that failed is said once as a toast, since a
 *   barrier that never lifts would otherwise be seen only in the debug log.
 */
async function judgePlace(
  $: EngineInterface,
  beneath: { readonly trace: readonly { readonly plugin: string }[]; readonly origin: { readonly plugin: string } },
  transitionsAt: number,
): Promise<'off' | undefined> {
  if (state.post === undefined) {
    return undefined
  }
  let verdict: Verdict | undefined
  try {
    verdict = await verdictOf(beneath.trace, beneath.origin.plugin, () => loadedGuard($))
  } catch (error) {
    const why = `bridge: its place among the secrets guards was not read: ${message(error)}`
    $.ui.log(why, { to: 'debug' })
    if (!state.isUnreadSaid) {
      state.isUnreadSaid = true
      $.ui.toast(`sminos: the bridge cannot read which secrets guard is loaded, so it cannot check its place: ${message(error)}`)
    }
    return undefined
  }
  if (state.post === undefined || verdict === undefined) {
    return undefined
  }
  const isCurrent = transitionsAt === state.transitions
  if (verdict === 'off') {
    if (isCurrent && state.place !== 'off') {
      turnOff($)
    }
    return 'off'
  }
  if (state.place === undefined) {
    state.place = 'safe'
    pump()
  } else if (state.place === 'off' && verdict === 'guarded' && isCurrent) {
    turnOn($)
  }
  return undefined
}

/**
 * The bridge found a guard outside it. What is queued is dropped, the child is
 * stopped, and the permissions it raised are withdrawn (their inputs came
 * through the guard; a question's never did); then the line says why, once, as a
 * toast and in the debug log. While off, nothing is queued or raised, and no
 * child is started (startChild).
 */
function turnOff($: EngineInterface) {
  // Off before it is said, so nothing the saying does can leave it running.
  state.place = 'off'
  state.transitions++
  state.queue = []
  stopChild()
  // A question's input never came through a guard: its dialog settles as it
  // would (its record, or the ask's note), and with it an async ask answered
  // through that dialog.
  for (const r of [...state.requests.values()]) {
    if (!r.isAsync && !r.isQuestion) {
      settle(r, 'withdrawn', 'bridge')
    }
  }
  $.ui.log(OFF_LINE, { to: 'debug' })
  $.ui.toast(OFF_LINE)
}

/**
 * The bridge is outside every guard again: a new child for the session, as a
 * reload starts one, whose hello names a nonce of its own (so an older
 * instance's posts are turned away) and opens with a resync of the live state
 * kept while off.
 */
function turnOn($: EngineInterface) {
  state.place = 'safe'
  state.transitions++
  $.ui.log(ON_LINE, { to: 'debug' })
  $.ui.toast(ON_LINE)
  if (state.session !== undefined) {
    state.restart?.(state.session)
  }
}

export async function bridgeStart($: EngineInterface, e: SessionStartInput) {
  // derive's headless fork of a session is never a member, and needs no bridge.
  if ((await $.env.get('SMNS_INTERNAL')) !== undefined) {
    return
  }
  // MAWS's lane B marker (O12 M3), read before anything is raised: until the
  // child's verdict on the parent check, the marker alone holds the bridge to
  // observing; a reload takes the verdict this process already has.
  state.isLaneMarked = (await $.env.get('MAWS_LANE')) === 'B'
  if (state.isLaneMarked && state.laneVerdict === undefined) {
    const kept = await $.state.get(LANE).then(
      (read) => read.value,
      () => undefined,
    )
    if (kept === 'match' || kept === 'mismatch') {
      state.laneVerdict = kept
    }
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
  state.isTurnStillUnknown = isTurnStillUnknown
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
  const version = await $.session.version()
  state.info = {
    cwd: e.cwd,
    surface: e.surface,
    isInteractive: e.isInteractive,
    model: await $.session.model(),
    version: version.version,
  }
  // What this module can do, said in every resync, so the child answers it at once.
  state.capabilities = await capabilitiesOf($, engineOf(version))
  // The initial catalog is assembled before the first child starts, so bind
  // it now. Later refreshes follow the binding, never merely the engine id.
  state.session ??= await $.session.id()
  // Serialize refreshes so a slower older list never replaces a newer one.
  let refresh = Promise.resolve()
  state.refreshCatalog = () => {
    // Capture before joining the queue: a predecessor's pending read cannot
    // become a successor's merely because it starts after the switch.
    const owner = { session: state.session, generation: state.generation }
    const next = refresh.then(async () => {
      if (!await catalogStillOwned($, owner)) {
        throw new Error(CATALOG_MOVED)
      }
      const catalog = await catalogNow($, engineOf(version))
      if (!await catalogStillOwned($, owner)) {
        throw new Error(CATALOG_MOVED)
      }
      if (catalog.fingerprint !== state.catalog?.fingerprint) {
        state.catalog = catalog
        emit({ type: 'catalog', ...catalog })
      }
      return catalog
    })
    refresh = next.then(() => undefined, () => undefined)
    return next
  }
  await state.refreshCatalog().catch((error: unknown) => $.ui.log(`bridge: catalog refresh failed: ${message(error)}`, { to: 'debug' }))
  // The agents running already, or over, learned before the first hello: its resync carries them.
  await refreshAgents()
  // So do the async asks open already, which the ask mod told of before
  // this bridge took notes: a resumed session's, read back from its
  // transcript in the SessionStart hooks, which the engine runs while this
  // start still waits on the plugin's tool registrations (live, 2.1.303,
  // tests/mods/live-ask-resume-check.py); a reloaded module's, taken up from
  // the last.
  for (const ask of asyncAsks().filter((candidate) => candidate.status === 'open')) {
    onAskNote({ kind: 'open', id: ask.id, questions: ask.questions })
  }
  // A side question a module before this one started, whose fork the reload
  // aborted: its end goes to the first child, after the resync.
  await endOrphanedSideQuestions($)
  // The desk's uploads a module before this one held: reconciled, their
  // unsaid states said to the first child, a pending one's wake armed again.
  await mediaLoaded($)
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

/**
 * A result's text as the desk draws it. Core sets `text` (the record as the
 * model reads it); a hook's own `{ result }` has none, and the record it
 * returns is the only form the bridge may post. That covers any hook's own
 * answer: the secrets guard's scrubbed record (with the bridge outside the
 * guard, where prependPlugins seats it and judgePlace holds it, core's text,
 * which holds the values, never comes up) and the tools plugins register
 * (this plugin's ask, doperpowers' compact and appeal). The record is drawn as it
 * is: a string whole, an array of content blocks as its text blocks joined
 * (an image's data is not text), any other record as JSON.
 */
function shownText(result: { result?: unknown; text?: unknown }): string | undefined {
  if (typeof result.text === 'string') {
    return result.text
  }
  if (typeof result.result === 'string') {
    return result.result
  }
  const record = result.result
  if (Array.isArray(record) && record.every((b) => typeof b === 'object' && b !== null && typeof (b as { type?: unknown }).type === 'string')) {
    return record.flatMap((b: { type: string; text?: unknown }) => (b.type === 'text' && typeof b.text === 'string' ? [b.text] : [])).join('\n')
  }
  try {
    return JSON.stringify(record, null, 2)
  } catch {
    return undefined
  }
}

/** A tool call's own arguments, every string in them held to TEXT_CAP. */
function toolInput(e: Record<string, unknown>): { value: unknown; cut: boolean } {
  return capped(Object.fromEntries(Object.entries(e).filter(([k]) => !RESERVED.has(k))))
}

/**
 * Registered first in register.tsx, so its hooks are the outermost of the
 * plugin's, and the plugin sits outside doperpowers' and every user-tier
 * plugin's (the owner's prependPlugins): what they report is what the session
 * showed and recorded. Its `tool.call` and `session.append` hooks check that
 * place on every dispatch (judgePlace). Each event is taken with a matcher that matches every
 * input, since the engine admits one unmatched registration per event per
 * module, which a mod beside it may need.
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
      forgetAgents()
      forgetLive()
      awaitNextSession()
    }
    return next(e)
  })

  on('turn.start', { turnId: /^/ }, ($, e, next) => {
    if (e.agentId === undefined) {
      state.mainTurn = e.turnId
      state.isTurnUnknown = false
      mediaTurnStarted()
      if (state.deliveredRows.length > 0) {
        void recheckDeliveries($, e.turnId)
      }
    }
    state.loopTurns.set(loopKey(e.agentId), e.turnId)
    // A loop whose spawn the bridge did not see (a forked skill): the list names it.
    if (e.agentId !== undefined && !state.agents.has(e.agentId)) {
      claimAgent(e.agentId)
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
      mediaTurnEnded($)
    }
    return result
  })

  // Every model request of the main loop and of every subagent: each chunk
  // as the engine streamed it, tagged with its message (turn, agent, step) and
  // its index there; the engine's own opaque items are left out. A main-loop
  // step with a desk upload pending is the bridge's own: it claims one and
  // streams its Read instead of a request (bridge-media.tsx), and its chunks go
  // on the stream as any step's do.
  on('turn.step', { turnId: /^/ }, async function* ($, e, next) {
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
    // Only a step with an upload pending waits on anything here. An observer
    // claims none, and rewrites no model or effort: those are MAWS's.
    const isControlled = isMain && !isObserver()
    const synthetic = isControlled && state.media.some((a) => a.state === 'pending')
      ? await claimMedia($, e).catch((error: unknown) => {
          $.ui.log(`bridge: no upload claimed: ${message(error)}`, { to: 'debug' })
          return undefined
        })
      : undefined
    // The model chosen through the bridge is the main loop's: a subagent runs
    // on what its definition or its caller chose.
    const o = isControlled ? state.override : undefined
    const input = o === undefined ? e : { ...e, ...(o.model !== null && { model: o.model }), ...(o.effort !== null && { effort: o.effort }) }
    if (isShown) {
      emit({ type: 'step', phase: 'start', ...tag, model: input.model, effort: input.effort ?? null, messageCount: e.messageCount })
    }
    if (isMain) {
      state.steps++
    }
    // Only a step that makes a request reads what was appended before it.
    if (isMain && synthetic === undefined) {
      // A request after the turn's first carries every row of its turn
      // appended before it. The first carries the conversation as the turn
      // began: a row appended between turn.start and it is not in it (live,
      // 2.1.302), so that row waits for the second request, or the wake.
      for (const s of state.steers) {
        if (e.index > 0 && s.isAppended && s.turnId === e.turnId) {
          s.isRead = true
        }
      }
      // A wake's rows were in before it was given: any later request carries
      // them, but the first of a turn that was already running.
      for (const w of state.wakes) {
        if (e.index > 0 || e.turnId !== w.turnAt) {
          w.isRead = true
        }
      }
      mediaPassedOn($)
    }
    let chunkIndex = 0
    let stopReason: unknown = null
    let usage: unknown = null
    try {
      const stream = synthetic ?? next(input)
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
    const transitionsAt = state.transitions
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
      shown: input,
      ...(base.toolUseId !== null && { toolUseId: base.toolUseId }),
      ...(e.tool === ASK_TOOL && { question: first }),
    })
    let resultText: string | undefined
    try {
      const result = await next(e)
      // Where the bridge stands, judged before anything of the result is
      // posted: a call that read the bridge inside a guard posts no result.
      const isInside = (await judgePlace($, next, transitionsAt)) === 'off'
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
      // An Agent call while the desk stops an agent: the call the stop ended
      // goes back to its loop with the stop's note in (bridge-agent-ops.tsx).
      if (AGENT_TOOLS.has(e.tool)) {
        await forNotes($, [...state.agentStops])
      }
      const shown = result.deny === undefined ? shownText(result) : undefined
      const text = capped(shown)
      const denied = capped(result.deny)
      if (isDialog || isInside) {
        return result
      }
      emit({
        type: 'tool',
        phase: 'result',
        ...base,
        isError: result.isError === true,
        ...(result.deny !== undefined && { denied: denied.value }),
        ...(shown !== undefined && { text: text.value }),
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
  // no call, so the check's id is kept for it, with the call as this
  // module's tool.call hook saw it (it runs on, beneath, until the check).
  on('tool.check', { tool: /^/ }, async (_, e, next) => {
    const verdict = await next(e)
    if (verdict.decision === 'ask' && typeof e.tool_use_id === 'string' && e.tool_use_id !== '' && state.post !== undefined) {
      const shown = shownCall(e.tool_use_id)
      state.checks.push({ toolUseId: e.tool_use_id, tool: e.tool, agentId: e.agentId ?? null, input: e.input, ...(shown !== undefined && { shown }) })
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
  //
  // A permission is raised with its call as this module's tool.call hook saw
  // it. The engine's check and this hook's input come after every tool.call
  // hook beneath, where a secrets guard restores its handles to the values
  // (devcloud's, or cua's copy, beneath the bridge where it must sit); that
  // form stays on this machine, since an allow hands an input back to the
  // engine alone (a plan's, a question's: engineDecision). A
  // permission for a call this module did not see is the terminal's alone, as
  // is one before the bridge knows its place: the call it saw may already
  // hold what a guard outside it restored. While the bridge is off, every
  // prompt is the terminal's, a question too (no child serves an answer). A
  // question is otherwise raised as the
  // engine gave it: the ask mod widens its dialog's beneath this module, and
  // no guard restores into one.
  //
  // The engine's suggestions (a rule, a directory) are made from its own
  // input, after those hooks: a Bash rule can carry the whole restored
  // command. They are raised only when that input is exactly the call this
  // module saw (claimCheck's `isSeen`), so nothing beneath restored
  // anything, and only within the bound the hub admits (boundedSuggestions).
  on('classic.PermissionRequest', { hook_event_name: 'PermissionRequest' }, async ($, e, next) => {
    // An observer raises nothing: MAWS answers its session's prompts
    // (--permission-prompt-tool stdio), and a desk card would be one it
    // cannot.
    if (state.post === undefined || isObserver()) {
      return next(e)
    }
    const agentId = e.agent_id ?? null
    const claimed = claimCheck(e.tool_name, agentId, e.tool_input)
    if (claimed?.isDecided) {
      return next(e)
    }
    const isQuestion = e.tool_name === 'AskUserQuestion'
    const input = isQuestion ? capped(e.tool_input) : claimed?.shown
    if (input === undefined) {
      state.log?.(`bridge: a ${e.tool_name} permission for a call this module did not see is left to the terminal`)
      return next(e)
    }
    if (state.place === 'off' || (!isQuestion && state.place === undefined)) {
      state.log?.(`bridge: a ${e.tool_name} ${isQuestion ? 'question' : 'permission'} is left to the terminal: the bridge ${state.place === 'off' ? 'is off' : 'does not know its place among the secrets guards yet'}`)
      return next(e)
    }
    const id = claimed?.toolUseId ?? `request-${Date.now().toString(36)}-${++state.minted}`
    const transitionsAt = state.transitions
    const beneath = await next(e)
    const now = await $.clock.now()
    // Decided after the last await, so a record that came meanwhile is seen:
    // a call already decided is never raised. Nor is one the bridge went off
    // (or off and back on) under while the hooks beneath ran: going off
    // withdraws only what is raised already, and a dispatch that began
    // before the last transition changes no state.
    if (beneath.decision !== undefined || state.records.has(id) || state.isEnding) {
      return beneath
    }
    if (state.transitions !== transitionsAt) {
      // Read anew: the place may have moved during the awaits, which the narrowing above cannot see.
      const place = state.place as Place | undefined
      state.log?.(`bridge: a ${e.tool_name} ${isQuestion ? 'question' : 'permission'} is left to the terminal: the bridge turned ${place === 'off' ? 'off' : 'off and on'} while the hooks beneath it ran`)
      return beneath
    }
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
      isQuestion,
      t: now,
      turnId: state.loopTurns.get(loopKey(agentId)),
      isAborted: false,
      transcript: typeof e.transcript_path === 'string' && e.transcript_path !== '' ? e.transcript_path : undefined,
    }
    const suggestions = !isQuestion && claimed?.isSeen === true ? boundedSuggestions(e.permission_suggestions) : undefined
    if (suggestions !== undefined) {
      r.suggestions = suggestions
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
  // main-loop row that may hold a message to the host or an answer to its
  // question. A row refused beneath is never written, and never named. Each
  // row, refused or kept, then says again where the bridge stands: after its
  // notice, so the guard reads never come between a row's write and its
  // notice (DX5's notice order). That costs nothing: a guard scrubs a row
  // before its own `next`, so a guard outside the bridge has scrubbed it.
  on('session.append', { door: /^/ }, async ($, e, next) => {
    const transitionsAt = state.transitions
    const isLive = state.post !== undefined
    const agentId = e.agentId ?? null
    // A background agent the desk stopped: its task notification, which may
    // start its parent's next request, waits for the stop's note
    // (bridge-agent-ops.tsx). The queue's record is no row of a conversation.
    if (e.door !== 'queue') {
      await forNotes($, notifiedStops(e.message))
    }
    const stored = await next(e)
    // A desk upload's Read: its result moves the attachment on (bridge-media.tsx).
    observeMediaResult($, e.door, e.message, agentId)
    if (isLive && stored.deny === undefined) {
      announceRow(e.door, e.door === 'note' ? stored.message : e.message, stored.uuid, agentId)
      observeRow(e.door, e.message, stored.uuid)
      if (agentId === null) {
        exportRow(e.door, stored.message, stored.uuid, e.origin)
        enteredRow(e.door, stored.message, stored.uuid, e.origin)
        // As the engine wrote it: a hook beneath may empty a command's rows (doperpowers' reload).
        commandRow(e.door, e.message, stored.uuid)
        if (e.door === 'command' && /<command-name>\/(reload-plugins|reload-skills|mcp)<\/command-name>/.test(JSON.stringify(e.message))) {
          void state.refreshCatalog?.().catch((error: unknown) => $.ui.log(`bridge: catalog refresh failed: ${message(error)}`, { to: 'debug' }))
        }
      }
    }
    await judgePlace($, next, transitionsAt)
    return stored
  }).catch((_, e, next) => next(e))

  // Every compaction this plugin did not start: the person's /compact, a
  // command run, the engine's own, and doperpowers' compact tool, whose rows
  // reach the bridge only through this hook (filter it by origin and they are
  // never named). This plugin's own compaction passes no hook of its, so
  // runCompaction names its rows itself. One that stood writes its rows once
  // the hooks are through: named from the transcript. A precompute installs
  // nothing.
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
      claimAgent(result.agentId)
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
