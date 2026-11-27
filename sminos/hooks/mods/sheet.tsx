import type { EngineInterface, On, ToolDescribeResult } from 'claude-code'

import type { AskSnapshot, SheetKept } from '../../types/sminos'
import { askChoiceMade, deferAskToChoice, readTodayAsks, yieldAsk } from './ask'
import {
  DESCRIPTION,
  INPUT_SCHEMA,
  NOT_KNOWN,
  SHEET_TOOL,
  STARTING,
  WITHDRAWN,
  announcement,
  answerOf,
  bandLine,
  capturedOf,
  checkRefusal,
  chooseStart,
  contentTexts,
  deliveredIn,
  deliveriesHeld,
  endedNotice,
  entryProblem,
  floorOfLines,
  floorOfMessages,
  floorOfSearch,
  floorSearchArgs,
  foreclosedResult,
  hasSubagent,
  heldKeys,
  isNewer,
  isRouteRow,
  isSheetCall,
  keysIn,
  landedSearchArgs,
  outcomeNotice,
  parseResult,
  readInput,
  resultTextOf,
  rowLines,
  searchedKeys,
  snapshotOf,
  surfaceOf,
  unreadClause,
  validateCall,
} from './sheet-model'
import type { Asker, Delivered, Effects, Probe, Recipient, Reference, Runner, SheetInput, StepAnswer, Surface, Verdict, View } from './sheet-model'

/**
 * The question sheet's mod (the plan
 * docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, I8, I11 and
 * M3): the start choice, the tool under the sheet's schema, a call through a
 * step, and the drains that keep the record applied. The record is the
 * command's (`sminos sheet step`, K1): the mod orders steps and keeps the last
 * view a step answered, nothing of the sheet's own. Delivery (M4, I9): the
 * envelopes a view holds ready go by the routes that open, and land on the
 * evidence of the row that holds them; a start's and a compaction's context
 * (I10). The terminal's drawing (M5, §8.3): the line above the prompt and a
 * call's row; a resume's open asks of today's tool staged for its start's
 * import. The other readers (M6): the ask snapshot another plugin reads
 * (I13), and the projection to the project log after a step that owes it
 * (I12).
 */

/** What the mod keeps in `$.state` for the process (types/sminos.d.ts). */
const KEPT = { plugin: 'sminos', key: 'sheet' } as const

/** A step waits at most 10 s for the record's lock (I1), and the command starts in about 0.3 s. */
const STEP_TIMEOUT_MS = 20_000
/** The check of K4 runs on this timer too: a nudge can be lost, and an idle session dispatches no hook. */
export const TICK_MS = 5_000
/** The band's link is judged again between steps every this many ticks (M5). */
const SURFACE_TICKS = 3
/** How many times a call with no answer from its step is settled in the same dispatch (I5). */
const SETTLES = 3
/** The keys one drain asks verdicts for: what the step takes in one event (I5). */
const EVENT_KEYS = 200
/** A transcript past this is searched, not read whole: what `$.fs.read` takes. */
const READ_LIMIT = 4 * 1024 * 1024
/** A call id names a directory of the staging (`CALL_ID_RE` in sminos_sheet.py). */
const CALL_ID = /^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,255}$/
/** An agent a send reaches without resuming it (I9): the others have ended. */
const RUNNING = new Set(['pending', 'running', 'waiting'])

/** The keys the engine reserves on a tool call's event: the rest are the tool's arguments. */
const RESERVED = new Set(['tool', 'tool_use_id', 'agentId', 'consent', 'requestMeta'])

/**
 * What the sheet reaches the engine through: closures made inside a hook of
 * this file (`portOf`), the `Out` pattern of ask.tsx, so `$` itself is never
 * kept. A test hands its own.
 */
export type Port = {
  /** The sminos command, with `stdin` written to it; rejects when it does not start or runs out of time. */
  run: (args: string[], stdin?: string) => Promise<{ exitCode: number; stdout: string; stderr: string; isStdoutTruncated?: boolean }>
  /** Any program (the floor's search). */
  exec: (argv: string[]) => Promise<{ exitCode: number; stdout: string; isStdoutTruncated: boolean }>
  /** The engine process's pid (`CLAUDE_PID`), or undefined when it is not known. */
  enginePid: () => Promise<string | undefined>
  write: (path: string, text: string) => Promise<void>
  read: (path: string) => Promise<string>
  /** A file's size, or undefined when it is not there. */
  size: (path: string) => Promise<number | undefined>
  exists: (path: string) => Promise<boolean>
  /** Where a path lands, its size and modification time: `$.fs.stat` with `resolve`. */
  stat: (path: string) => Promise<{ realPath?: string; size: number; mtimeMs: number }>
  /** The permission decision for a Read (`$.tool.check`), and the Read itself (`$.tool.call`). */
  check: (input: Record<string, unknown>) => Promise<unknown>
  readFile: (input: Record<string, unknown>) => Promise<unknown>
  cwd: () => Promise<string>
  agents: () => Promise<{ id: string; description: string; type: string; status: string }[]>
  /** The conversation the engine holds, in both forms; rejects where it cannot be read yet (C0's P5). */
  messages: () => Promise<{ messages: { role: string; text: string; toolUses: { tool: string; text?: string }[] }[]; api: { role: string; content: unknown }[] }>
  notify: (text: string) => void
  log: (text: string) => void
  keep: (kept: SheetKept) => void
  /** The ask key another plugin reads (I13): written as `ask.tsx` writes it where the sheet is not chosen; rejects when the write did not land. */
  publish: (snapshot: AskSnapshot) => Promise<void>
  invalidate: () => void
  /** A prompt of this plugin's (`$.prompt.submit`), the idle route; what entered, or why not. */
  submit: (text: string) => Promise<{ drop?: string; text?: string }>
  /** A message to a running subagent (`$.session.send`). */
  send: (agentId: string, text: string) => Promise<{ isDelivered: boolean; reason?: string }>
  /** `fn` from a `$.clock.after(0)` hop: outside every hook's dispatch (C0's P1). */
  after: (fn: () => void) => void
  /** The conversation as the model holds it (`$.session.messages({ as: 'api' })`). */
  api: () => Promise<readonly { role: string; content: unknown }[]>
  /** The rows draw again (`ui.render`). */
  redraw: () => void
  toast: (text: string) => void
  /** The names in a directory (`$.fs.list`). */
  list: (path: string) => Promise<string[]>
  /** Milliseconds since the epoch (`$.clock.now`). */
  now: () => Promise<number>
}

type Failure = { ok: false; code: string; error: string }
type Answer = StepAnswer | Failure
type StartSource = 'startup' | 'resume' | 'fork' | 'clear'

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))
const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)

/** A random name for a start or a call with no id of its own: hex, safe in the staging. */
function newName(prefix: string): string {
  const bytes = crypto.getRandomValues(new Uint8Array(8))
  return `${prefix}${[...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')}`
}

/**
 * One session's work in this process: the view a step answered, the calls
 * waiting for a step, the notices, the drains. A session change (a /clear, a
 * /branch, a fork) retires it and starts another: work still in flight
 * completes into the generation it began in, which nothing reads any more, so
 * a parent's call is never settled against its copy's record and no late
 * completion publishes into the session after it.
 */
type Gen = {
  session: string
  /** The last view a step answered for the session. */
  held?: View
  /** Calls the mod holds an answer for, acknowledged on its next step (E18). */
  toAck: Set<string>
  /** Calls answered `Outcome not known yet.`, settled at every trigger until a settle answers (I5). */
  unsettled: Set<string>
  /** Notices composed for the conversation, which M4's routes carry (I9). */
  notices: string[]
  /** The highest id the conversation names, once read (I10). */
  floor?: number
  /** The inbox's size at the last drain that answered, so an unfinished write at its end drains once. */
  drainedAt?: number
  /** A drain that gave no answer: ordered again at the next trigger. */
  isDrainOwed: boolean
  draining?: Promise<Answer>
  queued?: { keys: Set<string>; context?: 'compact'; promise: Promise<Answer>; resolve: (answer: Promise<Answer>) => void }
  /** The start in flight, by its nonce: one attempt at a time (I5); another only once it settled with no answer. */
  starting?: { nonce: string; attempt: Promise<Started> }
  isChecking: boolean
  /** The envelopes on a route (I9), until they land or fail. */
  flights: Flight[]
  /** Keys a `landed` or `reroute` step is ordered for and has not answered: still in flight for the routes. */
  landing: Set<string>
  /** Keys whose `landed`, or `reroute`, step gave no answer: ordered again at the next check. */
  landOwed: Set<string>
  rerouteOwed: Set<string>
  /** Keys whose idle flight did not land: their envelope waits for a route that starts no turn, so no turn is started for it again and again. */
  noIdle: Set<string>
  /** I10's context the next result or prompt route carries, once: where no SessionStart could return it (M4's decisions). */
  context?: string
  /** A compaction's context is owed: its drain gave no answer, so the next check's drain composes it. */
  isContextOwed: boolean
  /** A start's context goes by a route: its SessionStart returned before the start answered. */
  isStartRouted: boolean
  /** The transcript a start searches for the envelopes that landed (I9). */
  transcript?: string
  /** The questions a subagent's ended notice has named. */
  named: Set<string>
  /** The keys a send handed to a subagent, and to whom: owned by that agent from the hand-over until the step their receipt orders (`landed` or `reroute`) has answered, retries included. */
  sentTo: Map<string, string>
  /** The record's answered count when the idle route last failed: a count past it is a fresh answer, wherever the view lists it. */
  idleFailedAt?: number
  /** What the deliveries' blocks this conversation holds say of each question: a row's receipts where the view holds none (M5). */
  delivered: Map<string, Delivered>
  /** The one read of the conversation for those blocks: under way, made, or failed (where it cannot be read yet, C0's P5) when this many turns had started, and whether retried since. */
  deliveriesRead?: { state: 'reading' | 'done' } | { state: 'failed'; turns: number; isRetried: boolean }
  /** The projection to the project log running (I12), and whether a step owed it again meanwhile: one more after it. */
  logging?: Promise<void>
  isLogAgain: boolean
}

/**
 * One envelope on a route (I9), from the moment it is handed over until it
 * lands or fails. Landing is read from the row that holds it, never from
 * here; a flight is settled at a turn's end only by the turn it belongs to.
 */
type Flight = {
  route: 'idle' | 'result' | 'prompt' | 'send'
  keys: string[]
  text: string
  /** A subagent's envelope: whom it is sent to. */
  agentId?: string
  /** The main turn whose end settles it: the one its context entered, or the one its prompt opened; `*` whichever ends next (a turn this module did not see start). */
  turnId?: string
  /** A turn whose end settles it only if the conversation holds it: a prompt typed over a running turn enters that turn or the next. */
  tentative?: string
  /** Its turn is the next main turn to start. */
  awaitsTurn?: boolean
  /** How many main turns had started when it was reserved: a turn that started before is not its own. */
  turnsAt: number
  /** An idle prompt or a send given to the engine; until then it is a reservation, which the hop checks again and a route that opens first takes over. */
  handed?: boolean
  /** What opened an idle reservation: spent (`noIdle`, `idleFailedAt`) only if its submit fails. */
  wake?: Wake
}

/**
 * What opens the idle route (I9): fresh keys, or none when it is an answer past what the view lists (the record's
 * answered count); and that count as the view that opened it gave it, which a failed submit spends up to.
 */
type Wake = { keys: string[]; answeredCount?: number }

/** A start's answer, and the context it gives the conversation (I10): the start's own, or after the search's landing, the start's again. */
type Started = { answer: Answer; context?: string }

/**
 * The process's sheet: its choice and the session generation it serves. One
 * module serves one process; a reload starts a new one, which takes the
 * choice up from `$.state`.
 */
type Sheet = {
  port?: Port
  home: string
  kept?: SheetKept
  runner: Runner
  remote: boolean
  /** The built-in is withdrawn: the tool registered under the sheet's schema. */
  isWithdrawing: boolean
  /** The built-in was described already, so a choice made after it describes it again. */
  wasBuiltinDescribed: boolean
  gen?: Gen
  /** Each call of the tool in flight, by its id: the generation it was dispatched in, which its recovery binds to. */
  dispatching: Map<string, Gen>
  /** The sessions whose left record a removal is under way for. */
  removing: Set<string>
  /** The start a retired generation still has in flight: a removal waits for it, so no late start makes the record again. */
  retiring?: Promise<unknown>
  /**
   * A launch's classic SessionStart that came before the choice was made: at
   * a terminal's launch the engine runs it while session.start still awaits
   * (2.1.331, the live check). Ordered once the choice is the sheet; dropped
   * otherwise.
   */
  early?: { source: StartSource; session: string; transcript: string }
  /** The main turn running, by its id (`turn.start` without an agentId), until it completes. */
  mainTurn?: string
  /** How many main turns have started in this module. */
  turns: number
  /** Subagents that stopped and have not started again: never sent to, as a send resumes one (C0's P2). */
  stopped: Set<string>
  /** The surface the band links: the last view's, or the registrations' as a tick read them since (M5). */
  surface?: Surface | null
  /** How many ticks the timer has made: every third reads the registrations. */
  ticks: number
  /** How many views have set the band's link: a registrations' read that one overtook is dropped. */
  surfaceViews: number
  /** A row wanted the deliveries' blocks before the session's generation was there to read them. */
  isDeliveryWanted: boolean
  /** The ask snapshot last written or being written (I13), as its JSON: one that would say the same is not written again; forgotten when its write fails. */
  published?: string
  /** The snapshot writes, one after another, so the last asked for is the last to land. */
  publishing?: Promise<void>
}

function fresh(): Sheet {
  return {
    home: '',
    runner: 'terminal',
    remote: false,
    isWithdrawing: false,
    wasBuiltinDescribed: false,
    dispatching: new Map(),
    removing: new Set(),
    turns: 0,
    stopped: new Set(),
    ticks: 0,
    surfaceViews: 0,
    isDeliveryWanted: false,
  }
}

const newGen = (session: string): Gen => ({
  session,
  toAck: new Set(),
  unsettled: new Set(),
  notices: [],
  isDrainOwed: false,
  isChecking: false,
  flights: [],
  landing: new Set(),
  landOwed: new Set(),
  rerouteOwed: new Set(),
  noIdle: new Set(),
  isContextOwed: false,
  isStartRouted: false,
  named: new Set(),
  sentTo: new Map(),
  delivered: new Map(),
  isLogAgain: false,
})

let sheet: Sheet = fresh()

/** Forgets the process's sheet; for tests, which share this module. */
export function resetSheet() {
  sheet = fresh()
}

/** Whether this process asks through the sheet. */
export const isSheetChosen = () => sheet.kept?.choice === 'sheet'

/** The current session's generation, when it is the session the process is in. */
const current = (): Gen | undefined => (sheet.gen !== undefined && sheet.gen.session === sheet.kept?.session ? sheet.gen : undefined)

/** The notices composed for the current session's conversation (M4 carries them). */
export const sheetNotices = (): readonly string[] => current()?.notices ?? []

/** The view the mod holds for the session it is in, if any. */
export const sheetView = (): View | undefined => current()?.held

const staging = (session: string) => `${sheet.home}/sheet/.staging/${session}`
const inbox = (session: string) => `${sheet.home}/sheet/${session}/inbox.jsonl`

function keep(change: Partial<SheetKept>) {
  if (sheet.kept === undefined) return
  const wasStarted = sheet.kept.started
  sheet.kept = { ...sheet.kept, ...change }
  for (const key of Object.keys(change) as (keyof SheetKept)[]) {
    if (change[key] === undefined) delete sheet.kept[key]
  }
  sheet.port?.keep(sheet.kept)
  if (sheet.kept.started !== wasStarted) {
    // The band draws only for a started session (M5).
    sheet.port?.redraw()
  }
}

/** Retires the current generation (a session change): its start in flight is remembered for a removal to wait on. */
function retire() {
  const attempt = sheet.gen?.starting?.attempt
  if (attempt !== undefined) {
    sheet.retiring = attempt.catch(() => undefined)
  }
  sheet.gen = undefined
}

// ------------------------------------------------------------------ the step

/**
 * One step (I5) of a generation's session: the event, with what every event
 * carries (the runner, the reach, the calls now acknowledged, the running
 * agents where the view holds a subagent's question or outcome), to `sminos
 * sheet step`. A view answered is adopted in the record's order, into the
 * generation the step was ordered for. Anything but `ok: true` is no answer:
 * the caller orders the event again, or settles a call.
 */
async function step(port: Port, gen: Gen, event: Record<string, unknown>, agents?: string[]): Promise<Answer> {
  const own = isRecord(event.call) ? event.call.callId : undefined
  const acked = [...gen.toAck].filter((id) => id !== own)
  let running = agents
  // A view not held yet (a reload's first drain) may hold a running subagent's question: its agents are read too.
  const mayHoldSubagent = (gen.held === undefined && event.event !== 'start') || hasSubagent(gen.held) || gen.sentTo.size > 0
  if (running === undefined && mayHoldSubagent) {
    running = await runningAgents(port, gen).catch(() => undefined)
  }
  const full = {
    ...event,
    runner: sheet.runner,
    remote: sheet.remote,
    ...(acked.length > 0 && { acked }),
    ...(running !== undefined && { agents: { running, direct: true } }),
  }
  let answer: Answer
  try {
    const out = await port.run(['sheet', 'step', '--session', gen.session], JSON.stringify(full))
    answer = answerOf(out.stdout) ?? { ok: false, code: 'no-answer', error: `the step answered no JSON (exit ${out.exitCode}${out.stderr.trim() === '' ? '' : `: ${out.stderr.trim().slice(0, 300)}`})` }
  } catch (error) {
    answer = { ok: false, code: 'no-answer', error: message(error) }
  }
  if (!answer.ok) {
    port.log(`sheet: a ${String(event.event)} step gave no answer (${answer.code}: ${answer.error})`)
    return answer
  }
  acked.forEach((id) => gen.toAck.delete(id))
  if (answer.effects.owed > 0) {
    projectLog(port, gen)
  }
  if (isNewer(gen.held === undefined ? undefined : { session: gen.session, view: gen.held }, gen.session, answer.view)) {
    const before = gen.held
    gen.held = answer.view
    // A view adopted opens the routes it holds envelopes for (I9).
    deliver(port, gen)
    // And the band's line and the rows' receipts draw from it (M5): its surface is the full rule.
    if (gen === current()) {
      // A registrations' read under way when this view came is older than it: it sets nothing.
      sheet.surfaceViews += 1
      if (before?.seq !== answer.view.seq || JSON.stringify(sheet.surface) !== JSON.stringify(answer.view.surface)) {
        sheet.surface = answer.view.surface
        port.redraw()
      }
      publish(port)
    }
  }
  return answer
}

/**
 * The ask snapshot (I13) from the view held for the session the process is
 * in, written when it says something new: the answered questions, their
 * count and the open ones from the view, whether the main turn runs.
 */
function publish(port: Port) {
  const held = current()?.held
  if (held === undefined || !isSheetChosen()) return
  const snapshot = snapshotOf(held, sheet.mainTurn !== undefined)
  const text = JSON.stringify(snapshot)
  if (text === sheet.published) return
  sheet.published = text
  sheet.publishing = (sheet.publishing ?? Promise.resolve()).then(async () => {
    if (sheet.published !== text) return // a newer one is asked for: it is written instead
    try {
      await port.publish(snapshot)
    } catch (error) {
      port.log(`sheet: the ask snapshot is not written: ${message(error)}`)
      if (sheet.published === text) sheet.published = undefined // not acknowledged: the same one is written again when asked
    }
  })
}

/**
 * The projection to the project log (I12), `sminos sheet log`, after a step
 * whose effects say the log is owed: never awaited, one at a time, and one
 * more after it when a step owed it again meanwhile. What it could not write
 * stays owed in the record: the next step that owes orders it again, and
 * the Stop hook's record runs it too.
 */
function projectLog(port: Port, gen: Gen) {
  if (gen.logging !== undefined) {
    gen.isLogAgain = true
    return
  }
  gen.logging = (async () => {
    do {
      gen.isLogAgain = false
      try {
        const out = await port.run(['sheet', 'log', '--session', gen.session])
        if (out.exitCode !== 0) {
          port.log(`sheet: the project log was not written (exit ${out.exitCode}: ${out.stderr.trim().slice(0, 300)}); the next step that owes it orders it again`)
        }
      } catch (error) {
        port.log(`sheet: the project log was not written (${message(error)}); the next step that owes it orders it again`)
      }
    } while (gen.isLogAgain)
    gen.logging = undefined
  })()
}

/**
 * The subagents a step may leave an outcome with: running as the engine
 * lists them and not stopped since, and any that owns a key a send handed
 * it, until its receipt's step has answered, so the `agents` rule does not
 * take a key back for the main conversation while a send may still deliver
 * it (MAWS reads the record meanwhile).
 */
async function runningAgents(port: Port, gen: Gen): Promise<string[]> {
  const listed = (await port.agents()).filter((agent) => RUNNING.has(agent.status) && !sheet.stopped.has(agent.id)).map((agent) => agent.id)
  return [...new Set([...listed, ...gen.sentTo.values()])]
}

/**
 * Whether a step other than `start` may be ordered for a generation: it is
 * the current one, and its session's start has answered (I8).
 */
const isStarted = (gen: Gen | undefined): gen is Gen => gen !== undefined && gen === current() && isSheetChosen() && sheet.kept?.started === gen.session

/**
 * A drain (K4) of a generation: single-flight, one running and at most one
 * more remembered, which takes the keys of every request made meanwhile, and
 * the compaction's context when one asked for it. Each request resolves with
 * the step that took its keys.
 */
function drain(port: Port, gen: Gen, keys: string[] = [], context?: 'compact'): Promise<Answer> {
  if (gen.draining === undefined) {
    gen.draining = runDrain(port, gen, keys, context)
    return gen.draining
  }
  if (gen.queued === undefined) {
    let resolve: (answer: Promise<Answer>) => void = () => {}
    const promise = new Promise<Answer>((settle) => (resolve = settle))
    gen.queued = { keys: new Set(), promise, resolve }
  }
  keys.forEach((key) => gen.queued?.keys.add(key))
  if (context !== undefined) gen.queued.context = context
  return gen.queued.promise
}

async function runDrain(port: Port, gen: Gen, keys: string[], context?: 'compact'): Promise<Answer> {
  try {
    if (!isStarted(gen)) {
      return { ok: false, code: 'no-sheet', error: 'the sheet has not started in this session' }
    }
    const size = await port.size(inbox(gen.session)).catch(() => undefined)
    const answer = await step(port, gen, { event: 'drain', ...(keys.length > 0 && { keys: keys.slice(0, EVENT_KEYS) }), ...(context !== undefined && { context }) })
    gen.isDrainOwed = !answer.ok
    if (answer.ok) gen.drainedAt = size
    if (answer.ok && context === 'compact') {
      // A compaction's context its SessionStart could not return: the next result or prompt route carries it.
      gen.isContextOwed = false
      routeContext(gen, answer.effects.context)
    }
    return answer
  } finally {
    gen.draining = undefined
    const queued = gen.queued
    gen.queued = undefined
    if (queued !== undefined) {
      gen.draining = runDrain(port, gen, [...queued.keys], queued.context)
      queued.resolve(gen.draining)
    }
  }
}

/**
 * The start step owed for the generation's session (kept as `starting`, or
 * as `preparing` while a resume's or a copy's is made ready first):
 * single-flight by its nonce, so a trigger while one runs joins it; ordered
 * again only once an attempt settled with no answer. An answer is followed
 * by the search for what landed (I9), and marks the session started only
 * then, while the generation is current and the start the one kept: no
 * route takes an outcome the search is about to land.
 */
function startStep(port: Port, gen: Gen): Promise<Started> | undefined {
  const owed = sheet.kept?.starting ?? sheet.kept?.preparing
  if (owed === undefined || gen !== current()) {
    return undefined
  }
  if (gen.starting !== undefined && gen.starting.nonce === owed.nonce) {
    return gen.starting.attempt
  }
  const attempt = (async (): Promise<Started> => {
    const starting = sheet.kept?.starting ?? (await prepareStart(port, gen))
    if (starting === undefined) {
      return { answer: { ok: false, code: 'superseded', error: 'another start took the place of this one while it was made ready' } }
    }
    const event = {
      event: 'start',
      start: {
        source: starting.source,
        nonce: starting.nonce,
        ...(starting.floor !== undefined && { floor: starting.floor }),
        ...(starting.today !== undefined && { today: starting.today }),
      },
    }
    const answer = await step(port, gen, event)
    if (!answer.ok && answer.code === 'bad-event' && (starting.today?.asks.length ?? 0) > 0 && sheet.kept?.starting?.nonce === starting.nonce) {
      // Asks it could not take (a staged file gone): the start goes without them, and the next start reads them again.
      port.log(`sheet: the start refused the asks of today's tool it was given (${answer.error}); it goes without them`)
      keep({ starting: { ...starting, today: { definite: false, asks: [] } } })
    }
    if (!answer.ok || gen !== current() || sheet.kept?.starting?.nonce !== starting.nonce) {
      return { answer }
    }
    const context = await afterStart(port, gen, answer, event)
    if (gen === current() && sheet.kept?.starting?.nonce === starting.nonce) {
      // A start forgets every call (I5): nothing is left to acknowledge.
      gen.toAck.clear()
      keep({ started: gen.session, starting: undefined })
      if (gen.isStartRouted) routeContext(gen, context)
      deliver(port, gen)
    }
    return { answer, context }
  })()
  gen.starting = { nonce: owed.nonce, attempt }
  void attempt.finally(() => {
    if (gen.starting?.attempt === attempt) gen.starting = undefined
  })
  return attempt
}

/** A call answered `Outcome not known yet.`, settled again: once a settle answers, its outcome is a notice of its generation (I9). */
async function settleLate(port: Port, gen: Gen, callId: string) {
  const answer = await step(port, gen, { event: 'settle', call: { callId } })
  if (answer.ok) {
    gen.unsettled.delete(callId)
    gen.toAck.add(callId)
    gen.notices.push(outcomeNotice(callId, answer.effects.result !== undefined ? { result: answer.effects.result } : { foreclosed: true }))
  } else if (answer.code === 'gone' || answer.code === 'no-record') {
    // Nothing is left to settle: a start forgot it, or the record went.
    gen.unsettled.delete(callId)
  }
}

/**
 * The check of K4, at every hook dispatch it is triggered from and on the
 * timer, for the current generation: a start owed is ordered (or joined);
 * then, once the session's start has answered, every call still unsettled is
 * settled, and a drain is ordered when the inbox is longer than the view's
 * offset (one `$.fs.stat`), or a drain is owed. Never awaited by a hook: a
 * hook that only triggers a drain returns before the step does.
 */
async function check(port: Port) {
  const gen = current()
  if (!isSheetChosen() || gen === undefined || gen.isChecking) {
    return
  }
  gen.isChecking = true
  try {
    await startStep(port, gen)
    if (!isStarted(gen)) {
      return
    }
    for (const callId of [...gen.unsettled]) {
      await settleLate(port, gen, callId)
    }
    if (gen.landOwed.size > 0) await orderKeys(port, gen, 'landed', [...gen.landOwed])
    if (gen.rerouteOwed.size > 0) await orderKeys(port, gen, 'reroute', [...gen.rerouteOwed])
    if (gen.isContextOwed) await drain(port, gen, [], 'compact')
    const size = await port.size(inbox(gen.session)).catch(() => undefined)
    const view = gen.held
    if (view === undefined || gen.isDrainOwed || (size !== undefined && size > view.offset && size !== gen.drainedAt)) {
      await drain(port, gen)
    }
  } catch (error) {
    port.log(`sheet: the check failed: ${message(error)}`)
  } finally {
    gen.isChecking = false
  }
}

/** Triggers the check from a hook, never waiting for it. */
function triggerCheck() {
  if (sheet.port !== undefined && isSheetChosen()) {
    void check(sheet.port)
  }
}

/**
 * The bridge's `sheet` op (I3), and the nudge a child's hello gives: a drain
 * naming the keys a surface's door appended, answered with their verdicts.
 * `no-sheet` in a session whose choice is not the sheet, or whose start has
 * not answered.
 */
export async function sheetNudge(keys: unknown): Promise<{ ok: true; result: Record<string, unknown> } | { ok: false; error: string; code: string }> {
  const port = sheet.port
  const gen = current()
  if (port === undefined || !isStarted(gen)) {
    return { ok: false, code: 'no-sheet', error: 'this session does not ask through a question sheet, or its sheet has not started' }
  }
  const asked = Array.isArray(keys) ? keys.filter((key): key is string => typeof key === 'string').slice(0, EVENT_KEYS) : []
  const answer = await drain(port, gen, asked)
  if (!answer.ok) {
    return { ok: false, code: answer.code, error: answer.error }
  }
  const verdicts: Record<string, Verdict> = {}
  for (const key of asked) {
    const verdict = answer.effects.verdicts[key]
    if (verdict !== undefined) verdicts[key] = verdict
  }
  return { ok: true, result: { verdicts } }
}

// ------------------------------------------------------------------ delivery (I9)

type Envelope = View['ready'][number]

const isSame = (a: Recipient, b: Recipient) => (a === 'main' ? b === 'main' : b !== 'main' && a.agentId === b.agentId)

/** Whether a key is on a route, or a step that lands or reroutes it has not answered yet. */
const isInFlight = (gen: Gen, key: string) => gen.landing.has(key) || gen.flights.some((flight) => flight.keys.includes(key))

/** A recipient's ready envelope: the view's, when none of its keys is in a flight (I9). */
function readyFor(gen: Gen, recipient: Recipient): Envelope | undefined {
  const envelope = gen.held?.ready.find((ready) => isSame(ready.recipient, recipient))
  return envelope !== undefined && !envelope.keys.some((key) => isInFlight(gen, key)) ? envelope : undefined
}

/** The main conversation's routes are the tool's to open in a terminal session; in a MAWS-run one, MAWS delivers (§5.4). */
const isTerminal = () => sheet.runner === 'terminal'

/**
 * The routes a view opens (I9): the idle route, when no main turn runs and
 * the main conversation's ready envelope wakes for an answer not already
 * failed on it; a send to each subagent with an envelope ready that has not
 * stopped. Each reserves its envelope here, in one synchronous step, so no
 * other route takes it meanwhile, and goes from a `$.clock.after(0)` hop,
 * never inside a hook's dispatch (C0's P1), where the reservation is checked
 * again before anything is handed to the engine.
 */
function deliver(port: Port, gen: Gen) {
  if (!isStarted(gen)) {
    return
  }
  if (isTerminal() && sheet.mainTurn === undefined) {
    const envelope = readyFor(gen, 'main')
    const wake = envelope !== undefined && envelope.wakes ? freshWake(gen, envelope) : undefined
    if (envelope !== undefined && wake !== undefined) {
      const flight: Flight = { route: 'idle', keys: envelope.keys, text: envelope.text, turnsAt: sheet.turns, wake }
      gen.flights.push(flight)
      port.after(() => void submitIdle(port, gen, flight))
    }
  }
  for (const envelope of gen.held?.ready ?? []) {
    const recipient = envelope.recipient
    if (recipient !== 'main' && !sheet.stopped.has(recipient.agentId) && readyFor(gen, recipient) !== undefined) {
      const flight: Flight = { route: 'send', keys: envelope.keys, text: envelope.text, agentId: recipient.agentId, turnsAt: sheet.turns }
      gen.flights.push(flight)
      port.after(() => void sendTo(port, gen, flight))
    }
  }
}

/**
 * Whether a pending key wakes the session: an answer not owed across a stop
 * (I9). The view lists the first 200 pending; a key past them is taken to
 * wake, as its envelope does.
 */
function isWaking(view: View | undefined, key: string): boolean {
  const outcome = view?.pending.find((o) => o.key === key)
  return outcome === undefined || (outcome.kind === 'answer' && !outcome.acrossStop)
}

/**
 * What may open the idle route: the main conversation's answers no idle
 * submit has failed on, in its ready envelope or anywhere the view lists as
 * pending (the envelope packs the failed work first, and may be full of
 * it), or, past what the view lists, an answer the record accepted since
 * the last failure. Failed work alone never opens the route again: a
 * failed submit spends what opened it (`missed`); nothing else does.
 */
function freshWake(gen: Gen, envelope: Envelope): Wake | undefined {
  const view = gen.held
  const fresh = (key: string) => !gen.noIdle.has(key) && isWaking(view, key)
  const keys = [...new Set([...envelope.keys.filter(fresh), ...(view?.pending ?? []).filter((o) => o.recipient === 'main' && fresh(o.key)).map((o) => o.key)])]
  const answeredCount = view?.answeredCount
  if (keys.length > 0) return { keys, ...(answeredCount !== undefined && { answeredCount }) }
  if (view !== undefined && view.pendingCount > view.pending.length && gen.idleFailedAt !== undefined && view.answeredCount > gen.idleFailedAt) {
    return { keys: [], answeredCount: view.answeredCount }
  }
  return undefined
}

/** A reservation the hop finds no longer good: let go, nothing failed; the routes open again for what it held. */
function release(port: Port, gen: Gen, flight: Flight) {
  gen.flights = gen.flights.filter((other) => other !== flight)
  deliver(port, gen)
}

/**
 * The idle route: the envelope as this plugin's prompt, which starts a turn
 * once the session is idle, the notices waiting above it (the engine raises
 * no `prompt.submit` for a plugin's own prompt, so they would wait past this
 * turn). At the hop the reservation must still be good: the session's
 * generation, started, no main turn begun since, and not taken by a route
 * that opened first. It fails when the submit is dropped, rejects, or enters
 * without the envelope; it lands by its row. Its own turn is one that
 * started after the submit: a turn that was running already, or a prompt
 * queued ahead of it, ends without settling it.
 */
async function submitIdle(port: Port, gen: Gen, flight: Flight) {
  if (!gen.flights.includes(flight)) {
    return
  }
  if (!isStarted(gen) || sheet.mainTurn !== undefined) {
    release(port, gen, flight)
    return
  }
  flight.handed = true
  const notices = gen.notices.splice(0)
  let entered: { drop?: string; text?: string }
  try {
    entered = await port.submit([...notices, flight.text].join('\n\n'))
  } catch (error) {
    gen.notices.unshift(...notices)
    failIdle(port, gen, flight, message(error))
    return
  }
  const text = entered.drop === undefined ? (entered.text ?? '') : ''
  gen.notices.unshift(...notices.filter((notice) => entered.drop !== undefined || (entered.text !== undefined && !entered.text.includes(notice))))
  if (!gen.flights.includes(flight)) {
    // Its row landed it already.
    return
  }
  if (entered.drop !== undefined) {
    failIdle(port, gen, flight, entered.drop)
  } else if (entered.text !== undefined && !keysIn([text]).some((key) => flight.keys.includes(key))) {
    failIdle(port, gen, flight, 'a hook took the envelope out of the prompt')
  } else {
    turnOf(flight)
  }
}

/**
 * An idle submit that did not enter: failed, then the view held is
 * reconsidered at once, as an answer that came while the submit waited
 * found its envelope in flight and opened nothing; what the failed attempt
 * was opened for wakes nothing again (`missed`).
 */
function failIdle(port: Port, gen: Gen, flight: Flight, why: string) {
  failFlight(port, gen, flight, why)
  deliver(port, gen)
}

/** A flight that entered: its turn is the main turn that started since it was reserved, else the next to start. */
function turnOf(flight: Flight) {
  if (sheet.mainTurn !== undefined && sheet.turns > flight.turnsAt) {
    flight.turnId = sheet.mainTurn
  } else {
    flight.awaitsTurn = true
  }
}

/**
 * A send to a running subagent (§6): delivered is its landing (C0's P2); not
 * delivered, or a rejection, reroutes it to the main conversation. At the
 * hop the reservation must still be good: the generation current, the agent
 * not stopped since (a send would resume it). From the hand-over until its
 * receipt's step has answered (a retry at a check included), every step
 * passes the agent as running.
 */
async function sendTo(port: Port, gen: Gen, flight: Flight) {
  const agentId = flight.agentId as string
  if (!gen.flights.includes(flight)) {
    return
  }
  if (!isStarted(gen) || sheet.stopped.has(agentId)) {
    // The stop's drain hands its outcomes to the main conversation.
    release(port, gen, flight)
    return
  }
  flight.handed = true
  flight.keys.forEach((key) => gen.sentTo.set(key, agentId))
  let sent: { isDelivered: boolean; reason?: string }
  try {
    sent = await port.send(agentId, flight.text)
  } catch (error) {
    sent = { isDelivered: false, reason: message(error) }
  }
  gen.flights = gen.flights.filter((other) => other !== flight)
  flight.keys.forEach((key) => gen.landing.add(key))
  if (sent.isDelivered) {
    await orderKeys(port, gen, 'landed', flight.keys)
  } else {
    port.log(`sheet: a send to the subagent ${agentId} was not delivered (${sent.reason ?? 'no reason'}); its answers go to the main conversation`)
    await orderKeys(port, gen, 'reroute', flight.keys)
  }
}

/** A flight that did not go: its envelope is ready again, for the next route. */
function failFlight(port: Port, gen: Gen, flight: Flight, why: string) {
  if (!gen.flights.includes(flight)) {
    return
  }
  gen.flights = gen.flights.filter((other) => other !== flight)
  // A failed idle submit spends what opened it too: the hidden fresh answers it was opened for wake nothing more.
  missed(port, gen, flight.route, flight.keys, why, flight.wake)
}

/**
 * Keys a route did not bring to the model: ready again for the next route
 * (today's toast). After a failed idle submit, the idle route does not
 * retry them by itself, nor the answers that opened it (`woke`, up to the
 * answered count the view that opened it gave): no turn started again and
 * again for the same failure; a fresh answer, one that came while the
 * submit waited included, still wakes the session, and takes them along.
 */
function missed(port: Port, gen: Gen, route: Flight['route'], keys: readonly string[], why: string, woke?: Wake) {
  if (route === 'idle') {
    for (const key of [...keys, ...(woke?.keys ?? [])]) gen.noIdle.add(key)
    gen.idleFailedAt = woke?.answeredCount ?? gen.held?.answeredCount
  }
  port.log(`sheet: an envelope's ${route} route failed (${why}); ${keys.length} answers wait for the next route`)
  if (gen === current()) {
    port.toast(`An answer did not reach the model (${why}); it goes with the next message.`)
  }
}

/**
 * Keys the evidence says landed (I9): their flights are done, and a
 * `landed` step is ordered, never awaited by the hook that saw them; until
 * it answers they stay in flight, so no route sends them again.
 */
function land(port: Port, gen: Gen, keys: readonly string[]) {
  if (keys.length === 0) {
    return
  }
  gen.flights = gen.flights.filter((flight) => !flight.keys.some((key) => keys.includes(key)))
  keys.forEach((key) => gen.landing.add(key))
  void orderKeys(port, gen, 'landed', keys)
}

/** A `landed` or `reroute` step for keys, 200 an event (I5); with no answer, owed to the next check. */
async function orderKeys(port: Port, gen: Gen, event: 'landed' | 'reroute', keys: readonly string[]) {
  const owed = event === 'landed' ? gen.landOwed : gen.rerouteOwed
  const released = new Set<string>()
  for (let i = 0; i < keys.length; i += EVENT_KEYS) {
    const chunk = keys.slice(i, i + EVENT_KEYS)
    const answer = await step(port, gen, { event, keys: chunk })
    if (answer.ok || answer.code === 'no-record') {
      chunk.forEach((key) => {
        owed.delete(key)
        gen.landing.delete(key)
        if (event === 'landed') gen.noIdle.delete(key)
        const owner = gen.sentTo.get(key)
        if (owner !== undefined) {
          gen.sentTo.delete(key)
          released.add(owner)
        }
      })
    } else {
      chunk.forEach((key) => owed.add(key))
    }
  }
  // An agent that no longer owns a key and has stopped: what was left with it while it did (answers drained
  // meanwhile) goes to the main conversation by a drain, whose `agents` no longer name it.
  const owners = new Set(gen.sentTo.values())
  if ([...released].some((agent) => !owners.has(agent) && sheet.stopped.has(agent)) && isStarted(gen)) {
    void drain(port, gen)
  }
  deliver(port, gen)
}

/** A context for the next result or prompt route, once (I10): the newer replaces one still waiting. */
function routeContext(gen: Gen, context: string | undefined) {
  if (context !== undefined && context !== '') {
    gen.context = context
  }
}

/**
 * What a result or a prompt route carries (I9), taken in one synchronous
 * step: the ready envelope as a flight of its own (an idle reservation not
 * yet handed over yields it to the route that opened first), the notices
 * waiting, and a context owed; each an entry of its own. In a MAWS-run
 * session only the context (I10): no answer goes by a route there (§5.4).
 */
function take(gen: Gen, route: 'result' | 'prompt'): { entries: string[]; flight?: Flight; notices: string[]; context?: string } {
  const context = gen.context
  gen.context = undefined
  if (!isTerminal()) {
    return { entries: context === undefined ? [] : [context], notices: [], ...(context !== undefined && { context }) }
  }
  gen.flights = gen.flights.filter((other) => other.route !== 'idle' || other.handed === true)
  const envelope = readyFor(gen, 'main')
  const flight: Flight | undefined = envelope === undefined ? undefined : { route, keys: envelope.keys, text: envelope.text, turnsAt: sheet.turns }
  if (flight !== undefined) gen.flights.push(flight)
  const notices = gen.notices.splice(0)
  return { entries: [...(flight === undefined ? [] : [flight.text]), ...notices, ...(context === undefined ? [] : [context])], ...(flight !== undefined && { flight }), notices, ...(context !== undefined && { context }) }
}

/** The notices and the context a route took that what entered does not carry (`entered`, its context; none for what did not enter), back where they were, each on its own. */
function putBack(gen: Gen, taken: ReturnType<typeof take>, entered: readonly string[]) {
  gen.notices.unshift(...taken.notices.filter((notice) => !entered.includes(notice)))
  if (taken.context !== undefined && !entered.includes(taken.context)) gen.context ??= taken.context
}

/** The generation a route of the main conversation may open in: the current one, started; a result route only in a terminal session. */
function routable(): Gen | undefined {
  const gen = current()
  return sheet.port !== undefined && isStarted(gen) ? gen : undefined
}

/**
 * A main turn ended (I9): each flight it settles that neither landed nor
 * failed is looked for in the conversation the model holds, in a route's
 * framing; the keys found land, the rest are ready again (a context a hook
 * outside this plugin dropped, which no return value reports). A prompt
 * typed over this turn that the turn did not take belongs to the next turn,
 * marked before the conversation is read, so a turn that starts during the
 * read is that one. A turn that ends while an idle flight's prompt has not
 * entered settles nothing of it. Then, a turn that ended with the model's
 * answer opens the idle route for what wakes.
 */
async function endTurn(port: Port, gen: Gen, turnId: string, reason: string) {
  const due = gen.flights.filter((flight) => flight.turnId === turnId || flight.turnId === '*' || flight.tentative === turnId)
  const typedOver = new Set(due.filter((flight) => flight.turnId === undefined && flight.tentative === turnId))
  typedOver.forEach((flight) => {
    flight.tentative = undefined
    flight.awaitsTurn = true
  })
  if (due.length > 0) {
    let held = new Set<string>()
    try {
      held = heldKeys(await port.api())
    } catch (error) {
      port.log(`sheet: the conversation could not be read at a turn's end (${message(error)})`)
    }
    for (const flight of due) {
      if (!gen.flights.includes(flight)) continue
      const found = flight.keys.filter((key) => held.has(key))
      if (found.length > 0) {
        gen.flights = gen.flights.filter((other) => other !== flight)
        const rest = flight.keys.filter((key) => !found.includes(key))
        if (rest.length > 0) missed(port, gen, flight.route, rest, 'the conversation holds only part of it')
        land(port, gen, found)
      } else if (!typedOver.has(flight)) {
        failFlight(port, gen, flight, 'the conversation does not hold it at its turn\'s end')
      }
    }
  }
  if (reason === 'answer') {
    deliver(port, gen)
  }
}

/** A subagent stopped with questions open (E14): each question named to the main conversation once, from the view held. */
function noticeEnded(gen: Gen, agentId: string) {
  const fresh = (gen.held?.open ?? []).filter((q) => q.asker !== 'main' && q.asker.agentId === agentId && !gen.named.has(q.id))
  if (fresh.length === 0) {
    return
  }
  fresh.forEach((q) => gen.named.add(q.id))
  const asker = fresh[0]?.asker as { agentId: string; name: string }
  gen.notices.push(endedNotice(asker, fresh))
}

/**
 * After a start answered (M4's decisions): when its effects name outcomes
 * pending before its drain, the transcript is searched for the envelopes
 * that landed and their keys handed to `landed`, then the start is ordered
 * again under its nonce, so its context lists what is still owed; the
 * context of the start that answered last. A search that fails lands
 * nothing: those outcomes go again, owed across a stop.
 */
async function afterStart(port: Port, gen: Gen, answer: Extract<Answer, { ok: true }>, event: Record<string, unknown>): Promise<string | undefined> {
  const start = answer.effects.start
  // In a MAWS-run session only a `delivered` line moves an outcome of the main conversation (§5.4).
  if (start === undefined || start.beforeCount === 0 || gen.transcript === undefined || !isTerminal()) {
    return answer.effects.context
  }
  // When `before` lists every key pending, a key it does not list was not pending: the search prints those alone.
  const isComplete = start.beforeCount <= start.before.length
  const found = await searchLanded(port, gen.transcript, isComplete ? start.before : [])
  const keys = isComplete ? found.filter((key) => start.before.includes(key)) : found
  if (keys.length === 0) {
    return answer.effects.context
  }
  keys.forEach((key) => gen.landing.add(key))
  await orderKeys(port, gen, 'landed', keys)
  const again = await step(port, gen, event)
  return again.ok ? again.effects.context : answer.effects.context
}

/** The keys of the envelopes the transcript holds in rows of the routes' kinds: one perl pass printing each row's kind and keys, newest first. */
async function searchLanded(port: Port, transcript: string, only: readonly string[]): Promise<string[]> {
  try {
    const search = await port.exec(landedSearchArgs(transcript, only))
    if (search.exitCode === 1) return []
    if (search.exitCode !== 0) {
      port.log(`sheet: the transcript's search for delivered envelopes exited ${search.exitCode}; nothing is taken as landed`)
      return []
    }
    const lines = search.stdout.split('\n')
    if (search.isStdoutTruncated) {
      // Newest first, a key once: a cut loses only the oldest rows' keys, which go again owed across the stop.
      port.log('sheet: the transcript\'s search for delivered envelopes was cut; its oldest rows are not taken as landed')
      return searchedKeys(lines.slice(0, -1))
    }
    return searchedKeys(lines)
  } catch (error) {
    port.log(`sheet: the transcript could not be searched for delivered envelopes (${message(error)}); nothing is taken as landed`)
    return []
  }
}

// ------------------------------------------------------------------ the terminal's drawing (M5; §8.3)

/** The timer's tick: the check of K4; every third, the registrations read for the band's link. */
function tick(port: Port) {
  void check(port)
  sheet.ticks += 1
  if (sheet.ticks % SURFACE_TICKS === 0 && bandNow() !== undefined) {
    void readSurfaces(port)
  }
}

/**
 * The band's link between steps (M5): the registrations read with `$.fs`,
 * judged by their heartbeat's age alone (`surfaceOf`); a step's view, the full
 * rule, replaces it at the next step. A change redraws.
 */
async function readSurfaces(port: Port) {
  const dir = `${sheet.home}/sheet/surfaces`
  const views = sheet.surfaceViews
  try {
    const files: { file: string; text: string }[] = []
    for (const file of (await port.list(dir).catch(() => [])).filter((name) => name.endsWith('.json'))) {
      // A file gone since the listing is passed over.
      const text = await port.read(`${dir}/${file}`).catch(() => undefined)
      if (text !== undefined) files.push({ file, text })
    }
    const surface = surfaceOf(files, await port.now(), sheet.remote)
    if (views === sheet.surfaceViews && JSON.stringify(surface) !== JSON.stringify(sheet.surface ?? null)) {
      sheet.surface = surface
      port.redraw()
    }
  } catch (error) {
    port.log(`sheet: the registrations could not be read: ${message(error)}`)
  }
}

/** The line above the prompt (§8.3), in a terminal session under the sheet whose start has answered: from the view held, and the link the band holds. */
function bandNow(): string | undefined {
  const gen = current()
  if (!isTerminal() || !isStarted(gen) || gen.held === undefined) {
    return undefined
  }
  return bandLine({ open: gen.held.open.length, owed: gen.held.owedAcrossStop }, sheet.surface === undefined ? gen.held.surface : sheet.surface, gen.session)
}

/**
 * The deliveries' blocks the conversation holds, read once (M5): a row whose
 * question the view does not hold draws its receipt from them. Read when a
 * row first needs it, which for a resumed conversation's rows is its start;
 * where the conversation cannot be read yet (C0's P5: a copy's first start),
 * once more after a turn has started. Only for drawing: a read that fails
 * leaves the rows without receipts.
 */
function wantDeliveries() {
  const port = sheet.port
  const gen = current()
  if (port === undefined || gen === undefined) {
    sheet.isDeliveryWanted = true
    return
  }
  sheet.isDeliveryWanted = false
  const read = gen.deliveriesRead
  if (read !== undefined && (read.state !== 'failed' || read.isRetried || sheet.turns <= read.turns)) {
    return
  }
  const isRetry = read?.state === 'failed'
  gen.deliveriesRead = { state: 'reading' }
  void port.api().then(
    (api) => {
      // What the landing hook saw since is as new as anything the read finds.
      deliveriesHeld(api).forEach((outcome, id) => {
        if (!gen.delivered.has(id)) gen.delivered.set(id, outcome)
      })
      gen.deliveriesRead = { state: 'done' }
      port.redraw()
    },
    (error: unknown) => {
      gen.deliveriesRead = { state: 'failed', turns: sheet.turns, isRetried: isRetry }
      port.log(`sheet: the conversation could not be read for the deliveries' receipts (${message(error)})`)
    },
  )
}

/** What a call's row reads beyond its call (I11): the view's while the record lives, the deliveries' blocks for what it does not hold. */
function rowFacts(ids: readonly string[]) {
  const gen = current()
  const view = isSheetChosen() ? gen?.held : undefined
  if (ids.some((id) => view === undefined || (!view.open.some((q) => q.id === id) && view.closed[id] === undefined))) {
    wantDeliveries()
  }
  return { ...(view !== undefined && { view }), delivered: gen?.delivered ?? new Map<string, Delivered>() }
}

/**
 * The line above the prompt (§8.3): drawn above what the hooks beneath
 * drew, the place today's line has, so the to-human view's line (a plugin
 * seated outside this one) stays under it; not while a survey holds the band.
 */
export function registerSheetBand(on: On) {
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const line = bandNow()
    if (line === undefined || e.props.hasSurvey) {
      return next(e)
    }
    const inner = await next(e)
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        <Text dimColor>{line}</Text>
        {inner}
      </Box>
    )
  })
}

// ------------------------------------------------------------------ a call (I6; M3's decisions)

type Capture =
  | { ok: true; kind: 'text'; body: string; startLine: number; numLines: number; totalLines: number; abs: string; size: number; mtimeMs: number }
  | { ok: true; kind: 'image'; body: string; mediaType: string; abs: string; size: number; mtimeMs: number }
  | { ok: false; reason: string }

/**
 * A reference captured through the engine's own Read (C0's P3): the
 * permission decision first (`$.tool.check`, which runs the other plugins'
 * guards and the settings' rules and opens no dialog), and only on `allow`
 * the Read (`$.tool.call`, whose result a guard's `tool.call` hook scrubs),
 * then where the file lands, its size and modification time.
 */
async function capture(port: Port, reference: Reference, cwd: string): Promise<Capture> {
  const input = readInput(reference, cwd)
  let refusal: string | undefined
  try {
    refusal = checkRefusal(await port.check(input))
  } catch (error) {
    refusal = message(error)
  }
  if (refusal !== undefined) {
    return { ok: false, reason: refusal }
  }
  let read: unknown
  try {
    read = await port.readFile(input)
  } catch (error) {
    return { ok: false, reason: message(error) }
  }
  const captured = capturedOf(read)
  if (!captured.ok) {
    return captured
  }
  try {
    const stat = await port.stat(input.file_path)
    return { ...captured, abs: stat.realPath ?? input.file_path, size: stat.size, mtimeMs: stat.mtimeMs }
  } catch (error) {
    return { ok: false, reason: message(error) }
  }
}

/** The asker of a call: the main conversation, or the subagent by its id and its name (its description, else its type). */
function askerOf(agentId: string, agents: { id: string; description: string; type: string }[] | undefined): Asker {
  const agent = agents?.find((candidate) => candidate.id === agentId)
  return { agentId, name: agent?.description || agent?.type || agentId }
}

/**
 * The conversation's floor (I10), read once and kept: the conversation's
 * ids are fixed while the record has assigned none. Undefined where it cannot
 * be read yet.
 */
async function floorNow(port: Port, gen: Gen): Promise<number | undefined> {
  if (gen.floor !== undefined) {
    return gen.floor
  }
  try {
    const { messages, api } = await port.messages()
    gen.floor = floorOfMessages(messages, api)
  } catch (error) {
    port.log(`sheet: the conversation could not be read for its ids (${message(error)})`)
  }
  return gen.floor
}

/** The result of a call's answered step: its result text, or a foreclosed call's. */
function outcomeOf(port: Port, gen: Gen, callId: string, effects: Effects, why: string, input: SheetInput): { result: string } {
  gen.toAck.add(callId)
  if (effects.result === undefined) {
    return { result: foreclosedResult(why) }
  }
  const told = announcement(input, effects.result)
  // A call of a session the process has left tells the person nothing: its session is not the one in view.
  if (told !== undefined && gen === current()) {
    port.notify(told)
  }
  return { result: effects.result }
}

/**
 * A call (M3's first decision): the whole call validated (a denial reaches no
 * step); each entry's own rules checked and its references captured, one
 * after another, before any step; the call staged (`call.json` always, a file
 * for each entry that passed and each body); the running agents read when the
 * caller or the view has a subagent; `call` ordered. With no answer, the call
 * is settled: its recorded result, a foreclosed call's `Nothing done.`, or,
 * after three settles with none, `Outcome not known yet.`.
 */
export async function askCall(port: Port, e: Record<string, unknown>): Promise<{ deny: string } | { result: string }> {
  const input = Object.fromEntries(Object.entries(e).filter(([key]) => !RESERVED.has(key)))
  const denial = validateCall(input)
  if (denial !== undefined) {
    return { deny: denial }
  }
  const call = input as SheetInput
  const gen = current()
  if (!isStarted(gen)) {
    return { result: foreclosedResult(STARTING) }
  }
  const session = gen.session
  const callId = typeof e.tool_use_id === 'string' && CALL_ID.test(e.tool_use_id) && !e.tool_use_id.startsWith('start-') ? e.tool_use_id : newName('call-')
  const agentId = typeof e.agentId === 'string' ? e.agentId : undefined
  const dir = `${staging(session)}/${callId}`
  try {
    const cwd = await port.cwd()
    const entries: Record<string, unknown>[] = []
    for (const [i, entry] of (call.ask ?? []).entries()) {
      const n = i + 1
      const problem = entryProblem(entry)
      if (problem !== undefined) {
        entries.push({ refused: problem })
        continue
      }
      const captured: Exclude<Capture, { ok: false }>[] = []
      let refused: string | undefined
      for (const reference of entry.references ?? []) {
        const one = await capture(port, reference, cwd)
        if (!one.ok) {
          refused = unreadClause(reference.path, one.reason)
          break
        }
        captured.push(one)
      }
      if (refused !== undefined) {
        // Nothing of a refused entry is staged, so nothing of its files reaches the record.
        entries.push({ refused })
        continue
      }
      const captures: Record<string, unknown>[] = []
      for (const [m, one] of captured.entries()) {
        const file = `ref-${n}-${m + 1}`
        await port.write(`${dir}/${file}`, one.body)
        const { body: _, ...rest } = one
        captures.push({ ...rest, file })
      }
      await port.write(`${dir}/entry-${n}.json`, JSON.stringify(entry))
      entries.push({ file: `entry-${n}.json`, captures })
    }
    const asker = agentId === undefined ? 'main' : askerOf(agentId, await port.agents().catch(() => undefined))
    await port.write(`${dir}/call.json`, JSON.stringify({ asker, entries, withdraw: call.withdraw ?? [] }))
  } catch (error) {
    // Never ordered: the sheet is as it was.
    port.log(`sheet: call ${callId} could not be staged: ${message(error)}`)
    return { result: foreclosedResult(`its input could not be staged: ${message(error)}`) }
  }
  const view = gen.held
  const floor = view === undefined || view.nextId === 1 ? await floorNow(port, gen) : undefined
  // The running agents as each step is ordered: the call's after its staging (a capture can be slow), each settle's
  // then, so an agent that stopped meanwhile is not named.
  const running = () => (agentId !== undefined || hasSubagent(gen.held) || gen.sentTo.size > 0 ? runningAgents(port, gen).catch(() => undefined) : Promise.resolve(undefined))
  const first = await step(port, gen, { event: 'call', call: { callId, ...(floor !== undefined && { floor }) } }, await running())
  if (first.ok) {
    return outcomeOf(port, gen, callId, first.effects, 'a settle foreclosed it', call)
  }
  for (let i = 0; i < SETTLES; i++) {
    const settled = await step(port, gen, { event: 'settle', call: { callId } }, await running())
    if (settled.ok) {
      return outcomeOf(port, gen, callId, settled.effects, first.error, call)
    }
  }
  gen.unsettled.add(callId)
  return { result: NOT_KNOWN }
}

// ------------------------------------------------------------------ the start (I8, I10)

/**
 * The floor at a start (I10): none to find in a new conversation (a
 * startup, a /clear); a resumed session's and a /branch's from the
 * transcript, read whole or searched when it is too large; else from the
 * conversation the engine holds, which a launch's first start cannot read
 * yet (C0's P5), and then every call carries it.
 */
async function floorAtStart(port: Port, gen: Gen, source: StartSource, transcript: string): Promise<number | undefined> {
  if (source === 'startup' || source === 'clear') {
    return 0
  }
  if (await port.exists(transcript).catch(() => false)) {
    try {
      const size = await port.size(transcript)
      if (size !== undefined && size <= READ_LIMIT) {
        return floorOfLines((await port.read(transcript)).split('\n'))
      }
      const search = await port.exec(floorSearchArgs(transcript))
      if (search.exitCode === 1) return 0
      const floor = search.exitCode === 0 && !search.isStdoutTruncated ? floorOfSearch(search.stdout) : undefined
      if (floor !== undefined) return floor
      port.log(`sheet: the transcript's search ${search.exitCode === 0 ? 'printed no floor' : `exited ${search.exitCode}`}; the floor goes with the calls`)
    } catch (error) {
      port.log(`sheet: the transcript could not be read for its ids (${message(error)})`)
    }
    return undefined
  }
  return floorNow(port, gen)
}

/**
 * A resume's or a copy's start made ready (I10; M5): the conversation's floor
 * read, and for a resume its open asks of today's tool staged; then kept as
 * the start owed, under the nonce `preparing` kept before anything was
 * awaited, so a reload in between makes it ready again. Undefined when
 * another start took its place meanwhile.
 */
async function prepareStart(port: Port, gen: Gen): Promise<NonNullable<SheetKept['starting']> | undefined> {
  const preparing = sheet.kept?.preparing
  const isMine = () => gen === current() && sheet.kept?.preparing?.nonce === preparing?.nonce
  if (preparing === undefined || !isMine()) {
    return undefined
  }
  const floor = await floorAtStart(port, gen, preparing.source, preparing.transcript)
  if (!isMine()) {
    return undefined
  }
  if (floor !== undefined) {
    gen.floor = floor
  }
  // A resume's open asks of today's tool go with its start, which imports them once (M5); a copy's never do: its
  // first start records that it imports nothing.
  const today = preparing.source === 'resume' ? await stageToday(port, gen.session, preparing.nonce, preparing.transcript, floor !== undefined) : undefined
  if (!isMine()) {
    return undefined
  }
  const starting = { nonce: preparing.nonce, source: preparing.source, ...(floor !== undefined && { floor }), transcript: preparing.transcript, ...(today !== undefined && { today }) }
  keep({ preparing: undefined, starting })
  return starting
}

/**
 * The asks of today's tool a resume's start imports (M5; §9): the start reads
 * the transcript itself, as the ask reads it (`readTodayAsks`, its own calls:
 * no hook waits on another's work), and stages each open ask as a file of its
 * own under the start's nonce, its call's time where the transcript holds
 * one, else now. A read that was not definite (a search that failed or was
 * cut) sends none and says so, so nothing is recorded and the next start reads
 * again; so does a staging that fails. With the conversation's ids not known
 * (its floor's search failed) the asks go marked `floorUnknown`: an import
 * takes ids, which must not be ones the conversation used before, so the step
 * imports them only into a record that has assigned an id, past them, and
 * otherwise records nothing for the next start to read again.
 */
async function stageToday(port: Port, session: string, nonce: string, transcript: string, isFloorKnown: boolean): Promise<NonNullable<NonNullable<SheetKept['starting']>['today']>> {
  const none = { definite: false, asks: [] }
  const read = await readTodayAsks(port, transcript).catch((error: unknown) => (port.log(`sheet: the asks of today's tool could not be read (${message(error)})`), undefined))
  if (read === undefined || !read.isDefinite) {
    port.log("sheet: the read of the session's asks of today's tool was not definite; none is imported at this start")
    return none
  }
  try {
    const now = new Date(await port.now()).toISOString()
    const asks: { file: string }[] = []
    for (const [i, ask] of read.asks.entries()) {
      const file = `start-${nonce}/ask-${i + 1}.json`
      const askedAt = ask.askedAt !== undefined && TIME.test(ask.askedAt) ? ask.askedAt : now
      await port.write(`${staging(session)}/${file}`, JSON.stringify({ callId: ask.callId, askedAt, questions: ask.questions }))
      asks.push({ file })
    }
    if (!isFloorKnown) {
      port.log("sheet: the conversation's ids are not known; the asks of today's tool go marked so, imported only into a record that has assigned an id")
    }
    return { definite: true, asks, ...(!isFloorKnown && { floorUnknown: true }) }
  } catch (error) {
    port.log(`sheet: the asks of today's tool could not be staged (${message(error)}); none is imported at this start`)
    return none
  }
}

/** I2's time (K6): what a staged ask's `askedAt` must be. */
const TIME = /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$/

/** A record's identity as `sminos sheet witness` prints it: its directory's device and inode, and its nonce. */
const IDENTITY = /^[0-9]+:[0-9]+:[0-9a-f]{32}$/

/**
 * The record a /clear left, as it is now (`sminos sheet witness`, its nonce
 * minted if none is): its identity; null when there is no record; undefined
 * when it has none that can be told, so it is kept.
 */
async function witnessLeft(port: Port, left: string): Promise<string | null | undefined> {
  try {
    const out = await port.run(['sheet', 'witness', '--session', left])
    const identity = out.stdout.trim()
    if (out.exitCode === 0 && IDENTITY.test(identity)) {
      return identity
    }
    if (out.exitCode === 3) {
      return null
    }
    port.log(`sheet: the sheet ${left} a /clear left has no identity to remove it by (exit ${out.exitCode}: ${out.stderr.trim().slice(0, 300)}); it stays`)
  } catch (error) {
    port.log(`sheet: the sheet ${left} a /clear left could not be witnessed (${message(error)}); it stays`)
  }
  return undefined
}

/**
 * The record a /clear left, removed (U10): `sminos sheet remove --cleared`,
 * that record alone (`witnessed`), and not while a process other than this
 * one (`--clearing`, the engine's pid) runs the session: a resume during a
 * retry keeps it, as does a pid not known. True once it is gone or was never
 * there.
 */
async function removeLeft(port: Port, left: string, witnessed: string): Promise<boolean> {
  try {
    const clearing = await port.enginePid()
    if (clearing === undefined) {
      port.log(`sheet: the sheet ${left} a /clear left is kept: this process's pid is not known, so a resume of that session elsewhere could not be told`)
      return false
    }
    const out = await port.run(['sheet', 'remove', '--session', left, '--cleared', '--witness', witnessed, '--clearing', clearing])
    if (out.exitCode === 0 || out.exitCode === 3) {
      return true
    }
    port.log(`sheet: the sheet ${left} a /clear left was not removed (exit ${out.exitCode}: ${out.stderr.trim().slice(0, 300)})`)
  } catch (error) {
    port.log(`sheet: the sheet ${left} a /clear left was not removed: ${message(error)}`)
  }
  return false
}

/**
 * A process starts a session (E11): the session it is in now, the floor of
 * its conversation, and its `start` step, under a nonce of its own that every
 * retry repeats (I5). Kept, so a reload before it answers orders it still.
 * Answers the context for the conversation (I10), which the SessionStart
 * returns; when `isRouted` (the SessionStart has returned already) or the
 * start gives no answer, the start that answers puts it on the next result
 * or prompt route instead.
 */
async function sessionStarted(port: Port, source: StartSource, session: string, transcript: string, isRouted = false): Promise<string | undefined> {
  if (sheet.gen?.session !== session || source === 'clear') {
    // Another conversation in this process (a /clear, a /branch, a fork):
    // the work of the one before is retired, as at a /clear.
    retire()
    sheet.gen = newGen(session)
  }
  const gen = sheet.gen
  gen.transcript = transcript
  gen.isStartRouted = isRouted
  // A new conversation's floor is known at once, and its start is kept for a
  // retry before anything is awaited; a resumed one's or a copy's is kept as
  // being made ready, also before anything is awaited, and made ready first.
  const isNew = source === 'startup' || source === 'clear'
  const nonce = newName('n')
  keep({ session, started: undefined, ...(isNew ? { starting: { nonce, source, floor: 0, transcript }, preparing: undefined } : { starting: undefined, preparing: { nonce, source: source as 'resume' | 'fork', transcript } }) })
  // The SessionStart names only the new session (C0's P5): the session a
  // /clear left is the one the end hook kept. Its removal is ordered behind
  // that session's start still in flight, in the background: never a
  // prerequisite of this session's start.
  const left = source === 'clear' ? sheet.kept?.left : undefined
  if (left !== undefined) {
    removeLeftLater(port, left)
  }
  if (isNew) {
    gen.floor = 0
  }
  const started = await startStep(port, gen)
  if (started === undefined || !started.answer.ok) {
    // The retry the next check orders puts its context on a route.
    gen.isStartRouted = true
    return undefined
  }
  return gen.isStartRouted ? undefined : started.context
}

/**
 * Removes the record a /clear left, in the background, once the start of
 * that session still in flight (if any) has landed, so no late start makes
 * it again; one removal at a time for a session. The record is witnessed
 * first, at the clear, and only that record goes: a removal delayed behind
 * the start never takes one a resume of the left session made since. With
 * no record at the clear, the one the start in flight makes is the clear's
 * too, witnessed once it lands.
 */
function removeLeftLater(port: Port, left: string) {
  if (sheet.removing.has(left)) {
    return
  }
  sheet.removing.add(left)
  const inFlight = sheet.retiring
  const witnessing = witnessLeft(port, left)
  void (async () => {
    try {
      let witnessed = await witnessing
      await inFlight
      if (sheet.gen?.session === left) {
        // This process is back in the session it left (a /resume): the record is its own again.
        return
      }
      if (witnessed === null && inFlight !== undefined) {
        witnessed = await witnessLeft(port, left)
      }
      const isGone = witnessed === null || (witnessed !== undefined && (await removeLeft(port, left, witnessed)))
      if (isGone && sheet.kept?.left === left) {
        keep({ left: undefined })
      }
    } finally {
      sheet.removing.delete(left)
    }
  })()
}

// ------------------------------------------------------------------ the hooks

/** The sminos home as the command resolves it: SMINOS_HOME, else DAEMON_HOME, else ~/.claude/sminos. */
async function sminosHome($: EngineInterface): Promise<string> {
  const own = (await $.env.get('SMINOS_HOME')) || (await $.env.get('DAEMON_HOME'))
  return own || `${(await $.env.get('HOME')) ?? ''}/.claude/sminos`
}

/** The engine, as the sheet reaches it: closures made here, in this file's hook. */
function portOf($: EngineInterface): Port {
  const command = `${$.plugin.root}/skills/sminos/scripts/sminos`
  return {
    run: (args, stdin) => $.process.run([command, ...args], { ...(stdin !== undefined && { stdin }), timeoutMs: STEP_TIMEOUT_MS }),
    exec: (argv) => $.process.run(argv, { timeoutMs: STEP_TIMEOUT_MS }),
    enginePid: () =>
      $.process.hookEnv().then(
        (env) => (/^[1-9][0-9]*$/.test(env.CLAUDE_PID ?? '') ? env.CLAUDE_PID : undefined),
        () => undefined,
      ),
    write: (path, text) => $.fs.write(path, text),
    read: (path) => $.fs.read(path),
    size: (path) =>
      $.fs.stat(path).then(
        (stat) => stat.size,
        () => undefined,
      ),
    exists: (path) => $.fs.exists(path),
    stat: async (path) => {
      const stat = await $.fs.stat(path, { resolve: true })
      return { ...(stat.realPath !== undefined && { realPath: stat.realPath }), size: stat.size, mtimeMs: stat.mtimeMs }
    },
    check: (input) => $.tool.check({ tool: 'Read', input }),
    readFile: (input) => $.tool.call({ tool: 'Read', ...input } as Parameters<typeof $.tool.call>[0]),
    cwd: () => $.session.cwd(),
    agents: async () => (await $.agent.list()).map((agent) => ({ id: agent.id, description: agent.description, type: agent.type, status: agent.status })),
    messages: async () => {
      const [messages, api] = await Promise.all([$.session.messages(), $.session.messages({ as: 'api' })])
      return { messages: messages.map((m) => ({ role: m.role, text: m.text, toolUses: m.toolUses.map((use) => ({ tool: use.tool, ...(use.text !== undefined && { text: use.text }) })) })), api }
    },
    notify: (text) => void $.ui.notify(text).catch((error: unknown) => $.ui.log(`sheet: the question's notification failed (${message(error)})`, { to: 'debug' })),
    log: (text) => $.ui.log(text, { to: 'debug' }),
    keep: (kept) => void $.state.set(KEPT, kept).catch((error: unknown) => $.ui.log(`sheet: the choice is not kept for a reload: ${message(error)}`, { to: 'debug' })),
    publish: async (snapshot) => void (await $.state.set({ plugin: 'sminos', key: 'ask' }, snapshot)),
    invalidate: () => $.ui.invalidate('tool.describe'),
    submit: (text) => $.prompt.submit({ text }),
    send: (agentId, text) => $.session.send({ to: { agentId }, text }),
    after: (fn) => void $.clock.after(0, fn),
    api: () => $.session.messages({ as: 'api' }),
    redraw: () => $.ui.invalidate('ui.render'),
    toast: (text) => $.ui.toast(text),
    list: async (path) => (await $.fs.list(path)).map((entry) => entry.name),
    now: () => $.clock.now(),
  }
}

/** The choice a module before this one kept, when it is one this module reads (shape 1). */
async function keptBefore($: EngineInterface): Promise<SheetKept | undefined> {
  const read = await $.state.get(KEPT).catch(() => undefined)
  const value: unknown = read?.value
  return isRecord(value) && value.shape === 1 && ['sheet', 'today', 'none'].includes(String(value.choice)) && typeof value.session === 'string' ? (value as SheetKept) : undefined
}

/** Whether a module before this one served today's ask here: its snapshot is kept. */
async function hasKeptAsk($: EngineInterface): Promise<boolean> {
  const read = await $.state.get({ plugin: 'sminos', key: 'ask' }).catch(() => undefined)
  return read?.value !== undefined
}

/**
 * Registers the sheet's hooks, before the ask's of the same events, so they
 * are the outer ones: a hook of the sheet's handles what is the sheet's and
 * passes the rest on (I11). Each event is taken with a matcher every input
 * meets: the engine admits one unmatched registration per event per module.
 */
export function registerSheet(on: On) {
  // The ask takes up a session's asks only once the choice is made, whenever
  // a SessionStart comes.
  deferAskToChoice()
  // The choice, made at the process's first session.start and kept (I8);
  // the ask yields before its own session.start runs. A reload takes the kept
  // choice up and drains for a view (E13).
  on('session.start', { cwd: /^/ }, async ($, e, next) => {
    const kept = await keptBefore($)
    const session = await $.session.id()
    sheet.home = await sminosHome($)
    sheet.remote = ((await $.env.get('SSH_CONNECTION')) ?? '') !== ''
    const port = portOf($)
    const chosen = await chooseStart({
      kept,
      hasKeptAsk: kept === undefined && (await hasKeptAsk($)),
      session,
      isInteractive: e.isInteractive,
      env: {
        SMNS_INTERNAL: () => $.env.get('SMNS_INTERNAL'),
        MAWS_QUESTION_SHEET: () => $.env.get('MAWS_QUESTION_SHEET'),
        MAWS_NATIVE_TO_HUMAN: () => $.env.get('MAWS_NATIVE_TO_HUMAN'),
        SSH_CONNECTION: () => $.env.get('SSH_CONNECTION'),
        SMINOS_QUESTION_SHEET: () => $.env.get('SMINOS_QUESTION_SHEET'),
      },
      hasRecord: () => $.fs.exists(`${sheet.home}/sheet/${session}/state.json`).catch(() => false),
      probe: async (remote): Promise<Probe | undefined> => {
        try {
          const out = await port.run(['sheet', 'probe', '--session', session, ...(remote ? ['--remote'] : [])])
          const probe: unknown = JSON.parse(out.stdout)
          return isRecord(probe) && typeof probe.record === 'boolean' ? (probe as Probe) : undefined
        } catch {
          return undefined
        }
      },
    })
    chosen.log?.forEach((line) => port.log(line))
    port.log(`sheet: ${chosen.choice}${chosen.runner === undefined ? '' : ` (${chosen.runner})`}: ${chosen.why}`)
    // A start owed is its session's: one kept for another session (the process moved on before this reload) is not
    // ordered under this one, its nonce, transcript and asks being that session's.
    const owed = kept?.session === session ? { starting: kept.starting, preparing: kept.preparing } : {}
    sheet.kept = {
      shape: 1,
      choice: chosen.choice,
      ...(chosen.runner !== undefined && { runner: chosen.runner }),
      session,
      ...(kept?.started !== undefined && { started: kept.started }),
      ...(owed.starting !== undefined && { starting: owed.starting }),
      ...(owed.preparing !== undefined && { preparing: owed.preparing }),
      ...(kept?.left !== undefined && { left: kept.left }),
    }
    sheet.port = port
    if (sheet.gen?.session !== session) {
      sheet.gen = newGen(session)
      const start = owed.starting ?? owed.preparing
      if (start !== undefined) {
        // A start a module before this reload left unanswered, or still being made ready (made ready again then, under
        // its nonce): its retry searches the transcript it was given, and its context goes by a route, its
        // SessionStart long returned.
        sheet.gen.transcript = start.transcript
        sheet.gen.isStartRouted = true
      }
    }
    port.keep(sheet.kept)
    if (sheet.isDeliveryWanted) {
      // A row drawn before this asked for the deliveries' blocks (M5), whatever the choice.
      wantDeliveries()
    }
    const early = sheet.early
    sheet.early = undefined
    if (chosen.choice !== 'sheet') {
      askChoiceMade()
      return next(e)
    }
    sheet.runner = chosen.runner ?? 'terminal'
    sheet.isWithdrawing = true
    yieldAsk()
    askChoiceMade()
    const result = await next(e)
    try {
      await $.tool.register({ name: 'AskUserQuestion', description: DESCRIPTION, inputSchema: INPUT_SCHEMA })
    } catch (error) {
      // No question tool to ask through: the built-in is put back.
      sheet.isWithdrawing = false
      port.log(`sheet: the tool is not registered: ${message(error)}`)
    }
    if (sheet.wasBuiltinDescribed) {
      port.invalidate()
    }
    $.clock.every(TICK_MS, () => tick(port))
    if (early !== undefined) {
      // Its SessionStart has returned: the start's context goes by the next result or prompt route. Awaited, as its
      // own calls (a resume's read of its asks included), so no prompt enters before the start has answered.
      await sessionStarted(port, early.source, early.session, early.transcript, true)
    }
    if (kept?.choice === 'sheet' && (kept.started === session || owed.starting !== undefined || owed.preparing !== undefined)) {
      void check(port)
    }
    return result
  }).catch((_, e, next) => {
    // A choice that failed is no sheet: the ask serves as today.
    askChoiceMade()
    return next(e)
  })

  // A process starts a session (E11): its start step; a compaction (E12): a
  // drain that composes the context M4 hands the model.
  on('classic.SessionStart', { hook_event_name: 'SessionStart' }, async (_, e, next) => {
    const port = sheet.port
    if (sheet.kept === undefined && e.source !== 'compact') {
      // The choice is still being made: its session.start orders this start.
      sheet.early = { source: e.source, session: e.session_id, transcript: e.transcript_path }
      return next(e)
    }
    if (port === undefined || !isSheetChosen()) {
      return next(e)
    }
    let context: string | undefined
    if (e.source === 'compact') {
      const gen = current()
      if (isStarted(gen)) {
        // Its own step, awaited as its own `$` call (K4 allows it; the
        // record's lock serializes it with any other step): a drain that
        // composes I10's context, which this hook returns. With no answer
        // the next check's drain composes it for the next result or prompt
        // route.
        const answer = await step(port, gen, { event: 'drain', context: 'compact' })
        if (answer.ok) {
          context = answer.effects.context
        } else {
          gen.isContextOwed = true
        }
      }
    } else {
      context = await sessionStarted(port, e.source, e.session_id, e.transcript_path)
    }
    const result = await next(e)
    return context === undefined || context === '' ? result : { ...result, additionalContext: [...(result.additionalContext ?? []), context] }
  }).catch((_, e, next) => next(e))

  // A /clear leaves the session (E15): its record goes, here first, since the
  // next SessionStart names only the new session; not awaited, as a session's
  // end is given little time.
  on('session.end', { sessionId: /./ }, (_, e, next) => {
    const port = sheet.port
    if (port !== undefined && isSheetChosen() && e.reason === 'clear') {
      // The session's work retired, its start forgotten, so no trigger orders
      // it again; a start already in flight lands before the removal.
      retire()
      keep({ left: e.sessionId, started: undefined, starting: undefined, preparing: undefined })
      removeLeftLater(port, e.sessionId)
    }
    return next(e)
  })

  // The tool inline, under the sheet's description; the built-in withdrawn.
  on('tool.describe', { tool: SHEET_TOOL }, async (_, e, next) => {
    const described = await next(e)
    return isSheetChosen() ? ({ ...described, description: DESCRIPTION, isDeferred: false } as ToolDescribeResult) : described
  })
  on('tool.describe', { tool: 'AskUserQuestion' }, async (_, e, next) => {
    const described = await next(e)
    sheet.wasBuiltinDescribed = true
    return isSheetChosen() && sheet.isWithdrawing ? ({ description: WITHDRAWN, isDeferred: true } as ToolDescribeResult) : described
  })

  // The tool's own call. Elsewhere today's tool answers it.
  on('tool.call', { tool: SHEET_TOOL }, async (_, e, next) => {
    const port = sheet.port
    if (port === undefined || !isSheetChosen()) {
      return next(e)
    }
    // K4's check first: this hook answers the call and the catch-all below never sees it.
    triggerCheck()
    const id = (e as { tool_use_id?: string }).tool_use_id
    const gen = current()
    if (id !== undefined && gen !== undefined) sheet.dispatching.set(id, gen)
    const answered = await askCall(port, e as unknown as Record<string, unknown>)
    if (id !== undefined) sheet.dispatching.delete(id)
    // The tool's own result is a route like any other's (I9).
    return withResultRoute(gen, e.agentId, next.origin, next.signal, answered)
  }).catch((_, e, next) => {
    if (next.called || !isSheetChosen()) {
      return next(e)
    }
    // The hook failed (it ran out of time, or threw) with the call perhaps
    // committed: settled at the next trigger, its outcome a notice.
    // Bound to the generation the call was dispatched in: one the process has
    // left settles it never (no trigger reads a retired generation).
    const id = (e as { tool_use_id?: string }).tool_use_id
    if (id !== undefined) {
      sheet.dispatching.get(id)?.unsettled.add(id)
      sheet.dispatching.delete(id)
    }
    return { result: NOT_KNOWN }
  })

  // The built-in, withdrawn: a model's call of it is refused.
  on('tool.call', { tool: 'AskUserQuestion' }, (_, e, next) => {
    // K4's check first, as the refusal answers without reaching the catch-all below.
    triggerCheck()
    return isSheetChosen() && sheet.isWithdrawing && next.origin.plugin === 'engine' ? { deny: WITHDRAWN } : next(e)
  }).catch((_, e, next) => (!next.called && isSheetChosen() && sheet.isWithdrawing && next.origin.plugin === 'engine' ? { deny: WITHDRAWN } : next(e)))

  // The check of K4 at every tool call; the result route on the model's
  // main-loop calls (I9).
  on('tool.call', { tool: /^/ }, async (_, e, next) => {
    triggerCheck()
    const gen = current()
    const result = await next(e)
    return withResultRoute(gen, e.agentId, next.origin, next.signal, result)
  })

  // The prompt route (I9): what is ready rides any prompt that enters, as
  // context of its own; what a prompt dropped beneath, or one that entered
  // without it, did not carry is put back, each entry on its own. In a
  // MAWS-run session only a start's or a compaction's context rides it.
  on('prompt.submit', { text: /^/ }, async (_, e, next) => {
    triggerCheck()
    const gen = routable()
    // A slash command's prompt is passed over: what it runs may never reach the model.
    if (gen === undefined || e.command !== undefined) {
      return next(e)
    }
    const port = sheet.port as Port
    const taken = take(gen, 'prompt')
    if (taken.entries.length === 0) {
      return next(e)
    }
    const flight = taken.flight
    if (flight !== undefined && e.turnId !== undefined) {
      // Typed over a running turn: it enters that turn, or the next. Marked before the hooks beneath run, so a
      // turn that ends meanwhile hands it to the next turn rather than leaving it to none.
      flight.tentative = e.turnId
    }
    let result: Awaited<ReturnType<typeof next>>
    try {
      result = await next({ ...e, context: [...(e.context ?? []), ...taken.entries] })
    } catch (error) {
      putBack(gen, taken, [])
      if (flight !== undefined) failFlight(port, gen, flight, message(error))
      throw error
    }
    const entered = result.drop === undefined ? [...(result.context ?? [])] : []
    putBack(gen, taken, entered)
    if (flight === undefined) {
      return result
    }
    if (result.drop !== undefined) {
      failFlight(port, gen, flight, result.drop)
    } else if (!keysIn(entered).some((key) => flight.keys.includes(key))) {
      failFlight(port, gen, flight, 'a hook took it out of the prompt')
    } else if (gen.flights.includes(flight) && e.turnId === undefined) {
      // Its prompt opened a turn, started by now.
      turnOf(flight)
    }
    return result
  }).catch((_, e, next) => next(e))

  // The main turn: which runs (the idle route waits for none), and which
  // flights a turn's start makes its own. A subagent that starts again is
  // no longer stopped.
  on('turn.start', { turnId: /./ }, (_, e, next) => {
    if (e.agentId === undefined) {
      sheet.mainTurn = e.turnId
      sheet.turns += 1
      if (sheet.port !== undefined) publish(sheet.port)
      for (const flight of current()?.flights ?? []) {
        if (flight.awaitsTurn === true) {
          flight.awaitsTurn = false
          flight.turnId = e.turnId
        }
      }
    } else {
      sheet.stopped.delete(e.agentId)
    }
    return next(e)
  })

  // The check of K4; a main turn's end settles the flights it holds (I9).
  on('turn.complete', { turnId: /./ }, (_, e, next) => {
    triggerCheck()
    if (e.agentId === undefined) {
      if (sheet.mainTurn === e.turnId) sheet.mainTurn = undefined
      if (sheet.port !== undefined) publish(sheet.port)
      const gen = routable()
      if (gen !== undefined) {
        void endTurn(sheet.port as Port, gen, e.turnId, e.reason)
      }
    }
    return next(e)
  })

  // Landing (I9): a row of the routes' kinds, as stored, that holds a block
  // lands its keys, whichever module sent it. A human's prompt that quotes
  // one, or a steer, is another kind of row and lands nothing.
  on('session.append', { door: /./ }, async (_, e, next) => {
    const stored = await next(e)
    const gen = routable()
    // In a MAWS-run session only a `delivered` line moves an outcome of the main conversation (§5.4).
    if (gen !== undefined && isTerminal() && stored.message !== undefined && isRouteRow(e)) {
      const texts = contentTexts(stored.message.content)
      const keys = keysIn(texts)
      // What it delivered, for the rows' receipts (M5).
      deliveredIn(texts).forEach((outcome, id) => gen.delivered.set(id, outcome))
      if (keys.length > 0) {
        sheet.port?.log(`sheet: a ${e.door} row (${JSON.stringify(e.origin)}) landed ${keys.length} ${keys.length === 1 ? 'key' : 'keys'}: ${keys.slice(0, 3).join(', ')}${keys.length > 3 ? ', …' : ''}`)
        land(sheet.port as Port, gen, keys)
      }
    }
    return stored
  })

  // A call's row (§8.3; I11): in every session, whatever the choice, a stored
  // call of the sheet's form, from its input and its result alone, with the
  // receipts the view or the deliveries give. No head of its own: the
  // engine's tool row has its head, and ctrl+o (expanded) shows the engine's
  // whole row. A call still running, refused whole, or cut is the engine's.
  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    const { tool, input, output, isRunning, isErrored, isInterrupted, isExpanded } = e.props
    const parsed = tool === SHEET_TOOL && isSheetCall(input) && !isRunning && !isErrored && !isInterrupted && isExpanded !== true ? parseResult(resultTextOf(output)) : undefined
    if (parsed === undefined || !isSheetCall(input)) {
      return next(e)
    }
    const ids = parsed.form === 'sentences' ? [...parsed.added, ...parsed.revised].map((item) => item.id) : []
    const lines = rowLines(input, parsed, rowFacts(ids))
    const head = await next(e)
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        {head}
        <Box flexDirection="row">
          <Text dimColor>{'  ⎿  '}</Text>
          <Box flexDirection="column">
            {lines.map((line, i) => (
              <Text key={`${i}:${line}`} color="inactive" wrap="truncate-end">
                {line}
              </Text>
            ))}
          </Box>
        </Box>
      </Box>
    )
  })
  // Its result block: the row's lines stand in its place.
  on('ui.render', { component: 'ToolResult' }, async ($, e, next) => {
    const { tool, output, isErrored, isExpanded } = e.props
    if (tool !== SHEET_TOOL || isErrored || isExpanded === true || parseResult(resultTextOf(output)) === undefined) {
      return next(e)
    }
    const { Box } = $.ui.resolve(e)
    return <Box />
  })

  // A subagent stops (E14): a drain, so its pending outcomes go to the main
  // conversation; and, when it stopped with questions open, a notice.
  on('classic.SubagentStop', { hook_event_name: 'SubagentStop' }, (_, e, next) => {
    const gen = current()
    if (isSheetChosen()) {
      sheet.stopped.add(e.agent_id)
    }
    if (sheet.port !== undefined && isStarted(gen)) {
      // Named from the view held now, so the route that opens next carries
      // it: a background agent's completion enters as a prompt a few
      // milliseconds after its stop, before any step could answer (2.1.331).
      // The drain's view names a question the held one did not have yet.
      noticeEnded(gen, e.agent_id)
      void drain(sheet.port, gen).then(() => noticeEnded(gen, e.agent_id))
    }
    return next(e)
  })
}

/**
 * The result route (I9): a call of the model's main loop that returned, not
 * denied and not aborted, carries what is ready as context on its result:
 * the envelope, a flight of the running turn, and the notices and a context
 * waiting. Only into the generation it was dispatched in (`dispatched`): a
 * call that ran across a session change (a fork, a /clear) returns as it was,
 * carrying nothing of the session after it.
 */
function withResultRoute<R extends object>(dispatched: Gen | undefined, agentId: string | undefined, origin: { plugin: string }, signal: AbortSignal, result: R): R {
  const gen = routable()
  const { deny, context } = result as { deny?: unknown; context?: readonly string[] }
  if (gen === undefined || gen !== dispatched || !isTerminal() || agentId !== undefined || origin.plugin !== 'engine' || deny !== undefined || signal.aborted) {
    return result
  }
  const taken = take(gen, 'result')
  if (taken.entries.length === 0) {
    return result
  }
  if (taken.flight !== undefined) {
    taken.flight.turnId = sheet.mainTurn ?? '*'
  }
  return { ...result, context: [...(context ?? []), ...taken.entries] }
}

/** For tests: the same entry points the hooks use, on a port of the test's own. */
export const sheetForTests = {
  check,
  drain,
  sessionStarted,
  set: (port: Port, kept: SheetKept, home: string) => {
    sheet.port = port
    sheet.kept = kept
    sheet.home = home
    sheet.gen = newGen(kept.session)
  },
  sheet: () => sheet,
}
