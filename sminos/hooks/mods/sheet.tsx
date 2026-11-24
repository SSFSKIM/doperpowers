import type { EngineInterface, On, ToolDescribeResult } from 'claude-code'

import type { SheetKept } from '../../types/sminos'
import { askChoiceMade, deferAskToChoice, yieldAsk } from './ask'
import {
  DESCRIPTION,
  INPUT_SCHEMA,
  NOT_KNOWN,
  SHEET_TOOL,
  STARTING,
  WITHDRAWN,
  announcement,
  answerOf,
  capturedOf,
  checkRefusal,
  chooseStart,
  entryProblem,
  floorOfLines,
  floorOfMessages,
  floorSearchArgs,
  foreclosedResult,
  hasSubagent,
  isNewer,
  outcomeNotice,
  readInput,
  unreadClause,
  validateCall,
} from './sheet-model'
import type { Asker, Effects, Probe, Reference, Runner, SheetInput, StepAnswer, Verdict, View } from './sheet-model'

/**
 * The question sheet's mod (the plan
 * docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, I8, I11 and
 * M3): the start choice, the tool under the sheet's schema, a call through a
 * step, and the drains that keep the record applied. The record is the
 * command's (`sminos sheet step`, K1): the mod orders steps and keeps the last
 * view a step answered, nothing of the sheet's own. Delivery (M4), the
 * terminal's drawing (M5) and the snapshot (M6) are not here yet: answers are
 * accepted and wait in the record.
 */

/** What the mod keeps in `$.state` for the process (types/sminos.d.ts). */
const KEPT = { plugin: 'sminos', key: 'sheet' } as const

/** A step waits at most 10 s for the record's lock (I1), and the command starts in about 0.3 s. */
const STEP_TIMEOUT_MS = 20_000
/** The check of K4 runs on this timer too: a nudge can be lost, and an idle session dispatches no hook. */
export const TICK_MS = 5_000
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
  invalidate: () => void
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
  starting?: { nonce: string; attempt: Promise<Answer> }
  isChecking: boolean
}

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
}

function fresh(): Sheet {
  return { home: '', runner: 'terminal', remote: false, isWithdrawing: false, wasBuiltinDescribed: false, dispatching: new Map(), removing: new Set() }
}

const newGen = (session: string): Gen => ({ session, toAck: new Set(), unsettled: new Set(), notices: [], isDrainOwed: false, isChecking: false })

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
  sheet.kept = { ...sheet.kept, ...change }
  for (const key of Object.keys(change) as (keyof SheetKept)[]) {
    if (change[key] === undefined) delete sheet.kept[key]
  }
  sheet.port?.keep(sheet.kept)
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
  if (running === undefined && hasSubagent(gen.held)) {
    running = await runningAgents(port).catch(() => undefined)
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
  if (isNewer(gen.held === undefined ? undefined : { session: gen.session, view: gen.held }, gen.session, answer.view)) {
    gen.held = answer.view
  }
  return answer
}

async function runningAgents(port: Port): Promise<string[]> {
  return (await port.agents()).filter((agent) => RUNNING.has(agent.status)).map((agent) => agent.id)
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
 * The start step owed for the generation's session (kept as `starting`):
 * single-flight by its nonce, so a trigger while one runs joins it; ordered
 * again only once an attempt settled with no answer. Its answer marks the
 * session started only while the generation is current and the start the
 * one kept.
 */
function startStep(port: Port, gen: Gen): Promise<Answer> | undefined {
  const starting = sheet.kept?.starting
  if (starting === undefined || gen !== current()) {
    return undefined
  }
  if (gen.starting !== undefined && gen.starting.nonce === starting.nonce) {
    return gen.starting.attempt
  }
  const attempt = (async (): Promise<Answer> => {
    const answer = await step(port, gen, {
      event: 'start',
      start: { source: starting.source, nonce: starting.nonce, ...(starting.floor !== undefined && { floor: starting.floor }) },
    })
    if (answer.ok && gen === current() && sheet.kept?.starting?.nonce === starting.nonce) {
      // A start forgets every call (I5): nothing is left to acknowledge.
      gen.toAck.clear()
      keep({ started: gen.session, starting: undefined })
    }
    return answer
  })()
  gen.starting = { nonce: starting.nonce, attempt }
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
  // The running agents as the call is ordered, after its staging (a capture can be slow).
  const running = agentId !== undefined || hasSubagent(view) ? await runningAgents(port).catch(() => undefined) : undefined
  const first = await step(port, gen, { event: 'call', call: { callId, ...(floor !== undefined && { floor }) } }, running)
  if (first.ok) {
    return outcomeOf(port, gen, callId, first.effects, 'a settle foreclosed it', call)
  }
  for (let i = 0; i < SETTLES; i++) {
    const settled = await step(port, gen, { event: 'settle', call: { callId } }, running)
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
      if (search.exitCode === 0 && !search.isStdoutTruncated) return floorOfLines(search.stdout.split('\n'))
      port.log(`sheet: the transcript's search ${search.isStdoutTruncated ? 'was cut' : `exited ${search.exitCode}`}; the floor goes with the calls`)
    } catch (error) {
      port.log(`sheet: the transcript could not be read for its ids (${message(error)})`)
    }
    return undefined
  }
  return floorNow(port, gen)
}

/** The record a /clear left, removed (U10): `sminos sheet remove --cleared`. True once it is gone or was never there. */
async function removeLeft(port: Port, left: string): Promise<boolean> {
  try {
    const out = await port.run(['sheet', 'remove', '--session', left, '--cleared'])
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
 */
async function sessionStarted(port: Port, source: StartSource, session: string, transcript: string) {
  if (sheet.gen?.session !== session || source === 'clear') {
    // Another conversation in this process (a /clear, a /branch, a fork):
    // the work of the one before is retired, as at a /clear.
    retire()
    sheet.gen = newGen(session)
  }
  const gen = sheet.gen
  // A new conversation's floor is known at once, and its start is kept for a
  // retry before anything is awaited; a resumed one's is read first.
  const isNew = source === 'startup' || source === 'clear'
  keep({ session, started: undefined, starting: isNew ? { nonce: newName('n'), source, floor: 0 } : undefined })
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
  } else {
    const floor = await floorAtStart(port, gen, source, transcript)
    if (gen !== current()) {
      return
    }
    if (floor !== undefined) {
      gen.floor = floor
    }
    keep({ starting: { nonce: newName('n'), source, ...(floor !== undefined && { floor }) } })
  }
  await startStep(port, gen)
}

/**
 * Removes the record a /clear left, in the background, once the start of
 * that session still in flight (if any) has landed, so no late start makes
 * it again; one removal at a time for a session.
 */
function removeLeftLater(port: Port, left: string) {
  if (sheet.removing.has(left)) {
    return
  }
  sheet.removing.add(left)
  const inFlight = sheet.retiring
  void (async () => {
    try {
      await inFlight
      if ((await removeLeft(port, left)) && sheet.kept?.left === left) {
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
    invalidate: () => $.ui.invalidate('tool.describe'),
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
    sheet.kept = {
      shape: 1,
      choice: chosen.choice,
      ...(chosen.runner !== undefined && { runner: chosen.runner }),
      session,
      ...(kept?.started !== undefined && { started: kept.started }),
      ...(kept?.starting !== undefined && { starting: kept.starting }),
      ...(kept?.left !== undefined && { left: kept.left }),
    }
    sheet.port = port
    if (sheet.gen?.session !== session) {
      sheet.gen = newGen(session)
    }
    port.keep(sheet.kept)
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
    $.clock.every(TICK_MS, () => void check(port))
    if (early !== undefined) {
      await sessionStarted(port, early.source, early.session, early.transcript)
    }
    if (kept?.choice === 'sheet' && (kept.started === session || kept.starting !== undefined)) {
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
    if (e.source === 'compact') {
      const gen = current()
      if (isStarted(gen)) {
        // Queued, never awaited (K4: a SessionStart is held on no other
        // work): through the drain queue, so it never runs beside another
        // drain, and one that fails is owed to the next trigger. The seam
        // for M4: this drain's answer carries I10's context
        // (`effects.context`), which reaches the model by the next route a
        // context takes, as an envelope does, not through this hook's result.
        void drain(port, gen, [], 'compact')
      }
    } else {
      await sessionStarted(port, e.source, e.session_id, e.transcript_path)
    }
    return next(e)
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
      keep({ left: e.sessionId, started: undefined, starting: undefined })
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
    return answered
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

  // The check of K4 alone, at the dispatches the sheet's hooks see.
  on('tool.call', { tool: /^/ }, (_, e, next) => {
    triggerCheck()
    return next(e)
  })
  on('prompt.submit', { text: /^/ }, (_, e, next) => {
    triggerCheck()
    return next(e)
  })
  on('turn.complete', { turnId: /./ }, (_, e, next) => {
    triggerCheck()
    return next(e)
  })

  // A subagent stops (E14): a drain, so its pending outcomes go to the main conversation.
  on('classic.SubagentStop', { hook_event_name: 'SubagentStop' }, (_, e, next) => {
    const gen = current()
    if (sheet.port !== undefined && isStarted(gen)) {
      void drain(sheet.port, gen)
    }
    return next(e)
  })
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
