import type { HookStream, HttpResponse, ProcessSpawnChunk, ProcessSpawnResult, Timer } from 'claude-code'

import type { MediaAttachment, ModeKept } from '../../types/sminos'

import type { Place } from './bridge-place'
import type { Catalog } from './bridge-catalog'

/**
 * The bridge's state: one object for the session, which each of the bridge's
 * modules reads and writes (bridge.tsx names them), the types they share, and
 * their common helpers. `resetBridge` replaces the object whole.
 */

/**
 * The first line of every wake the bridge sends, naming who sends it, so a
 * reader of the transcript (the desk among them) tells a wake from the
 * human's own prompt or a peer's message.
 */
export const WAKE_LINE = '[sminos bridge]'
/** The longest string an event carries; the rest is in the transcript. */
export const TEXT_CAP = 65_536
/** How long a Bash call of an interrupted turn waits for the interrupt's record, and what an agent's stop hands its parent for the stop's note, at most (a TaskStop or an append that never answers). */
export const INTERRUPT_HOLD_MS = 10_000
/** A child that ended on its own is started again after this long, the first time (after a stable run, or ever)... */
export const RESPAWN_FIRST_MS = 0
/** ...and this long the next time it ends at once, doubling from there while it keeps doing so. */
export const RESPAWN_STEP_MS = 1_000
/** Characters of a block's text a snapshot or a resync carries: past it, its tail, marked `truncated`. */
export const BLOCK_TAIL = 65_536
export const EFFORTS = ['low', 'medium', 'high', 'xhigh', 'max'] as const
export type Effort = (typeof EFFORTS)[number]

/**
 * The bridge child's verdict on whether this session is MAWS's lane B (O12
 * M3): `match`, its parent is the pid SMNS_MEMBER names; `mismatch`, another
 * spawner is evident (that pid's process alive, older than the session and
 * not its parent: a `claude` a lane B session's Bash started, the marker
 * inherited); `unresolved`, not known (the session's pid not in the
 * registry, `ps` failing, the host gone), which the child retries.
 */
export type LaneVerdict = 'match' | 'mismatch' | 'unresolved'
export const isLaneVerdict = (value: unknown): value is LaneVerdict => value === 'match' || value === 'mismatch' || value === 'unresolved'

export type BridgeEvent = Record<string, unknown> & { type: string }
export type Command = Record<string, unknown> & { id: string; op: string }
/** A command's answer: the `result` event's fields; a refusal's `code` names its kind where DX5 gives one. */
export type Answer = { ok: true; result: Record<string, unknown> } | { ok: false; error: string; code?: string }
/** The model and effort chosen for this session through the bridge; null keeps the session's own. */
export type Override = { model: string | null; effort: Effort | null }
/** A value as an event carries it (`capped`): every string held to TEXT_CAP, and whether any was. */
export type Capped = { value: unknown; cut: boolean }
/**
 * A tool call running now: `owner` is the main turn it belongs to (a main-loop
 * call's turn, or the turn a foreground subagent it runs in was spawned in);
 * `done` resolves with its result's text once it settles; `shown`, its input
 * as the bridge's `tool.call` hook was handed it, the form its events carry.
 */
export type Call = {
  tool: string
  owner: string | undefined
  done: Promise<string | undefined>
  settle: (text: string | undefined) => void
  shown: Capped
  toolUseId?: string
  /** An ask call's first question: what pairs it with the dialog the ask mod opens inside it. */
  question?: unknown
}
/**
 * A steer (or a delivery given into the turn), bound to the main turn it was
 * given in before its row is appended.
 * `isAppended`: the row is in; `isRead`: a main-loop request began after it;
 * `ended`: how its turn ended, while some append of that turn is still pending;
 * `isDelivery`: a delivery's row, which an interrupted turn does not leave unread;
 * `text`: a delivery's text, by which its row is found in the conversation;
 * `frame`: a delivery's frame line, which a wake names (bridge.tsx, wakeText).
 */
export type Steer = { turnId: string; isAppended: boolean; isRead: boolean; ended?: string; isDelivery?: boolean; text?: string; frame?: string }
/**
 * The wake a turn owes for delivered rows it answered before reading, until
 * its prompt settles: `isRead`, a main-loop request began since that carries
 * them; `turnAt`, the main turn already running when it was given, whose
 * first request was built before the rows went in.
 */
export type Wake = { isRead: boolean; turnAt?: string }
/** What an interrupt did to the Bash calls it moved to the background: the tasks it stopped, and those it could not. */
export type Stops = { stopped: string[]; running: string[] }
/** An interrupt of a main turn: `recorded` settles once its record is in (or it failed); the turn's Bash calls wait for it. */
export type Interrupt = { recorded: Promise<void> }
/**
 * A content block of a request still open: its text (a tool call's arguments
 * as JSON) and its last chunk's index; once its `block-row` named it, `uuid`
 * the row and `namedAt` the notice's stamp (ms). A named block is kept until
 * its step ends, since the engine flushes its row only then.
 */
export type Block = { index: number; kind: string; text: string; upTo: number; id?: string; name?: string; uuid?: string; namedAt?: number; truncated?: true }
/**
 * A message still streaming, as the child's snapshot carries it (DX4): its
 * blocks, named or not, the ones a row settled, and `upTo`, its last chunk.
 */
export type Streaming = { turnId: string; agentId: string | null; step: number; model: string; upTo: number; blocks: Map<number, Block>; settled: Set<number> }
/** A loop's latest model request: where its blocks started, in order, and which a row has named. */
export type StepBlocks = {
  turnId: string
  agentId: string | null
  step: number
  starts: { index: number; kind: string; id?: string }[]
  named: Set<number>
  /** The step's end, held until every block that streamed has its row named (STEP_END_WAIT_MS at most). */
  heldEnd?: BridgeEvent
}
/**
 * What a client decided, as the child hands it over: a question's answers;
 * a scoped allow's rules (`updatedPermissions`), resolved by the daemon from
 * the request's own suggestions.
 */
export type Decision = { behavior: 'allow' | 'deny'; message?: string; updatedInput?: { answers?: Record<string, string> }; updatedPermissions?: Record<string, unknown>[] }
export type Outcome = 'allow' | 'deny' | 'answered' | 'withdrawn'
/**
 * A request from outside the terminal, raised until settled: a permission
 * prompt or a question in a dialog (under its call's tool-use id), or an
 * async question of the ask mod's.
 */
export type Request = {
  id: string
  tool: string
  /**
   * The tool's input as `raised` carries it (capped): a permission's call as
   * the bridge's `tool.call` hook saw it, a question's as the engine gave it.
   * `rawInput`, as the engine gave it, never leaves the machine.
   */
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
  /** The bridge's interrupt aborted its turn. */
  isAborted: boolean
  /** The session's transcript (the PermissionRequest's `transcript_path`): where its loop's rows are read when no record came. */
  transcript?: string
  /** The ask mod's dialog: the call it opened inside, which the transcript names (DX5 `toolUseId`). */
  toolUseId?: string
  /** The engine's `permission_suggestions`, raised only within their bound and for the call this module saw (DX5 `suggestions`). */
  suggestions?: Record<string, unknown>[]
}
/** A row as the session's transcript keeps it, in the shape the Stop hook's export reads (`sminos record`). */
export type TranscriptRecord =
  | { type: 'assistant' | 'user'; uuid: string; origin?: unknown; message: { content: Record<string, unknown>[] } }
  | { type: 'attachment'; uuid: string; attachment: Record<string, unknown> }
/** A response row holding message calls, held for the export until `calls`, those still without a result, is empty. */
export type HeldRow = { row: TranscriptRecord; calls: Set<string>; results: TranscriptRecord[] }
/**
 * A call the engine's check put to the dialog: `input` as the check holds it,
 * which pairs the call with its PermissionRequest; `shown`, the running call's
 * input as the bridge's `tool.call` hook saw it, none when it saw no such call.
 */
export type Check = { toolUseId: string; tool: string; agentId: string | null; input: unknown; shown?: Capped }
/** One agent of the session as `$.agent.list()` gives it (the fields the bridge reads). */
/** An agent the desk is stopping: its id, and its note's keeping (resolved once kept, or not to be). */
export type AgentStop = { agentId: string; noted: Promise<void> }
export type ListedAgent = { id: string; description: string; type: string; status: string; parentId?: string; name?: string }
/** A log event's key: its project (absent from a CLI older than the project in the key), writer and seq. */
export type DeliveryKey = { project?: string; writer: string; seq: number }
/** A log event submitted as the human's words, whose row is still to be kept. */
export type Submission = { key: DeliveryKey; text: string }
/**
 * A delivery the bridge put in the conversation as a row, until the
 * conversation is known to keep it: `turnId`, the main turn it was appended
 * in, none for a row given while no turn ran (a stop refused its prompt).
 */
export type DeliveredRow = { key: DeliveryKey; text: string; turnId?: string }
/** A delivery the engine dropped after it was submitted, as `delivered {outcome: "refused"}` reports it. */
export type Refusal = { key: DeliveryKey; reason: string }
/** What the bridge can do, as `GET /status` and the plane's presence carry it (DX5 `capabilities`). */
export type Capabilities = {
  sminos: string
  protocol: number
  engine: string
  ops: string[]
  reads: string[]
  routes: { measured: string }
  /** Each desk control's capability, every key present (bridge-controls.tsx). */
  controls: Record<string, { available: boolean; reason?: string }>
}
/** A desk command (DX5 op `command`) the bridge runs: its op id, the command and its trimmed args. */
export type DeskRun = { id: string; name: string; args: string; prompt?: boolean }
/** How a command's outcome was read back (DX5 `run` end): the settled text, its output row, or nothing sure. */
export type Readback = { how: 'text' | 'row' | 'effect' | 'none'; text?: string; uuid?: string }
/**
 * The readback of the desk run that settled last, while its rows are looked
 * for in the `session.append` hook (bridge-rows.tsx): its command row, then
 * the output row after it; `output` once seen, until its window closes.
 */
export type ReadbackWatch = {
  name: string
  args: string
  phase: 'command' | 'output'
  output?: { text: string; uuid: string }
  done: (readback: Readback) => void
}

export type BridgeState = {
  /**
   * The calls that outlive a hook, made in session.start: its `$` lives as
   * long as the child's loop does, so posts, timers and restarts run on it.
   */
  post?: (socketPath: string, nonce: string | undefined, body: string) => Promise<HttpResponse>
  /** A file's text, outside any hook (a transcript read when no record of a decision came). */
  read?: (path: string) => Promise<string>
  log?: (text: string) => void
  after?: (ms: number, fn: () => void) => void
  readId?: () => Promise<string>
  /**
   * A loop's rows on disk past one of them, in disk order, as the child reads
   * its transcript (GET /rows); undefined while that row is not on disk.
   */
  rowsAfter?: (loop: string, after: string) => Promise<string[] | undefined>
  /** Stops the child and starts one for this session. */
  restart?: (session: string) => void
  /** The session's agents as the engine lists them now (`$.agent.list()`). */
  listAgents?: () => Promise<readonly ListedAgent[]>
  /** What the session start said, sent to each child once it says hello. */
  info?: Record<string, unknown>
  /** The session the child serves, the socket it named, and the child itself. */
  session?: string
  socket?: string
  /** The child's, from its hello: every post carries it (DX5 fence). */
  nonce?: string
  child?: HookStream<ProcessSpawnChunk, ProcessSpawnResult>
  /**
   * The bridge's place among the secrets guards (bridge-place.tsx), this
   * module instance's alone: none until a dispatch first settles it. Until
   * then a tool event waits in the queue and no permission's input is raised.
   * While `off` there is no child, nothing is queued (the live state is still
   * kept, for the resync of the child a later `safe` starts), and nothing is
   * raised.
   */
  place?: Place
  /**
   * How many times the bridge turned off or back on. A dispatch begun before
   * the last of them read a chain that may no longer stand: it neither turns
   * the bridge back on nor, reading off, turns it off again.
   */
  transitions: number
  /** A read of which guard is loaded failed, and the person was told (once per module instance). */
  isUnreadSaid: boolean
  /** Bumped whenever a child is started or stopped on purpose; a loop of an older one does nothing more. */
  generation: number
  respawnMs: number
  heartbeat?: Timer
  queue: BridgeEvent[]
  isPosting: boolean
  /** The poster loop (started in session.start) and, while it sleeps, what wakes it. */
  isPosterRunning: boolean
  wake?: () => void
  /**
   * A post to the child of `generation` failed: that child's next post waits
   * RETRY_MS. A wait set for a child since replaced holds up nothing: its
   * successor posts at once.
   */
  retry?: { generation: number }
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
  /**
   * Per mark, the highest seq of a log event submitted: delivery goes in seq
   * order, so any key at or below it was. A mark is `<project>/<writer>`, or
   * the bare writer for a key naming no project; kept marks are taken as
   * they come, whichever they are.
   */
  delivered: Map<string, number>
  /**
   * Whether the module's first hello was read: what the child keeps
   * (override, delivered) and its seed of each loop's cut are taken from it
   * once per module, and a model request begun before it never streams.
   */
  isSeeded: boolean
  /** Steers given in the main turn, and those whose turn ended before their row was in. */
  steers: Steer[]
  /** Wakes for unread delivered rows whose prompt has not settled (bridge.tsx, wakeForSteer). */
  wakes: Wake[]
  /** The main turns the bridge's interrupt is ending, by turn, until each one ends. */
  interrupts: Map<string, Interrupt>
  /** For each running foreground subagent, the main turn it belongs to (its tool calls are that turn's). */
  foreground: Map<string, string>
  /** A compaction asked for during the main turn, run when it ends. */
  compact?: { id: string; instructions?: string }
  /** Each loop's running turn (the main loop's under ''). */
  loopTurns: Map<string, string>
  /** Each loop's latest model request and where its blocks started, for pairing rows with blocks. */
  stepBlocks: Map<string, StepBlocks>
  /** Calls the engine's check put to the dialog, oldest first: a PermissionRequest takes its call's id from one. */
  checks: Check[]
  /** Checks whose decision the engine recorded before a PermissionRequest took them (no dialog, or answered at once). */
  decidedChecks: Check[]
  /**
   * The engine's recent decision records by call, oldest first: kept until a
   * request is raised or an async question's dialog is attributed, which may
   * come after the record (the person answered while the hook still ran).
   */
  records: Map<string, { source: string; isAccepted: boolean }>
  /** An async question answered through a dialog whose request had not settled yet: dialog id → question id. */
  askDialogs: Map<string, string>
  /** The ask mod's dialogs running now: dialog id → the ask call it opened inside, if one runs. */
  dialogCalls: Map<string, string | undefined>
  /** Each loop's last row notice (`main`, or the subagent's id): the cut a resync carries. */
  cut: Map<string, string>
  /** Each loop's rows its latest notices named (as `cut` keys them), oldest first: a row past a cut that none named is one no hook saw. */
  named: Map<string, Set<string>>
  /** The loops this module saw from their first row (as `cut` keys them): no seed, nothing held back. */
  freshLoops: Set<string>
  /**
   * Whether a main turn may be running unseen: a module loaded into a session
   * that had its conversation (a reload, a resume) knows neither, until a
   * main turn starts or completes, its next request names it, or the
   * session's engine record says idle.
   */
  isTurnUnknown: boolean
  /** The session's engine record (`<config>/sessions/<pid>.json`), from the child's hello. */
  record?: string
  /** The main loop's async asks and message calls, their call and result rows by call, until both are kept (`export`). */
  pairs: Map<string, { use?: TranscriptRecord; result?: TranscriptRecord }>
  /**
   * The main loop's exports in the transcript's order while a row holding a
   * message call waits for its calls' results: the row (HeldRow), and the
   * exports kept after it by their records. Empty while no row waits.
   */
  exportHold: (HeldRow | TranscriptRecord[])[]
  /** Requests raised and not yet settled, by id; and the last settlements, oldest first. */
  requests: Map<string, Request>
  settled: Record<string, unknown>[]
  /** Request ids minted for a question no check named. */
  minted: number
  /** The agents `$.agent.list()` has named: only a finished agent leaves the list. */
  listed: Set<string>
  /** The agents of the conversation before a /clear: never the new session's. */
  cleared: Set<string>
  /** The agents this conversation's own hooks named since the last /clear (a spawn, a loop's first turn): never set aside. */
  claimed: Set<string>
  /** `agent.spawn` hooks between their `next` and their spawn event: the agent they report is theirs to report. */
  spawning: number
  /** A refresh of the list is due (while any agent runs). */
  isAgentsWatched: boolean
  /** Reads of the list, numbered as they begin: the last begun, and the latest applied. */
  agentReads: { asked: number; applied: number }
  /** Moves at each /clear: a read begun in an earlier conversation is not this one's. */
  conversation: number
  /**
   * Moves at each compaction of the main conversation: a check of delivered
   * rows begun before it holds rows the summary now carries (bridge.tsx).
   */
  compactions: number
  /** After a /clear, the answers that set the old conversation's agents aside; every later read waits for them. */
  clearing?: Promise<void>
  /** The reads of the list not answered yet: a /clear waits for each of them. */
  agentListsInFlight: Set<Promise<readonly ListedAgent[]>>
  /** Deliveries submitted whose prompt row has not been kept yet, oldest first (`delivered` `entered`). */
  submissions: Submission[]
  /** Delivered rows not yet known to stay in the conversation the next request reads (bridge.tsx, recheckDeliveries). */
  deliveredRows: DeliveredRow[]
  /**
   * Refusals no post the child answered has carried yet, oldest first: every
   * resync carries them, so one whose post was lost still reaches the child.
   */
  refusals: Refusal[]
  /** What this module can do, assembled at its session start (and again when the lane verdict moves it); every resync carries it to the child. */
  capabilities?: Capabilities
  /**
   * MAWS's lane B marker (MAWS_LANE=B) on the session's process, read at its
   * session start: the bridge only observes until its child's verdict says
   * `mismatch` (isObserver).
   */
  isLaneMarked: boolean
  /** The child's verdict, once one came; a resolved one is the process's and stands. */
  laneVerdict?: LaneVerdict
  /**
   * The launch (O12 M7): this process's id, minted at its first session
   * start and kept in `$.state` for a reload, handed to every child
   * (`--launch`), which refuses a desk action sealed for another launch.
   */
  launch?: string
  /**
   * The main loop's permission mode as the engine last reported it, absent
   * until it has (bridge.tsx, `observeMode`); kept in `$.state` for a reload.
   * `modeReports` counts the reports, so one read after a later one never
   * replaces it.
   */
  permissionMode?: ModeKept
  modeReports: number
  catalog?: Catalog
  refreshCatalog?: () => Promise<Catalog>
  /** The desk command called and not yet read back: the next waits for it (one at a time, spec §6). */
  deskRun?: DeskRun
  /** Desk commands waiting for the one before them, oldest first. */
  deskQueue: DeskRun[]
  /** The readback looked for now, if any. */
  readback?: ReadbackWatch
  /** Events a caller waits to see posted (bridge-stream, emitTaken): settled true once the child took one, false once it is lost. */
  taking: Map<BridgeEvent, (isTaken: boolean) => void>
  /**
   * The ends of ops answered at once (a desk command's `run`, a side
   * question's `btw`) that no post the child answered has carried yet, oldest
   * first, each with what waits on its taking (bridge-stream, emitOwed): every
   * resync is followed by them, so one whose post was lost, or that came while
   * no child was there, still reaches the child.
   */
  owedEnds: Map<BridgeEvent, () => void>
  /** The side questions open in this session as this module knows them: its own, and those it ends for a module before it (bridge-btw.tsx). */
  btwOpen: Set<string>
  /** The writes of `btwOpen` to the session's `$.state`, in order. */
  btwWrites: Promise<void>
  /**
   * The desk's agent stops whose note to the parent is not in yet
   * (bridge-agent-ops.tsx): an Agent call's result and the stopped agent's
   * task notification wait for them, so the parent's next request carries
   * the note.
   */
  agentStops: Set<AgentStop>
  /**
   * The desk's uploads this module holds (bridge-media.tsx): what `$.state`
   * kept for the session, reconciled once (`mediaLoad`), then every upload the
   * bridge accepts, each attachment where its intake stands.
   */
  media: MediaAttachment[]
  mediaLoad?: Promise<void>
  /** The writes of `media` to the session's `$.state`, in order. */
  mediaWrites: Promise<void>
  /** The one wake an intake may owe: armed until a turn starts, then submitted until its turn starts. */
  mediaWake: { armed?: object; isSubmitted: boolean }
  /** Whether the main turn's state is still unknown (bridge.tsx): a wake waits while it is. */
  isTurnStillUnknown?: () => Promise<boolean>
}

const fresh = (): BridgeState => ({
  loopTurns: new Map(),
  stepBlocks: new Map(),
  checks: [],
  decidedChecks: [],
  records: new Map(),
  askDialogs: new Map(),
  dialogCalls: new Map(),
  cut: new Map(),
  named: new Map(),
  freshLoops: new Set(),
  isTurnUnknown: false,
  pairs: new Map(),
  exportHold: [],
  requests: new Map(),
  settled: [],
  minted: 0,
  listed: new Set(),
  cleared: new Set(),
  claimed: new Set(),
  spawning: 0,
  isAgentsWatched: false,
  agentReads: { asked: 0, applied: 0 },
  conversation: 0,
  compactions: 0,
  agentListsInFlight: new Set(),
  submissions: [],
  deliveredRows: [],
  refusals: [],
  deskQueue: [],
  taking: new Map(),
  owedEnds: new Map(),
  btwOpen: new Set(),
  btwWrites: Promise.resolve(),
  agentStops: new Set(),
  media: [],
  mediaWrites: Promise.resolve(),
  mediaWake: { isSubmitted: false },
  transitions: 0,
  modeReports: 0,
  isLaneMarked: false,
  isUnreadSaid: false,
  generation: 0,
  respawnMs: RESPAWN_FIRST_MS,
  queue: [],
  isPosting: false,
  isPosterRunning: false,
  isEnding: false,
  turns: new Map(),
  messages: new Map(),
  agents: new Map(),
  steps: 0,
  calls: new Map(),
  toolCalls: 0,
  delivered: new Map(),
  isSeeded: false,
  steers: [],
  wakes: [],
  interrupts: new Map(),
  foreground: new Map(),
})

export let state = fresh()

/** Forgets everything; for tests, which share this module. */
export function resetBridge() {
  state = fresh()
}

/**
 * Whether the bridge only observes (O12 M3): a marked session until its
 * child's verdict says `mismatch`, so a lane B session that MAWS controls
 * never has a second controller, and a marked one whose verdict is not in
 * yet (or unresolved) is held to the safe side.
 */
export const isObserver = () => state.isLaneMarked && state.laneVerdict !== 'mismatch'

export const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

export const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)

export const parsed = (text: string): Record<string, unknown> | undefined => {
  try {
    const value: unknown = JSON.parse(text)
    return isRecord(value) ? value : undefined
  } catch {
    return undefined
  }
}

/**
 * A value with every string in it, at any depth, held to `cap` (TEXT_CAP)
 * UTF-16 units; `cut` says whether any was. A cut never ends inside a
 * surrogate pair (one that would keep a pair's high half alone is a unit
 * shorter): a lone surrogate has no canonical form, so the input could be
 * neither sealed nor matched against a decision's digest.
 */
export function capped(value: unknown, cap = TEXT_CAP): Capped {
  if (typeof value === 'string') {
    if (value.length <= cap) {
      return { value, cut: false }
    }
    const last = value.charCodeAt(cap - 1)
    return { value: value.slice(0, last >= 0xd800 && last <= 0xdbff ? cap - 1 : cap), cut: true }
  }
  if (Array.isArray(value)) {
    const items = value.map((v) => capped(v, cap))
    return { value: items.map((i) => i.value), cut: items.some((i) => i.cut) }
  }
  if (typeof value === 'object' && value !== null) {
    const entries = Object.entries(value).map(([k, v]) => [k, capped(v, cap)] as const)
    return { value: Object.fromEntries(entries.map(([k, c]) => [k, c.value])), cut: entries.some(([, c]) => c.cut) }
  }
  return { value, cut: false }
}

/** A UTF-16 surrogate without its pair: no canonical JSON or UTF-8 carries one. */
const LONE_SURROGATE = /[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/

/**
 * A JSON value's canonical text (RFC 8785, as the hub's codes and the
 * daemon's digests write it: keys sorted by UTF-16 code units, no
 * whitespace, strings and numbers as JSON.stringify writes them), or
 * undefined for a value that has none: a lone surrogate, a number that is
 * not finite, anything that is not JSON.
 */
export function canonical(value: unknown): string | undefined {
  if (value === null || typeof value === 'boolean') {
    return JSON.stringify(value)
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? JSON.stringify(value) : undefined
  }
  if (typeof value === 'string') {
    return LONE_SURROGATE.test(value) ? undefined : JSON.stringify(value)
  }
  if (Array.isArray(value)) {
    const items = value.map(canonical)
    return items.every((i) => i !== undefined) ? `[${items.join(',')}]` : undefined
  }
  const proto = isRecord(value) ? Object.getPrototypeOf(value) : undefined
  if (isRecord(value) && (proto === Object.prototype || proto === null)) {
    const entries = Object.keys(value)
      .filter((k) => value[k] !== undefined)
      .sort()
      .map((k) => [canonical(k), canonical(value[k])])
    return entries.every(([k, v]) => k !== undefined && v !== undefined) ? `{${entries.map(([k, v]) => `${k}:${v}`).join(',')}}` : undefined
  }
  return undefined
}

/** UTF-8 bytes of a text that holds no lone surrogate (a canonical text). */
export function utf8Bytes(text: string): number {
  let bytes = 0
  for (const ch of text) {
    const cp = ch.codePointAt(0)!
    bytes += cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4
  }
  return bytes
}

/** The key of a loop: a subagent's id, '' for the main loop. */
export const loopKey = (agentId: unknown) => (typeof agentId === 'string' ? agentId : '')

export const isEffort = (value: unknown): value is Effort => EFFORTS.includes(value as Effort)
