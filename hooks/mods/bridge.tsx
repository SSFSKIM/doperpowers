import type { EngineInterface, HookStream, HttpResponse, On, PermissionRequestDecision, ProcessSpawnChunk, ProcessSpawnResult, SessionStartInput, Timer } from 'claude-code'

import { ASK_TOOL, answerAsync, answerRows, observeAsks } from './ask'
import type { AskNote, AskQuestion } from './ask'

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
 * `session.start` again, which spawns the next.
 *
 * The mod keeps the session's live state itself (open turns, every message
 * still streaming with its text and last chunk index, the subagents), so
 * whenever the child's copy may be wrong (a post was lost, a new child said
 * hello) the next post opens with a `resync` that replaces it.
 *
 * Control (DC2 M2): `steer` appends a user row the loop reads at its next
 * request; `interrupt` aborts the main turn and stops each Bash call the abort
 * moved to the background; `model` rewrites the main loop's requests;
 * `compact` runs between turns; `deliver` submits a log event as the human's
 * words, once per key. What must outlive a module reload (the model chosen,
 * the keys delivered) the child keeps on disk: its hello hands it back.
 *
 * Requests from outside (DC2 M3): a permission prompt or a question the
 * engine puts to its dialog is `raised`, and its `classic.PermissionRequest`
 * hook long-polls the child for a decision while the terminal's dialog stays
 * up; an async question of the ask mod is raised as it opens and answered
 * through it. Each ends with one `settled` naming the side whose answer the
 * engine used, read from what the engine did: its mark of a hook's decision
 * beside the call's result, the result itself, the dialog closing in the
 * terminal (the child watches the session record), the turn ending.
 *
 * Streaming is per content block: each response row the engine writes is
 * paired with its block (`block-row`), which settles the block.
 */

export const HEARTBEAT_MS = 5_000
/** The longest string an event carries; the rest is in the transcript. */
export const TEXT_CAP = 65_536
const BATCH_MAX = 500
const QUEUE_MAX = 10_000
const RESPAWN_FIRST_MS = 1_000
const RESPAWN_MAX_MS = 60_000
/** A child that lived this long ended for a reason of its own: start again quickly. */
const STABLE_MS = 30_000
/** After a /clear: how often, and how many times, the new session's id is looked for. */
export const CLEAR_POLL_MS = 100
const CLEAR_POLL_TRIES = 50
/** How many polls the old session's last events may take to reach its child before it is stopped. */
const DRAIN_TRIES = 10
/** After a post that failed, the next waits this long. */
const RETRY_MS = 500
/**
 * The prompt that wakes a session whose turn answered before any model request
 * read a steer: the steer's row is already in the conversation, so this names
 * it rather than repeating it.
 */
export const STEER_WAKE = 'I added a note to the conversation while you were finishing your answer. Read it and act on it.'
/** After an abort, how long the Bash calls it ended have to report where they went. */
export const INTERRUPT_WAIT_MS = 3_000
const EFFORTS = ['low', 'medium', 'high', 'xhigh', 'max'] as const
type Effort = (typeof EFFORTS)[number]
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
/**
 * After the terminal answered, or a decision went to the engine, how long the
 * call has to show what the engine did (a refusal ends it at once) before the
 * running call is read as allowed.
 */
export const SETTLE_GRACE_MS = 1_500
/** The child holds a poll this long at most, under `$.http.fetch`'s 30-second bound. */
const POLL_HOLD_MS = 20_000
/** With no child answering (one restarting), the hook waits this long, so many times, out of its own budget. */
const POLL_RETRY_MS = 250
const POLL_RETRIES = 16
/** Tool checks put to the dialog, kept for their PermissionRequest; recent settlements, for a late subscriber. */
const CHECKS_KEPT = 50
const SETTLED_KEPT = 100
/** A deny that carries no words of its own. */
const DENIED = 'The human denied this request.'
/** The engine's result for a call the terminal's dialog refused. */
const REFUSAL = "The user doesn't want to proceed with this tool use."
/** A response row's block, as its chunks name its kind. */
const ROW_KIND: Record<string, string> = { text: 'text', thinking: 'thinking', redacted_thinking: 'thinking', tool_use: 'tool' }
/** A chunk's block kind: an `input` chunk is a tool call's arguments. */
const BLOCK_KIND: Record<string, string> = { text: 'text', thinking: 'thinking', tool: 'tool', input: 'tool' }

type BridgeEvent = Record<string, unknown> & { type: string }
type Command = Record<string, unknown> & { id: string; op: string }
/** A command's answer: the `result` event's fields. */
type Answer = { ok: true; result: Record<string, unknown> } | { ok: false; error: string }
/** The model and effort chosen for this session through the bridge; null keeps the session's own. */
type Override = { model: string | null; effort: Effort | null }
/**
 * A tool call running now: `owner` is the main turn it belongs to (a main-loop
 * call's turn, or the turn a foreground subagent it runs in was spawned in);
 * `done` resolves with its result's text once it settles.
 */
type Call = { tool: string; owner: string | undefined; done: Promise<string | undefined>; settle: (text: string | undefined) => void }
/**
 * A steer, bound to the main turn it was given in before its row is appended.
 * `isAppended`: the row is in; `isRead`: a main-loop request began after it;
 * `ended`: how its turn ended, while some append of that turn is still pending.
 */
type Steer = { turnId: string; isAppended: boolean; isRead: boolean; ended?: string }
/** A content block still streaming: its text (a tool call's arguments as JSON), and its last chunk's index. */
type Block = { index: number; kind: string; text: string; upTo: number; id?: string; name?: string }
/**
 * A message still streaming, as the child's snapshot carries it (DX4): its
 * blocks without a row yet, the ones a row settled, and `upTo`, its last chunk.
 */
type Streaming = { turnId: string; agentId: string | null; step: number; model: string; upTo: number; blocks: Map<number, Block>; settled: Set<number> }
/** A loop's latest model request: where its blocks started, in order, and which a row has named. */
type StepBlocks = { turnId: string; agentId: string | null; step: number; starts: { index: number; kind: string; id?: string }[]; named: Set<number> }
/** What a client decided, as the child hands it over. */
type Decision = { behavior: 'allow' | 'deny'; message?: string; updatedInput?: { answers?: Record<string, string> } }
type Outcome = 'allow' | 'deny' | 'answered' | 'withdrawn'
/**
 * A request from outside the terminal, raised until settled: a permission
 * prompt or a question in a dialog (under its call's tool-use id), or an
 * async question of the ask mod's.
 */
type Request = {
  id: string
  tool: string
  /** The tool's input as `raised` carries it (capped), and as the engine gave it. */
  input: unknown
  rawInput: unknown
  isTruncated: boolean
  agentId: string | null
  /** A background subagent's window: after it, the prompt is the terminal's. */
  deadline?: number
  isAsync: boolean
  isQuestion: boolean
  t: number
  /** The turn of its loop it was raised in: that turn's end withdraws it. */
  turnId?: string
  decided?: { decision: Decision; by: string }
  /** The terminal answered it: the child saw the dialog close. */
  isClosed: boolean
  /** The engine kept a hook's decision in its loop after a decision went to it. */
  isMarked: boolean
  /** The bridge's interrupt aborted its turn. */
  isAborted: boolean
}

type BridgeState = {
  /**
   * The calls that outlive a hook, made in session.start: its `$` lives as
   * long as the child's loop does, so posts, timers and restarts run on it.
   */
  post?: (socketPath: string, body: string) => Promise<HttpResponse>
  /** A GET on the child's endpoint, outside any hook (a request watched after its hook returned). */
  get?: (socketPath: string, path: string) => Promise<HttpResponse>
  log?: (text: string) => void
  after?: (ms: number, fn: () => void) => void
  readId?: () => Promise<string>
  /** Stops the child and starts one for this session. */
  restart?: (session: string) => void
  /** What the session start said, sent to each child once it says hello. */
  info?: Record<string, unknown>
  /** The session the child serves, the socket it named, and the child itself. */
  session?: string
  socket?: string
  child?: HookStream<ProcessSpawnChunk, ProcessSpawnResult>
  /** Bumped whenever a child is started or stopped on purpose; a loop of an older one does nothing more. */
  generation: number
  respawnMs: number
  heartbeat?: Timer
  queue: BridgeEvent[]
  isPosting: boolean
  /** The poster loop (started in session.start) and, while it sleeps, what wakes it. */
  isPosterRunning: boolean
  wake?: () => void
  /** A post failed: the next waits for RETRY_MS. */
  isWaiting: boolean
  /**
   * Between a /clear's session.end and the new session's child: nothing is
   * sent (the old child must not get the new session's events), and the live
   * state they build reaches the new child as its first resync.
   */
  isEnding: boolean
  /** The session's live state, the source of every resync. */
  turns: Map<string, Record<string, unknown>>
  messages: Map<string, Streaming>
  agents: Map<string, Record<string, unknown>>
  mainTurn?: string
  /** Main-loop model requests streaming now. */
  steps: number
  /** Tool calls running now, by call. */
  calls: Map<string, Call>
  toolCalls: number
  /** The model and effort chosen through the bridge, if any. */
  override?: Override
  /** Per writer, the highest seq of a log event submitted: delivery goes in seq order, so any key at or below it was. */
  delivered: Map<string, number>
  /** Whether what the child keeps (override, delivered) was taken from its hello: once per module. */
  isKeptLoaded: boolean
  /** Steers given in the main turn, and those whose turn ended before their row was in. */
  steers: Steer[]
  /** For each running foreground subagent, the main turn it belongs to (its tool calls are that turn's). */
  foreground: Map<string, string>
  /** A compaction asked for during the main turn, run when it ends. */
  compact?: { id: string; instructions?: string }
  /** Each loop's running turn (the main loop's under ''). */
  loopTurns: Map<string, string>
  /** Each loop's latest model request and where its blocks started, for pairing rows with blocks. */
  stepBlocks: Map<string, StepBlocks>
  /** Calls the engine's check put to the dialog, oldest first: a PermissionRequest takes its call's id from one. */
  checks: { toolUseId: string; tool: string; agentId: string | null; input: unknown }[]
  /** Requests raised and not yet settled, by id; and the last settlements, oldest first. */
  requests: Map<string, Request>
  settled: Record<string, unknown>[]
  /** Request ids minted for a prompt no check named. */
  minted: number
}

const fresh = (): BridgeState => ({
  loopTurns: new Map(),
  stepBlocks: new Map(),
  checks: [],
  requests: new Map(),
  settled: [],
  minted: 0,
  generation: 0,
  respawnMs: RESPAWN_FIRST_MS,
  queue: [],
  isPosting: false,
  isPosterRunning: false,
  isWaiting: false,
  isEnding: false,
  turns: new Map(),
  messages: new Map(),
  agents: new Map(),
  steps: 0,
  calls: new Map(),
  toolCalls: 0,
  delivered: new Map(),
  isKeptLoaded: false,
  steers: [],
  foreground: new Map(),
})

let state = fresh()

/** Forgets everything; for tests, which share this module. */
export function resetBridge() {
  state = fresh()
}

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

/** Cuts `pending + text` into whole lines, keeping the unfinished rest. */
export function splitLines(pending: string, text: string): { lines: string[]; rest: string } {
  const parts = (pending + text).split('\n')
  const rest = parts.pop() ?? ''
  return { lines: parts.filter((l) => l.trim() !== ''), rest }
}

/** Where the session stands, for a command's answer and the heartbeat. */
function turnState() {
  return { mainTurn: state.mainTurn ?? null, isStreaming: state.steps > 0, tools: [...state.calls.values()].map((c) => c.tool) }
}

/**
 * A value with every string in it, at any depth, held to TEXT_CAP; `cut`
 * says whether any was.
 */
export function capped(value: unknown): { value: unknown; cut: boolean } {
  if (typeof value === 'string') {
    return value.length > TEXT_CAP ? { value: value.slice(0, TEXT_CAP), cut: true } : { value, cut: false }
  }
  if (Array.isArray(value)) {
    const items = value.map(capped)
    return { value: items.map((i) => i.value), cut: items.some((i) => i.cut) }
  }
  if (typeof value === 'object' && value !== null) {
    const entries = Object.entries(value).map(([k, v]) => [k, capped(v)] as const)
    return { value: Object.fromEntries(entries.map(([k, c]) => [k, c.value])), cut: entries.some(([, c]) => c.cut) }
  }
  return { value, cut: false }
}

const messageKey = (turnId: unknown, agentId: unknown, step: unknown) => `${String(turnId)}|${String(agentId)}|${String(step)}`

/** The key of a loop: a subagent's id, '' for the main loop. */
const loopKey = (agentId: unknown) => (typeof agentId === 'string' ? agentId : '')

/** A chunk folded into its message's block, and the block's start noted for pairing its row. */
function trackChunk(e: BridgeEvent) {
  const chunkIndex = Number(e.chunkIndex)
  const c = e.chunk as { kind?: string; index?: number; text?: string; json?: string; id?: string; name?: string }
  const kind = BLOCK_KIND[c.kind ?? '']
  const s = state.stepBlocks.get(loopKey(e.agentId))
  if (s !== undefined && s.turnId === e.turnId && s.step === e.step && typeof c.index === 'number' && kind !== undefined && !s.starts.some((b) => b.index === c.index)) {
    s.starts.push({ index: c.index, kind, ...(c.kind === 'tool' && { id: c.id }) })
  }
  const m = state.messages.get(messageKey(e.turnId, e.agentId, e.step))
  if (m === undefined) {
    return
  }
  m.upTo = chunkIndex
  if (typeof c.index !== 'number' || kind === undefined || m.settled.has(c.index)) {
    return
  }
  let b = m.blocks.get(c.index)
  if (b === undefined) {
    b = { index: c.index, kind, text: '', upTo: -1 }
    m.blocks.set(c.index, b)
  }
  if (c.kind === 'text' || c.kind === 'thinking') {
    b.text += c.text ?? ''
  } else if (c.kind === 'tool') {
    b.id = c.id
    b.name = c.name
  } else {
    b.text += c.json ?? ''
  }
  b.upTo = chunkIndex
}

/** Folds an event into the session's live state. */
function track(e: BridgeEvent) {
  if (e.type === 'chunk') {
    trackChunk(e)
  } else if (e.type === 'block-row') {
    const m = state.messages.get(messageKey(e.turnId, e.agentId, e.step))
    if (m !== undefined && typeof e.index === 'number') {
      m.blocks.delete(e.index)
      m.settled.add(e.index)
    }
  } else if (e.type === 'step' && e.phase === 'start') {
    const m: Streaming = { turnId: String(e.turnId), agentId: (e.agentId as string | null) ?? null, step: Number(e.step), model: String(e.model), upTo: -1, blocks: new Map(), settled: new Set() }
    state.messages.set(messageKey(m.turnId, m.agentId, m.step), m)
    state.stepBlocks.set(loopKey(m.agentId), { turnId: m.turnId, agentId: m.agentId, step: m.step, starts: [], named: new Set() })
  } else if (e.type === 'step' && e.phase === 'end') {
    state.messages.delete(messageKey(e.turnId, e.agentId, e.step))
  } else if (e.type === 'turn' && e.phase === 'start') {
    state.turns.set(String(e.turnId), { turnId: e.turnId, agentId: e.agentId, t: e.t })
  } else if (e.type === 'turn' && e.phase === 'complete') {
    state.turns.delete(String(e.turnId))
    for (const [k, m] of state.messages) {
      if (m.turnId === e.turnId) {
        state.messages.delete(k)
      }
    }
  } else if (e.type === 'agent') {
    const { type: _type, phase, t: _t, ...fields } = e
    state.agents.set(String(e.agentId), { ...state.agents.get(String(e.agentId)), ...fields, running: phase !== 'stop' })
    if (phase === 'stop') {
      state.stepBlocks.delete(loopKey(e.agentId))
    }
  }
}

/** A streaming message as the snapshot shows it: the blocks without a row yet, by index. */
const shownMessage = (m: Streaming) => ({
  turnId: m.turnId,
  agentId: m.agentId,
  step: m.step,
  model: m.model,
  upTo: m.upTo,
  blocks: [...m.blocks.values()].sort((a, b) => a.index - b.index).map((b) => ({ ...b })),
})

/** A pending request as `raised` and the snapshot carry it. */
const raisedFields = (r: Request) => ({
  request: r.id,
  tool: r.tool,
  input: r.input,
  agentId: r.agentId,
  ...(r.deadline !== undefined && { deadline: r.deadline }),
  ...(r.isAsync && { async: true }),
  ...(r.isTruncated && { truncated: true }),
})

/** The live state whole, and what the child keeps for this session: what it replaces its own with. */
function resyncEvent(): BridgeEvent {
  return {
    type: 'resync',
    turns: [...state.turns.values()],
    streaming: [...state.messages.values()].map(shownMessage),
    agents: [...state.agents.values()],
    pending: [...state.requests.values()].map((r) => ({ ...raisedFields(r), t: r.t })),
    settled: state.settled.map((s) => ({ ...s })),
    override: state.override ?? null,
    delivered: Object.fromEntries(state.delivered),
    t: Date.now(),
  }
}

/**
 * Forgets the live state: the session after a /clear starts with none, and
 * no delivery to the old id is the new one's. The model chosen stays, as the
 * terminal's own choice of model does across a /clear.
 */
function forgetLive() {
  state.turns.clear()
  state.messages.clear()
  state.agents.clear()
  state.delivered.clear()
  state.loopTurns.clear()
  state.stepBlocks.clear()
  state.checks = []
  state.requests.clear()
  state.settled = []
}

const isEffort = (value: unknown): value is Effort => EFFORTS.includes(value as Effort)

/** What the child kept for the session (its hello's `kept`), taken by a module that holds none yet. */
function adoptKept(kept: unknown) {
  if (typeof kept !== 'object' || kept === null) {
    return
  }
  const { override, delivered } = kept as { override?: unknown; delivered?: unknown }
  if (typeof override === 'object' && override !== null) {
    const { model, effort } = override as Record<string, unknown>
    const next: Override = { model: typeof model === 'string' ? model : null, effort: isEffort(effort) ? effort : null }
    state.override = next.model === null && next.effort === null ? undefined : next
  }
  if (typeof delivered === 'object' && delivered !== null) {
    for (const [writer, seq] of Object.entries(delivered)) {
      if (Number.isInteger(seq) && (seq as number) > (state.delivered.get(writer) ?? 0)) {
        state.delivered.set(writer, seq as number)
      }
    }
  }
}

/**
 * Events that reached no child: counted in a gap, and the queue replaced by
 * that gap and a resync of the state as it stands now, which covers every
 * event lost and every one queued behind them.
 */
function lose(events: BridgeEvent[]) {
  const dropped = events.reduce((n, e) => n + (e.type === 'gap' ? Number(e.dropped) : e.type === 'resync' ? 0 : 1), 0)
  state.queue = [{ type: 'gap', dropped, t: Date.now() }, resyncEvent()]
}

function emit(event: BridgeEvent) {
  // Nothing is kept for a session with no bridge (an internal fork, a start that failed).
  if (state.post === undefined) {
    return
  }
  const stamped = { ...event, t: Date.now() }
  track(stamped)
  if (state.isEnding) {
    return
  }
  state.queue.push(stamped)
  if (state.queue.length > QUEUE_MAX) {
    lose(state.queue)
  }
  pump()
}

/** Wakes the poster, which posts what is queued. */
function pump() {
  state.wake?.()
}

/**
 * The poster: posts what is queued, one request at a time, once a child has
 * said where, and sleeps until woken. It is started in session.start and
 * every post begins in it: a post begun inside another hook's dispatch is
 * aborted with that dispatch (live, 2.1.300: an Esc at a permission dialog,
 * or a turn the bridge aborted, failed the post carrying the call's result
 * with "The operation was aborted", and a command's answer with it).
 */
async function poster() {
  for (;;) {
    const { post, socket: socketPath } = state
    if (post === undefined || socketPath === undefined || state.isWaiting || state.queue.length === 0) {
      await new Promise<void>((resolve) => (state.wake = resolve))
      state.wake = undefined
      continue
    }
    const batch = state.queue.splice(0, BATCH_MAX)
    const generation = state.generation
    let failed = false
    state.isPosting = true
    const lost = (why: string) => {
      failed = true
      state.log?.(`bridge: ${batch.length} events not delivered: ${why}`)
      // A child replaced meanwhile gets its resync at its hello; one being
      // retired after a /clear gets nothing more.
      if (generation === state.generation && !state.isEnding) {
        lose([...batch, ...state.queue])
      }
    }
    await post(socketPath, JSON.stringify(batch)).then(
      (res) => {
        if (!res.ok) {
          lost(`status ${res.status}`)
        }
      },
      (error: unknown) => lost(message(error)),
    )
    state.isPosting = false
    if (failed && state.after !== undefined) {
      state.isWaiting = true
      state.after(RETRY_MS, () => {
        state.isWaiting = false
        pump()
      })
    }
  }
}

/** Answers one command line with a `result` event. M3 adds its ops here. */
async function runCommand($: EngineInterface, command: Command) {
  let answer: Answer
  try {
    answer = await commandAnswer($, command)
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
      return interrupt($)
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
 */
async function interrupt($: EngineInterface): Promise<Answer> {
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
  await $.turn.abort({ turnId })
  const bound = new Promise<undefined>((resolve) => void $.clock.after(INTERRUPT_WAIT_MS, () => resolve(undefined)))
  const texts = await Promise.all(ours.map((c) => Promise.race([c.done, bound])))
  const stopped: string[] = []
  const running: string[] = []
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
      stopped.push(task)
    } else {
      $.ui.log(`bridge: TaskStop ${task} failed: ${failure}`, { to: 'debug' })
      running.push(task)
    }
  }
  return { ok: true, result: { turnId, stopped, running } }
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
  const refused = (reason: string) => {
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

// Requests from outside the terminal.

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)

/** DX4's winner for who answered: the terminal; the CLI or the bridge itself (other); anyone else, a member on the web. */
const winnerOf = (by: string) => (by === 'terminal' ? 'terminal' : by === 'cli' || by === 'bridge' ? 'other' : 'web')

function raise(r: Request) {
  state.requests.set(r.id, r)
  emit({ type: 'raised', ...raisedFields(r) })
}

/** The one settlement of a request: the side whose answer the engine used, what it was, and who answered. */
function settle(r: Request, outcome: Outcome, by: string) {
  if (state.requests.get(r.id) !== r) {
    return
  }
  state.requests.delete(r.id)
  const settled = { request: r.id, winner: winnerOf(by), outcome, by }
  state.settled.push({ ...settled, t: Date.now() })
  if (state.settled.length > SETTLED_KEPT) {
    state.settled.shift()
  }
  emit({ type: 'settled', ...settled })
}

/** Whether a subagent runs in the background, itself or under an ancestor; one the bridge does not know of is taken to (its window is bounded). */
function isBackground(agentId: string): boolean {
  let at: string | null = agentId
  for (let depth = 0; at !== null && depth < 16; depth++) {
    const agent: Record<string, unknown> | undefined = state.agents.get(at)
    if (agent === undefined || agent.background === true) {
      return true
    }
    at = typeof agent.parentAgentId === 'string' ? agent.parentAgentId : null
  }
  return false
}

/**
 * The call a PermissionRequest is for: the hook's input names no call, so the
 * engine's check that put a call of that tool, in that loop, to the dialog
 * names it (the one with the same input first).
 */
function claimCheck(tool: string, agentId: string | null, input: unknown): string | undefined {
  const same = (c: BridgeState['checks'][number]) => c.tool === tool && c.agentId === agentId
  const text = JSON.stringify(input)
  const exact = state.checks.findIndex((c) => same(c) && JSON.stringify(c.input) === text)
  const at = exact >= 0 ? exact : state.checks.findIndex(same)
  return at < 0 ? undefined : state.checks.splice(at, 1)[0]?.toolUseId
}

/** The decision as the engine takes it: a question's allow carries the dialog's own questions with the answers. */
function engineDecision(r: Request, d: Decision): PermissionRequestDecision {
  if (d.behavior === 'deny') {
    return { behavior: 'deny', message: d.message ?? DENIED }
  }
  if (r.isQuestion) {
    return { behavior: 'allow', updatedInput: { ...(isRecord(r.rawInput) ? r.rawInput : {}), answers: d.updatedInput?.answers ?? {} } }
  }
  return { behavior: 'allow' }
}

/**
 * Polls the child for a decision while the dialog is up, in holds under the
 * fetch bound, until one is handed out, the terminal answered, the request
 * settled, or a background window's deadline passed. Past the deadline (or
 * with no child answering) the dialog is the terminal's, and the request's
 * end is watched from outside the hook.
 */
async function awaitDecision($: EngineInterface, r: Request, signal: AbortSignal): Promise<PermissionRequestDecision | undefined> {
  let retries = 0
  while (state.requests.get(r.id) === r && !signal.aborted) {
    const hold = r.deadline === undefined ? POLL_HOLD_MS : Math.min(POLL_HOLD_MS, r.deadline - (await $.clock.now()))
    if (hold <= 0) {
      break
    }
    const socketPath = state.socket
    let res: HttpResponse | undefined
    if (socketPath !== undefined) {
      res = await $.http.fetch(`http://bridge/requests/${encodeURIComponent(r.id)}/wait?ms=${hold}`, { socketPath }).catch(() => undefined)
    }
    if (res === undefined) {
      if (++retries > POLL_RETRIES) {
        break
      }
      await $.clock.sleep(POLL_RETRY_MS)
      continue
    }
    if (res.status === 200) {
      const handed = parsed(res.text)
      const decision = handed?.decision as Decision | undefined
      if (decision !== undefined && (decision.behavior === 'allow' || decision.behavior === 'deny') && typeof handed?.by === 'string') {
        r.decided = { decision, by: handed.by }
        graceFor(r)
        return engineDecision(r, decision)
      }
    } else if (res.status === 410) {
      if (parsed(res.text)?.reason === 'terminal') {
        terminalAnswered(r)
      }
      return undefined
    }
  }
  if (state.requests.get(r.id) === r) {
    watchRequest(r)
  }
  return undefined
}

const parsed = (text: string): Record<string, unknown> | undefined => {
  try {
    const value: unknown = JSON.parse(text)
    return isRecord(value) ? value : undefined
  } catch {
    return undefined
  }
}

/** A request whose hook stopped waiting: the child says when the terminal answers it (it hands out nothing here). */
function watchRequest(r: Request) {
  const round = () => {
    if (state.requests.get(r.id) !== r || r.isClosed || state.get === undefined) {
      return
    }
    const socketPath = state.socket
    if (socketPath === undefined) {
      state.after?.(1_000, round)
      return
    }
    state.get(socketPath, `/requests/${encodeURIComponent(r.id)}/wait?ms=${POLL_HOLD_MS}&watch=1`).then(
      (res) => {
        if (res.status !== 410) {
          round()
        } else if (parsed(res.text)?.reason === 'terminal') {
          terminalAnswered(r)
        }
      },
      () => state.after?.(1_000, round),
    )
  }
  round()
}

function terminalAnswered(r: Request) {
  r.isClosed = true
  graceFor(r)
}

/** Once the call has had its grace to show what the engine did, what it shows by running on. */
function graceFor(r: Request) {
  state.after?.(SETTLE_GRACE_MS, () => {
    if (state.requests.get(r.id) !== r) {
      return
    }
    const ran = r.isQuestion ? 'answered' : 'allow'
    if (r.isAborted) {
      settle(r, 'withdrawn', 'bridge')
    } else if (r.decided !== undefined) {
      // A deny the engine used ends the call at once; one still running was allowed in the terminal.
      settle(r, ran, r.decided.decision.behavior === 'deny' ? 'terminal' : r.decided.by)
    } else if (r.isClosed) {
      settle(r, ran, 'terminal')
    }
  })
}

/** Whether a question's result holds the answers a client decided. */
function sameAnswers(r: Request, text: string): boolean {
  const asked = isRecord(r.rawInput) && Array.isArray(r.rawInput.questions) ? (r.rawInput.questions as AskQuestion[]) : []
  const decided = r.decided?.decision.updatedInput?.answers ?? {}
  const rows = answerRows(asked, text)
  return rows.length === Object.keys(decided).length && rows.every(([question, answer]) => decided[question] === answer)
}

/**
 * A request's call ended with this result: whose answer the engine used. A
 * decision that went to the engine was used when the engine kept its mark
 * beside the result (a question: when the result holds its answers); else the
 * terminal answered, and the result says what (a refusal is its deny).
 */
function callEnded(toolUseId: string, result: { isError: boolean; text: string }) {
  const r = state.requests.get(toolUseId)
  if (r === undefined || r.isAsync) {
    return
  }
  if (r.isAborted) {
    settle(r, 'withdrawn', 'bridge')
    return
  }
  const outcome: Outcome = r.isQuestion ? (result.isError ? 'deny' : 'answered') : result.text.includes(REFUSAL) ? 'deny' : 'allow'
  const d = r.decided
  if (d !== undefined) {
    const decided: Outcome = d.decision.behavior === 'deny' ? 'deny' : r.isQuestion ? 'answered' : 'allow'
    const isUsed = r.isQuestion ? decided === outcome && (outcome !== 'answered' || sameAnswers(r, result.text)) : r.isMarked
    if (isUsed) {
      settle(r, decided, d.by)
      return
    }
  }
  settle(r, outcome, 'terminal')
}

/** A tool result's text: a string, or its text blocks joined. */
function resultText(content: unknown): string {
  if (typeof content === 'string') {
    return content
  }
  return Array.isArray(content) ? content.map((b) => (isRecord(b) && typeof b.text === 'string' ? b.text : '')).join('\n') : ''
}

/**
 * A row the session kept: a response row names its block (`block-row`); the
 * engine's mark of a hook's decision, and a call's result, settle requests.
 */
function observeRow(door: string, message: { name?: string; content?: unknown }, uuid: string, agentId: string | null) {
  const content = Array.isArray(message.content) ? message.content.filter(isRecord) : []
  if (door === 'response') {
    nameBlock(agentId, uuid, content[0])
  } else if (door === 'hook-context' && message.name === 'hook_permission_decision') {
    for (const r of state.requests.values()) {
      if (r.agentId === agentId && r.decided !== undefined) {
        r.isMarked = true
      }
    }
  } else if (door === 'tool-result') {
    for (const block of content) {
      if (block.type === 'tool_result' && typeof block.tool_use_id === 'string') {
        callEnded(block.tool_use_id, { isError: block.is_error === true, text: resultText(block.content) })
      }
    }
  }
}

/**
 * Pairs a response row with its block: by the row's block type and the order
 * the loop's latest request started its blocks (a tool call by its id), not
 * by the row's own position. A row whose block never streamed names none.
 */
function nameBlock(agentId: string | null, uuid: string, block: Record<string, unknown> | undefined) {
  const s = state.stepBlocks.get(loopKey(agentId))
  const kind = ROW_KIND[String(block?.type)]
  if (s === undefined || kind === undefined) {
    return
  }
  const open = s.starts.filter((b) => b.kind === kind && !s.named.has(b.index))
  const start = (kind === 'tool' ? open.find((b) => b.id === block?.id) : undefined) ?? open[0]
  if (start === undefined) {
    return
  }
  s.named.add(start.index)
  emit({ type: 'block-row', uuid, turnId: s.turnId, agentId: s.agentId, step: s.step, index: start.index })
}

/**
 * What the ask mod's asks do (its observer): an async question is raised as
 * it opens and settled as it is answered or forgotten; a dialog it raised
 * settling is its request's result.
 */
export function onAskNote(note: AskNote) {
  if (state.post === undefined) {
    return
  }
  if (note.kind === 'open') {
    if (!state.requests.has(note.id)) {
      const input = capped({ questions: note.questions })
      raise({ id: note.id, tool: ASK_TOOL, input: input.value, rawInput: { questions: note.questions }, isTruncated: input.cut, agentId: null, isAsync: true, isQuestion: true, t: Date.now(), isClosed: false, isMarked: false, isAborted: false })
    }
  } else if (note.kind === 'answered') {
    const r = state.requests.get(note.id)
    if (r?.isAsync) {
      settle(r, 'answered', note.by)
    }
  } else if (note.kind === 'forgotten') {
    for (const id of note.ids) {
      const r = state.requests.get(id)
      if (r?.isAsync) {
        settle(r, 'withdrawn', 'bridge')
      }
    }
  } else {
    callEnded(note.toolUseId, { isError: note.isError, text: note.text })
  }
}

/** An async question's answer from outside (the child relays a client's), handed to the ask mod, which delivers it. */
function answerFromOutside(command: Command): Answer {
  const { request, answers, by } = command
  if (typeof request !== 'string' || typeof by !== 'string' || !isRecord(answers) || !Object.values(answers).every((a) => typeof a === 'string')) {
    return { ok: false, error: 'answer needs request, answers (by question) and by' }
  }
  if (state.requests.get(request)?.isAsync !== true) {
    return { ok: false, error: `no async question ${request} is pending` }
  }
  const done = answerAsync(request, answers as Record<string, string>, by)
  return done.ok ? { ok: true, result: { answered: true } } : { ok: false, error: done.error }
}

/** The session ended: what it left pending is withdrawn. */
function withdrawAll() {
  for (const r of [...state.requests.values()]) {
    settle(r, 'withdrawn', 'bridge')
  }
}

/**
 * The end of the main turn: a compaction held for it, then the turn's steers
 * settled (settleSteers): when it answered before any request read one, one
 * wake (the row is in the conversation already), as a prompt typed mid-turn
 * would start the next turn — at once, or once the last of its pending
 * appends settles. An interrupted or failed turn wakes nothing.
 */
async function mainTurnEnded($: EngineInterface, turnId: string, reason: string) {
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
    // What the child kept on disk is this module's only after a reload; a
    // module that holds its own hands it to the child in the resync.
    if (!state.isKeptLoaded) {
      adoptKept(msg.kept)
      state.isKeptLoaded = true
    }
    // A new child knows nothing of the session: what it started as, then
    // where it stands. What was queued for no child is in that state.
    state.queue = [{ type: 'session', phase: 'start', session: state.session, ...state.info, t: Date.now() }, resyncEvent()]
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

function stopChild() {
  state.generation++
  const child = state.child
  state.child = undefined
  state.socket = undefined
  // Leaving the stream kills the child.
  void child?.return({ code: null, signal: null })
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
  emit({ type: 'heartbeat', state: turnState() })
}

export async function bridgeStart($: EngineInterface, e: SessionStartInput) {
  // derive's headless fork of a session is never a member, and needs no bridge.
  if ((await $.env.get('SMNS_INTERNAL')) !== undefined) {
    return
  }
  state.post = (socketPath, body) =>
    $.http.fetch('http://bridge/events', { method: 'POST', socketPath, headers: { 'content-type': 'application/json' }, body })
  state.get = (socketPath, path) => $.http.fetch(`http://bridge${path}`, { socketPath })
  state.log = (text) => $.ui.log(text, { to: 'debug' })
  state.after = (ms, fn) => void $.clock.after(ms, fn)
  state.readId = () => $.session.id()
  state.restart = (session) => {
    stopChild()
    startChild($, session)
  }
  state.info = {
    cwd: e.cwd,
    surface: e.surface,
    isInteractive: e.isInteractive,
    model: await $.session.model(),
    version: (await $.session.version()).version,
  }
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
    }
    state.loopTurns.set(loopKey(e.agentId), e.turnId)
    const text = capped(e.text)
    emit({ type: 'turn', phase: 'start', turnId: e.turnId, agentId: e.agentId ?? null, text: text.value, ...(text.cut && { truncated: true }) })
    return next(e)
  })

  on('turn.complete', { turnId: /^/ }, async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined && state.mainTurn === e.turnId) {
      state.mainTurn = undefined
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
    const isMain = e.agentId === undefined
    // The model chosen through the bridge is the main loop's: a subagent runs
    // on what its definition or its caller chose.
    const o = isMain ? state.override : undefined
    const input = o === undefined ? e : { ...e, ...(o.model !== null && { model: o.model }), ...(o.effort !== null && { effort: o.effort }) }
    emit({ type: 'step', phase: 'start', ...tag, model: input.model, effort: input.effort ?? null, messageCount: e.messageCount })
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
        if (chunk.kind !== 'engine') {
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
      emit({ type: 'step', phase: 'end', ...tag, stopReason, usage })
    }
  })

  on('tool.call', { tool: /^/ }, async (_, e, next) => {
    const call = `${e.tool_use_id ?? ''}#${++state.toolCalls}`
    const base = { toolUseId: e.tool_use_id || null, tool: e.tool, agentId: e.agentId ?? null }
    const input = toolInput(e as Record<string, unknown>)
    emit({ type: 'tool', phase: 'call', ...base, input: input.value, ...(input.cut && { truncated: true }) })
    let settle: (text: string | undefined) => void = () => undefined
    const done = new Promise<string | undefined>((resolve) => (settle = resolve))
    const owner = e.agentId === undefined ? state.mainTurn : state.foreground.get(e.agentId)
    state.calls.set(call, { tool: String(e.tool), owner, done, settle })
    let resultText: string | undefined
    try {
      const result = await next(e)
      resultText = typeof result.text === 'string' ? result.text : undefined
      const text = capped(result.text)
      const denied = capped(result.deny)
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
  // beneath decide first; one that did leaves nothing to raise.
  on('classic.PermissionRequest', { hook_event_name: 'PermissionRequest' }, async ($, e, next) => {
    const beneath = await next(e)
    if (beneath.decision !== undefined || state.post === undefined || state.isEnding) {
      return beneath
    }
    const agentId = e.agent_id ?? null
    const input = capped(e.tool_input)
    const now = await $.clock.now()
    const r: Request = {
      id: claimCheck(e.tool_name, agentId, e.tool_input) ?? `request-${Date.now().toString(36)}-${++state.minted}`,
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
      isClosed: false,
      isMarked: false,
      isAborted: false,
    }
    raise(r)
    const decision = await awaitDecision($, r, next.signal)
    return decision === undefined ? beneath : { ...beneath, decision }
  }).catch((_, e, next) => next(e))

  // Every row the session keeps: a response row's block, the engine's mark of
  // a hook's decision, a call's result.
  on('session.append', { door: /^/ }, async (_, e, next) => {
    const stored = await next(e)
    if (state.post !== undefined) {
      observeRow(e.door, e.message, stored.uuid ?? e.uuid, e.agentId ?? null)
    }
    return stored
  }).catch((_, e, next) => next(e))

  on('agent.spawn', { tool_use_id: /^/ }, async (_, e, next) => {
    const result = await next(e)
    if (result.agentId !== undefined) {
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
    }
    return result
  })

  on('classic.SubagentStop', { hook_event_name: 'SubagentStop' }, async (_, e, next) => {
    state.foreground.delete(e.agent_id)
    emit({ type: 'agent', phase: 'stop', agentId: e.agent_id, agentType: e.agent_type })
    return next(e)
  })
}
