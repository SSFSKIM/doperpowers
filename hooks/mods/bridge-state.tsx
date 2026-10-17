import type { HookStream, HttpResponse, ProcessSpawnChunk, ProcessSpawnResult, Timer } from 'claude-code'

/**
 * The bridge's state: one object for the session, which each of the bridge's
 * modules reads and writes (bridge.tsx names them), the types they share, and
 * their common helpers. `resetBridge` replaces the object whole.
 */

/** The longest string an event carries; the rest is in the transcript. */
export const TEXT_CAP = 65_536
export const RESPAWN_FIRST_MS = 1_000
export const EFFORTS = ['low', 'medium', 'high', 'xhigh', 'max'] as const
export type Effort = (typeof EFFORTS)[number]

export type BridgeEvent = Record<string, unknown> & { type: string }
export type Command = Record<string, unknown> & { id: string; op: string }
/** A command's answer: the `result` event's fields. */
export type Answer = { ok: true; result: Record<string, unknown> } | { ok: false; error: string }
/** The model and effort chosen for this session through the bridge; null keeps the session's own. */
export type Override = { model: string | null; effort: Effort | null }
/**
 * A tool call running now: `owner` is the main turn it belongs to (a main-loop
 * call's turn, or the turn a foreground subagent it runs in was spawned in);
 * `done` resolves with its result's text once it settles.
 */
export type Call = {
  tool: string
  owner: string | undefined
  done: Promise<string | undefined>
  settle: (text: string | undefined) => void
  toolUseId?: string
  /** An ask call's first question: what pairs it with the dialog the ask mod opens inside it. */
  question?: unknown
}
/**
 * A steer, bound to the main turn it was given in before its row is appended.
 * `isAppended`: the row is in; `isRead`: a main-loop request began after it;
 * `ended`: how its turn ended, while some append of that turn is still pending.
 */
export type Steer = { turnId: string; isAppended: boolean; isRead: boolean; ended?: string }
/** What an interrupt did to the Bash calls it moved to the background: the tasks it stopped, and those it could not. */
export type Stops = { stopped: string[]; running: string[] }
/** An interrupt of a main turn: `recorded` settles once its record is in (or it failed); the turn's Bash calls wait for it. */
export type Interrupt = { recorded: Promise<void> }
/** A content block still streaming: its text (a tool call's arguments as JSON), and its last chunk's index. */
export type Block = { index: number; kind: string; text: string; upTo: number; id?: string; name?: string }
/**
 * A message still streaming, as the child's snapshot carries it (DX4): its
 * blocks without a row yet, the ones a row settled, and `upTo`, its last chunk.
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
/** What a client decided, as the child hands it over. */
export type Decision = { behavior: 'allow' | 'deny'; message?: string; updatedInput?: { answers?: Record<string, string> } }
export type Outcome = 'allow' | 'deny' | 'answered' | 'withdrawn'
/**
 * A request from outside the terminal, raised until settled: a permission
 * prompt or a question in a dialog (under its call's tool-use id), or an
 * async question of the ask mod's.
 */
export type Request = {
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
  /** The bridge's interrupt aborted its turn. */
  isAborted: boolean
  /** The session's transcript (the PermissionRequest's `transcript_path`): where its loop's rows are read when no record came. */
  transcript?: string
  /** The ask mod's dialog: the call it opened inside, which the transcript names (DX5 `toolUseId`). */
  toolUseId?: string
}
/** A row as the session's transcript keeps it, in the shape the Stop hook's export reads (`sminos record`). */
export type TranscriptRecord = { type: 'assistant' | 'user'; uuid: string; message: { content: Record<string, unknown>[] } }
/** A call the engine's check put to the dialog. */
export type Check = { toolUseId: string; tool: string; agentId: string | null; input: unknown }
/** One agent of the session as `$.agent.list()` gives it (the fields the bridge reads). */
export type ListedAgent = { id: string; description: string; type: string; status: string; parentId?: string; name?: string }
/** A log event submitted as the human's words, whose row is still to be kept. */
export type Submission = { key: { writer: string; seq: number }; text: string }
/** A delivery the engine dropped after it was submitted, as `delivered {outcome: "refused"}` reports it. */
export type Refusal = { key: { writer: string; seq: number }; reason: string }

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
  /**
   * Whether the module's first hello was read: what the child keeps
   * (override, delivered) and its seed of each loop's cut are taken from it
   * once per module, and a model request begun before it never streams.
   */
  isSeeded: boolean
  /** Steers given in the main turn, and those whose turn ended before their row was in. */
  steers: Steer[]
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
  /** The ask tool's calls and results on the main loop, by call, until both rows of an async ask are kept (`export`). */
  asks: Map<string, { use?: TranscriptRecord; result?: TranscriptRecord }>
  /** Requests raised and not yet settled, by id; and the last settlements, oldest first. */
  requests: Map<string, Request>
  settled: Record<string, unknown>[]
  /** Request ids minted for a prompt no check named. */
  minted: number
  /** The agents `$.agent.list()` has named: only a finished agent leaves the list. */
  listed: Set<string>
  /** The agents of the conversation before a /clear: never the new session's. */
  cleared: Set<string>
  /** `agent.spawn` hooks between their `next` and their spawn event: the agent they report is theirs to report. */
  spawning: number
  /** A refresh of the list is due (while any agent runs). */
  isAgentsWatched: boolean
  /** Reads of the list, numbered as they begin: the last begun, and the latest applied. */
  agentReads: { asked: number; applied: number }
  /** Moves at each /clear: a read begun in an earlier conversation is not this one's. */
  conversation: number
  /** After a /clear, the answers that set the old conversation's agents aside; every later read waits for them. */
  clearing?: Promise<void>
  /** The reads of the list not answered yet: a /clear waits for each of them. */
  agentListsInFlight: Set<Promise<readonly ListedAgent[]>>
  /** Deliveries submitted whose prompt row has not been kept yet, oldest first (`delivered` `entered`). */
  submissions: Submission[]
  /**
   * Refusals no post the child answered has carried yet, oldest first: every
   * resync carries them, so one whose post was lost still reaches the child.
   */
  refusals: Refusal[]
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
  asks: new Map(),
  requests: new Map(),
  settled: [],
  minted: 0,
  listed: new Set(),
  cleared: new Set(),
  spawning: 0,
  isAgentsWatched: false,
  agentReads: { asked: 0, applied: 0 },
  conversation: 0,
  agentListsInFlight: new Set(),
  submissions: [],
  refusals: [],
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
  isSeeded: false,
  steers: [],
  interrupts: new Map(),
  foreground: new Map(),
})

export let state = fresh()

/** Forgets everything; for tests, which share this module. */
export function resetBridge() {
  state = fresh()
}

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

/** The key of a loop: a subagent's id, '' for the main loop. */
export const loopKey = (agentId: unknown) => (typeof agentId === 'string' ? agentId : '')

export const isEffort = (value: unknown): value is Effort => EFFORTS.includes(value as Effort)
